/* ==========================================================================
   GÜLYABANI — the pistol
   A suppressed 9mm with eight rounds and no reload. Modelled from
   primitives and drawn in its own overlay scene so it can never clip
   through a wall. Aiming down the sights is the only reliable way to put a
   round in the creature's head, and the head is the only thing that counts.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;

  var MAG = 8;

  function Weapon(audio, level) {
    this.audio = audio;
    this.level = level;
    this.ammo = MAG;
    this.max = MAG;

    this.ads = 0;            // 0 hip, 1 sights
    this.adsWant = false;
    this.recoil = 0;
    this.recoilRot = 0;
    this.slideBack = 0;
    this.slideLock = false;
    this.cooldown = 0;
    this.sway = new THREE.Vector2();
    this.swayVel = new THREE.Vector2();
    this.bobT = 0;
    this.flash = 0;
    this.kick = new THREE.Vector2();   // camera kick (pitch, yaw)
    this.kickVel = new THREE.Vector2();

    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(50, 1, 0.008, 12);
    this.root = new THREE.Group();
    this.scene.add(this.root);

    this._buildLights();
    this._buildModel();

    // Hip pose frames the whole pistol in the lower right third at a
    // believable arm's length. Aim pose subtracts the sight height, which
    // lands the notch and post exactly on the camera axis.
    this.HIP = new THREE.Vector3(0.163, -0.127, -0.600);
    this.AIM = new THREE.Vector3(0.0, -this.SIGHT_Y, -0.345);
    this.HIP_ROT = new THREE.Euler(0.022, -0.115, 0.030);
    this.AIM_ROT = new THREE.Euler(0, 0, 0);
  }

  Weapon.prototype._buildLights = function () {
    this.amb = new THREE.AmbientLight(0x5f6975, 0.14);
    this.scene.add(this.amb);

    // stands in for light bouncing back off whatever the torch is pointed at
    this.torch = new THREE.SpotLight(0xfff8ea, 0.0, 6, 0.75, 0.65, 1.4);
    this.torch.position.set(0.05, 0.02, 0.1);
    this.torch.target.position.set(0, -0.1, -1);
    this.scene.add(this.torch);
    this.scene.add(this.torch.target);

    this.fill = new THREE.DirectionalLight(0xbbcadb, 0.15);
    this.fill.position.set(-0.6, 0.9, 0.4);
    this.scene.add(this.fill);

    // a warm rim from below-left keeps the slide readable in the dark
    this.rim = new THREE.DirectionalLight(0xffe6c4, 0.12);
    this.rim.position.set(0.8, -0.5, 0.6);
    this.scene.add(this.rim);

    this.muzzleLight = new THREE.PointLight(0xffe9c2, 0, 1.4, 2);
    this.muzzleLight.position.set(0, 0.0, -0.44);
    this.root.add(this.muzzleLight);
  };

  Weapon.prototype._buildModel = function () {
    var steel = new THREE.MeshStandardMaterial({ color: 0x3e4147, roughness: 0.34, metalness: 0.86, envMapIntensity: 0.85 });
    var steelDark = new THREE.MeshStandardMaterial({ color: 0x2c2e33, roughness: 0.46, metalness: 0.80, envMapIntensity: 0.7 });
    var can = new THREE.MeshStandardMaterial({ color: 0x35383d, roughness: 0.60, metalness: 0.76, envMapIntensity: 0.65 });
    var grip = new THREE.MeshStandardMaterial({ color: 0x2c2e33, roughness: 0.92, metalness: 0.05, envMapIntensity: 0.3 });
    var brass = new THREE.MeshStandardMaterial({ color: 0xedd791, roughness: 0.28, metalness: 0.92, envMapIntensity: 1.8 });
    var white = new THREE.MeshStandardMaterial({
      color: 0xf7fafc, roughness: 0.4, metalness: 0.1,
      emissive: 0x8a9498, emissiveIntensity: 0.85
    });
    var skin = new THREE.MeshStandardMaterial({ color: 0x6f573f, roughness: 0.88, metalness: 0.0, envMapIntensity: 0.22 });
    var sleeve = new THREE.MeshStandardMaterial({ color: 0x353229, roughness: 0.97, metalness: 0.0, envMapIntensity: 0.15 });
    this.mats = [steel, steelDark, can, grip, brass, white, skin, sleeve];

    // The sight line. Rear notch and front post tip share this height, and
    // the aim pose cancels it so the sights land exactly on screen centre.
    var SIGHT_Y = 0.0445;
    this.SIGHT_Y = SIGHT_Y;

    var g = new THREE.Group();

    /* ------------------------------- frame ------------------------------- */
    g.add(mesh(new THREE.BoxGeometry(0.030, 0.030, 0.175), steelDark, 0, -0.024, -0.028));
    g.add(mesh(new THREE.BoxGeometry(0.026, 0.012, 0.10), steelDark, 0, -0.040, -0.075));

    /* ------------------------------- slide ------------------------------- */
    this.slide = new THREE.Group();
    this.slide.add(mesh(new THREE.BoxGeometry(0.032, 0.036, 0.185), steel, 0, 0.004, -0.030));
    this.slide.add(mesh(new THREE.BoxGeometry(0.024, 0.008, 0.185), steel, 0, 0.024, -0.030));
    for (var i = 0; i < 7; i++) {
      this.slide.add(mesh(new THREE.BoxGeometry(0.0335, 0.026, 0.0035), steelDark, 0, 0.004, 0.036 - i * 0.0085));
    }
    this.slide.add(mesh(new THREE.BoxGeometry(0.034, 0.017, 0.042), steelDark, 0.001, 0.010, -0.036));

    /* ------------------------------ sights ------------------------------ */
    // rear: a blade with a square notch. Blade tops, the front post tip and
    // all three dots sit on one line; two points at different distances only
    // line up on screen when both are at the camera height, which is exactly
    // what the aim pose arranges by subtracting the sight height.
    var rearY = SIGHT_Y - 0.008;
    this.slide.add(mesh(new THREE.BoxGeometry(0.011, 0.016, 0.008), steelDark, -0.0095, rearY, 0.030));
    this.slide.add(mesh(new THREE.BoxGeometry(0.011, 0.016, 0.008), steelDark, 0.0095, rearY, 0.030));
    this.slide.add(mesh(new THREE.BoxGeometry(0.030, 0.006, 0.008), steelDark, 0, rearY - 0.010, 0.030));
    for (var d = 0; d < 2; d++) {
      var dot = new THREE.Mesh(new THREE.SphereGeometry(0.0019, 6, 5), white);
      dot.position.set((d ? 1 : -1) * 0.0095, SIGHT_Y, 0.0265);
      this.slide.add(dot);
    }
    // front: a post whose tip sits on the same line
    this.slide.add(mesh(new THREE.BoxGeometry(0.0055, 0.024, 0.006), steelDark, 0, SIGHT_Y - 0.012, -0.118));
    var fdot = new THREE.Mesh(new THREE.SphereGeometry(0.0022, 6, 5), white);
    fdot.position.set(0, SIGHT_Y, -0.1205);
    this.slide.add(fdot);
    g.add(this.slide);

    /* ---------------------------- suppressor ---------------------------- */
    var canBody = new THREE.Mesh(new THREE.CylinderGeometry(0.0192, 0.0192, 0.205, 20), can);
    canBody.rotation.x = Math.PI / 2;
    canBody.position.set(0, 0.0035, -0.232);
    g.add(canBody);
    for (var r = 0; r < 6; r++) {
      var ring = new THREE.Mesh(new THREE.CylinderGeometry(0.0206, 0.0206, 0.0055, 20), steelDark);
      ring.rotation.x = Math.PI / 2;
      ring.position.set(0, 0.0035, -0.152 - r * 0.031);
      g.add(ring);
    }
    var cap = new THREE.Mesh(new THREE.CylinderGeometry(0.0192, 0.0175, 0.014, 20), steelDark);
    cap.rotation.x = Math.PI / 2;
    cap.position.set(0, 0.0035, -0.331);
    g.add(cap);
    var bore = new THREE.Mesh(new THREE.CylinderGeometry(0.0068, 0.0068, 0.02, 12),
      new THREE.MeshBasicMaterial({ color: 0x000000 }));
    bore.rotation.x = Math.PI / 2;
    bore.position.set(0, 0.0035, -0.335);
    g.add(bore);
    this.muzzlePos = new THREE.Vector3(0, 0.0035, -0.342);

    /* ------------------------------- grip ------------------------------- */
    var GRIP_TILT = -0.20;
    g.add(mesh(new THREE.BoxGeometry(0.030, 0.125, 0.048), grip, 0, -0.098, 0.028, GRIP_TILT));
    g.add(mesh(new THREE.BoxGeometry(0.031, 0.128, 0.010), steelDark, 0, -0.098, 0.052, GRIP_TILT));
    for (var c = 0; c < 6; c++) {
      g.add(mesh(new THREE.BoxGeometry(0.0315, 0.004, 0.046), steelDark,
        0, -0.052 - c * 0.017, 0.0245 + c * 0.0035, GRIP_TILT));
    }
    g.add(mesh(new THREE.BoxGeometry(0.033, 0.010, 0.050), steelDark, 0, -0.163, 0.041, GRIP_TILT));

    /* --------------------------- trigger group --------------------------- */
    var guard = new THREE.Mesh(new THREE.TorusGeometry(0.024, 0.0045, 6, 16, Math.PI * 1.15), steelDark);
    guard.rotation.set(Math.PI / 2, 0, 0.35);
    guard.position.set(0, -0.048, -0.004);
    g.add(guard);
    this.trigger = mesh(new THREE.BoxGeometry(0.007, 0.022, 0.005), steelDark, 0, -0.045, 0.004);
    g.add(this.trigger);
    this.hammer = mesh(new THREE.BoxGeometry(0.008, 0.020, 0.007), steelDark, 0, -0.004, 0.062);
    g.add(this.hammer);

    /* ------------------------- the hand and arm -------------------------
       A bare floating fist reads as a bug. What sells it is the forearm
       running out of frame in a dark sleeve, with the fingers actually
       wrapped around the front of the grip rather than stuck to it.      */
    var hand = new THREE.Group();
    hand.rotation.x = GRIP_TILT;

    // heel of the hand behind the backstrap
    hand.add(mesh(new THREE.BoxGeometry(0.040, 0.086, 0.036), skin, 0.002, -0.104, 0.068));
    // the meat of the palm hugging the right side of the grip
    hand.add(mesh(new THREE.BoxGeometry(0.020, 0.090, 0.052), skin, 0.024, -0.100, 0.040));
    // knuckles, then four fingers curling round the front strap
    hand.add(mesh(new THREE.BoxGeometry(0.026, 0.072, 0.020), skin, 0.020, -0.072, 0.006));
    for (var f = 0; f < 4; f++) {
      var fy = -0.056 - f * 0.021;
      var fw = 0.019 - f * 0.0015;
      hand.add(mesh(new THREE.BoxGeometry(0.030, fw, 0.030), skin, 0.008, fy, 0.006, 0.06 * f));
      // fingertip curling back toward the palm
      hand.add(mesh(new THREE.BoxGeometry(0.016, fw, 0.018), skin, -0.012, fy - 0.002, 0.012));
    }
    // thumb laid along the frame
    var thumb = mesh(new THREE.BoxGeometry(0.016, 0.050, 0.020), skin, -0.020, -0.066, 0.036);
    thumb.rotation.set(0.30, 0, 0.42);
    hand.add(thumb);

    // Wrist only. A full forearm cannot work here: on the aim pose the gun
    // comes to within 35 cm of the eye, and anything trailing back from the
    // wrist ends up in front of the lens. So the arm stops at a dark cuff.
    var cuff = new THREE.Mesh(new THREE.CylinderGeometry(0.044, 0.050, 0.075, 12), sleeve);
    cuff.position.set(0.014, -0.156, 0.074);
    cuff.rotation.set(-0.40, 0, -0.12);
    hand.add(cuff);

    g.add(hand);
    this.hand = hand;

    g.traverse(function (o) { if (o.isMesh) { o.castShadow = false; o.receiveShadow = false; } });
    this.model = g;
    this.root.add(g);

    /* ---------------------------- muzzle flash ---------------------------- */
    var flashMat = new THREE.SpriteMaterial({
      map: global.GTX.glowSprite('rgb(255,206,140)', 0.16),
      color: 0xffe1b1, transparent: true, opacity: 0,
      blending: THREE.AdditiveBlending, depthWrite: false, depthTest: false
    });
    this.flashSprite = new THREE.Sprite(flashMat);
    this.flashSprite.scale.set(0.14, 0.14, 1);
    this.flashSprite.position.copy(this.muzzlePos);
    this.root.add(this.flashSprite);

    var smokeMat = new THREE.SpriteMaterial({
      map: global.GTX.smokeSprite(7), color: 0xccd0d4,
      transparent: true, opacity: 0, depthWrite: false, depthTest: false
    });
    this.smoke = new THREE.Sprite(smokeMat);
    this.smoke.scale.set(0.1, 0.1, 1);
    this.smoke.position.copy(this.muzzlePos);
    this.root.add(this.smoke);
    this.smokeT = 0;

    /* -------------------------------- brass -------------------------------- */
    this.shells = [];
    var shellGeo = new THREE.CylinderGeometry(0.0047, 0.0047, 0.019, 8);
    for (var sI = 0; sI < 4; sI++) {
      var sh = new THREE.Mesh(shellGeo, brass);
      sh.visible = false;
      this.scene.add(sh);
      this.shells.push({ mesh: sh, life: 0, vel: new THREE.Vector3(), spin: new THREE.Vector3() });
    }

    function mesh(geo, mat, x, y, z, rx) {
      var m = new THREE.Mesh(geo, mat);
      m.position.set(x, y, z);
      if (rx) m.rotation.x = rx;
      return m;
    }
  };

  /* ------------------------------ firing ------------------------------ */
  Weapon.prototype.canFire = function () {
    return this.ammo > 0 && this.cooldown <= 0;
  };

  Weapon.prototype.spread = function () {
    // sights bring it to nothing; hip fire is a prayer
    return U.lerp(0.031, 0.0016, U.smootherstep(this.ads));
  };

  Weapon.prototype.fire = function (rnd) {
    if (this.cooldown > 0) return null;
    if (this.ammo <= 0) {
      this.cooldown = 0.28;
      this.slideLock = true;
      this.audio.dryfire();
      return { empty: true };
    }
    this.ammo--;
    this.cooldown = 0.19;
    this.recoil = 1;
    this.recoilRot = 1;
    this.slideBack = 1;
    this.flash = 1;
    this.smokeT = 1;
    this.audio.shot();

    var kickUp = U.lerp(0.030, 0.017, this.ads);
    this.kickVel.x += kickUp + Math.random() * 0.008;
    this.kickVel.y += (Math.random() - 0.5) * 0.014;

    if (this.ammo === 0) this.slideLock = true;
    this._ejectShell();

    var sp = this.spread();
    return {
      empty: false,
      spreadX: (Math.random() * 2 - 1) * sp,
      spreadY: (Math.random() * 2 - 1) * sp
    };
  };

  Weapon.prototype._ejectShell = function () {
    for (var i = 0; i < this.shells.length; i++) {
      var s = this.shells[i];
      if (s.life > 0) continue;
      s.life = 0.7;
      s.mesh.visible = true;
      s.mesh.position.set(this.root.position.x + 0.03, this.root.position.y + 0.02, this.root.position.z + 0.03);
      s.mesh.rotation.set(0, 0, Math.PI / 2);
      s.vel.set(0.62 + Math.random() * 0.3, 0.52 + Math.random() * 0.3, 0.42 + Math.random() * 0.25);
      s.spin.set(Math.random() * 22 - 11, Math.random() * 22 - 11, Math.random() * 22 - 11);
      return;
    }
  };

  /* ------------------------------ update ------------------------------ */
  Weapon.prototype.update = function (dt, player, input, torchOn) {
    var inp = input;
    this.adsWant = (inp.mouse.right || inp.touch.ads) && !player.grabbed;
    this.ads = U.damp(this.ads, this.adsWant ? 1 : 0, 13, dt);

    if (this.cooldown > 0) this.cooldown -= dt;
    this.recoil = U.damp(this.recoil, 0, 9, dt);
    this.recoilRot = U.damp(this.recoilRot, 0, 7.5, dt);
    this.slideBack = U.damp(this.slideBack, this.slideLock ? 0.72 : 0, 26, dt);
    this.flash = Math.max(0, this.flash - dt * 22);
    this.smokeT = Math.max(0, this.smokeT - dt * 1.05);

    // camera kick spring
    this.kick.x += this.kickVel.x;
    this.kick.y += this.kickVel.y;
    this.kickVel.multiplyScalar(Math.pow(0.0001, dt));
    this.kick.x = U.damp(this.kick.x, 0, 6.5, dt);
    this.kick.y = U.damp(this.kick.y, 0, 6.5, dt);

    // sway from looking around, damped harder when aiming
    var swayScale = U.lerp(0.00055, 0.00013, this.ads);
    this.swayVel.x += -inp.mouseDX * swayScale;
    this.swayVel.y += inp.mouseDY * swayScale;
    this.swayVel.multiplyScalar(Math.pow(0.0015, dt));
    this.sway.x = U.clamp(U.damp(this.sway.x + this.swayVel.x, 0, 5, dt), -0.05, 0.05);
    this.sway.y = U.clamp(U.damp(this.sway.y + this.swayVel.y, 0, 5, dt), -0.05, 0.05);

    // walking bob for the weapon, mostly suppressed while aiming
    var moving = player.speed > 0.35;
    if (moving) this.bobT += dt * (player.speed / 1.35) * Math.PI * 2;
    var bAmp = U.clamp01(player.speed / 5.15) * U.lerp(1, 0.22, this.ads) * (player.crouching ? 0.5 : 1);
    var bobX = Math.cos(this.bobT) * 0.016 * bAmp;
    var bobY = Math.sin(this.bobT * 2) * 0.011 * bAmp;
    var lowerReady = U.clamp01(player.speed / 5.15) * (player.sprinting ? 1 : 0);

    // pose
    var t = U.smootherstep(this.ads);
    var px = U.lerp(this.HIP.x, this.AIM.x, t) + this.sway.x + bobX;
    var py = U.lerp(this.HIP.y, this.AIM.y, t) + this.sway.y + bobY - lowerReady * 0.045;
    var pz = U.lerp(this.HIP.z, this.AIM.z, t) + this.recoil * 0.030;
    this.root.position.set(px, py, pz);

    var rx = U.lerp(this.HIP_ROT.x, this.AIM_ROT.x, t) - this.recoilRot * 0.16 + bobY * 0.6;
    var ry = U.lerp(this.HIP_ROT.y, this.AIM_ROT.y, t) - this.sway.x * 2.4;
    var rz = U.lerp(this.HIP_ROT.z, this.AIM_ROT.z, t) + this.sway.x * 1.6 - lowerReady * 0.42;
    this.root.rotation.set(rx, ry, rz);

    // slide travel + hammer + trigger
    this.slide.position.z = this.slideBack * 0.026;
    this.hammer.rotation.x = -this.slideBack * 1.1;
    this.trigger.position.z = 0.004 + (this.cooldown > 0.08 ? 0.006 : 0);

    // flash + light
    this.flashSprite.material.opacity = this.flash * 0.85;
    this.flashSprite.scale.setScalar(0.10 + (1 - this.flash) * 0.06);
    this.muzzleLight.intensity = this.flash * 2.6;
    this.smoke.material.opacity = this.smokeT * 0.22;
    this.smoke.scale.setScalar(0.09 + (1 - this.smokeT) * 0.20);
    this.smoke.position.set(
      this.muzzlePos.x, this.muzzlePos.y + (1 - this.smokeT) * 0.06,
      this.muzzlePos.z - (1 - this.smokeT) * 0.03
    );

    // torch bounce on the model
    this.torch.intensity = U.damp(this.torch.intensity, torchOn ? 0.58 : 0.0, 8, dt);
    this.amb.intensity = U.damp(this.amb.intensity, torchOn ? 0.21 : 0.09, 6, dt);
    this.rim.intensity = U.damp(this.rim.intensity, torchOn ? 0.16 : 0.06, 6, dt);

    // brass
    for (var i = 0; i < this.shells.length; i++) {
      var s = this.shells[i];
      if (s.life <= 0) continue;
      s.life -= dt;
      if (s.life <= 0) { s.mesh.visible = false; continue; }
      s.vel.y -= 4.6 * dt;
      s.mesh.position.addScaledVector(s.vel, dt);
      s.mesh.rotation.x += s.spin.x * dt;
      s.mesh.rotation.y += s.spin.y * dt;
      s.mesh.rotation.z += s.spin.z * dt;
    }
  };

  Weapon.prototype.setFov = function (fov) {
    // narrow the viewmodel camera slightly under ADS for a subtle zoom
    this.camera.fov = fov;
    this.camera.updateProjectionMatrix();
  };

  Weapon.prototype.resize = function (aspect) {
    this.camera.aspect = aspect;
    this.camera.updateProjectionMatrix();
  };

  Weapon.prototype.reset = function () {
    this.ammo = MAG;
    this.slideLock = false;
    this.slideBack = 0;
    this.ads = 0;
    this.kick.set(0, 0); this.kickVel.set(0, 0);
    for (var i = 0; i < this.shells.length; i++) {
      this.shells[i].life = 0;
      this.shells[i].mesh.visible = false;
    }
  };

  Weapon.prototype.dispose = function () {
    this.model.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
    this.mats.forEach(function (m) { m.dispose(); });
  };

  Weapon.MAG = MAG;
  global.GWeapon = Weapon;
})(window);
