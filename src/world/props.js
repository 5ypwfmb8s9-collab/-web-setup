/* ==========================================================================
   GÜLYABANI — props and set dressing
   Doors, the sealed exit, the amulets, and the furniture that makes the
   konak feel lived-in and then abandoned. Point lights are NOT created per
   candle: emitters are registered and the renderer assigns a small pool of
   real lights to the nearest ones each frame (see game.js).
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;
  var TX = global.GTX;
  var P = {};

  var CS = 3.5, WH = 3.4;
  var M = null;   // material cache
  var G = null;   // geometry cache

  P.initMaterials = function (seed) {
    if (M) return M;
    var dw = TX.doorwood(seed + 21);
    var met = TX.metal(seed + 22);
    var cl = TX.cloth(seed + 23);
    var pap = TX.paper(seed + 24);

    M = {
      doorWood: new THREE.MeshStandardMaterial({
        map: dw.map, normalMap: dw.normalMap, roughnessMap: dw.roughnessMap,
        roughness: 0.92, metalness: 0.0, color: 0xa8967c, envMapIntensity: 0.4
      }),
      darkWood: new THREE.MeshStandardMaterial({ color: 0x6f5f4b, roughness: 0.84, metalness: 0.0, envMapIntensity: 0.45 }),
      midWood: new THREE.MeshStandardMaterial({ color: 0x8a7658, roughness: 0.80, metalness: 0.0, envMapIntensity: 0.45 }),
      iron: new THREE.MeshStandardMaterial({
        map: met.map, normalMap: met.normalMap, roughnessMap: met.roughnessMap,
        roughness: 0.62, metalness: 0.72, color: 0xdbdbdd, envMapIntensity: 1.1
      }),
      brass: new THREE.MeshStandardMaterial({ color: 0xebd388, roughness: 0.34, metalness: 0.88, envMapIntensity: 1.4 }),
      cloth: new THREE.MeshStandardMaterial({
        map: cl.map, normalMap: cl.normalMap, roughnessMap: cl.roughnessMap,
        roughness: 1.0, metalness: 0.0, color: 0xbcb2a7, side: THREE.DoubleSide, envMapIntensity: 0.3
      }),
      paper: new THREE.MeshStandardMaterial({
        map: pap.map, normalMap: pap.normalMap, roughness: 1.0, metalness: 0.0,
        color: 0xfaf5e5, side: THREE.DoubleSide, envMapIntensity: 0.3
      }),
      wax: new THREE.MeshStandardMaterial({ color: 0xf9f5e5, roughness: 0.5, metalness: 0.0, envMapIntensity: 0.5 }),
      glass: new THREE.MeshStandardMaterial({
        color: 0x838e98, roughness: 0.08, metalness: 0.25, transparent: true, opacity: 0.35, envMapIntensity: 1.6
      }),
      bone: new THREE.MeshStandardMaterial({ color: 0xdad4c4, roughness: 0.85, envMapIntensity: 0.4 }),
      stone: new THREE.MeshStandardMaterial({ color: 0x8f8b84, roughness: 0.94, envMapIntensity: 0.4 }),
      sealRed: new THREE.MeshStandardMaterial({
        color: 0x5a3832, emissive: 0xeb714f, emissiveIntensity: 1.4, roughness: 0.7
      }),
      sealGold: new THREE.MeshStandardMaterial({
        color: 0x716232, emissive: 0xf5da91, emissiveIntensity: 2.2, roughness: 0.5
      }),
      muskaMat: null,
      flame: new THREE.MeshBasicMaterial({ color: 0xffdb9b, transparent: true, opacity: 0.95 })
    };
    M.portraits = [];
    for (var pi = 0; pi < 3; pi++) {
      M.portraits.push(new THREE.MeshStandardMaterial({
        map: TX.portrait(seed + pi * 37), roughness: 0.88, metalness: 0.0,
        color: 0xddd7ca, envMapIntensity: 0.3
      }));
    }
    var mt = TX.muska();
    M.muskaMat = new THREE.MeshStandardMaterial({
      map: mt, emissiveMap: mt, emissive: 0xffffff, emissiveIntensity: 1.5,
      color: 0xc2ad71, roughness: 0.45, metalness: 0.6, side: THREE.DoubleSide
    });

    G = {
      box: new THREE.BoxGeometry(1, 1, 1),
      cyl: new THREE.CylinderGeometry(1, 1, 1, 12),
      cyl6: new THREE.CylinderGeometry(1, 1, 1, 6),
      sph: new THREE.SphereGeometry(1, 10, 8),
      plane: new THREE.PlaneGeometry(1, 1),
      cone: new THREE.ConeGeometry(1, 1, 8)
    };
    return M;
  };

  P.disposeMaterials = function () { M = null; G = null; };

  /* ------------------------------ helpers ------------------------------ */
  function box(w, h, d, mat, x, y, z, ry) {
    var m = new THREE.Mesh(G.box, mat);
    m.scale.set(w, h, d);
    m.position.set(x, y, z);
    if (ry) m.rotation.y = ry;
    m.castShadow = true; m.receiveShadow = true;
    return m;
  }
  function cyl(r1, r2, h, mat, x, y, z, seg) {
    var g = (r1 === r2) ? G.cyl : new THREE.CylinderGeometry(r1, r2, 1, seg || 12);
    var m = new THREE.Mesh(g, mat);
    if (r1 === r2) m.scale.set(r1, h, r1); else m.scale.set(1, h, 1);
    m.position.set(x, y, z);
    m.castShadow = true; m.receiveShadow = true;
    return m;
  }
  P.box = box;

  function addCollider(level, x, z, hw, hd) {
    var b = { minX: x - hw, minZ: z - hd, maxX: x + hw, maxZ: z + hd };
    level.boxes.push(b);
    return b;
  }

  /* ================================ DOOR ================================ */
  P.makeDoor = function (level, cx, cy, axis, rnd) {
    var x = level.cellX(cx), z = level.cellZ(cy);
    var pivot = new THREE.Group();
    var leafW = CS * 0.94, leafH = 2.62, leafT = 0.085;

    // hinge sits at one edge of the opening; base rotation orients the door
    if (axis === 'z') {
      pivot.position.set(x - CS / 2 + 0.03, 0, z);
      pivot.rotation.y = 0;
    } else {
      pivot.position.set(x, 0, z - CS / 2 + 0.03);
      pivot.rotation.y = -Math.PI / 2;
    }

    var leaf = new THREE.Group();
    var panel = box(leafW, leafH, leafT, M.doorWood, leafW / 2, leafH / 2, 0);
    leaf.add(panel);
    // iron bands and a ring handle
    leaf.add(box(leafW * 0.96, 0.075, leafT + 0.03, M.iron, leafW / 2, leafH * 0.24, 0));
    leaf.add(box(leafW * 0.96, 0.075, leafT + 0.03, M.iron, leafW / 2, leafH * 0.76, 0));
    var ring = new THREE.Mesh(new THREE.TorusGeometry(0.075, 0.017, 6, 14), M.iron);
    ring.position.set(leafW - 0.22, leafH * 0.5, leafT * 0.5 + 0.03);
    ring.castShadow = true;
    leaf.add(ring);
    pivot.add(leaf);

    // frame around the opening (drawn in the parent space, not the pivot)
    var frame = new THREE.Group();
    var fw = 0.11;
    if (axis === 'z') {
      frame.add(box(fw, WH, 0.24, M.darkWood, x - CS / 2 + fw / 2, WH / 2, z));
      frame.add(box(fw, WH, 0.24, M.darkWood, x + CS / 2 - fw / 2, WH / 2, z));
      frame.add(box(CS, WH - leafH - 0.1, 0.26, M.darkWood, x, leafH + 0.1 + (WH - leafH - 0.1) / 2, z));
    } else {
      frame.add(box(0.24, WH, fw, M.darkWood, x, WH / 2, z - CS / 2 + fw / 2));
      frame.add(box(0.24, WH, fw, M.darkWood, x, WH / 2, z + CS / 2 - fw / 2));
      frame.add(box(0.26, WH - leafH - 0.1, CS, M.darkWood, x, leafH + 0.1 + (WH - leafH - 0.1) / 2, z));
    }

    var grp = new THREE.Group();
    grp.add(pivot); grp.add(frame);

    var collider = axis === 'z'
      ? addCollider(level, x, z, CS / 2, 0.13)
      : addCollider(level, x, z, 0.13, CS / 2);

    var startOpen = rnd() < 0.35;
    var door = {
      cx: cx, cy: cy, x: x, z: z, axis: axis,
      pivotGroup: grp, pivot: pivot, leaf: leaf,
      basis: pivot.rotation.y,
      open: startOpen, broken: false,
      angle: startOpen ? Math.PI * 0.5 : 0,
      target: startOpen ? Math.PI * 0.5 : 0,
      collider: collider,
      breakT: 0
    };
    collider.disabled = startOpen;
    pivot.rotation.y = door.basis + door.angle;

    door.toggle = function (audio) {
      if (this.broken) return false;
      this.open = !this.open;
      this.target = this.open ? Math.PI * 0.52 : 0;
      this.collider.disabled = this.open;
      if (audio) {
        if (this.open) audio.doorCreak({ x: this.x, y: 1.2, z: this.z });
        else audio.doorSlam({ x: this.x, y: 1.2, z: this.z });
      }
      return true;
    };
    door.smash = function (audio) {
      this.broken = true; this.open = true;
      this.target = Math.PI * 0.62;
      this.collider.disabled = true;
      if (audio) audio.doorBreak({ x: this.x, y: 1.2, z: this.z });
    };
    door.update = function (dt) {
      if (Math.abs(this.angle - this.target) > 0.001) {
        var speed = this.broken ? 16 : 7;
        this.angle = U.damp(this.angle, this.target, speed, dt);
        this.pivot.rotation.y = this.basis + this.angle;
      }
      if (this.broken) {
        // sag on the hinge once it has been kicked through
        this.leaf.rotation.z = U.damp(this.leaf.rotation.z, -0.19, 3, dt);
        this.leaf.position.y = U.damp(this.leaf.position.y, -0.08, 3, dt);
      }
    };
    return door;
  };

  /* ================================ EXIT ================================ */
  P.makeExit = function (level, cell) {
    var cx = cell.cx, cy = cell.cy, dir = cell.dir;
    var x = level.cellX(cx) + dir.dx * (CS / 2 - 0.07);
    var z = level.cellZ(cy) + dir.dy * (CS / 2 - 0.07);
    var grp = new THREE.Group();
    var rotY = Math.atan2(-dir.dx, -dir.dy);  // face inward
    grp.position.set(x, 0, z);
    grp.rotation.y = rotY;

    var dw = CS * 0.86, dh = 2.85;
    // arch surround
    grp.add(box(dw + 0.5, 0.2, 0.34, M.stone, 0, dh + 0.12, 0));
    grp.add(box(0.24, dh + 0.2, 0.32, M.stone, -dw / 2 - 0.13, (dh + 0.2) / 2, 0));
    grp.add(box(0.24, dh + 0.2, 0.32, M.stone, dw / 2 + 0.13, (dh + 0.2) / 2, 0));

    // two leaves
    var leaves = [];
    for (var i = 0; i < 2; i++) {
      var s = i ? 1 : -1;
      var piv = new THREE.Group();
      piv.position.set(s * dw / 2, 0, 0.02);
      var lf = box(dw / 2, dh, 0.1, M.doorWood, -s * dw / 4, dh / 2, 0);
      piv.add(lf);
      piv.add(box(dw / 2 * 0.9, 0.09, 0.14, M.iron, -s * dw / 4, dh * 0.2, 0));
      piv.add(box(dw / 2 * 0.9, 0.09, 0.14, M.iron, -s * dw / 4, dh * 0.5, 0));
      piv.add(box(dw / 2 * 0.9, 0.09, 0.14, M.iron, -s * dw / 4, dh * 0.8, 0));
      grp.add(piv);
      leaves.push({ piv: piv, sign: s });
    }

    // three seals, one per amulet
    var seals = [];
    for (var k = 0; k < 3; k++) {
      var sm = new THREE.Mesh(new THREE.TorusGeometry(0.17, 0.045, 7, 18), M.sealRed);
      sm.position.set(0, 0.85 + k * 0.62, 0.1);
      sm.rotation.x = 0;
      grp.add(sm);
      var bar = new THREE.Mesh(G.box, M.sealRed);
      bar.scale.set(dw * 0.92, 0.06, 0.06);
      bar.position.set(0, 0.85 + k * 0.62, 0.11);
      bar.rotation.z = (k - 1) * 0.16;
      grp.add(bar);
      seals.push({ ring: sm, bar: bar });
    }

    // a beacon so the exit can be picked out from down a corridor
    var emitter = {
      x: x - dir.dx * 0.7, y: 1.75, z: z - dir.dy * 0.7,
      color: 0xed7a5d, power: 1.8, range: 13, priority: 10, phase: 0
    };
    level.emitters.push(emitter);

    var exit = {
      cx: cx, cy: cy, x: x, z: z, group: grp, seals: seals, light: emitter,
      leaves: leaves, unlocked: false, opened: false, openT: 0,
      dirX: dir.dx, dirY: dir.dy,
      // stand-in point the player must reach
      targetX: level.cellX(cx) + dir.dx * (CS * 0.28),
      targetZ: level.cellZ(cy) + dir.dy * (CS * 0.28)
    };

    exit.setProgress = function (n) {
      for (var i = 0; i < 3; i++) {
        var mat = i < n ? M.sealGold : M.sealRed;
        this.seals[i].ring.material = mat;
        this.seals[i].bar.material = mat;
      }
      var f = n / 3;
      this.light.color = (n >= 3 ? 0xf5da91 : 0xed7a5d);
      this.light.power = 1.7 + f * 1.5;
    };
    exit.unlock = function () {
      this.unlocked = true;
      this.setProgress(3);
    };
    exit.update = function (dt, t) {
      this.light.power = (this.unlocked ? 3.0 : 1.7) *
        (0.86 + Math.sin(t * (this.unlocked ? 2.2 : 5.5)) * 0.14);
      for (var i = 0; i < 3; i++) {
        this.seals[i].ring.rotation.z += dt * (this.unlocked ? 0.9 : 0.25) * (i % 2 ? 1 : -1);
      }
      if (this.opened) {
        this.openT = Math.min(1, this.openT + dt * 0.55);
        var a = U.smootherstep(this.openT) * 1.35;
        this.leaves[0].piv.rotation.y = a;
        this.leaves[1].piv.rotation.y = -a;
      }
    };
    exit.setProgress(0);
    return exit;
  };

  /* ============================== PICKUPS ============================== */
  function hoverItem(level, cx, cy, y, mesh, glowColor, kind) {
    var grp = new THREE.Group();
    grp.position.set(level.cellX(cx), 0, level.cellZ(cy));
    grp.add(mesh);
    var spr = new THREE.Sprite(new THREE.SpriteMaterial({
      map: TX.glowSprite('rgb(255,210,120)', 0.2),
      color: glowColor, transparent: true, opacity: 0.55,
      blending: THREE.AdditiveBlending, depthWrite: false
    }));
    spr.scale.set(1.1, 1.1, 1);
    spr.position.set(0, y, 0);
    grp.add(spr);
    return {
      kind: kind, cx: cx, cy: cy,
      x: level.cellX(cx), z: level.cellZ(cy), y: y,
      group: grp, mesh: mesh, glow: spr, taken: false,
      collect: function () {
        this.taken = true;
        this.group.visible = false;
        if (this.emitter) this.emitter.dead = true;
      }
    };
  }

  P.makeMuska = function (level, cx, cy, index) {
    var g = new THREE.Group();
    // a low stool, so the amulet reads at a findable height
    var stool = new THREE.Group();
    stool.add(box(0.46, 0.05, 0.46, M.darkWood, 0, 0.52, 0));
    for (var i = 0; i < 4; i++) {
      var sx = (i % 2 ? 1 : -1) * 0.18, sz = (i < 2 ? 1 : -1) * 0.18;
      stool.add(box(0.045, 0.52, 0.045, M.darkWood, sx, 0.26, sz));
    }
    g.add(stool);

    var plate = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.34), M.muskaMat);
    plate.position.set(0, 0.86, 0);
    plate.castShadow = false;
    g.add(plate);
    var cord = cyl(0.006, 0.006, 0.2, M.iron, 0, 1.06, 0);
    g.add(cord);

    var it = hoverItem(level, cx, cy, 0.86, g, 0xfbe9b8, 'muska');
    it.index = index;
    it.plate = plate;
    it.emitter = {
      x: it.x, y: 1.0, z: it.z, color: 0xf8e2ab,
      power: 1.35, range: 7.5, priority: 7, phase: index * 2.1
    };
    level.emitters.push(it.emitter);
    it.update = function (dt, t, camPos) {
      if (this.taken) return;
      this.plate.position.y = 0.86 + Math.sin(t * 1.6 + this.index) * 0.035;
      this.plate.lookAt(camPos.x, this.plate.getWorldPosition(_v).y, camPos.z);
      this.glow.material.opacity = 0.45 + Math.sin(t * 2.4 + this.index * 2) * 0.14;
    };
    return it;
  };
  var _v = new THREE.Vector3();

  P.makeNote = function (level, cx, cy, index) {
    var g = new THREE.Group();
    var sheet = new THREE.Mesh(new THREE.PlaneGeometry(0.3, 0.4), M.paper);
    sheet.rotation.x = -Math.PI / 2;
    sheet.rotation.z = Math.random() * 2;
    sheet.position.set(0, 0.012, 0);
    sheet.receiveShadow = true;
    g.add(sheet);
    var it = hoverItem(level, cx, cy, 0.09, g, 0xede5cc, 'note');
    it.glow.scale.set(0.55, 0.55, 1);
    it.glow.material.opacity = 0.22;
    it.index = index;
    it.update = function (dt, t) {
      if (this.taken) return;
      this.glow.material.opacity = 0.16 + Math.sin(t * 1.5 + this.index) * 0.07;
    };
    return it;
  };

  P.makeBattery = function (level, cx, cy) {
    var g = new THREE.Group();
    var b = cyl(0.033, 0.033, 0.12, M.iron, 0, 0.06, 0);
    g.add(b);
    var cap = cyl(0.02, 0.02, 0.02, M.brass, 0, 0.13, 0);
    g.add(cap);
    var it = hoverItem(level, cx, cy, 0.13, g, 0xcce9f1, 'battery');
    it.glow.scale.set(0.55, 0.55, 1);
    it.glow.material.opacity = 0.3;
    it.update = function (dt, t) {
      if (this.taken) return;
      this.mesh.rotation.y += dt * 0.8;
      this.glow.material.opacity = 0.24 + Math.sin(t * 3) * 0.1;
    };
    return it;
  };

  P.makeStonePile = function (level, cx, cy) {
    var g = new THREE.Group();
    for (var i = 0; i < 4; i++) {
      var s = 0.05 + Math.random() * 0.05;
      var m = new THREE.Mesh(G.sph, M.stone);
      m.scale.set(s, s * 0.75, s * 0.9);
      m.position.set((Math.random() - 0.5) * 0.3, s * 0.7, (Math.random() - 0.5) * 0.3);
      m.rotation.set(Math.random(), Math.random(), Math.random());
      m.castShadow = true; m.receiveShadow = true;
      g.add(m);
    }
    var it = hoverItem(level, cx, cy, 0.1, g, 0xd4d8dd, 'stone');
    it.glow.scale.set(0.45, 0.45, 1);
    it.glow.material.opacity = 0.14;
    it.update = function () { };
    return it;
  };

  /* ============================ SET DRESSING ============================ */
  P.dressLevel = function (level) {
    var rnd = U.rng(level.seed * 31 + 9);
    var W = level.W, H = level.H;
    var emitters = level.emitters;   // shared with the light pool
    var group = level.group;

    function wallDirs(cx, cy) {
      var d = [];
      if (!level.isOpen(cx, cy - 1)) d.push({ dx: 0, dy: -1, ry: 0 });
      if (!level.isOpen(cx, cy + 1)) d.push({ dx: 0, dy: 1, ry: Math.PI });
      if (!level.isOpen(cx - 1, cy)) d.push({ dx: -1, dy: 0, ry: -Math.PI / 2 });
      if (!level.isOpen(cx + 1, cy)) d.push({ dx: 1, dy: 0, ry: Math.PI / 2 });
      return d;
    }

    /* ---- a candle stub on a shelf: warm, fragile light ---- */
    function candle(x, y, z, scale) {
      var g = new THREE.Group();
      g.position.set(x, y, z);
      var s = scale || 1;
      g.add(cyl(0.028 * s, 0.028 * s, 0.13 * s, M.wax, 0, 0.065 * s, 0));
      var flame = new THREE.Mesh(G.cone, M.flame);
      flame.scale.set(0.022 * s, 0.075 * s, 0.022 * s);
      flame.position.set(0, 0.17 * s, 0);
      g.add(flame);
      var spr = new THREE.Sprite(new THREE.SpriteMaterial({
        map: TX.glowSprite('rgb(255,178,90)', 0.18),
        transparent: true, opacity: 0.75, blending: THREE.AdditiveBlending, depthWrite: false
      }));
      spr.scale.set(0.6 * s, 0.6 * s, 1);
      spr.position.set(0, 0.17 * s, 0);
      g.add(spr);
      group.add(g);
      emitters.push({
        x: x, y: y + 0.18 * s, z: z, color: 0xffd491,
        power: 2.4 * s, range: 7.5 * s, flame: flame, glow: spr, phase: rnd() * 10
      });
      return g;
    }

    /* ---- furniture ---- */
    function table(x, z, ry) {
      var g = new THREE.Group();
      g.position.set(x, 0, z); g.rotation.y = ry;
      g.add(box(1.35, 0.07, 0.78, M.midWood, 0, 0.74, 0));
      for (var i = 0; i < 4; i++) {
        g.add(box(0.08, 0.72, 0.08, M.darkWood,
          (i % 2 ? 1 : -1) * 0.58, 0.36, (i < 2 ? 1 : -1) * 0.31));
      }
      group.add(g);
      addCollider(level, x, z, Math.abs(Math.cos(ry)) * 0.68 + 0.05, Math.abs(Math.cos(ry)) * 0.39 + 0.28);
      return g;
    }

    function chair(x, z, ry, broken) {
      var g = new THREE.Group();
      g.position.set(x, 0, z);
      g.rotation.y = ry;
      if (broken) { g.rotation.z = 1.5; g.position.y = 0.22; }
      g.add(box(0.42, 0.05, 0.42, M.midWood, 0, 0.45, 0));
      g.add(box(0.42, 0.55, 0.05, M.midWood, 0, 0.72, -0.19));
      for (var i = 0; i < 4; i++) {
        g.add(box(0.05, 0.45, 0.05, M.darkWood,
          (i % 2 ? 1 : -1) * 0.17, 0.22, (i < 2 ? 1 : -1) * 0.17));
      }
      group.add(g);
      if (!broken) addCollider(level, x, z, 0.26, 0.26);
      return g;
    }

    function cabinet(x, z, ry) {
      var g = new THREE.Group();
      g.position.set(x, 0, z); g.rotation.y = ry;
      g.add(box(1.05, 1.95, 0.46, M.darkWood, 0, 0.98, 0));
      g.add(box(0.48, 1.7, 0.03, M.midWood, -0.26, 1.0, 0.24));
      g.add(box(0.48, 1.7, 0.03, M.midWood, 0.26, 1.0, 0.24));
      g.add(box(0.03, 0.1, 0.04, M.brass, -0.03, 1.0, 0.27));
      g.add(box(0.03, 0.1, 0.04, M.brass, 0.03, 1.0, 0.27));
      group.add(g);
      var c = Math.abs(Math.cos(ry)), s = Math.abs(Math.sin(ry));
      addCollider(level, x, z, 0.53 * c + 0.24 * s, 0.24 * c + 0.53 * s);
      return g;
    }

    function shelf(x, y, z, ry) {
      var g = new THREE.Group();
      g.position.set(x, y, z); g.rotation.y = ry;
      g.add(box(0.8, 0.045, 0.24, M.midWood, 0, 0, 0));
      g.add(box(0.05, 0.16, 0.2, M.darkWood, -0.33, -0.1, 0));
      g.add(box(0.05, 0.16, 0.2, M.darkWood, 0.33, -0.1, 0));
      group.add(g);
      return g;
    }

    function crate(x, z, ry, s) {
      var g = box(0.62 * s, 0.58 * s, 0.62 * s, M.midWood, x, 0.29 * s, z, ry);
      group.add(g);
      addCollider(level, x, z, 0.34 * s, 0.34 * s);
      return g;
    }

    function barrel(x, z) {
      var g = new THREE.Group();
      g.position.set(x, 0, z);
      g.add(cyl(0.32, 0.28, 0.82, M.midWood, 0, 0.41, 0));
      g.add(cyl(0.335, 0.335, 0.05, M.iron, 0, 0.2, 0));
      g.add(cyl(0.335, 0.335, 0.05, M.iron, 0, 0.62, 0));
      group.add(g);
      addCollider(level, x, z, 0.34, 0.34);
      return g;
    }

    function rug(x, z, ry) {
      var m = new THREE.Mesh(new THREE.PlaneGeometry(2.1, 1.35), level.mat.kilim);
      m.rotation.x = -Math.PI / 2; m.rotation.z = ry;
      m.position.set(x, 0.008, z);
      m.receiveShadow = true;
      group.add(m);
      return m;
    }

    function drape(x, y, z, ry, w, h) {
      var geo = new THREE.PlaneGeometry(w, h, 6, 3);
      var p = geo.attributes.position;
      for (var i = 0; i < p.count; i++) {
        var px = p.getX(i), py = p.getY(i);
        p.setZ(i, Math.sin(px * 4.2 + py) * 0.06);
      }
      geo.computeVertexNormals();
      var m = new THREE.Mesh(geo, M.cloth);
      m.position.set(x, y, z); m.rotation.y = ry;
      m.castShadow = true; m.receiveShadow = true;
      group.add(m);
      return m;
    }

    function picture(x, y, z, ry) {
      var g = new THREE.Group();
      g.position.set(x, y, z); g.rotation.y = ry;
      var w = 0.42 + rnd() * 0.3, h = 0.52 + rnd() * 0.34;
      g.add(box(w, h, 0.05, M.darkWood, 0, 0, 0));
      var canvasM = new THREE.Mesh(new THREE.PlaneGeometry(w - 0.10, h - 0.10),
        M.portraits[rnd.int(0, M.portraits.length - 1)]);
      canvasM.position.set(0, 0, 0.028);
      canvasM.receiveShadow = true;
      g.add(canvasM);
      g.rotation.z = (rnd() - 0.5) * 0.16;
      group.add(g);
      return g;
    }

    function chandelier(x, z) {
      var g = new THREE.Group();
      g.position.set(x, WH, z);
      g.add(cyl(0.012, 0.012, 0.5, M.iron, 0, -0.25, 0));
      var ring = new THREE.Mesh(new THREE.TorusGeometry(0.34, 0.022, 6, 18), M.iron);
      ring.rotation.x = Math.PI / 2;
      ring.position.y = -0.52; ring.castShadow = true;
      g.add(ring);
      group.add(g);
      for (var i = 0; i < 4; i++) {
        var a = i * Math.PI / 2 + 0.4;
        candle(x + Math.cos(a) * 0.34, WH - 0.5, z + Math.sin(a) * 0.34, 0.9);
      }
      return g;
    }

    function window_(cx, cy, dir) {
      var x = level.cellX(cx) + dir.dx * (CS / 2 - 0.04);
      var z = level.cellZ(cy) + dir.dy * (CS / 2 - 0.04);
      var g = new THREE.Group();
      g.position.set(x, 1.75, z);
      g.rotation.y = Math.atan2(-dir.dx, -dir.dy);
      g.add(box(1.15, 1.5, 0.05, M.glass, 0, 0, 0));
      g.add(box(1.3, 0.08, 0.12, M.darkWood, 0, 0.79, 0.02));
      g.add(box(1.3, 0.08, 0.12, M.darkWood, 0, -0.79, 0.02));
      g.add(box(0.08, 1.6, 0.12, M.darkWood, -0.65, 0, 0.02));
      g.add(box(0.08, 1.6, 0.12, M.darkWood, 0.65, 0, 0.02));
      g.add(box(0.05, 1.5, 0.09, M.darkWood, 0, 0, 0.03));
      g.add(box(1.15, 0.05, 0.09, M.darkWood, 0, 0, 0.03));
      // boards nailed across, half torn off
      for (var b = 0; b < 2; b++) {
        var bd = box(1.5, 0.16, 0.04, M.midWood, 0, -0.35 + b * 0.7, 0.1);
        bd.rotation.z = (rnd() - 0.5) * 0.3;
        g.add(bd);
      }
      group.add(g);
      // no dedicated light: the pane itself flares when lightning strikes
      var pane = new THREE.Mesh(new THREE.PlaneGeometry(1.15, 1.5),
        new THREE.MeshBasicMaterial({ color: 0x8198af, transparent: true, opacity: 0.10 }));
      pane.position.set(0, 0, 0.03);
      g.add(pane);
      level.windows.push({ pane: pane, x: x, z: z });
      return g;
    }

    function cobweb(cx, cy) {
      var x = level.cellX(cx), z = level.cellZ(cy);
      var g = new THREE.Mesh(new THREE.PlaneGeometry(1.1, 1.1),
        new THREE.MeshBasicMaterial({
          color: 0xcccac5, transparent: true, opacity: 0.11,
          side: THREE.DoubleSide, depthWrite: false
        }));
      var corner = rnd.int(0, 3);
      g.position.set(x + (corner % 2 ? 1 : -1) * CS * 0.34, WH - 0.5, z + (corner < 2 ? 1 : -1) * CS * 0.34);
      g.rotation.set(-Math.PI / 4, Math.PI / 4 * (corner + 1), 0);
      group.add(g);
      return g;
    }

    /* ---------------- room dressing ---------------- */
    for (var ri = 0; ri < level.rooms.length; ri++) {
      var rm = level.rooms[ri];
      var ccx = rm.x + rm.w / 2 - 0.5, ccy = rm.y + rm.h / 2 - 0.5;
      var wx = level.cellX(ccx), wz = level.cellZ(ccy);

      if (rnd() < 0.75) chandelier(wx, wz);
      if (rnd() < 0.6) rug(wx, wz, rnd() * Math.PI);

      // a table with chairs in bigger rooms
      if (rm.w >= 4 && rm.h >= 3 && rnd() < 0.8) {
        var ry = rnd() < 0.5 ? 0 : Math.PI / 2;
        table(wx, wz, ry);
        var nch = rnd.int(1, 3);
        for (var q = 0; q < nch; q++) {
          var a = rnd() * Math.PI * 2;
          chair(wx + Math.cos(a) * 1.15, wz + Math.sin(a) * 1.15, a + Math.PI / 2, rnd() < 0.4);
        }
        if (rnd() < 0.7) candle(wx + (rnd() - 0.5) * 0.5, 0.78, wz + (rnd() - 0.5) * 0.3, 1);
      }

      // wall furniture
      for (var yy = rm.y; yy < rm.y + rm.h; yy++) {
        for (var xx = rm.x; xx < rm.x + rm.w; xx++) {
          var ds = wallDirs(xx, yy);
          if (!ds.length) continue;
          var d = ds[rnd.int(0, ds.length - 1)];
          var px = level.cellX(xx) + d.dx * (CS / 2 - 0.3);
          var pz = level.cellZ(yy) + d.dy * (CS / 2 - 0.3);
          var roll = rnd();
          if (roll < 0.14) cabinet(px, pz, d.ry);
          else if (roll < 0.24) { shelf(px, 1.25, pz, d.ry); if (rnd() < 0.7) candle(px, 1.3, pz, 1); }
          else if (roll < 0.34) picture(level.cellX(xx) + d.dx * (CS / 2 - 0.09), 1.85,
            level.cellZ(yy) + d.dy * (CS / 2 - 0.09), d.ry);
          else if (roll < 0.42) crate(px, pz, rnd() * 3, 0.8 + rnd() * 0.5);
          else if (roll < 0.48) barrel(px, pz);
          else if (roll < 0.54) drape(level.cellX(xx) + d.dx * (CS / 2 - 0.07), 1.9,
            level.cellZ(yy) + d.dy * (CS / 2 - 0.07), d.ry, 1.0, 2.4);
        }
      }
    }

    /* ---------------- corridor dressing ---------------- */
    for (var cy2 = 1; cy2 < H - 1; cy2++) {
      for (var cx2 = 1; cx2 < W - 1; cx2++) {
        if (!level.isOpen(cx2, cy2)) continue;
        var inRoom = false;
        for (var r2 = 0; r2 < level.rooms.length; r2++) {
          var R = level.rooms[r2];
          if (cx2 >= R.x && cx2 < R.x + R.w && cy2 >= R.y && cy2 < R.y + R.h) { inRoom = true; break; }
        }
        if (inRoom) continue;

        var ds2 = wallDirs(cx2, cy2);
        if (rnd() < 0.10 && ds2.length) {
          var dd = ds2[rnd.int(0, ds2.length - 1)];
          shelf(level.cellX(cx2) + dd.dx * (CS / 2 - 0.22), 1.3,
            level.cellZ(cy2) + dd.dy * (CS / 2 - 0.22), dd.ry);
          if (rnd() < 0.75) {
            candle(level.cellX(cx2) + dd.dx * (CS / 2 - 0.22), 1.35,
              level.cellZ(cy2) + dd.dy * (CS / 2 - 0.22), 1);
          }
        } else if (rnd() < 0.07 && ds2.length) {
          var dd2 = ds2[rnd.int(0, ds2.length - 1)];
          picture(level.cellX(cx2) + dd2.dx * (CS / 2 - 0.08), 1.8,
            level.cellZ(cy2) + dd2.dy * (CS / 2 - 0.08), dd2.ry);
        } else if (rnd() < 0.05) {
          crate(level.cellX(cx2) + (rnd() - 0.5) * 1.2, level.cellZ(cy2) + (rnd() - 0.5) * 1.2,
            rnd() * 3, 0.7 + rnd() * 0.4);
        }
        if (rnd() < 0.10) cobweb(cx2, cy2);

        // windows on the outer ring
        if ((cx2 === 1 || cx2 === W - 2 || cy2 === 1 || cy2 === H - 2) && rnd() < 0.30) {
          var outer = null;
          if (cy2 === 1 && !level.isOpen(cx2, 0)) outer = { dx: 0, dy: -1 };
          else if (cy2 === H - 2 && !level.isOpen(cx2, H - 1)) outer = { dx: 0, dy: 1 };
          else if (cx2 === 1 && !level.isOpen(0, cy2)) outer = { dx: -1, dy: 0 };
          else if (cx2 === W - 2 && !level.isOpen(W - 1, cy2)) outer = { dx: 1, dy: 0 };
          if (outer) window_(cx2, cy2, outer);
        }
      }
    }

    // a handful of candles along the route so the house isn't pitch black
    var lit = 0, guard = 0;
    while (lit < 14 && guard++ < 400) {
      var ci = level.open[rnd.int(0, level.open.length - 1)];
      var gx = ci % W, gy = (ci / W) | 0;
      var dsx = wallDirs(gx, gy);
      if (!dsx.length) continue;
      var dz = dsx[rnd.int(0, dsx.length - 1)];
      candle(level.cellX(gx) + dz.dx * (CS / 2 - 0.16), 1.05 + rnd() * 0.5,
        level.cellZ(gy) + dz.dy * (CS / 2 - 0.16), 1);
      lit++;
    }

    return level;
  };

  global.GProps = P;
})(window);
