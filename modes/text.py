import time
from PIL import Image, ImageDraw, ImageFont
from modes.base import BaseMode, image_to_canvas


def _paste_text(img, pos, text, color, font):
    """Draw text via grayscale mask to avoid FreeType sub-pixel color artifacts."""
    mask = Image.new('L', img.size, 0)
    ImageDraw.Draw(mask).text(pos, text, fill=255, font=font)
    img.paste(Image.new('RGB', img.size, color), mask=mask)

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'


def load_font(size=8):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()


class TextMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.scroll_x = 64.0
        self.last_frame = time.time()

    def start(self):
        super().start()
        self.scroll_x = 64.0
        self.last_frame = time.time()

    def render(self, canvas):
        cfg = self.config.get_section('text')
        content = cfg.get('content', 'Hello World!')
        color = tuple(cfg.get('color', [255, 255, 255]))
        speed = cfg.get('speed', 30)      # pixels per second
        scroll = cfg.get('scroll', True)
        size = int(cfg.get('size', 1))    # 1=small(8px), 2=med(16px), 3=large(24px)

        font_size = min(30, max(6, size * 8))
        font = load_font(font_size)

        img = Image.new('RGB', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        bbox = draw.textbbox((0, 0), content, font=font)
        text_w = bbox[2] - bbox[0]
        text_h = bbox[3] - bbox[1]
        text_y = max(0, (32 - text_h) // 2)

        if scroll:
            now = time.time()
            elapsed = now - self.last_frame
            self.last_frame = now
            self.scroll_x -= speed * elapsed

            if self.scroll_x < -text_w:
                self.scroll_x = 64.0

            _paste_text(img, (int(self.scroll_x), text_y), content, color, font)
        else:
            text_x = max(0, (64 - text_w) // 2)
            _paste_text(img, (text_x, text_y), content, color, font)

        image_to_canvas(canvas, img)
