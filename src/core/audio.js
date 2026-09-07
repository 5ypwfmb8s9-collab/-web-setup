/* ==========================================================================
   GÜLYABANI — procedural audio
   Every sound in the game is synthesised with the Web Audio API at runtime.
   There are no audio files. Positional sources use HRTF panning so the
   creature can be located by ear alone, which is the point of the design.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;

  function A() {
    this.ready = false;
    this.ctx = null;
    this.volume = 0.8;
    this.muted = false;
    this._hbAcc = 0;
    this._brAcc = 0;
    this._whAcc = 14;
    this._creakAcc = 9;
    this._lastFoot = 0;
  }

  A.prototype.init = function () {
    if (this.ready) return true;
    var Ctx = global.AudioContext || global.webkitAudioContext;
    if (!Ctx) return false;
    try { this.ctx = new Ctx({ latencyHint: 'interactive' }); } catch (e) { return false; }
    var c = this.ctx;

    // ---- master chain: bus -> gentle limiter -> out -------------------
    this.master = c.createGain();
    this.master.gain.value = this.volume;

    this.comp = c.createDynamicsCompressor();
    this.comp.threshold.value = -14;
    this.comp.knee.value = 22;
    this.comp.ratio.value = 7;
    this.comp.attack.value = 0.004;
    this.comp.release.value = 0.22;

    this.master.connect(this.comp);
    this.comp.connect(c.destination);

    // ---- reverb bus: a stone house with wooden floors ------------------
    this.verb = c.createConvolver();
    this.verb.buffer = this._makeIR(2.6, 2.4);
    this.verbGain = c.createGain();
    this.verbGain.gain.value = 0.5;
    this.verb.connect(this.verbGain);
    this.verbGain.connect(this.master);

    // dry bus
    this.dry = c.createGain();
    this.dry.gain.value = 1;
    this.dry.connect(this.master);

    // a low-pass that closes when the player's sanity drops (muffled dread)
    this.duck = c.createBiquadFilter();
    this.duck.type = 'lowpass';
    this.duck.frequency.value = 20000;
    this.duck.Q.value = 0.4;
    this.duck.connect(this.dry);

    this.noiseBuf = this._makeNoise(3);
    this.brownBuf = this._makeBrown(4);

    this._startBeds();
    this.ready = true;
    return true;
  };

  A.prototype.resume = function () {
    if (this.ctx && this.ctx.state === 'suspended') this.ctx.resume();
  };

  A.prototype.setVolume = function (v) {
    this.volume = U.clamp01(v);
    if (this.master) this.master.gain.value = this.muted ? 0 : this.volume;
  };

  A.prototype.suspendBeds = function (on) {
    if (!this.ready) return;
    var t = this.ctx.currentTime;
    this.bedGain.gain.cancelScheduledValues(t);
    this.bedGain.gain.setTargetAtTime(on ? 0.0 : 1.0, t, 0.25);
  };

  /* ------------------------------ buffers ------------------------------ */
  A.prototype._makeNoise = function (sec) {
    var c = this.ctx, n = (c.sampleRate * sec) | 0;
    var b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0);
    for (var i = 0; i < n; i++) d[i] = Math.random() * 2 - 1;
    return b;
  };

  A.prototype._makeBrown = function (sec) {
    var c = this.ctx, n = (c.sampleRate * sec) | 0;
    var b = c.createBuffer(1, n, c.sampleRate), d = b.getChannelData(0);
    var last = 0;
    for (var i = 0; i < n; i++) {
      var w = Math.random() * 2 - 1;
      last = (last + 0.02 * w) / 1.02;
      d[i] = last * 3.2;
    }
    return b;
  };

  /** Synthetic impulse response: early reflections + exponential noise tail. */
  A.prototype._makeIR = function (sec, decay) {
    var c = this.ctx, n = (c.sampleRate * sec) | 0;
    var b = c.createBuffer(2, n, c.sampleRate);
    for (var ch = 0; ch < 2; ch++) {
      var d = b.getChannelData(ch);
      for (var i = 0; i < n; i++) {
        var t = i / n;
        var env = Math.pow(1 - t, decay);
        d[i] = (Math.random() * 2 - 1) * env * 0.55;
      }
      // discrete early reflections give the space a size
      var taps = [0.011, 0.019, 0.028, 0.041, 0.057, 0.079, 0.103];
      for (var k = 0; k < taps.length; k++) {
        var idx = (taps[k] * c.sampleRate * (ch ? 1.06 : 1)) | 0;
        if (idx < n) d[idx] += (0.72 - k * 0.09) * (Math.random() * 0.4 + 0.8);
      }
    }
    return b;
  };

  /* ------------------------------ routing ------------------------------ */
  /** Returns a gain node feeding both the dry bus and the reverb send. */
  A.prototype._bus = function (wet) {
    var c = this.ctx, g = c.createGain();
    g.connect(this.duck);
    if (wet > 0) {
      var s = c.createGain();
      s.gain.value = wet;
      g.connect(s); s.connect(this.verb);
    }
    return g;
  };

  A.prototype._panner = function (pos, ref, max) {
    var c = this.ctx, p = c.createPanner();
    p.panningModel = 'HRTF';
    p.distanceModel = 'inverse';
    p.refDistance = ref || 2.2;
    p.maxDistance = max || 55;
    p.rolloffFactor = 1.15;
    this._setPos(p, pos);
    return p;
  };

  A.prototype._setPos = function (node, pos) {
    if (!pos) return;
    if (node.positionX) {
      node.positionX.value = pos.x; node.positionY.value = pos.y; node.positionZ.value = pos.z;
    } else if (node.setPosition) {
      node.setPosition(pos.x, pos.y, pos.z);
    }
  };

  /** Positional bus: source -> panner -> (dry + reverb send). */
  A.prototype._pbus = function (pos, wet, ref) {
    var c = this.ctx;
    var g = c.createGain();
    var p = this._panner(pos, ref);
    g.connect(p);
    p.connect(this.duck);
    if (wet > 0) {
      var s = c.createGain(); s.gain.value = wet;
      p.connect(s); s.connect(this.verb);
    }
    return g;
  };

  A.prototype.listener = function (pos, fwd, up) {
    if (!this.ready) return;
    var L = this.ctx.listener;
    if (L.positionX) {
      var t = this.ctx.currentTime;
      L.positionX.setTargetAtTime(pos.x, t, 0.02);
      L.positionY.setTargetAtTime(pos.y, t, 0.02);
      L.positionZ.setTargetAtTime(pos.z, t, 0.02);
      L.forwardX.setTargetAtTime(fwd.x, t, 0.02);
      L.forwardY.setTargetAtTime(fwd.y, t, 0.02);
      L.forwardZ.setTargetAtTime(fwd.z, t, 0.02);
      L.upX.setTargetAtTime(up.x, t, 0.02);
      L.upY.setTargetAtTime(up.y, t, 0.02);
      L.upZ.setTargetAtTime(up.z, t, 0.02);
    } else {
      L.setPosition(pos.x, pos.y, pos.z);
      L.setOrientation(fwd.x, fwd.y, fwd.z, up.x, up.y, up.z);
    }
  };

  /* ------------------------- primitive voices ------------------------- */
  A.prototype._noise = function (dest, dur, when) {
    var c = this.ctx, s = c.createBufferSource();
    s.buffer = this.noiseBuf;
    s.loop = true;
    s.playbackRate.value = 0.8 + Math.random() * 0.4;
    s.connect(dest);
    s.start(when || c.currentTime, Math.random() * 2);
    s.stop((when || c.currentTime) + dur);
    return s;
  };

  A.prototype._tone = function (dest, type, f0, f1, dur, when) {
    var c = this.ctx, o = c.createOscillator();
    o.type = type;
    var t = when || c.currentTime;
    o.frequency.setValueAtTime(f0, t);
    if (f1 !== f0) o.frequency.exponentialRampToValueAtTime(Math.max(1, f1), t + dur);
    o.connect(dest);
    o.start(t); o.stop(t + dur + 0.02);
    return o;
  };

  A.prototype._env = function (g, t, a, peak, d, sustain, rel) {
    var p = g.gain;
    p.cancelScheduledValues(t);
    p.setValueAtTime(0.0001, t);
    p.exponentialRampToValueAtTime(Math.max(0.0002, peak), t + a);
    if (sustain !== undefined) {
      p.exponentialRampToValueAtTime(Math.max(0.0002, sustain), t + a + d);
      p.exponentialRampToValueAtTime(0.0001, t + a + d + rel);
    } else {
      p.exponentialRampToValueAtTime(0.0001, t + a + d);
    }
  };

  A.prototype._filter = function (type, freq, q) {
    var f = this.ctx.createBiquadFilter();
    f.type = type; f.frequency.value = freq; f.Q.value = q === undefined ? 1 : q;
    return f;
  };

  /* ============================ AMBIENT BEDS ============================ */
  A.prototype._startBeds = function () {
    var c = this.ctx;
    this.bedGain = c.createGain();
    this.bedGain.gain.value = 1;
    this.bedGain.connect(this.duck);

    // --- wind through shutters ---
    var w = c.createBufferSource();
    w.buffer = this.brownBuf; w.loop = true;
    var wf = this._filter('bandpass', 320, 0.7);
    var wg = c.createGain(); wg.gain.value = 0.09;
    var wlfo = c.createOscillator(); wlfo.type = 'sine'; wlfo.frequency.value = 0.06;
    var wlg = c.createGain(); wlg.gain.value = 190;
    wlfo.connect(wlg); wlg.connect(wf.frequency);
    var wag = c.createOscillator(); wag.type = 'sine'; wag.frequency.value = 0.041;
    var wagg = c.createGain(); wagg.gain.value = 0.05;
    wag.connect(wagg); wagg.connect(wg.gain);
    w.connect(wf); wf.connect(wg); wg.connect(this.bedGain);
    w.start(); wlfo.start(); wag.start();
    this.windGain = wg;

    // --- distant rain on the roof ---
    var r = c.createBufferSource();
    r.buffer = this.noiseBuf; r.loop = true;
    var rf = this._filter('bandpass', 2400, 0.45);
    var rf2 = this._filter('lowpass', 3600, 0.5);
    var rg = c.createGain(); rg.gain.value = 0.028;
    r.connect(rf); rf.connect(rf2); rf2.connect(rg); rg.connect(this.bedGain);
    r.start();
    this.rainGain = rg;

    // --- dread drone: detuned lows that rise with the creature ---
    this.droneGain = c.createGain(); this.droneGain.gain.value = 0.0;
    var dfil = this._filter('lowpass', 260, 3.2);
    this.droneFilter = dfil;
    dfil.connect(this.droneGain); this.droneGain.connect(this.bedGain);
    var freqs = [38.5, 39.1, 57.8, 77.3];
    this.droneOscs = [];
    for (var i = 0; i < freqs.length; i++) {
      var o = c.createOscillator();
      o.type = i < 2 ? 'sawtooth' : 'triangle';
      o.frequency.value = freqs[i];
      var og = c.createGain(); og.gain.value = i < 2 ? 0.5 : 0.24;
      o.connect(og); og.connect(dfil); o.start();
      this.droneOscs.push(o);
    }
    // slow wobble so the drone never sits still
    var wob = c.createOscillator(); wob.type = 'sine'; wob.frequency.value = 0.11;
    var wobg = c.createGain(); wobg.gain.value = 2.4;
    wob.connect(wobg); wobg.connect(this.droneOscs[1].frequency); wob.start();

    // --- tinnitus-like high tone that appears at low sanity ---
    this.tinnGain = c.createGain(); this.tinnGain.gain.value = 0;
    var tin = c.createOscillator(); tin.type = 'sine'; tin.frequency.value = 5240;
    tin.connect(this.tinnGain); this.tinnGain.connect(this.bedGain); tin.start();

    // --- heartbeat bus ---
    this.hbGain = c.createGain(); this.hbGain.gain.value = 1;
    this.hbGain.connect(this.duck);
  };

  /** Continuous state, called every frame. */
  A.prototype.update = function (dt, s) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;

    // drone follows creature proximity and fear
    var target = U.clamp01(s.dread) * 0.16;
    this.droneGain.gain.setTargetAtTime(target, t, 0.5);
    this.droneFilter.frequency.setTargetAtTime(150 + s.dread * 460, t, 0.6);

    // muffle the world as sanity drops
    this.duck.frequency.setTargetAtTime(U.lerp(2400, 20000, U.clamp01(s.sanity)), t, 0.4);
    this.tinnGain.gain.setTargetAtTime((1 - U.clamp01(s.sanity)) * 0.012, t, 0.7);
    this.windGain.gain.setTargetAtTime(0.06 + (1 - s.sanity) * 0.07, t, 1.0);

    // heartbeat
    var hbRate = U.lerp(0.85, 2.9, U.clamp01(Math.max(s.dread, 1 - s.sanity, s.exert * 0.8)));
    var hbVol = U.clamp01(Math.max(s.dread * 1.15, (1 - s.sanity) * 0.9, s.exert * 0.7) - 0.08);
    this._hbAcc += dt * hbRate;
    if (this._hbAcc >= 1 && hbVol > 0.03) {
      this._hbAcc -= 1;
      this._beat(hbVol);
    }

    // breathing
    var brRate = U.lerp(0.28, 1.35, U.clamp01(s.exert * 1.1 + s.dread * 0.35));
    this._brAcc += dt * brRate;
    if (this._brAcc >= 1) {
      this._brAcc -= 1;
      this._breath(U.clamp01(0.1 + s.exert * 0.8 + s.dread * 0.3), s.exert > 0.55);
    }

    // whispers when sanity is low
    this._whAcc -= dt * (0.25 + (1 - s.sanity) * 1.5);
    if (this._whAcc <= 0) {
      this._whAcc = 6 + Math.random() * 12;
      if (s.sanity < 0.7) this.whisper(1 - s.sanity);
    }

    // the house settling
    this._creakAcc -= dt;
    if (this._creakAcc <= 0) {
      this._creakAcc = 11 + Math.random() * 22;
      this.houseCreak();
    }
  };

  A.prototype._beat = function (vol) {
    var c = this.ctx, t = c.currentTime;
    for (var i = 0; i < 2; i++) {
      var when = t + i * 0.17;
      var g = c.createGain();
      g.connect(this.hbGain);
      var amp = vol * (i ? 0.62 : 1) * 0.75;
      this._env(g, when, 0.008, amp, 0.19);
      this._tone(g, 'sine', i ? 62 : 76, 26, 0.2, when);
      // chest thump body
      var ng = c.createGain(); ng.connect(this.hbGain);
      var lp = this._filter('lowpass', 150, 1.2);
      ng.connect(lp); lp.connect(this.hbGain);
      this._env(ng, when, 0.005, amp * 0.5, 0.09);
      this._noise(ng, 0.1, when);
    }
  };

  A.prototype._breath = function (vol, hard) {
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.12);
    var bp = this._filter('bandpass', hard ? 780 : 520, hard ? 1.1 : 0.8);
    var hp = this._filter('highpass', 190, 0.7);
    var n = c.createBufferSource(); n.buffer = this.noiseBuf; n.loop = true;
    n.playbackRate.value = 0.6 + Math.random() * 0.3;
    n.connect(hp); hp.connect(bp); bp.connect(g);
    var dur = hard ? 0.34 : 0.55;
    this._env(g, t, dur * 0.35, vol * 0.10, dur * 0.65);
    bp.frequency.setValueAtTime(hard ? 620 : 420, t);
    bp.frequency.linearRampToValueAtTime(hard ? 980 : 620, t + dur);
    n.start(t, Math.random() * 2); n.stop(t + dur + 0.05);
  };

  /* ============================== SFX ============================== */

  /** Footstep. surface: 0 wood, 1 stone, 2 carpet. */
  A.prototype.footstep = function (surface, intensity, pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    if (t - this._lastFoot < 0.06) return;
    this._lastFoot = t;
    var g = pos ? this._pbus(pos, 0.3, 3) : this._bus(0.22);
    var vol = 0.11 * (0.5 + intensity);
    if (surface === 2) {
      var lp = this._filter('lowpass', 900, 0.8);
      lp.connect(g);
      var ng = c.createGain(); ng.connect(lp);
      this._env(ng, t, 0.006, vol * 0.55, 0.08);
      this._noise(ng, 0.1);
    } else if (surface === 1) {
      var hp = this._filter('highpass', 400, 0.9);
      var bp = this._filter('bandpass', 1900 + Math.random() * 700, 1.6);
      hp.connect(bp); bp.connect(g);
      var ng2 = c.createGain(); ng2.connect(hp);
      this._env(ng2, t, 0.002, vol, 0.06);
      this._noise(ng2, 0.09);
      var tg = c.createGain(); tg.connect(g);
      this._env(tg, t, 0.002, vol * 0.5, 0.07);
      this._tone(tg, 'triangle', 210 + Math.random() * 60, 90, 0.07);
    } else {
      // wood: a low knock plus a board creak
      var bp2 = this._filter('bandpass', 260 + Math.random() * 120, 2.4);
      bp2.connect(g);
      var ng3 = c.createGain(); ng3.connect(bp2);
      this._env(ng3, t, 0.003, vol * 1.1, 0.1);
      this._noise(ng3, 0.12);
      var tg2 = c.createGain(); tg2.connect(g);
      this._env(tg2, t, 0.003, vol * 0.55, 0.11);
      this._tone(tg2, 'sine', 130 + Math.random() * 40, 62, 0.12);
      if (Math.random() < 0.25) {
        var cg = c.createGain(); cg.connect(g);
        var cf = this._filter('bandpass', 900 + Math.random() * 800, 8);
        cg.connect(cf); cf.connect(g);
        this._env(cg, t + 0.03, 0.02, vol * 0.25, 0.2);
        this._tone(cg, 'sawtooth', 380, 300, 0.22, t + 0.03);
      }
    }
  };

  /** A suppressed 9mm: mostly mechanical. The gas is a soft thump. */
  A.prototype.shot = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.5);

    // gas thump through the can
    var lp = this._filter('lowpass', 620, 1.1);
    lp.connect(g);
    var ng = c.createGain(); ng.connect(lp);
    this._env(ng, t, 0.0015, 0.5, 0.075);
    this._noise(ng, 0.09);

    // "thwip" — the pressure wave leaving the suppressor
    var bg = c.createGain(); bg.connect(g);
    var bp = this._filter('bandpass', 1500, 2.2);
    bg.connect(bp); bp.connect(g);
    this._env(bg, t, 0.001, 0.3, 0.05);
    this._tone(bg, 'sine', 1700, 380, 0.06, t);

    // slide cycling: two metallic clacks
    for (var i = 0; i < 2; i++) {
      var when = t + (i ? 0.052 : 0.012);
      var mg = c.createGain();
      var mf = this._filter('bandpass', i ? 3200 : 2350, 7);
      var mf2 = this._filter('highpass', 1200, 0.7);
      mg.connect(mf); mf.connect(mf2); mf2.connect(g);
      this._env(mg, when, 0.0012, i ? 0.2 : 0.26, 0.045);
      this._noise(mg, 0.06, when);
    }
    // spring
    var sg = c.createGain(); sg.connect(g);
    var sf = this._filter('bandpass', 2600, 12);
    sg.connect(sf); sf.connect(g);
    this._env(sg, t + 0.03, 0.004, 0.055, 0.16);
    this._tone(sg, 'triangle', 1500, 900, 0.18, t + 0.03);

    this.shell(t + 0.34);
  };

  A.prototype.shell = function (when) {
    if (!this.ready) return;
    var c = this.ctx;
    var g = this._bus(0.55);
    for (var i = 0; i < 3; i++) {
      var t = when + i * (0.07 + Math.random() * 0.05);
      var bg = c.createGain();
      var bp = this._filter('bandpass', 3600 + Math.random() * 2200, 16);
      bg.connect(bp); bp.connect(g);
      this._env(bg, t, 0.001, 0.09 / (i + 1), 0.09);
      this._tone(bg, 'triangle', 4200 + Math.random() * 1800, 2600, 0.1, t);
    }
  };

  A.prototype.dryfire = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.3);
    var bp = this._filter('bandpass', 2800, 9);
    var mg = c.createGain(); mg.connect(bp); bp.connect(g);
    this._env(mg, t, 0.001, 0.22, 0.04);
    this._noise(mg, 0.05);
  };

  A.prototype.adsClick = function (up) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.15);
    var bp = this._filter('bandpass', up ? 2000 : 1500, 8);
    var mg = c.createGain(); mg.connect(bp); bp.connect(g);
    this._env(mg, t, 0.001, 0.075, 0.035);
    this._noise(mg, 0.04);
  };

  /* --------------------------- the creature --------------------------- */
  A.prototype.growl = function (pos, intensity) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.65, 3.5);
    var dur = 1.1 + Math.random() * 1.3;
    this._env(g, t, 0.28, 0.5 * (0.4 + intensity), dur * 0.4, 0.3 * (0.4 + intensity), dur * 0.5);

    var lp = this._filter('lowpass', 420, 2.6);
    lp.connect(g);
    var o1 = c.createOscillator(); o1.type = 'sawtooth';
    var base = 52 + Math.random() * 22;
    o1.frequency.setValueAtTime(base, t);
    o1.frequency.linearRampToValueAtTime(base * (0.7 + Math.random() * 0.5), t + dur);
    var o2 = c.createOscillator(); o2.type = 'square';
    o2.frequency.setValueAtTime(base * 1.51, t);
    o2.frequency.linearRampToValueAtTime(base * 1.2, t + dur);
    var g2 = c.createGain(); g2.gain.value = 0.22;
    o1.connect(lp); o2.connect(g2); g2.connect(lp);

    // ragged amplitude — a throat, not a machine
    var lfo = c.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 7 + Math.random() * 9;
    var lg = c.createGain(); lg.gain.value = 90;
    lfo.connect(lg); lg.connect(lp.frequency);

    // breath noise on top
    var ng = c.createGain(); ng.gain.value = 0.1;
    var nf = this._filter('bandpass', 700, 0.9);
    ng.connect(nf); nf.connect(g);
    this._noise(ng, dur);

    o1.start(t); o2.start(t); lfo.start(t);
    o1.stop(t + dur + 0.1); o2.stop(t + dur + 0.1); lfo.stop(t + dur + 0.1);
  };

  /** Chains and the staff on stone — the folkloric signature. */
  A.prototype.chains = function (pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.7, 3.5);
    var n = 4 + (Math.random() * 5 | 0);
    for (var i = 0; i < n; i++) {
      var when = t + i * (0.03 + Math.random() * 0.07);
      var bg = c.createGain();
      var bp = this._filter('bandpass', 2600 + Math.random() * 3200, 22);
      bg.connect(bp); bp.connect(g);
      this._env(bg, when, 0.001, 0.06 + Math.random() * 0.06, 0.13);
      this._noise(bg, 0.14, when);
    }
  };

  A.prototype.ghostStep = function (pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.45, 3);
    var lp = this._filter('lowpass', 190, 1.4);
    lp.connect(g);
    var ng = c.createGain(); ng.connect(lp);
    this._env(ng, t, 0.006, 0.5, 0.17);
    this._noise(ng, 0.2);
    var tg = c.createGain(); tg.connect(g);
    this._env(tg, t, 0.005, 0.3, 0.2);
    this._tone(tg, 'sine', 74, 34, 0.22);
    // the staff striking the floor
    if (Math.random() < 0.45) {
      var sg = c.createGain();
      var sf = this._filter('bandpass', 1400 + Math.random() * 700, 9);
      sg.connect(sf); sf.connect(g);
      this._env(sg, t + 0.09, 0.002, 0.16, 0.22);
      this._tone(sg, 'triangle', 900, 380, 0.24, t + 0.09);
    }
  };

  /** Hit reaction: a shriek that tears upward then collapses. */
  A.prototype.shriek = function (pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.8, 2.5);
    var dur = 1.5;
    this._env(g, t, 0.02, 0.85, 0.35, 0.4, 1.05);
    var o = c.createOscillator(); o.type = 'sawtooth';
    o.frequency.setValueAtTime(320, t);
    o.frequency.exponentialRampToValueAtTime(1350, t + 0.14);
    o.frequency.exponentialRampToValueAtTime(120, t + dur);
    var dist = c.createWaveShaper();
    dist.curve = this._distCurve(28);
    var lp = this._filter('lowpass', 3000, 1.4);
    o.connect(dist); dist.connect(lp); lp.connect(g);
    var o2 = c.createOscillator(); o2.type = 'square';
    o2.frequency.setValueAtTime(196, t);
    o2.frequency.exponentialRampToValueAtTime(70, t + dur);
    var g2 = c.createGain(); g2.gain.value = 0.3;
    o2.connect(g2); g2.connect(lp);
    var ng = c.createGain(); ng.gain.value = 0.24;
    var nf = this._filter('bandpass', 1800, 0.8);
    ng.connect(nf); nf.connect(g);
    this._noise(ng, dur);
    o.start(t); o2.start(t); o.stop(t + dur); o2.stop(t + dur);
    this.chains(pos);
  };

  A.prototype.roar = function (pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = pos ? this._pbus(pos, 0.7, 2) : this._bus(0.6);
    var dur = 1.9;
    this._env(g, t, 0.03, 1.15, 0.5, 0.55, 1.3);
    var o = c.createOscillator(); o.type = 'sawtooth';
    o.frequency.setValueAtTime(140, t);
    o.frequency.exponentialRampToValueAtTime(48, t + dur);
    var dist = c.createWaveShaper(); dist.curve = this._distCurve(45);
    var lp = this._filter('lowpass', 1200, 2.2);
    o.connect(dist); dist.connect(lp); lp.connect(g);
    var sub = c.createOscillator(); sub.type = 'sine'; sub.frequency.value = 42;
    var sg = c.createGain(); sg.gain.value = 0.7;
    sub.connect(sg); sg.connect(g);
    var lfo = c.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 18;
    var lg = c.createGain(); lg.gain.value = 260;
    lfo.connect(lg); lg.connect(lp.frequency);
    var ng = c.createGain(); ng.gain.value = 0.3;
    var nf = this._filter('bandpass', 900, 0.6);
    ng.connect(nf); nf.connect(g);
    this._noise(ng, dur);
    o.start(t); sub.start(t); lfo.start(t);
    o.stop(t + dur); sub.stop(t + dur); lfo.stop(t + dur);
  };

  A.prototype._distCurve = function (amount) {
    var n = 1024, curve = new Float32Array(n), k = amount;
    for (var i = 0; i < n; i++) {
      var x = (i * 2) / n - 1;
      curve[i] = ((3 + k) * x * 20 * Math.PI / 180) / (Math.PI + k * Math.abs(x));
    }
    return curve;
  };

  /* ---------------------------- environment ---------------------------- */
  A.prototype.thunder = function (near) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime + (near ? 0.25 : 1.4 + Math.random() * 2.6);
    var g = this._bus(0.7);
    var dur = near ? 3.2 : 4.6;
    var lp = this._filter('lowpass', near ? 900 : 300, 0.9);
    lp.connect(g);
    var ng = c.createGain(); ng.connect(lp);
    var p = ng.gain;
    p.setValueAtTime(0.0001, t);
    p.exponentialRampToValueAtTime(near ? 0.85 : 0.34, t + (near ? 0.02 : 0.5));
    // rolling: several decaying bumps
    for (var i = 0; i < 5; i++) {
      var tt = t + 0.4 + i * (0.35 + Math.random() * 0.5);
      p.exponentialRampToValueAtTime(Math.max(0.005, (near ? 0.5 : 0.2) * (1 - i / 5) * (0.5 + Math.random())), tt);
    }
    p.exponentialRampToValueAtTime(0.0001, t + dur);
    lp.frequency.setValueAtTime(near ? 1400 : 420, t);
    lp.frequency.exponentialRampToValueAtTime(70, t + dur);
    this._noise(ng, dur, t);
    var sub = c.createGain(); sub.connect(g);
    this._env(sub, t, near ? 0.03 : 0.6, near ? 0.5 : 0.18, dur * 0.9);
    this._tone(sub, 'sine', near ? 44 : 32, 18, dur, t);
  };

  A.prototype.houseCreak = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.6);
    var dur = 0.7 + Math.random() * 1.4;
    this._env(g, t, dur * 0.3, 0.05, dur * 0.7);
    var bp = this._filter('bandpass', 300 + Math.random() * 900, 11);
    bp.connect(g);
    var o = c.createOscillator(); o.type = 'sawtooth';
    var f = 90 + Math.random() * 200;
    o.frequency.setValueAtTime(f, t);
    o.frequency.linearRampToValueAtTime(f * (0.7 + Math.random() * 0.7), t + dur);
    var lfo = c.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 5 + Math.random() * 12;
    var lg = c.createGain(); lg.gain.value = f * 0.12;
    lfo.connect(lg); lg.connect(o.frequency);
    o.connect(bp);
    o.start(t); lfo.start(t); o.stop(t + dur); lfo.stop(t + dur);
  };

  A.prototype.doorCreak = function (pos, fast) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.6, 3);
    var dur = fast ? 0.4 : 1.1;
    this._env(g, t, 0.05, 0.30, dur);
    var bp = this._filter('bandpass', 620, 14);
    bp.connect(g);
    var o = c.createOscillator(); o.type = 'sawtooth';
    o.frequency.setValueAtTime(150, t);
    o.frequency.linearRampToValueAtTime(340, t + dur);
    var lfo = c.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 22;
    var lg = c.createGain(); lg.gain.value = 34;
    lfo.connect(lg); lg.connect(o.frequency);
    o.connect(bp);
    o.start(t); lfo.start(t); o.stop(t + dur); lfo.stop(t + dur);
  };

  A.prototype.doorSlam = function (pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.8, 3);
    var lp = this._filter('lowpass', 400, 1.2);
    lp.connect(g);
    var ng = c.createGain(); ng.connect(lp);
    this._env(ng, t, 0.002, 0.75, 0.3);
    this._noise(ng, 0.35);
    var tg = c.createGain(); tg.connect(g);
    this._env(tg, t, 0.003, 0.6, 0.35);
    this._tone(tg, 'sine', 110, 40, 0.36);
  };

  A.prototype.doorBreak = function (pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.9, 3);
    // splintering wood: a burst of short bandpassed cracks
    for (var i = 0; i < 12; i++) {
      var when = t + Math.random() * 0.3;
      var bg = c.createGain();
      var bp = this._filter('bandpass', 500 + Math.random() * 3500, 10);
      bg.connect(bp); bp.connect(g);
      this._env(bg, when, 0.001, 0.14 + Math.random() * 0.2, 0.06 + Math.random() * 0.14);
      this._noise(bg, 0.2, when);
    }
    var lp = this._filter('lowpass', 300, 1);
    lp.connect(g);
    var ng = c.createGain(); ng.connect(lp);
    this._env(ng, t, 0.004, 0.8, 0.45);
    this._noise(ng, 0.5);
  };

  A.prototype.stoneThrow = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.2);
    var bp = this._filter('bandpass', 900, 1.4);
    bp.connect(g);
    var ng = c.createGain(); ng.connect(bp);
    this._env(ng, t, 0.03, 0.1, 0.14);
    this._noise(ng, 0.2);
  };

  A.prototype.stoneHit = function (pos) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._pbus(pos, 0.7, 2);
    for (var i = 0; i < 3; i++) {
      var when = t + i * (0.1 + Math.random() * 0.09);
      var bg = c.createGain();
      var bp = this._filter('bandpass', 1400 + Math.random() * 1600, 14);
      bg.connect(bp); bp.connect(g);
      this._env(bg, when, 0.001, 0.4 / (i + 1.2), 0.1);
      this._noise(bg, 0.12, when);
      var tg = c.createGain(); tg.connect(g);
      this._env(tg, when, 0.001, 0.22 / (i + 1.2), 0.12);
      this._tone(tg, 'triangle', 700 + Math.random() * 500, 300, 0.13, when);
    }
  };

  A.prototype.pickup = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.4);
    this._env(g, t, 0.01, 0.16, 0.3);
    this._tone(g, 'triangle', 620, 900, 0.3);
  };

  /** Muska found: a small bell with an inharmonic shimmer. */
  A.prototype.chime = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.85);
    var parts = [1, 2.02, 2.98, 4.31, 5.42];
    for (var i = 0; i < parts.length; i++) {
      var pg = c.createGain(); pg.connect(g);
      this._env(pg, t + i * 0.012, 0.005, 0.13 / (i * 0.7 + 1), 1.6 + i * 0.3);
      this._tone(pg, 'sine', 523.25 * parts[i], 523.25 * parts[i] * 0.995, 2.2, t + i * 0.012);
    }
    var sg = c.createGain(); sg.connect(g);
    var bp = this._filter('bandpass', 4200, 3);
    sg.connect(bp); bp.connect(g);
    this._env(sg, t, 0.004, 0.05, 0.5);
    this._noise(sg, 0.6);
  };

  /** All three amulets: the seal on the exit tears open. */
  A.prototype.sealBreak = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.9);
    this._env(g, t, 0.01, 0.55, 2.6);
    var o = c.createOscillator(); o.type = 'sawtooth';
    o.frequency.setValueAtTime(880, t);
    o.frequency.exponentialRampToValueAtTime(55, t + 2.4);
    var lp = this._filter('lowpass', 2600, 4);
    o.connect(lp); lp.connect(g);
    var ng = c.createGain(); ng.gain.value = 0.4;
    var nf = this._filter('bandpass', 2000, 0.6);
    ng.connect(nf); nf.connect(g);
    this._noise(ng, 2.4);
    o.start(t); o.stop(t + 2.5);
    this.chime();
  };

  A.prototype.whisper = function (intensity) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    // place it just off to one side of the head
    var side = Math.random() < 0.5 ? -1 : 1;
    var g = this._bus(0.5);
    var pan = c.createStereoPanner ? c.createStereoPanner() : null;
    if (pan) { pan.pan.value = side * (0.6 + Math.random() * 0.4); g.disconnect(); g.connect(pan); pan.connect(this.duck); }
    var dur = 1.1 + Math.random() * 1.4;
    this._env(g, t, 0.25, 0.055 * (0.4 + intensity), dur * 0.4, 0.03, dur * 0.5);
    var src = c.createBufferSource(); src.buffer = this.noiseBuf; src.loop = true;
    src.playbackRate.value = 0.35 + Math.random() * 0.2;
    // three formants approximating vowel sounds
    var f1 = this._filter('bandpass', 420 + Math.random() * 180, 9);
    var f2 = this._filter('bandpass', 1180 + Math.random() * 420, 11);
    var f3 = this._filter('bandpass', 2500 + Math.random() * 700, 8);
    var m = c.createGain(); m.gain.value = 0.55;
    src.connect(f1); src.connect(f2); src.connect(f3);
    f1.connect(m); f2.connect(m); f3.connect(m); m.connect(g);
    // syllable rhythm
    var lfo = c.createOscillator(); lfo.type = 'sine'; lfo.frequency.value = 3.2 + Math.random() * 2.4;
    var lg = c.createGain(); lg.gain.value = 220;
    lfo.connect(lg); lg.connect(f2.frequency);
    src.start(t, Math.random() * 2); src.stop(t + dur);
    lfo.start(t); lfo.stop(t + dur);
  };

  A.prototype.hurt = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.3);
    this._env(g, t, 0.005, 0.4, 0.45);
    var lp = this._filter('lowpass', 700, 1.4);
    lp.connect(g);
    var ng = c.createGain(); ng.connect(lp);
    this._env(ng, t, 0.004, 0.3, 0.4);
    this._noise(ng, 0.45);
    this._tone(g, 'sawtooth', 180, 70, 0.4);
  };

  /** Deep, slow toll on death — the house closing. */
  A.prototype.deathToll = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.95);
    this._env(g, t, 0.02, 0.6, 4.5);
    var parts = [1, 1.51, 2.03, 2.62];
    for (var i = 0; i < parts.length; i++) {
      var pg = c.createGain(); pg.connect(g);
      this._env(pg, t, 0.01, 0.28 / (i + 1), 4.2);
      this._tone(pg, 'sine', 55 * parts[i], 54 * parts[i], 4.4, t);
    }
  };

  A.prototype.win = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.8);
    var notes = [261.6, 392.0, 523.25, 659.25];
    for (var i = 0; i < notes.length; i++) {
      var pg = c.createGain(); pg.connect(g);
      var when = t + i * 0.42;
      this._env(pg, when, 0.06, 0.16, 2.4);
      this._tone(pg, 'triangle', notes[i], notes[i], 2.6, when);
      var hg = c.createGain(); hg.connect(g);
      this._env(hg, when, 0.06, 0.05, 2.0);
      this._tone(hg, 'sine', notes[i] * 2, notes[i] * 2, 2.2, when);
    }
  };

  A.prototype.ui = function (kind) {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.15);
    if (kind === 'hover') {
      this._env(g, t, 0.002, 0.03, 0.05);
      this._tone(g, 'sine', 1400, 1400, 0.05);
    } else {
      this._env(g, t, 0.002, 0.09, 0.11);
      this._tone(g, 'triangle', 320, 180, 0.12);
      var bp = this._filter('bandpass', 2400, 8);
      var ng = c.createGain(); ng.connect(bp); bp.connect(g);
      this._env(ng, t, 0.001, 0.05, 0.05);
      this._noise(ng, 0.06);
    }
  };

  A.prototype.batteryClick = function () {
    if (!this.ready) return;
    var c = this.ctx, t = c.currentTime;
    var g = this._bus(0.2);
    var bp = this._filter('bandpass', 3400, 12);
    var ng = c.createGain(); ng.connect(bp); bp.connect(g);
    this._env(ng, t, 0.001, 0.14, 0.03);
    this._noise(ng, 0.04);
  };

  global.GAudio = new A();
})(window);
