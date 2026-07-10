# Patternflow canvas — adapted for led-matrix integration.
# The controller owns canvas creation and SwapOnVSync.
# Patterns call set_pixel() then present() (present is a no-op here).
# PatternflowMode.render() calls render_to(canvas) to push the frame.
import numpy as np
import logging
from PIL import Image

logger = logging.getLogger(__name__)

W = 64
H = 32

_diag_done = False

# Calibration — mirror of C++ config.h defaults
_GAMMA_R   = 2.5;  _WB_R = 0.92
_GAMMA_G   = 2.4;  _WB_G = 0.92
_GAMMA_B   = 2.2;  _WB_B = 1.00
_SAT_BOOST = 1.10

_buffer: np.ndarray = np.zeros((H, W, 3), dtype=np.uint8)
_out: np.ndarray = np.empty((H, W, 3), dtype=np.uint8)
_gamma_r: np.ndarray
_gamma_g: np.ndarray
_gamma_b: np.ndarray
_luts_ready = False


def _build_luts():
    global _gamma_r, _gamma_g, _gamma_b, _luts_ready
    lut = np.arange(256, dtype=np.float32) / 255.0
    _gamma_r = np.clip(np.power(lut, _GAMMA_R) * 255.0 * _WB_R, 0, 255).astype(np.uint8)
    _gamma_g = np.clip(np.power(lut, _GAMMA_G) * 255.0 * _WB_G, 0, 255).astype(np.uint8)
    _gamma_b = np.clip(np.power(lut, _GAMMA_B) * 255.0 * _WB_B, 0, 255).astype(np.uint8)
    _luts_ready = True


def init():
    _build_luts()
    clear()


def clear():
    _buffer[:] = 0


def set_pixel(x: int, y: int, r: int, g: int, b: int):
    if 0 <= x < W and 0 <= y < H:
        _buffer[y, x, 0] = r
        _buffer[y, x, 1] = g
        _buffer[y, x, 2] = b


def present():
    """No-op: controller calls render_to() instead of patterns triggering swap."""
    pass


def _corrected_frame() -> np.ndarray:
    """Apply sat boost + gamma LUTs and return the RGB output buffer."""
    if not _luts_ready:
        _build_luts()

    buf = _buffer.astype(np.int16)
    if _SAT_BOOST != 1.0:
        gray = ((buf[:, :, 0] * 77 + buf[:, :, 1] * 150 + buf[:, :, 2] * 29) >> 8)[:, :, np.newaxis]
        buf = np.clip(gray + (buf - gray) * _SAT_BOOST, 0, 255).astype(np.int16)

    _out[:, :, 0] = _gamma_r[buf[:, :, 0]]
    _out[:, :, 1] = _gamma_g[buf[:, :, 1]]
    _out[:, :, 2] = _gamma_b[buf[:, :, 2]]
    return _out


def render_to(canvas, fast_image: bool = True):
    """Apply correction and push the frame to the matrix canvas.

    SetImage is much faster because the rgbmatrix binding copies the whole
    frame in C. If a matrix build skips rows with SetImage, callers can pass
    fast_image=False to use the slower but reliable SetPixel path.
    """
    out = _corrected_frame()
    global _diag_done
    if not _diag_done:
        nonzero = int(np.count_nonzero(out.sum(axis=2)))
        path = "SetImage" if fast_image else "SetPixel"
        logger.info(f"render_to diag: path={path} out shape={out.shape} nonzero_pixels={nonzero}/{H*W}")
        _diag_done = True

    if fast_image:
        canvas.SetImage(Image.fromarray(out, 'RGB'))
        return

    for y in range(H):
        for x in range(W):
            r, g, b = out[y, x]
            canvas.SetPixel(x, y, int(r), int(g), int(b))
