#!/usr/bin/env python3
"""
LED Matrix Controller — main entry point.
Must run as root: sudo python3 main.py
"""

import time
import threading
import signal
import sys
import os
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(name)s %(levelname)s %(message)s',
)
logger = logging.getLogger('main')

try:
    from rgbmatrix import RGBMatrix, RGBMatrixOptions
    MATRIX_AVAILABLE = True
except ImportError:
    MATRIX_AVAILABLE = False
    logger.warning("rgbmatrix not found — running in simulation mode (no display output)")

try:
    import RPi.GPIO as GPIO
    GPIO_AVAILABLE = True
except ImportError:
    GPIO_AVAILABLE = False
    logger.warning("RPi.GPIO not found — GPIO shutdown disabled")

from config import Config
from modes.clock import ClockMode
from modes.spotify import SpotifyMode
from modes.gameoflife import GameOfLifeMode
from modes.text import TextMode
from modes.patternflow import PatternflowMode


# ── Simulation canvas (dev/non-Pi use) ──────────────────────────────────────

class SimCanvas:
    def SetPixel(self, x, y, r, g, b):
        pass

    def SetImage(self, image, offset_x=0, offset_y=0, unsafe=True):
        pass

    def Clear(self):
        pass


# ── Controller ───────────────────────────────────────────────────────────────

class MatrixController:
    MODES = {
        'clock': ClockMode,
        'spotify': SpotifyMode,
        'gameoflife': GameOfLifeMode,
        'text': TextMode,
        'patternflow': PatternflowMode,
    }

    def __init__(self):
        self.config = Config()
        self.matrix = self._init_matrix()
        self.current_mode = None
        self.current_mode_name = None
        self.modes = {name: cls(self.config) for name, cls in self.MODES.items()}
        self.running = False
        self._mode_lock = threading.Lock()
        self._setup_gpio()
        self.set_mode(self.config.get('mode', 'clock'))

    def _init_matrix(self):
        if not MATRIX_AVAILABLE:
            return None

        opts = RGBMatrixOptions()
        opts.rows = 32
        opts.cols = 64
        opts.chain_length = 1
        opts.parallel = 1
        opts.hardware_mapping = 'adafruit-hat'
        opts.brightness = self.config.get('brightness', 50)
        opts.gpio_slowdown = 4
        opts.pwm_bits = 7
        opts.drop_privileges = False
        opts.disable_hardware_pulsing = True
        opts.limit_refresh_rate_hz = 100
        return RGBMatrix(options=opts)

    def _setup_gpio(self):
        if not GPIO_AVAILABLE:
            return
        pin = self.config.get('shutdown_gpio', 21)
        try:
            GPIO.setmode(GPIO.BCM)
            GPIO.setup(pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
            GPIO.add_event_detect(
                pin, GPIO.FALLING,
                callback=self._gpio_press,
                bouncetime=200,
            )
            logger.info(f"Shutdown button on GPIO{pin}")
        except Exception as e:
            logger.warning(f"GPIO setup failed: {e}")

    def _gpio_press(self, channel):
        press_start = time.time()
        while GPIO_AVAILABLE and GPIO.input(channel) == GPIO.LOW:
            held = time.time() - press_start
            if held >= 3.0:
                logger.info("Long press → shutdown")
                self.trigger_shutdown()
                return
            time.sleep(0.05)

    # ── Mode management ──────────────────────────────────────────────────────

    def set_mode(self, name, **kwargs):
        if name not in self.modes:
            logger.error(f"Unknown mode '{name}'")
            return False
        with self._mode_lock:
            if self.current_mode:
                self.current_mode.stop()
            self.current_mode = self.modes[name]
            self.current_mode_name = name
            if kwargs:
                self.config.set_section(name, kwargs)
            self.current_mode.start()
        self.config.set('mode', name)
        logger.info(f"Mode → {name}")
        return True

    def get_mode(self):
        return self.current_mode_name

    def get_mode_names(self):
        return list(self.modes.keys())

    def set_brightness(self, value):
        value = max(1, min(100, int(value)))
        self.config.set('brightness', value)
        if self.matrix:
            self.matrix.brightness = value

    # ── Main render loop ─────────────────────────────────────────────────────

    def run(self):
        self.running = True
        logger.info("Render loop started")

        if self.matrix:
            canvas = self.matrix.CreateFrameCanvas()
        else:
            canvas = SimCanvas()

        try:
            while self.running:
                with self._mode_lock:
                    mode = self.current_mode

                if mode:
                    try:
                        canvas.Clear()
                        mode.render(canvas)
                    except Exception as e:
                        logger.error(f"Render error: {e}")

                if self.matrix:
                    canvas = self.matrix.SwapOnVSync(canvas)
                else:
                    time.sleep(0.033)

        except KeyboardInterrupt:
            pass
        finally:
            self._cleanup()

    def _cleanup(self):
        self.running = False
        with self._mode_lock:
            if self.current_mode:
                self.current_mode.stop()
        if self.matrix:
            self.matrix.Clear()
            time.sleep(0.15)  # give refresh thread time to push blank frame
        if GPIO_AVAILABLE:
            try:
                GPIO.cleanup()
            except Exception:
                pass
        logger.info("Controller stopped")

    def trigger_shutdown(self):
        """Shut down the Pi. Called from GPIO or API."""
        logger.info("System shutdown requested")
        self._cleanup()
        os.system("sudo shutdown -h now")


# ── Entry point ───────────────────────────────────────────────────────────────

controller: MatrixController | None = None


def get_controller() -> MatrixController | None:
    return controller


if __name__ == '__main__':
    controller = MatrixController()

    from api import create_app
    flask_app = create_app(get_controller)

    def _run_api():
        flask_app.run(host='0.0.0.0', port=8080, debug=False, use_reloader=False)

    api_thread = threading.Thread(target=_run_api, daemon=True, name='api')
    api_thread.start()

    def _sig(sig, frame):
        logger.info(f"Signal {sig} received")
        controller._cleanup()
        sys.exit(0)

    signal.signal(signal.SIGTERM, _sig)
    signal.signal(signal.SIGINT, _sig)

    controller.run()
