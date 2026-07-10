import threading
import time
from PIL import Image, ImageDraw
from modes.base import BaseMode, image_to_canvas
from modes.spotify import TEXT_GLYPHS, _display_text, _draw_glyph_text, _glyph_width

W, H = 64, 32


def _rgb(value, fallback):
    try:
        return tuple(max(0, min(255, int(v))) for v in value[:3])
    except Exception:
        return fallback


def _mix(a, b, t):
    return tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))


def _gradient_background(start, end):
    img = Image.new('RGB', (W, H), start)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / max(1, H - 1)
        draw.line([(0, y), (W - 1, y)], fill=_mix(start, end, t))
    return img


def _wrap_lines(text, max_lines=3):
    words = _display_text(text).split()
    if not words:
        return ["REMINDER"]

    lines = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if current and _glyph_width(candidate, TEXT_GLYPHS) > W:
            lines.append(current)
            current = word
        else:
            current = candidate

        while _glyph_width(current, TEXT_GLYPHS) > W and len(current) > 1:
            cut = max(1, len(current) - 1)
            while cut > 1 and _glyph_width(current[:cut], TEXT_GLYPHS) > W:
                cut -= 1
            lines.append(current[:cut])
            current = current[cut:]

        if len(lines) >= max_lines:
            break

    if current and len(lines) < max_lines:
        lines.append(current)
    return lines[:max_lines] or ["REMINDER"]


class ReminderMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self._lock = threading.Lock()
        self._active = None
        self._requested_mode = None

    def show(self, reminder, return_mode):
        try:
            duration = max(1, int(reminder.get('display_time_s', 10) or 10))
        except Exception:
            duration = 10
        with self._lock:
            self._active = {
                'text': str(reminder.get('text', 'REMINDER') or 'REMINDER'),
                'text_color': _rgb(reminder.get('text_color'), (255, 255, 255)),
                'gradient_start': _rgb(reminder.get('gradient_start'), (20, 30, 80)),
                'gradient_end': _rgb(reminder.get('gradient_end'), (180, 40, 80)),
                'display_until': time.monotonic() + duration,
                'return_mode': return_mode,
            }
            self._requested_mode = None

    def consume_requested_mode(self):
        with self._lock:
            mode = self._requested_mode
            self._requested_mode = None
            return mode

    def render(self, canvas):
        with self._lock:
            active = dict(self._active) if self._active else None

        if not active:
            img = Image.new('RGB', (W, H), (0, 0, 0))
            image_to_canvas(canvas, img)
            return

        if time.monotonic() >= active['display_until']:
            with self._lock:
                self._active = None
                self._requested_mode = active.get('return_mode') or 'clock'
            image_to_canvas(canvas, Image.new('RGB', (W, H), (0, 0, 0)))
            return

        img = _gradient_background(active['gradient_start'], active['gradient_end'])
        draw = ImageDraw.Draw(img)
        lines = _wrap_lines(active['text'])
        total_h = len(lines) * 5 + (len(lines) - 1) * 2
        y = max(0, (H - total_h) // 2)
        for line in lines:
            text_w = _glyph_width(line, TEXT_GLYPHS)
            _draw_glyph_text(draw, max(0, (W - text_w) // 2), y, line, active['text_color'], TEXT_GLYPHS)
            y += 7

        image_to_canvas(canvas, img)
