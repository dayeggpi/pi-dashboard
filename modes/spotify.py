import os
import time
import threading
import io
import requests
from PIL import Image, ImageDraw, ImageFont
from modes.base import BaseMode

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False

FONT_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'
FONT_BOLD_PATH = '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf'
PANEL_W = 31   # right panel pixel width (x 33..63)
SCROLL_SPEED = 15   # px/sec
SCROLL_GAP = 16     # blank px between text end and restart


def load_font(size=7):
    try:
        return ImageFont.truetype(FONT_PATH, size)
    except Exception:
        try:
            return ImageFont.load_default(size=size)
        except Exception:
            return ImageFont.load_default()


def load_font_bold(size=7):
    try:
        return ImageFont.truetype(FONT_BOLD_PATH, size)
    except Exception:
        return load_font(size)


def _text_w(text, font):
    try:
        bb = font.getbbox(text)
        return bb[2] - bb[0]
    except Exception:
        return len(text) * 4


class SpotifyMode(BaseMode):
    def __init__(self, config):
        super().__init__(config)
        self.sp = None
        self.track = None
        self.album_art = None
        self.rotation = 0.0
        self._update_thread = None
        self._lock = threading.Lock()
        self.last_render = time.time()
        self._artist_scroll = 0.0
        self._track_scroll = 0.0
        self._cd_mask = None

    def start(self):
        super().start()
        self._init_spotify()
        self._update_thread = threading.Thread(target=self._update_loop, daemon=True)
        self._update_thread.start()

    def stop(self):
        super().stop()

    def _init_spotify(self):
        if not SPOTIPY_AVAILABLE:
            return
        cfg = self.config.get_section('spotify')
        cid = cfg.get('client_id', '')
        secret = cfg.get('client_secret', '')
        redirect = cfg.get('redirect_uri', 'http://localhost:8080/spotiup')

        if not cid or not secret:
            return
        try:
            auth = SpotifyOAuth(
                client_id=cid,
                client_secret=secret,
                redirect_uri=redirect,
                scope='user-read-currently-playing user-read-playback-state',
                cache_path=os.path.join(os.path.dirname(__file__), '..', '.spotify_token_cache'),
                open_browser=False,
            )
            self.sp = spotipy.Spotify(auth_manager=auth)
        except Exception as e:
            print(f"Spotify init error: {e}")

    def reinit(self):
        self.sp = None
        self._init_spotify()

    def _update_loop(self):
        while self.active:
            try:
                self._fetch()
            except Exception as e:
                print(f"Spotify fetch error: {e}")
            with self._lock:
                track = self.track
            if track and track.get('is_playing'):
                time.sleep(4)    # active playback
            elif track:
                time.sleep(15)   # paused
            else:
                time.sleep(30)   # nothing playing

    def _fetch(self):
        if not self.sp:
            return
        result = self.sp.current_playback()
        if not result:
            with self._lock:
                self.track = None
            return

        item = result.get('item') or {}
        if not item:
            with self._lock:
                self.track = None
            return

        name = item.get('name', '')
        artist = ', '.join(a['name'] for a in item.get('artists', []))
        progress = result.get('progress_ms', 0)
        duration = item.get('duration_ms', 1)
        is_playing = result.get('is_playing', False)

        images = item.get('album', {}).get('images', [])
        art_url = images[-1]['url'] if images else None

        old_url = (self.track or {}).get('art_url')
        if art_url and art_url != old_url:
            self._load_art(art_url)

        with self._lock:
            self.track = {
                'name': name,
                'artist': artist,
                'progress': progress,
                'duration': duration,
                'is_playing': is_playing,
                'art_url': art_url,
            }

    def _load_art(self, url):
        try:
            r = requests.get(url, timeout=5)
            r.raise_for_status()
            art = Image.open(io.BytesIO(r.content)).convert('RGB')
            art = art.resize((32, 32), Image.LANCZOS)
            with self._lock:
                self.album_art = art
        except Exception as e:
            print(f"Album art error: {e}")

    # ── CD mask ──────────────────────────────────────────────────────────────

    def _get_cd_mask(self):
        if self._cd_mask is None:
            mask = Image.new('L', (32, 32), 0)
            d = ImageDraw.Draw(mask)
            d.ellipse([1, 1, 30, 30], fill=255)   # outer circle
            d.ellipse([13, 13, 18, 18], fill=0)   # center spindle hole
            self._cd_mask = mask
        return self._cd_mask

    def _apply_cd_mask(self, art):
        result = Image.new('RGB', (32, 32), (0, 0, 0))
        result.paste(art, mask=self._get_cd_mask())
        # subtle ring around spindle hole
        ImageDraw.Draw(result).ellipse([12, 12, 19, 19], outline=(55, 55, 55))
        return result

    # ── Scrolling ─────────────────────────────────────────────────────────────

    @staticmethod
    def _advance_scroll(offset, text_w, panel_w, elapsed):
        if text_w <= panel_w:
            return 0.0
        return (offset + SCROLL_SPEED * elapsed) % (text_w + SCROLL_GAP)

    @staticmethod
    def _draw_scrolling(panel, y, text, text_w, offset, fill, font):
        """Draw scrolling text via grayscale mask to avoid FreeType sub-pixel color artifacts."""
        mask = Image.new('L', panel.size, 0)
        d = ImageDraw.Draw(mask)
        px = -int(offset)
        d.text((px, y), text, fill=255, font=font)
        if text_w > PANEL_W:
            d.text((px + text_w + SCROLL_GAP, y), text, fill=255, font=font)
        panel.paste(Image.new('RGB', panel.size, fill), mask=mask)

    # ── Formatting ────────────────────────────────────────────────────────────

    @staticmethod
    def _fmt(ms):
        s = ms // 1000
        return f"{s // 60}:{s % 60:02d}"

    # ── Render ────────────────────────────────────────────────────────────────

    def render(self, canvas):
        now = time.time()
        elapsed = now - self.last_render
        self.last_render = now

        img = Image.new('RGB', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(img)
        font = load_font(7)
        font_bold = load_font_bold(7)
        font_small = load_font(6)

        with self._lock:
            track = self.track
            art = self.album_art

        if not track:
            msg = "No Spotify" if SPOTIPY_AVAILABLE else "Install spotipy"
            mask = Image.new('L', img.size, 0)
            ImageDraw.Draw(mask).text((2, 12), msg, fill=255, font=font)
            img.paste(Image.new('RGB', img.size, (80, 80, 80)), mask=mask)
            canvas.SetImage(img)
            return

        # --- Left 32px: rotating CD ---
        if art:
            speed_deg = 20 if track.get('is_playing') else 0
            self.rotation = (self.rotation + speed_deg * elapsed) % 360
            rotated = art.rotate(-self.rotation, resample=Image.BILINEAR)
            img.paste(self._apply_cd_mask(rotated), (0, 0))
        else:
            cx, cy = 16, 16
            draw.ellipse([cx-14, cy-14, cx+14, cy+14], outline=(60, 60, 60))
            draw.ellipse([cx-3,  cy-3,  cx+3,  cy+3],  outline=(60, 60, 60))

        # --- Right 31px panel (x=33..63) ---
        panel = Image.new('RGB', (PANEL_W, 32), (0, 0, 0))
        pdraw = ImageDraw.Draw(panel)

        artist = track['artist']
        name = track['name']
        artist_w = _text_w(artist, font)
        track_w = _text_w(name, font_bold)

        self._artist_scroll = self._advance_scroll(self._artist_scroll, artist_w, PANEL_W, elapsed)
        self._track_scroll = self._advance_scroll(self._track_scroll, track_w, PANEL_W, elapsed)

        # Artist (y=1)
        self._draw_scrolling(panel, 1, artist, artist_w, self._artist_scroll,
                             (180, 180, 180), font)
        # Track name (y=10)
        self._draw_scrolling(panel, 10, name, track_w, self._track_scroll,
                             (255, 255, 255), font_bold)

        # Progress bar (y=21, 2px tall)
        progress_ratio = track['progress'] / max(track['duration'], 1)
        pdraw.rectangle([0, 21, PANEL_W - 1, 22], fill=(40, 40, 40))
        fill_w = int((PANEL_W - 1) * progress_ratio)
        if fill_w > 0:
            pdraw.rectangle([0, 21, fill_w, 22], fill=(30, 215, 96))

        # Time string (y=25) — mode '1' forces PIL into binary pixel rendering, no anti-aliasing
        time_str = f"{self._fmt(track['progress'])}/{self._fmt(track['duration'])}"
        t_bin = Image.new('1', panel.size, 0)
        ImageDraw.Draw(t_bin).text((0, 25), time_str, fill=1, font=font_small)
        t_mask = t_bin.convert('L')
        panel.paste(Image.new('RGB', panel.size, (180, 180, 180)), mask=t_mask)

        img.paste(panel, (33, 0))
        canvas.SetImage(img)
