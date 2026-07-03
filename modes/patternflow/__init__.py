"""
Patternflow — generative LED pattern mode for led-matrix.

Encoder control (optional hardware):
  K4 long-press  → cycle through patterns
  K1–K4 turn     → pattern-specific parameters (hue, speed, mode, freq, …)
  K1–K4 press    → reset that parameter to default

Pattern selection is also available via the web API:
  GET  /api/patternflow/patterns   → list names
  POST /api/patternflow/pattern    → {"index": N}  or  {"name": "..."}

Encoder GPIO pins are read from config.json → "patternflow" → "encoders".
Set any pin to -1 to mark it unconnected. If no GPIO is available the mode
falls back to web-only control.
"""

import time
import logging
import threading

from PIL import Image, ImageDraw, ImageFont

from modes.base import BaseMode
from . import core_canvas  as pf_canvas
from . import core_encoders as pf_enc
from .registry import PATTERNS

logger = logging.getLogger(__name__)

_MODE_RUNNING   = 0
_MODE_SELECTING = 1
_LONG_PRESS_S   = 1.0

_DEFAULT_ENC_CFG = [
    # Physical encoders are opt-in. On RGB matrix HATs/bonnets, choosing a
    # matrix signal pin here can leave the display sliced into horizontal bands
    # until the service restarts.
    {"clk": -1, "dt": -1, "sw": -1},
    {"clk": -1, "dt": -1, "sw": -1},
    {"clk": -1, "dt": -1, "sw": -1},
    {"clk": -1, "dt": -1, "sw": -1},
]


class PatternflowMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self._patterns = PATTERNS
        self._current_idx  = 0
        self._app_mode     = _MODE_RUNNING
        self._prev_knobs   = [0, 0, 0, 0]
        self._last_delta_t = [0.0, 0.0, 0.0, 0.0]
        self._last_t       = 0.0
        self._enc_ok       = False
        self._content_notice = 0.0
        self._font = ImageFont.load_default()
        self._web_deltas = [0, 0, 0, 0]
        self._web_btns   = [False, False, False, False]
        self._web_lock   = threading.Lock()

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        super().start()
        pf_canvas.init()

        cfg = self.config.get_section('patternflow')
        idx = cfg.get('current_pattern', 0)
        self._current_idx = max(0, min(idx, len(self._patterns) - 1))

        encoders_enabled = cfg.get('encoders_enabled', False)
        if encoders_enabled:
            enc_cfg = cfg.get('encoders', _DEFAULT_ENC_CFG)
            invert  = cfg.get('invert_encoder', False)
            try:
                self._enc_ok = pf_enc.init_encoders(enc_cfg, invert)
            except Exception as e:
                logger.warning(f"Encoder init error: {e}")
                self._enc_ok = False
        else:
            self._enc_ok = False
            logger.info("Patternflow physical encoders disabled; using web controls only")

        for pat in self._patterns:
            try:
                pat.setup()
            except Exception as e:
                logger.error(f"Pattern setup error ({pat.NAME}): {e}")

        self._last_t = time.monotonic()
        logger.info(f"Patternflow started — {len(self._patterns)} patterns, "
                    f"encoders={'ok' if self._enc_ok else 'disabled'}")

    def stop(self):
        if self._enc_ok:
            pf_enc.cleanup_encoders()
            self._enc_ok = False
        self.config.set_section('patternflow', {'current_pattern': self._current_idx})
        super().stop()

    # ── Public API (called from api.py) ───────────────────────────────────────

    def web_knob(self, knob: int, delta: int):
        with self._web_lock:
            self._web_deltas[knob] += delta

    def web_button(self, knob: int):
        with self._web_lock:
            self._web_btns[knob] = True

    def set_pattern(self, idx: int):
        self._current_idx = max(0, min(idx, len(self._patterns) - 1))
        self._content_notice = 1.0
        self.config.set_section('patternflow', {'current_pattern': self._current_idx})

    def get_pattern_names(self) -> list[str]:
        return [p.NAME for p in self._patterns]

    def get_current_pattern(self) -> dict:
        p = self._patterns[self._current_idx]
        return {'index': self._current_idx, 'name': p.NAME, 'knob_labels': list(p.KNOB_LABELS)}

    # ── Render (called by MatrixController every vsync) ───────────────────────

    def render(self, canvas):
        now = time.monotonic()
        dt  = max(0.0, min(now - self._last_t, 0.1))  # cap at 100ms to avoid jumps
        self._last_t = now

        if self._enc_ok:
            inp = pf_enc.read_input_frame(self._prev_knobs, self._last_delta_t)
        else:
            inp = pf_enc.InputFrame()
            inp.now = now

        with self._web_lock:
            for i in range(4):
                inp.knob_deltas[i] += self._web_deltas[i]
                if self._web_btns[i]:
                    inp.btn_pressed[i] = True
            self._web_deltas = [0, 0, 0, 0]
            self._web_btns   = [False, False, False, False]

        self._handle_select(inp)

        pat = self._patterns[self._current_idx]

        if self._app_mode == _MODE_RUNNING:
            try:
                pat.update(dt, inp)
                pat.draw()
            except Exception as e:
                logger.error(f"Pattern render error ({pat.NAME}): {e}")
                pf_canvas.clear()
        else:
            # SELECT mode: K4 rotates, neutral preview behind overlay
            if inp.knob_deltas[3]:
                n = len(self._patterns)
                self._current_idx = (self._current_idx + inp.knob_deltas[3]) % n
                pat = self._patterns[self._current_idx]

            preview = pf_enc.InputFrame()
            preview.now = inp.now
            preview.knobs = list(inp.knobs)
            try:
                pat.update(dt, preview)
                pat.draw()
            except Exception:
                pf_canvas.clear()

        # Push pattern buffer → canvas
        pf_canvas.render_to(canvas)

        # Overlays drawn directly on canvas (on top of SetImage result)
        if self._content_notice > 0.0:
            self._draw_notice(canvas, pat.NAME)
            self._content_notice -= dt

        if self._app_mode == _MODE_SELECTING:
            self._draw_select_overlay(canvas, pat.NAME)

    # ── Input handling ────────────────────────────────────────────────────────

    def _handle_select(self, inp):
        if not self._enc_ok:
            return
        btn4 = pf_enc.logical_button(3)
        if btn4 and btn4.long_pressed(_LONG_PRESS_S):
            if self._app_mode == _MODE_RUNNING:
                self._app_mode = _MODE_SELECTING
                logger.info("SELECT mode")
            else:
                self._app_mode = _MODE_RUNNING
                self._content_notice = 1.0
                self.config.set_section('patternflow', {'current_pattern': self._current_idx})
                logger.info(f"Pattern confirmed: {self._patterns[self._current_idx].NAME}")

    # ── Text overlay helpers ──────────────────────────────────────────────────

    def _text_onto_canvas(self, canvas, text: str, x: int, y: int,
                          color: tuple[int, int, int], scrim: bool = False):
        """Rasterise text with PIL and write pixels onto the FrameCanvas."""
        img = Image.new('RGB', (pf_canvas.W, pf_canvas.H), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        bbox = self._font.getbbox(text)
        tw = bbox[2] - bbox[0] if bbox else len(text) * 6
        cx = max(0, (pf_canvas.W - tw) // 2) if x < 0 else x

        if scrim:
            draw.rectangle([cx - 1, y - 1, cx + tw + 1, y + 8], fill=(0, 0, 0))

        draw.text((cx, y), text, font=self._font, fill=color)
        import numpy as np
        arr = np.array(img)
        ys, xs = np.where((arr[:, :, 0] > 0) | (arr[:, :, 1] > 0) | (arr[:, :, 2] > 0))
        for ry, rx in zip(ys.tolist(), xs.tolist()):
            r, g, b = arr[ry, rx]
            canvas.SetPixel(rx, ry, int(r), int(g), int(b))

    def _draw_notice(self, canvas, name: str):
        self._text_onto_canvas(canvas, name, -1, pf_canvas.H // 2 - 4, (255, 255, 255), scrim=True)

    def _draw_select_overlay(self, canvas, name: str):
        n   = len(self._patterns)
        self._text_onto_canvas(canvas, f"{self._current_idx + 1}/{n}", -1,  2, (160, 160, 160), scrim=True)
        self._text_onto_canvas(canvas, name,                            -1, 12, (255, 255, 255), scrim=True)
        self._text_onto_canvas(canvas, "HOLD K4",                       -1, 22, (180, 180, 180), scrim=True)
