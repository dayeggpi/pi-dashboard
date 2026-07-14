import time
import requests
from PIL import Image, ImageDraw
from modes.base import BaseMode, image_to_canvas
from modes.spotify import (
    TEXT_GLYPHS,
    _display_text,
    _draw_centered_glyph_lines,
    _draw_glyph_text,
    _glyph_width,
)

LINE_HEIGHT = 9  # 7px glyph + 2px gap between lines


def _wrap_text(text, max_w, glyphs):
    """Wrap text into lines fitting max_w pixels, hyphenating words that are too long."""
    lines = []
    words = text.split(' ')
    current = ''

    for word in words:
        if not word:
            continue
        candidate = (current + ' ' + word) if current else word
        if _glyph_width(candidate, glyphs) <= max_w:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = ''
            if _glyph_width(word, glyphs) <= max_w:
                current = word
            else:
                chunk = ''
                for ch in word:
                    test = chunk + ch
                    if _glyph_width(test + '-', glyphs) <= max_w:
                        chunk = test
                    else:
                        if chunk:
                            lines.append(chunk + '-')
                        chunk = ch
                current = chunk

    if current:
        lines.append(current)

    return lines if lines else ['']


class TextMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.scroll_x = 64.0
        self.scroll_y = 32.0
        self.last_frame = time.time()
        self._cfg = {}
        self._last_cfg_load = 0.0
        self._layout_key = None
        self._text_w = 0
        self._text_y = 0
        self._url_content = None
        self._last_url_fetch = 0.0
        self._last_url = None

    def start(self):
        super().start()
        self.scroll_x = 64.0
        self.scroll_y = 32.0
        self.last_frame = time.time()
        self._last_cfg_load = 0.0
        self._url_content = None
        self._last_url_fetch = 0.0

    def _fetch_url_content(self, cfg):
        url = str(cfg.get('url', '') or '').strip()
        if not url:
            self._url_content = ''
            self._last_url = url
            return self._url_content

        now = time.time()
        poll_interval = max(10, int(cfg.get('poll_interval', 60) or 60))
        if url == self._last_url and self._url_content is not None and now - self._last_url_fetch < poll_interval:
            return self._url_content

        self._last_url = url
        self._last_url_fetch = now
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            self._url_content = r.text.strip()
        except Exception:
            self._url_content = ''
        return self._url_content

    def _load_runtime(self):
        now = time.time()
        if now - self._last_cfg_load >= 0.25 or not self._cfg:
            self._cfg = self.config.get_section('text')
            self._last_cfg_load = now

        if self._cfg.get('source', 'manual') == 'url':
            content = self._fetch_url_content(self._cfg)
        else:
            content = self._cfg.get('content', 'Hello World!')
        empty = not str(content).strip()
        content = _display_text(str(content).strip())

        scroll_direction = self._cfg.get('scroll_direction') or (
            'horizontal' if self._cfg.get('scroll', True) else 'off'
        )

        layout_key = (content, scroll_direction)
        if layout_key != self._layout_key:
            self._text_w = _glyph_width(content, TEXT_GLYPHS)
            self._text_y = 12
            self._layout_key = layout_key
            self.scroll_x = 64.0
            self.scroll_y = 32.0

        return self._cfg, content, empty, self._text_w, self._text_y, scroll_direction

    def render(self, canvas):
        cfg, content, empty, text_w, text_y, scroll_direction = self._load_runtime()
        color = tuple(cfg.get('color', [255, 255, 255]))
        speed = cfg.get('speed', 30)

        img = Image.new('RGB', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        if empty:
            _draw_centered_glyph_lines(draw, ("NO TEXT",), 12, color)
            image_to_canvas(canvas, img)
            return

        if scroll_direction == 'vertical':
            now = time.time()
            elapsed = now - self.last_frame
            self.last_frame = now

            lines = _wrap_text(content, 64, TEXT_GLYPHS)
            total_h = len(lines) * LINE_HEIGHT

            self.scroll_y -= speed * elapsed
            if self.scroll_y < -total_h:
                self.scroll_y = 32.0

            for i, line in enumerate(lines):
                y = int(self.scroll_y) + i * LINE_HEIGHT
                if -LINE_HEIGHT < y < 32:
                    line_w = _glyph_width(line, TEXT_GLYPHS)
                    x = max(0, (64 - line_w) // 2)
                    _draw_glyph_text(draw, x, y, line, color, TEXT_GLYPHS)

        elif scroll_direction == 'horizontal':
            now = time.time()
            elapsed = now - self.last_frame
            self.last_frame = now
            self.scroll_x -= speed * elapsed
            if self.scroll_x < -text_w:
                self.scroll_x = 64.0
            _draw_glyph_text(draw, int(self.scroll_x), text_y, content, color, TEXT_GLYPHS)

        else:
            text_x = max(0, (64 - text_w) // 2)
            _draw_glyph_text(draw, text_x, text_y, content, color, TEXT_GLYPHS)

        image_to_canvas(canvas, img)
