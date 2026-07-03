# SPDX-License-Identifier: CC-BY-SA-4.0
# Pattern: <Name>
# Copy this file, rename it, and add to registry.py:
#   from .patterns.yourname import YourName; PATTERNS.append(YourName)
from .. import core_math   as pf_math
from .. import core_color  as pf_color
from .. import core_noise  as pf_noise
from .. import core_canvas as pf_canvas

NAME = "Template"
KNOB_LABELS = ["k1", "k2", "k3", "k4"]


def setup():
    pf_math.build_sin_lut()


def update(dt: float, inp) -> None:
    # inp.knob_deltas[i]  — per-frame detent delta (±1 normal, ±2–5 fast spin)
    # inp.btn_pressed[i]  — True on the frame a button is first pressed
    # inp.btn_held[i]     — True while button is held
    # i = 0..3
    pass


def draw() -> None:
    for y in range(pf_canvas.H):
        for x in range(pf_canvas.W):
            pf_canvas.set_pixel(x, y, 0, 0, 0)
    pf_canvas.present()   # no-op in led-matrix; required for standalone rpi use
