import math

TWO_PI = math.tau
SIN_LUT_SIZE = 1024
_ANGLE_TO_LUT = SIN_LUT_SIZE / TWO_PI

_sin_lut: list[float] = [0.0] * SIN_LUT_SIZE
_built = False


def build_sin_lut():
    global _built
    if _built:
        return
    for i in range(SIN_LUT_SIZE):
        _sin_lut[i] = math.sin(i / SIN_LUT_SIZE * TWO_PI)
    _built = True


def fast_sin(x: float) -> float:
    return _sin_lut[int(x * _ANGLE_TO_LUT) & (SIN_LUT_SIZE - 1)]


def fast_cos(x: float) -> float:
    return fast_sin(x + math.pi / 2)


def fract(x: float) -> float:
    return x - math.floor(x)


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def approx_length(x: float, y: float) -> float:
    ax, ay = abs(x), abs(y)
    mx = ax if ax > ay else ay
    mn = ay if ax > ay else ax
    return mx + mn * 0.375
