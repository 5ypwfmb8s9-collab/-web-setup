/* ==========================================================================
   GÜLYABANI — the konak
   Procedural level: a braided maze carved into a grid, widened into rooms,
   dressed with doors, props and objectives. Geometry is emitted into a few
   merged buffers (one per material) so the whole house is a handful of
   draw calls, which leaves the frame budget for shadows and post.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;
  var TX = global.GTX;

  var CS = 3.5;          // cell size, metres
  var WH = 3.4;          // wall height
  var WALL = 0, OPEN = 1;

  /* ------------------------- small mesh builder ------------------------- */
  function Builder() {
    this.pos = []; this.nor = []; this.uv = []; this.idx = []; this.col = []; this.n = 0;
  }
  Builder.prototype.quad = function (a, b, c, d, u0, v0, u1, v1) {
    // a,b,c,d counter-clockwise viewed from the front face
    var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    var vx = d[0] - a[0], vy = d[1] - a[1], vz = d[2] - a[2];
    var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    var l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;
    var p = this.pos, no = this.nor, uvv = this.uv;
    p.push(a[0], a[1], a[2], b[0], b[1], b[2], c[0], c[1], c[2], d[0], d[1], d[2]);
    for (var i = 0; i < 4; i++) no.push(nx, ny, nz);
    uvv.push(u0, v0, u1, v0, u1, v1, u0, v1);
    for (var ci = 0; ci < 4; ci++) this.col.push(1, 1, 1);
    var k = this.n;
    this.idx.push(k, k + 1, k + 2, k, k + 2, k + 3);
    this.n += 4;
  };
  /**
   * Subdivided quad with a per-vertex tint. The tint is where the house
   * gets its depth: baked corner occlusion, grime rising from the skirting
   * and soot under the ceiling, plus large-scale world noise that breaks up
   * the texture tiling far better than a bigger texture ever could.
   */
  Builder.prototype.quadSub = function (a, b, c, d, u0, v0, u1, v1, sx, sy, colFn) {
    var ux = b[0] - a[0], uy = b[1] - a[1], uz = b[2] - a[2];
    var vx = d[0] - a[0], vy = d[1] - a[1], vz = d[2] - a[2];
    var nx = uy * vz - uz * vy, ny = uz * vx - ux * vz, nz = ux * vy - uy * vx;
    var l = Math.hypot(nx, ny, nz) || 1; nx /= l; ny /= l; nz /= l;

    var base = this.n;
    for (var j = 0; j <= sy; j++) {
      var t = j / sy;
      for (var i = 0; i <= sx; i++) {
        var s = i / sx;
        var w0 = (1 - s) * (1 - t), w1 = s * (1 - t), w2 = s * t, w3 = (1 - s) * t;
        var px = a[0] * w0 + b[0] * w1 + c[0] * w2 + d[0] * w3;
        var py = a[1] * w0 + b[1] * w1 + c[1] * w2 + d[1] * w3;
        var pz = a[2] * w0 + b[2] * w1 + c[2] * w2 + d[2] * w3;
        this.pos.push(px, py, pz);
        this.nor.push(nx, ny, nz);
        this.uv.push(u0 + (u1 - u0) * s, v0 + (v1 - v0) * t);
        var k = colFn ? colFn(px, py, pz, nx, ny, nz) : 1;
        this.col.push(k, k, k);
      }
    }
    var row = sx + 1;
    for (var jj = 0; jj < sy; jj++) {
      for (var ii = 0; ii < sx; ii++) {
        var p0 = base + jj * row + ii;
        this.idx.push(p0, p0 + 1, p0 + row + 1, p0, p0 + row + 1, p0 + row);
      }
    }
    this.n += row * (sy + 1);
  };

  Builder.prototype.empty = function () { return this.n === 0; };
  Builder.prototype.geometry = function () {
    var g = new THREE.BufferGeometry();
    g.setAttribute('position', new THREE.Float32BufferAttribute(this.pos, 3));
    g.setAttribute('normal', new THREE.Float32BufferAttribute(this.nor, 3));
    g.setAttribute('uv', new THREE.Float32BufferAttribute(this.uv, 2));
    if (this.col.length === (this.pos.length)) {
      g.setAttribute('color', new THREE.Float32BufferAttribute(this.col, 3));
    }
    g.setIndex(this.idx);
    g.computeBoundingSphere();
    return g;
  };

  /* =============================== LEVEL =============================== */
  function Level(seed, difficulty) {
    this.seed = seed >>> 0;
    this.rnd = U.rng(this.seed);
    this.difficulty = difficulty || 1;
    this.W = 25; this.H = 25;
    this.CS = CS; this.WH = WH;
    this.group = new THREE.Group();
    this.group.name = 'konak';

    this.doors = [];
    this.items = [];
    this.props = [];        // { x, z, r }  cylindrical colliders
    this.boxes = [];        // { minX, minZ, maxX, maxZ } static colliders
    this.lights = [];
    this.windows = [];
    this.emitters = [];   // candle-like sources; a small pool of real lights follows them
    this.surface = null;    // 0 wood, 1 stone, 2 carpet
  }

  Level.prototype.cellCenter = function (cx, cy, out) {
    out = out || new THREE.Vector3();
    out.set((cx - this.W / 2 + 0.5) * CS, 0, (cy - this.H / 2 + 0.5) * CS);
    return out;
  };
  Level.prototype.cellX = function (cx) { return (cx - this.W / 2 + 0.5) * CS; };
  Level.prototype.cellZ = function (cy) { return (cy - this.H / 2 + 0.5) * CS; };
  Level.prototype.toCellX = function (x) { return Math.floor(x / CS + this.W / 2); };
  Level.prototype.toCellY = function (z) { return Math.floor(z / CS + this.H / 2); };

  Level.prototype.inside = function (x, y) {
    return x >= 0 && y >= 0 && x < this.W && y < this.H;
  };
  Level.prototype.isOpen = function (x, y) {
    return this.inside(x, y) && this.grid[y * this.W + x] === OPEN;
  };
  Level.prototype.isWallAt = function (x, y) { return !this.isOpen(x, y); };

  /* --------------------------- maze carving --------------------------- */
  Level.prototype.generate = function () {
    var W = this.W, H = this.H, rnd = this.rnd;
    var g = new Uint8Array(W * H); // all WALL
    this.grid = g;

    // 1. recursive backtracker on odd cells
    var stack = [];
    var sx = 1, sy = 1;
    g[sy * W + sx] = OPEN;
    stack.push([sx, sy]);
    var DIRS = [[0, -2], [2, 0], [0, 2], [-2, 0]];
    while (stack.length) {
      var top = stack[stack.length - 1];
      var cx = top[0], cy = top[1];
      var opts = [];
      for (var i = 0; i < 4; i++) {
        var nx = cx + DIRS[i][0], ny = cy + DIRS[i][1];
        if (nx > 0 && ny > 0 && nx < W - 1 && ny < H - 1 && g[ny * W + nx] === WALL) opts.push(i);
      }
      if (!opts.length) { stack.pop(); continue; }
      var d = DIRS[rnd.pick(opts)];
      var mx = cx + d[0] / 2, my = cy + d[1] / 2;
      g[my * W + mx] = OPEN;
      g[(cy + d[1]) * W + (cx + d[0])] = OPEN;
      stack.push([cx + d[0], cy + d[1]]);
    }

    // 2. braid: knock through walls to create loops (a perfect maze is a
    //    death sentence when something is always behind you)
    var braid = 0.16 + this.difficulty * 0.02;
    for (var y = 1; y < H - 1; y++) {
      for (var x = 1; x < W - 1; x++) {
        if (g[y * W + x] !== WALL) continue;
        var h = this.isOpen(x - 1, y) && this.isOpen(x + 1, y);
        var v = this.isOpen(x, y - 1) && this.isOpen(x, y + 1);
        if ((h || v) && rnd() < braid) g[y * W + x] = OPEN;
      }
    }

    // 3. rooms: carve rectangles so the house has halls, not just corridors
    this.rooms = [];
    var tries = 34;
    while (tries-- > 0 && this.rooms.length < 7) {
      var rw = rnd.int(3, 6), rh = rnd.int(3, 5);
      var rx = rnd.int(1, W - rw - 2), ry = rnd.int(1, H - rh - 2);
      var ok = true;
      for (var r = 0; r < this.rooms.length; r++) {
        var o = this.rooms[r];
        if (rx < o.x + o.w + 1 && rx + rw + 1 > o.x && ry < o.y + o.h + 1 && ry + rh + 1 > o.y) { ok = false; break; }
      }
      if (!ok) continue;
      for (var yy = ry; yy < ry + rh; yy++)
        for (var xx = rx; xx < rx + rw; xx++) g[yy * W + xx] = OPEN;
      this.rooms.push({ x: rx, y: ry, w: rw, h: rh });
    }

    // 4. open cells list + distance field from the start
    this.open = [];
    for (var y2 = 0; y2 < H; y2++)
      for (var x2 = 0; x2 < W; x2++)
        if (g[y2 * W + x2] === OPEN) this.open.push(x2 + y2 * W);

    this.start = { x: 1, y: 1 };
    // put the player in a room if one exists near a corner
    var best = null;
    for (var ri = 0; ri < this.rooms.length; ri++) {
      var rm = this.rooms[ri];
      var d2 = rm.x * rm.x + rm.y * rm.y;
      if (!best || d2 < best.d) best = { d: d2, r: rm };
    }
    if (best) this.start = { x: best.r.x + (best.r.w >> 1), y: best.r.y + (best.r.h >> 1) };

    this.dist = this.bfsField(this.start.x, this.start.y);

    // 5. surfaces per cell
    this.surface = new Uint8Array(W * H);
    for (var y3 = 0; y3 < H; y3++) {
      for (var x3 = 0; x3 < W; x3++) {
        var n = U.fbm(x3 * 0.16, y3 * 0.16, 3, this.seed + 5);
        this.surface[y3 * W + x3] = n < 0.42 ? 1 : 0;   // stone or wood
      }
    }
    // carpet runners down long straight corridors
    for (var y4 = 1; y4 < H - 1; y4++) {
      for (var x4 = 1; x4 < W - 1; x4++) {
        if (!this.isOpen(x4, y4)) continue;
        var horiz = this.isOpen(x4 - 1, y4) && this.isOpen(x4 + 1, y4) && !this.isOpen(x4, y4 - 1) && !this.isOpen(x4, y4 + 1);
        var vert = this.isOpen(x4, y4 - 1) && this.isOpen(x4, y4 + 1) && !this.isOpen(x4 - 1, y4) && !this.isOpen(x4 + 1, y4);
        if ((horiz || vert) && U.noise2(x4 * 0.5, y4 * 0.5, this.seed + 3) > 0.42) {
          this.surface[y4 * W + x4] = 2;
        }
      }
    }
    // wall dressing region: plaster vs wallpaper
    this.wallStyle = new Uint8Array(W * H);
    for (var y5 = 0; y5 < H; y5++)
      for (var x5 = 0; x5 < W; x5++)
        this.wallStyle[y5 * W + x5] = U.fbm(x5 * 0.11, y5 * 0.11, 3, this.seed + 77) > 0.5 ? 1 : 0;

    return this;
  };

  /** Breadth-first distance field over open cells. -1 = unreachable. */
  Level.prototype.bfsField = function (sx, sy) {
    var W = this.W, H = this.H;
    var d = new Int32Array(W * H).fill(-1);
    if (!this.isOpen(sx, sy)) return d;
    var q = [sx + sy * W], head = 0;
    d[sx + sy * W] = 0;
    while (head < q.length) {
      var c = q[head++], cx = c % W, cy = (c / W) | 0, nd = d[c] + 1;
      for (var i = 0; i < 4; i++) {
        var nx = cx + (i === 0 ? 1 : i === 1 ? -1 : 0);
        var ny = cy + (i === 2 ? 1 : i === 3 ? -1 : 0);
        if (!this.isOpen(nx, ny)) continue;
        var ni = nx + ny * W;
        if (d[ni] !== -1) continue;
        d[ni] = nd; q.push(ni);
      }
    }
    return d;
  };

  /** Path from (ax,ay) to (bx,by) as an array of cell indices, or null. */
  Level.prototype.path = function (ax, ay, bx, by) {
    var W = this.W;
    if (!this.isOpen(ax, ay) || !this.isOpen(bx, by)) return null;
    var from = new Int32Array(W * this.H).fill(-2);
    var s = ax + ay * W, t = bx + by * W;
    from[s] = -1;
    var q = [s], head = 0;
    while (head < q.length) {
      var c = q[head++];
      if (c === t) break;
      var cx = c % W, cy = (c / W) | 0;
      for (var i = 0; i < 4; i++) {
        var nx = cx + (i === 0 ? 1 : i === 1 ? -1 : 0);
        var ny = cy + (i === 2 ? 1 : i === 3 ? -1 : 0);
        if (!this.isOpen(nx, ny)) continue;
        var ni = nx + ny * W;
        if (from[ni] !== -2) continue;
        from[ni] = c; q.push(ni);
      }
    }
    if (from[t] === -2) return null;
    var out = [], cur = t;
    while (cur !== -1) { out.push(cur); cur = from[cur]; }
    out.reverse();
    return out;
  };

  /* --------------------------- materials --------------------------- */
  Level.prototype.buildMaterials = function () {
    var s = this.seed;
    var plaster = TX.plaster(s + 1);
    var paper = TX.wallpaper(s + 2);
    var wood = TX.wood(s + 3, false);
    var stone = TX.stone(s + 4);
    var kilim = TX.kilim(s + 5);
    var ceil = TX.ceiling(s + 6);

    function setRep(set, r) {
      for (var k in set) { set[k].repeat.set(r, r); set[k].needsUpdate = true; }
      return set;
    }

    // repeats are set per-mesh below by baking world units into the UVs,
    // so textures stay at 1:1 and we only need wrap mode.
    this.mat = {
      plaster: new THREE.MeshStandardMaterial({
        map: plaster.map, normalMap: plaster.normalMap, roughnessMap: plaster.roughnessMap,
        roughness: 1.0, metalness: 0.0, normalScale: new THREE.Vector2(1.25, 1.25),
        color: 0xd9c8a4, envMapIntensity: 0.35, vertexColors: true
      }),
      paper: new THREE.MeshStandardMaterial({
        map: paper.map, normalMap: paper.normalMap, roughnessMap: paper.roughnessMap,
        roughness: 1.0, metalness: 0.0, normalScale: new THREE.Vector2(1.0, 1.0),
        color: 0xd2c3a2, envMapIntensity: 0.32, vertexColors: true
      }),
      wood: new THREE.MeshStandardMaterial({
        map: wood.map, normalMap: wood.normalMap, roughnessMap: wood.roughnessMap,
        roughness: 0.95, metalness: 0.0, normalScale: new THREE.Vector2(1.1, 1.1),
        color: 0xdfd4c2, envMapIntensity: 0.38, vertexColors: true
      }),
      stone: new THREE.MeshStandardMaterial({
        map: stone.map, normalMap: stone.normalMap, roughnessMap: stone.roughnessMap,
        roughness: 0.96, metalness: 0.03, normalScale: new THREE.Vector2(1.3, 1.3),
        color: 0xc4c0b6, envMapIntensity: 0.4, vertexColors: true
      }),
      kilim: new THREE.MeshStandardMaterial({
        map: kilim.map, normalMap: kilim.normalMap, roughnessMap: kilim.roughnessMap,
        roughness: 1.0, metalness: 0.0, normalScale: new THREE.Vector2(0.8, 0.8),
        color: 0xede7db, envMapIntensity: 0.25, vertexColors: true
      }),
      ceiling: new THREE.MeshStandardMaterial({
        map: ceil.map, normalMap: ceil.normalMap, roughnessMap: ceil.roughnessMap,
        roughness: 1.0, metalness: 0.0, color: 0xb8b0a0, envMapIntensity: 0.25, vertexColors: true
      })
    };
    this._texSets = { plaster: plaster, paper: paper, wood: wood, stone: stone, kilim: kilim, ceiling: ceil };
    return this;
  };

  /* --------------------------- geometry build --------------------------- */
  Level.prototype.build = function () {
    var W = this.W, H = this.H, self = this;
    var bFloorWood = new Builder(), bFloorStone = new Builder(), bFloorKilim = new Builder();
    var bCeil = new Builder();
    var bWallP = new Builder(), bWallW = new Builder();

    var half = CS / 2;
    var TEX_WALL = 3.6;    // metres per wall texture tile
    var TEX_FLOOR = 3.2;

    // large-scale dirt so two neighbouring tiles never look identical
    function grime(x, z) {
      return 0.80 + U.fbm(x * 0.085, z * 0.085, 3, self.seed + 401) * 0.34;
    }

    function wallTint(px, py, pz, nx, ny, nz) {
      // corner occlusion: sample the wall field a little way into the room
      var prox = self.wallProximity(px + nx * 0.55, pz + nz * 0.55, 1.55);
      var corner = 1 - U.smoothstep(prox) * 0.30;
      // grime at the skirting, soot under the ceiling
      var low = 1 - U.clamp01(1 - py / 0.90) * 0.34;
      var high = 1 - U.clamp01((py - (WH - 1.0)) / 1.0) * 0.30;
      return U.clamp(corner * low * high * grime(px, pz), 0.16, 1.35);
    }

    function floorTint(px, py, pz) {
      var prox = self.wallProximity(px, pz, 1.45);
      var corner = 1 - U.smoothstep(prox) * 0.36;
      return U.clamp(corner * grime(px, pz), 0.16, 1.3);
    }

    function ceilTint(px, py, pz) {
      var prox = self.wallProximity(px, pz, 1.3);
      return U.clamp((1 - U.smoothstep(prox) * 0.40) * grime(px + 91, pz - 57) * 0.9, 0.12, 1.2);
    }

    for (var cy = 0; cy < H; cy++) {
      for (var cx = 0; cx < W; cx++) {
        if (!this.isOpen(cx, cy)) continue;
        var x = this.cellX(cx), z = this.cellZ(cy);
        var x0 = x - half, x1 = x + half, z0 = z - half, z1 = z + half;
        var surf = this.surface[cy * W + cx];
        var fb = surf === 1 ? bFloorStone : (surf === 2 ? bFloorKilim : bFloorWood);
        var fs = surf === 2 ? 1.9 : TEX_FLOOR;

        // floor (normal +Y)
        fb.quadSub([x0, 0, z1], [x1, 0, z1], [x1, 0, z0], [x0, 0, z0],
          x0 / fs, z1 / fs, x1 / fs, z0 / fs, 4, 4, floorTint);

        // ceiling (normal -Y)
        bCeil.quadSub([x0, WH, z0], [x1, WH, z0], [x1, WH, z1], [x0, WH, z1],
          x0 / 2.6, z0 / 2.6, x1 / 2.6, z1 / 2.6, 3, 3, ceilTint);

        var style = this.wallStyle[cy * W + cx];
        var wb = style ? bWallW : bWallP;

        if (!this.isOpen(cx, cy - 1)) {
          wb.quadSub([x0, 0, z0], [x1, 0, z0], [x1, WH, z0], [x0, WH, z0],
            x0 / TEX_WALL, WH / TEX_WALL, x1 / TEX_WALL, 0, 4, 5, wallTint);
        }
        if (!this.isOpen(cx, cy + 1)) {
          wb.quadSub([x1, 0, z1], [x0, 0, z1], [x0, WH, z1], [x1, WH, z1],
            -x1 / TEX_WALL, WH / TEX_WALL, -x0 / TEX_WALL, 0, 4, 5, wallTint);
        }
        if (!this.isOpen(cx - 1, cy)) {
          wb.quadSub([x0, 0, z1], [x0, 0, z0], [x0, WH, z0], [x0, WH, z1],
            z1 / TEX_WALL, WH / TEX_WALL, z0 / TEX_WALL, 0, 4, 5, wallTint);
        }
        if (!this.isOpen(cx + 1, cy)) {
          wb.quadSub([x1, 0, z0], [x1, 0, z1], [x1, WH, z1], [x1, WH, z0],
            -z0 / TEX_WALL, WH / TEX_WALL, -z1 / TEX_WALL, 0, 4, 5, wallTint);
        }
      }
    }

    function add(builder, mat, castShadow) {
      if (builder.empty()) return null;
      var m = new THREE.Mesh(builder.geometry(), mat);
      m.castShadow = !!castShadow;
      m.receiveShadow = true;
      m.matrixAutoUpdate = false;
      m.updateMatrix();
      self.group.add(m);
      return m;
    }

    add(bFloorWood, this.mat.wood, false);
    add(bFloorStone, this.mat.stone, false);
    add(bFloorKilim, this.mat.kilim, false);
    add(bCeil, this.mat.ceiling, false);
    this.wallMeshP = add(bWallP, this.mat.plaster, true);
    this.wallMeshW = add(bWallW, this.mat.paper, true);

    return this;
  };

  /* ------------------------------ doors ------------------------------ */
  Level.prototype.placeDoors = function (Props) {
    var W = this.W, H = this.H, rnd = this.rnd;
    var candidates = [];
    for (var cy = 1; cy < H - 1; cy++) {
      for (var cx = 1; cx < W - 1; cx++) {
        if (!this.isOpen(cx, cy)) continue;
        var horiz = this.isOpen(cx - 1, cy) && this.isOpen(cx + 1, cy) &&
          !this.isOpen(cx, cy - 1) && !this.isOpen(cx, cy + 1);
        var vert = this.isOpen(cx, cy - 1) && this.isOpen(cx, cy + 1) &&
          !this.isOpen(cx - 1, cy) && !this.isOpen(cx + 1, cy);
        if (!horiz && !vert) continue;
        if (Math.abs(cx - this.start.x) + Math.abs(cy - this.start.y) < 3) continue;
        candidates.push({ cx: cx, cy: cy, axis: horiz ? 'x' : 'z' });
      }
    }
    rnd.shuffle(candidates);
    var count = Math.min(candidates.length, 11);
    for (var i = 0; i < count; i++) {
      var c = candidates[i];
      // don't cluster doors
      var tooClose = false;
      for (var j = 0; j < this.doors.length; j++) {
        var d0 = this.doors[j];
        if (Math.abs(d0.cx - c.cx) + Math.abs(d0.cy - c.cy) < 4) { tooClose = true; break; }
      }
      if (tooClose) continue;
      var door = Props.makeDoor(this, c.cx, c.cy, c.axis, rnd);
      this.doors.push(door);
      this.group.add(door.pivotGroup);
    }
    return this;
  };

  /* ---------------------------- objectives ---------------------------- */
  Level.prototype.placeObjectives = function (Props) {
    var W = this.W, H = this.H, rnd = this.rnd;
    var self = this;

    // rank open cells by distance from the spawn, prefer dead ends
    var scored = [];
    for (var i = 0; i < this.open.length; i++) {
      var ci = this.open[i], cx = ci % W, cy = (ci / W) | 0;
      var d = this.dist[ci];
      if (d < 0) continue;
      var deg = 0;
      if (this.isOpen(cx - 1, cy)) deg++;
      if (this.isOpen(cx + 1, cy)) deg++;
      if (this.isOpen(cx, cy - 1)) deg++;
      if (this.isOpen(cx, cy + 1)) deg++;
      scored.push({ ci: ci, cx: cx, cy: cy, d: d, deg: deg, score: d + (deg === 1 ? 14 : 0) });
    }
    scored.sort(function (a, b) { return b.score - a.score; });

    // --- exit door: far from spawn, on an outer wall ---
    var exitCell = null;
    for (var e = 0; e < scored.length; e++) {
      var s = scored[e];
      var dir = null;
      if (s.cy === 1 && !this.isOpen(s.cx, 0)) dir = { dx: 0, dy: -1 };
      else if (s.cy === H - 2 && !this.isOpen(s.cx, H - 1)) dir = { dx: 0, dy: 1 };
      else if (s.cx === 1 && !this.isOpen(0, s.cy)) dir = { dx: -1, dy: 0 };
      else if (s.cx === W - 2 && !this.isOpen(W - 1, s.cy)) dir = { dx: 1, dy: 0 };
      if (dir) { exitCell = { cx: s.cx, cy: s.cy, dir: dir, d: s.d }; break; }
    }
    if (!exitCell) {
      // fall back to the farthest cell and just place it against any wall
      var f = scored[0];
      var dd = { dx: 0, dy: -1 };
      if (!this.isOpen(f.cx, f.cy - 1)) dd = { dx: 0, dy: -1 };
      else if (!this.isOpen(f.cx, f.cy + 1)) dd = { dx: 0, dy: 1 };
      else if (!this.isOpen(f.cx - 1, f.cy)) dd = { dx: -1, dy: 0 };
      else dd = { dx: 1, dy: 0 };
      exitCell = { cx: f.cx, cy: f.cy, dir: dd, d: f.d };
    }
    this.exit = Props.makeExit(this, exitCell);
    this.group.add(this.exit.group);

    // --- three muskas, spread apart and away from the exit ---
    var picks = [];
    var minSep = 7;
    for (var k = 0; k < scored.length && picks.length < 3; k++) {
      var c = scored[k];
      if (c.d < 6) continue;
      if (Math.abs(c.cx - this.exit.cx) + Math.abs(c.cy - this.exit.cy) < 5) continue;
      var ok = true;
      for (var p = 0; p < picks.length; p++) {
        if (Math.abs(c.cx - picks[p].cx) + Math.abs(c.cy - picks[p].cy) < minSep) { ok = false; break; }
      }
      if (!ok) continue;
      picks.push(c);
    }
    while (picks.length < 3 && scored.length > picks.length) {
      picks.push(scored[picks.length * 3 % scored.length]);
    }
    this.muskaCells = picks;
    for (var m = 0; m < picks.length; m++) {
      var it = Props.makeMuska(this, picks[m].cx, picks[m].cy, m);
      this.items.push(it);
      this.group.add(it.group);
    }

    // --- notes, batteries, stones: mid-distance, scattered ---
    var used = {};
    picks.forEach(function (c) { used[c.ci] = 1; });
    used[this.exit.cx + this.exit.cy * W] = 1;

    function takeCell(minD, maxD) {
      var pool = scored.filter(function (c) {
        return !used[c.ci] && c.d >= minD && c.d <= maxD;
      });
      if (!pool.length) pool = scored.filter(function (c) { return !used[c.ci]; });
      if (!pool.length) return null;
      var c = pool[rnd.int(0, pool.length - 1)];
      used[c.ci] = 1;
      return c;
    }

    var noteCount = 5;
    for (var nn = 0; nn < noteCount; nn++) {
      var nc = takeCell(3, 999);
      if (!nc) break;
      var note = Props.makeNote(this, nc.cx, nc.cy, nn);
      this.items.push(note); this.group.add(note.group);
    }
    var batCount = this.difficulty === 2 ? 2 : (this.difficulty === 1 ? 3 : 4);
    for (var bb = 0; bb < batCount; bb++) {
      var bc = takeCell(5, 999);
      if (!bc) break;
      var bat = Props.makeBattery(this, bc.cx, bc.cy);
      this.items.push(bat); this.group.add(bat.group);
    }
    var stoneCount = 5;
    for (var ss = 0; ss < stoneCount; ss++) {
      var sc = takeCell(2, 999);
      if (!sc) break;
      var st = Props.makeStonePile(this, sc.cx, sc.cy);
      this.items.push(st); this.group.add(st.group);
    }
    return this;
  };

  /* ---------------------------- decoration ---------------------------- */
  Level.prototype.decorate = function (Props) {
    Props.dressLevel(this);
    return this;
  };

  /* ---------------------------- collision ---------------------------- */
  /** Push a circle out of every wall cell and prop it overlaps. */
  Level.prototype.resolve = function (px, pz, radius, out) {
    var W = this.W, H = this.H, half = CS / 2;
    var cx = this.toCellX(px), cy = this.toCellY(pz);
    var push = { x: 0, z: 0 };
    var tmp = { x: 0, z: 0 };
    var hit = false;
    out.x = px; out.z = pz;

    for (var it = 0; it < 3; it++) {
      var moved = false;
      cx = this.toCellX(out.x); cy = this.toCellY(out.z);
      for (var dy = -1; dy <= 1; dy++) {
        for (var dx = -1; dx <= 1; dx++) {
          var nx = cx + dx, ny = cy + dy;
          if (this.isOpen(nx, ny)) continue;
          var wx = this.cellX(nx), wz = this.cellZ(ny);
          if (U.circleBoxPush(out.x, out.z, radius, wx - half, wz - half, wx + half, wz + half, tmp)) {
            out.x += tmp.x; out.z += tmp.z; hit = true; moved = true;
          }
        }
      }
      // static boxes (furniture, closed doors)
      for (var b = 0; b < this.boxes.length; b++) {
        var bx = this.boxes[b];
        if (bx.disabled) continue;
        if (U.circleBoxPush(out.x, out.z, radius, bx.minX, bx.minZ, bx.maxX, bx.maxZ, tmp)) {
          out.x += tmp.x; out.z += tmp.z; hit = true; moved = true;
        }
      }
      if (!moved) break;
    }
    return hit;
  };

  /** Cheap line-of-sight test on the grid (DDA through wall cells). */
  Level.prototype.lineOfSight = function (ax, az, bx, bz) {
    var dx = bx - ax, dz = bz - az;
    var dist = Math.hypot(dx, dz);
    if (dist < 0.001) return true;
    var steps = Math.ceil(dist / (CS * 0.32));
    for (var i = 1; i < steps; i++) {
      var t = i / steps;
      var x = ax + dx * t, z = az + dz * t;
      if (!this.isOpen(this.toCellX(x), this.toCellY(z))) return false;
      // closed doors block sight too
      for (var d = 0; d < this.doors.length; d++) {
        var dr = this.doors[d];
        if (dr.open || dr.broken) continue;
        if (Math.abs(x - dr.x) < CS * 0.5 && Math.abs(z - dr.z) < CS * 0.5) return false;
      }
    }
    return true;
  };

  /** 0 = open floor, 1 = right up against a wall. Used to bake occlusion. */
  Level.prototype.wallProximity = function (x, z, range) {
    var half = CS / 2;
    var cx = this.toCellX(x), cy = this.toCellY(z);
    var best = 1e9;
    for (var dy = -1; dy <= 1; dy++) {
      for (var dx = -1; dx <= 1; dx++) {
        var nx = cx + dx, ny = cy + dy;
        if (this.isOpen(nx, ny)) continue;
        var wx = this.cellX(nx), wz = this.cellZ(ny);
        var qx = U.clamp(x, wx - half, wx + half), qz = U.clamp(z, wz - half, wz + half);
        var d = Math.hypot(x - qx, z - qz);
        if (d < best) best = d;
      }
    }
    if (best > 1e8) return 0;
    return U.clamp01(1 - best / range);
  };

  Level.prototype.surfaceAt = function (x, z) {
    var cx = this.toCellX(x), cy = this.toCellY(z);
    if (!this.inside(cx, cy)) return 0;
    return this.surface[cy * this.W + cx];
  };

  Level.prototype.dispose = function () {
    this.group.traverse(function (o) {
      if (o.geometry) o.geometry.dispose();
      if (o.material) {
        var mats = Array.isArray(o.material) ? o.material : [o.material];
        mats.forEach(function (m) {
          for (var k in m) { if (m[k] && m[k].isTexture) m[k].dispose(); }
          m.dispose();
        });
      }
    });
  };

  Level.CS = CS;
  Level.WH = WH;
  Level.Builder = Builder;
  global.GLevel = Level;
})(window);
