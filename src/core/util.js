/* ==========================================================================
   GÜLYABANI — core utilities
   Deterministic RNG, math helpers, value noise, tiny helpers.
   No THREE access at load time: this file must be safe to parse before
   the 3D library has finished loading.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = {};

  /* ------------------------------ math ------------------------------ */
  U.clamp = function (v, a, b) { return v < a ? a : (v > b ? b : v); };
  U.clamp01 = function (v) { return v < 0 ? 0 : (v > 1 ? 1 : v); };
  U.lerp = function (a, b, t) { return a + (b - a) * t; };
  U.invLerp = function (a, b, v) { return b === a ? 0 : (v - a) / (b - a); };
  U.smoothstep = function (t) { t = U.clamp01(t); return t * t * (3 - 2 * t); };
  U.smootherstep = function (t) { t = U.clamp01(t); return t * t * t * (t * (t * 6 - 15) + 10); };
  U.sign = function (v) { return v < 0 ? -1 : (v > 0 ? 1 : 0); };
  U.TAU = Math.PI * 2;
  U.DEG = Math.PI / 180;

  /** Frame-rate independent exponential approach. rate = "how much closes per second". */
  U.damp = function (a, b, rate, dt) { return U.lerp(a, b, 1 - Math.exp(-rate * dt)); };

  /** Shortest signed angular difference b-a, wrapped to [-PI, PI]. */
  U.angDelta = function (a, b) {
    var d = (b - a) % U.TAU;
    if (d > Math.PI) d -= U.TAU;
    if (d < -Math.PI) d += U.TAU;
    return d;
  };

  U.dampAngle = function (a, b, rate, dt) {
    return a + U.angDelta(a, b) * (1 - Math.exp(-rate * dt));
  };

  /* ------------------------------ RNG ------------------------------ */
  /** Mulberry32: small, fast, good enough, fully deterministic from a seed. */
  U.rng = function (seed) {
    var s = (seed >>> 0) || 1;
    var f = function () {
      s = (s + 0x6D2B79F5) >>> 0;
      var t = s;
      t = Math.imul(t ^ (t >>> 15), t | 1);
      t ^= t + Math.imul(t ^ (t >>> 7), t | 61);
      return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
    };
    f.range = function (a, b) { return a + f() * (b - a); };
    f.int = function (a, b) { return Math.floor(a + f() * (b - a + 1)); };
    f.pick = function (arr) { return arr[Math.floor(f() * arr.length)]; };
    f.chance = function (p) { return f() < p; };
    f.sign = function () { return f() < 0.5 ? -1 : 1; };
    f.shuffle = function (arr) {
      for (var i = arr.length - 1; i > 0; i--) {
        var j = Math.floor(f() * (i + 1));
        var t = arr[i]; arr[i] = arr[j]; arr[j] = t;
      }
      return arr;
    };
    return f;
  };

  /** A shared, non-deterministic RNG for cosmetic effects. */
  U.rand = Math.random;
  U.randRange = function (a, b) { return a + Math.random() * (b - a); };
  U.randSign = function () { return Math.random() < 0.5 ? -1 : 1; };

  /* --------------------------- value noise --------------------------- */
  function hash2(x, y, seed) {
    var h = x * 374761393 + y * 668265263 + seed * 1442695040888963407;
    h = (h ^ (h >> 13)) * 1274126177;
    return ((h ^ (h >> 16)) >>> 0) / 4294967296;
  }
  U.hash2 = hash2;

  /** Smooth 2D value noise in [0,1]. */
  U.noise2 = function (x, y, seed) {
    seed = seed || 0;
    var xi = Math.floor(x), yi = Math.floor(y);
    var xf = x - xi, yf = y - yi;
    var u = xf * xf * (3 - 2 * xf), v = yf * yf * (3 - 2 * yf);
    var a = hash2(xi, yi, seed), b = hash2(xi + 1, yi, seed);
    var c = hash2(xi, yi + 1, seed), d = hash2(xi + 1, yi + 1, seed);
    return (a * (1 - u) + b * u) * (1 - v) + (c * (1 - u) + d * u) * v;
  };

  /** Fractal Brownian motion over value noise. */
  U.fbm = function (x, y, octaves, seed, gain, lacunarity) {
    gain = gain === undefined ? 0.5 : gain;
    lacunarity = lacunarity === undefined ? 2 : lacunarity;
    var amp = 1, freq = 1, sum = 0, norm = 0;
    for (var i = 0; i < octaves; i++) {
      sum += amp * U.noise2(x * freq, y * freq, (seed || 0) + i * 131);
      norm += amp; amp *= gain; freq *= lacunarity;
    }
    return sum / norm;
  };

  /** Tileable fbm: wraps seamlessly over a period p. */
  U.fbmTile = function (x, y, p, octaves, seed) {
    var amp = 1, f = 1, sum = 0, norm = 0;
    for (var i = 0; i < octaves; i++) {
      var pp = p * f;
      var xx = ((x * f) % pp + pp) % pp, yy = ((y * f) % pp + pp) % pp;
      // Blend the four wrapped corners so edges meet.
      var s = (seed || 0) + i * 977;
      var n = U.noise2(xx, yy, s);
      var n2 = U.noise2(xx - pp, yy, s);
      var n3 = U.noise2(xx, yy - pp, s);
      var n4 = U.noise2(xx - pp, yy - pp, s);
      var fx = xx / pp, fy = yy / pp;
      var v = (n * (1 - fx) + n2 * fx) * (1 - fy) + (n3 * (1 - fx) + n4 * fx) * fy;
      sum += amp * v; norm += amp; amp *= 0.5; f *= 2;
    }
    return sum / norm;
  };

  /* ------------------------------ misc ------------------------------ */
  U.fmtTime = function (sec) {
    sec = Math.max(0, sec | 0);
    var m = (sec / 60) | 0, s = sec % 60;
    return (m < 10 ? '0' : '') + m + ':' + (s < 10 ? '0' : '') + s;
  };

  U.store = {
    get: function (k, def) {
      try {
        var v = localStorage.getItem('gulyabani.' + k);
        return v === null ? def : JSON.parse(v);
      } catch (e) { return def; }
    },
    set: function (k, v) {
      try { localStorage.setItem('gulyabani.' + k, JSON.stringify(v)); } catch (e) { /* private mode */ }
    }
  };

  U.$ = function (sel) { return document.querySelector(sel); };
  U.$$ = function (sel) { return Array.prototype.slice.call(document.querySelectorAll(sel)); };

  /** Simple 2D circle-vs-axis-aligned-box overlap resolution helper. */
  U.circleBoxPush = function (cx, cz, r, minX, minZ, maxX, maxZ, out) {
    var qx = U.clamp(cx, minX, maxX);
    var qz = U.clamp(cz, minZ, maxZ);
    var dx = cx - qx, dz = cz - qz;
    var d2 = dx * dx + dz * dz;
    if (d2 >= r * r) return false;
    if (d2 > 1e-9) {
      var d = Math.sqrt(d2), push = r - d;
      out.x = (dx / d) * push; out.z = (dz / d) * push;
    } else {
      // Centre is inside the box: eject along the shallowest axis.
      var toL = cx - minX, toR = maxX - cx, toT = cz - minZ, toB = maxZ - cz;
      var m = Math.min(toL, toR, toT, toB);
      out.x = 0; out.z = 0;
      if (m === toL) out.x = -(toL + r);
      else if (m === toR) out.x = (toR + r);
      else if (m === toT) out.z = -(toT + r);
      else out.z = (toB + r);
    }
    return true;
  };

  /** Exponential moving-average smoother with a settable half life. */
  U.Smooth = function (initial, halfLife) {
    this.v = initial || 0;
    this.hl = halfLife || 0.15;
  };
  U.Smooth.prototype.step = function (target, dt) {
    var k = 1 - Math.pow(0.5, dt / this.hl);
    this.v += (target - this.v) * k;
    return this.v;
  };

  /** A small ring of recent values, for spike-resistant frame timing. */
  U.Ring = function (n, init) {
    this.a = new Float32Array(n); this.i = 0; this.n = n;
    for (var k = 0; k < n; k++) this.a[k] = init || 0;
  };
  U.Ring.prototype.push = function (v) { this.a[this.i] = v; this.i = (this.i + 1) % this.n; };
  U.Ring.prototype.avg = function () {
    var s = 0; for (var k = 0; k < this.n; k++) s += this.a[k];
    return s / this.n;
  };

  /* --------------------------- colour space ---------------------------
     This build of the 3D library predates automatic colour management, so
     a hex passed to a material or a light is consumed as a LINEAR value.
     Every colour in this project is authored the way a designer reads it,
     i.e. as sRGB, so each one is converted exactly once. Without this,
     "near-black" materials render as mid grey and the whole scene flattens.
  ------------------------------------------------------------------- */
  var _converted = (typeof WeakSet !== 'undefined') ? new WeakSet() : null;

  U.toLinear = function (color) {
    if (!color || !color.convertSRGBToLinear) return color;
    if (_converted) {
      if (_converted.has(color)) return color;
      _converted.add(color);
    }
    color.convertSRGBToLinear();
    return color;
  };

  /** sRGB hex -> a linear THREE.Color, safe to call repeatedly. */
  U.srgb = function (hex) {
    return new THREE.Color(hex).convertSRGBToLinear();
  };

  /** Walk a scene graph and correct every material and light colour. */
  U.linearizeGraph = function (root) {
    root.traverse(function (o) {
      if (o.isLight) {
        U.toLinear(o.color);
        if (o.groundColor) U.toLinear(o.groundColor);
      }
      if (o.material) {
        var mats = Array.isArray(o.material) ? o.material : [o.material];
        for (var i = 0; i < mats.length; i++) {
          var m = mats[i];
          if (!m) continue;
          U.toLinear(m.color);
          U.toLinear(m.emissive);
        }
      }
    });
  };

  global.GU = U;
})(window);
