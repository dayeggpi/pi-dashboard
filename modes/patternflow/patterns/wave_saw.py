# SPDX-License-Identifier: CC-BY-SA-4.0
# Pattern: Wave Saw — adapted for 64×32 panel
# Author: Seunghun LEE  |  Port: led-matrix integration
import math
from .. import core_math   as pf_math
from .. import core_noise  as pf_noise
from .. import core_canvas as pf_canvas

NAME = "Wave Saw"
KNOB_LABELS = ["angle", "scale", "dist", "dscale"]

_DETAIL_ROUGHNESS = 0.22
_DETAIL_OCTAVES   = 2
_PHASE_PER_SEC    = 2.4
_SCALE_MIN,  _SCALE_MAX  = 0.5, 6.0
_DIST_MIN,   _DIST_MAX   = 0.0, 4.0
_DSCALE_MIN, _DSCALE_MAX = 0.3, 5.0
_INV_TWO_PI = 1.0 / (2.0 * math.pi)

_angle  = 0.0
_scale  = 3.0
_dist   = 0.0
_dscale = 1.0
_phase  = 0.0


def _color(t: float) -> tuple[int, int, int]:
    if   t < 0.14: return (255, 255, 255)
    elif t < 0.40: return (255, 0,   0)
    else:          return (0,   0,   255)


def setup():
    global _angle, _scale, _dist, _dscale, _phase
    pf_math.build_sin_lut()
    _angle = 0.0; _scale = 3.0; _dist = 0.0; _dscale = 1.0; _phase = 0.0


def update(dt: float, inp) -> None:
    global _angle, _scale, _dist, _dscale, _phase

    d = inp.knob_deltas[0]
    if d: _angle = (_angle + d * 0.1) % (2.0 * math.pi)
    if inp.btn_pressed[0]: _angle = 0.0

    d = inp.knob_deltas[1]
    if d: _scale = max(_SCALE_MIN, min(_SCALE_MAX, _scale + d * 0.2))
    if inp.btn_pressed[1]: _scale = 3.0

    d = inp.knob_deltas[2]
    if d: _dist = max(_DIST_MIN, min(_DIST_MAX, _dist + d * 0.1))
    if inp.btn_pressed[2]: _dist = 0.0

    d = inp.knob_deltas[3]
    if d: _dscale = max(_DSCALE_MIN, min(_DSCALE_MAX, _dscale + d * 0.2))
    if inp.btn_pressed[3]: _dscale = 1.0

    _phase += dt * _PHASE_PER_SEC


def draw() -> None:
    cos_a = pf_math.fast_cos(_angle)
    sin_a = pf_math.fast_sin(_angle)
    hw = pf_canvas.W / 2.0
    hh = pf_canvas.H / 2.0
    use_dist = _dist > 0.01

    for y in range(pf_canvas.H):
        v = (y - hh) / pf_canvas.H
        for x in range(pf_canvas.W):
            u = (x - hw) / hw
            xr = u * cos_a - v * sin_a
            yr = u * sin_a + v * cos_a
            n = xr * _scale * 20.0 + _phase
            if use_dist:
                n += _dist * pf_noise.fractal2d(xr * _dscale, yr * _dscale,
                                                _DETAIL_OCTAVES, _DETAIL_ROUGHNESS)
            t = n * _INV_TWO_PI
            t -= math.floor(t)
            r, g, b = _color(t)
            pf_canvas.set_pixel(x, y, r, g, b)

    pf_canvas.present()
