import copy
import json
import os
import threading

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULT_CONFIG = {
    "mode": "clock",
    "brightness": 50,
    "shutdown_gpio": 21,
    "matrix": {
        "gpio_slowdown": 2,
        "pwm_bits": 7,
        "limit_refresh_rate_hz": 0,
        "disable_hardware_pulsing": False
    },
    "carousel": {
        "enabled": False,
        "skip_spotify_if_idle": False,
        "modes": ["clock", "spotify", "gameoflife", "text", "patternflow", "draw", "pomodoro", "library", "weather"],
        "interval": 30,
        "durations": {
            "clock": 30,
            "spotify": 30,
            "gameoflife": 30,
            "text": 30,
            "patternflow": 30,
            "draw": 30,
            "pomodoro": 30,
            "library": 30,
            "weather": 60
        }
    },
    "text": {
        "content": "Hello World!",
        "source": "manual",
        "url": "",
        "poll_interval": 60,
        "color": [255, 255, 255],
        "speed": 30,
        "size": 1,
        "scroll": True
    },
    "clock": {
        "color": [255, 0, 0],
        "show_seconds": True
    },
    "spotify": {
        "client_id": "",
        "client_secret": "",
        "redirect_uri": "",
        "callback_path": "/callback",
        "artist_speed": 12,
        "track_speed": 12
    },
    "gameoflife": {
        "speed": 10,
        "color": [0, 255, 0],
        "wrap": True
    },
    "patternflow": {
        "current_pattern": 0,
        "encoders_enabled": False,
        "invert_encoder": False,
        "show_fps": False,
        "donut_fast_render": True,
        "fast_image_push": True,
        "encoders": [
            {"clk": -1, "dt": -1, "sw": -1},
            {"clk": -1, "dt": -1, "sw": -1},
            {"clk": -1, "dt": -1, "sw": -1},
            {"clk": -1, "dt": -1, "sw": -1}
        ],
        "extra_buttons": [-1, -1]
    },
    "draw": {
        "width": 64,
        "scroll": False,
        "scroll_speed": 20,
        "pixels": []
    },
    "pomodoro": {
        "gradient_start": [30, 215, 96],
        "gradient_end": [255, 210, 64],
        "background_color": [0, 0, 0],
        "elapsed_background": [25, 25, 25],
        "text_color": [255, 255, 255],
        "flash_red": True,
        "flash_threshold_ms": 5000,
        "tick_pixel_enabled": True,
        "tick_pixel_color": [255, 255, 255],
        "return_after_elapsed_enabled": False,
        "return_after_elapsed_delay_s": 10,
        "return_after_elapsed_mode": "clock"
    },
    "reminders": {
        "enabled": False,
        "palettes": [
            {"id": "pal-classic", "name": "Classic", "text_color": [255, 255, 255], "gradient_start": [20, 30, 80], "gradient_end": [180, 40, 80]},
            {"id": "pal-ocean",   "name": "Ocean",   "text_color": [220, 240, 255], "gradient_start": [10, 40, 100], "gradient_end": [0, 80, 160]},
            {"id": "pal-sunset",  "name": "Sunset",  "text_color": [255, 230, 180], "gradient_start": [160, 50, 0], "gradient_end": [120, 0, 40]},
            {"id": "pal-forest",  "name": "Forest",  "text_color": [200, 255, 200], "gradient_start": [10, 60, 20], "gradient_end": [0, 100, 40]},
        ],
        "items": []
    },
    "library": {
        "rotation_enabled": True,
        "interval": 10,
        "items": []
    },
    "night_mode": {
        "enabled": False,
        "brightness": 20,
        "start": "22:00",
        "end": "05:00"
    },
    "weather": {
        "api_key": "",
        "units": "metric",
        "refresh_interval": 600,
        "city_interval": 30,
        "cities": [],
        "test_condition": ""
    }
}


class Config:
    def __init__(self):
        self._data = self._deep_copy(DEFAULT_CONFIG)
        self._lock = threading.Lock()
        self._load()

    def _deep_copy(self, d):
        return copy.deepcopy(d)

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    saved = json.load(f)
                    self._deep_update(self._data, saved)
                    self._migrate_removed_modes()
            except Exception as e:
                print(f"Config load error: {e}")

    def _migrate_removed_modes(self):
        self._data.pop("ledder", None)
        if self._data.get("mode") == "ledder":
            self._data["mode"] = "clock"

    def _deep_update(self, base, update):
        for key, value in update.items():
            if key in base and isinstance(base[key], dict) and isinstance(value, dict):
                self._deep_update(base[key], value)
            else:
                base[key] = value

    def save(self):
        try:
            with open(CONFIG_FILE, 'w') as f:
                json.dump(self._data, f, indent=2)
        except Exception as e:
            print(f"Config save error: {e}")

    def get(self, key, default=None):
        with self._lock:
            return self._data.get(key, default)

    def get_section(self, section):
        with self._lock:
            return self._deep_copy(self._data.get(section, {}))

    def set(self, key, value):
        with self._lock:
            self._data[key] = value
        self.save()

    def set_section(self, section, data):
        with self._lock:
            if section not in self._data:
                self._data[section] = {}
            self._deep_update(self._data[section], data)
        self.save()

    def get_all(self):
        with self._lock:
            return self._deep_copy(self._data)

    def import_all(self, data):
        with self._lock:
            self._deep_update(self._data, data)
        self.save()
