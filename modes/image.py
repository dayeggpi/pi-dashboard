import os
import time
from PIL import Image
from modes.base import BaseMode, image_to_canvas

W, H = 64, 32
_STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'static')
IMAGE_PNG = os.path.join(_STATIC_DIR, 'matrix_image.png')
IMAGE_GIF = os.path.join(_STATIC_DIR, 'matrix_image.gif')


class ImageMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self._frames = []
        self._durations = []   # ms per frame
        self._frame_idx = 0
        self._frame_deadline = 0.0
        self._file_mtime = None
        self._last_check = 0.0

    def start(self):
        super().start()
        self._last_check = 0.0

    def _load_media(self):
        now = time.time()
        if now - self._last_check < 1.0 and self._frames:
            return
        self._last_check = now

        gif = os.path.abspath(IMAGE_GIF)
        png = os.path.abspath(IMAGE_PNG)
        path = gif if os.path.exists(gif) else (png if os.path.exists(png) else None)

        if path is None:
            self._frames = [Image.new('RGB', (W, H), (0, 0, 0))]
            self._durations = [100]
            self._file_mtime = None
            return

        try:
            mtime = os.path.getmtime(path)
            if mtime == self._file_mtime and self._frames:
                return
            img = Image.open(path)
            n = getattr(img, 'n_frames', 1)
            frames, durations = [], []
            for i in range(n):
                img.seek(i)
                frame = img.convert('RGB').copy()
                if frame.size != (W, H):
                    frame = frame.resize((W, H), Image.LANCZOS)
                frames.append(frame)
                ms = img.info.get('duration', 100)
                durations.append(max(20, ms))  # floor at 20ms (avoid 0-delay frames)
            self._frames = frames
            self._durations = durations
            self._file_mtime = mtime
            self._frame_idx = 0
            self._frame_deadline = time.time() + durations[0] / 1000.0
        except Exception:
            self._frames = [Image.new('RGB', (W, H), (0, 0, 0))]
            self._durations = [100]
            self._file_mtime = None

    def render(self, canvas):
        self._load_media()
        if not self._frames:
            return
        now = time.time()
        if len(self._frames) > 1 and now >= self._frame_deadline:
            self._frame_idx = (self._frame_idx + 1) % len(self._frames)
            self._frame_deadline = now + self._durations[self._frame_idx] / 1000.0
        image_to_canvas(canvas, self._frames[self._frame_idx])
