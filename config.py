import json
import os
import threading

CONFIG_FILE = os.path.join(os.path.dirname(__file__), 'config.json')

DEFAULT_CONFIG = {
    "mode": "clock",
    "brightness": 50,
    "shutdown_gpio": 21,
    "text": {
        "content": "Hello World!",
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
        "redirect_uri": "http://YOUR_PI_IP:8080/callback"
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
        "encoders": [
            {"clk": -1, "dt": -1, "sw": -1},
            {"clk": -1, "dt": -1, "sw": -1},
            {"clk": -1, "dt": -1, "sw": -1},
            {"clk": -1, "dt": -1, "sw": -1}
        ]
    }
}


class Config:
    def __init__(self):
        self._data = self._deep_copy(DEFAULT_CONFIG)
        self._lock = threading.Lock()
        self._load()

    def _deep_copy(self, d):
        return json.loads(json.dumps(d))

    def _load(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    saved = json.load(f)
                    self._deep_update(self._data, saved)
            except Exception as e:
                print(f"Config load error: {e}")

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
