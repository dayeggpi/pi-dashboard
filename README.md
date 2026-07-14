# LED Matrix Controller

Fits a HUB75 64x32 3mm pitch. It is important to print the Screen on the lowest layer height possible (max 0.2 mm)

A full-featured controller for a **64×32 RGB LED matrix** driven by a Raspberry Pi with the Adafruit RGB Matrix Bonnet. Modes: digital clock, Spotify now-playing, Conway's Game of Life, scrolling text, Patternflow, pixel draw, Pomodoro timer, reminders, image/GIF display, image library, and live weather. Controlled via REST API and a built-in web interface.

---

## Requirements

- Raspberry PI (4B preferred, zero 2W ok with some lags)
- 5V power supply
- Adafruit RGB Matrix Bonnet for Raspberry Pi ([www.adafruit.com/product/3211](https://www.adafruit.com/product/3211))
- Hourglass app (with Endpoint feature : see [github.com/dayeggpi/hourglass2](https://github.com/dayeggpi/hourglass2))
- 3D printed enclosure (see attached files for Pi 4B support, print in lowest layer height possible max 0.2mm) (Original 3D print enclosure : https://www.printables.com/model/850534-rgb-led-clock-case-64x32-matrix, adjusted 3D files for RPi 4B in this repo)

---


## Current Features

- Modes: clock, Spotify, Game of Life, text, Patternflow (Original project : https://github.com/engmung/PatternFlow), draw, Pomodoro, background reminders, image/GIF display, image library, and live weather.
- Built-in web UI for mode switching, brightness, mode settings, carousel, reminders, image upload/crop, image library, and service controls.
- REST API for mode/config updates, Spotify OAuth, Patternflow controls, Pomodoro timer events, draw updates, image upload/delete, library management, and system actions.
- Settings export and import as a single JSON file.
- Reminder color palettes: named palettes with instant load into any reminder.
- Matrix runtime tuning through config for GPIO slowdown, PWM bits, refresh-rate limiting, and hardware pulsing.

---

## Hardware

| Part | Notes |
|---|---|
| 64×32 RGB LED Matrix (HUB75) | P2.5 or P3 pitch both work |
| Adafruit RGB Matrix Bonnet | [PID 3211](https://www.adafruit.com/product/3211) |
| Raspberry Pi Zero 2W | See Pi Zero 1.3 note below |
| 5V power supply, **≥4A** | 10A recommended for full brightness |
| Momentary pushbutton | For hardware shutdown (optional) |

---

## Wiring

### LED Matrix → Bonnet

The bonnet ships with a 16-pin ribbon cable. Connect it from the **IDC output header on the bonnet** to the **P3 (HUB75) data input** on the LED panel. The connectors are keyed — insert with the notch facing the correct direction.

```
Bonnet IDC output  ──────ribbon──────  LED Panel HUB75 IN
```

If your panel has two connectors (IN and OUT), always use IN.

### Power Supply → Bonnet

The bonnet has screw terminals labeled **5V** and **GND**:

```
Power Supply (+5V)  →  Bonnet "5V" terminal
Power Supply (GND)  →  Bonnet "GND" terminal
```

**Do NOT power the LED matrix from the Pi's USB port** — it cannot supply enough current. The bonnet passes 5V to the panel via its own power path.

#### Power the Pi from the same supply (optional but tidy)

There is a solder jumper on the bonnet labeled **"Power Pi"**. If you bridge it, the Pi draws power from the screw terminals (no separate USB cable needed). Otherwise power the Pi via its micro-USB port as normal.

### Shutdown Button (GPIO21)

```
Button pin 1  →  GPIO21 (BCM) = physical pin 40
Button pin 2  →  GND          = physical pin 39
```

Hold the button for **3 seconds** to trigger a safe shutdown.  
The GPIO is configured with an internal pull-up so no resistor is needed.

### Complete GPIO Map (Pi → Bonnet, automatic via header)

The bonnet plugs directly onto all 40 GPIO pins. No manual wiring is needed for the matrix signals — the bonnet handles R1, G1, B1, R2, G2, B2, A, B, C, D, E, CLK, LAT, OE automatically.

---

## Software Architecture

```
main.py            ← render loop + controller
├── config.py      ← JSON config store
├── api.py         ← Flask REST API + web UI
└── modes/
    ├── base.py       ← BaseMode ABC
    ├── clock.py      ← 7-segment digital clock
    ├── spotify.py    ← Now-playing with rotating art
    ├── gameoflife.py ← Conway's Game of Life
    ├── text.py       ← Horizontal/vertical scrolling or static text
    ├── draw.py       ← Pixel canvas with optional scroll
    ├── pomodoro.py   ← Gradient progress timer
    ├── reminder.py   ← Background-triggered text takeover
    ├── image.py      ← Static image and animated GIF display
    ├── library.py    ← Persistent image library with rotation
    ├── weather.py    ← Live weather with animated conditions and forecast graph
    └── patternflow/  ← Generative pattern engine
```

The main loop runs at the matrix's VSync rate (~100 Hz). Each mode's `render(canvas)` is called every frame. Mode-specific state (scroll position, rotation angle, GoL grid, animation frame) is maintained per-mode instance. The Flask API runs in a daemon thread.

Reminder scheduling is handled by the controller in the background: when a reminder matches the local `HH:MM`, the controller temporarily switches to the internal `reminder` mode, displays it for the configured duration, then returns to the previous mode.

`ImageMode` stores the uploaded media at `static/matrix_image.png` (static) or `static/matrix_image.gif` (animated). The GIF path takes priority when both exist. All frames are pre-loaded and resized to 64×32 on first read; frame advancement is driven by `time.time()` against each frame's original duration.

`LibraryMode` stores its files in `static/library/<id>.<ext>`. PNGs may be wider than 64 px (saved from scrolling draw canvases); the mode handles wrap-around scrolling identically to `DrawMode`. GIFs are always 64×32 and animate normally. The item list and rotation settings are re-read from config every second so changes made through the API or UI take effect without a mode restart.

---

## Recent Changes

### 2026-07-14 (latest)

- Added **vertical scroll** to Text mode:
  - New `scroll_direction` config key: `"off"` (static, centered), `"horizontal"` (original ticker), or `"vertical"` (teleprompter — text enters from bottom, scrolls up).
  - Vertical mode wraps text to fit the 64 px width; words too long to fit are split with a hyphen.
  - Same `speed` (px/s) applies to both scroll axes.
  - Scroll direction resets the animation when the text content or direction changes.
  - Web UI: the scroll checkbox is replaced by a three-option select — **Off (static)**, **Horizontal**, **Vertical (teleprompter)**.
  - Backward-compatible: configs with the old `"scroll": true/false` boolean continue to work (mapped to `horizontal`/`off`).

### 2026-07-13

- Added **Weather** mode (`modes/weather.py`):
  - Fetches current conditions and 3-hourly forecast (12 points = 36 h) from the OpenWeatherMap API.
  - Left panel: city name (scrolls if long), temperature in large digits with temp-mapped color (blue → cyan → green → yellow → red), humidity bar (width proportional to humidity, blue-tinted).
  - Right panel: animated weather condition — sun with rotating rays, moon with twinkling stars, drifting clouds, rain drops, snow flakes, lightning bolts, fog wisps, extreme-heat blaze, extreme-cold ice crystals.
  - Bottom strip (rows 24–31): 3-hourly forecast graph — line + dots, each dot colored by temperature.
  - Condition icons: `clear_day`, `clear_night`, `partly_cloudy`, `clouds`, `drizzle`, `rain`, `thunderstorm`, `snow`, `fog`, `extreme_hot`, `extreme_cold`.
  - `extreme_hot` triggers only when temp ≥ 35 °C **and** the sky is clear/sunny; overcast hot days keep their cloud icon.
  - `extreme_cold` triggers when temp < −10 °C regardless of sky condition.
  - Multi-city carousel: rotates through configured cities at a configurable interval; each city fetched independently.
  - Background fetch thread polls every `refresh_interval` seconds (default 600); detects city-list changes and flushes stale data automatically.
  - City lookup supports OWM city ID (`owm_id`), lat/lon, or name string.
  - Built-in test presets (`test_condition` config key) for offline development.
  - Config section: `weather` (see Configuration below).

- **Fixed** `extreme_hot` override: previously fired whenever temp ≥ 35 °C regardless of cloud cover. Now requires clear/sunny conditions — 36 °C under broken clouds renders as `clouds`, not `extreme_hot`.

### 2026-07-10

- Added **Library** mode (`modes/library.py`):
  - Save any uploaded image/GIF or pixel drawing to a persistent library stored in `static/library/`.
  - Library mode cycles through saved items; each item has a configurable display duration.
  - Wide PNGs from scrolling draw canvases are stored at their original width and scroll wrap-around, identical to Draw mode.
  - Animated GIFs animate normally.
  - "Save to Library" button (with optional name field) added to both the Image panel and Draw panel in the web UI.
  - Library tab in the web UI: rename items, set per-item duration, remove items, toggle auto-rotation, set default interval, and activate library mode directly.
  - Config is re-read live so additions/removals take effect without restarting the mode.
  - REST API: `GET /api/library`, `POST /api/library/add/image`, `POST /api/library/add/draw`, `DELETE /api/library/<id>`, `POST /api/library/config`.

- Added **Settings export / import**:
  - `GET /api/config/export` — downloads the full `config.json` as an attachment (`led-matrix-config.json`).
  - `POST /api/config/import` — accepts a previously exported JSON and deep-merges it into the live config, triggering Spotify reinit and brightness refresh as needed.
  - Export and Import buttons in the System section of the web UI.

- Added **Reminder color palettes**:
  - Named palettes stored under `reminders.palettes` in config; each palette holds a text color and two gradient colors.
  - Four built-in palettes shipped as defaults: Classic, Ocean, Sunset, Forest.
  - Color Palettes card at the top of the Reminders tab: create palettes (name + 3 color pickers), edit and save existing palettes, delete palettes.
  - Each reminder row now has a palette selector dropdown — choosing a palette instantly fills that reminder's three color pickers; the selector resets afterward (colors are owned by the reminder, not the palette).
  - Clear button in each reminder row resets colors to the Classic defaults.
  - REST API: `POST /api/reminders/palettes` (create or update), `DELETE /api/reminders/palettes/<id>`.

### 2026-07-09

- Added **Image / GIF** mode:
  - Upload any static image (JPEG, PNG, WebP, …) or animated GIF via the web UI.
  - Browser-side crop/zoom UI: drag to pan, slider to zoom (100–500 %), live preview at the 2:1 matrix ratio.
  - Animated GIFs are previewed live in the crop canvas (real animation shown). Each frame is cropped and resized to 64×32 server-side; original frame durations are preserved.
  - Current image shown as a pixelated preview in the web UI; remove button with confirmation deletes the file from the Pi and returns to clock mode.
  - REST API: `GET /api/image`, `DELETE /api/image`, `POST /api/image/upload`.
  - Uploaded media stored at `static/matrix_image.png` (static) or `static/matrix_image.gif` (animated GIF); GIF takes priority when both exist.
  - `ImageMode` pre-loads all frames on first render, polls for file changes every second, and advances frames via wall-clock timing.

### 2026-07-06

- Added **Reminder** support:
  - Background scheduler with a master enable toggle.
  - Add/edit/delete reminders from the web UI.
  - Each reminder has an hour/minute time, text, text color, gradient background, display duration, and per-reminder enable toggle.
  - Reminder display uses the same glyph-style text as Spotify/Text status messages.
  - Reminder mode is hidden from normal mode and carousel controls because it is a temporary background-triggered takeover mode.
- Added **Pomodoro** mode:
  - Gradient progress bar fills progressively across the configured timer duration.
  - Configurable background, elapsed background, text color, gradient colors, end flash, tick pixel, and return-after-elapsed behavior.
  - Fixed a timing bug where Pomodoro progress could loop/collapse every second by double-subtracting elapsed time.
- Added **Draw** mode with browser pixel canvas, pen/eraser, width controls, optional scrolling, and text placement.
- Added **Carousel** controls for selecting modes and per-mode durations.
- Expanded **Patternflow** web controls with pattern picker, web knob/button controls, FPS overlay option, Donut fast render, and fast image push.
- Expanded **Spotify** display settings with artist/track scroll speeds and configurable OAuth callback path.
- Added service controls in the web UI/API: restart service, stop service, disable autostart, and shutdown.
- Added matrix runtime options in config: `gpio_slowdown`, `pwm_bits`, `limit_refresh_rate_hz`, and `disable_hardware_pulsing`.
- Added regression tests for Pomodoro timing and reminder return behavior.

---

## Installation

### 1. Flash Raspberry Pi OS Lite (64-bit for Zero 2W, 32-bit for Zero 1.3)

Use Raspberry Pi Imager. Enable SSH and configure Wi-Fi in the imager before flashing.

### 2. SSH in and clone the project

```bash
ssh pi@<your-pi-ip>
git clone https://github.com/yourname/led-matrix.git
cd led-matrix
```

Or copy files with `scp`:

```bash
scp -r led-matrix/ pi@<pi-ip>:/home/pi/
ssh pi@<pi-ip>
cd led-matrix
```

### 3. Run the installer

```bash
sudo bash install.sh
```

The installer:
- Installs system dependencies
- Clones and builds [hzeller/rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix)
- Creates a Python virtualenv at `/opt/led-matrix/venv`
- Installs Python packages (Flask, Pillow, spotipy, …)
- **Disables audio** in `/boot/config.txt` (required — the matrix PWM conflicts with the Pi's audio hardware)
- Installs and enables the `led-matrix` systemd service
- Waits for Wi-Fi/networking before launching `main.py`

### 4. Reboot

```bash
sudo reboot
```

After reboot the service starts automatically. Open `http://<pi-ip>:8080` in your browser.

---

## Configuration

Config is stored at `/opt/led-matrix/config.json` and updated live through the API/web UI.

```json
{
  "mode": "clock",
  "brightness": 50,
  "shutdown_gpio": 21,
  "matrix": {
    "gpio_slowdown": 2,
    "pwm_bits": 7,
    "limit_refresh_rate_hz": 0,
    "disable_hardware_pulsing": false
  },
  "carousel": {
    "enabled": false,
    "modes": ["clock", "spotify", "gameoflife", "text", "patternflow", "draw", "pomodoro", "library", "weather"],
    "durations": {
      "clock": 30,
      "spotify": 30,
      "gameoflife": 30,
      "text": 30,
      "patternflow": 30,
      "draw": 30,
      "pomodoro": 30,
      "library": 30,
      "weather": 30
    }
  },
  "clock": {
    "color": [255, 0, 0],
    "show_seconds": true
  },
  "text": {
    "content": "Hello!",
    "source": "manual",
    "url": "",
    "poll_interval": 60,
    "color": [255, 255, 255],
    "speed": 30,
    "scroll_direction": "horizontal"
  },
  "gameoflife": {
    "speed": 10,
    "color": [0, 255, 0],
    "wrap": true
  },
  "spotify": {
    "client_id": "your_id",
    "client_secret": "your_secret",
    "redirect_uri": "http://YOUR_PI_IP:8080/callback",
    "callback_path": "/callback",
    "artist_speed": 12,
    "track_speed": 12
  },
  "patternflow": {
    "current_pattern": 0,
    "encoders_enabled": false,
    "invert_encoder": false,
    "show_fps": false,
    "donut_fast_render": true,
    "fast_image_push": true,
    "encoders": [
      {"clk": -1, "dt": -1, "sw": -1},
      {"clk": -1, "dt": -1, "sw": -1},
      {"clk": -1, "dt": -1, "sw": -1},
      {"clk": -1, "dt": -1, "sw": -1}
    ]
  },
  "draw": {
    "width": 64,
    "scroll": false,
    "scroll_speed": 20,
    "pixels": []
  },
  "pomodoro": {
    "gradient_start": [30, 215, 96],
    "gradient_end": [255, 210, 64],
    "background_color": [0, 0, 0],
    "elapsed_background": [25, 25, 25],
    "text_color": [255, 255, 255],
    "flash_red": true,
    "flash_threshold_ms": 5000,
    "tick_pixel_enabled": true,
    "tick_pixel_color": [255, 255, 255],
    "return_after_elapsed_enabled": false,
    "return_after_elapsed_delay_s": 10,
    "return_after_elapsed_mode": "clock"
  },
  "reminders": {
    "enabled": false,
    "palettes": [
      {"id": "pal-classic", "name": "Classic", "text_color": [255, 255, 255], "gradient_start": [20, 30, 80],   "gradient_end": [180, 40, 80]},
      {"id": "pal-ocean",   "name": "Ocean",   "text_color": [220, 240, 255], "gradient_start": [10, 40, 100],  "gradient_end": [0, 80, 160]},
      {"id": "pal-sunset",  "name": "Sunset",  "text_color": [255, 230, 180], "gradient_start": [160, 50, 0],   "gradient_end": [120, 0, 40]},
      {"id": "pal-forest",  "name": "Forest",  "text_color": [200, 255, 200], "gradient_start": [10, 60, 20],   "gradient_end": [0, 100, 40]}
    ],
    "items": [
      {
        "id": "standup",
        "enabled": true,
        "time": "09:00",
        "text": "STAND UP",
        "text_color": [255, 255, 255],
        "gradient_start": [20, 30, 80],
        "gradient_end": [180, 40, 80],
        "display_time_s": 10
      }
    ]
  },
  "weather": {
    "api_key": "your_openweathermap_api_key",
    "units": "metric",
    "refresh_interval": 600,
    "city_interval": 30,
    "show_city_name": true,
    "test_condition": "",
    "cities": [
      { "name": "Paris", "owm_id": 2988507 },
      { "name": "Tokyo", "lat": 35.6895, "lon": 139.6917 }
    ]
  },
  "library": {
    "rotation_enabled": true,
    "interval": 10,
    "items": [
      {
        "id": "a1b2c3d4e5f6a7b8",
        "name": "My Drawing",
        "filename": "a1b2c3d4e5f6a7b8.png",
        "width": 64,
        "scroll": false,
        "scroll_speed": 20,
        "duration": 10,
        "source": "draw"
      }
    ]
  }
}
```

`patternflow` physical encoders are disabled by default. Enable them only after
choosing GPIO pins that do not overlap the RGB matrix HAT/Bonnet signals;
overlapping pins can make the display render as a few horizontal bands until
the service is restarted.

## Web Interface

Open `http://<pi-ip>:8080` in any browser.

Current UI sections:

- **Mode** — switch foreground modes instantly.
- **Brightness** — 1–100% slider.
- **Night Mode** — auto-dim between configurable hours at a lower brightness.
- **Clock** — color picker and seconds toggle.
- **Text** — manual or URL content, color, scroll speed, and scroll mode selector (Off / Horizontal / Vertical teleprompter).
- **Game of Life** — color, speed, and edge wrap.
- **Spotify** — credentials, authorize button, callback path, and artist/track scroll speeds.
- **Draw** — pixel canvas, pen/eraser, width controls, optional scrolling, text placement, and "Save to Library" button.
- **Pomodoro** — gradient, background, text, tick pixel, flash, and return-after-elapsed settings.
- **Patternflow** — pattern selector, web knob/button controls, FPS overlay, Donut fast render, and fast image push.
- **Image** — upload a static image or animated GIF, crop/zoom in the browser, see a live pixelated preview; remove button clears and returns to clock; "Save to Library" button saves the current image.
- **Library** — displays current library status; "Manage Library" button jumps to the Library tab.
- **Carousel tab** — enable carousel rotation and set per-mode durations.
- **Reminders tab** — Color Palettes card (create/edit/delete named palettes; load into any reminder via dropdown; clear colors); Reminders card (enable, add/edit/delete timed reminder takeovers).
- **Library tab** — manage saved items (rename, set duration, remove), toggle auto-rotation, set default display interval, activate library mode directly.
- **System** — export all settings as JSON, import a previously exported JSON, restart service, stop service, disable autostart, and shutdown Pi.

## REST API

Base URL: `http://<pi-ip>:8080`

### GET /api/status
Returns current mode, brightness, full config.

### GET|POST /api/mode
```json
// POST body
{ "mode": "clock" }
// modes: "clock", "spotify", "gameoflife", "text", "patternflow", "draw", "pomodoro", "image", "library", "weather"
```

`reminder` is an internal temporary display mode. It is triggered by the reminders scheduler and should not normally be selected manually.

### POST /api/brightness
```json
{ "value": 75 }
```

### GET|POST /api/text
```json
// POST — switches to text mode and displays
{
  "content": "Hello World",
  "source": "manual",
  "url": "",
  "poll_interval": 60,
  "color": [255, 128, 0],
  "speed": 40,
  "scroll_direction": "horizontal"
}
```
`speed`: pixels per second (applies to both scroll axes).  
`scroll_direction`: `"off"` (static, centered), `"horizontal"` (ticker), or `"vertical"` (teleprompter — wraps to fit width, hyphenates long words).  
Legacy `"scroll": true/false` is still accepted and maps to `"horizontal"`/`"off"`.

### GET|POST /api/config/{section}
`section` = `clock` | `text` | `gameoflife` | `spotify` | `patternflow` | `matrix` | `carousel` | `draw` | `pomodoro` | `reminders` | `night_mode`

GET returns current section config.  
POST merges the body into that section's config.

```bash
# Example: change clock color to blue
curl -X POST http://pi-ip:8080/api/config/clock \
  -H 'Content-Type: application/json' \
  -d '{"color": [0, 0, 255]}'
```

### GET /api/spotify/auth_url
Returns the Spotify OAuth URL to open in a browser.

### GET|POST /api/draw
GET returns the draw config. POST saves a drawing and switches to draw mode.

```json
{
  "width": 64,
  "scroll": false,
  "scroll_speed": 20,
  "pixels": [
    { "x": 0, "y": 0, "color": [255, 255, 255] }
  ]
}
```

### GET|POST /api/pomodoro
GET returns Pomodoro display config. POST accepts timer events from an external timer source and switches to Pomodoro while the timer is active.

```json
{
  "event": "start",
  "state": "running",
  "timeLeftMs": 1500000,
  "totalTimeMs": 1500000
}
```

Supported stop-like events/states include `stop`, `stopped`, `cancel`, `cancelled`, `reset`, `end`, and `idle`. Pause-like events/states include `pause` and `paused`.

### Reminder config
Reminders are managed through `GET|POST /api/config/reminders`. The body can include `enabled`, `items`, and `palettes`.

```json
{
  "enabled": true,
  "palettes": [
    {
      "id": "pal-ocean",
      "name": "Ocean",
      "text_color": [220, 240, 255],
      "gradient_start": [10, 40, 100],
      "gradient_end": [0, 80, 160]
    }
  ],
  "items": [
    {
      "id": "water",
      "enabled": true,
      "time": "14:30",
      "text": "DRINK WATER",
      "text_color": [255, 255, 255],
      "gradient_start": [20, 30, 80],
      "gradient_end": [180, 40, 80],
      "display_time_s": 10
    }
  ]
}
```

Reminder times use the Raspberry Pi's local time in `HH:MM` 24-hour format. Each enabled reminder fires once per local calendar day for its configured time.

### POST /api/reminders/palettes
Create a new palette (no `id` field) or update an existing one (provide `id`). Returns the full updated reminders config.

```json
{ "name": "Ocean", "text_color": [220, 240, 255], "gradient_start": [10, 40, 100], "gradient_end": [0, 80, 160] }
```

### DELETE /api/reminders/palettes/{id}
Removes the palette with the given ID. Returns the full updated reminders config.

### Library API

```text
GET  /api/library                  — list items and settings
POST /api/library/add/image        — copy current matrix image into library
POST /api/library/add/draw         — render current draw pixels into library
DELETE /api/library/{id}           — remove item (deletes file + config entry)
POST /api/library/config           — update rotation_enabled, interval, item name/duration
```

**POST /api/library/add/image** and **POST /api/library/add/draw** both accept an optional `name` field in the JSON body. `/add/draw` reads the current draw config (pixels, width, scroll, scroll_speed) at the time of the call and renders it to a PNG.

**POST /api/library/config** body:
```json
{
  "rotation_enabled": true,
  "interval": 10,
  "items": [
    { "id": "a1b2c3d4e5f6a7b8", "name": "My Drawing", "duration": 15 }
  ]
}
```
Only `name` and `duration` are merged from the `items` array; file metadata is preserved.

### Settings export / import

**GET /api/config/export** — returns the full config as a downloadable JSON file (`Content-Disposition: attachment; filename="led-matrix-config.json"`).

**POST /api/config/import** — accepts a JSON object (previously exported config) and deep-merges it into the live config. Triggers Spotify reinit if OAuth settings changed, and brightness refresh if night mode settings changed. Returns the resulting full config.

```bash
# Export
curl http://pi-ip:8080/api/config/export -o my-backup.json

# Import
curl -X POST http://pi-ip:8080/api/config/import \
  -H 'Content-Type: application/json' \
  -d @my-backup.json
```

### Weather config

Weather is configured via `GET|POST /api/config/weather`.

| Key | Default | Description |
|---|---|---|
| `api_key` | `""` | OpenWeatherMap API key (free tier sufficient) |
| `units` | `"metric"` | `"metric"` (°C) or `"imperial"` (°F) |
| `refresh_interval` | `600` | Seconds between fetches (minimum 60) |
| `city_interval` | `30` | Seconds each city is shown in the carousel |
| `show_city_name` | `true` | Show/hide scrolling city name |
| `test_condition` | `""` | Force a condition for testing (see presets below) |
| `cities` | `[]` | List of city objects |

Each city object: `{ "name": "Paris", "owm_id": 2988507 }` or `{ "name": "Tokyo", "lat": 35.69, "lon": 139.69 }`. `owm_id` takes priority over lat/lon, which takes priority over name.

**Test condition presets** (set `test_condition` to one of): `clear_day`, `clear_night`, `partly_cloudy`, `cloudy`, `drizzle`, `rain`, `thunderstorm`, `snow`, `fog`, `extreme_hot`, `extreme_cold`.

**Condition logic:**
- `extreme_hot` — temp ≥ 35 °C **and** sky is clear/sunny
- `extreme_cold` — temp < −10 °C (any sky condition)
- All other conditions come directly from the OWM weather code

### Patternflow API

```text
GET  /api/patternflow/patterns
POST /api/patternflow/pattern
POST /api/patternflow/knob
POST /api/patternflow/button
POST /api/patternflow/options
```

`/api/patternflow/pattern` accepts either `{ "index": 0 }` or `{ "name": "Pattern Name" }`. Knob/button endpoints are used by the web UI to drive Patternflow controls without physical encoders.

### GET /api/image
Returns `{ "has_image": bool, "is_gif": bool }`.

### DELETE /api/image
Removes the uploaded image/GIF from the Pi and switches back to clock mode.

### POST /api/image/upload
Upload a static image or animated GIF. The request must be `multipart/form-data`.

**Static image** (JPEG, PNG, WebP, …) — send the file pre-cropped to 64×32 by the browser:
```bash
curl -X POST http://pi-ip:8080/api/image/upload \
  -F "file=@cropped_64x32.png"
```

**Animated GIF** — send the original file with crop parameters (server crops each frame):
```bash
curl -X POST http://pi-ip:8080/api/image/upload \
  -F "file=@animation.gif" \
  -F "ox=10" -F "oy=5" -F "cropW=200" -F "cropH=100"
```

`ox`/`oy`: top-left of the crop rect in source-image pixels. `cropW`/`cropH`: size of the crop rect. Omit or set to `-1` to use the full frame. The server resizes each frame to 64×32 and saves the result as `static/matrix_image.gif`.

### POST /api/shutdown
Triggers `sudo shutdown -h now` on the Pi.

### POST /api/restart
Restarts the `led-matrix` systemd service.

### POST /api/service/stop
Stops the `led-matrix` systemd service. The web UI will go offline until the
service is started again from SSH or the Pi is rebooted with autostart enabled.

### POST /api/service/disable
Disables autostart after reboot without stopping the currently running service.

---

## Spotify Setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create a new app.
2. Add `http://YOUR_PI_IP:8080/callback` as a **Redirect URI**. If you want another path such as `/spotiup`, set `callback_path` to match.
3. Copy the **Client ID** and **Client Secret**.
4. In the web UI → **Spotify** section, enter your credentials, redirect URI, and callback path, then click **Save credentials**.
5. Click **Authorize Spotify** — a Spotify login page opens. After approving, you'll be redirected back and the token is saved to `/tmp/.spotify_token_cache` on the Pi.
6. Switch mode to **spotify** — the current track should appear.

The token is cached and refreshed automatically. You only need to authorize once.

---

## Adding a New Mode

1. Create `modes/mymode.py`:

```python
from PIL import Image, ImageDraw
from modes.base import BaseMode

class MyMode(BaseMode):
    def start(self):
        super().start()
        # initialize state

    def render(self, canvas):
        img = Image.new('RGB', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        # draw your frame
        canvas.SetImage(img)
```

2. Register it in `main.py` inside `MatrixController.MODES`:

```python
from modes.mymode import MyMode

MODES = {
    ...
    'mymode': MyMode,
}
```

3. Restart the service: `sudo systemctl restart led-matrix`

The new mode will appear automatically in the web UI.

---

## Service Management

After changing code, update the installed app and restart the service with:

```bash
cd /dashboard/claude/led-matrix
sudo bash update.sh
```

```bash
# Status
sudo systemctl status led-matrix

# Logs (live)
sudo journalctl -u led-matrix -f

# Restart
sudo systemctl restart led-matrix

# Stop
sudo systemctl stop led-matrix

# Start again after stopping
sudo systemctl start led-matrix

# Disable autostart
sudo systemctl disable led-matrix

# Re-enable autostart
sudo systemctl enable led-matrix
```

The installed service is `/etc/systemd/system/led-matrix.service`. It starts
`/opt/led-matrix/main.py` after `network-online.target` and after
`/opt/led-matrix/wait-for-network.sh` sees a default route plus an IPv4 address.

Emergency autostart kill switch if the app prevents normal access:

```bash
sudo nano /etc/systemd/system/led-matrix.service
```

Change this line:

```ini
ExecStart=/opt/led-matrix/venv/bin/python /opt/led-matrix/main.py
```

to:

```ini
ExecStart=/bin/sleep infinity
```

Then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart led-matrix
```

To restore the app, put the original `ExecStart` line back, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart led-matrix
```

---

## Troubleshooting

**Matrix shows nothing**  
- Confirm 5V supply is connected to the bonnet terminals (not just USB)  
- Check the ribbon cable is in the HUB75 **IN** connector  
- Run `sudo systemctl status led-matrix` — look for Python errors  
- Ensure audio is disabled: `/boot/config.txt` must have `dtparam=audio=off`

**"Permission denied" errors**  
The service must run as root. Check `User=root` in the service file.

**Dim or wrong colors**  
Increase brightness via `/api/brightness` or the web UI. Also check `gpio_slowdown` in `main.py` — try values 1–4.

**Spotify shows "No Spotify"**  
- Verify credentials are saved (`GET /api/config/spotify`)  
- Re-authorize via the web UI  
- Check logs for spotipy errors  
- Token cache at `/tmp/.spotify_token_cache` is lost on reboot — this is intentional (tmpfs). For persistence, change `cache_path` in `modes/spotify.py` to `/opt/led-matrix/.spotify_cache`

**Flickering / timing issues**  
Matrix timing is configured in `config.json` under `matrix`. Lower values are
faster; higher values are more tolerant of slow wiring/panels:

```json
"matrix": {
  "gpio_slowdown": 2,
  "pwm_bits": 7,
  "limit_refresh_rate_hz": 0,
  "disable_hardware_pulsing": false
}
```

If the panel flickers or shows artifacts, try `gpio_slowdown` values `3` or
`4`, or set `disable_hardware_pulsing` back to `true`. Restart the service
after matrix config changes.

---

## Pi Zero 1.3 Compatibility

**Short answer: Yes, but with caveats.**

| Feature | Pi Zero 2W | Pi Zero 1.3 |
|---|---|---|
| Matrix refresh (hardware) | ✅ Full speed | ✅ Full speed |
| Clock mode | ✅ Smooth | ✅ Smooth |
| Text scrolling | ✅ Smooth | ✅ Good |
| Game of Life | ✅ 20+ gen/s | ⚠️ 5–10 gen/s |
| Spotify rotation | ✅ 20+ fps | ⚠️ 5–10 fps |
| Boot time | ~20s | ~40s |

The **LED matrix refresh itself is hardware-driven** (DMA + GPIO). The Pi's CPU only needs to prepare each frame. On the Zero 1.3 (single-core ARM11 at 1 GHz), Python frame preparation is slower, so:

- **Clock & text**: No perceptible difference.
- **Game of Life**: Works but reduce `speed` to ≤8 gen/s to avoid frame-drop.
- **Spotify**: Album art rotation may be choppy (5–8 fps). Reduce by setting `speed_deg = 10` in `modes/spotify.py`.
- **Flask API**: Fully functional, slightly slower to start.

**Required hardware addition**: The Zero 1.3 has no built-in Wi-Fi. Use a USB Wi-Fi dongle (e.g., official Raspberry Pi Zero W dongle or any RTL8188-based adapter). You'll need a USB OTG adapter since the Zero 1.3 has only a micro-USB OTG port.

**Recommendation**: The Zero 2W is worth the small price difference (~$15) for the quad-core CPU. But if you already own a Zero 1.3, it will work fine for clock/text/GoL. Only Spotify rotation will feel less smooth.

**gpio_slowdown for Zero 1.3**: Set `matrix.gpio_slowdown` to `1` (the ARM11 is slower — ironically needs *less* slowdown).

---

## Power Supply Sizing

| Scenario | Current |
|---|---|
| All LEDs off (Pi only) | 0.5 A |
| Clock (red digits, most LEDs off) | 1–2 A |
| Game of Life (partial fill) | 2–4 A |
| All LEDs white, 100% brightness | ~8–10 A |

Use a **5V 4A minimum** supply. A quality **5V 5A** supply covers almost all real-world use at normal brightness (≤70%). A 10A supply gives headroom for 100% brightness white scenes.

---

## License

GPL-3.0-or-later
