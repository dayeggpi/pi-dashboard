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


class TextMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.scroll_x = 64.0
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
        layout_key = content
        if layout_key != self._layout_key:
            self._text_w = _glyph_width(content, TEXT_GLYPHS)
            self._text_y = 12
            self._layout_key = layout_key
            self.scroll_x = 64.0

        return self._cfg, content, empty, self._text_w, self._text_y

    def render(self, canvas):
        cfg, content, empty, text_w, text_y = self._load_runtime()
        color = tuple(cfg.get('color', [255, 255, 255]))
        speed = cfg.get('speed', 30)      # pixels per second
        scroll = cfg.get('scroll', True)

        img = Image.new('RGB', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        if empty:
            _draw_centered_glyph_lines(draw, ("NO TEXT",), 12, color)
            image_to_canvas(canvas, img)
            return

        if scroll:
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
