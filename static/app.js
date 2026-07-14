'use strict';

let _toastTimer = null;
let _screenOn = true;
let _nightModeEnabled = false;
let drawTool = 'pen';
let drawPixels = new Map();
let drawMouseDown = false;
let drawCanvasWidth = 64;
const DRAW_H = 32;
let DRAW_SCALE = 8;
let reminders = [];
let palettes = [];

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

function uid() {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

function rgbKey(rgb) {
  return rgb.join(',');
}

function keyRgb(value) {
  return value.split(',').map(v => parseInt(v, 10) || 0);
}

function showTab(name) {
  document.querySelectorAll('.tab-panel').forEach(panel => {
    panel.classList.toggle('active', panel.id === `tab-${name}`);
  });
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.classList.toggle('active', btn.id === `tab-btn-${name}`);
  });
}

function foregroundModes(modes) {
  return modes.filter(name => name !== 'reminder');
}

function carouselModes(modes) {
  return modes.filter(name => !['reminder', 'workout'].includes(name));
}

// ── Init ──────────────────────────────────────────────────────────────────────

async function init() {
  const data = await api('/api/status').catch(() => null);
  if (!data) { toast('Cannot reach API', false); return; }

  document.getElementById('current-mode').textContent = data.mode || '—';
  document.getElementById('current-brightness').textContent = data.brightness ?? '—';

  _screenOn = data.screen_on !== false;
  _nightModeEnabled = !!(data.config?.night_mode?.enabled);
  updateScreenBtn();
  updateNightBtn();

  const br = document.getElementById('brightness');
  br.value = data.brightness ?? 50;
  document.getElementById('brightness-val').textContent = br.value;

  // Build mode buttons
  const container = document.getElementById('mode-buttons');
  const modeNames = data.modes || [];
  const displayModeNames = foregroundModes(modeNames);
  displayModeNames.forEach(name => {
    const btn = document.createElement('button');
    btn.className = 'mode-btn' + (name === data.mode ? ' active' : '');
    btn.textContent = name;
    btn.dataset.mode = name;
    btn.onclick = () => setMode(name);
    container.appendChild(btn);
  });

  // Populate config panels from saved config
  const cfg = data.config || {};

  // Night mode
  if (cfg.night_mode) {
    document.getElementById('night-enabled').checked = !!cfg.night_mode.enabled;
    const nb = cfg.night_mode.brightness ?? 20;
    document.getElementById('night-brightness').value = nb;
    document.getElementById('night-brightness-val').textContent = nb;
    document.getElementById('night-start').value = cfg.night_mode.start || '22:00';
    document.getElementById('night-end').value = cfg.night_mode.end || '05:00';
  }

  // Carousel (exclude workout — auto-cycling during workout would interrupt it)
  buildCarouselModes(carouselModes(modeNames), cfg.carousel || {});
  buildPomodoroReturnModes(displayModeNames, cfg.pomodoro || {});
  loadReminders(cfg.reminders || {});

  // Clock
  if (cfg.clock) {
    document.getElementById('clock-color').value = rgbToHex(cfg.clock.color || [255, 0, 0]);
    document.getElementById('clock-seconds').checked = cfg.clock.show_seconds !== false;
  }

  // Text
  if (cfg.text) {
    document.getElementById('text-source').value = cfg.text.source || 'manual';
    document.getElementById('text-content').value = cfg.text.content || '';
    document.getElementById('text-url').value = cfg.text.url || '';
    document.getElementById('text-poll-interval').value = cfg.text.poll_interval || 60;
    document.getElementById('text-color').value = rgbToHex(cfg.text.color || [255, 255, 255]);
    document.getElementById('text-speed').value = cfg.text.speed || 30;
    document.getElementById('text-speed-val').textContent = cfg.text.speed || 30;
    const scrollDir = cfg.text.scroll_direction || (cfg.text.scroll !== false ? 'horizontal' : 'off');
    document.getElementById('text-scroll-mode').value = scrollDir;
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
    document.getElementById('sp-callback-path').value = cfg.spotify.callback_path || '/callback';
    document.getElementById('sp-artist-speed').value = cfg.spotify.artist_speed || 12;
    document.getElementById('sp-artist-speed-val').textContent = cfg.spotify.artist_speed || 12;
    document.getElementById('sp-track-speed').value = cfg.spotify.track_speed || 12;
    document.getElementById('sp-track-speed-val').textContent = cfg.spotify.track_speed || 12;
    // never pre-fill secret
  }

  if (cfg.draw) {
    loadDrawConfig(cfg.draw);
  } else {
    setupDrawCanvas();
  }

  if (cfg.pomodoro) {
    document.getElementById('pom-gradient-start').value = rgbToHex(cfg.pomodoro.gradient_start || [30, 215, 96]);
    document.getElementById('pom-gradient-end').value = rgbToHex(cfg.pomodoro.gradient_end || [255, 210, 64]);
    document.getElementById('pom-background').value = rgbToHex(cfg.pomodoro.background_color || [0, 0, 0]);
    document.getElementById('pom-elapsed-background').value = rgbToHex(cfg.pomodoro.elapsed_background || [25, 25, 25]);
    document.getElementById('pom-text-color').value = rgbToHex(cfg.pomodoro.text_color || [255, 255, 255]);
    document.getElementById('pom-tick-pixel-color').value = rgbToHex(cfg.pomodoro.tick_pixel_color || [255, 255, 255]);
    document.getElementById('pom-flash-red').checked = cfg.pomodoro.flash_red !== false;
    document.getElementById('pom-tick-pixel-enabled').checked = cfg.pomodoro.tick_pixel_enabled !== false;
    document.getElementById('pom-flash-threshold').value = Math.round((cfg.pomodoro.flash_threshold_ms || 5000) / 1000);
    document.getElementById('pom-return-enabled').checked = !!cfg.pomodoro.return_after_elapsed_enabled;
    document.getElementById('pom-return-delay').value = cfg.pomodoro.return_after_elapsed_delay_s ?? 10;
    document.getElementById('pom-return-mode').value = cfg.pomodoro.return_after_elapsed_mode || 'clock';
  }

  // Workout
  if (cfg.workout) {
    const wc = cfg.workout;
    const wt = wc.workout_type || 'tabata';
    if (wt === 'hiit') {
      _workoutCfg.hiit.work_s = wc.work_s || 30;
      _workoutCfg.hiit.rest_s = wc.rest_s !== undefined ? wc.rest_s : 15;
      _workoutCfg.hiit.rounds = wc.rounds || 10;
      _refreshWorkoutDisplay();
    }
    _workoutType = wt;
    selectWorkoutType(wt);
  }

  // Library
  const lib = cfg.library || {};
  document.getElementById('lib-rotation').checked = lib.rotation_enabled !== false;
  document.getElementById('lib-interval').value = lib.interval || 10;
  _libraryItems = lib.items || [];
  renderLibraryList();

  // Patternflow
  try {
    const pf = await api('/api/patternflow/patterns');
    if (pf && pf.patterns) {
      loadPfPatterns(pf.patterns, pf.index, pf.knob_labels, pf.extra_button_labels);
      syncPfOptions(pf);
    }
  } catch (_) {}

  // Weather
  try {
    const wx = await api('/api/weather');
    if (wx) loadWeatherConfig(wx);
    const conds = await api('/api/weather/test-conditions');
    if (conds && conds.conditions) buildWeatherTestGrid(conds.conditions, (wx || {}).test_condition);
  } catch (_) {}

  showPanelForMode(data.mode);
}

// ── Mode ──────────────────────────────────────────────────────────────────────

async function setMode(name) {
  const data = await api('/api/mode', 'POST', { mode: name });
  if (data.error) { toast(data.error, false); return; }
  document.getElementById('current-mode').textContent = name;
  document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === name);
  });
  showPanelForMode(name);
  toast(`Mode → ${name}`);
}

function showPanelForMode(mode) {
  ['clock', 'text', 'gameoflife', 'spotify', 'patternflow', 'draw', 'pomodoro', 'workout', 'reminder', 'image', 'library', 'weather'].forEach(m => {
    const el = document.getElementById(`panel-${m}`);
    if (el) el.style.display = (m === mode) ? '' : 'none';
  });
  if (mode === 'image') refreshImagePanel();
  if (mode === 'workout') _pollWorkoutStatus();
}

function buildCarouselModes(modes, cfg) {
  document.getElementById('carousel-enabled').checked = !!cfg.enabled;
  document.getElementById('carousel-skip-spotify').checked = !!cfg.skip_spotify_if_idle;
  const selected = new Set(cfg.modes || modes);
  const durations = cfg.durations || {};
  const wrap = document.getElementById('carousel-modes');
  wrap.innerHTML = '';
  modes.forEach(name => {
    const row = document.createElement('div');
    row.className = 'carousel-row';
    const input = document.createElement('input');
    input.type = 'checkbox';
    input.value = name;
    input.checked = selected.has(name);
    const nameEl = document.createElement('span');
    nameEl.textContent = name;
    const duration = document.createElement('input');
    duration.type = 'number';
    duration.min = '2';
    duration.max = '3600';
    duration.value = durations[name] || cfg.interval || 30;
    duration.dataset.mode = name;
    row.appendChild(input);
    row.appendChild(nameEl);
    row.appendChild(duration);
    wrap.appendChild(row);
  });
}

function buildPomodoroReturnModes(modes, cfg) {
  const select = document.getElementById('pom-return-mode');
  if (!select) return;
  select.innerHTML = '';
  modes.filter(name => name !== 'pomodoro').forEach(name => {
    const option = document.createElement('option');
    option.value = name;
    option.textContent = name;
    select.appendChild(option);
  });
  select.value = cfg.return_after_elapsed_mode || 'clock';
}

async function saveCarousel() {
  const modes = Array.from(document.querySelectorAll('#carousel-modes input:checked')).map(el => el.value);
  const durations = {};
  document.querySelectorAll('#carousel-modes input[type="number"]').forEach(el => {
    durations[el.dataset.mode] = parseInt(el.value) || 30;
  });
  const payload = {
    enabled: document.getElementById('carousel-enabled').checked,
    skip_spotify_if_idle: document.getElementById('carousel-skip-spotify').checked,
    modes,
    durations,
  };
  const data = await api('/api/config/carousel', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  toast('Carousel config saved');
}

function defaultReminder() {
  return {
    id: uid(),
    enabled: true,
    time: '09:00',
    text: 'REMINDER',
    text_color: [255, 255, 255],
    gradient_start: [20, 30, 80],
    gradient_end: [180, 40, 80],
    display_time_s: 10,
  };
}

// ── Reminder palettes ─────────────────────────────────────────────────────────

function renderPaletteList() {
  const list = document.getElementById('palette-list');
  if (!list) return;
  list.innerHTML = '';
  if (!palettes.length) {
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'No palettes yet.';
    list.appendChild(p);
    return;
  }
  palettes.forEach(pal => {
    const row = document.createElement('div');
    row.className = 'palette-row';
    row.dataset.id = pal.id;
    row.innerHTML = [
      '<input type="text" class="pal-name-input" placeholder="Name">',
      '<div class="pal-colors">',
      '  <label title="Text color"><span>T</span><input type="color" class="pal-text-color"></label>',
      '  <label title="Gradient start"><span>A</span><input type="color" class="pal-start-color"></label>',
      '  <label title="Gradient end"><span>B</span><input type="color" class="pal-end-color"></label>',
      '</div>',
      '<button class="pal-action-btn pal-save-btn">Save</button>',
      '<button class="pal-action-btn btn-danger pal-del-btn">Delete</button>',
    ].join('');
    row.querySelector('.pal-name-input').value = pal.name || '';
    row.querySelector('.pal-text-color').value = rgbToHex(pal.text_color || [255, 255, 255]);
    row.querySelector('.pal-start-color').value = rgbToHex(pal.gradient_start || [20, 30, 80]);
    row.querySelector('.pal-end-color').value = rgbToHex(pal.gradient_end || [180, 40, 80]);
    row.querySelector('.pal-save-btn').onclick = () => savePalette(pal.id, row);
    row.querySelector('.pal-del-btn').onclick = () => deletePalette(pal.id);
    list.appendChild(row);
  });
}

function populatePaletteSelects() {
  document.querySelectorAll('.rem-palette-sel').forEach(sel => {
    const cur = sel.value;
    while (sel.options.length > 1) sel.remove(1);
    palettes.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      sel.appendChild(opt);
    });
    sel.value = palettes.find(p => p.id === cur) ? cur : '';
  });
}

async function createPalette() {
  const name = document.getElementById('pal-new-name').value.trim() || 'Palette';
  const payload = {
    name,
    text_color: hexToRgb(document.getElementById('pal-new-text').value),
    gradient_start: hexToRgb(document.getElementById('pal-new-start').value),
    gradient_end: hexToRgb(document.getElementById('pal-new-end').value),
  };
  const data = await api('/api/reminders/palettes', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  palettes = (data.config || {}).palettes || [];
  document.getElementById('pal-new-name').value = '';
  renderPaletteList();
  populatePaletteSelects();
  toast(`Palette "${name}" added`);
}

async function savePalette(id, row) {
  const payload = {
    id,
    name: row.querySelector('.pal-name-input').value.trim() || 'Palette',
    text_color: hexToRgb(row.querySelector('.pal-text-color').value),
    gradient_start: hexToRgb(row.querySelector('.pal-start-color').value),
    gradient_end: hexToRgb(row.querySelector('.pal-end-color').value),
  };
  const data = await api('/api/reminders/palettes', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  palettes = (data.config || {}).palettes || [];
  renderPaletteList();
  populatePaletteSelects();
  toast('Palette saved');
}

async function deletePalette(id) {
  if (!confirm('Delete this palette?')) return;
  const data = await fetch(`/api/reminders/palettes/${id}`, { method: 'DELETE' }).then(r => r.json());
  if (data.error) { toast(data.error, false); return; }
  palettes = (data.config || {}).palettes || [];
  renderPaletteList();
  populatePaletteSelects();
  toast('Palette deleted');
}

function loadReminders(cfg) {
  document.getElementById('reminders-enabled').checked = !!cfg.enabled;
  palettes = (cfg.palettes || []).map(p => ({
    id: p.id || uid(),
    name: p.name || 'Palette',
    text_color: p.text_color || [255, 255, 255],
    gradient_start: p.gradient_start || [20, 30, 80],
    gradient_end: p.gradient_end || [180, 40, 80],
  }));
  reminders = (cfg.items || []).map(item => ({
    id: item.id || uid(),
    enabled: item.enabled !== false,
    time: item.time || '09:00',
    text: item.text || 'REMINDER',
    text_color: item.text_color || [255, 255, 255],
    gradient_start: item.gradient_start || [20, 30, 80],
    gradient_end: item.gradient_end || [180, 40, 80],
    display_time_s: item.display_time_s || 10,
  }));
  renderPaletteList();
  renderReminders();
}

function renderReminders() {
  const list = document.getElementById('reminder-list');
  if (!list) return;
  list.innerHTML = '';
  if (!reminders.length) {
    const empty = document.createElement('p');
    empty.className = 'hint';
    empty.textContent = 'No reminders yet.';
    list.appendChild(empty);
    return;
  }
  reminders.forEach((reminder, index) => {
    const row = document.createElement('div');
    row.className = 'reminder-row';
    row.innerHTML = [
      '<label class="row reminder-toggle"><input type="checkbox" class="rem-enabled"> On</label>',
      '<label>Time<input type="time" class="rem-time"></label>',
      '<label class="rem-text-field">Text<input type="text" class="rem-text" maxlength="60"></label>',
      '<label>Text color<input type="color" class="rem-text-color"></label>',
      '<label>Gradient start<input type="color" class="rem-grad-start"></label>',
      '<label>Gradient end<input type="color" class="rem-grad-end"></label>',
      '<label>Display seconds<input type="number" class="rem-duration" min="1" max="3600"></label>',
      '<button class="btn-danger rem-delete" type="button">Delete</button>',
    ].join('');
    row.querySelector('.rem-enabled').checked = reminder.enabled !== false;
    row.querySelector('.rem-time').value = reminder.time || '09:00';
    row.querySelector('.rem-text').value = reminder.text || '';
    row.querySelector('.rem-text-color').value = rgbToHex(reminder.text_color || [255, 255, 255]);
    row.querySelector('.rem-grad-start').value = rgbToHex(reminder.gradient_start || [20, 30, 80]);
    row.querySelector('.rem-grad-end').value = rgbToHex(reminder.gradient_end || [180, 40, 80]);
    row.querySelector('.rem-duration').value = reminder.display_time_s || 10;
    row.querySelector('.rem-delete').onclick = () => deleteReminder(index);

    // Palette bar
    const palBar = document.createElement('div');
    palBar.className = 'rem-palette-bar';
    const palLabel = document.createElement('span');
    palLabel.className = 'hint';
    palLabel.style.margin = '0';
    palLabel.textContent = 'Palette';
    const palSel = document.createElement('select');
    palSel.className = 'rem-palette-sel';
    palSel.innerHTML = '<option value="">— load —</option>';
    palettes.forEach(p => {
      const opt = document.createElement('option');
      opt.value = p.id;
      opt.textContent = p.name;
      palSel.appendChild(opt);
    });
    palSel.addEventListener('change', () => {
      if (!palSel.value) return;
      const pal = palettes.find(p => p.id === palSel.value);
      if (pal) {
        row.querySelector('.rem-text-color').value = rgbToHex(pal.text_color || [255, 255, 255]);
        row.querySelector('.rem-grad-start').value = rgbToHex(pal.gradient_start || [20, 30, 80]);
        row.querySelector('.rem-grad-end').value = rgbToHex(pal.gradient_end || [180, 40, 80]);
      }
      palSel.value = '';
    });
    const clearBtn = document.createElement('button');
    clearBtn.className = 'rem-clear-btn';
    clearBtn.type = 'button';
    clearBtn.textContent = 'Clear';
    clearBtn.onclick = () => {
      row.querySelector('.rem-text-color').value = '#ffffff';
      row.querySelector('.rem-grad-start').value = '#141e50';
      row.querySelector('.rem-grad-end').value = '#b42850';
    };
    palBar.appendChild(palLabel);
    palBar.appendChild(palSel);
    palBar.appendChild(clearBtn);
    row.appendChild(palBar);
    list.appendChild(row);
  });
}

function collectReminders() {
  const rows = Array.from(document.querySelectorAll('#reminder-list .reminder-row'));
  reminders = rows.map((row, index) => ({
    id: reminders[index]?.id || uid(),
    enabled: row.querySelector('.rem-enabled').checked,
    time: row.querySelector('.rem-time').value || '09:00',
    text: row.querySelector('.rem-text').value.trim() || 'REMINDER',
    text_color: hexToRgb(row.querySelector('.rem-text-color').value),
    gradient_start: hexToRgb(row.querySelector('.rem-grad-start').value),
    gradient_end: hexToRgb(row.querySelector('.rem-grad-end').value),
    display_time_s: Math.max(1, parseInt(row.querySelector('.rem-duration').value) || 10),
  }));
}

function addReminder() {
  collectReminders();
  reminders.push(defaultReminder());
  renderReminders();
}

function deleteReminder(index) {
  collectReminders();
  reminders.splice(index, 1);
  renderReminders();
}

async function saveReminders() {
  collectReminders();
  const payload = {
    enabled: document.getElementById('reminders-enabled').checked,
    items: reminders,
    palettes,
  };
  const data = await api('/api/config/reminders', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  loadReminders(data.config || payload);
  toast('Reminders saved');
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

  const as = document.getElementById('sp-artist-speed');
  const av = document.getElementById('sp-artist-speed-val');
  as.addEventListener('input', () => av.textContent = as.value);

  const ss = document.getElementById('sp-track-speed');
  const sv = document.getElementById('sp-track-speed-val');
  ss.addEventListener('input', () => sv.textContent = ss.value);

  const ds = document.getElementById('draw-scroll-speed');
  const dv = document.getElementById('draw-scroll-speed-val');
  ds.addEventListener('input', () => dv.textContent = ds.value);

  const nb = document.getElementById('night-brightness');
  const nv = document.getElementById('night-brightness-val');
  nb?.addEventListener('input', () => nv.textContent = nb.value);
  document.getElementById('draw-width').addEventListener('change', resizeDrawCanvas);

  ensurePfOptions();
  document.getElementById('pf-show-fps')?.addEventListener('change', savePfOptions);
  document.getElementById('pf-donut-fast')?.addEventListener('change', savePfOptions);
  document.getElementById('pf-fast-image')?.addEventListener('change', savePfOptions);
  init();
});

window.addEventListener('resize', () => setupDrawCanvas());

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
    source: document.getElementById('text-source').value,
    content: document.getElementById('text-content').value,
    url: document.getElementById('text-url').value.trim(),
    poll_interval: parseInt(document.getElementById('text-poll-interval').value),
    color: hexToRgb(document.getElementById('text-color').value),
    speed: parseInt(document.getElementById('text-speed').value),
    scroll_direction: document.getElementById('text-scroll-mode').value,
  };
  const data = await api('/api/text', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  // Switch mode button to text
  document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
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
    callback_path: document.getElementById('sp-callback-path').value.trim() || '/callback',
  };
  const secret = document.getElementById('sp-client-secret').value.trim();
  if (secret) payload.client_secret = secret;

  const data = await api('/api/config/spotify', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  toast('Spotify credentials saved');
}

async function saveSpotifyDisplay() {
  const payload = {
    artist_speed: parseInt(document.getElementById('sp-artist-speed').value),
    track_speed: parseInt(document.getElementById('sp-track-speed').value),
  };
  const data = await api('/api/config/spotify', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  toast('Spotify display saved');
}

async function authorizeSpotify() {
  const data = await api('/api/spotify/auth_url');
  if (data.error) { toast(data.error, false); return; }
  window.open(data.url, '_blank');
}

// ── Patternflow ───────────────────────────────────────────────────────────────

// Draw

function setupDrawCanvas() {
  const canvas = document.getElementById('draw-canvas');
  if (!canvas) return;
  const wrap = canvas.parentElement;
  const available = Math.max(320, wrap ? wrap.clientWidth - 2 : 512);
  DRAW_SCALE = Math.max(4, Math.min(10, Math.floor(available / 64)));
  canvas.width = drawCanvasWidth * DRAW_SCALE;
  canvas.height = DRAW_H * DRAW_SCALE;
  canvas.onmousedown = e => { drawMouseDown = true; paintDrawEvent(e); };
  canvas.onmousemove = e => { if (drawMouseDown) paintDrawEvent(e); };
  canvas.onmouseup = () => { drawMouseDown = false; };
  canvas.onmouseleave = () => { drawMouseDown = false; };
  canvas.ontouchstart = e => { e.preventDefault(); drawMouseDown = true; paintDrawEvent(e.touches[0]); };
  canvas.ontouchmove = e => { e.preventDefault(); if (drawMouseDown) paintDrawEvent(e.touches[0]); };
  canvas.ontouchend = () => { drawMouseDown = false; };
  renderDrawCanvas();
}

function loadDrawConfig(cfg) {
  drawCanvasWidth = Math.max(64, Math.min(512, parseInt(cfg.width || 64)));
  document.getElementById('draw-width').value = drawCanvasWidth;
  document.getElementById('draw-scroll').checked = !!cfg.scroll;
  document.getElementById('draw-scroll-speed').value = cfg.scroll_speed || 20;
  document.getElementById('draw-scroll-speed-val').textContent = cfg.scroll_speed || 20;
  drawPixels = new Map();
  (cfg.pixels || []).forEach(p => {
    if (p.x >= 0 && p.x < drawCanvasWidth && p.y >= 0 && p.y < DRAW_H) {
      drawPixels.set(`${p.x},${p.y}`, rgbKey(p.color || [255, 255, 255]));
    }
  });
  setupDrawCanvas();
}

function renderDrawCanvas() {
  const canvas = document.getElementById('draw-canvas');
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  drawPixels.forEach((color, key) => {
    const [x, y] = key.split(',').map(Number);
    ctx.fillStyle = `rgb(${color})`;
    ctx.fillRect(x * DRAW_SCALE, y * DRAW_SCALE, DRAW_SCALE, DRAW_SCALE);
  });
  ctx.strokeStyle = 'rgba(255,255,255,0.08)';
  ctx.lineWidth = 1;
  for (let x = 0; x <= drawCanvasWidth; x++) {
    ctx.beginPath();
    ctx.moveTo(x * DRAW_SCALE + 0.5, 0);
    ctx.lineTo(x * DRAW_SCALE + 0.5, canvas.height);
    ctx.stroke();
  }
  for (let y = 0; y <= DRAW_H; y++) {
    ctx.beginPath();
    ctx.moveTo(0, y * DRAW_SCALE + 0.5);
    ctx.lineTo(canvas.width, y * DRAW_SCALE + 0.5);
    ctx.stroke();
  }
}

function paintDrawEvent(e) {
  const canvas = document.getElementById('draw-canvas');
  const rect = canvas.getBoundingClientRect();
  const x = Math.floor((e.clientX - rect.left) / rect.width * drawCanvasWidth);
  const y = Math.floor((e.clientY - rect.top) / rect.height * DRAW_H);
  if (x < 0 || x >= drawCanvasWidth || y < 0 || y >= DRAW_H) return;
  if (drawTool === 'eraser') {
    drawPixels.delete(`${x},${y}`);
  } else {
    drawPixels.set(`${x},${y}`, rgbKey(hexToRgb(document.getElementById('draw-color').value)));
  }
  renderDrawCanvas();
}

function setDrawTool(tool) {
  drawTool = tool;
  document.getElementById('draw-tool-pen').classList.toggle('active', tool === 'pen');
  document.getElementById('draw-tool-eraser').classList.toggle('active', tool === 'eraser');
}

function resizeDrawCanvas() {
  const nextWidth = Math.max(64, Math.min(512, parseInt(document.getElementById('draw-width').value) || 64));
  drawCanvasWidth = nextWidth;
  document.getElementById('draw-width').value = nextWidth;
  drawPixels.forEach((_, key) => {
    const x = parseInt(key.split(',')[0], 10);
    if (x >= drawCanvasWidth) drawPixels.delete(key);
  });
  setupDrawCanvas();
}

function adjustDrawWidth(delta) {
  document.getElementById('draw-width').value = drawCanvasWidth + delta;
  resizeDrawCanvas();
}

function clearDraw() {
  if (!confirm('Clear the drawing?')) return;
  drawPixels.clear();
  renderDrawCanvas();
}

function placeDrawText() {
  const text = document.getElementById('draw-text').value;
  if (!text) return;
  const x = Math.max(0, parseInt(document.getElementById('draw-text-x').value) || 0);
  const y = Math.max(0, Math.min(31, parseInt(document.getElementById('draw-text-y').value) || 0));
  const color = rgbKey(hexToRgb(document.getElementById('draw-color').value));
  const tmp = document.createElement('canvas');
  tmp.width = drawCanvasWidth;
  tmp.height = DRAW_H;
  const ctx = tmp.getContext('2d');
  ctx.fillStyle = '#fff';
  ctx.font = '8px monospace';
  ctx.textBaseline = 'top';
  ctx.fillText(text, x, y);
  const data = ctx.getImageData(0, 0, drawCanvasWidth, DRAW_H).data;
  for (let py = 0; py < DRAW_H; py++) {
    for (let px = 0; px < drawCanvasWidth; px++) {
      if (data[(py * drawCanvasWidth + px) * 4 + 3] > 0) {
        drawPixels.set(`${px},${py}`, color);
      }
    }
  }
  renderDrawCanvas();
}

async function saveDraw() {
  const pixels = Array.from(drawPixels.entries()).map(([key, color]) => {
    const [x, y] = key.split(',').map(Number);
    return { x, y, color: keyRgb(color) };
  });
  const payload = {
    width: drawCanvasWidth,
    scroll: document.getElementById('draw-scroll').checked,
    scroll_speed: parseInt(document.getElementById('draw-scroll-speed').value),
    pixels,
  };
  const data = await api('/api/draw', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === 'draw');
  });
  document.getElementById('current-mode').textContent = 'draw';
  toast('Drawing saved');
}

async function savePomodoro() {
  const payload = {
    gradient_start: hexToRgb(document.getElementById('pom-gradient-start').value),
    gradient_end: hexToRgb(document.getElementById('pom-gradient-end').value),
    background_color: hexToRgb(document.getElementById('pom-background').value),
    elapsed_background: hexToRgb(document.getElementById('pom-elapsed-background').value),
    text_color: hexToRgb(document.getElementById('pom-text-color').value),
    tick_pixel_color: hexToRgb(document.getElementById('pom-tick-pixel-color').value),
    flash_red: document.getElementById('pom-flash-red').checked,
    tick_pixel_enabled: document.getElementById('pom-tick-pixel-enabled').checked,
    flash_threshold_ms: (parseInt(document.getElementById('pom-flash-threshold').value) || 5) * 1000,
    return_after_elapsed_enabled: document.getElementById('pom-return-enabled').checked,
    return_after_elapsed_delay_s: Math.max(0, parseInt(document.getElementById('pom-return-delay').value) || 0),
    return_after_elapsed_mode: document.getElementById('pom-return-mode').value || 'clock',
  };
  const data = await api('/api/config/pomodoro', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  toast('Pomodoro config saved');
}

// ── Workout ───────────────────────────────────────────────────────────────────

let _workoutCfg = {
  tabata: { work_s: 20, rest_s: 10, rounds: 8 },
  hiit:   { work_s: 30, rest_s: 15, rounds: 10 },
};
let _workoutType = 'tabata';
let _workoutPaused = false;
let _workoutActive = false;
let _workoutPollTimer = null;

function selectWorkoutType(type) {
  _workoutType = type;
  document.getElementById('workout-section-tabata').style.display = type === 'tabata' ? '' : 'none';
  document.getElementById('workout-section-hiit').style.display  = type === 'hiit'   ? '' : 'none';
  document.getElementById('workout-tab-tabata').classList.toggle('active', type === 'tabata');
  document.getElementById('workout-tab-hiit').classList.toggle('active', type === 'hiit');
}

function stepWorkout(type, key, delta) {
  const limits = { work_s: [5, 999], rest_s: [0, 999], rounds: [1, 99] };
  const [mn, mx] = limits[key] || [1, 999];
  _workoutCfg[type][key] = Math.max(mn, Math.min(mx, (_workoutCfg[type][key] || 0) + delta));
  const idMap = { work_s: 'work', rest_s: 'rest', rounds: 'rounds' };
  const el = document.getElementById(`workout-${type}-${idMap[key]}`);
  if (el) el.textContent = _workoutCfg[type][key];
}

function _refreshWorkoutDisplay() {
  document.getElementById('workout-hiit-work').textContent   = _workoutCfg.hiit.work_s;
  document.getElementById('workout-hiit-rest').textContent   = _workoutCfg.hiit.rest_s;
  document.getElementById('workout-hiit-rounds').textContent = _workoutCfg.hiit.rounds;
}

async function startWorkout(type) {
  const data = await api('/api/workout', 'POST', {
    action: 'start', workout_type: type,
    work_s: 20, rest_s: 10, rounds: 8,
  });
  if (data.error) { toast(data.error, false); return; }
  _workoutPaused = false;
  _workoutActive = true;
  _workoutType = type;
  selectWorkoutType(type);
  _setWorkoutActive(true);
  if (document.getElementById('current-mode').textContent !== 'workout') {
    document.getElementById('current-mode').textContent = 'workout';
    document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === 'workout');
    });
    showPanelForMode('workout');
  }
  toast('Workout started — 10s get ready!');
  _startWorkoutPoll();
}

async function startCustomWorkout(type) {
  const cfg = _workoutCfg[type];
  const data = await api('/api/workout', 'POST', {
    action: 'start', workout_type: type,
    work_s: cfg.work_s, rest_s: cfg.rest_s, rounds: cfg.rounds,
  });
  if (data.error) { toast(data.error, false); return; }
  _workoutPaused = false;
  _workoutActive = true;
  _workoutType = type;
  _setWorkoutActive(true);
  if (document.getElementById('current-mode').textContent !== 'workout') {
    document.getElementById('current-mode').textContent = 'workout';
    document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.mode === 'workout');
    });
    showPanelForMode('workout');
  }
  toast('Workout started — 10s get ready!');
  _startWorkoutPoll();
}

async function toggleWorkoutPause() {
  const action = _workoutPaused ? 'resume' : 'pause';
  const data = await api('/api/workout', 'POST', { action });
  if (data.error) { toast(data.error, false); return; }
  _workoutPaused = !_workoutPaused;
  const btn = document.getElementById('workout-btn-pause');
  if (btn) btn.innerHTML = _workoutPaused ? '&#9654; Resume' : '&#9646;&#9646; Pause';
  toast(_workoutPaused ? 'Paused' : 'Resumed');
}

async function stopWorkout() {
  const data = await api('/api/workout', 'POST', { action: 'stop' });
  if (data.error) { toast(data.error, false); return; }
  _workoutActive = false;
  _workoutPaused = false;
  _setWorkoutActive(false);
  _stopWorkoutPoll();
  toast('Workout stopped');
}

function _setWorkoutActive(active) {
  const ctrl = document.getElementById('workout-active-controls');
  if (ctrl) ctrl.style.display = active ? '' : 'none';
  if (!active) {
    const status = document.getElementById('workout-status');
    if (status) status.innerHTML = '';
    const btn = document.getElementById('workout-btn-pause');
    if (btn) btn.innerHTML = '&#9646;&#9646; Pause';
  }
}

function _startWorkoutPoll() {
  _stopWorkoutPoll();
  _workoutPollTimer = setInterval(_pollWorkoutStatus, 1000);
}

function _stopWorkoutPoll() {
  if (_workoutPollTimer) { clearInterval(_workoutPollTimer); _workoutPollTimer = null; }
}

async function _pollWorkoutStatus() {
  const data = await api('/api/workout').catch(() => null);
  if (!data) return;
  const ph = data.phase || 'idle';
  if (ph === 'idle') { _setWorkoutActive(false); _stopWorkoutPoll(); return; }

  _workoutPaused = !!data.paused;
  const btn = document.getElementById('workout-btn-pause');
  if (btn) btn.innerHTML = _workoutPaused ? '&#9654; Resume' : '&#9646;&#9646; Pause';

  const phaseClass = { work: 'ws-work', rest: 'ws-rest', getready: 'ws-ready', done: 'ws-done', cooldown: 'ws-done' };
  const phaseLabel = { work: 'WORK', rest: 'REST', getready: 'GET READY', done: 'DONE!', cooldown: 'COOLDOWN' };
  const cls = phaseClass[ph] || '';
  const lbl = phaseLabel[ph] || ph.toUpperCase();
  const tl = Math.ceil(data.time_left || 0);
  const roundInfo = ph !== 'getready' && ph !== 'done' && ph !== 'cooldown'
    ? `Round ${data.round || 0} / ${data.total_rounds || 0}`
    : '';
  const pauseTag = data.paused ? ' <span class="ws-pause">[PAUSED]</span>' : '';
  const status = document.getElementById('workout-status');
  if (status) {
    status.innerHTML = `<span class="ws-phase ${cls}">${lbl}</span>${tl > 0 ? ` &mdash; ${tl}s` : ''}${roundInfo ? ' &mdash; ' + roundInfo : ''}${pauseTag}`;
  }

  if (ph === 'done' || ph === 'cooldown') {
    _setWorkoutActive(false);
    _stopWorkoutPoll();
    _workoutActive = false;
  }
}

function ensurePfOptions() {
  if (document.getElementById('pf-show-fps') &&
      document.getElementById('pf-donut-fast') &&
      document.getElementById('pf-fast-image')) return;
  const panel = document.getElementById('panel-patternflow');
  const patternButtons = document.getElementById('pf-pattern-buttons');
  if (!panel || !patternButtons) return;

  const wrap = document.createElement('div');
  wrap.className = 'pf-options';
  wrap.innerHTML = [
    '<label><input type="checkbox" id="pf-show-fps"> Show FPS</label>',
    '<label><input type="checkbox" id="pf-donut-fast"> Donut fast render</label>',
    '<label><input type="checkbox" id="pf-fast-image"> Fast image push</label>',
  ].join('');
  panel.insertBefore(wrap, patternButtons);
  document.getElementById('pf-show-fps')?.addEventListener('change', savePfOptions);
  document.getElementById('pf-donut-fast')?.addEventListener('change', savePfOptions);
  document.getElementById('pf-fast-image')?.addEventListener('change', savePfOptions);
}

function loadPfPatterns(names, activeIdx, knobLabels, extraButtonLabels) {
  ensurePfOptions();
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
  buildPfKnobs(knobLabels, extraButtonLabels);
}

function buildPfKnobs(labels, extraButtonLabels) {
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

  (extraButtonLabels || []).forEach((label, i) => {
    const num = document.createElement('span');
    num.className = 'pf-k-num';
    num.textContent = `B${i + 1}`;

    const name = document.createElement('span');
    name.className = 'pf-k-name';
    name.textContent = label;

    const btns = document.createElement('div');
    btns.className = 'pf-k-btns';

    const b = document.createElement('button');
    b.className = 'pf-btn pf-btn-action';
    b.textContent = 'Press';
    b.title = label;
    b.onclick = () => pfBtn(4 + i);
    btns.appendChild(b);

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

function syncPfOptions(data) {
  ensurePfOptions();
  const fps = document.getElementById('pf-show-fps');
  const fast = document.getElementById('pf-donut-fast');
  const image = document.getElementById('pf-fast-image');
  if (fps) fps.checked = !!data.show_fps;
  if (fast) fast.checked = !!data.donut_fast_render;
  if (image) image.checked = data.fast_image_push !== false;
}

async function savePfOptions() {
  const show_fps = !!document.getElementById('pf-show-fps')?.checked;
  const donut_fast_render = !!document.getElementById('pf-donut-fast')?.checked;
  const fast_image_push = !!document.getElementById('pf-fast-image')?.checked;
  const data = await api('/api/patternflow/options', 'POST', { show_fps, donut_fast_render, fast_image_push });
  if (data.error) { toast(data.error, false); return; }
  syncPfOptions(data);
}

async function setPfPattern(idx, name, allNames, prevLabels) {
  const data = await api('/api/patternflow/pattern', 'POST', { index: idx });
  if (data.error) { toast(data.error, false); return; }

  document.querySelectorAll('#pf-pattern-buttons .mode-btn').forEach((b, i) => {
    b.classList.toggle('active', i === idx);
  });
  buildPfKnobs(data.knob_labels || prevLabels, data.extra_button_labels || []);
  syncPfOptions(data);

  document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === 'patternflow');
  });
  document.getElementById('current-mode').textContent = 'patternflow';
  showPanelForMode('patternflow');
  toast(`Pattern → ${name}`);
}

// ── Screen & Night Mode ───────────────────────────────────────────────────────

function updateScreenBtn() {
  const btn = document.getElementById('btn-screen');
  if (!btn) return;
  btn.classList.toggle('is-on', _screenOn);
  btn.classList.toggle('is-off', !_screenOn);
  btn.title = _screenOn ? 'Turn screen off' : 'Turn screen on';
}

function updateNightBtn() {
  const btn = document.getElementById('btn-night');
  if (!btn) return;
  btn.classList.toggle('is-active', _nightModeEnabled);
  btn.title = _nightModeEnabled ? 'Night mode on — click to disable' : 'Night mode off — click to enable';
}

async function toggleScreen() {
  const data = await api('/api/screen', 'POST', { on: !_screenOn });
  if (data.error) { toast(data.error, false); return; }
  _screenOn = data.screen_on;
  updateScreenBtn();
  toast(_screenOn ? 'Screen on' : 'Screen off');
}

async function toggleNightMode() {
  document.getElementById('night-enabled').checked = !_nightModeEnabled;
  await saveNightMode();
}

async function saveNightMode() {
  const payload = {
    enabled: document.getElementById('night-enabled').checked,
    brightness: parseInt(document.getElementById('night-brightness').value) || 20,
    start: document.getElementById('night-start').value || '22:00',
    end: document.getElementById('night-end').value || '05:00',
  };
  const data = await api('/api/config/night_mode', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  _nightModeEnabled = payload.enabled;
  updateNightBtn();
  toast(payload.enabled ? 'Night mode enabled' : 'Night mode disabled');
}

// ── System ────────────────────────────────────────────────────────────────────

async function restartService() {
  if (!confirm('Restart the LED Matrix service?')) return;
  await api('/api/restart', 'POST');
  toast('Service restarting…');
}

async function stopService() {
  if (!confirm('Stop the LED Matrix service? The web UI will go offline until you start it again from SSH.')) return;
  await api('/api/service/stop', 'POST');
  toast('Service stopping...');
}

async function disableAutostart() {
  if (!confirm('Disable LED Matrix autostart after reboot? The current service will keep running.')) return;
  const data = await api('/api/service/disable', 'POST');
  if (data.error) { toast(data.error, false); return; }
  toast('Autostart disabled');
}

async function confirmShutdown() {
  if (!confirm('Shut down the Raspberry Pi?')) return;
  await api('/api/shutdown', 'POST');
  toast('Shutting down…');
}

// ── Image mode ────────────────────────────────────────────────────────────────

let _imgEl = null;
let _imgFile = null;
let _imgIsGif = false;
let _imgAnimFrame = null;
let _imgZoom = 1.0;
let _imgPanX = 0.5;
let _imgPanY = 0.5;
let _imgDragging = false;
let _imgDragStart = null;
let _imgHasImage = false;

async function refreshImagePanel() {
  const data = await api('/api/image').catch(() => null);
  _imgHasImage = data?.has_image || false;
  const wrap = document.getElementById('img-current-wrap');
  if (wrap) wrap.style.display = _imgHasImage ? '' : 'none';
  if (_imgHasImage) {
    const preview = document.getElementById('img-current-preview');
    if (preview) {
      const src = data.is_gif ? '/static/matrix_image.gif' : '/static/matrix_image.png';
      preview.src = src + '?t=' + Date.now();
    }
  }
}

function _imgCropGeometry() {
  if (!_imgEl) return null;
  const sw = _imgEl.naturalWidth;
  const sh = _imgEl.naturalHeight;
  const srcAspect = sw / sh;
  let baseCropW, baseCropH;
  if (srcAspect > 2) {
    baseCropH = sh;
    baseCropW = sh * 2;
  } else {
    baseCropW = sw;
    baseCropH = sw / 2;
  }
  const cropW = baseCropW / _imgZoom;
  const cropH = baseCropH / _imgZoom;
  const maxX = Math.max(0, sw - cropW);
  const maxY = Math.max(0, sh - cropH);
  const ox = _imgPanX * maxX;
  const oy = _imgPanY * maxY;
  return { sw, sh, cropW, cropH, maxX, maxY, ox, oy };
}

function renderCropCanvas() {
  const canvas = document.getElementById('img-crop-canvas');
  if (!canvas || !_imgEl) return;
  const g = _imgCropGeometry();
  if (!g) return;
  const ctx = canvas.getContext('2d');
  ctx.clearRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(_imgEl, g.ox, g.oy, g.cropW, g.cropH, 0, 0, canvas.width, canvas.height);
}

function _setupCropCanvas() {
  const canvas = document.getElementById('img-crop-canvas');
  if (!canvas) return;
  const wrap = canvas.parentElement;
  const w = Math.min(480, wrap ? wrap.clientWidth - 2 : 320);
  canvas.width = w;
  canvas.height = Math.round(w / 2);

  canvas.onmousedown = e => {
    _imgDragging = true;
    _imgDragStart = { x: e.clientX, y: e.clientY, panX: _imgPanX, panY: _imgPanY };
  };
  canvas.onmousemove = e => { if (_imgDragging) _imgDoDrag(e.clientX, e.clientY, canvas); };
  canvas.onmouseup = () => { _imgDragging = false; };
  canvas.onmouseleave = () => { _imgDragging = false; };
  canvas.ontouchstart = e => {
    e.preventDefault();
    _imgDragging = true;
    const t = e.touches[0];
    _imgDragStart = { x: t.clientX, y: t.clientY, panX: _imgPanX, panY: _imgPanY };
  };
  canvas.ontouchmove = e => {
    e.preventDefault();
    if (_imgDragging) _imgDoDrag(e.touches[0].clientX, e.touches[0].clientY, canvas);
  };
  canvas.ontouchend = () => { _imgDragging = false; };
  renderCropCanvas();
}

function _imgDoDrag(cx, cy, canvas) {
  if (!_imgDragStart || !_imgEl) return;
  const g = _imgCropGeometry();
  if (!g) return;
  const rect = canvas.getBoundingClientRect();
  const dx = cx - _imgDragStart.x;
  const dy = cy - _imgDragStart.y;
  const dxSrc = -dx * (g.cropW / rect.width);
  const dySrc = -dy * (g.cropH / rect.height);
  _imgPanX = Math.max(0, Math.min(1, _imgDragStart.panX + (g.maxX > 0 ? dxSrc / g.maxX : 0)));
  _imgPanY = Math.max(0, Math.min(1, _imgDragStart.panY + (g.maxY > 0 ? dySrc / g.maxY : 0)));
  renderCropCanvas();
}

function _startCropAnimation() {
  _stopCropAnimation();
  const loop = () => { renderCropCanvas(); _imgAnimFrame = requestAnimationFrame(loop); };
  _imgAnimFrame = requestAnimationFrame(loop);
}

function _stopCropAnimation() {
  if (_imgAnimFrame !== null) { cancelAnimationFrame(_imgAnimFrame); _imgAnimFrame = null; }
}

function onImageSelected(e) {
  const file = e.target.files[0];
  if (!file) return;
  _stopCropAnimation();
  _imgFile = file;
  _imgIsGif = file.type === 'image/gif';
  const url = URL.createObjectURL(file);
  const img = new Image();
  img.onload = () => {
    _imgEl = img;
    _imgZoom = 1.0;
    _imgPanX = 0.5;
    _imgPanY = 0.5;
    document.getElementById('img-zoom').value = 100;
    document.getElementById('img-zoom-val').textContent = '100';
    const wrap = document.getElementById('img-crop-wrap');
    if (wrap) wrap.style.display = '';
    _setupCropCanvas();
    if (_imgIsGif) _startCropAnimation();
  };
  img.src = url;
}

async function uploadImage() {
  if (!_imgEl || !_imgFile) return;
  const g = _imgCropGeometry();
  if (!g) return;

  const form = new FormData();
  if (_imgIsGif) {
    form.append('file', _imgFile, _imgFile.name);
    form.append('ox', Math.round(g.ox));
    form.append('oy', Math.round(g.oy));
    form.append('cropW', Math.round(g.cropW));
    form.append('cropH', Math.round(g.cropH));
  } else {
    const off = document.createElement('canvas');
    off.width = 64; off.height = 32;
    off.getContext('2d').drawImage(_imgEl, g.ox, g.oy, g.cropW, g.cropH, 0, 0, 64, 32);
    const blob = await new Promise(res => off.toBlob(res, 'image/png'));
    form.append('file', blob, 'image.png');
  }

  let data;
  try {
    const r = await fetch('/api/image/upload', { method: 'POST', body: form });
    data = await r.json();
  } catch {
    toast('Upload failed', false);
    return;
  }
  if (data.error) { toast(data.error, false); return; }

  _stopCropAnimation();
  _imgEl = null; _imgFile = null; _imgIsGif = false;
  document.getElementById('img-file').value = '';
  document.getElementById('img-crop-wrap').style.display = 'none';
  _imgHasImage = true;
  refreshImagePanel();
  document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === 'image');
  });
  document.getElementById('current-mode').textContent = 'image';
  toast('Image uploaded!');
}

// ── Library ───────────────────────────────────────────────────────────────────

let _libraryItems = [];

function renderLibraryList() {
  const list = document.getElementById('lib-list');
  if (!list) return;
  list.innerHTML = '';
  if (!_libraryItems.length) {
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'No items yet. Add images or drawings using the "Save to Library" buttons.';
    list.appendChild(p);
    return;
  }
  _libraryItems.forEach(item => {
    const row = document.createElement('div');
    row.className = 'lib-item-row';
    row.dataset.id = item.id;
    row.innerHTML = [
      '<img class="lib-thumb" alt="">',
      '<div class="lib-item-meta">',
      '  <input type="text" class="lib-name-input" placeholder="Name">',
      '  <div class="lib-duration-row">Duration <input type="number" class="lib-duration-input" min="1" max="3600"> s</div>',
      '  <span class="lib-item-source"></span>',
      '</div>',
      '<div class="lib-item-actions">',
      '  <button class="lib-btn-display">Display</button>',
      '  <button class="btn-danger lib-btn-remove">Remove</button>',
      '</div>',
    ].join('');
    row.querySelector('.lib-thumb').src = `/static/library/${item.filename}`;
    row.querySelector('.lib-name-input').value = item.name || '';
    row.querySelector('.lib-duration-input').value = item.duration || 10;
    row.querySelector('.lib-item-source').textContent = item.source || '';
    row.querySelector('.lib-btn-display').onclick = () => setMode('library');
    row.querySelector('.lib-btn-remove').onclick = () => deleteLibraryItem(item.id);
    list.appendChild(row);
  });
}

async function saveLibraryConfig() {
  const rows = document.querySelectorAll('#lib-list .lib-item-row');
  const itemUpdates = Array.from(rows).map(row => ({
    id: row.dataset.id,
    name: row.querySelector('.lib-name-input').value.trim() || 'Item',
    duration: Math.max(1, parseInt(row.querySelector('.lib-duration-input').value) || 10),
  }));
  const payload = {
    rotation_enabled: document.getElementById('lib-rotation').checked,
    interval: Math.max(1, parseInt(document.getElementById('lib-interval').value) || 10),
    items: itemUpdates,
  };
  const data = await api('/api/library/config', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  _libraryItems = (data.config || {}).items || [];
  renderLibraryList();
  toast('Library settings saved');
}

async function deleteLibraryItem(id) {
  if (!confirm('Remove this item from the library?')) return;
  const data = await fetch(`/api/library/${id}`, { method: 'DELETE' }).then(r => r.json());
  if (data.error) { toast(data.error, false); return; }
  _libraryItems = (data.config || {}).items || [];
  renderLibraryList();
  toast('Item removed');
}

async function addImageToLibrary() {
  const name = document.getElementById('lib-img-name').value.trim() || 'Image';
  const data = await api('/api/library/add/image', 'POST', { name });
  if (data.error) { toast(data.error, false); return; }
  document.getElementById('lib-img-name').value = '';
  _libraryItems = (data.config || {}).items || [];
  renderLibraryList();
  toast(`"${data.item?.name || name}" saved to library`);
}

async function addDrawToLibrary() {
  const name = document.getElementById('lib-draw-name').value.trim() || 'Drawing';
  const data = await api('/api/library/add/draw', 'POST', { name });
  if (data.error) { toast(data.error, false); return; }
  document.getElementById('lib-draw-name').value = '';
  _libraryItems = (data.config || {}).items || [];
  renderLibraryList();
  toast(`"${data.item?.name || name}" saved to library`);
}

// ── Settings export / import ──────────────────────────────────────────────────

function exportSettings() {
  window.location.href = '/api/config/export';
}

async function importSettings(e) {
  const file = e.target.files[0];
  if (!file) return;
  let parsed;
  try {
    parsed = JSON.parse(await file.text());
  } catch {
    toast('Invalid JSON file', false);
    e.target.value = '';
    return;
  }
  const data = await api('/api/config/import', 'POST', parsed);
  e.target.value = '';
  if (data.error) { toast(data.error, false); return; }
  toast('Settings imported — reloading…');
  setTimeout(() => location.reload(), 1200);
}

async function clearImage() {
  if (!confirm('Remove this image from the matrix?')) return;
  const r = await fetch('/api/image', { method: 'DELETE' });
  const data = await r.json();
  if (data.error) { toast(data.error, false); return; }
  _stopCropAnimation();
  _imgHasImage = false;
  document.getElementById('img-current-wrap').style.display = 'none';
  document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === 'clock');
  });
  document.getElementById('current-mode').textContent = 'clock';
  showPanelForMode('clock');
  toast('Image removed');
}

// ── Weather ───────────────────────────────────────────────────────────────────

let _wxCities = [];
let _wxTestCondition = '';

const WX_CONDITION_LABELS = {
  clear_day:     'Clear Day ☀️',
  clear_night:   'Clear Night 🌙',
  partly_cloudy: 'Partly Cloudy ⛅',
  cloudy:        'Overcast ☁️',
  drizzle:       'Drizzle 🌦️',
  rain:          'Rain 🌧️',
  thunderstorm:  'Storm ⛈️',
  snow:          'Snow 🌨️',
  fog:           'Fog 🌫️',
  extreme_hot:   'Extreme Hot 🔥',
  extreme_cold:  'Extreme Cold 🧊',
};

function loadWeatherConfig(cfg) {
  document.getElementById('wx-api-key').value = cfg.api_key || '';
  document.getElementById('wx-units').value = cfg.units || 'metric';
  document.getElementById('wx-refresh').value = cfg.refresh_interval || 600;
  document.getElementById('wx-city-interval').value = cfg.city_interval || 30;
  document.getElementById('wx-show-city').checked = cfg.show_city_name !== false;
  _wxCities = cfg.cities || [];
  _wxTestCondition = cfg.test_condition || '';
  renderWeatherCities();
}

function renderWeatherCities() {
  const list = document.getElementById('wx-city-list');
  if (!list) return;
  list.innerHTML = '';
  if (!_wxCities.length) {
    const p = document.createElement('p');
    p.className = 'hint';
    p.textContent = 'No cities added yet.';
    list.appendChild(p);
    return;
  }
  _wxCities.forEach(city => {
    const row = document.createElement('div');
    row.className = 'wx-city-row';
    const name = document.createElement('span');
    name.className = 'wx-city-name';
    name.textContent = city.name;
    if (city.lat !== undefined) {
      name.textContent += ` (${city.lat.toFixed(2)}, ${city.lon.toFixed(2)})`;
    }
    const del = document.createElement('button');
    del.className = 'btn-danger';
    del.textContent = '×';
    del.onclick = () => deleteWeatherCity(city.id);
    row.appendChild(name);
    row.appendChild(del);
    list.appendChild(row);
  });
}

async function saveWeatherSettings() {
  const payload = {
    api_key: document.getElementById('wx-api-key').value.trim(),
    units: document.getElementById('wx-units').value,
    refresh_interval: Math.max(60, parseInt(document.getElementById('wx-refresh').value) || 600),
    city_interval: Math.max(5, parseInt(document.getElementById('wx-city-interval').value) || 30),
    show_city_name: document.getElementById('wx-show-city').checked,
  };
  const data = await api('/api/weather/settings', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  toast('Weather settings saved');
}

async function addWeatherCity() {
  const input = document.getElementById('wx-new-city');
  const val = input.value.trim();
  if (!val) { toast('Enter a city name or OWM ID', false); return; }
  const payload = /^\d+$/.test(val) ? { owm_id: parseInt(val, 10) } : { name: val };
  const data = await api('/api/weather/cities', 'POST', payload);
  if (data.error) { toast(data.error, false); return; }
  input.value = '';
  const wx = await api('/api/weather');
  _wxCities = (wx || {}).cities || [];
  renderWeatherCities();
  toast(`Added "${name}"`);
}

async function deleteWeatherCity(id) {
  const data = await fetch(`/api/weather/cities/${id}`, { method: 'DELETE' }).then(r => r.json());
  if (data.error) { toast(data.error, false); return; }
  _wxCities = (data.config || {}).cities || [];
  renderWeatherCities();
  toast('City removed');
}

function buildWeatherTestGrid(conditions, active) {
  const grid = document.getElementById('wx-test-grid');
  if (!grid) return;
  grid.innerHTML = '';
  conditions.forEach(cond => {
    const btn = document.createElement('button');
    btn.className = 'wx-test-btn' + (cond === active ? ' active' : '');
    btn.textContent = WX_CONDITION_LABELS[cond] || cond;
    btn.dataset.cond = cond;
    btn.onclick = () => setWeatherTest(cond);
    grid.appendChild(btn);
  });
}

async function setWeatherTest(condition) {
  const data = await api('/api/weather/test', 'POST', { condition });
  if (data.error) { toast(data.error, false); return; }
  _wxTestCondition = condition;
  document.querySelectorAll('.wx-test-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.cond === condition);
  });
  document.getElementById('current-mode').textContent = 'weather';
  document.querySelectorAll('#mode-buttons .mode-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.mode === 'weather');
  });
  showPanelForMode('weather');
  toast(`Test: ${WX_CONDITION_LABELS[condition] || condition}`);
}

async function clearWeatherTest() {
  const data = await api('/api/weather/test', 'POST', { condition: '' });
  if (data.error) { toast(data.error, false); return; }
  _wxTestCondition = '';
  document.querySelectorAll('.wx-test-btn').forEach(b => b.classList.remove('active'));
  toast('Live weather data active');
}

document.addEventListener('DOMContentLoaded', () => {
  document.getElementById('img-current-wrap').style.display = 'none';
  document.getElementById('img-crop-wrap').style.display = 'none';
  document.getElementById('img-zoom').addEventListener('input', e => {
    _imgZoom = parseInt(e.target.value) / 100;
    document.getElementById('img-zoom-val').textContent = e.target.value;
    renderCropCanvas();
  });
});
