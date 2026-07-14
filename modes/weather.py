import math
import random
import threading
import time

from urllib.parse import quote as _url_quote

import requests
from PIL import Image, ImageDraw, ImageFont

from modes.base import BaseMode, image_to_canvas
from modes.clock import draw_digit

W, H = 64, 32
PANEL_X = 27   # right panel (animation) starts here
GRAPH_Y = 24   # hourly graph starts here (rows 24-31)
ANIM_CX = PANEL_X + (W - PANEL_X) // 2   # 46
ANIM_CY = (GRAPH_Y) // 2                  # 12

_FONT = ImageFont.load_default()

TEST_PRESETS = {
    'clear_day':     {'temp': 24, 'humidity': 45, 'code': 800, 'description': 'Clear sky',       'is_day': True},
    'clear_night':   {'temp': 14, 'humidity': 68, 'code': 800, 'description': 'Clear sky',       'is_day': False},
    'partly_cloudy': {'temp': 19, 'humidity': 60, 'code': 802, 'description': 'Partly cloudy',   'is_day': True},
    'cloudy':        {'temp': 16, 'humidity': 74, 'code': 804, 'description': 'Overcast',        'is_day': True},
    'drizzle':       {'temp': 13, 'humidity': 84, 'code': 301, 'description': 'Drizzle',         'is_day': True},
    'rain':          {'temp': 10, 'humidity': 89, 'code': 501, 'description': 'Moderate rain',   'is_day': True},
    'thunderstorm':  {'temp':  9, 'humidity': 93, 'code': 211, 'description': 'Thunderstorm',    'is_day': True},
    'snow':          {'temp': -3, 'humidity': 86, 'code': 601, 'description': 'Snow',            'is_day': True},
    'fog':           {'temp':  7, 'humidity': 97, 'code': 741, 'description': 'Fog',             'is_day': True},
    'extreme_hot':   {'temp': 43, 'humidity': 12, 'code': 900, 'description': 'Extreme heat',    'is_day': True},
    'extreme_cold':  {'temp': -22,'humidity': 70, 'code': 901, 'description': 'Extreme cold',    'is_day': True},
}


def _code_to_type(code, is_day=True):
    if 200 <= code < 300: return 'thunderstorm'
    if 300 <= code < 400: return 'drizzle'
    if 500 <= code < 600: return 'rain'
    if 600 <= code < 700: return 'snow'
    if 700 <= code < 800: return 'fog'
    if code == 800: return 'clear_day' if is_day else 'clear_night'
    if 801 <= code <= 802: return 'partly_cloudy'
    if 803 <= code < 900: return 'clouds'
    if code == 900: return 'extreme_hot'
    if code == 901: return 'extreme_cold'
    return 'clear_day' if is_day else 'clear_night'


def _temp_color(temp):
    """Blue (cold) → cyan → green → yellow → red (hot)."""
    if temp <= 0:
        return (40, 80, 200)
    if temp <= 10:
        t = temp / 10
        return (int(40 + t * 20), int(80 + t * 100), int(200 - t * 50))
    if temp <= 20:
        t = (temp - 10) / 10
        return (int(60 + t * 100), int(180 + t * 30), int(150 - t * 150))
    if temp <= 30:
        t = (temp - 20) / 10
        return (int(160 + t * 90), int(210 - t * 80), 0)
    t = min(1.0, (temp - 30) / 15)
    return (min(255, 250), int(130 - t * 130), 0)


def _fake_forecast(base_temp):
    return [base_temp + math.sin(i * 0.7) * 5 + (i - 6) * 0.3 for i in range(12)]


class WeatherMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self._lock = threading.Lock()
        self._weather = {}     # city_idx -> dict
        self._forecast = {}    # city_idx -> [float]
        self._last_fetch = {}  # city_idx -> monotonic
        self._last_api_error = ''
        self._known_city_ids = []  # tracks city list identity to detect changes
        self._fetch_stop = threading.Event()
        self._fetch_thread = None

        # city carousel
        self._city_idx = 0
        self._city_start = 0.0

        # animation state
        self._t = 0.0
        self._last_mono = 0.0
        self._sun_angle = 0.0
        self._cloud_x = 0.0
        self._lightning_bolt = []
        self._lightning_until = 0.0
        self._lightning_next = 0.0
        self._rain = []
        self._snow = []
        self._stars = []
        self._last_cond = None

        # city name scroll
        self._name_x = 0.0

    def start(self):
        super().start()
        self._t = 0.0
        self._last_mono = time.monotonic()
        self._city_idx = 0
        self._city_start = time.monotonic()
        self._name_x = 0.0
        self._last_cond = None
        self._known_city_ids = []
        self._fetch_stop.clear()
        self._fetch_thread = threading.Thread(
            target=self._fetch_loop, daemon=True, name='weather-fetch'
        )
        self._fetch_thread.start()

    def stop(self):
        super().stop()
        self._fetch_stop.set()

    # ── Background fetch ──────────────────────────────────────────────────────

    def _fetch_loop(self):
        while not self._fetch_stop.wait(0):
            cfg = self.config.get_section('weather')
            api_key = cfg.get('api_key', '').strip()
            cities = cfg.get('cities', [])
            units = cfg.get('units', 'metric')
            interval = max(60, int(cfg.get('refresh_interval', 600)))

            # Detect city list changes and flush stale index-keyed data
            current_ids = [c.get('id', c.get('name', '')) for c in cities]
            if current_ids != self._known_city_ids:
                with self._lock:
                    self._weather.clear()
                    self._forecast.clear()
                    self._last_fetch.clear()
                self._known_city_ids = current_ids

            now = time.monotonic()
            for i, city in enumerate(cities):
                if api_key and now - self._last_fetch.get(i, 0) >= interval:
                    self._fetch_city(i, city, api_key, units)

            self._fetch_stop.wait(30)

    def _fetch_city(self, idx, city, api_key, units):
        name = city.get('name', '')
        lat = city.get('lat')
        lon = city.get('lon')
        owm_id = city.get('owm_id')
        try:
            if owm_id is not None:
                base = f'id={owm_id}'
            elif lat is not None and lon is not None:
                base = f'lat={lat}&lon={lon}'
            else:
                base = f'q={_url_quote(name)}'

            cur = requests.get(
                f'https://api.openweathermap.org/data/2.5/weather?{base}&appid={api_key}&units={units}',
                timeout=10,
            ).json()

            if cur.get('cod') != 200:
                msg = str(cur.get('message', f'cod={cur.get("cod")}'))
                with self._lock:
                    self._last_api_error = msg[:28]
                return

            code = cur['weather'][0]['id']
            sunrise = cur['sys'].get('sunrise', 0)
            sunset = cur['sys'].get('sunset', 0)
            is_day = sunrise < time.time() < sunset

            w = {
                'temp': float(cur['main']['temp']),
                'humidity': int(cur['main']['humidity']),
                'code': code,
                'description': cur['weather'][0]['description'].capitalize(),
                'is_day': is_day,
                'city_name': cur.get('name', name),
            }

            with self._lock:
                self._weather[idx] = w
                self._last_fetch[idx] = time.monotonic()
                self._last_api_error = ''

            try:
                fore_raw = requests.get(
                    f'https://api.openweathermap.org/data/2.5/forecast?{base}&appid={api_key}&units={units}&cnt=12',
                    timeout=10,
                ).json()
                temps = [item['main']['temp'] for item in fore_raw.get('list', [])]
                with self._lock:
                    self._forecast[idx] = temps
            except Exception:
                pass
        except Exception as e:
            with self._lock:
                self._last_api_error = str(e)[:28]

    # ── Display data ──────────────────────────────────────────────────────────

    def _display_data(self):
        cfg = self.config.get_section('weather')
        test = cfg.get('test_condition', '')
        if test and test in TEST_PRESETS:
            w = dict(TEST_PRESETS[test])
            with self._lock:
                fore = self._forecast.get('test') or _fake_forecast(w['temp'])
            return w, fore, 'TEST'

        cities = cfg.get('cities', [])
        if not cities:
            return None, [], ''

        idx = self._city_idx % len(cities)
        with self._lock:
            w = self._weather.get(idx)
            fore = self._forecast.get(idx, [])
        city_name = (w.get('city_name') if w else None) or cities[idx].get('name', '?')
        return w, fore, city_name

    # ── Particle init ─────────────────────────────────────────────────────────

    def _init_particles(self, cond):
        rx0, rx1 = PANEL_X, W - 1
        self._rain = [
            [float(random.randint(rx0, rx1)), float(random.randint(0, GRAPH_Y - 2)),
             random.uniform(10, 20)]
            for _ in range(14)
        ]
        self._snow = [
            [float(random.randint(rx0, rx1)), float(random.randint(0, GRAPH_Y - 2)),
             random.uniform(-0.8, 0.8), random.uniform(3, 7)]
            for _ in range(10)
        ]
        self._stars = [
            (random.randint(rx0, rx1), random.randint(1, GRAPH_Y - 4),
             random.uniform(0, math.pi * 2))
            for _ in range(9)
        ]
        self._cloud_x = 0.0
        self._sun_angle = 0.0
        self._lightning_bolt = []
        self._lightning_until = 0.0
        self._lightning_next = 0.0

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, canvas):
        mono = time.monotonic()
        dt = min(mono - self._last_mono, 0.1)
        self._last_mono = mono
        self._t += dt

        cfg = self.config.get_section('weather')
        cities = cfg.get('cities', [])
        city_interval = max(5, int(cfg.get('city_interval', 30)))
        test = cfg.get('test_condition', '')

        if not test and len(cities) > 1:
            if mono - self._city_start >= city_interval:
                self._city_idx = (self._city_idx + 1) % len(cities)
                self._city_start = mono
                self._name_x = 0.0
                self._last_cond = None

        weather, forecast, city_name = self._display_data()

        img = Image.new('RGB', (W, H), (0, 0, 12))
        draw = ImageDraw.Draw(img)

        if weather is None:
            self._draw_no_data(draw, city_name)
            image_to_canvas(canvas, img)
            return

        cond = _code_to_type(weather['code'], weather.get('is_day', True))
        # Override with extreme conditions based on temperature (metric; convert if Fahrenheit)
        temp_c = weather['temp']
        if cfg.get('units', 'metric') != 'metric':
            temp_c = (temp_c - 32) * 5 / 9
        if temp_c >= 35 and cond == 'clear_day':
            cond = 'extreme_hot'
        elif temp_c < -10:
            cond = 'extreme_cold'

        if cond != self._last_cond:
            self._init_particles(cond)
            self._last_cond = cond

        self._draw_background(draw, cond)
        self._draw_animation(draw, img, cond, dt)
        self._draw_temp(draw, weather, cfg.get('units', 'metric'))
        self._draw_humidity(draw, weather['humidity'])
        if cfg.get('show_city_name', True):
            self._draw_city(draw, city_name, dt)
        if forecast:
            self._draw_graph(draw, forecast)

        image_to_canvas(canvas, img)

    # ── Background ────────────────────────────────────────────────────────────

    def _draw_background(self, draw, cond):
        BGTOP = {
            'clear_day':    (0, 18, 55),
            'clear_night':  (2, 2, 22),
            'partly_cloudy':(3, 22, 58),
            'clouds':       (20, 26, 42),
            'drizzle':      (14, 22, 38),
            'rain':         (10, 16, 32),
            'thunderstorm': (8, 8, 18),
            'snow':         (12, 18, 38),
            'fog':          (35, 38, 48),
            'extreme_hot':  (55, 12, 0),
            'extreme_cold': (0, 4, 32),
        }
        BGBOT = {
            'clear_day':    (0, 8, 28),
            'clear_night':  (0, 0, 10),
            'partly_cloudy':(0, 12, 32),
            'clouds':       (10, 14, 22),
            'drizzle':      (6, 10, 18),
            'rain':         (4, 8, 16),
            'thunderstorm': (4, 4, 10),
            'snow':         (6, 10, 22),
            'fog':          (20, 22, 30),
            'extreme_hot':  (28, 5, 0),
            'extreme_cold': (0, 2, 16),
        }
        top = BGTOP.get(cond, (0, 15, 40))
        bot = BGBOT.get(cond, (0, 5, 15))
        for y in range(H):
            t = y / (H - 1)
            r = int(top[0] + (bot[0] - top[0]) * t)
            g = int(top[1] + (bot[1] - top[1]) * t)
            b = int(top[2] + (bot[2] - top[2]) * t)
            draw.line([(0, y), (W - 1, y)], fill=(r, g, b))

    # ── Animation dispatch ────────────────────────────────────────────────────

    def _draw_animation(self, draw, img, cond, dt):
        if cond == 'clear_day':
            self._anim_sun(draw, dt)
        elif cond == 'clear_night':
            self._anim_moon(draw)
        elif cond == 'clouds':
            self._anim_clouds(draw, img, dt, n=2, gray=130)
        elif cond == 'partly_cloudy':
            self._anim_sun(draw, dt, small=True)
            self._anim_clouds(draw, img, dt, n=1, gray=140, offset_y=6)
        elif cond == 'drizzle':
            self._anim_sun(draw, dt, small=True)
            self._anim_clouds(draw, img, dt, n=1, gray=105, offset_y=4)
            self._anim_rain(draw, dt, cond)
        elif cond == 'rain':
            self._anim_clouds(draw, img, dt, n=1, gray=100, offset_y=2)
            self._anim_rain(draw, dt, cond)
        elif cond == 'thunderstorm':
            self._anim_clouds(draw, img, dt, n=2, gray=70, offset_y=0)
            self._anim_rain(draw, dt, cond)
            self._anim_lightning(draw, dt)
        elif cond == 'snow':
            self._anim_clouds(draw, img, dt, n=1, gray=110, offset_y=1)
            self._anim_snow(draw, dt)
        elif cond == 'fog':
            self._anim_fog(draw, img)
        elif cond == 'extreme_hot':
            self._anim_extreme_hot(draw, dt)
        elif cond == 'extreme_cold':
            self._anim_extreme_cold(draw, dt)

    # ── Sun ───────────────────────────────────────────────────────────────────

    def _anim_sun(self, draw, dt, small=False):
        self._sun_angle = (self._sun_angle + dt * 0.6) % (math.pi * 2)
        cx, cy = ANIM_CX, ANIM_CY - (2 if small else 0)
        r_core = 4 if small else 6

        # Core glow
        for dy in range(-r_core - 1, r_core + 2):
            for dx in range(-r_core - 1, r_core + 2):
                d2 = dx * dx + dy * dy
                if d2 <= r_core * r_core:
                    frac = d2 / (r_core * r_core)
                    intensity = 1.0 - frac * 0.4
                    px, py = cx + dx, cy + dy
                    if 0 <= px < W and 0 <= py < GRAPH_Y:
                        draw.point([px, py], fill=(
                            int(255 * intensity),
                            int(200 * intensity),
                            int(30 * intensity),
                        ))

        # Rays
        n_rays = 8
        ray_inner = r_core + 2
        ray_outer = r_core + (4 if small else 5)
        for i in range(n_rays):
            angle = self._sun_angle + i * math.pi / 4
            for rr in range(ray_inner, ray_outer + 1):
                frac = (rr - ray_inner) / max(1, ray_outer - ray_inner)
                intensity = 1.0 - frac * 0.7
                px = cx + int(round(rr * math.cos(angle)))
                py = cy + int(round(rr * math.sin(angle)))
                if PANEL_X <= px < W and 0 <= py < GRAPH_Y:
                    draw.point([px, py], fill=(
                        int(255 * intensity),
                        int(160 * intensity),
                        0,
                    ))

    # ── Moon + stars ──────────────────────────────────────────────────────────

    def _anim_moon(self, draw):
        cx, cy = ANIM_CX, ANIM_CY
        r = 7
        # Moon body
        for dy in range(-r, r + 1):
            for dx in range(-r, r + 1):
                if dx * dx + dy * dy <= r * r:
                    ox, oy = dx - 3, dy + 2
                    if ox * ox + oy * oy > (r - 2) * (r - 2):
                        px, py = cx + dx, cy + dy
                        if PANEL_X <= px < W and 0 <= py < GRAPH_Y:
                            bri = int(170 + 30 * (1 - (dx * dx + dy * dy) / (r * r)))
                            draw.point([px, py], fill=(bri, bri, int(bri * 0.85)))
        # Stars
        for sx, sy, phase in self._stars:
            bri = int(80 + 100 * (0.5 + 0.5 * math.sin(self._t * 2.5 + phase)))
            px, py = int(sx), int(sy)
            if PANEL_X <= px < W and 0 <= py < GRAPH_Y:
                if (px - cx) ** 2 + (py - cy) ** 2 > (r + 2) ** 2:
                    draw.point([px, py], fill=(bri, bri, bri))

    # ── Clouds ────────────────────────────────────────────────────────────────

    def _cloud_shape(self, draw, img, cx, cy, gray):
        blobs = [(0, 0, 6), (-5, 2, 4), (5, 2, 4), (0, 4, 5)]
        for bx, by, br in blobs:
            for dy in range(-br, br + 1):
                for dx in range(-br, br + 1):
                    if dx * dx + dy * dy <= br * br:
                        px, py = cx + bx + dx, cy + by + dy
                        if PANEL_X <= px < W and 0 <= py < GRAPH_Y:
                            existing = img.getpixel((px, py))
                            blended = tuple(min(255, int(e + (gray - e) * 0.85)) for e in existing)
                            draw.point([px, py], fill=blended)

    def _anim_clouds(self, draw, img, dt, n=2, gray=130, offset_y=0):
        self._cloud_x = (self._cloud_x + dt * 2.5) % 20
        offsets = [(0, 0), (12, -3)] if n >= 2 else [(0, 0)]
        for i, (ox, oy) in enumerate(offsets):
            drift = (self._cloud_x + i * 10) % 20 - 10
            cx = ANIM_CX + ox + int(drift)
            cy = ANIM_CY - 4 + oy + offset_y
            self._cloud_shape(draw, img, cx, cy, gray)

    # ── Rain ─────────────────────────────────────────────────────────────────

    def _anim_rain(self, draw, dt, cond):
        heavy = cond in ('rain', 'thunderstorm')
        color = (55, 85, 170) if heavy else (45, 70, 140)
        bright = (90, 130, 220) if heavy else (70, 110, 190)
        for drop in self._rain:
            drop[1] += drop[2] * dt
            if drop[1] >= GRAPH_Y - 1:
                drop[1] = 0.0
                drop[0] = float(random.randint(PANEL_X, W - 1))
            x, y = int(drop[0]), int(drop[1])
            if PANEL_X <= x < W and 0 <= y < GRAPH_Y:
                draw.point([x, y], fill=bright)
            if PANEL_X <= x < W and 0 <= y + 1 < GRAPH_Y:
                draw.point([x, y + 1], fill=color)

    # ── Lightning ────────────────────────────────────────────────────────────

    def _anim_lightning(self, draw, dt):
        now = self._t

        # Generate a new bolt when the wait period expires and none is active
        if not self._lightning_bolt and now >= self._lightning_next:
            x = random.randint(PANEL_X + 4, W - 5)
            y = 4
            segs = []
            for _ in range(5):
                nx = max(PANEL_X, min(W - 1, x + random.randint(-2, 2)))
                ny = min(GRAPH_Y - 1, y + 3)
                segs.append((x, y, nx, ny))
                x, y = nx, ny
            self._lightning_bolt = segs
            self._lightning_until = now + 0.13
            self._lightning_next = now + 0.13 + random.uniform(1.8, 4.5)

        # Draw stored bolt while flash is active
        if self._lightning_bolt:
            if now < self._lightning_until:
                x0, y0 = self._lightning_bolt[0][0], self._lightning_bolt[0][1]
                draw.point([x0, y0], fill=(255, 255, 220))
                for x1, y1, x2, y2 in self._lightning_bolt:
                    draw.line([(x1, y1), (x2, y2)], fill=(230, 230, 120))
            else:
                self._lightning_bolt = []

    # ── Snow ─────────────────────────────────────────────────────────────────

    def _anim_snow(self, draw, dt):
        for flake in self._snow:
            flake[0] += flake[2] * dt
            flake[1] += flake[3] * dt
            if flake[1] >= GRAPH_Y - 1:
                flake[1] = 0.0
                flake[0] = float(random.randint(PANEL_X, W - 1))
            if flake[0] < PANEL_X or flake[0] >= W:
                flake[0] = float(random.randint(PANEL_X, W - 1))
            x, y = int(flake[0]), int(flake[1])
            pulse = int(160 + 60 * math.sin(self._t * 3 + flake[2] * 10))
            if PANEL_X <= x < W and 0 <= y < GRAPH_Y:
                draw.point([x, y], fill=(pulse, pulse, 255))

    # ── Fog ──────────────────────────────────────────────────────────────────

    def _anim_fog(self, draw, img):
        fog_rgb = (175, 180, 200)
        for row in range(1, GRAPH_Y - 1):
            # Two sine waves at different frequencies → layered wisps
            w1 = math.sin(self._t * 0.35 + row * 0.32)
            w2 = math.sin(self._t * 0.65 + row * 0.17)
            density = 0.42 + 0.32 * ((w1 + w2) * 0.5)
            for col in range(PANEL_X, W):
                existing = img.getpixel((col, row))
                blended = tuple(int(e + (f - e) * density) for e, f in zip(existing, fog_rgb))
                draw.point([col, row], fill=blended)

    # ── Extreme hot ───────────────────────────────────────────────────────────

    def _anim_extreme_hot(self, draw, dt):
        self._sun_angle = (self._sun_angle + dt * 1.4) % (math.pi * 2)
        cx, cy = ANIM_CX, ANIM_CY - 1
        r_core = 7
        pulse = 0.85 + 0.15 * math.sin(self._t * 3.5)

        # Blazing core
        for dy in range(-r_core - 1, r_core + 2):
            for dx in range(-r_core - 1, r_core + 2):
                d2 = dx * dx + dy * dy
                if d2 <= r_core * r_core:
                    frac = d2 / (r_core * r_core)
                    intensity = (1.0 - frac * 0.25) * pulse
                    px, py = cx + dx, cy + dy
                    if PANEL_X <= px < W and 0 <= py < GRAPH_Y:
                        draw.point([px, py], fill=(255, int(65 * intensity), 0))

        # Many long pulsing rays
        n_rays = 12
        for i in range(n_rays):
            angle = self._sun_angle + i * math.pi / 6
            ray_len = 6 + int(2 * math.sin(self._t * 5.0 + i * 1.3))
            for rr in range(r_core + 2, r_core + 2 + ray_len):
                frac = (rr - r_core - 2) / max(1, ray_len - 1)
                intensity = (1.0 - frac * 0.9) * pulse
                px = cx + int(round(rr * math.cos(angle)))
                py = cy + int(round(rr * math.sin(angle)))
                if PANEL_X <= px < W and 0 <= py < GRAPH_Y:
                    draw.point([px, py], fill=(255, int(45 * intensity), 0))

        # Heat shimmer dots near bottom of animation area
        for _ in range(4):
            hx = random.randint(PANEL_X, W - 1)
            hy = random.randint(GRAPH_Y - 7, GRAPH_Y - 2)
            v = random.randint(60, 140)
            draw.point([hx, hy], fill=(v, v // 5, 0))

    # ── Extreme cold ──────────────────────────────────────────────────────────

    def _anim_extreme_cold(self, draw, dt):
        # Pale ice-blue sun low in the sky
        cx, cy = ANIM_CX, ANIM_CY + 3
        r_core = 5
        pulse = 0.65 + 0.20 * math.sin(self._t * 0.9)
        for dy in range(-r_core - 1, r_core + 2):
            for dx in range(-r_core - 1, r_core + 2):
                d2 = dx * dx + dy * dy
                if d2 <= r_core * r_core:
                    frac = d2 / (r_core * r_core)
                    intensity = (1.0 - frac * 0.55) * pulse
                    px, py = cx + dx, cy + dy
                    if PANEL_X <= px < W and 0 <= py < GRAPH_Y:
                        draw.point([px, py], fill=(
                            int(160 * intensity),
                            int(205 * intensity),
                            int(255 * intensity),
                        ))

        # Sparse ice crystal particles (reuses self._snow list)
        for flake in self._snow:
            flake[1] += flake[3] * dt * 0.4
            flake[0] += math.sin(self._t * 1.8 + flake[2]) * 0.25
            if flake[1] >= GRAPH_Y - 1:
                flake[1] = 0.0
                flake[0] = float(random.randint(PANEL_X, W - 1))
            if flake[0] < PANEL_X or flake[0] >= W:
                flake[0] = float(random.randint(PANEL_X, W - 1))
            x, y = int(flake[0]), int(flake[1])
            bri = int(130 + 90 * math.sin(self._t * 4.5 + flake[2] * 6))
            if PANEL_X <= x < W and 0 <= y < GRAPH_Y:
                draw.point([x, y], fill=(bri, bri, 255))
                # Small cross arms for crystal look
                for adx, ady in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ax, ay = x + adx, y + ady
                    if PANEL_X <= ax < W and 0 <= ay < GRAPH_Y:
                        draw.point([ax, ay], fill=(bri // 2, bri // 2, 200))

    # ── Temperature ──────────────────────────────────────────────────────────

    def _draw_temp(self, draw, weather, units):
        temp = weather['temp']
        temp_int = int(round(temp))
        col = _temp_color(temp)
        dw, dh, t = 8, 14, 2

        digits = str(abs(temp_int))
        x = 1
        y = 4

        if temp_int < 0:
            draw.rectangle([x, y + dh // 2 - 1, x + 3, y + dh // 2 + t - 2], fill=(180, 180, 220))
            x += 5

        for ch in digits:
            draw_digit(draw, x, y, ch, col, dw, dh, t)
            x += dw + 1

        # Degree symbol (tiny)
        draw.ellipse([x, y, x + 1, y + 1], outline=(200, 200, 200))
        # Unit label (C or F)
        unit = 'C' if units == 'metric' else 'F'
        draw.text([x + 3, y - 1], unit, font=_FONT, fill=(160, 160, 180))

    # ── Humidity ─────────────────────────────────────────────────────────────

    def _draw_humidity(self, draw, humidity):
        y = 21
        bar_w = int(round(humidity / 100 * 20))
        # Track
        draw.rectangle([1, y, 21, y + 1], fill=(20, 30, 50))
        # Fill
        hue_r = int(40 + humidity * 0.4)
        hue_b = int(120 + humidity * 1.35)
        draw.rectangle([1, y, max(1, bar_w), y + 1], fill=(hue_r, 80, min(255, hue_b)))
        # Label
        draw.text([1, y + 3], f'{humidity}%', font=_FONT, fill=(90, 130, 190))

    # ── City name ────────────────────────────────────────────────────────────

    def _draw_city(self, draw, city_name, dt):
        name = (city_name or '').upper()[:12]
        # Tiny font is 8px per char but approx 6px visible width
        char_w = 6
        total_w = len(name) * char_w
        x = 1
        if total_w > PANEL_X - 2:
            # scroll
            self._name_x = (self._name_x + dt * 18) % (total_w + 8)
            x = int(1 - self._name_x)
        draw.text([x, 0], name, font=_FONT, fill=(160, 180, 210))

    # ── Hourly graph ─────────────────────────────────────────────────────────

    def _draw_graph(self, draw, forecast):
        temps = forecast[:12]
        if len(temps) < 2:
            return

        mn = min(temps)
        mx = max(temps)
        span = max(1.0, mx - mn)

        gx0, gx1 = 0, W - 1
        gy0, gy1 = GRAPH_Y + 1, H - 2  # inner bounds
        gw = gx1 - gx0
        gh = gy1 - gy0

        # Background bar
        draw.rectangle([gx0, GRAPH_Y, gx1, H - 1], fill=(8, 10, 18))

        n = len(temps)
        pts = []
        for i, t in enumerate(temps):
            norm = 1.0 - (t - mn) / span
            px = gx0 + int(i * gw / (n - 1))
            py = gy0 + int(norm * gh)
            pts.append((px, py, t))

        # Lines
        for i in range(len(pts) - 1):
            ax, ay, _ = pts[i]
            bx, by, _ = pts[i + 1]
            draw.line([(ax, ay), (bx, by)], fill=(50, 80, 130))

        # Dots
        for px, py, t in pts:
            col = _temp_color(t)
            draw.point([px, py], fill=col)

    # ── No data ───────────────────────────────────────────────────────────────

    def _draw_no_data(self, draw, city_name):
        pulse = int(120 + 60 * math.sin(self._t * 1.5))
        draw.text([2, 2], 'Weather', font=_FONT, fill=(pulse, pulse, pulse))
        with self._lock:
            err = self._last_api_error
        if err:
            draw.text([2, 11], 'API err:', font=_FONT, fill=(200, 60, 60))
            # Show up to two lines of error text (6 chars each)
            draw.text([2, 19], err[:12], font=_FONT, fill=(170, 70, 70))
        else:
            draw.text([2, 12], city_name[:8] if city_name else 'No city', font=_FONT, fill=(80, 100, 140))
            draw.text([2, 22], 'Fetching...', font=_FONT, fill=(60, 80, 100))
