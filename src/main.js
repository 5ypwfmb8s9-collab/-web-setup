/* ==========================================================================
   GÜLYABANI — bootstrap
   Menus, the frame loop, pointer lock, touch controls and the screens that
   bookend a run.
   ========================================================================== */
(function (global) {
  'use strict';

  var U, game, hud, audio;
  var $ = function (s) { return document.querySelector(s); };
  var $$ = function (s) { return Array.prototype.slice.call(document.querySelectorAll(s)); };

  var DIFF_DESC = [
    'Er ist langsamer und die Batterien halten. Zum Kennenlernen.',
    'Der vorgesehene Weg. Er ist schnell und er wird nicht müde.',
    'Er ist schneller als du rennst. Der Rückstoß deiner Treffer hält kaum an.'
  ];

  /* ============================ BOOTSTRAP ============================ */
  function boot() {
    if (!global.THREE) { setTimeout(boot, 60); return; }
    U = global.GU;
    audio = global.GAudio;

    var canvas = $('#gl');
    game = new global.GGame(canvas);
    if (!game.init()) {
      $('#warn-gl').textContent = 'WebGL ist auf diesem Gerät nicht verfügbar.';
      return;
    }
    hud = game.hud;
    global.__gulyabani = game;   // handy for debugging

    wireMenus();
    wireSettings();
    wireTouch();
    wireGlobalKeys();
    refreshBest();
    startLoop();
  }

  /* ============================== MENUS ============================== */
  function showPane(id) {
    $$('#pane-main, #pane-howto, #pane-settings, #pane-lore').forEach(function (p) {
      p.classList.toggle('hidden', p.id !== id);
    });
  }

  function overlay(id, on) {
    var el = $(id);
    if (el) el.classList.toggle('hidden', !on);
  }

  function wireMenus() {
    $('#btn-play').addEventListener('click', function () { startGame(); });
    $('#btn-howto').addEventListener('click', function () { audio.ui('click'); showPane('pane-howto'); });
    $('#btn-settings').addEventListener('click', function () { audio.ui('click'); showPane('pane-settings'); });
    $('#btn-lore').addEventListener('click', function () { audio.ui('click'); showPane('pane-lore'); });
    $$('.btn.back').forEach(function (b) {
      b.addEventListener('click', function () { audio.ui('click'); showPane('pane-main'); });
    });
    $$('.btn').forEach(function (b) {
      b.addEventListener('mouseenter', function () { audio.ui('hover'); });
    });

    // difficulty
    seg('#seg-diff', game.difficulty, function (v) {
      game.difficulty = v;
      $('#diff-desc').textContent = DIFF_DESC[v];
      U.store.set('difficulty', v);
      refreshBest();
    });
    $('#diff-desc').textContent = DIFF_DESC[game.difficulty];

    // pause menu
    $('#btn-resume').addEventListener('click', function () { resumeGame(); });
    $('#btn-settings2').addEventListener('click', function () {
      audio.ui('click');
      overlay('#pause', false);
      overlay('#menu', true);
      showPane('pane-settings');
      $('#menu').dataset.fromPause = '1';
    });
    $('#btn-quit').addEventListener('click', function () { audio.ui('click'); toMenu(); });

    $('#btn-retry').addEventListener('click', function () { audio.ui('click'); startGame(); });
    $('#btn-again').addEventListener('click', function () { audio.ui('click'); startGame(); });
    $('#btn-menu').addEventListener('click', function () { audio.ui('click'); toMenu(); });
    $('#btn-menu2').addEventListener('click', function () { audio.ui('click'); toMenu(); });

    $('#clicklock').addEventListener('click', function () { resumeGame(); });

    // note reader closes on E or a click
    $('#note').addEventListener('click', function () { closeNote(); });

    game.onDeath = function (reason) {
      $('#dead-sub').textContent = reason;
      renderStats('#dead-stats', game.summary(), false);
      overlay('#dead', true);
      hud.show(false);
    };
    game.onWin = function () {
      var s = game.summary();
      renderStats('#win-stats', s, true);
      saveBest(s);
      overlay('#win', true);
      hud.show(false);
    };
  }

  function seg(sel, value, onChange) {
    var root = $(sel);
    if (!root) return;
    var btns = Array.prototype.slice.call(root.querySelectorAll('button'));
    function setVal(v) {
      btns.forEach(function (b) { b.classList.toggle('on', +b.dataset.v === v); });
    }
    setVal(value);
    btns.forEach(function (b) {
      b.addEventListener('click', function () {
        audio.ui('click');
        var v = +b.dataset.v;
        setVal(v);
        onChange(v);
      });
    });
    return setVal;
  }

  /* ============================= SETTINGS ============================= */
  function wireSettings() {
    var s = game.settings;

    function slider(sel, key, fmt, apply) {
      var el = $(sel);
      if (!el) return;
      var out = el.parentNode.querySelector('output');
      el.value = s[key];
      out.textContent = fmt(s[key]);
      el.addEventListener('input', function () {
        s[key] = +el.value;
        out.textContent = fmt(s[key]);
        game.applySettings();
        if (apply) apply();
      });
    }

    slider('#s-sens', 'sens', function (v) { return (v / 100).toFixed(2); });
    slider('#s-fov', 'fov', function (v) { return v; });
    slider('#s-bright', 'bright', function (v) { return (v / 100).toFixed(2); });
    slider('#s-vol', 'vol', function (v) { return v; });
    slider('#s-scale', 'scale', function (v) { return (v / 100).toFixed(2); }, function () { game.resize(); });

    seg('#seg-qual', s.quality, function (v) { s.quality = v; game.applySettings(); game.resize(); });
    seg('#seg-grain', s.grain, function (v) { s.grain = v; game.applySettings(); });
    seg('#seg-shake', s.shake, function (v) { s.shake = v; game.applySettings(); });
    seg('#seg-subs', s.subs, function (v) { s.subs = v; game.applySettings(); });
  }

  /* ============================ RUN CONTROL ============================ */
  function startGame() {
    audio.init();
    audio.resume();
    audio.ui('click');

    overlay('#menu', false);
    overlay('#dead', false);
    overlay('#win', false);
    overlay('#pause', false);
    overlay('#loading', true);
    hud.show(false);

    var fill = $('.load-fill'), txt = $('.load-txt');
    fill.style.width = '0%';

    game.buildRun(game.difficulty, function (p, label) {
      fill.style.width = (p * 100).toFixed(0) + '%';
      if (label) txt.textContent = label;
    }, function () {
      fill.style.width = '100%';
      setTimeout(function () {
        overlay('#loading', false);
        hud.show(true);
        game.state = global.GGame.STATE.PLAYING;
        game.fadeTarget = 0; game.fadeSpeed = 0.9;
        audio.suspendBeds(false);
        game.input.clearPresses();
        game.input.requestLock(document.body);
        hud.subtitle('Hinter dir schließt sich eine Tür, die du nicht geöffnet hast.', false, 4.5);
        hud.toast('Finde drei Muskalar. Dann die Tür.');
      }, 220);
    });
  }

  function toMenu() {
    game.state = global.GGame.STATE.MENU;
    game.input.exitLock();
    audio.suspendBeds(true);
    overlay('#pause', false);
    overlay('#dead', false);
    overlay('#win', false);
    overlay('#clicklock', false);
    hud.show(false);
    hud.prompt(null);
    overlay('#menu', true);
    showPane('pane-main');
    refreshBest();
  }

  function pauseGame() {
    if (!game.pause()) return;
    overlay('#pause', true);
    renderStats('#pause-stats', game.summary(), false);
    hud.prompt(null);
  }

  function resumeGame() {
    overlay('#pause', false);
    overlay('#clicklock', false);
    if ($('#menu').dataset.fromPause === '1') {
      $('#menu').dataset.fromPause = '';
      overlay('#menu', false);
    }
    game.unpause();
  }

  function closeNote() {
    if (game.state !== global.GGame.STATE.NOTE) return;
    game.closeNote();
  }

  /* ============================== STATS ============================== */
  var DIFF_NAME = ['KORKU', 'DEHŞET', 'KÂBUS'];

  function renderStats(sel, s, won) {
    var rows = [
      ['ZEIT', s.time, won],
      ['MUSKALAR', s.muskas + ' / 3', s.muskas >= 3],
      ['SCHÜSSE', s.shots + ' / 8', false],
      ['KOPFTREFFER', s.hits + (s.shots ? '  (' + s.accuracy + '%)' : ''), s.hits > 0],
      ['PATRONEN ÜBRIG', s.ammoLeft, s.ammoLeft > 0 && won],
      ['SEITEN GELESEN', s.notes + ' / 5', s.notes >= 5],
      ['GRIFFE ÜBERLEBT', s.grabs, false],
      ['STRECKE', s.distance + ' m', false],
      ['SCHWIERIGKEIT', DIFF_NAME[s.difficulty], false]
    ];
    var html = '';
    for (var i = 0; i < rows.length; i++) {
      html += '<div class="k">' + rows[i][0] + '</div><div class="v' + (rows[i][2] ? ' good' : '') + '">' +
        rows[i][1] + '</div>';
    }
    $(sel).innerHTML = html;
  }

  function bestKey() { return 'best' + game.difficulty; }

  function saveBest(s) {
    var prev = U.store.get(bestKey(), null);
    if (prev === null || s.timeRaw < prev) {
      U.store.set(bestKey(), s.timeRaw);
      hud.toast('NEUE BESTZEIT — ' + s.time);
    }
  }

  function refreshBest() {
    var b = U.store.get(bestKey(), null);
    $('#best-line').textContent = b === null
      ? 'Noch nie entkommen.'
      : 'Beste Flucht auf ' + DIFF_NAME[game.difficulty] + ': ' + U.fmtTime(b);
  }

  /* ============================ GLOBAL KEYS ============================ */
  function wireGlobalKeys() {
    var S = global.GGame.STATE;

    window.addEventListener('keydown', function (e) {
      if (e.code === 'Escape' || e.code === 'KeyP') {
        if (game.state === S.PLAYING) { e.preventDefault(); pauseGame(); }
        else if (game.state === S.PAUSED) { e.preventDefault(); resumeGame(); }
        else if (game.state === S.NOTE) { e.preventDefault(); closeNote(); }
      }
      if (e.code === 'KeyE' && game.state === S.NOTE) { e.preventDefault(); closeNote(); }
      if (e.code === 'Enter' && game.state === S.MENU && !$('#menu').classList.contains('hidden')) {
        if (!$('#pane-main').classList.contains('hidden')) startGame();
      }
      if (e.code === 'F11') return;   // let the browser handle fullscreen
    });

    game.input.onLockChange = function (locked) {
      // In drag-to-look mode there is no lock to lose, so losing it is not a
      // reason to interrupt the run.
      if (!locked && !game.input.dragLook && game.state === S.PLAYING) pauseGame();
    };

    game.input.onDragLook = function () {
      document.body.classList.add('draglook');
      if (game.state === S.PLAYING) {
        hud.toast('Maus ziehen zum Umsehen · Klicken zum Schießen');
      }
    };

    // clicking the canvas while paused-by-lock-loss resumes
    $('#gl').addEventListener('click', function () {
      if (game.state === S.PAUSED && $('#pause').classList.contains('hidden')) resumeGame();
    });

    // orientation guard
    function checkOrientation() {
      var portrait = window.innerHeight > window.innerWidth;
      var coarse = window.matchMedia('(pointer: coarse)').matches;
      overlay('#rotate', portrait && coarse);
    }
    window.addEventListener('resize', checkOrientation);
    window.addEventListener('orientationchange', function () { setTimeout(checkOrientation, 220); });
    checkOrientation();
  }

  /* ============================== TOUCH ============================== */
  function wireTouch() {
    var coarse = window.matchMedia('(pointer: coarse)').matches ||
      ('ontouchstart' in window && navigator.maxTouchPoints > 0);
    if (!coarse) return;

    var t = $('#touch');
    t.classList.remove('hidden');
    var input = game.input;
    input.touch.active = true;

    /* --- movement stick --- */
    var stick = $('#stick-l'), knob = stick.querySelector('i');
    var stickId = null, sx = 0, sy = 0;
    var lookId = null, lookX = 0, lookY = 0;
    var R = 46;

    stick.addEventListener('touchstart', function (e) {
      var to = e.changedTouches[0];
      stickId = to.identifier;
      var r = stick.getBoundingClientRect();
      sx = r.left + r.width / 2; sy = r.top + r.height / 2;
      e.preventDefault();
    }, { passive: false });

    window.addEventListener('touchmove', function (e) {
      for (var i = 0; i < e.changedTouches.length; i++) {
        var to = e.changedTouches[i];
        if (to.identifier === stickId) {
          var dx = to.clientX - sx, dy = to.clientY - sy;
          var l = Math.hypot(dx, dy);
          if (l > R) { dx = dx / l * R; dy = dy / l * R; }
          knob.style.transform = 'translate(' + dx + 'px,' + dy + 'px)';
          input.touch.moveX = dx / R;
          input.touch.moveY = -dy / R;
          e.preventDefault();
        } else if (to.identifier === lookId) {
          input.touch.lookDX += to.clientX - lookX;
          input.touch.lookDY += to.clientY - lookY;
          lookX = to.clientX; lookY = to.clientY;
          e.preventDefault();
        }
      }
    }, { passive: false });

    function endTouch(e) {
      for (var i = 0; i < e.changedTouches.length; i++) {
        var to = e.changedTouches[i];
        if (to.identifier === stickId) {
          stickId = null;
          knob.style.transform = '';
          input.touch.moveX = 0; input.touch.moveY = 0;
        }
        if (to.identifier === lookId) lookId = null;
      }
    }
    window.addEventListener('touchend', endTouch);
    window.addEventListener('touchcancel', endTouch);

    /* --- look drag anywhere on the right, away from the buttons --- */
    $('#stage').addEventListener('touchstart', function (e) {
      if (game.state !== global.GGame.STATE.PLAYING) return;
      for (var i = 0; i < e.changedTouches.length; i++) {
        var to = e.changedTouches[i];
        if (to.identifier === stickId || lookId !== null) continue;
        if (to.clientX < window.innerWidth * 0.35) continue;
        if (to.clientY > window.innerHeight - 110 && to.clientX > window.innerWidth - 220) continue;
        lookId = to.identifier; lookX = to.clientX; lookY = to.clientY;
      }
    }, { passive: true });

    /* --- buttons --- */
    function hold(sel, on, off) {
      var el = $(sel);
      if (!el) return;
      el.addEventListener('touchstart', function (e) { e.preventDefault(); on(); }, { passive: false });
      el.addEventListener('touchend', function (e) { e.preventDefault(); if (off) off(); }, { passive: false });
    }
    hold('#t-fire', function () { input.queueFire(); });
    hold('#t-ads', function () { input.touch.ads = !input.touch.ads; });
    hold('#t-run', function () { input.touch.sprint = true; }, function () { input.touch.sprint = false; });
    hold('#t-light', function () { if (game.player) game.player.toggleLight(); });
    hold('#t-use', function () {
      if (game.state === global.GGame.STATE.NOTE) { closeNote(); return; }
      input._pressed['KeyE'] = true;
    });
    hold('#t-stone', function () { input._pressed['KeyG'] = true; });

    // QTE on touch: tap anywhere
    $('#stage').addEventListener('touchstart', function () {
      if (game.qte && game.qte.active) input._pressed['Space'] = true;
    }, { passive: true });
  }

  /* ============================== LOOP ============================== */
  function startLoop() {
    var last = performance.now();
    function frame(now) {
      var dt = (now - last) / 1000;
      last = now;
      if (dt > 0.25) dt = 0.016;      // tab was backgrounded
      try { game.step(dt); } catch (e) { console.error(e); }
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else boot();
})(window);
