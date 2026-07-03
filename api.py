"""
REST API + Web UI for LED Matrix Controller.
All endpoints return JSON. Web UI served at /.
"""

import os
import threading
from flask import Flask, jsonify, request, render_template

try:
    import spotipy
    from spotipy.oauth2 import SpotifyOAuth
    SPOTIPY_AVAILABLE = True
except ImportError:
    SPOTIPY_AVAILABLE = False


def create_app(get_controller_fn):
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), 'templates'),
        static_folder=os.path.join(os.path.dirname(__file__), 'static'),
    )

    def ctrl():
        return get_controller_fn()

    # ── Web UI ────────────────────────────────────────────────────────────────

    @app.route('/')
    def index():
        return render_template('index.html')

    # ── Status ────────────────────────────────────────────────────────────────

    @app.route('/api/status')
    def status():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503
        return jsonify(
            mode=c.get_mode(),
            modes=c.get_mode_names(),
            brightness=c.config.get('brightness', 50),
            config=c.config.get_all(),
        )

    # ── Mode ─────────────────────────────────────────────────────────────────

    @app.route('/api/mode', methods=['GET', 'POST'])
    def mode():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503

        if request.method == 'GET':
            return jsonify(mode=c.get_mode(), modes=c.get_mode_names())

        data = request.get_json(force=True, silent=True) or {}
        name = data.get('mode', '').strip()
        if not name:
            return jsonify(error='mode field required'), 400

        ok = c.set_mode(name)
        if not ok:
            return jsonify(error=f'unknown mode: {name}'), 400
        return jsonify(mode=name, status='ok')

    # ── Brightness ────────────────────────────────────────────────────────────

    @app.route('/api/brightness', methods=['POST'])
    def brightness():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503
        data = request.get_json(force=True, silent=True) or {}
        value = int(data.get('value', 50))
        c.set_brightness(value)
        return jsonify(brightness=c.config.get('brightness'), status='ok')

    # ── Text ──────────────────────────────────────────────────────────────────

    @app.route('/api/text', methods=['GET', 'POST'])
    def text():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503

        if request.method == 'GET':
            return jsonify(c.config.get_section('text'))

        data = request.get_json(force=True, silent=True) or {}
        c.config.set_section('text', data)
        # Switch to text mode automatically
        if c.get_mode() != 'text':
            c.set_mode('text')
        return jsonify(status='ok', config=c.config.get_section('text'))

    # ── Generic section config ────────────────────────────────────────────────

    @app.route('/api/config/<section>', methods=['GET', 'POST'])
    def config_section(section):
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503

        allowed = {'clock', 'spotify', 'gameoflife', 'text', 'patternflow'}
        if section not in allowed:
            return jsonify(error=f'unknown section: {section}'), 400

        if request.method == 'GET':
            return jsonify(c.config.get_section(section))

        data = request.get_json(force=True, silent=True) or {}
        c.config.set_section(section, data)

        # If updating spotify creds, reinit the spotify mode
        if section == 'spotify':
            spotify_mode = c.modes.get('spotify')
            if spotify_mode:
                spotify_mode.reinit()

        return jsonify(status='ok', config=c.config.get_section(section))

    # ── Spotify OAuth ─────────────────────────────────────────────────────────

    @app.route('/api/spotify/auth_url')
    def spotify_auth_url():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503
        if not SPOTIPY_AVAILABLE:
            return jsonify(error='spotipy not installed'), 500

        cfg = c.config.get_section('spotify')
        cid = cfg.get('client_id', '')
        secret = cfg.get('client_secret', '')
        redirect = cfg.get('redirect_uri', '')

        if not cid or not secret:
            return jsonify(error='spotify client_id/secret not configured'), 400

        try:
            auth = SpotifyOAuth(
                client_id=cid,
                client_secret=secret,
                redirect_uri=redirect,
                scope='user-read-currently-playing user-read-playback-state',
                cache_path='/tmp/.spotify_token_cache',
                open_browser=False,
            )
            url = auth.get_authorize_url()
            return jsonify(url=url)
        except Exception as e:
            return jsonify(error=str(e)), 500

    @app.route('/callback')
    def spotify_callback():
        code = request.args.get('code')
        if not code:
            return 'Missing code parameter', 400

        c = ctrl()
        if not c:
            return 'Controller not ready', 503

        cfg = c.config.get_section('spotify')
        try:
            auth = SpotifyOAuth(
                client_id=cfg.get('client_id', ''),
                client_secret=cfg.get('client_secret', ''),
                redirect_uri=cfg.get('redirect_uri', ''),
                scope='user-read-currently-playing user-read-playback-state',
                cache_path='/tmp/.spotify_token_cache',
                open_browser=False,
            )
            auth.get_access_token(code, as_dict=False)
            spotify_mode = c.modes.get('spotify')
            if spotify_mode:
                spotify_mode.reinit()
            return '<h2>Spotify connected!</h2><p>You can close this tab.</p>'
        except Exception as e:
            return f'Error: {e}', 500

    # ── Patternflow ───────────────────────────────────────────────────────────

    @app.route('/api/patternflow/patterns')
    def pf_patterns():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503
        pf = c.modes.get('patternflow')
        if not pf:
            return jsonify(error='patternflow mode not loaded'), 404
        current = pf.get_current_pattern()
        return jsonify(patterns=pf.get_pattern_names(), **current)

    @app.route('/api/patternflow/pattern', methods=['POST'])
    def pf_set_pattern():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503
        pf = c.modes.get('patternflow')
        if not pf:
            return jsonify(error='patternflow mode not loaded'), 404

        data = request.get_json(force=True, silent=True) or {}
        if 'index' in data:
            idx = int(data['index'])
        elif 'name' in data:
            names = pf.get_pattern_names()
            name = data['name'].strip()
            if name not in names:
                return jsonify(error=f'unknown pattern: {name}'), 400
            idx = names.index(name)
        else:
            return jsonify(error='index or name required'), 400

        pf.set_pattern(idx)
        if c.get_mode() != 'patternflow':
            c.set_mode('patternflow')
        return jsonify(status='ok', **pf.get_current_pattern())

    @app.route('/api/patternflow/knob', methods=['POST'])
    def pf_knob():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503
        pf = c.modes.get('patternflow')
        if not pf:
            return jsonify(error='patternflow mode not loaded'), 404
        data = request.get_json(force=True, silent=True) or {}
        knob  = int(data.get('knob', 0))
        delta = int(data.get('delta', 0))
        if not (0 <= knob <= 3):
            return jsonify(error='knob must be 0-3'), 400
        pf.web_knob(knob, delta)
        return jsonify(status='ok')

    @app.route('/api/patternflow/button', methods=['POST'])
    def pf_button():
        c = ctrl()
        if not c:
            return jsonify(error='controller not ready'), 503
        pf = c.modes.get('patternflow')
        if not pf:
            return jsonify(error='patternflow mode not loaded'), 404
        data = request.get_json(force=True, silent=True) or {}
        knob = int(data.get('knob', 0))
        if not (0 <= knob <= 3):
            return jsonify(error='knob must be 0-3'), 400
        pf.web_button(knob)
        return jsonify(status='ok')

    # ── Shutdown ──────────────────────────────────────────────────────────────

    @app.route('/api/shutdown', methods=['POST'])
    def shutdown():
        c = ctrl()
        if c:
            t = threading.Thread(target=c.trigger_shutdown, daemon=True)
            t.start()
        return jsonify(status='shutting down')

    # ── Restart (restart the service, not the Pi) ─────────────────────────────

    @app.route('/api/restart', methods=['POST'])
    def restart():
        os.system("sudo systemctl restart led-matrix")
        return jsonify(status='restarting')

    return app
