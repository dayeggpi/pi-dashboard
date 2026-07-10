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

import numpy as np
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
_DEFAULT_EXTRA_BUTTON_PINS = [-1, -1]


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
        self._show_fps = False
        self._fps_ema = 0.0
        self._fast_image_push = True
        self._web_deltas = [0, 0, 0, 0]
        self._web_btns   = [False, False, False, False, False, False]
        self._web_lock   = threading.Lock()
        self._perf_frames = 0
        self._perf_update_s = 0.0
        self._perf_draw_s = 0.0
        self._perf_push_s = 0.0
        self._perf_overlay_s = 0.0
        self._perf_last_log = time.monotonic()
        self._auto_fast_applied = False

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def start(self):
        super().start()
        pf_canvas.init()

        cfg = self.config.get_section('patternflow')
        idx = cfg.get('current_pattern', 0)
        self._current_idx = max(0, min(idx, len(self._patterns) - 1))
        self._show_fps = bool(cfg.get('show_fps', False))
        self._fast_image_push = bool(cfg.get('fast_image_push', True))
        self._apply_pattern_options(cfg)

        encoders_enabled = cfg.get('encoders_enabled', False)
        if encoders_enabled:
            enc_cfg = cfg.get('encoders', _DEFAULT_ENC_CFG)
            extra_button_pins = cfg.get('extra_buttons', _DEFAULT_EXTRA_BUTTON_PINS)
            invert  = cfg.get('invert_encoder', False)
            try:
                self._enc_ok = pf_enc.init_encoders(enc_cfg, invert, extra_button_pins)
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
        self._perf_frames = 0
        self._perf_update_s = 0.0
        self._perf_draw_s = 0.0
        self._perf_push_s = 0.0
        self._perf_overlay_s = 0.0
        self._perf_last_log = self._last_t
        self._auto_fast_applied = False
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

    def set_options(self, show_fps=None, donut_fast_render=None, fast_image_push=None):
        update = {}
        if show_fps is not None:
            self._show_fps = bool(show_fps)
            update['show_fps'] = self._show_fps
        if donut_fast_render is not None:
            update['donut_fast_render'] = bool(donut_fast_render)
        if fast_image_push is not None:
            self._fast_image_push = bool(fast_image_push)
            update['fast_image_push'] = self._fast_image_push
        if update:
            self.config.set_section('patternflow', update)
            self._apply_pattern_options(self.config.get_section('patternflow'))

    def _apply_pattern_options(self, cfg: dict):
        donut_fast = bool(cfg.get('donut_fast_render', True))
        for pat in self._patterns:
            setter = getattr(pat, 'set_fast_render', None)
            if setter:
                try:
                    setter(donut_fast)
                except Exception as e:
                    logger.warning(f"Pattern option error ({pat.NAME}): {e}")

    def set_pattern(self, idx: int):
        self._current_idx = max(0, min(idx, len(self._patterns) - 1))
        self._content_notice = 1.0
        self.config.set_section('patternflow', {'current_pattern': self._current_idx})

    def get_pattern_names(self) -> list[str]:
        return [p.NAME for p in self._patterns]

    def get_current_pattern(self) -> dict:
        p = self._patterns[self._current_idx]
        return {
            'index': self._current_idx,
            'name': p.NAME,
            'knob_labels': list(p.KNOB_LABELS),
            'extra_button_labels': list(getattr(p, 'EXTRA_BUTTON_LABELS', [])),
            'show_fps': self._show_fps,
            'donut_fast_render': bool(self.config.get_section('patternflow').get('donut_fast_render', True)),
            'fast_image_push': self._fast_image_push,
        }

    # ── Render (called by MatrixController every vsync) ───────────────────────

    def render(self, canvas):
        now = time.monotonic()
        raw_dt = max(0.0, now - self._last_t)
        # Keep animation jumps bounded after slow frames, but measure FPS from
        # the real frame interval so the overlay does not stick at 10.0 fps.
        dt = min(raw_dt, 0.1)
        self._last_t = now
        if raw_dt > 0.0:
            fps = 1.0 / raw_dt
            self._fps_ema = fps if self._fps_ema <= 0.0 else self._fps_ema * 0.88 + fps * 0.12

        if self._enc_ok:
            inp = pf_enc.read_input_frame(self._prev_knobs, self._last_delta_t)
        else:
            inp = pf_enc.InputFrame()
            inp.now = now

        with self._web_lock:
            for i in range(4):
                inp.knob_deltas[i] += self._web_deltas[i]
            for i in range(len(self._web_btns)):
                if self._web_btns[i]:
                    inp.btn_pressed[i] = True
            self._web_deltas = [0, 0, 0, 0]
            self._web_btns   = [False, False, False, False, False, False]

        self._handle_select(inp)

        pat = self._patterns[self._current_idx]
        update_s = 0.0
        draw_s = 0.0

        if self._app_mode == _MODE_RUNNING:
            try:
                t0 = time.monotonic()
                pat.update(dt, inp)
                t1 = time.monotonic()
                pat.draw()
                t2 = time.monotonic()
                update_s = t1 - t0
                draw_s = t2 - t1
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
                t0 = time.monotonic()
                pat.update(dt, preview)
                t1 = time.monotonic()
                pat.draw()
                t2 = time.monotonic()
                update_s = t1 - t0
                draw_s = t2 - t1
            except Exception:
                pf_canvas.clear()

        # Push pattern buffer → canvas
        push_start = time.monotonic()
        pf_canvas.render_to(canvas, fast_image=self._fast_image_push)
        push_s = time.monotonic() - push_start

        # Overlays drawn directly on canvas (on top of SetImage result)
        overlay_start = time.monotonic()
        if self._content_notice > 0.0:
            self._draw_notice(canvas, pat.NAME)
            self._content_notice -= dt

        if self._app_mode == _MODE_SELECTING:
            self._draw_select_overlay(canvas, pat.NAME)
        elif self._show_fps:
            self._draw_fps(canvas)
        overlay_s = time.monotonic() - overlay_start
        self._record_perf(pat, update_s, draw_s, push_s, overlay_s)

    # ── Input handling ────────────────────────────────────────────────────────

    def _record_perf(self, pat, update_s: float, draw_s: float, push_s: float, overlay_s: float):
        self._perf_frames += 1
        self._perf_update_s += update_s
        self._perf_draw_s += draw_s
        self._perf_push_s += push_s
        self._perf_overlay_s += overlay_s

        now = time.monotonic()
        elapsed = now - self._perf_last_log
        if elapsed < 5.0:
            return

        frames = max(1, self._perf_frames)
        update_ms = self._perf_update_s * 1000.0 / frames
        draw_ms = self._perf_draw_s * 1000.0 / frames
        push_ms = self._perf_push_s * 1000.0 / frames
        overlay_ms = self._perf_overlay_s * 1000.0 / frames
        logger.info(
            "Patternflow perf: pattern=%s fps=%.1f update_ms=%.1f draw_ms=%.1f push_ms=%.1f overlay_ms=%.1f fast_image=%s",
            pat.NAME,
            frames / max(0.001, elapsed),
            update_ms,
            draw_ms,
            push_ms,
            overlay_ms,
            self._fast_image_push,
        )

        if (not self._auto_fast_applied and draw_ms > 70.0 and
                getattr(pat, 'set_fast_render', None) is not None):
            logger.info("Patternflow auto-fast: enabling fast render for %s after draw_ms=%.1f", pat.NAME, draw_ms)
            self._auto_fast_applied = True
            try:
                pat.set_fast_render(True)
                self.config.set_section('patternflow', {'donut_fast_render': True})
            except Exception as e:
                logger.warning("Patternflow auto-fast failed for %s: %s", pat.NAME, e)

        self._perf_frames = 0
        self._perf_update_s = 0.0
        self._perf_draw_s = 0.0
        self._perf_push_s = 0.0
        self._perf_overlay_s = 0.0
        self._perf_last_log = now

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
        arr = np.array(img)
        ys, xs = np.where((arr[:, :, 0] > 0) | (arr[:, :, 1] > 0) | (arr[:, :, 2] > 0))
        for ry, rx in zip(ys, xs):
            r, g, b = arr[ry, rx]
            canvas.SetPixel(rx, ry, int(r), int(g), int(b))

    def _draw_notice(self, canvas, name: str):
        self._text_onto_canvas(canvas, name, -1, pf_canvas.H // 2 - 4, (255, 255, 255), scrim=True)

    def _draw_fps(self, canvas):
        self._text_onto_canvas(canvas, f"{self._fps_ema:4.1f}", 1, 1, (80, 255, 120), scrim=True)

    def _draw_select_overlay(self, canvas, name: str):
        n   = len(self._patterns)
        self._text_onto_canvas(canvas, f"{self._current_idx + 1}/{n}", -1,  2, (160, 160, 160), scrim=True)
        self._text_onto_canvas(canvas, name,                            -1, 12, (255, 255, 255), scrim=True)
        self._text_onto_canvas(canvas, "HOLD K4",                       -1, 22, (180, 180, 180), scrim=True)
