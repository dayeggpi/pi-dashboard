# Patternflow encoder layer — adapted for led-matrix.
# GPIO.setmode(BCM) is already called by MatrixController before modes start.
# cleanup() removes only encoder event detects, NOT a full GPIO.cleanup().
import time
import threading
import logging

logger = logging.getLogger(__name__)

try:
    import RPi.GPIO as GPIO
    _GPIO_OK = True
except ImportError:
    _GPIO_OK = False


class InputFrame:
    __slots__ = ('knobs', 'knob_deltas', 'btn_pressed', 'btn_held', 'now')

    def __init__(self):
        self.knobs:       list[int]  = [0, 0, 0, 0]
        self.knob_deltas: list[int]  = [0, 0, 0, 0]
        self.btn_pressed: list[bool] = [False, False, False, False]
        self.btn_held:    list[bool] = [False, False, False, False]
        self.now:         float      = 0.0


class RotaryEncoder:
    def __init__(self, pin_clk: int, pin_dt: int, invert: bool = False):
        self._clk = pin_clk
        self._dt  = pin_dt
        self._invert = invert
        self._pos = 0
        self._lock = threading.Lock()
        GPIO.setup(pin_clk, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(pin_dt,  GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._state = (GPIO.input(pin_clk) << 1) | GPIO.input(pin_dt)
        GPIO.add_event_detect(pin_clk, GPIO.BOTH, callback=self._cb)
        GPIO.add_event_detect(pin_dt,  GPIO.BOTH, callback=self._cb)

    def _cb(self, _ch):
        s = (GPIO.input(self._clk) << 1) | GPIO.input(self._dt)
        combined = (self._state << 2) | s
        inc = 0
        if   combined in (0b0001, 0b0111, 0b1110, 0b1000): inc =  1
        elif combined in (0b0010, 0b1011, 0b1101, 0b0100): inc = -1
        if self._invert: inc = -inc
        with self._lock:
            self._pos += inc
        self._state = s

    def remove(self):
        try: GPIO.remove_event_detect(self._clk)
        except Exception: pass
        try: GPIO.remove_event_detect(self._dt)
        except Exception: pass

    @property
    def clicks(self) -> int:
        with self._lock:
            return self._pos // 4


class Button:
    DEBOUNCE = 0.05

    def __init__(self, pin: int):
        self._pin = pin
        GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        self._last_state = GPIO.HIGH
        self._last_change = 0.0
        self._press_start = 0.0
        self._long_fired  = False

    def pressed(self) -> bool:
        cur = GPIO.input(self._pin)
        now = time.monotonic()
        if cur != self._last_state and (now - self._last_change) > self.DEBOUNCE:
            self._last_state = cur
            self._last_change = now
            if cur == GPIO.LOW:
                self._press_start = now
                self._long_fired  = False
                return True
        return False

    def is_down(self) -> bool:
        return GPIO.input(self._pin) == GPIO.LOW

    def long_pressed(self, threshold: float = 1.0) -> bool:
        if not self.is_down():
            self._long_fired = False
            return False
        if not self._long_fired and (time.monotonic() - self._press_start) > threshold:
            self._long_fired = True
            return True
        return False


# K1↔K2 mirrored (front-panel left-right match), K3/K4 straight
_LOGICAL_TO_PHYS = [1, 0, 2, 3]

_encoders: list[RotaryEncoder] = []
_buttons:  list[Button | None] = []


def init_encoders(enc_cfg: list[dict], invert: bool = False) -> bool:
    """
    enc_cfg: list of 4 dicts with keys 'clk', 'dt', 'sw' (BCM pin numbers).
             Use -1 for unconnected pins. Returns True if at least one encoder inited.
    """
    global _encoders, _buttons
    if not _GPIO_OK:
        logger.warning("RPi.GPIO not available — encoders disabled")
        return False

    _encoders.clear()
    _buttons.clear()

    ok = False
    for i, cfg in enumerate(enc_cfg):
        clk = cfg.get('clk', -1)
        dt  = cfg.get('dt',  -1)
        sw  = cfg.get('sw',  -1)
        try:
            if clk >= 0 and dt >= 0:
                _encoders.append(RotaryEncoder(clk, dt, invert))
                ok = True
            else:
                _encoders.append(None)
        except Exception as e:
            logger.warning(f"Encoder {i+1} init failed (CLK={clk}, DT={dt}): {e}")
            _encoders.append(None)

        try:
            _buttons.append(Button(sw) if sw >= 0 else None)
        except Exception as e:
            logger.warning(f"Button {i+1} init failed (SW={sw}): {e}")
            _buttons.append(None)

    return ok


def cleanup_encoders():
    for enc in _encoders:
        if enc is not None:
            enc.remove()
    _encoders.clear()
    _buttons.clear()


def _enc(logical: int):
    phys = _LOGICAL_TO_PHYS[logical]
    return _encoders[phys] if phys < len(_encoders) else None


def _btn(logical: int):
    phys = _LOGICAL_TO_PHYS[logical]
    return _buttons[phys] if phys < len(_buttons) else None


def read_input_frame(prev_knobs: list[int], last_delta_t: list[float]) -> InputFrame:
    inp = InputFrame()
    inp.now = time.monotonic()

    for i in range(4):
        enc = _enc(i)
        inp.knobs[i] = enc.clicks if enc else 0

    for i in range(4):
        raw = inp.knobs[i] - prev_knobs[i]
        if raw != 0:
            gap_ms = (inp.now - last_delta_t[i]) * 1000.0
            if   gap_ms < 40:  mult = 5
            elif gap_ms < 90:  mult = 3
            elif gap_ms < 180: mult = 2
            else:              mult = 1
            inp.knob_deltas[i] = raw * mult
            last_delta_t[i] = inp.now
        else:
            inp.knob_deltas[i] = 0
        prev_knobs[i] = inp.knobs[i]

    for i in range(4):
        btn = _btn(i)
        inp.btn_pressed[i] = btn.pressed()  if btn else False
        inp.btn_held[i]    = btn.is_down()  if btn else False

    return inp


def logical_button(i: int):
    return _btn(i)
