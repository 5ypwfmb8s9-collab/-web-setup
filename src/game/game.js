/* ==========================================================================
   GÜLYABANI — the game
   Renderer, world assembly, the light pool, weather, and the loop that ties
   the player, the creature and the house together.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;
  var TX = global.GTX;

  var STATE = {
    BOOT: 'boot', MENU: 'menu', LOADING: 'loading', PLAYING: 'playing',
    PAUSED: 'paused', NOTE: 'note', DEAD: 'dead', WON: 'won', INTRO: 'intro'
  };

  function Game(canvas) {
    this.canvas = canvas;
    this.state = STATE.BOOT;
    this.time = 0;
    this.runTime = 0;
    this.dt = 0;
    this.frame = 0;
    this.fpsRing = new U.Ring(30, 60);

    this.settings = {
      sens: U.store.get('sens', 130),
      fov: U.store.get('fov', 78),
      bright: U.store.get('bright', 100),
      vol: U.store.get('vol', 80),
      scale: U.store.get('scale', 100),
      quality: U.store.get('quality', 1),
      grain: U.store.get('grain', 1),
      shake: U.store.get('shake', 1),
      subs: U.store.get('subs', 1)
    };
    this.difficulty = U.store.get('difficulty', 1);

    this.stats = { shots: 0, hits: 0, misses: 0, notes: 0, doors: 0, grabs: 0, distance: 0 };

    this._v1 = new THREE.Vector3();
    this._v2 = new THREE.Vector3();
    this._v3 = new THREE.Vector3();
    this._q = new THREE.Quaternion();
    this._e = new THREE.Euler(0, 0, 0, 'YXZ');
  }

  Game.STATE = STATE;

  /* ============================== BOOT ============================== */
  Game.prototype.init = function () {
    var ok = true;
    try {
      this.renderer = new THREE.WebGLRenderer({
        canvas: this.canvas,
        antialias: false,
        alpha: false,
        powerPreference: 'high-performance',
        stencil: false,
        depth: true
      });
    } catch (e) { ok = false; }
    if (!ok || !this.renderer) return false;

    var r = this.renderer;
    r.setPixelRatio(1);                       // we supersample manually instead
    r.outputEncoding = THREE.sRGBEncoding;
    r.toneMapping = THREE.ACESFilmicToneMapping;
    r.toneMappingExposure = 1.12;
    r.shadowMap.enabled = true;
    r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.shadowMap.autoUpdate = true;
    r.autoClear = false;
    r.setClearColor(0x000000, 1);

    this.maxAniso = r.capabilities.getMaxAnisotropy();
    TX.maxAniso = Math.min(8, this.maxAniso);

    this.post = new global.GPostFX(r, this.settings.quality);
    this.input = new global.GInput();
    this.input.sensitivity = this.settings.sens / 100;
    this.hud = new global.GHUD();
    this.hud.subsOn = !!this.settings.subs;
    this.audio = global.GAudio;

    this.camera = new THREE.PerspectiveCamera(this.settings.fov, 1, 0.045, 95);
    this.camera.rotation.order = 'YXZ';

    this.resize();
    var self = this;
    window.addEventListener('resize', function () { self.resize(); });
    window.addEventListener('orientationchange', function () { setTimeout(function () { self.resize(); }, 250); });

    this.state = STATE.MENU;
    return true;
  };

  Game.prototype.resize = function () {
    var w = Math.max(320, window.innerWidth);
    var h = Math.max(240, window.innerHeight);
    var dpr = Math.min(window.devicePixelRatio || 1, 2);
    var scale = this.settings.scale / 100;
    // supersample a little on capable displays: sharper than any AA filter
    var rw = Math.round(w * dpr * scale);
    var rh = Math.round(h * dpr * scale);
    var maxPix = this.settings.quality >= 2 ? 3200000 : (this.settings.quality >= 1 ? 2400000 : 1300000);
    var pix = rw * rh;
    if (pix > maxPix) {
      var k = Math.sqrt(maxPix / pix);
      rw = Math.round(rw * k); rh = Math.round(rh * k);
    }
    this.renderer.setSize(rw, rh, false);
    this.canvas.style.width = w + 'px';
    this.canvas.style.height = h + 'px';
    this.post.setSize(rw, rh);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
    if (this.weapon) this.weapon.resize(w / h);
  };

  /* ============================ WORLD BUILD ============================ */
  Game.prototype.buildRun = function (difficulty, onProgress, onDone) {
    var self = this;
    this.difficulty = difficulty;
    this.state = STATE.LOADING;
    this.stats = { shots: 0, hits: 0, misses: 0, notes: 0, doors: 0, grabs: 0, distance: 0 };

    var seed = (Math.random() * 0xffffffff) >>> 0;
    this.seed = seed;

    var Props = global.GProps;
    var steps = [
      ['Der Konak wird gebaut…', function () {
        self.disposeRun();
        self.scene = new THREE.Scene();
        self.scene.background = new THREE.Color(0x161c26);
        self.scene.fog = new THREE.FogExp2(0x262e40, 0.036);
        self.level = new global.GLevel(seed, difficulty).generate();
      }],
      ['Wände werden verputzt…', function () {
        Props.disposeMaterials();
        Props.initMaterials(seed);
        self.level.buildMaterials();
      }],
      ['Dielen werden gelegt…', function () { self.level.build(); }],
      ['Türen werden eingehängt…', function () { self.level.placeDoors(Props); }],
      ['Muskalar werden versteckt…', function () { self.level.placeObjectives(Props); }],
      ['Das Haus wird möbliert…', function () { self.level.decorate(Props); }],
      ['Lichter werden entzündet…', function () { self.setupLights(); }],
      ['Staub legt sich…', function () { self.setupAtmosphere(); }],
      ['Etwas wacht auf…', function () { self.setupActors(); }],
      ['', function () { self.linearizeColours(); self.finalizeRun(); }]
    ];

    var i = 0;
    function next() {
      if (i >= steps.length) { onDone && onDone(); return; }
      var st = steps[i];
      if (st[0] && onProgress) onProgress(i / steps.length, st[0]);
      // give the browser a frame so the loading bar actually paints
      requestAnimationFrame(function () {
        setTimeout(function () {
          try { st[1](); } catch (err) {
            console.error('build step failed:', err);
          }
          i++;
          if (onProgress) onProgress(i / steps.length, st[0]);
          next();
        }, 0);
      });
    }
    next();
  };

  Game.prototype.setupLights = function () {
    var s = this.scene;

    // barely-there ambient so pure black still has shape
    this.ambient = new THREE.AmbientLight(0x4f5d71, 0.34);
    s.add(this.ambient);
    this.hemi = new THREE.HemisphereLight(0x5c7191, 0x4b3d32, 0.30);
    s.add(this.hemi);

    // a pre-filtered environment, so metals and glass have something to
    // reflect instead of rendering as flat black cut-outs
    if (!this.envRT) {
      var pmrem = new THREE.PMREMGenerator(this.renderer);
      pmrem.compileEquirectangularShader();
      var eqt = TX.envMap();
      this.envRT = pmrem.fromEquirectangular(eqt);
      eqt.dispose();
      pmrem.dispose();
    }
    s.environment = this.envRT.texture;

    // ---- the flashlight ----
    var q = this.settings.quality;
    this.torch = new THREE.SpotLight(0xffdca2, 5.4, 32, 0.47, 0.58, 1.22);
    this.torch.castShadow = true;
    this.torch.shadow.mapSize.width = q >= 2 ? 2048 : (q >= 1 ? 1280 : 768);
    this.torch.shadow.mapSize.height = this.torch.shadow.mapSize.width;
    this.torch.shadow.camera.near = 0.28;
    this.torch.shadow.camera.far = 26;
    this.torch.shadow.bias = -0.0009;
    this.torch.shadow.normalBias = 0.028;
    this.torch.shadow.radius = 1.6;
    this.torchTarget = new THREE.Object3D();
    s.add(this.torch);
    s.add(this.torchTarget);
    this.torch.target = this.torchTarget;
    this.torchDir = new THREE.Vector3(0, 0, -1);
    this.torchFlicker = 1;

    // ---- the light pool: a few real lights chasing the nearest emitters ----
    var poolSize = q >= 2 ? 6 : (q >= 1 ? 5 : 3);
    this.pool = [];
    for (var i = 0; i < poolSize; i++) {
      var pl = new THREE.PointLight(0xffd491, 0, 6, 2);
      pl.castShadow = false;
      s.add(pl);
      this.pool.push({ light: pl, emitter: null });
    }
    this.poolTimer = 0;

    s.add(this.level.group);
  };

  Game.prototype.setupAtmosphere = function () {
    var s = this.scene;

    // ---- dust motes, visible where the beam catches them ----
    var N = this.settings.quality >= 2 ? 620 : (this.settings.quality >= 1 ? 420 : 180);
    var pos = new Float32Array(N * 3);
    var spd = new Float32Array(N * 3);
    var BOX = 13;
    for (var i = 0; i < N; i++) {
      pos[i * 3] = (Math.random() - 0.5) * BOX;
      pos[i * 3 + 1] = Math.random() * 3.2;
      pos[i * 3 + 2] = (Math.random() - 0.5) * BOX;
      spd[i * 3] = (Math.random() - 0.5) * 0.09;
      spd[i * 3 + 1] = -0.012 - Math.random() * 0.035;
      spd[i * 3 + 2] = (Math.random() - 0.5) * 0.09;
    }
    var geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(pos, 3));
    this.dust = new THREE.Points(geo, new THREE.PointsMaterial({
      map: TX.dustSprite(), size: 0.019, sizeAttenuation: true,
      transparent: true, opacity: 0.0, depthWrite: false,
      blending: THREE.AdditiveBlending, color: 0xede9d7
    }));
    this.dust.frustumCulled = false;
    this.dustSpd = spd;
    this.dustBox = BOX;
    s.add(this.dust);

    // ---- lightning ----
    this.storm = new THREE.DirectionalLight(0xd7e3f5, 0);
    this.storm.position.set(0.4, 1, 0.3);
    s.add(this.storm);
    this.lightning = { t: 8 + Math.random() * 14, seq: null, v: 0 };

    // ---- impact puffs ----
    this.puffs = [];
    for (var p = 0; p < 10; p++) {
      var sp = new THREE.Sprite(new THREE.SpriteMaterial({
        map: TX.smokeSprite(p + 11), color: 0xd8d4c8,
        transparent: true, opacity: 0, depthWrite: false
      }));
      sp.scale.set(0.3, 0.3, 1);
      sp.visible = false;
      s.add(sp);
      this.puffs.push({ spr: sp, life: 0 });
    }

    // ---- thrown stones ----
    this.stones = [];
    var stoneGeo = new THREE.SphereGeometry(0.055, 7, 6);
    var stoneMat = new THREE.MeshStandardMaterial({ color: 0xa29f99, roughness: 0.95 });
    this.stoneMat = stoneMat;
    for (var k = 0; k < 4; k++) {
      var m = new THREE.Mesh(stoneGeo, stoneMat);
      m.visible = false; m.castShadow = true;
      s.add(m);
      this.stones.push({ mesh: m, live: false, vel: new THREE.Vector3(), life: 0 });
    }
  };

  Game.prototype.setupActors = function () {
    this.player = new global.GPlayer(this.level, this.input, this.audio, this.difficulty);
    this.player.spawn(this.level.start.x, this.level.start.y, Math.random() * Math.PI * 2);

    this.weapon = new global.GWeapon(this.audio, this.level);
    this.weapon.resize(window.innerWidth / window.innerHeight);
    if (this.envRT) this.weapon.scene.environment = this.envRT.texture;

    this.ghost = new global.GGhost(this.level, this.audio, this.difficulty);
    this.scene.add(this.ghost.group);
    this.ghost.spawn(this.level, this.level.start, this.player.yaw);
  };

  Game.prototype.finalizeRun = function () {
    this.runTime = 0;
    this.qte = { active: false, presses: 0, need: 7 + this.difficulty * 2, t: 0, max: 1.7 };
    this.fade = 1;
    this.fadeTarget = 0;
    this.flash = 0;
    this.senseT = 0;
    this.senseTarget = null;
    this.endSeq = null;
    this.hud._lastAmmo = -1;
    this.hud._lastMuska = -1;
    this.hud.hideNote();
    this.applySettings();
    this.renderer.compile(this.scene, this.camera);
  };

  /**
   * Correct every authored colour in the run exactly once, then keep the
   * light pool honest: it re-assigns colours from emitter hexes each frame,
   * so those have to be converted at assignment time.
   */
  Game.prototype.linearizeColours = function () {
    U.linearizeGraph(this.scene);
    U.linearizeGraph(this.weapon.scene);
    var extra = [this.torch, this.ambient, this.hemi, this.storm];
    for (var i = 0; i < extra.length; i++) {
      if (!extra[i]) continue;
      U.toLinear(extra[i].color);
      if (extra[i].groundColor) U.toLinear(extra[i].groundColor);
    }
    for (var j = 0; j < this.pool.length; j++) U.toLinear(this.pool[j].light.color);
    if (this.scene.fog) U.toLinear(this.scene.fog.color);
    if (this.scene.background) U.toLinear(this.scene.background);
  };

  Game.prototype.disposeRun = function () {
    if (!this.scene) return;
    if (this.level) this.level.dispose();
    if (this.ghost) this.ghost.dispose();
    if (this.weapon) this.weapon.dispose();
    if (this.dust) { this.dust.geometry.dispose(); this.dust.material.dispose(); }
    this.scene = null;
  };

  /* ============================== SETTINGS ============================== */
  Game.prototype.applySettings = function () {
    var s = this.settings;
    this.input.sensitivity = s.sens / 100;
    this.camera.fov = s.fov;
    this.camera.updateProjectionMatrix();
    this.audio.setVolume(s.vol / 100);
    this.hud.subsOn = !!s.subs;
    this.post.setQuality(s.quality);
    var u = this.post.u;
    u.grain.value = s.grain ? 0.055 : 0.0;
    u.aberration.value = s.grain ? 0.0022 : 0.0006;
    u.distortion.value = s.grain ? 0.055 : 0.0;
    u.exposure.value = s.bright / 100;
    u.bloomAmount.value = s.quality >= 1 ? 0.6 : 0.4;
    u.sharpen.value = s.quality >= 1 ? 0.55 : 0.3;
    if (this.torch) {
      var q = s.quality;
      var mp = q >= 2 ? 2048 : (q >= 1 ? 1280 : 768);
      if (this.torch.shadow.mapSize.width !== mp) {
        this.torch.shadow.mapSize.width = this.torch.shadow.mapSize.height = mp;
        if (this.torch.shadow.map) { this.torch.shadow.map.dispose(); this.torch.shadow.map = null; }
      }
    }
    for (var k in s) U.store.set(k, s[k]);
    U.store.set('difficulty', this.difficulty);
  };

  /* =============================== LOOP =============================== */
  Game.prototype.step = function (dtRaw) {
    var dt = Math.min(dtRaw, 0.05);
    this.dt = dt;
    this.time += dt;
    this.frame++;
    this.fpsRing.push(1 / Math.max(dtRaw, 0.0001));

    var playing = this.state === STATE.PLAYING;

    if (playing) {
      this.runTime += dt;
      this.updateGameplay(dt);
    } else if (this.state === STATE.DEAD || this.state === STATE.WON) {
      this.updateEndSequence(dt);
    }

    if (this.scene) {
      this.updateCamera(dt);
      this.updatePost(dt);
      this.render();
    }
    this.input.clearFrame();
  };

  /* --------------------------- gameplay tick --------------------------- */
  Game.prototype.updateGameplay = function (dt) {
    var p = this.player, g = this.ghost, lv = this.level, inp = this.input;

    /* ---- context the player and ghost both need ---- */
    var eye = p.eyePos(this._v1);
    var dGhost = Math.hypot(g.pos.x - p.pos.x, g.pos.z - p.pos.z);
    var los = lv.lineOfSight(eye.x, eye.z, g.pos.x, g.pos.z);
    var fwd = p.forward(this._v2);
    var toG = this._v3.set(g.pos.x - p.pos.x, 0, g.pos.z - p.pos.z);
    var toGLen = toG.length() || 1;
    var facing = (toG.x / toGLen) * fwd.x + (toG.z / toGLen) * fwd.z;
    var ghostVisible = los && facing > 0.34 && dGhost < 26;

    // nearest lit emitter, for the sanity model
    var nearLight = 0;
    for (var i = 0; i < this.pool.length; i++) {
      var em = this.pool[i].emitter;
      if (!em || em.dead) continue;
      var d = Math.hypot(em.x - p.pos.x, em.z - p.pos.z);
      nearLight = Math.max(nearLight, U.clamp01(1 - d / 4.5));
    }

    var self = this;
    var ctx = {
      ghostDist: dGhost,
      ghostVisible: ghostVisible,
      ghostPos: g.pos,
      nearLight: nearLight,
      onToast: function (t, w) { self.hud.toast(t, w); },
      onFootstep: function (vol) {
        if (vol > 0.8) g.hearNoise(p.pos.x, p.pos.z, 0.35);
      }
    };

    /* ---- player ---- */
    var prevX = p.pos.x, prevZ = p.pos.z;
    p.update(dt, ctx);
    this.stats.distance += Math.hypot(p.pos.x - prevX, p.pos.z - prevZ);

    /* ---- weapon ---- */
    var torchOn = p.lightOn && p.battery > 0;
    this.weapon.update(dt, p, inp, torchOn);
    if ((inp.mouse.left || inp.touch.fire) && !p.grabbed && !this.qte.active) this.tryFire();
    if (inp.touch.fire) inp.touch.fire = false;

    /* ---- ghost ---- */
    g.update(dt, {
      playerPos: p.pos, time: this.time, los: los, visible: ghostVisible,
      torchOn: torchOn,
      onCatch: function () { self.onCaught(); },
      onDoorBroken: function () {
        self.hud.subtitle('Holz splittert hinter dir.', true, 2.4);
        p.shake = Math.min(1.2, p.shake + 0.5);
      }
    });

    /* ---- doors, items, exit ---- */
    for (var d = 0; d < lv.doors.length; d++) lv.doors[d].update(dt);
    for (var it = 0; it < lv.items.length; it++) {
      var item = lv.items[it];
      if (item.taken) continue;
      if (Math.abs(item.x - p.pos.x) > 14 || Math.abs(item.z - p.pos.z) > 14) continue;
      if (item.update) item.update(dt, this.time, eye);
    }
    lv.exit.update(dt, this.time);

    /* ---- interaction, throwing, sensing ---- */
    this.updateInteraction(dt);
    if (inp.pressed('KeyG')) this.throwStone();
    if (inp.pressed('KeyQ')) this.useSense();
    if (this.senseT > 0) this.senseT -= dt;

    /* ---- QTE ---- */
    if (this.qte.active) this.updateQTE(dt);

    /* ---- world systems ---- */
    this.updateLightPool(dt);
    this.updateDust(dt);
    this.updateWeather(dt);
    this.updateProjectiles(dt);
    this.updatePuffs(dt);

    /* ---- audio state ---- */
    var dread = U.clamp01(1 - dGhost / 17) * (ghostVisible ? 1.25 : 1);
    this.audio.update(dt, {
      dread: U.clamp01(dread),
      sanity: p.sanity,
      exert: U.clamp01(1 - p.stamina)
    });
    this.audio.listener(
      { x: eye.x, y: eye.y, z: eye.z },
      { x: fwd.x, y: fwd.y, z: fwd.z },
      { x: 0, y: 1, z: 0 }
    );

    /* ---- whispers ---- */
    if (p.sanity < 0.45 && Math.random() < dt * 0.16) {
      this.hud.subtitle(global.GHUD.WHISPERS[(Math.random() * global.GHUD.WHISPERS.length) | 0], true, 2.6);
    }

    /* ---- HUD ---- */
    var bearing = this.relativeBearing(p, g.pos.x, g.pos.z);
    var exitBearing = null;
    if (lv.exit.unlocked) exitBearing = this.relativeBearing(p, lv.exit.x, lv.exit.z);
    else if (this.senseT > 0 && this.senseTarget) {
      exitBearing = this.relativeBearing(p, this.senseTarget.x, this.senseTarget.z);
    }
    this.hud.update({
      dt: dt,
      stamina: p.stamina, sanity: p.sanity, battery: p.battery, lightOn: torchOn,
      ammo: this.weapon.ammo, stones: p.stones, muskas: p.muskas,
      time: this.runTime, yaw: p.yaw,
      spread: this.weapon.spread(), ads: this.weapon.ads,
      ghostDist: dGhost, ghostBearing: bearing, exitBearing: exitBearing
    });
  };

  Game.prototype.relativeBearing = function (p, tx, tz) {
    var fx = -Math.sin(p.yaw), fz = -Math.cos(p.yaw);
    var rx = -fz, rz = fx;
    var dx = tx - p.pos.x, dz = tz - p.pos.z;
    var l = Math.hypot(dx, dz) || 1;
    dx /= l; dz /= l;
    return Math.atan2(dx * rx + dz * rz, dx * fx + dz * fz);
  };

  /* --------------------------- interaction --------------------------- */
  Game.prototype.updateInteraction = function (dt) {
    var p = this.player, lv = this.level;
    var eye = p.eyePos(this._v1);
    var fwd = p.forward(this._v2);
    var best = null, bestScore = 0;

    function consider(x, z, range, label, key, action) {
      var dx = x - p.pos.x, dz = z - p.pos.z;
      var d = Math.hypot(dx, dz);
      if (d > range) return;
      var dot = d < 0.3 ? 1 : (dx / d) * fwd.x + (dz / d) * fwd.z;
      if (dot < 0.38) return;
      var score = dot * 2 - d / range;
      if (!best || score > bestScore) {
        bestScore = score;
        best = { label: label, key: key, action: action };
      }
    }

    for (var i = 0; i < lv.items.length; i++) {
      var it = lv.items[i];
      if (it.taken) continue;
      var label = it.kind === 'muska' ? 'Muska aufheben'
        : it.kind === 'note' ? 'Seite lesen'
          : it.kind === 'battery' ? 'Batterie nehmen' : 'Steine aufheben';
      (function (item, lbl) {
        consider(item.x, item.z, 2.1, lbl, 'E', function () { this.pickUp(item); });
      })(it, label);
    }

    for (var d2 = 0; d2 < lv.doors.length; d2++) {
      var dr = lv.doors[d2];
      if (dr.broken) continue;
      (function (door) {
        consider(door.x, door.z, 2.0, door.open ? 'Tür schließen' : 'Tür öffnen', 'E', function () {
          if (door.toggle(this.audio)) {
            if (!door.open) {
              this.stats.doors++;
              this.hud.toast('Tür geschlossen — das hält ihn kurz auf.');
            }
            this.ghost.hearNoise(door.x, door.z, 0.5);
          }
        });
      })(dr);
    }

    var ex = lv.exit;
    consider(ex.targetX, ex.targetZ, 2.9,
      ex.unlocked ? 'HINAUS' : 'Versiegelt — ' + p.muskas + '/3 Muskalar', 'E',
      function () {
        if (ex.unlocked) this.startWin();
        else {
          this.hud.toast('Das Siegel hält. Es fehlen ' + (3 - p.muskas) + ' Muskalar.', true);
          this.audio.dryfire();
        }
      });

    this.hud.prompt(best ? best.label : null, best ? best.key : 'E');
    this._interact = best;

    if (best && this.input.pressed('KeyE')) best.action.call(this);
    else if (!best) this.input.pressed('KeyE');
  };

  Game.prototype.pickUp = function (item) {
    var p = this.player;
    if (item.kind === 'muska') {
      item.collect();
      p.muskas++;
      this.audio.chime();
      this.hud.toast('MUSKA ' + p.muskas + '/3 — ein Siegel bricht');
      if (p.muskas >= 3) {
        this.level.exit.unlock();
        this.audio.sealBreak();
        this.hud.toast('Das Siegel ist gebrochen. Die Tür wartet.');
        this.hud.subtitle('Irgendwo im Haus schlägt Holz gegen Stein.', true, 3.4);
      } else {
        this.level.exit.setProgress(p.muskas);
      }
      // it hears the amulet
      this.ghost.hearNoise(item.x, item.z, 0.8);
    } else if (item.kind === 'note') {
      item.collect();
      this.stats.notes++;
      p.notesRead.push(item.index);
      this.audio.pickup();
      this.openNote(item.index);
    } else if (item.kind === 'battery') {
      item.collect();
      p.addBattery(0.45);
      this.audio.pickup();
      this.hud.toast('Batterie — Fener +45%');
    } else {
      item.collect();
      p.stones += 3;
      this.audio.pickup();
      this.hud.toast('Steine aufgehoben (+3)');
    }
  };

  Game.prototype.openNote = function (index) {
    this.state = STATE.NOTE;
    this.hud.showNote(index);
    this.input.exitLock();
    this.audio.suspendBeds(false);
  };
  Game.prototype.closeNote = function () {
    this.hud.hideNote();
    this.state = STATE.PLAYING;
    this.input.requestLock(document.body);
  };

  /* ---------------------------- shooting ---------------------------- */
  Game.prototype.tryFire = function () {
    var w = this.weapon;
    if (w.cooldown > 0) return;
    var res = w.fire();
    if (!res) return;
    if (res.empty) {
      this.hud.toast('Leer. Es gibt keine Patronen mehr.', true);
      return;
    }
    this.stats.shots++;
    this.flash = Math.max(this.flash, 0.10);

    var p = this.player, g = this.ghost;
    var origin = p.eyePos(this._v1).clone();
    var dir = p.forward(this._v2).clone();
    // apply spread in view space
    var right = new THREE.Vector3(-Math.cos(p.yaw), 0, Math.sin(p.yaw));
    var up = new THREE.Vector3().crossVectors(right, dir).normalize();
    dir.addScaledVector(right, res.spreadX).addScaledVector(up, res.spreadY).normalize();

    var wallDist = this.raycastWalls(origin, dir, 60);
    var headT = g.headHit(origin, dir, Math.min(wallDist, 60));
    var bodyT = g.bodyHit(origin, dir, Math.min(wallDist, 60));

    if (headT >= 0 && (bodyT < 0 || headT <= bodyT + 0.35)) {
      this.stats.hits++;
      var n = g.takeHeadshot(g.pos.x - p.pos.x, g.pos.z - p.pos.z);
      this.hud.el.crosshair.classList.add('hit');
      var self = this;
      setTimeout(function () { self.hud.el.crosshair.classList.remove('hit'); }, 160);
      this.hud.toast('KOPFTREFFER — er fällt zurück (' + n + '/8)');
      this.hud.subtitle('Es kreischt. Der Boden zittert.', true, 2.6);
      p.shake = Math.min(1.3, p.shake + 0.45);
      this.spawnPuff(g.headWorld.x, g.headWorld.y, g.headWorld.z, 0.6, 0x834747);
    } else if (bodyT >= 0) {
      this.stats.misses++;
      this.hud.toast('Durchgegangen. Nur der Kopf zählt.', true);
      this.hud.subtitle('Die Kugel geht durch ihn hindurch wie durch Rauch.', false, 2.6);
    } else {
      this.stats.misses++;
      var hx = origin.x + dir.x * wallDist;
      var hy = origin.y + dir.y * wallDist;
      var hz = origin.z + dir.z * wallDist;
      this.spawnPuff(hx, hy, hz, 0.34, 0xddd7cb);
      this.audio.stoneHit({ x: hx, y: hy, z: hz });
      this.ghost.hearNoise(hx, hz, 0.45);
    }
  };

  /** Marches the grid to find where a ray meets a wall. */
  Game.prototype.raycastWalls = function (origin, dir, maxDist) {
    var lv = this.level;
    var step = 0.14;
    var t = 0.25;
    while (t < maxDist) {
      var x = origin.x + dir.x * t;
      var y = origin.y + dir.y * t;
      var z = origin.z + dir.z * t;
      if (y < 0.02) return t;
      if (y > lv.WH - 0.02) return t;
      if (!lv.isOpen(lv.toCellX(x), lv.toCellY(z))) return t;
      t += step;
    }
    return maxDist;
  };

  Game.prototype.spawnPuff = function (x, y, z, scale, color) {
    for (var i = 0; i < this.puffs.length; i++) {
      var p = this.puffs[i];
      if (p.life > 0) continue;
      p.life = 0.85;
      p.scale = scale;
      p.spr.visible = true;
      p.spr.position.set(x, y, z);
      p.spr.material.color.setHex(color);
      p.spr.material.opacity = 0.8;
      p.spr.scale.set(scale, scale, 1);
      return;
    }
  };

  Game.prototype.updatePuffs = function (dt) {
    for (var i = 0; i < this.puffs.length; i++) {
      var p = this.puffs[i];
      if (p.life <= 0) continue;
      p.life -= dt;
      if (p.life <= 0) { p.spr.visible = false; continue; }
      var k = 1 - p.life / 0.85;
      p.spr.material.opacity = (1 - k) * 0.75;
      p.spr.scale.setScalar(p.scale * (1 + k * 2.4));
      p.spr.position.y += dt * 0.25;
    }
  };

  /* ---------------------------- stones ---------------------------- */
  Game.prototype.throwStone = function () {
    var p = this.player;
    if (p.stones <= 0) { this.hud.toast('Keine Steine mehr.', true); return; }
    for (var i = 0; i < this.stones.length; i++) {
      var s = this.stones[i];
      if (s.live) continue;
      p.stones--;
      var eye = p.eyePos(this._v1);
      var fwd = p.forward(this._v2);
      s.mesh.position.set(eye.x + fwd.x * 0.4, eye.y - 0.1, eye.z + fwd.z * 0.4);
      s.vel.set(fwd.x * 12.5, fwd.y * 12.5 + 2.2, fwd.z * 12.5);
      s.live = true; s.life = 5;
      s.mesh.visible = true;
      this.audio.stoneThrow();
      this.hud.toast('Stein geworfen');
      return;
    }
  };

  Game.prototype.updateProjectiles = function (dt) {
    var lv = this.level;
    for (var i = 0; i < this.stones.length; i++) {
      var s = this.stones[i];
      if (!s.live) continue;
      s.life -= dt;
      s.vel.y -= 12.5 * dt;
      var np = s.mesh.position.clone().addScaledVector(s.vel, dt);
      var hit = false;
      if (np.y < 0.055) { np.y = 0.055; hit = true; }
      else if (np.y > lv.WH - 0.06) { np.y = lv.WH - 0.06; s.vel.y *= -0.3; }
      if (!lv.isOpen(lv.toCellX(np.x), lv.toCellY(np.z))) { hit = true; np.copy(s.mesh.position); }
      s.mesh.position.copy(np);
      if (hit) {
        this.audio.stoneHit({ x: np.x, y: np.y, z: np.z });
        this.ghost.hearNoise(np.x, np.z, 1.0);
        this.spawnPuff(np.x, np.y + 0.05, np.z, 0.22, 0xc2beb6);
        s.live = false; s.mesh.visible = false;
        this.hud.subtitle('Der Stein schlägt auf. Etwas dreht sich danach um.', false, 2.4);
      } else if (s.life <= 0) {
        s.live = false; s.mesh.visible = false;
      }
    }
  };

  /* ------------------------- the muska sense ------------------------- */
  Game.prototype.useSense = function () {
    var p = this.player;
    if (this.senseT > 0) return;
    if (p.sanity < 0.12) { this.hud.toast('Zu erschöpft, um etwas zu spüren.', true); return; }
    var lv = this.level;
    var target = null, bestD = 1e9;
    if (p.muskas >= 3) target = { x: lv.exit.x, z: lv.exit.z };
    else {
      for (var i = 0; i < lv.items.length; i++) {
        var it = lv.items[i];
        if (it.kind !== 'muska' || it.taken) continue;
        var d = Math.hypot(it.x - p.pos.x, it.z - p.pos.z);
        if (d < bestD) { bestD = d; target = { x: it.x, z: it.z }; }
      }
    }
    if (!target) return;
    this.senseTarget = target;
    this.senseT = 6;
    p.sanity = U.clamp01(p.sanity - 0.07);
    this.audio.chime();
    this.hud.toast('Du spürst einen Zug… (6s)');
  };

  /* ------------------------- being caught ------------------------- */
  Game.prototype.onCaught = function () {
    if (this.qte.active || this.state !== STATE.PLAYING) return;
    var p = this.player;
    this.stats.grabs++;
    this.audio.roar(this.ghost.pos);
    p.shake = 1.4;

    if (p.stamina < 0.18) { this.die('Kein Atem mehr, um dich zu wehren.'); return; }

    p.grabbed = true;
    this.ghost.setGrabbed(true);
    this.qte.active = true;
    this.qte.presses = 0;
    this.qte.t = this.qte.max;
    this.input.clearPresses();
    this.hud.qte(true, 0);
    this.hud.subtitle('Er hat dich. WEHR DICH.', true, 2.0);
  };

  Game.prototype.updateQTE = function (dt) {
    var q = this.qte;
    q.t -= dt;
    if (this.input.pressed('Space') || this.input.pressed('Enter')) {
      q.presses++;
      this.player.shake = Math.min(1.5, this.player.shake + 0.2);
      this.audio.hurt();
    }
    this.hud.qte(true, q.presses / q.need);
    if (q.presses >= q.need) {
      q.active = false;
      this.hud.qte(false, 0);
      this.player.grabbed = false;
      this.player.stamina = 0;
      this.player.hurt(0.55);
      this.ghost.setGrabbed(false);
      this.hud.toast('Losgerissen — aber du hast nichts mehr im Tank.', true);
      this.hud.subtitle('Du reißt dich los. Deine Beine sind aus Blei.', false, 2.8);
    } else if (q.t <= 0) {
      q.active = false;
      this.hud.qte(false, 0);
      this.die('Er hat nicht losgelassen.');
    }
  };

  /* ---------------------------- light pool ---------------------------- */
  Game.prototype.updateLightPool = function (dt) {
    var p = this.player;
    this.poolTimer -= dt;
    var ems = this.level.emitters;

    if (this.poolTimer <= 0) {
      this.poolTimer = 0.18;
      // score every emitter and take the best few
      var scored = [];
      for (var i = 0; i < ems.length; i++) {
        var e = ems[i];
        if (e.dead) continue;
        var d = Math.hypot(e.x - p.pos.x, e.z - p.pos.z);
        if (d > 26) continue;
        scored.push({ e: e, s: d - (e.priority || 0) * 2.2 });
      }
      scored.sort(function (a, b) { return a.s - b.s; });
      for (var k = 0; k < this.pool.length; k++) {
        this.pool[k].emitter = k < scored.length ? scored[k].e : null;
      }
    }

    for (var j = 0; j < this.pool.length; j++) {
      var slot = this.pool[j];
      var em = slot.emitter;
      if (!em || em.dead) { slot.light.intensity = 0; continue; }
      slot.light.position.set(em.x, em.y, em.z);
      slot.light.color.setHex(em.color).convertSRGBToLinear();
      slot.light.distance = em.range;
      var flick = 0.78 + U.noise2(this.time * 6.5, em.phase || 0, 3) * 0.44;
      slot.light.intensity = (em.power || 1.4) * flick;
      if (em.flame) {
        em.flame.scale.set(0.022 * flick, (0.075 + flick * 0.03), 0.022 * flick);
        em.glow.material.opacity = 0.55 + flick * 0.3;
        em.glow.scale.setScalar(0.5 + flick * 0.22);
      }
    }
  };

  /* ------------------------------ dust ------------------------------ */
  Game.prototype.updateDust = function (dt) {
    var p = this.player;
    var arr = this.dust.geometry.attributes.position.array;
    var spd = this.dustSpd, B = this.dustBox, H = 3.3;
    var cx = p.pos.x, cz = p.pos.z;
    var torchOn = p.lightOn && p.battery > 0;
    for (var i = 0; i < arr.length; i += 3) {
      arr[i] += spd[i] * dt;
      arr[i + 1] += spd[i + 1] * dt;
      arr[i + 2] += spd[i + 2] * dt;
      // slow swirl
      arr[i] += Math.sin(this.time * 0.35 + arr[i + 2] * 0.7) * 0.012 * dt * 10;
      if (arr[i + 1] < 0.05) arr[i + 1] = H;
      if (arr[i + 1] > H) arr[i + 1] = 0.05;
      var dx = arr[i] - cx, dz = arr[i + 2] - cz;
      if (dx > B / 2) arr[i] -= B; else if (dx < -B / 2) arr[i] += B;
      if (dz > B / 2) arr[i + 2] -= B; else if (dz < -B / 2) arr[i + 2] += B;
    }
    this.dust.geometry.attributes.position.needsUpdate = true;
    this.dust.material.opacity = U.damp(this.dust.material.opacity, torchOn ? 0.20 : 0.04, 4, dt);
  };

  /* ----------------------------- weather ----------------------------- */
  Game.prototype.updateWeather = function (dt) {
    var L = this.lightning;
    L.t -= dt;
    if (L.t <= 0 && !L.seq) {
      L.t = 18 + Math.random() * 30;
      var near = Math.random() < 0.35;
      L.seq = { t: 0, near: near, bursts: [] };
      var n = 2 + (Math.random() * 3 | 0);
      var at = 0;
      for (var i = 0; i < n; i++) {
        at += 0.04 + Math.random() * 0.13;
        L.seq.bursts.push({ at: at, power: (near ? 1 : 0.55) * (0.5 + Math.random() * 0.8), dur: 0.05 + Math.random() * 0.1 });
      }
      this.audio.thunder(near);
      if (near) this.hud.subtitle('Ein Blitz. Für einen Moment siehst du das ganze Haus.', false, 2.6);
    }

    var v = 0;
    if (L.seq) {
      L.seq.t += dt;
      for (var b = 0; b < L.seq.bursts.length; b++) {
        var B2 = L.seq.bursts[b];
        if (L.seq.t >= B2.at && L.seq.t < B2.at + B2.dur) v = Math.max(v, B2.power);
      }
      if (L.seq.t > 1.4) L.seq = null;
    }
    L.v = U.damp(L.v, v, 26, dt);
    this.storm.intensity = L.v * 1.5;
    this.hemi.intensity = 0.30 + L.v * 1.15;
    this.flash = Math.max(this.flash, L.v * 0.30);

    // window panes catch the strike
    for (var w = 0; w < this.level.windows.length; w++) {
      var win = this.level.windows[w];
      if (win.pane) win.pane.material.opacity = 0.10 + L.v * 0.85;
    }
  };

  /* ----------------------------- camera ----------------------------- */
  Game.prototype.updateCamera = function (dt) {
    var p = this.player;
    if (!p) return;
    var eye = p.eyePos(this._v1);
    var shake = this._v3;
    if (this.settings.shake) p.shakeOffset(this.time, shake);
    else shake.set(0, 0, 0);

    this.camera.position.set(eye.x + shake.x, eye.y + shake.y, eye.z + shake.z);
    var kick = this.weapon ? this.weapon.kick : { x: 0, y: 0 };
    this.camera.rotation.set(p.pitch + kick.x, p.yaw + kick.y, p.roll, 'YXZ');

    // ADS pulls the field of view in a touch
    var fov = this.settings.fov - (this.weapon ? this.weapon.ads * 9 : 0);
    if (Math.abs(this.camera.fov - fov) > 0.01) {
      this.camera.fov = fov;
      this.camera.updateProjectionMatrix();
    }

    /* ---- flashlight follows the head, with lag ---- */
    if (this.torch) {
      var fwd = p.forward(this._v2);
      this.torchDir.x = U.damp(this.torchDir.x, fwd.x, 17, dt);
      this.torchDir.y = U.damp(this.torchDir.y, fwd.y, 17, dt);
      this.torchDir.z = U.damp(this.torchDir.z, fwd.z, 17, dt);
      var right = -Math.cos(p.yaw) * 0.16, rightZ = Math.sin(p.yaw) * 0.16;
      this.torch.position.set(eye.x + right, eye.y - 0.10, eye.z + rightZ);
      this.torchTarget.position.set(
        this.torch.position.x + this.torchDir.x * 12,
        this.torch.position.y + this.torchDir.y * 12,
        this.torch.position.z + this.torchDir.z * 12
      );
      var on = p.lightOn && p.battery > 0;
      var lowBat = p.battery < 0.2 ? (0.45 + U.noise2(this.time * 22, 3, 9) * 0.85) : 1;
      var fear = p.sanity < 0.3 ? (0.8 + U.noise2(this.time * 9, 7, 2) * 0.4) : 1;
      this.torchFlicker = U.damp(this.torchFlicker, on ? lowBat * fear : 0, 24, dt);
      this.torch.intensity = 5.4 * this.torchFlicker;
      this.torch.visible = this.torch.intensity > 0.01;
    }
  };

  /* ------------------------------ post ------------------------------ */
  Game.prototype.updatePost = function (dt) {
    var u = this.post.u;
    u.time.value = this.time;
    var p = this.player;
    this.flash = Math.max(0, this.flash - dt * 3.4);
    u.flash.value = this.flash;
    u.fade.value = this.fade === undefined ? 0 : this.fade;
    if (p) {
      var fear = U.clamp01((1 - p.sanity) * 0.9 + p.fear * 0.45);
      u.fear.value = U.damp(u.fear.value, fear, 3, dt);
      u.hurt.value = U.damp(u.hurt.value, p.hurtT, 5, dt);
      u.scanline.value = U.clamp01((0.45 - p.sanity) * 2);
      u.saturation.value = U.lerp(0.92, 0.55, U.clamp01(1 - p.sanity));
    }
    if (this.fadeTarget !== undefined) {
      this.fade = U.damp(this.fade, this.fadeTarget, this.fadeSpeed || 3, dt);
    }
  };

  /* ----------------------------- render ----------------------------- */
  Game.prototype.render = function () {
    var self = this;
    var r = this.renderer;
    this.post.render(function () {
      r.render(self.scene, self.camera);
      if (self.weapon && self.state !== STATE.DEAD) {
        r.clearDepth();
        r.render(self.weapon.scene, self.weapon.camera);
      }
    });
  };

  /* ---------------------------- end states ---------------------------- */
  Game.prototype.die = function (reason) {
    if (this.state === STATE.DEAD) return;
    this.state = STATE.DEAD;
    this.player.grabbed = true;
    this.qte.active = false;
    this.hud.qte(false, 0);
    this.hud.prompt(null);
    this.audio.roar(this.ghost.pos);
    this.audio.deathToll();
    this.audio.suspendBeds(true);
    this.player.shake = 1.5;
    this.endSeq = { t: 0, kind: 'dead', reason: reason || 'Gülyabani seni aldı.' };
    this.fadeTarget = 1; this.fadeSpeed = 0.75;
    this.input.exitLock();
  };

  Game.prototype.startWin = function () {
    if (this.state === STATE.WON) return;
    this.state = STATE.WON;
    this.level.exit.opened = true;
    this.audio.doorCreak({ x: this.level.exit.x, y: 1.4, z: this.level.exit.z }, false);
    this.audio.win();
    this.audio.suspendBeds(true);
    this.endSeq = { t: 0, kind: 'won' };
    this.hud.prompt(null);
    this.input.exitLock();
  };

  Game.prototype.updateEndSequence = function (dt) {
    if (!this.endSeq) return;
    this.endSeq.t += dt;
    var p = this.player, g = this.ghost;

    for (var d = 0; d < this.level.doors.length; d++) this.level.doors[d].update(dt);
    this.level.exit.update(dt, this.time);
    this.updateLightPool(dt);

    if (this.endSeq.kind === 'dead') {
      // it comes the rest of the way and fills the screen
      var t = U.clamp01(this.endSeq.t / 1.1);
      var dx = p.pos.x - g.pos.x, dz = p.pos.z - g.pos.z;
      var l = Math.hypot(dx, dz) || 1;
      g.pos.x += (dx / l) * dt * 2.2;
      g.pos.z += (dz / l) * dt * 2.2;
      g.group.position.set(g.pos.x, 0, g.pos.z);
      g.body.rotation.y = Math.atan2(p.pos.x - g.pos.x, p.pos.z - g.pos.z);
      g.chest.rotation.x = U.lerp(0.14, -0.3, t);
      g.neck.rotation.x = U.lerp(-0.12, 0.5, t);
      g.jaw.rotation.x = U.lerp(0.06, 0.9, t);
      g.eyeGlow.intensity = 1.2 + t * 2.2;
      for (var e = 0; e < g.eyes.length; e++) {
        if (g.eyes[e].isSprite) {
          g.eyes[e].material.opacity = 1;
          g.eyes[e].scale.setScalar(0.17 + t * 0.5);
        }
      }
      var want = Math.atan2(-(g.pos.x - p.pos.x), -(g.pos.z - p.pos.z));
      p.yaw = U.dampAngle(p.yaw, want, 9, dt);
      p.pitch = U.damp(p.pitch, 0.16, 5, dt);
      p.shake = Math.max(p.shake, 1.2 * (1 - t));
      this.post.u.fear.value = U.damp(this.post.u.fear.value, 1, 4, dt);
      this.post.u.hurt.value = U.damp(this.post.u.hurt.value, 0.75, 3, dt);
      if (this.endSeq.t > 2.6 && !this.endSeq.shown) {
        this.endSeq.shown = true;
        if (this.onDeath) this.onDeath(this.endSeq.reason);
      }
    } else {
      // the door swings, the outside floods in
      var k = U.clamp01((this.endSeq.t - 0.7) / 2.0);
      this.fadeTarget = 0;
      this.post.u.flash.value = k * 1.6;
      this.post.u.fear.value = U.damp(this.post.u.fear.value, 0, 2, dt);
      // stop short of the leaf: any closer and the near plane cuts into it
      var ex = this.level.exit;
      var tx = ex.x - ex.dirX * 1.15, tz = ex.z - ex.dirY * 1.15;
      p.pos.x = U.damp(p.pos.x, tx, 1.1, dt);
      p.pos.z = U.damp(p.pos.z, tz, 1.1, dt);
      p.eye = U.damp(p.eye, 1.68, 3, dt);
      var wy = Math.atan2(-(ex.x - p.pos.x), -(ex.z - p.pos.z));
      p.yaw = U.dampAngle(p.yaw, wy, 3, dt);
      p.pitch = U.damp(p.pitch, 0, 3, dt);
      if (this.endSeq.t > 3.2 && !this.endSeq.shown) {
        this.endSeq.shown = true;
        if (this.onWin) this.onWin();
      }
    }
  };

  /* ---------------------------- pause ---------------------------- */
  Game.prototype.pause = function () {
    if (this.state !== STATE.PLAYING) return false;
    this.state = STATE.PAUSED;
    this.input.exitLock();
    this.audio.suspendBeds(true);
    return true;
  };
  Game.prototype.unpause = function () {
    if (this.state !== STATE.PAUSED) return;
    this.state = STATE.PLAYING;
    this.input.clearPresses();
    this.audio.suspendBeds(false);
    this.input.requestLock(document.body);
  };

  Game.prototype.summary = function () {
    var acc = this.stats.shots ? Math.round(this.stats.hits / this.stats.shots * 100) : 0;
    return {
      time: U.fmtTime(this.runTime),
      timeRaw: this.runTime,
      muskas: this.player ? this.player.muskas : 0,
      shots: this.stats.shots,
      hits: this.stats.hits,
      accuracy: acc,
      ammoLeft: this.weapon ? this.weapon.ammo : 0,
      notes: this.stats.notes,
      grabs: this.stats.grabs,
      distance: Math.round(this.stats.distance),
      difficulty: this.difficulty
    };
  };

  global.GGame = Game;
})(window);
