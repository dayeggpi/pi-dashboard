import math
import threading
import time
from PIL import Image, ImageDraw
from modes.base import BaseMode, image_to_canvas
from modes.clock import draw_digit
from modes.spotify import _draw_centered_glyph_lines

W, H = 64, 32

# Layout: rows 0-6 = phase label, 7-28 = big digit (h=22), 29-31 = round dots

_PHASE_COLORS = {
    'idle':     {'bg': (0, 0, 0),     'fg': (200, 200, 200), 'flash': None},
    'getready': {'bg': (160, 110, 0), 'fg': (0, 0, 0),       'flash': (255, 210, 0)},
    'work':     {'bg': (0, 155, 0),   'fg': (255, 255, 255), 'flash': (0, 240, 0)},
    'rest':     {'bg': (0, 45, 195),  'fg': (255, 255, 255), 'flash': (0, 100, 255)},
    'done':     {'bg': (185, 0, 0),   'fg': (255, 255, 255), 'flash': (255, 40, 40)},
    'cooldown': {'bg': (0, 0, 110),   'fg': (80, 140, 255),  'flash': None},
}

_PHASE_LABEL = {
    'getready': 'GET READY',
    'work':     'WORK',
    'rest':     'REST',
    'done':     'DONE!',
}


def _dim(rgb, f):
    return tuple(max(0, int(c * f)) for c in rgb)


class WorkoutMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self._lock = threading.Lock()
        self._state = self._idle_state()

    @staticmethod
    def _idle_state():
        return {
            'phase': 'idle',
            'round': 0,
            'total_rounds': 8,
            'work_s': 20,
            'rest_s': 10,
            'workout_type': 'tabata',
            'phase_end_at': None,
            'paused': False,
            'pause_time_left': None,
            'done_at': None,
        }

    def is_active(self):
        with self._lock:
            return self._state['phase'] not in ('idle', 'cooldown')

    def get_status(self):
        now = time.monotonic()
        with self._lock:
            s = dict(self._state)
        ph = s['phase']
        if s['paused']:
            tl = float(s.get('pause_time_left') or 0)
        elif s['phase_end_at'] and ph not in ('idle', 'done', 'cooldown'):
            tl = max(0.0, s['phase_end_at'] - now)
        else:
            tl = 0.0
        s['time_left'] = round(tl, 2)
        return s

    def command(self, action, cfg=None):
        now = time.monotonic()
        with self._lock:
            s = self._state

            if action == 'stop':
                new = self._idle_state()
                if cfg:
                    self._apply_cfg(new, cfg)
                self._state = new
                return 'stopped'

            if action == 'start':
                new = self._idle_state()
                if cfg:
                    self._apply_cfg(new, cfg)
                new['phase'] = 'getready'
                new['round'] = 0
                new['phase_end_at'] = now + 10.0
                self._state = new
                return 'getready'

            if action == 'pause':
                if s['phase'] in ('idle', 'done', 'cooldown') or s['paused']:
                    return 'ignored'
                tl = max(0.0, (s['phase_end_at'] or now) - now)
                s['pause_time_left'] = tl
                s['paused'] = True
                return 'paused'

            if action == 'resume':
                if not s['paused']:
                    return 'ignored'
                tl = float(s.get('pause_time_left') or 0)
                s['phase_end_at'] = now + tl
                s['paused'] = False
                s['pause_time_left'] = None
                return 'resumed'

        return 'unknown'

    @staticmethod
    def _apply_cfg(state, cfg):
        try:
            state['work_s'] = max(1, int(cfg.get('work_s', 20) or 20))
        except Exception:
            pass
        try:
            state['rest_s'] = max(0, int(cfg.get('rest_s', 10) or 0))
        except Exception:
            pass
        try:
            state['total_rounds'] = max(1, int(cfg.get('rounds', 8) or 8))
        except Exception:
            pass
        wt = str(cfg.get('workout_type', 'tabata') or 'tabata').lower()
        state['workout_type'] = wt if wt in ('tabata', 'hiit') else 'tabata'

    def _advance(self, now):
        with self._lock:
            s = self._state
            if s['paused'] or s['phase'] in ('idle', 'cooldown'):
                return
            if s['phase'] == 'done':
                if now - (s.get('done_at') or now) >= 5.0:
                    s['phase'] = 'cooldown'
                return
            end = s.get('phase_end_at')
            if end and now < end:
                return
            ph = s['phase']
            if ph == 'getready':
                s['phase'] = 'work'
                s['round'] = 1
                s['phase_end_at'] = now + s['work_s']
            elif ph == 'work':
                if s['rest_s'] > 0:
                    s['phase'] = 'rest'
                    s['phase_end_at'] = now + s['rest_s']
                elif s['round'] >= s['total_rounds']:
                    s['phase'] = 'done'
                    s['done_at'] = now
                    s['phase_end_at'] = None
                else:
                    s['round'] += 1
                    s['phase_end_at'] = now + s['work_s']
            elif ph == 'rest':
                if s['round'] >= s['total_rounds']:
                    s['phase'] = 'done'
                    s['done_at'] = now
                    s['phase_end_at'] = None
                else:
                    s['round'] += 1
                    s['phase'] = 'work'
                    s['phase_end_at'] = now + s['work_s']

    def render(self, canvas):
        now_m = time.monotonic()
        self._advance(now_m)
        with self._lock:
            s = dict(self._state)
        ph = s['phase']
        if s['paused']:
            tl = float(s.get('pause_time_left') or 0)
        elif s['phase_end_at'] and ph not in ('idle', 'done', 'cooldown'):
            tl = max(0.0, s['phase_end_at'] - now_m)
        else:
            tl = 0.0
        image_to_canvas(canvas, self._build_frame(ph, s['paused'], tl, s))

    def _build_frame(self, phase, paused, time_left, state):
        now_t = time.time()
        cols = _PHASE_COLORS.get(phase, _PHASE_COLORS['idle'])
        bg, fg = cols['bg'], cols['fg']

        # Cooldown: slow-pulsing blue
        if phase == 'cooldown':
            pulse = (math.sin(now_t * 1.5) + 1) / 2
            bv = int(55 + 120 * pulse)
            return Image.new('RGB', (W, H), (0, 0, bv))

        # Done: flashing red + DONE text
        if phase == 'done':
            flash_on = int(now_t * 3) % 2 == 0
            img = Image.new('RGB', (W, H), cols['flash'] if flash_on else (0, 0, 0))
            _draw_centered_glyph_lines(ImageDraw.Draw(img), ('DONE!',), 12,
                                       (0, 0, 0) if flash_on else (255, 255, 255))
            return img

        # Idle: show workout type name
        if phase == 'idle':
            img = Image.new('RGB', (W, H), bg)
            draw = ImageDraw.Draw(img)
            wt = state.get('workout_type', 'tabata').upper()
            if wt == 'HIIT':
                _draw_centered_glyph_lines(draw, ('HIIT',), 6, fg)
                _draw_centered_glyph_lines(draw, ('WORKOUT',), 17, _dim(fg, 0.6))
            else:
                _draw_centered_glyph_lines(draw, ('TABATA',), 12, fg)
            return img

        # Active phases: getready / work / rest
        flashing = not paused and 0 < time_left <= 3.0
        if flashing:
            flash_on = int(now_t * 4) % 2 == 0
            actual_bg = cols['flash'] if flash_on else (0, 0, 0)
            actual_fg = fg if flash_on else (180, 180, 180)
        elif paused:
            slow_on = int(now_t * 1.5) % 2 == 0
            actual_bg = _dim(bg, 0.3) if slow_on else (0, 0, 0)
            actual_fg = (210, 180, 0)
        else:
            actual_bg, actual_fg = bg, fg

        img = Image.new('RGB', (W, H), actual_bg)
        draw = ImageDraw.Draw(img)

        # Phase label (rows 0-6)
        label = 'PAUSE' if paused else _PHASE_LABEL.get(phase, '')
        if label:
            _draw_centered_glyph_lines(draw, (label,), 0, actual_fg)

        # Big countdown digits (rows 7-28, h=22)
        secs = int(math.ceil(time_left)) if time_left > 0 else 0
        self._draw_big_number(draw, secs, 7, actual_fg)

        # Round dots (rows 29-31) — not during getready
        if phase != 'getready':
            self._draw_round_dots(
                draw, state.get('round', 0), state.get('total_rounds', 8),
                now_t, paused, actual_bg, actual_fg,
            )

        return img

    @staticmethod
    def _draw_big_number(draw, secs, y, color):
        digits = str(max(0, secs))
        n = len(digits)
        if n <= 2:
            dw, dh, t = 12, 22, 2
        else:
            dw, dh, t = 8, 15, 2
        gap = 2
        total_w = n * dw + (n - 1) * gap
        x0 = (W - total_w) // 2
        for i, ch in enumerate(digits):
            draw_digit(draw, x0 + i * (dw + gap), y, ch, color, dw, dh, t)

    @staticmethod
    def _draw_round_dots(draw, current_round, total_rounds, now_t, paused, bg, fg):
        if total_rounds <= 0:
            return
        seg_w = W / total_rounds
        for r in range(total_rounds):
            x1 = int(round(r * seg_w))
            x2 = int(round((r + 1) * seg_w)) - 2  # 1px gap between dots
            if x2 < x1:
                x2 = x1
            if x2 >= W:
                x2 = W - 1
            ri = r + 1
            if ri < current_round:
                dot_c = fg
            elif ri == current_round:
                if paused:
                    dot_c = (210, 180, 0)
                else:
                    dot_c = fg if int(now_t * 3) % 2 == 0 else bg
            else:
                dot_c = _dim(fg, 0.15)
            draw.rectangle([x1, 29, x2, 31], fill=dot_c)
