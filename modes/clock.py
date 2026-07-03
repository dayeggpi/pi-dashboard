import time
from PIL import Image, ImageDraw
from modes.base import BaseMode, image_to_canvas

# seg indices: top, top-right, bot-right, bottom, bot-left, top-left, middle
DIGIT_SEGS = {
    '0': [1, 1, 1, 1, 1, 1, 0],
    '1': [0, 1, 1, 0, 0, 0, 0],
    '2': [1, 1, 0, 1, 1, 0, 1],
    '3': [1, 1, 1, 1, 0, 0, 1],
    '4': [0, 1, 1, 0, 0, 1, 1],
    '5': [1, 0, 1, 1, 0, 1, 1],
    '6': [1, 0, 1, 1, 1, 1, 1],
    '7': [1, 1, 1, 0, 0, 0, 0],
    '8': [1, 1, 1, 1, 1, 1, 1],
    '9': [1, 1, 1, 1, 0, 1, 1],
}


def draw_digit(draw, x, y, char, color, w=7, h=13, t=2):
    segs = DIGIT_SEGS.get(str(char), [0] * 7)
    mid = y + h // 2

    if segs[0]:  # top
        draw.rectangle([x + 1, y, x + w - 2, y + t - 1], fill=color)
    if segs[1]:  # top-right
        draw.rectangle([x + w - t, y + 1, x + w - 1, mid - 1], fill=color)
    if segs[2]:  # bot-right
        draw.rectangle([x + w - t, mid + 1, x + w - 1, y + h - 2], fill=color)
    if segs[3]:  # bottom
        draw.rectangle([x + 1, y + h - t, x + w - 2, y + h - 1], fill=color)
    if segs[4]:  # bot-left
        draw.rectangle([x, mid + 1, x + t - 1, y + h - 2], fill=color)
    if segs[5]:  # top-left
        draw.rectangle([x, y + 1, x + t - 1, mid - 1], fill=color)
    if segs[6]:  # middle
        draw.rectangle([x + 1, mid - 1, x + w - 2, mid + t - 2], fill=color)


class ClockMode(BaseMode):
    def render(self, canvas):
        cfg = self.config.get_section('clock')
        color = tuple(cfg.get('color', [255, 0, 0]))
        show_seconds = cfg.get('show_seconds', True)

        now = time.localtime()
        img = Image.new('RGB', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(img)

        blink = (now.tm_sec % 2 == 0)

        if show_seconds:
            # 6 digits + 2 colons, digit=7x13, gap=1, colon=3
            # layout: DD:DD:DD total ≈ 52px → start x=6
            dw, dh, t = 7, 13, 2
            sy = (32 - dh) // 2
            positions = [
                (6,  f"{now.tm_hour:02d}"[0]),
                (14, f"{now.tm_hour:02d}"[1]),
                (25, f"{now.tm_min:02d}"[0]),
                (33, f"{now.tm_min:02d}"[1]),
                (44, f"{now.tm_sec:02d}"[0]),
                (52, f"{now.tm_sec:02d}"[1]),
            ]
            for cx, ch in positions:
                draw_digit(draw, cx, sy, ch, color, dw, dh, t)

            # colons
            if blink:
                dot_color = color
            else:
                dot_color = (80, 0, 0) if color == (255, 0, 0) else (30, 30, 30)

            for cx in [22, 41]:
                draw.rectangle([cx, sy + 3, cx + 1, sy + 4], fill=dot_color)
                draw.rectangle([cx, sy + 8, cx + 1, sy + 9], fill=dot_color)
        else:
            # 4 digits + 1 colon, bigger: digit=12x22
            dw, dh, t = 12, 22, 2
            sy = (32 - dh) // 2
            positions = [
                (2,  f"{now.tm_hour:02d}"[0]),
                (15, f"{now.tm_hour:02d}"[1]),
                (32, f"{now.tm_min:02d}"[0]),
                (45, f"{now.tm_min:02d}"[1]),
            ]
            for cx, ch in positions:
                draw_digit(draw, cx, sy, ch, color, dw, dh, t)

            dot_color = color if blink else (80, 0, 0) if color == (255, 0, 0) else (30, 30, 30)
            draw.rectangle([28, sy + 6, 29, sy + 7], fill=dot_color)
            draw.rectangle([28, sy + 14, 29, sy + 15], fill=dot_color)

        image_to_canvas(canvas, img)
