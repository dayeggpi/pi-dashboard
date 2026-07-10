import threading
import time
from PIL import Image, ImageDraw
from modes.base import BaseMode, image_to_canvas
from modes.spotify import _draw_centered_glyph_lines

W, H = 64, 32
STOP_EVENTS = {'stop', 'stopped', 'cancel', 'cancelled', 'reset', 'end'}
PAUSE_EVENTS = {'pause', 'paused'}


def _rgb(value, fallback):
    try:
        return tuple(max(0, min(255, int(v))) for v in value[:3])
    except Exception:
        return fallback


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


class PomodoroMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self._lock = threading.Lock()
        self._timer = None
        self._cfg = {}
        self._last_cfg_load = 0.0
        self._requested_mode = None

    def start(self):
        super().start()
        self._last_cfg_load = 0.0

    @staticmethod
    def _coerce_ms(payload, key, fallback=None):
        if key not in payload or payload.get(key) is None:
            if fallback is None:
                raise ValueError(f'{key} field required')
            return fallback
        return int(payload.get(key) or 0)

    @staticmethod
    def _current_left(timer, now):
        left = max(0, int(timer.get('time_left_ms', 0) or 0))
        if timer.get('state') == 'running' and left > 0:
            left = max(0, left - int((now - timer.get('received_at', now)) * 1000))
        return left

    @staticmethod
    def _is_new_timer_event(event, state, left, total):
        if event not in ('start', 'restart', 'resume') and state not in ('running', 'resumed'):
            return False
        return total > 0 and left > 0

    def update_timer(self, payload):
        now = time.time()
        event = str(payload.get('event', 'update')).strip().lower()
        state = str(payload.get('state', 'unknown')).strip().lower()
        with self._lock:
            if event in STOP_EVENTS or state in STOP_EVENTS or state == 'idle':
                self._timer = {
                    'event': event,
                    'state': 'stopped',
                    'time_left_ms': 0,
                    'total_time_ms': 1,
                    'received_at': now,
                    'elapsed_at': None,
                    'handoff_requested': False,
                }
                self._requested_mode = None
                return 'stopped'

            previous = dict(self._timer) if self._timer else None
            fallback_total = max(1, int(previous.get('total_time_ms', 1))) if previous else None
            fallback_left = self._current_left(previous, now) if previous else None

            if event in PAUSE_EVENTS or state in PAUSE_EVENTS:
                total = max(1, self._coerce_ms(payload, 'totalTimeMs', fallback_total))
                left = max(0, self._coerce_ms(payload, 'timeLeftMs', fallback_left))
                self._timer = {
                    'event': event,
                    'state': 'paused',
                    'time_left_ms': left,
                    'total_time_ms': total,
                    'received_at': now,
                    'elapsed_at': None,
                    'handoff_requested': False,
                }
                self._requested_mode = None
                return 'paused'

            raw_total = self._coerce_ms(payload, 'totalTimeMs', fallback_total)
            raw_left = self._coerce_ms(payload, 'timeLeftMs', fallback_left)
            if previous and previous.get('state') == 'elapsed' and raw_left <= 0:
                return 'elapsed_ignored'

            total = max(1, raw_total)
            left = max(0, raw_left)
            if not self._is_new_timer_event(event, state, left, total) and previous and previous.get('state') == 'elapsed':
                return 'elapsed_ignored'

            self._timer = {
                'event': event,
                'state': state,
                'time_left_ms': left,
                'total_time_ms': total,
                'received_at': now,
                'elapsed_at': None,
                'handoff_requested': False,
            }
            self._requested_mode = None
        return state

    def _get_cfg(self):
        now = time.time()
        if now - self._last_cfg_load >= 0.25 or not self._cfg:
            self._cfg = self.config.get_section('pomodoro')
            self._last_cfg_load = now
        return self._cfg

    def _snapshot(self):
        now = time.time()
        with self._lock:
            if not self._timer:
                return None

            left = self._current_left(self._timer, now)
            if left <= 0 and self._timer.get('state') not in ('stopped', 'paused', 'elapsed'):
                self._timer['state'] = 'elapsed'
                self._timer['time_left_ms'] = 0
                self._timer['elapsed_at'] = self._timer.get('elapsed_at') or now
            timer = dict(self._timer)

        if not timer:
            return None

        left = max(0, int(left or 0))
        total = max(1, timer['total_time_ms'])
        progress = max(0.0, min(1.0, (total - left) / total))
        timer['time_left_ms'] = left
        timer['progress'] = progress
        return timer

    def _maybe_request_handoff(self, cfg, timer):
        if timer.get('state') != 'elapsed' or not bool(cfg.get('return_after_elapsed_enabled', False)):
            return
        try:
            delay_s = max(0, int(cfg.get('return_after_elapsed_delay_s', 10) or 0))
        except Exception:
            delay_s = 10
        elapsed_at = timer.get('elapsed_at') or time.time()
        if time.time() - elapsed_at < delay_s:
            return
        target = str(cfg.get('return_after_elapsed_mode', 'clock') or 'clock').strip()
        if not target or target == 'pomodoro':
            return
        with self._lock:
            if self._timer and not self._timer.get('handoff_requested'):
                self._timer['handoff_requested'] = True
                self._requested_mode = target

    def consume_requested_mode(self):
        with self._lock:
            mode = self._requested_mode
            self._requested_mode = None
            return mode

    def _draw_gradient_bar(self, img, progress, start, end):
        draw = ImageDraw.Draw(img)
        fill_w = max(0, min(W, int(round(W * progress))))
        for x in range(fill_w):
            t = x / max(1, W - 1)
            draw.line([(x, 0), (x, H - 1)], fill=_mix(start, end, t))

    def _draw_tick_pixel(self, img, cfg, timer):
        if timer.get('state') != 'running' or not bool(cfg.get('tick_pixel_enabled', True)):
            return
        if int(time.time() * 2) % 2 == 0:
            img.putpixel((W - 1, 0), _rgb(cfg.get('tick_pixel_color'), (255, 255, 255)))

    def render(self, canvas):
        cfg = self._get_cfg()
        timer = self._snapshot()
        bg = _rgb(cfg.get('background_color'), (0, 0, 0))
        text_color = _rgb(cfg.get('text_color'), (255, 255, 255))

        if not timer:
            img = Image.new('RGB', (W, H), bg)
            image_to_canvas(canvas, img)
            return

        if timer['state'] == 'stopped':
            img = Image.new('RGB', (W, H), bg)
            image_to_canvas(canvas, img)
            return

        if timer['time_left_ms'] <= 0:
            self._maybe_request_handoff(cfg, timer)
            elapsed_bg = _rgb(cfg.get('elapsed_background'), (25, 25, 25))
            img = Image.new('RGB', (W, H), elapsed_bg)
            _draw_centered_glyph_lines(ImageDraw.Draw(img), ("TIME", "ELAPSED"), 8, text_color)
            image_to_canvas(canvas, img)
            return

        if timer['state'] == 'paused':
            img = Image.new('RGB', (W, H), bg)
            _draw_centered_glyph_lines(ImageDraw.Draw(img), ("PAUSE",), 12, text_color)
            image_to_canvas(canvas, img)
            return

        threshold = max(0, int(cfg.get('flash_threshold_ms', 5000) or 5000))
        flash = bool(cfg.get('flash_red', True)) and timer['time_left_ms'] <= threshold
        if flash and int(time.time() * 4) % 2 == 0:
            img = Image.new('RGB', (W, H), (180, 0, 0))
        else:
            img = Image.new('RGB', (W, H), bg)
            start = _rgb(cfg.get('gradient_start'), (30, 215, 96))
            end = _rgb(cfg.get('gradient_end'), (255, 210, 64))
            self._draw_gradient_bar(img, timer['progress'], start, end)

        self._draw_tick_pixel(img, cfg, timer)
        image_to_canvas(canvas, img)
