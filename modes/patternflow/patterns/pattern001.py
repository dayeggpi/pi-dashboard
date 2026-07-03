# Pattern: Pattern 001
import math
from .. import core_color  as pf_color
from .. import core_canvas as pf_canvas

NAME = "Pattern 001"
KNOB_LABELS = ["hue", "speed", "scale", "chaos"]

_hue_base = 0.5
_speed = 1.0
_scale = 0.1
_chaos = 1.0
_time_acc = 0.0


def _clamp(val: float, min_val: float, max_val: float) -> float:
    return max(min_val, min(max_val, val))


def setup():
    global _hue_base, _speed, _scale, _chaos, _time_acc
    _hue_base = 0.5
    _speed = 1.0
    _scale = 0.1
    _chaos = 1.0
    _time_acc = 0.0


def update(dt: float, inp) -> None:
    global _hue_base, _speed, _scale, _chaos, _time_acc

    d = inp.knob_deltas[0]
    if d:
        _hue_base = (_hue_base + d * 0.05) % 1.0
    if inp.btn_pressed[0]:
        _hue_base = 0.5

    d = inp.knob_deltas[1]
    if d:
        _speed = max(0.0, _speed + d * 0.05)
    if inp.btn_pressed[1]:
        _speed = 1.0

    d = inp.knob_deltas[2]
    if d:
        _scale = _clamp(_scale + d * 0.01, 0.02, 0.2)
    if inp.btn_pressed[2]:
        _scale = 0.1

    d = inp.knob_deltas[3]
    if d:
        _chaos = _clamp(_chaos + d * 0.1, 0.0, 3.0)
    if inp.btn_pressed[3]:
        _chaos = 1.0

    _time_acc += dt * _speed


def draw() -> None:
    t = _time_acc
    s = _scale
    c = _chaos

    for y in range(pf_canvas.H):
        ny = y * s
        for x in range(pf_canvas.W):
            nx = x * s

            v1 = math.sin(nx + t)
            v2 = math.cos(ny - t * 0.8)

            warp_x = math.sin(ny * 2.0 + t) * c
            warp_y = math.cos(nx * 2.0 - t * 1.2) * c

            v3 = math.sin((nx + warp_x) * 1.5 + t * 1.5)
            v4 = math.cos((ny + warp_y) * 1.5 - t)

            field = abs(v1 + v2 + v3 + v4)
            val = 1.0 - field * 0.5
            val = _clamp(val, 0.0, 1.0) ** 3.0
            val = _clamp(val * 2.5, 0.0, 1.0)

            hue = (_hue_base + nx * 0.1 + ny * 0.1 + field * 0.05) % 1.0
            r, g, b = pf_color.hsv_to_rgb(hue, 1.0 - val * 0.2, val)
            pf_canvas.set_pixel(x, y, r, g, b)

    pf_canvas.present()
