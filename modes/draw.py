import time
from PIL import Image
from modes.base import BaseMode, image_to_canvas

W, H = 64, 32


class DrawMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.scroll_x = 0.0
        self.last_frame = time.time()
        self._cfg = {}
        self._last_cfg_load = 0.0
        self._image_key = None
        self._image = None

    def start(self):
        super().start()
        self.scroll_x = 0.0
        self.last_frame = time.time()
        self._last_cfg_load = 0.0

    def _get_cfg(self):
        now = time.time()
        if now - self._last_cfg_load >= 0.25 or not self._cfg:
            self._cfg = self.config.get_section('draw')
            self._last_cfg_load = now
        return self._cfg

    def _build_image(self, cfg):
        width = max(W, min(512, int(cfg.get('width', W) or W)))
        pixels = cfg.get('pixels') or []
        key = (width, repr(pixels))
        if key == self._image_key and self._image is not None:
            return self._image

        img = Image.new('RGB', (width, H), (0, 0, 0))
        px = img.load()
        for item in pixels:
            try:
                x = int(item.get('x', -1))
                y = int(item.get('y', -1))
                color = item.get('color', [0, 0, 0])
                if 0 <= x < width and 0 <= y < H:
                    px[x, y] = tuple(max(0, min(255, int(v))) for v in color[:3])
            except Exception:
                continue

        self._image = img
        self._image_key = key
        return img

    def render(self, canvas):
        cfg = self._get_cfg()
        source = self._build_image(cfg)
        width = source.size[0]
        scroll = bool(cfg.get('scroll', False)) and width > W

        if scroll:
            now = time.time()
            elapsed = now - self.last_frame
            self.last_frame = now
            speed = max(1, min(120, int(cfg.get('scroll_speed', 20) or 20)))
            self.scroll_x = (self.scroll_x + speed * elapsed) % width
        else:
            self.scroll_x = 0.0
            self.last_frame = time.time()

        x = int(self.scroll_x)
        if x + W <= width:
            frame = source.crop((x, 0, x + W, H))
        else:
            frame = Image.new('RGB', (W, H), (0, 0, 0))
            right_w = width - x
            frame.paste(source.crop((x, 0, width, H)), (0, 0))
            frame.paste(source.crop((0, 0, W - right_w, H)), (right_w, 0))

        image_to_canvas(canvas, frame)
