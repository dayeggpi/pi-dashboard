'use strict';

let _toastTimer = null;

function toast(msg, ok = true) {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.style.background = ok ? '#2e7d32' : '#b71c1c';
  el.classList.add('show');
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => el.classList.remove('show'), 2500);
}

async function api(path, method = 'GET', body = null) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body) opts.body = JSON.stringify(body);
  const r = await fetch(path, opts);
  return r.json();
}

// ── Helpers ──────────────────────────────────────────────────────────────────

function hexToRgb(hex) {
  const m = hex.match(/^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i);
  return m ? [parseInt(m[1], 16), parseInt(m[2], 16), parseInt(m[3], 16)] : [255, 255, 255];
}

function rgbToHex(arr) {
  return '#' + arr.map(v => v.toString(16).padStart(2, '0')).join('');
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  const data = await api('/api/status').catch(() => null);
  if (!data) { toast('Cannot reach API', false); return; }

  document.getElementById('current-mode').textContent = data.mode || '—';
  document.getElementById('current-brightness').textContent = data.brightness ?? '—';

  const br = document.getElementById('brightness');
  br.value = data.brightness ?? 50;
  document.getElementById('brightness-val').textContent = br.value;

  // Build mode buttons
  const container = document.getElementById('mode-buttons');
  (data.modes || []).forEach(name => {
    const btn = document.createElement('button');
    btn.className = 'mode-btn' + (name === data.mode ? ' active' : '');
    btn.textContent = name;
    btn.dataset.mode = name;
    btn.onclick = () => setMode(name);
    container.appendChild(btn);
  });

  // Populate config panels from saved config
  const cfg = data.config || {};

  // Clock
  if (cfg.clock) {
    document.getElementById('clock-color').value = rgbToHex(cfg.clock.color || [255, 0, 0]);
    document.getElementById('clock-seconds').checked = cfg.clock.show_seconds !== false;
  }

  // Text
  if (cfg.text) {
    document.getElementById('text-content').value = cfg.text.content || '';
    document.getElementById('text-color').value = rgbToHex(cfg.text.color || [255, 255, 255]);
    document.getElementById('text-size').value = cfg.text.size || 1;
    document.getElementById('text-speed').value = cfg.text.speed || 30;
    document.getElementById('text-speed-val').textContent = cfg.text.speed || 30;
    document.getElementById('text-scroll').checked = cfg.text.scroll !== false;
  }

  // Game of Life
  if (cfg.gameoflife) {
    document.getElementById('gol-color').value = rgbToHex(cfg.gameoflife.color || [0, 255, 0]);
    document.getElementById('gol-speed').value = cfg.gameoflife.speed || 10;
    document.getElementById('gol-speed-val').textContent = cfg.gameoflife.speed || 10;
    document.getElementById('gol-wrap').checked = cfg.gameoflife.wrap !== false;
  }

  // Spotify
  if (cfg.spotify) {
    document.getElementById('sp-client-id').value = cfg.spotify.client_id || '';
    document.getElementById('sp-redirect').value = cfg.spotify.redirect_uri || '';
    // never pre-fill secret
  }

  // Patternflow
  try {
    const pf = await api('/api/patternflow/patterns');
    if (pf && pf.patterns) {
      loadPfPatterns(pf.patterns, pf.index, pf.knob_labels);
    }
  } catch (_) {}

  showPanelForMode(data.mode);
}

// ── Mode ──────────────────────────────────────────────────────────────────────

async function setMode(name) {
  const data = await api('/api/mode', 'POST', { mode: name });
  if (data.error) { toast(data.error, false); return; }
  document.getElementById('current-mode').textContent = name;
  document.querySelectorAll('.mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === name);
  });
  showPanelForMode(name);
  toast(`Mode → ${name}`);
}

function showPanelForMode(mode) {
  ['clock', 'text', 'gameoflife', 'spotify', 'patternflow'].forEach(m => {
    const el = document.getElementById(`panel-${m}`);
    if (el) el.style.display = (m === mode) ? '' : 'none';
  });
}

// ── Brightness ────────────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', () => {
  const br = document.getElementById('brightness');
  const bv = document.getElementById('brightness-val');
  br.addEventListener('input', () => bv.textContent = br.value);

  const ts = document.getElementById('text-speed');
  const tv = document.getElementById('text-speed-val');
  ts.addEventListener('input', () => tv.textContent = ts.value);

  const gs = document.getElementById('gol-speed');
  const gv = document.getElementById('gol-speed-val');
  gs.addEventListener('input', () => gv.textContent = gs.value);

  init();
});

async function setBrightness() {
  const value = parseInt(document.getElementById('brightness').value);
  const data = await api('/api/brightness', 'POST', { value });
  if (data.error) { toast(data.error, false); return; }
  document.getElementById('current-brightness').textContent = value;
  toast(`Brightness → ${value}%`);
}

// ── Clock ─────────────────────────────────────────────────────────────────────

async function saveClock() {
  const color = hexToRgb(document.getElementById('clock-color').value);
  const show_seconds = document.getElementById('clock-seconds').checked;
  const data = await api('/api/config/clock', 'POST', { color, show_seconds });
  if (data.error) { toast(data.error, false); return; }
  toast('Clock config saved');
}

// ── Text ──────────────────────────────────────────────────────────────────────

async function saveText() {
  const payload = {
    content: document.getElementById('text-content').value,
    color: hexToRgb(document.getElementById('text-color').value),
    size: parseInt(document.getElementById('text-size').value),
    speed: parseInt(document.getElementById('text-speed').value),
    scroll: document.getElementById('text-scroll').checked,
  };
  const data = await api('/api/text', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  // Switch mode button to text
  document.querySelectorAll('.mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === 'text');
  });
  document.getElementById('current-mode').textContent = 'text';
  toast('Text sent!');
}

// ── Game of Life ──────────────────────────────────────────────────────────────

async function saveGol() {
  const color = hexToRgb(document.getElementById('gol-color').value);
  const speed = parseInt(document.getElementById('gol-speed').value);
  const wrap = document.getElementById('gol-wrap').checked;
  const data = await api('/api/config/gameoflife', 'POST', { color, speed, wrap });
  if (data.error) { toast(data.error, false); return; }
  toast('Game of Life config saved');
}

// ── Spotify ───────────────────────────────────────────────────────────────────

async function saveSpotify() {
  const payload = {
    client_id: document.getElementById('sp-client-id').value.trim(),
    redirect_uri: document.getElementById('sp-redirect').value.trim(),
  };
  const secret = document.getElementById('sp-client-secret').value.trim();
  if (secret) payload.client_secret = secret;

  const data = await api('/api/config/spotify', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  toast('Spotify credentials saved');
}

async function authorizeSpotify() {
  const data = await api('/api/spotify/auth_url');
  if (data.error) { toast(data.error, false); return; }
  window.open(data.url, '_blank');
}

// ── Patternflow ───────────────────────────────────────────────────────────────

function loadPfPatterns(names, activeIdx, knobLabels) {
  const container = document.getElementById('pf-pattern-buttons');
  if (!container) return;
  container.innerHTML = '';
  names.forEach((name, i) => {
    const btn = document.createElement('button');
    btn.className = 'mode-btn' + (i === activeIdx ? ' active' : '');
    btn.textContent = name;
    btn.dataset.mode = name;
    btn.onclick = () => setPfPattern(i, name, names, knobLabels);
    container.appendChild(btn);
  });
  buildPfKnobs(knobLabels);
}

function buildPfKnobs(labels) {
  const grid = document.getElementById('pf-knob-controls');
  if (!grid || !labels) return;
  grid.innerHTML = '';
  labels.forEach((label, k) => {
    const num = document.createElement('span');
    num.className = 'pf-k-num';
    num.textContent = `K${k + 1}`;

    const name = document.createElement('span');
    name.className = 'pf-k-name';
    name.textContent = label;

    const btns = document.createElement('div');
    btns.className = 'pf-k-btns';

    [[-5, '−5'], [-1, '−1'], [0, '↺'], [1, '+1'], [5, '+5']].forEach(([delta, text]) => {
      const b = document.createElement('button');
      b.className = 'pf-btn' + (delta === 0 ? ' pf-btn-reset' : '');
      b.textContent = text;
      b.title = delta === 0 ? `Reset K${k + 1}` : `K${k + 1} ${delta > 0 ? '+' : ''}${delta}`;
      b.onclick = delta === 0 ? () => pfBtn(k) : () => pfKnob(k, delta);
      btns.appendChild(b);
    });

    grid.appendChild(num);
    grid.appendChild(name);
    grid.appendChild(btns);
  });
}

async function pfKnob(knob, delta) {
  await api('/api/patternflow/knob', 'POST', { knob, delta });
}

async function pfBtn(knob) {
  await api('/api/patternflow/button', 'POST', { knob });
}

async function setPfPattern(idx, name, allNames, prevLabels) {
  const data = await api('/api/patternflow/pattern', 'POST', { index: idx });
  if (data.error) { toast(data.error, false); return; }

  document.querySelectorAll('#pf-pattern-buttons .mode-btn').forEach((b, i) => {
    b.classList.toggle('active', i === idx);
  });
  buildPfKnobs(data.knob_labels || prevLabels);

  document.querySelectorAll('.mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === 'patternflow');
  });
  document.getElementById('current-mode').textContent = 'patternflow';
  showPanelForMode('patternflow');
  toast(`Pattern → ${name}`);
}

// ── System ────────────────────────────────────────────────────────────────────

async function restartService() {
  if (!confirm('Restart the LED Matrix service?')) return;
  await api('/api/restart', 'POST');
  toast('Service restarting…');
}

async function confirmShutdown() {
  if (!confirm('Shut down the Raspberry Pi?')) return;
  await api('/api/shutdown', 'POST');
  toast('Shutting down…');
}
