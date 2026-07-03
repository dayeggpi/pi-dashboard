from .patterns import origin, wave_saw, pattern001

# Each entry is a module with: NAME, KNOB_LABELS, setup(), update(dt, inp), draw()
# Add new patterns by importing the module and appending here.
PATTERNS = [
    origin,
    wave_saw,
    pattern001,
]
