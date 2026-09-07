/* ==========================================================================
   GÜLYABANI — input and the player
   Movement, collision, crouch/sprint, head bob, the flashlight (which is
   both your only real tool and the thing that makes you visible), and the
   two meters the whole game is balanced around: Nefes and Akıl.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;

  /* ================================ INPUT ================================ */
  function Input() {
    this.keys = {};
    this.mouseDX = 0; this.mouseDY = 0;
    this.mouse = { left: false, right: false };
    this.locked = false;
    this.sensitivity = 1.3;
    this.invertY = false;
    this.touch = {
      active: false, moveX: 0, moveY: 0,
      lookDX: 0, lookDY: 0, fire: false, ads: false, sprint: false
    };
    this._pressed = {};
    this._bind();
  }

  Input.prototype._bind = function () {
    var self = this;

    window.addEventListener('keydown', function (e) {
      if (e.repeat) { return; }
      var k = e.code;
      self.keys[k] = true;
      self._pressed[k] = true;
      if (['Space', 'ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'Tab'].indexOf(k) >= 0) e.preventDefault();
    }, { passive: false });

    window.addEventListener('keyup', function (e) { self.keys[e.code] = false; });
    window.addEventListener('blur', function () { self.keys = {}; self.mouse.left = self.mouse.right = false; });

    document.addEventListener('mousemove', function (e) {
      if (!self.locked) return;
      self.mouseDX += e.movementX || 0;
      self.mouseDY += e.movementY || 0;
    });

    document.addEventListener('mousedown', function (e) {
      if (!self.locked) return;
      if (e.button === 0) self.mouse.left = true;
      if (e.button === 2) self.mouse.right = true;
    });
    document.addEventListener('mouseup', function (e) {
      if (e.button === 0) self.mouse.left = false;
      if (e.button === 2) self.mouse.right = false;
    });
    document.addEventListener('contextmenu', function (e) { e.preventDefault(); });

    document.addEventListener('pointerlockchange', function () {
      self.locked = document.pointerLockElement === document.body ||
        document.pointerLockElement === document.getElementById('stage') ||
        !!document.pointerLockElement;
      if (self.onLockChange) self.onLockChange(self.locked);
    });
  };

  /** True once per press. */
  Input.prototype.pressed = function (code) {
    if (this._pressed[code]) { this._pressed[code] = false; return true; }
    return false;
  };
  Input.prototype.down = function (code) { return !!this.keys[code]; };
  Input.prototype.clearFrame = function () {
    this.mouseDX = 0; this.mouseDY = 0;
    this.touch.lookDX = 0; this.touch.lookDY = 0;
  };
  Input.prototype.clearPresses = function () { this._pressed = {}; };

  Input.prototype.requestLock = function (el) {
    var t = el || document.body;
    if (t.requestPointerLock) {
      var p = t.requestPointerLock();
      if (p && p.catch) p.catch(function () { });
    }
  };
  Input.prototype.exitLock = function () {
    if (document.exitPointerLock) document.exitPointerLock();
  };

  /* =============================== PLAYER =============================== */
  var EYE_STAND = 1.68, EYE_CROUCH = 1.02;
  var RADIUS = 0.32;

  function Player(level, input, audio, difficulty) {
    this.level = level;
    this.input = input;
    this.audio = audio;
    this.difficulty = difficulty || 1;

    this.pos = new THREE.Vector3();
    this.vel = new THREE.Vector3();
    this.yaw = 0; this.pitch = 0;

    this.eye = EYE_STAND;
    this.crouching = false;
    this.sprinting = false;
    this.speed = 0;

    this.stamina = 1;
    this.sanity = 1;
    this.battery = 1;
    this.lightOn = true;
    this.stones = 3;
    this.muskas = 0;
    this.notesRead = [];
    this.alive = true;

    this.bobT = 0;
    this.bobAmp = 0;
    this.stepAcc = 0;
    this.headOffset = new THREE.Vector3();
    this.roll = 0;
    this.shake = 0;
    this.shakeSeed = Math.random() * 100;

    this.fear = 0;        // 0..1 immediate dread
    this.hurtT = 0;
    this.senseT = 0;      // "muska sense" cooldown / active timer
    this.grabbed = false;

    this._tmp = new THREE.Vector3();
    this._res = { x: 0, z: 0 };
    this._fwd = new THREE.Vector3();
    this._right = new THREE.Vector3();

    // difficulty knobs
    var D = [
      { drain: 0.0068, sanityRate: 0.055, staminaDrain: 0.185, staminaRegen: 0.135 },
      { drain: 0.0092, sanityRate: 0.075, staminaDrain: 0.215, staminaRegen: 0.115 },
      { drain: 0.0125, sanityRate: 0.105, staminaDrain: 0.255, staminaRegen: 0.092 }
    ][this.difficulty];
    this.D = D;
  }

  Player.prototype.spawn = function (cx, cy, yaw) {
    this.pos.set(this.level.cellX(cx), 0, this.level.cellZ(cy));
    this.yaw = yaw || 0;
    this.pitch = 0;
  };

  Player.prototype.eyePos = function (out) {
    out = out || new THREE.Vector3();
    out.copy(this.pos);
    out.y += this.eye;
    out.add(this.headOffset);
    return out;
  };

  Player.prototype.forward = function (out) {
    out = out || new THREE.Vector3();
    out.set(-Math.sin(this.yaw) * Math.cos(this.pitch), Math.sin(this.pitch), -Math.cos(this.yaw) * Math.cos(this.pitch));
    return out;
  };

  /* ------------------------------- update ------------------------------- */
  Player.prototype.update = function (dt, ctx) {
    var inp = this.input;

    /* ---- look ---- */
    if (!this.grabbed) {
      var sens = inp.sensitivity * 0.0016;
      this.yaw -= inp.mouseDX * sens;
      this.pitch -= (inp.invertY ? -1 : 1) * inp.mouseDY * sens;
      this.yaw -= inp.touch.lookDX * sens * 1.35;
      this.pitch -= inp.touch.lookDY * sens * 1.35;
    } else {
      // during a grab the camera is dragged toward the creature
      var want = Math.atan2(-(ctx.ghostPos.x - this.pos.x), -(ctx.ghostPos.z - this.pos.z));
      this.yaw = U.dampAngle(this.yaw, want, 7, dt);
      this.pitch = U.damp(this.pitch, 0.12, 6, dt);
    }
    this.pitch = U.clamp(this.pitch, -1.35, 1.35);

    /* ---- movement intent ---- */
    var mf = 0, ms = 0;
    if (!this.grabbed) {
      if (inp.down('KeyW') || inp.down('ArrowUp')) mf += 1;
      if (inp.down('KeyS') || inp.down('ArrowDown')) mf -= 1;
      if (inp.down('KeyD') || inp.down('ArrowRight')) ms += 1;
      if (inp.down('KeyA') || inp.down('ArrowLeft')) ms -= 1;
      mf += inp.touch.moveY; ms += inp.touch.moveX;
    }
    var mag = Math.hypot(mf, ms);
    if (mag > 1) { mf /= mag; ms /= mag; }

    /* ---- crouch ---- */
    var wantCrouch = inp.down('ControlLeft') || inp.down('KeyC') || inp.down('ControlRight');
    this.crouching = wantCrouch && !this.grabbed;
    var targetEye = this.crouching ? EYE_CROUCH : EYE_STAND;
    this.eye = U.damp(this.eye, targetEye, 11, dt);

    /* ---- sprint ---- */
    var wantSprint = (inp.down('ShiftLeft') || inp.down('ShiftRight') || inp.touch.sprint) &&
      mf > 0.15 && !this.crouching && this.stamina > 0.03 && !this.grabbed;
    this.sprinting = wantSprint;

    if (this.sprinting) {
      this.stamina = Math.max(0, this.stamina - this.D.staminaDrain * dt);
    } else {
      var regen = this.D.staminaRegen * (this.crouching ? 1.7 : (mag > 0.1 ? 0.75 : 1.35));
      this.stamina = Math.min(1, this.stamina + regen * dt);
    }

    var base = this.crouching ? 1.55 : 3.05;
    if (this.sprinting) base = 5.15;
    // exhaustion bites
    if (this.stamina < 0.16) base *= U.lerp(0.62, 1, this.stamina / 0.16);
    // fear makes your legs heavy
    base *= U.lerp(1, 0.9, U.clamp01(this.fear));

    /* ---- integrate ---- */
    var cy = Math.cos(this.yaw), sy = Math.sin(this.yaw);
    var wishX = (-sy * mf) + (cy * ms);
    var wishZ = (-cy * mf) + (-sy * ms);
    var accel = 34, decel = 22;
    var targetVX = wishX * base, targetVZ = wishZ * base;
    var rate = (mag > 0.05) ? accel : decel;
    this.vel.x = U.damp(this.vel.x, this.grabbed ? 0 : targetVX, rate * 0.35, dt);
    this.vel.z = U.damp(this.vel.z, this.grabbed ? 0 : targetVZ, rate * 0.35, dt);

    var nx = this.pos.x + this.vel.x * dt;
    var nz = this.pos.z + this.vel.z * dt;
    this.level.resolve(nx, nz, RADIUS, this._res);
    // if collision changed our position, kill the velocity into the wall
    var corrX = this._res.x - nx, corrZ = this._res.z - nz;
    if (Math.abs(corrX) > 1e-6 || Math.abs(corrZ) > 1e-6) {
      var cl = Math.hypot(corrX, corrZ);
      var cnx = corrX / cl, cnz = corrZ / cl;
      var into = this.vel.x * cnx + this.vel.z * cnz;
      if (into < 0) { this.vel.x -= cnx * into; this.vel.z -= cnz * into; }
    }
    this.pos.x = this._res.x; this.pos.z = this._res.z;

    this.speed = Math.hypot(this.vel.x, this.vel.z);

    /* ---- head bob + footsteps ---- */
    var moving = this.speed > 0.35;
    var stepLen = this.sprinting ? 1.55 : (this.crouching ? 1.15 : 1.35);
    if (moving) {
      this.stepAcc += this.speed * dt;
      this.bobT += dt * (this.speed / stepLen) * Math.PI * 2;
      if (this.stepAcc >= stepLen) {
        this.stepAcc -= stepLen;
        var surf = this.level.surfaceAt(this.pos.x, this.pos.z);
        var vol = this.crouching ? 0.28 : (this.sprinting ? 1.0 : 0.62);
        this.audio.footstep(surf, vol, null);
        if (ctx.onFootstep) ctx.onFootstep(vol);
      }
    } else {
      this.bobT = U.damp(this.bobT, Math.round(this.bobT / Math.PI) * Math.PI, 6, dt);
    }
    var bobTarget = moving ? U.clamp01(this.speed / 5.15) : 0;
    this.bobAmp = U.damp(this.bobAmp, bobTarget, 7, dt);

    var amp = this.bobAmp * (this.crouching ? 0.5 : 1);
    var bobY = Math.sin(this.bobT * 2) * 0.036 * amp;
    var bobX = Math.cos(this.bobT) * 0.045 * amp;
    // breathing when still
    var breathe = Math.sin(performance.now() * 0.0011) * 0.008 * (1 - this.bobAmp) * (1 + (1 - this.stamina));
    this.headOffset.set(
      bobX * Math.cos(this.yaw), bobY + breathe, -bobX * Math.sin(this.yaw)
    );
    this.roll = U.damp(this.roll, -Math.cos(this.bobT) * 0.011 * amp + (-ms * 0.016), 9, dt);

    /* ---- shake ---- */
    if (this.shake > 0) this.shake = Math.max(0, this.shake - dt * 2.2);

    /* ---- flashlight ---- */
    if (inp.pressed('KeyF') && !this.grabbed) this.toggleLight();
    if (this.lightOn && this.battery > 0) {
      this.battery = Math.max(0, this.battery - this.D.drain * dt);
      if (this.battery <= 0) {
        this.lightOn = false;
        this.audio.batteryClick();
        if (ctx.onToast) ctx.onToast('Die Batterie ist leer.', true);
      }
    }

    /* ---- sanity ---- */
    var lit = this.lightOn && this.battery > 0;
    var nearLight = ctx.nearLight || 0;      // 0..1 from candle proximity
    var darkness = U.clamp01(1 - Math.max(lit ? 0.85 : 0, nearLight));
    var proxFear = ctx.ghostDist === undefined ? 0 : U.clamp01(1 - (ctx.ghostDist - 2.5) / 15);
    var seenFear = ctx.ghostVisible ? 0.55 : 0;
    this.fear = U.damp(this.fear, U.clamp01(Math.max(proxFear, proxFear * 0.5 + seenFear) + darkness * 0.22), 3.2, dt);

    var drain = this.fear * this.D.sanityRate * 1.9 + darkness * this.D.sanityRate * 0.55;
    var recover = (1 - this.fear) * (lit || nearLight > 0.4 ? 0.055 : 0.012);
    this.sanity = U.clamp01(this.sanity - drain * dt + recover * dt);

    if (this.hurtT > 0) this.hurtT = Math.max(0, this.hurtT - dt * 1.4);
    if (this.senseT > 0) this.senseT = Math.max(0, this.senseT - dt);

    inp.clearFrame();
  };

  Player.prototype.toggleLight = function () {
    if (this.battery <= 0) { this.audio.batteryClick(); return; }
    this.lightOn = !this.lightOn;
    this.audio.batteryClick();
  };

  Player.prototype.addBattery = function (amount) {
    this.battery = U.clamp01(this.battery + amount);
  };

  Player.prototype.hurt = function (amount) {
    this.hurtT = Math.min(1, this.hurtT + amount);
    this.sanity = U.clamp01(this.sanity - amount * 0.35);
    this.shake = Math.min(1.4, this.shake + amount);
    this.audio.hurt();
  };

  /** Camera shake offset, sampled from noise so it never loops audibly. */
  Player.prototype.shakeOffset = function (t, out) {
    var s = this.shake;
    if (s <= 0.0005) { out.set(0, 0, 0); return 0; }
    var k = s * s * 0.14;
    out.set(
      (U.noise2(t * 21, this.shakeSeed, 1) - 0.5) * k,
      (U.noise2(t * 24, this.shakeSeed + 40, 2) - 0.5) * k,
      (U.noise2(t * 19, this.shakeSeed + 80, 3) - 0.5) * k
    );
    return s;
  };

  Player.RADIUS = RADIUS;
  Player.EYE_STAND = EYE_STAND;
  global.GInput = Input;
  global.GPlayer = Player;
})(window);
