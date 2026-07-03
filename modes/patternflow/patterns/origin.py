# SPDX-License-Identifier: CC-BY-SA-4.0
# Pattern: Origin — adapted for 64×32 panel
# Author: Seunghun LEE  |  Port: led-matrix integration
import math
from .. import core_math   as pf_math
from .. import core_color  as pf_color
from .. import core_canvas as pf_canvas

NAME = "Origin"
KNOB_LABELS = ["hue", "speed", "mode", "freq"]

# Presets scaled to fit 64×32 (halved from the 128×64 originals).
# Layout: (rows, cols, gap, tile_size, grid_step, grid_cells)
_PRESETS = [
    (1, 2, 2, 28, 4, 7),   # 2 big tiles  — totalW=62, totalH=32
    (2, 4, 1, 13, 2, 6),   # 8 medium tiles — totalW=57, totalH=29
    (3, 6, 1,  9, 1, 9),   # 18 small tiles — totalW=61, totalH=31
    (3, 6, 1,  9, 3, 3),   # same layout, coarser grid
    (4, 8, 0,  8, 2, 4),   # 32 tiny tiles, full fill — 64×32
]

_hue_deg = 0
_speed   = 2.0
_mode    = 0
_freq    = 20.0
_phase   = 0.0

_cur_mode = -1
_offset_x = 0
_offset_y = 0
_dist_lut: list[list[float]] = []
_color_ramp: list[tuple] = []


def _update_ramp(hue_norm: float):
    global _color_ramp
    hr, hg, hb = pf_color.hsv_to_rgb(hue_norm, 1.0, 1.0)
    _color_ramp = [
        (0.000, 0,   0,   0),
        (0.154, 40,  40,  40),
        (0.556, hr,  hg,  hb),
        (0.816, 255, 255, 255),
        (1.000, 255, 255, 255),
    ]


def _sample_ramp(val: float) -> tuple[int, int, int]:
    return pf_color.sample_ramp(_color_ramp, (val + 1.0) * 0.5)


def _apply_preset(idx: int):
    global _cur_mode, _offset_x, _offset_y, _dist_lut
    rows, cols, gap, tile_size, grid_step, grid_cells = _PRESETS[idx]
    total_w = cols * tile_size + (cols + 1) * gap
    total_h = rows * tile_size + (rows + 1) * gap
    _offset_x = (pf_canvas.W - total_w) // 2
    _offset_y = (pf_canvas.H - total_h) // 2
    cx = tile_size / 2.0
    _dist_lut = []
    for gy in range(grid_cells):
        row = []
        for gx in range(grid_cells):
            dx = gx * grid_step + grid_step / 2.0 - cx
            dy = gy * grid_step + grid_step / 2.0 - cx
            row.append(math.sqrt(dx * dx + dy * dy))
        _dist_lut.append(row)
    _cur_mode = idx


def setup():
    global _hue_deg, _speed, _mode, _freq, _phase
    pf_math.build_sin_lut()
    _hue_deg = 0; _speed = 2.0; _mode = 0; _freq = 220.0; _phase = 0.0
    _apply_preset(0)
    _update_ramp(0.0)


def update(dt: float, inp) -> None:
    global _hue_deg, _speed, _mode, _freq, _phase, _cur_mode

    d = inp.knob_deltas[0]
    if d: _hue_deg = (_hue_deg + d * 10) % 360
    if inp.btn_pressed[0]: _hue_deg = 0

    d = inp.knob_deltas[1]
    if d: _speed = max(0.0, min(5.0, _speed + d * 0.1))
    if inp.btn_pressed[1]: _speed = 0.0

    d = inp.knob_deltas[2]
    if d: _mode = ((_mode + int(d)) % len(_PRESETS) + len(_PRESETS)) % len(_PRESETS)
    if inp.btn_pressed[2]: _mode = 0

    d = inp.knob_deltas[3]
    if d: _freq = max(0.1, min(1000.0, _freq + d * 10.0))
    if inp.btn_pressed[3]: _freq = 0.1

    if _mode != _cur_mode:
        _apply_preset(_mode)

    _phase += dt * _speed * 2.0
    _update_ramp(_hue_deg / 360.0)


def draw() -> None:
    rows, cols, gap, tile_size, grid_step, grid_cells = _PRESETS[_cur_mode]
    br = 0.80
    cell_w = tile_size + gap
    cell_h = tile_size + gap
    freq_base = _freq
    freq_var  = _freq * 0.9

    for y in range(pf_canvas.H):
        for x in range(pf_canvas.W):
            lx = x - _offset_x
            ly = y - _offset_y
            ti = (lx - gap) // cell_w
            tj = (ly - gap) // cell_h

            if ti < 0 or ti >= cols or tj < 0 or tj >= rows:
                pf_canvas.set_pixel(x, y, 0, 0, 0)
                continue

            local_x = lx - (gap + ti * cell_w)
            local_y = ly - (gap + tj * cell_h)
            if local_x < 0 or local_x >= tile_size or local_y < 0 or local_y >= tile_size:
                pf_canvas.set_pixel(x, y, 0, 0, 0)
                continue

            gx = min(local_x // grid_step, grid_cells - 1)
            gy = min(local_y // grid_step, grid_cells - 1)
            dist = _dist_lut[gy][gx]
            tile_freq = freq_base + (tj * cols + ti) * freq_var * 0.15
            wave = pf_math.fast_sin(dist * tile_freq * 2.0 + _phase)
            r, g, b = _sample_ramp(wave * br)
            pf_canvas.set_pixel(x, y, r, g, b)

    pf_canvas.present()
