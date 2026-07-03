# Patternflow canvas — adapted for led-matrix integration.
# The controller owns canvas creation and SwapOnVSync.
# Patterns call set_pixel() then present() (present is a no-op here).
# PatternflowMode.render() calls render_to(canvas) to push the frame.
import numpy as np
import logging

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


def render_to(canvas):
    """Apply sat boost + gamma LUTs, push every pixel via SetPixel.

    SetImage skips rows on some rpi-rgb-led-matrix builds; SetPixel is the
    reliable path that all other modes use internally.
    """
    if not _luts_ready:
        _build_luts()

    buf = _buffer.astype(np.int32)
    if _SAT_BOOST != 1.0:
        gray = ((buf[:, :, 0] * 77 + buf[:, :, 1] * 150 + buf[:, :, 2] * 29) >> 8)[:, :, np.newaxis]
        buf = np.clip(gray + (buf - gray) * _SAT_BOOST, 0, 255).astype(np.int32)

    out = np.empty((H, W, 3), dtype=np.uint8)
    out[:, :, 0] = _gamma_r[buf[:, :, 0]]
    out[:, :, 1] = _gamma_g[buf[:, :, 1]]
    out[:, :, 2] = _gamma_b[buf[:, :, 2]]

    global _diag_done
    if not _diag_done:
        nonzero = int(np.count_nonzero(out.sum(axis=2)))
        logger.info(f"render_to diag: out shape={out.shape} nonzero_pixels={nonzero}/{H*W}")
        _diag_done = True

    rows = out.tolist()
    for y, row in enumerate(rows):
        for x, (r, g, b) in enumerate(row):
            canvas.SetPixel(x, y, r, g, b)
