/* ==========================================================================
   GÜLYABANI — the thing behind you
   Two and a half metres of hair, chains and patience. It always knows
   roughly where you are, so there is no hiding: the only currencies are
   distance and time. A round through the skull buys both — it is thrown
   back, slowed hard for several seconds, and permanently a little slower
   for the rest of the run. Anywhere else the bullet simply passes through.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;
  var TX = global.GTX;

  var STATE = { HUNT: 0, INVESTIGATE: 1, STAGGER: 2, GRAB: 3, BREAK: 4 };

  function Ghost(level, audio, difficulty) {
    this.level = level;
    this.audio = audio;
    this.difficulty = difficulty || 1;

    // Speeds are set against the player: walk 3.05, sprint 5.15 m/s.
    // Below walking pace and it can never close; above sprint and stamina
    // stops mattering. Dehset sits just under a walk so it gains ground
    // every time you stop to search, which is the whole loop.
    var D = [
      { speed: 2.50, stagger: 7.2, perm: 0.855, accel: 5.0, breakTime: 2.2 },
      { speed: 2.95, stagger: 6.0, perm: 0.882, accel: 6.0, breakTime: 1.7 },
      { speed: 3.40, stagger: 4.8, perm: 0.905, accel: 7.0, breakTime: 1.25 }
    ][this.difficulty];
    this.D = D;

    this.baseSpeed = D.speed;
    this.permMul = 1;            // cumulative slow from headshots
    this.slowMul = 1;            // temporary slow
    this.state = STATE.HUNT;
    this.stateT = 0;
    this.hits = 0;

    this.pos = new THREE.Vector3();
    this.vel = new THREE.Vector3();
    this.facing = 0;
    this.speed = 0;
    this.walkPhase = 0;
    this.pathTimer = 0;
    this.path = null;
    this.pathIdx = 0;
    this.target = new THREE.Vector3();
    this.noisePoint = null;
    this.growlTimer = 3;
    this.stepAcc = 0;
    this.breakDoor = null;
    this.visible = false;
    this.distToPlayer = 99;
    this.headWorld = new THREE.Vector3();
    this.knock = new THREE.Vector3();

    this._res = { x: 0, z: 0 };
    this._v = new THREE.Vector3();

    this.group = new THREE.Group();
    this._build();
  }

  Ghost.STATE = STATE;

  /* ------------------------------- model ------------------------------- */
  Ghost.prototype._build = function () {
    // It must stay a silhouette in the dark but pick up enough of the torch
    // to be aimable at ten metres. These values are the whole balance.
    var hide = new THREE.MeshStandardMaterial({
      color: 0x24242b, roughness: 0.98, metalness: 0.0, envMapIntensity: 0.12
    });
    var hair = new THREE.MeshStandardMaterial({
      color: 0x2c2830, roughness: 1.0, metalness: 0.0, flatShading: true, envMapIntensity: 0.1
    });
    var skin = new THREE.MeshStandardMaterial({
      color: 0x6b5a4c, roughness: 0.90, metalness: 0.0, envMapIntensity: 0.25
    });
    var iron = new THREE.MeshStandardMaterial({ color: 0x6a6e77, roughness: 0.62, metalness: 0.78, envMapIntensity: 0.55 });
    var eyeMat = new THREE.MeshBasicMaterial({ color: 0xffad71 });
    this.mats = [hide, hair, skin, iron, eyeMat];

    var body = new THREE.Group();
    this.body = body;
    this.group.add(body);

    // --- legs: long, thin, backwards-kneed ---
    this.legs = [];
    for (var i = 0; i < 2; i++) {
      var s = i ? 1 : -1;
      var hip = new THREE.Group();
      hip.position.set(s * 0.16, 1.06, 0);
      var thigh = new THREE.Mesh(new THREE.CylinderGeometry(0.075, 0.058, 0.56, 7), hide);
      thigh.position.y = -0.28; thigh.castShadow = true;
      hip.add(thigh);
      var knee = new THREE.Group();
      knee.position.y = -0.56;
      var shin = new THREE.Mesh(new THREE.CylinderGeometry(0.056, 0.042, 0.52, 7), hide);
      shin.position.y = -0.26; shin.castShadow = true;
      knee.add(shin);
      var foot = new THREE.Mesh(new THREE.BoxGeometry(0.12, 0.06, 0.27), hide);
      foot.position.set(0, -0.53, 0.06); foot.castShadow = true;
      knee.add(foot);
      hip.add(knee);
      body.add(hip);
      this.legs.push({ hip: hip, knee: knee });
    }

    // --- torso: narrow, hunched ---
    var pelvis = new THREE.Mesh(new THREE.CylinderGeometry(0.20, 0.17, 0.30, 8), hide);
    pelvis.position.y = 1.18; pelvis.castShadow = true;
    body.add(pelvis);

    this.chest = new THREE.Group();
    this.chest.position.y = 1.34;
    var torso = new THREE.Mesh(new THREE.CylinderGeometry(0.235, 0.20, 0.72, 9), hide);
    torso.position.y = 0.34; torso.castShadow = true;
    this.chest.add(torso);
    // ribs pushing through the hide
    for (var r = 0; r < 4; r++) {
      var rib = new THREE.Mesh(new THREE.TorusGeometry(0.20 - r * 0.012, 0.016, 5, 10, Math.PI), hide);
      rib.rotation.set(Math.PI / 2, 0, 0);
      rib.position.set(0, 0.18 + r * 0.13, -0.02);
      this.chest.add(rib);
    }
    // matted fur across the shoulders
    for (var f = 0; f < 16; f++) {
      var a = (f / 16) * Math.PI * 2;
      var tuft = new THREE.Mesh(new THREE.ConeGeometry(0.05, 0.30 + Math.random() * 0.22, 4), hair);
      tuft.position.set(Math.cos(a) * 0.21, 0.62 + Math.random() * 0.08, Math.sin(a) * 0.19);
      tuft.rotation.set(Math.random() * 0.5 - 0.25, a, Math.PI + (Math.random() - 0.5) * 0.6);
      tuft.castShadow = true;
      this.chest.add(tuft);
    }
    body.add(this.chest);

    // --- neck + head: the only target that matters ---
    this.neck = new THREE.Group();
    this.neck.position.y = 0.70;
    var neckMesh = new THREE.Mesh(new THREE.CylinderGeometry(0.062, 0.085, 0.20, 7), skin);
    neckMesh.position.y = 0.09; neckMesh.castShadow = true;
    this.neck.add(neckMesh);

    this.head = new THREE.Group();
    this.head.position.y = 0.20;
    var skull = new THREE.Mesh(new THREE.SphereGeometry(0.175, 12, 10), skin);
    skull.scale.set(0.94, 1.16, 1.0);
    skull.position.y = 0.15;
    skull.castShadow = true;
    this.head.add(skull);
    var jaw = new THREE.Mesh(new THREE.BoxGeometry(0.16, 0.11, 0.15), skin);
    jaw.position.set(0, 0.045, 0.055);
    this.jaw = jaw;
    this.head.add(jaw);
    // teeth
    for (var tI = 0; tI < 6; tI++) {
      var tooth = new THREE.Mesh(new THREE.ConeGeometry(0.013, 0.045, 4),
        new THREE.MeshStandardMaterial({ color: 0xc9bfa4, roughness: 0.8, envMapIntensity: 0.4 }));
      tooth.position.set(-0.055 + tI * 0.022, 0.09, 0.125);
      tooth.rotation.x = Math.PI;
      this.head.add(tooth);
    }
    // long matted hair hanging over the face
    for (var h = 0; h < 22; h++) {
      var ha = (h / 22) * Math.PI * 2;
      var strand = new THREE.Mesh(new THREE.ConeGeometry(0.026, 0.42 + Math.random() * 0.3, 4), hair);
      strand.position.set(Math.cos(ha) * 0.16, 0.10 - Math.random() * 0.1, Math.sin(ha) * 0.15);
      strand.rotation.set((Math.random() - 0.5) * 0.5, ha, Math.PI + (Math.random() - 0.5) * 0.5);
      strand.castShadow = true;
      this.head.add(strand);
    }
    // the eyes: two coals. They are how you find it in the dark.
    this.eyes = [];
    for (var e = 0; e < 2; e++) {
      var eye = new THREE.Mesh(new THREE.SphereGeometry(0.030, 8, 6), eyeMat);
      eye.position.set((e ? 1 : -1) * 0.062, 0.175, 0.135);
      this.head.add(eye);
      this.eyes.push(eye);
    }
    this.eyeGlow = new THREE.PointLight(0xffa063, 0.55, 3.4, 2);
    this.eyeGlow.position.set(0, 0.175, 0.2);
    this.head.add(this.eyeGlow);
    for (var eg = 0; eg < 2; eg++) {
      var spr = new THREE.Sprite(new THREE.SpriteMaterial({
        map: TX.glowSprite('rgb(255,110,40)', 0.14), color: 0xffb878,
        transparent: true, opacity: 0.85, blending: THREE.AdditiveBlending,
        depthWrite: false
      }));
      spr.scale.set(0.17, 0.17, 1);
      spr.position.set((eg ? 1 : -1) * 0.062, 0.175, 0.15);
      this.head.add(spr);
      this.eyes.push(spr);
    }

    this.neck.add(this.head);
    this.chest.add(this.neck);

    // --- arms: too long by half ---
    this.arms = [];
    for (var ai = 0; ai < 2; ai++) {
      var sgn = ai ? 1 : -1;
      var sh = new THREE.Group();
      sh.position.set(sgn * 0.245, 0.60, 0);
      var upper = new THREE.Mesh(new THREE.CylinderGeometry(0.062, 0.05, 0.58, 7), hide);
      upper.position.y = -0.29; upper.castShadow = true;
      sh.add(upper);
      var elbow = new THREE.Group();
      elbow.position.y = -0.58;
      var fore = new THREE.Mesh(new THREE.CylinderGeometry(0.048, 0.036, 0.56, 7), hide);
      fore.position.y = -0.28; fore.castShadow = true;
      elbow.add(fore);
      var handG = new THREE.Group();
      handG.position.y = -0.56;
      var palm = new THREE.Mesh(new THREE.BoxGeometry(0.085, 0.10, 0.045), skin);
      palm.position.y = -0.05;
      handG.add(palm);
      for (var fi = 0; fi < 4; fi++) {
        var finger = new THREE.Mesh(new THREE.CylinderGeometry(0.011, 0.006, 0.24, 5), skin);
        finger.position.set(-0.033 + fi * 0.022, -0.20, 0.005);
        finger.rotation.x = 0.25;
        handG.add(finger);
      }
      elbow.add(handG);
      sh.add(elbow);
      this.chest.add(sh);
      this.arms.push({ shoulder: sh, elbow: elbow, hand: handG });
    }

    // --- the staff, struck against the floor as it walks ---
    var staff = new THREE.Mesh(new THREE.CylinderGeometry(0.028, 0.034, 2.05, 6), hide);
    staff.position.set(0, -0.85, 0.02);
    staff.rotation.x = 0.08;
    staff.castShadow = true;
    this.arms[1].hand.add(staff);

    // --- chains, the sound of it ---
    for (var ci = 0; ci < 3; ci++) {
      var chain = new THREE.Group();
      chain.position.set((ci - 1) * 0.14, 0.52, 0.16);
      for (var li = 0; li < 7; li++) {
        var link = new THREE.Mesh(new THREE.TorusGeometry(0.024, 0.008, 4, 8), iron);
        link.position.y = -li * 0.042;
        link.rotation.y = li % 2 ? Math.PI / 2 : 0;
        chain.add(link);
      }
      this.chest.add(chain);
      if (!this.chains) this.chains = [];
      this.chains.push(chain);
    }

    // --- a murk that clings to it ---
    this.aura = [];
    for (var si = 0; si < 4; si++) {
      var sm = new THREE.Sprite(new THREE.SpriteMaterial({
        map: TX.smokeSprite(si + 3), color: 0x0a0a12,
        transparent: true, opacity: 0.42, depthWrite: false
      }));
      sm.scale.set(1.5 + si * 0.3, 1.9 + si * 0.3, 1);
      sm.position.set((Math.random() - 0.5) * 0.4, 1.1 + si * 0.32, (Math.random() - 0.5) * 0.4);
      this.group.add(sm);
      this.aura.push({ spr: sm, phase: Math.random() * 10, baseY: 1.1 + si * 0.32 });
    }

    this.group.visible = false;
  };

  /* ------------------------------- spawn ------------------------------- */
  Ghost.prototype.spawn = function (level, playerCell, playerYaw) {
    // place it behind the player: prefer a cell 4-7 steps away, out of sight
    var field = level.bfsField(playerCell.x, playerCell.y);
    var best = null;
    for (var i = 0; i < level.open.length; i++) {
      var ci = level.open[i];
      var d = field[ci];
      if (d < 4 || d > 8) continue;
      var cx = ci % level.W, cy = (ci / level.W) | 0;
      var wx = level.cellX(cx), wz = level.cellZ(cy);
      var px = level.cellX(playerCell.x), pz = level.cellZ(playerCell.y);
      // behind = opposite the facing direction
      var fx = -Math.sin(playerYaw), fz = -Math.cos(playerYaw);
      var dx = wx - px, dz = wz - pz;
      var len = Math.hypot(dx, dz) || 1;
      var dot = (dx / len) * fx + (dz / len) * fz;
      var score = -dot * 10 + d;
      if (!best || score > best.score) best = { score: score, cx: cx, cy: cy };
    }
    if (!best) best = { cx: playerCell.x, cy: playerCell.y };
    this.pos.set(level.cellX(best.cx), 0, level.cellZ(best.cy));
    this.group.position.copy(this.pos);
    this.group.visible = true;
    this.facing = 0;
    this.permMul = 1; this.slowMul = 1; this.hits = 0;
    this.state = STATE.HUNT; this.stateT = 0;
    this.path = null; this.pathTimer = 0;
    this.knock.set(0, 0, 0);
  };

  /* -------------------------------- hit -------------------------------- */
  /**
   * Ray/sphere test against the head only. Returns the distance along the
   * ray, or -1. Body hits are handled separately and do nothing on purpose.
   */
  Ghost.prototype.headHit = function (origin, dir, maxDist) {
    this.head.getWorldPosition(this.headWorld);
    var ox = origin.x - this.headWorld.x;
    var oy = origin.y - this.headWorld.y - 0.14;   // aim at the skull, not the neck
    var oz = origin.z - this.headWorld.z;
    var r = 0.215;
    var b = ox * dir.x + oy * dir.y + oz * dir.z;
    var c = ox * ox + oy * oy + oz * oz - r * r;
    var disc = b * b - c;
    if (disc < 0) return -1;
    var t = -b - Math.sqrt(disc);
    if (t < 0) t = -b + Math.sqrt(disc);
    if (t < 0 || t > maxDist) return -1;
    return t;
  };

  Ghost.prototype.bodyHit = function (origin, dir, maxDist) {
    // vertical capsule from y=0.4 to y=2.0, radius 0.32, around this.pos
    var px = this.pos.x, pz = this.pos.z;
    var ox = origin.x - px, oz = origin.z - pz;
    var a = dir.x * dir.x + dir.z * dir.z;
    if (a < 1e-6) return -1;
    var b = 2 * (ox * dir.x + oz * dir.z);
    var c = ox * ox + oz * oz - 0.34 * 0.34;
    var disc = b * b - 4 * a * c;
    if (disc < 0) return -1;
    var t = (-b - Math.sqrt(disc)) / (2 * a);
    if (t < 0) t = (-b + Math.sqrt(disc)) / (2 * a);
    if (t < 0 || t > maxDist) return -1;
    var y = origin.y + dir.y * t - this.pos.y;
    if (y < 0.35 || y > 2.05) return -1;
    return t;
  };

  /** A round through the skull. Buys distance, and buys it permanently. */
  Ghost.prototype.takeHeadshot = function (dirX, dirZ) {
    this.hits++;
    this.permMul *= this.D.perm;
    this.slowMul = 0.10;
    this.state = STATE.STAGGER;
    this.stateT = this.D.stagger;
    // thrown backwards
    var l = Math.hypot(dirX, dirZ) || 1;
    this.knock.set((dirX / l) * 5.4, 0, (dirZ / l) * 5.4);
    this.audio.shriek(this.pos);
    return this.hits;
  };

  Ghost.prototype.hearNoise = function (x, z, strength) {
    if (this.state === STATE.STAGGER || this.state === STATE.GRAB) return;
    var d = Math.hypot(x - this.pos.x, z - this.pos.z);
    if (d > 26 * strength) return;
    this.noisePoint = { x: x, z: z, t: 5.5 + strength * 3 };
    this.state = STATE.INVESTIGATE;
    this.stateT = this.noisePoint.t;
    this.path = null;
  };

  /* ------------------------------- update ------------------------------- */
  Ghost.prototype.update = function (dt, ctx) {
    var level = this.level;
    var px = ctx.playerPos.x, pz = ctx.playerPos.z;
    this.distToPlayer = Math.hypot(px - this.pos.x, pz - this.pos.z);

    /* ---- state machine ---- */
    this.stateT -= dt;

    if (this.state === STATE.STAGGER) {
      // recover speed gradually so the reprieve tapers rather than snaps back
      var k = 1 - U.clamp01(this.stateT / this.D.stagger);
      this.slowMul = U.lerp(0.10, 1.0, U.smootherstep(k));
      if (this.stateT <= 0) { this.state = STATE.HUNT; this.slowMul = 1; }
    } else if (this.state === STATE.INVESTIGATE) {
      this.slowMul = 0.82;
      if (this.stateT <= 0 || !this.noisePoint) {
        this.state = STATE.HUNT; this.noisePoint = null; this.path = null;
      } else if (Math.hypot(this.noisePoint.x - this.pos.x, this.noisePoint.z - this.pos.z) < 1.2) {
        this.state = STATE.HUNT; this.noisePoint = null; this.path = null;
        this.audio.growl(this.pos, 0.9);
      }
    } else if (this.state === STATE.BREAK) {
      this.slowMul = 0;
      if (this.stateT <= 0) {
        if (this.breakDoor) this.breakDoor.smash(this.audio);
        this.breakDoor = null;
        this.state = STATE.HUNT;
        if (ctx.onDoorBroken) ctx.onDoorBroken();
      }
    } else if (this.state === STATE.GRAB) {
      this.slowMul = 0;
    } else {
      this.slowMul = 1;
      // the torch makes you worth hurrying for
      if (ctx.torchOn && ctx.visible) this.slowMul = 1.14;
      else if (ctx.torchOn) this.slowMul = 1.05;
      // and it closes faster when you are far away, so distance is never free
      if (this.distToPlayer > 16) this.slowMul *= 1.16;
    }

    /* ---- pathing ---- */
    this.pathTimer -= dt;
    var goalX, goalZ;
    if (this.state === STATE.INVESTIGATE && this.noisePoint) {
      goalX = this.noisePoint.x; goalZ = this.noisePoint.z;
    } else {
      goalX = px; goalZ = pz;
    }

    if (this.pathTimer <= 0) {
      this.pathTimer = 0.3;
      var gcx = level.toCellX(goalX), gcy = level.toCellY(goalZ);
      var mcx = level.toCellX(this.pos.x), mcy = level.toCellY(this.pos.z);
      var p = level.path(mcx, mcy, gcx, gcy);
      if (p && p.length) { this.path = p; this.pathIdx = Math.min(1, p.length - 1); }
    }

    /* ---- steering ---- */
    var tx = goalX, tz = goalZ;
    if (this.path && this.path.length) {
      // advance along the path
      while (this.pathIdx < this.path.length - 1) {
        var ci = this.path[this.pathIdx];
        var cxx = level.cellX(ci % level.W), czz = level.cellZ((ci / level.W) | 0);
        if (Math.hypot(cxx - this.pos.x, czz - this.pos.z) < level.CS * 0.55) this.pathIdx++;
        else break;
      }
      var ni = this.path[this.pathIdx];
      tx = level.cellX(ni % level.W);
      tz = level.cellZ((ni / level.W) | 0);
      // if the player is in line of sight, cut the corner and come straight
      if (ctx.los && this.distToPlayer < 12) { tx = goalX; tz = goalZ; }
    }

    var dx = tx - this.pos.x, dz = tz - this.pos.z;
    var dlen = Math.hypot(dx, dz);
    var desired = this.baseSpeed * this.permMul * this.slowMul;

    if (this.state === STATE.GRAB || this.state === STATE.BREAK) desired = 0;

    var wishX = 0, wishZ = 0;
    if (dlen > 0.05) { wishX = (dx / dlen) * desired; wishZ = (dz / dlen) * desired; }

    this.vel.x = U.damp(this.vel.x, wishX, this.D.accel, dt);
    this.vel.z = U.damp(this.vel.z, wishZ, this.D.accel, dt);

    // knockback from a headshot decays fast but moves it a long way
    if (this.knock.lengthSq() > 0.0001) {
      this.vel.x += this.knock.x; this.vel.z += this.knock.z;
      this.knock.multiplyScalar(Math.pow(0.0006, dt));
      if (this.knock.lengthSq() < 0.01) this.knock.set(0, 0, 0);
    }

    var nx = this.pos.x + this.vel.x * dt;
    var nz = this.pos.z + this.vel.z * dt;
    level.resolve(nx, nz, 0.34, this._res);
    this.pos.x = this._res.x; this.pos.z = this._res.z;

    this.speed = Math.hypot(this.vel.x, this.vel.z);

    /* ---- doors ---- */
    if (this.state === STATE.HUNT || this.state === STATE.INVESTIGATE) {
      for (var di = 0; di < level.doors.length; di++) {
        var dr = level.doors[di];
        if (dr.open || dr.broken) continue;
        var dd = Math.hypot(dr.x - this.pos.x, dr.z - this.pos.z);
        if (dd < 1.35) {
          // is it between us and where we are going?
          var toDoorX = dr.x - this.pos.x, toDoorZ = dr.z - this.pos.z;
          var dot = toDoorX * (dx / (dlen || 1)) + toDoorZ * (dz / (dlen || 1));
          if (dot > -0.2) {
            this.state = STATE.BREAK;
            this.stateT = this.D.breakTime;
            this.breakDoor = dr;
            this.audio.growl(this.pos, 1);
            break;
          }
        }
      }
    }

    /* ---- catching you ---- */
    if (this.state === STATE.HUNT && this.distToPlayer < 1.25 && ctx.onCatch) {
      ctx.onCatch();
    }

    /* ---- facing ---- */
    var faceTarget = this.facing;
    if (this.speed > 0.2) faceTarget = Math.atan2(this.vel.x, this.vel.z);
    else if (this.state === STATE.GRAB || this.distToPlayer < 4) {
      faceTarget = Math.atan2(px - this.pos.x, pz - this.pos.z);
    }
    this.facing = U.dampAngle(this.facing, faceTarget, 6, dt);

    this.group.position.set(this.pos.x, 0, this.pos.z);
    this.body.rotation.y = this.facing;

    /* ---- animation ---- */
    this._animate(dt, ctx);

    /* ---- sound ---- */
    this.stepAcc += this.speed * dt;
    var stride = 1.55;
    if (this.stepAcc >= stride && this.state !== STATE.GRAB) {
      this.stepAcc -= stride;
      this.audio.ghostStep(this.pos);
      if (Math.random() < 0.5) this.audio.chains(this.pos);
    }
    this.growlTimer -= dt;
    if (this.growlTimer <= 0) {
      this.growlTimer = 4.5 + Math.random() * 7 - U.clamp01(1 - this.distToPlayer / 20) * 2.5;
      if (this.state !== STATE.STAGGER) {
        this.audio.growl(this.pos, U.clamp01(1 - this.distToPlayer / 22));
      }
    }
  };

  Ghost.prototype._animate = function (dt, ctx) {
    var t = ctx.time;
    var staggered = this.state === STATE.STAGGER;
    var grabbing = this.state === STATE.GRAB;
    var breaking = this.state === STATE.BREAK;

    // walk cycle
    this.walkPhase += dt * (this.speed / 1.55) * Math.PI * 2;
    var w = Math.min(1, this.speed / this.baseSpeed);

    for (var i = 0; i < 2; i++) {
      var sgn = i ? 1 : -1;
      var ph = this.walkPhase + (i ? Math.PI : 0);
      this.legs[i].hip.rotation.x = Math.sin(ph) * 0.62 * w;
      this.legs[i].knee.rotation.x = Math.max(0, -Math.sin(ph - 0.7)) * 0.95 * w;
      // arms counter-swing; they hang far too low
      var arm = this.arms[i];
      if (grabbing) {
        arm.shoulder.rotation.x = U.damp(arm.shoulder.rotation.x, -2.1, 12, dt);
        arm.shoulder.rotation.z = U.damp(arm.shoulder.rotation.z, sgn * 0.35, 12, dt);
        arm.elbow.rotation.x = U.damp(arm.elbow.rotation.x, 0.4, 12, dt);
      } else if (staggered) {
        arm.shoulder.rotation.x = U.damp(arm.shoulder.rotation.x, 0.7, 8, dt);
        arm.shoulder.rotation.z = U.damp(arm.shoulder.rotation.z, sgn * 0.9, 8, dt);
        arm.elbow.rotation.x = U.damp(arm.elbow.rotation.x, -0.5, 8, dt);
      } else if (breaking) {
        arm.shoulder.rotation.x = -1.5 + Math.sin(t * 22) * 0.7;
        arm.shoulder.rotation.z = U.damp(arm.shoulder.rotation.z, sgn * 0.2, 9, dt);
        arm.elbow.rotation.x = U.damp(arm.elbow.rotation.x, 0.2, 9, dt);
      } else {
        var reach = U.clamp01(1 - (this.distToPlayer - 1.2) / 3.2);
        arm.shoulder.rotation.x = U.damp(arm.shoulder.rotation.x,
          -Math.sin(ph) * 0.42 * w - reach * 1.7, 9, dt);
        arm.shoulder.rotation.z = U.damp(arm.shoulder.rotation.z, sgn * (0.16 + reach * 0.3), 9, dt);
        arm.elbow.rotation.x = U.damp(arm.elbow.rotation.x, -0.35 + reach * 0.5, 9, dt);
      }
    }

    // torso sway + the hunch
    var bobY = Math.abs(Math.sin(this.walkPhase)) * 0.055 * w;
    this.chest.position.y = 1.34 + bobY;
    this.chest.rotation.z = Math.sin(this.walkPhase) * 0.055 * w;
    this.chest.rotation.x = U.damp(this.chest.rotation.x,
      staggered ? -0.55 : (grabbing ? 0.28 : 0.14 + w * 0.06), 7, dt);

    // head: it lolls as it walks, which is what makes the shot hard
    var headTilt = Math.sin(this.walkPhase * 1.0 + 0.6) * 0.14 * w;
    var headYaw = Math.sin(this.walkPhase * 0.5) * 0.22 * w;
    this.neck.rotation.z = U.damp(this.neck.rotation.z, headTilt, 10, dt);
    this.neck.rotation.y = U.damp(this.neck.rotation.y, headYaw, 8, dt);
    this.neck.rotation.x = U.damp(this.neck.rotation.x,
      staggered ? -0.85 : (grabbing ? 0.35 : -0.12 - w * 0.1), 8, dt);
    this.head.position.y = 0.20 + Math.sin(this.walkPhase * 2 + 1.1) * 0.028 * w;

    // jaw
    var open = grabbing ? 0.5 : (staggered ? 0.45 : 0.06 + w * 0.05 + Math.sin(t * 1.7) * 0.03);
    this.jaw.position.y = U.damp(this.jaw.position.y, 0.045 - open * 0.14, 12, dt);
    this.jaw.rotation.x = U.damp(this.jaw.rotation.x, open * 0.7, 12, dt);

    // eyes brighten when it has line of sight on you
    var glow = staggered ? 0.15 : (ctx.los ? 1 : 0.55);
    var pulse = 0.8 + Math.sin(t * 3.1) * 0.2;
    this.eyeGlow.intensity = U.damp(this.eyeGlow.intensity, glow * 0.85 * pulse, 5, dt);
    for (var ei = 0; ei < this.eyes.length; ei++) {
      var em = this.eyes[ei];
      if (em.material.opacity !== undefined && em.isSprite) {
        em.material.opacity = U.damp(em.material.opacity, glow * 0.9 * pulse, 5, dt);
      }
    }

    // chains swing
    for (var ci = 0; ci < this.chains.length; ci++) {
      this.chains[ci].rotation.x = Math.sin(this.walkPhase + ci) * 0.3 * w;
      this.chains[ci].rotation.z = Math.cos(this.walkPhase * 0.7 + ci) * 0.2 * w;
    }

    // the murk
    for (var ai = 0; ai < this.aura.length; ai++) {
      var a = this.aura[ai];
      a.spr.position.y = a.baseY + Math.sin(t * 0.6 + a.phase) * 0.1;
      a.spr.position.x = Math.sin(t * 0.4 + a.phase * 2) * 0.16;
      a.spr.position.z = Math.cos(t * 0.35 + a.phase * 1.7) * 0.16;
      a.spr.material.opacity = (staggered ? 0.22 : 0.4) + Math.sin(t * 0.9 + a.phase) * 0.08;
    }

    // knocked backwards, physically
    if (staggered) {
      var s = U.clamp01(this.stateT / this.D.stagger);
      this.body.rotation.x = -s * 0.42;
      this.body.position.y = -s * 0.12;
    } else {
      this.body.rotation.x = U.damp(this.body.rotation.x, 0, 5, dt);
      this.body.position.y = U.damp(this.body.position.y, 0, 5, dt);
    }
  };

  Ghost.prototype.setGrabbed = function (on) {
    this.state = on ? STATE.GRAB : STATE.HUNT;
    this.stateT = on ? 99 : 0;
    if (!on) {
      // shoved off: a short reprieve, but nothing like a headshot
      this.state = STATE.STAGGER;
      this.stateT = this.D.stagger * 0.42;
      this.slowMul = 0.25;
      var dx = this.pos.x, dz = this.pos.z;
      this.knock.set(0, 0, 0);
    }
  };

  Ghost.prototype.dispose = function () {
    this.group.traverse(function (o) { if (o.geometry) o.geometry.dispose(); });
    this.mats.forEach(function (m) { m.dispose(); });
  };

  global.GGhost = Ghost;
})(window);
