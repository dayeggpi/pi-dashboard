# LED Matrix Controller

Original project : https://github.com/engmung/PatternFlow

A full-featured controller for a **64×32 RGB LED matrix** driven by a Raspberry Pi with the Adafruit RGB Matrix Bonnet. Modes: digital clock, Spotify now-playing, Conway's Game of Life, and scrolling text. Controlled via REST API and a built-in web interface.

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
    ├── base.py    ← BaseMode ABC
    ├── clock.py   ← 7-segment digital clock
    ├── spotify.py ← Now-playing with rotating art
    ├── gameoflife.py ← Conway's Game of Life
    └── text.py    ← Scrolling/static text
```

The main loop runs at the matrix's VSync rate (~100 Hz). Each mode's `render(canvas)` is called every frame. Mode-specific state (scroll position, rotation angle, GoL grid) is maintained per-mode instance. The Flask API runs in a daemon thread.

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
  "clock": {
    "color": [255, 0, 0],
    "show_seconds": true
  },
  "text": {
    "content": "Hello!",
    "color": [255, 255, 255],
    "speed": 30,
    "size": 1,
    "scroll": true
  },
  "gameoflife": {
    "speed": 10,
    "color": [0, 255, 0],
    "wrap": true
  },
  "spotify": {
    "client_id": "your_id",
    "client_secret": "your_secret",
    "redirect_uri": "http://YOUR_PI_IP:8080/callback"
  },
  "patternflow": {
    "current_pattern": 0,
    "encoders_enabled": false,
    "invert_encoder": false,
    "encoders": [
      {"clk": -1, "dt": -1, "sw": -1},
      {"clk": -1, "dt": -1, "sw": -1},
      {"clk": -1, "dt": -1, "sw": -1},
      {"clk": -1, "dt": -1, "sw": -1}
    ]
  }
}
```

`patternflow` physical encoders are disabled by default. Enable them only after
choosing GPIO pins that do not overlap the RGB matrix HAT/Bonnet signals;
overlapping pins can make the display render as a few horizontal bands until
the service is restarted.

---

## Web Interface

Open `http://<pi-ip>:8080` in any browser.

- **Mode** — click a button to switch modes instantly
- **Brightness** — 1–100% slider
- **Clock** — color picker, toggle seconds
- **Text** — content, color, size (1–3), scroll speed, scroll toggle
- **Game of Life** — color, speed, edge wrap
- **Spotify** — credentials, authorize button
- **System** — restart service, shutdown Pi

---

## REST API

Base URL: `http://<pi-ip>:8080`

### GET /api/status
Returns current mode, brightness, full config.

### GET|POST /api/mode
```json
// POST body
{ "mode": "clock" }
// modes: "clock", "spotify", "gameoflife", "text", "patternflow"
```

### POST /api/brightness
```json
{ "value": 75 }
```

### GET|POST /api/text
```json
// POST — switches to text mode and displays
{
  "content": "Hello World",
  "color": [255, 128, 0],
  "speed": 40,
  "size": 1,
  "scroll": true
}
```
`size`: 1 = 8px, 2 = 16px, 3 = 24px  
`speed`: pixels per second (scrolling)

### GET|POST /api/config/{section}
`section` = `clock` | `text` | `gameoflife` | `spotify`

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

### POST /api/shutdown
Triggers `sudo shutdown -h now` on the Pi.

### POST /api/restart
Restarts the `led-matrix` systemd service.

---

## Spotify Setup

1. Go to [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) and create a new app.
2. Add `http://YOUR_PI_IP:8080/callback` as a **Redirect URI**.
3. Copy the **Client ID** and **Client Secret**.
4. In the web UI → **Spotify** section, enter your credentials and the redirect URI, then click **Save credentials**.
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

```bash
# Status
sudo systemctl status led-matrix

# Logs (live)
sudo journalctl -u led-matrix -f

# Restart
sudo systemctl restart led-matrix

# Stop
sudo systemctl stop led-matrix

# Disable autostart
sudo systemctl disable led-matrix
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
Try `options.gpio_slowdown = 3` or `4` in `main.py → _init_matrix()`. Higher values slow GPIO to match slower Pi models.

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

**gpio_slowdown for Zero 1.3**: Set `opts.gpio_slowdown = 1` (the ARM11 is slower — ironically needs *less* slowdown).

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

MIT
