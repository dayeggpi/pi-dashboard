import math


def hsv_to_rgb(h: float, s: float, v: float) -> tuple[int, int, int]:
    h = h - math.floor(h)
    if h < 0:
        h += 1.0
    s = max(0.0, min(1.0, s))
    v = max(0.0, min(1.0, v))
    c = v * s
    hh = h * 6.0
    x = c * (1.0 - abs(math.fmod(hh, 2.0) - 1.0))
    m = v - c
    i = int(hh) % 6
    if i == 0:   rf, gf, bf = c, x, 0.0
    elif i == 1: rf, gf, bf = x, c, 0.0
    elif i == 2: rf, gf, bf = 0.0, c, x
    elif i == 3: rf, gf, bf = 0.0, x, c
    elif i == 4: rf, gf, bf = x, 0.0, c
    else:        rf, gf, bf = c, 0.0, x
    return int((rf + m) * 255), int((gf + m) * 255), int((bf + m) * 255)


# ramp: list of (position, r, g, b), positions ascending. Step function (no interp).
def sample_ramp(ramp: list[tuple], t: float) -> tuple[int, int, int]:
    t = max(0.0, min(1.0, t))
    r, g, b = ramp[0][1], ramp[0][2], ramp[0][3]
    for pos, cr, cg, cb in ramp:
        if t >= pos:
            r, g, b = cr, cg, cb
        else:
            break
    return r, g, b
