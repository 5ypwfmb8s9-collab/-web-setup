/* ==========================================================================
   GÜLYABANI — procedural PBR texture factory
   Everything the game renders is generated at runtime on a 2D canvas:
   albedo, height (converted to a tangent-space normal map) and roughness.
   No external image assets, so the whole game runs offline from file://.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;
  var TX = { cache: {} };

  /* --------------------------- canvas helpers --------------------------- */
  function mk(size) {
    var c = document.createElement('canvas');
    c.width = c.height = size;
    return c;
  }

  function ctxOf(c) {
    var x = c.getContext('2d', { willReadFrequently: true });
    x.imageSmoothingEnabled = true;
    return x;
  }

  /** Fill a canvas per pixel. fn(x,y,u,v) -> [r,g,b] in 0..255. */
  function paint(c, fn) {
    var x = ctxOf(c), n = c.width;
    var img = x.createImageData(n, n), d = img.data, i = 0;
    for (var y = 0; y < n; y++) {
      for (var px = 0; px < n; px++) {
        var rgb = fn(px, y, px / n, y / n);
        d[i++] = rgb[0]; d[i++] = rgb[1]; d[i++] = rgb[2]; d[i++] = 255;
      }
    }
    x.putImageData(img, 0, 0);
    return c;
  }

  /** Grayscale height canvas from fn(x,y,u,v) -> 0..1 */
  function paintH(c, fn) {
    var x = ctxOf(c), n = c.width;
    var img = x.createImageData(n, n), d = img.data, i = 0;
    for (var y = 0; y < n; y++) {
      for (var px = 0; px < n; px++) {
        var v = (U.clamp01(fn(px, y, px / n, y / n)) * 255) | 0;
        d[i++] = v; d[i++] = v; d[i++] = v; d[i++] = 255;
      }
    }
    x.putImageData(img, 0, 0);
    return c;
  }

  /** Wrapping draw: repeats a drawing callback across the seam so tiles match. */
  function wrapDraw(ctx, n, cb) {
    for (var oy = -1; oy <= 1; oy++) {
      for (var ox = -1; ox <= 1; ox++) {
        ctx.save();
        ctx.translate(ox * n, oy * n);
        cb(ctx);
        ctx.restore();
      }
    }
  }

  /* ---------------------- height -> normal (Sobel) ---------------------- */
  function normalFromHeight(hc, strength) {
    var n = hc.width;
    var src = ctxOf(hc).getImageData(0, 0, n, n).data;
    var out = mk(n), oc = ctxOf(out);
    var img = oc.createImageData(n, n), d = img.data;

    function H(x, y) {
      x = ((x % n) + n) % n; y = ((y % n) + n) % n;
      return src[(y * n + x) * 4] / 255;
    }

    var i = 0;
    for (var y = 0; y < n; y++) {
      for (var x = 0; x < n; x++) {
        var tl = H(x - 1, y - 1), t = H(x, y - 1), tr = H(x + 1, y - 1);
        var l = H(x - 1, y), r = H(x + 1, y);
        var bl = H(x - 1, y + 1), b = H(x, y + 1), br = H(x + 1, y + 1);
        var dx = (tr + 2 * r + br) - (tl + 2 * l + bl);
        var dy = (bl + 2 * b + br) - (tl + 2 * t + tr);
        var nx = -dx * strength, ny = -dy * strength, nz = 1;
        var len = Math.sqrt(nx * nx + ny * ny + nz * nz);
        d[i++] = ((nx / len) * 0.5 + 0.5) * 255;
        d[i++] = ((ny / len) * 0.5 + 0.5) * 255;
        d[i++] = ((nz / len) * 0.5 + 0.5) * 255;
        d[i++] = 255;
      }
    }
    oc.putImageData(img, 0, 0);
    return out;
  }

  /** Roughness map derived from a height field plus an optional modulator. */
  function roughFromHeight(hc, lo, hi, invert) {
    var n = hc.width;
    var src = ctxOf(hc).getImageData(0, 0, n, n).data;
    var out = mk(n), oc = ctxOf(out);
    var img = oc.createImageData(n, n), d = img.data;
    for (var i = 0, j = 0; i < n * n; i++) {
      var h = src[i * 4] / 255;
      if (invert) h = 1 - h;
      var v = (U.lerp(lo, hi, h) * 255) | 0;
      d[j++] = v; d[j++] = v; d[j++] = v; d[j++] = 255;
    }
    oc.putImageData(img, 0, 0);
    return out;
  }

  /* ------------------------------ to THREE ------------------------------ */
  function tex(canvas, repeat, srgb, aniso) {
    var t = new THREE.CanvasTexture(canvas);
    t.wrapS = t.wrapT = THREE.RepeatWrapping;
    t.repeat.set(repeat || 1, repeat || 1);
    t.anisotropy = aniso || TX.maxAniso || 4;
    t.encoding = srgb ? THREE.sRGBEncoding : THREE.LinearEncoding;
    t.needsUpdate = true;
    return t;
  }
  TX.tex = tex;

  /** Bundle a colour + height pair into a THREE material set. */
  function bundle(colorCanvas, heightCanvas, opts) {
    opts = opts || {};
    var rep = opts.repeat || 1;
    var set = {
      map: tex(colorCanvas, rep, true),
      normalMap: tex(normalFromHeight(heightCanvas, opts.bump === undefined ? 2.2 : opts.bump), rep, false),
      roughnessMap: tex(roughFromHeight(heightCanvas, opts.rLo === undefined ? 0.55 : opts.rLo,
        opts.rHi === undefined ? 0.98 : opts.rHi, opts.rInv), rep, false)
    };
    return set;
  }

  /* ============================= GENERATORS ============================= */

  /* ---- worn lime plaster: the konak's walls ----
     Authored to survive tiling: the loud features (deep cracks, patches)
     are gone, and what is left is low-contrast mottling plus hairlines, so
     a repeated tile reads as one continuous surface rather than wallpaper. */
  TX.plaster = function (seed) {
    var N = 512, c = mk(N), h = mk(N);

    paint(c, function (x, y, u, v) {
      // three scales of mottling; the coarsest does most of the work
      var big = U.fbmTile(u * 2, v * 2, 2, 3, seed);
      var mid = U.fbmTile(u * 7, v * 7, 7, 4, seed + 17);
      var fine = U.fbmTile(u * 31, v * 31, 31, 3, seed + 41);
      var grain = U.fbmTile(u * 96, v * 96, 96, 2, seed + 63);

      var lum = 0.50 + big * 0.26 + mid * 0.16 + fine * 0.07 + grain * 0.04;

      // soft brown water staining, broad and low contrast
      var stain = U.smoothstep(U.fbmTile(u * 1.7, v * 1.7 + 0.9, 2, 3, seed + 31) * 1.5 - 0.62);
      // sooty haze near the ceiling, damp near the skirting
      var soot = U.clamp01(1 - v * 3.4) * 0.5 * (0.5 + mid);
      var damp = U.clamp01((v - 0.62) * 2.6) * (0.45 + mid * 0.7);

      var r = lum, g = lum * 0.955, b = lum * 0.855;
      r = U.lerp(r, r * 0.80, stain * 0.7);
      g = U.lerp(g, g * 0.68, stain * 0.7);
      b = U.lerp(b, b * 0.55, stain * 0.7);
      r = U.lerp(r, r * 0.58, damp * 0.8); g = U.lerp(g, g * 0.60, damp * 0.8); b = U.lerp(b, b * 0.66, damp * 0.8);
      r = U.lerp(r, r * 0.62, soot);       g = U.lerp(g, g * 0.63, soot);       b = U.lerp(b, b * 0.66, soot);

      return [r * 255, g * 255, b * 255];
    });

    paintH(h, function (x, y, u, v) {
      return 0.52 +
        U.fbmTile(u * 5, v * 5, 5, 4, seed) * 0.26 +
        U.fbmTile(u * 26, v * 26, 26, 3, seed + 5) * 0.14 +
        U.fbmTile(u * 90, v * 90, 90, 2, seed + 9) * 0.07;
    });

    // hairline cracks: many, thin, low contrast, drawn into both maps
    function cracks(ctx, colour, widthScale, alpha) {
      var rnd = U.rng(seed * 7 + 3);
      wrapDraw(ctx, N, function (g2) {
        g2.lineCap = 'round';
        for (var i = 0; i < 16; i++) {
          var px = rnd() * N, py = rnd() * N, a = rnd() * U.TAU;
          var segs = 14 + (rnd() * 22 | 0);
          var w = (0.35 + rnd() * 0.7) * widthScale;
          g2.beginPath(); g2.moveTo(px, py);
          for (var t = 0; t < segs; t++) {
            a += (rnd() - 0.5) * 0.75;
            px += Math.cos(a) * 6; py += Math.sin(a) * 6;
            g2.lineTo(px, py);
          }
          g2.strokeStyle = colour.replace('ALPHA', (alpha * (0.4 + rnd() * 0.6)).toFixed(2));
          g2.lineWidth = w;
          g2.stroke();
          // a couple of branches, so they read as fractures not scribbles
          if (rnd() < 0.55) {
            var bx = px, by = py, ba = a + (rnd() - 0.5) * 1.6;
            g2.beginPath(); g2.moveTo(bx, by);
            for (var k = 0; k < 7; k++) {
              ba += (rnd() - 0.5) * 0.8;
              bx += Math.cos(ba) * 5; by += Math.sin(ba) * 5;
              g2.lineTo(bx, by);
            }
            g2.lineWidth = w * 0.6;
            g2.stroke();
          }
        }
      });
    }
    cracks(ctxOf(c), 'rgba(46,38,30,ALPHA)', 1.0, 0.30);
    cracks(ctxOf(h), 'rgba(0,0,0,ALPHA)', 1.6, 0.55);

    // small chips where the lime has flaked off: subtle, never circular blobs
    var rnd3 = U.rng(seed + 555);
    var cx = ctxOf(c), hx = ctxOf(h);
    wrapDraw(cx, N, function (g2) {
      for (var i = 0; i < 14; i++) {
        var px = rnd3() * N, py = rnd3() * N, rr = 5 + rnd3() * 16;
        g2.beginPath();
        for (var a = 0; a <= U.TAU + 0.01; a += 0.5) {
          var rad = rr * (0.5 + rnd3() * 0.9);
          var vx = px + Math.cos(a) * rad, vy = py + Math.sin(a) * rad * 0.7;
          if (a === 0) g2.moveTo(vx, vy); else g2.lineTo(vx, vy);
        }
        g2.closePath();
        g2.fillStyle = 'rgba(96,80,64,0.34)';
        g2.fill();
      }
    });
    var rnd4 = U.rng(seed + 555);
    wrapDraw(hx, N, function (g2) {
      for (var i = 0; i < 14; i++) {
        var px = rnd4() * N, py = rnd4() * N, rr = 5 + rnd4() * 16;
        g2.beginPath();
        for (var a = 0; a <= U.TAU + 0.01; a += 0.5) {
          var rad = rr * (0.5 + rnd4() * 0.9);
          var vx = px + Math.cos(a) * rad, vy = py + Math.sin(a) * rad * 0.7;
          if (a === 0) g2.moveTo(vx, vy); else g2.lineTo(vx, vy);
        }
        g2.closePath();
        g2.fillStyle = 'rgba(0,0,0,0.45)';
        g2.fill();
      }
    });

    return bundle(c, h, { repeat: 1, bump: 2.1, rLo: 0.74, rHi: 0.99 });
  };

  /* ---- aged oak floorboards ---- */
  TX.wood = function (seed, dark) {
    var N = 512, c = mk(N), h = mk(N);
    var planks = 6, pw = N / planks;
    var rnd = U.rng(seed);
    var offs = [];
    for (var i = 0; i < planks; i++) offs.push({ o: rnd() * 40, tone: 0.78 + rnd() * 0.44, seam: rnd() * N });

    function plankAt(y) { var i = Math.floor(y / pw) % planks; return offs[(i + planks) % planks]; }

    paint(c, function (x, y, u, v) {
      var p = plankAt(y);
      var ly = (y % pw) / pw;                     // 0..1 across the board
      var grainY = (y * 0.06 + p.o);
      var grain = U.fbmTile(u * 3 + p.o, grainY * 0.5, 3, 3, seed + 11);
      var rings = Math.abs(Math.sin((u * 9 + grain * 5.5 + p.o) * Math.PI));
      rings = Math.pow(rings, 0.42);
      var edge = U.smoothstep(U.clamp01(Math.min(ly, 1 - ly) * 13));       // dark board gaps
      var wear = U.fbmTile(u * 5, v * 5, 5, 3, seed + 61);

      var base = (dark ? 44 : 70) + rings * (dark ? 22 : 40) + wear * 16;
      base *= p.tone;
      var r = base * 1.30, g = base * 0.92, b = base * 0.60;
      r *= (0.35 + edge * 0.65); g *= (0.35 + edge * 0.65); b *= (0.35 + edge * 0.65);
      // scuffs
      var scuff = U.smoothstep(U.fbmTile(u * 14, v * 14, 14, 2, seed + 3) * 1.4 - 0.62);
      r = U.lerp(r, r * 1.22, scuff); g = U.lerp(g, g * 1.2, scuff); b = U.lerp(b, b * 1.16, scuff);
      return [r, g, b];
    });

    paintH(h, function (x, y, u, v) {
      var p = plankAt(y);
      var ly = (y % pw) / pw;
      var edge = U.smoothstep(U.clamp01(Math.min(ly, 1 - ly) * 11));
      var grain = U.fbmTile(u * 4 + p.o, y * 0.03, 4, 3, seed + 11);
      var rings = Math.abs(Math.sin((u * 9 + grain * 5.5 + p.o) * Math.PI));
      return 0.16 + edge * 0.66 + rings * 0.13 + U.fbmTile(u * 30, v * 30, 30, 2, seed + 9) * 0.06;
    });

    return bundle(c, h, { repeat: 1, bump: 2.0, rLo: 0.42, rHi: 0.92 });
  };

  /* ---- irregular stone flags ---- */
  TX.stone = function (seed) {
    var N = 512, c = mk(N), h = mk(N);
    var cells = 5, cs = N / cells;
    var pts = [];
    var rnd = U.rng(seed + 17);
    for (var gy = -1; gy <= cells; gy++) {
      for (var gx = -1; gx <= cells; gx++) {
        pts.push({
          x: (gx + 0.5 + (rnd() - 0.5) * 0.62) * cs,
          y: (gy + 0.5 + (rnd() - 0.5) * 0.62) * cs,
          t: 0.72 + rnd() * 0.56
        });
      }
    }
    function nearest(x, y) {
      var b1 = 1e9, b2 = 1e9, bi = 0;
      for (var i = 0; i < pts.length; i++) {
        var dx = x - pts[i].x, dy = y - pts[i].y;
        var d = dx * dx + dy * dy;
        if (d < b1) { b2 = b1; b1 = d; bi = i; } else if (d < b2) b2 = d;
      }
      return { d1: Math.sqrt(b1), d2: Math.sqrt(b2), i: bi };
    }

    paint(c, function (x, y, u, v) {
      var wob = U.fbmTile(u * 9, v * 9, 9, 3, seed) * 11;
      var n = nearest(x + wob - 5.5, y + wob - 5.5);
      var edge = U.smoothstep(U.clamp01((n.d2 - n.d1) / 7));
      var g = U.fbmTile(u * 16, v * 16, 16, 4, seed + n.i * 31);
      var base = (58 + g * 44) * pts[n.i].t;
      var r = base * 1.03, gg = base * 1.0, b = base * 0.95;
      var mortar = 32 + U.fbmTile(u * 30, v * 30, 30, 2, seed + 3) * 20;
      r = U.lerp(mortar * 1.02, r, edge);
      gg = U.lerp(mortar, gg, edge);
      b = U.lerp(mortar * 0.94, b, edge);
      return [r, gg, b];
    });
    paintH(h, function (x, y, u, v) {
      var wob = U.fbmTile(u * 9, v * 9, 9, 3, seed) * 11;
      var n = nearest(x + wob - 5.5, y + wob - 5.5);
      var edge = U.smoothstep(U.clamp01((n.d2 - n.d1) / 7));
      return 0.12 + edge * 0.72 + U.fbmTile(u * 26, v * 26, 26, 3, seed + 5) * 0.14;
    });

    return bundle(c, h, { repeat: 1, bump: 2.5, rLo: 0.62, rHi: 0.99 });
  };

  /* ---- Anatolian kilim: the one warm thing in the house ---- */
  TX.kilim = function (seed) {
    var N = 512, c = mk(N), h = mk(N);
    var x = ctxOf(c);
    var rnd = U.rng(seed + 404);

    var MADDER = '#7d2a20', INDIGO = '#1d2b44', CREAM = '#c6b490',
      SAFFRON = '#9a742a', COAL = '#181410', TERRA = '#a2492c';

    x.fillStyle = COAL; x.fillRect(0, 0, N, N);

    // field
    x.fillStyle = MADDER; x.fillRect(0, 0, N, N);

    function diamond(cx, cy, w, hh, fill, stroke) {
      x.beginPath();
      x.moveTo(cx, cy - hh); x.lineTo(cx + w, cy); x.lineTo(cx, cy + hh); x.lineTo(cx - w, cy);
      x.closePath();
      if (fill) { x.fillStyle = fill; x.fill(); }
      if (stroke) { x.strokeStyle = stroke; x.lineWidth = 3; x.stroke(); }
    }
    // stepped "elibelinde" style hooks
    function hookRow(cy, col) {
      x.fillStyle = col;
      for (var i = -1; i < 9; i++) {
        var px = i * (N / 8);
        x.fillRect(px, cy, 12, 12);
        x.fillRect(px + 12, cy - 12, 12, 12);
        x.fillRect(px + 24, cy, 12, 12);
      }
    }

    // border bands
    var bw = 34;
    x.fillStyle = INDIGO;
    x.fillRect(0, 0, N, bw); x.fillRect(0, N - bw, N, bw);
    x.fillRect(0, 0, bw, N); x.fillRect(N - bw, 0, bw, N);
    x.fillStyle = CREAM;
    for (var i = 0; i < 16; i++) {
      var t = i * (N / 16) + 6;
      x.fillRect(t, 10, 14, 14); x.fillRect(t, N - 24, 14, 14);
      x.fillRect(10, t, 14, 14); x.fillRect(N - 24, t, 14, 14);
    }

    // central medallions
    for (var m = 0; m < 3; m++) {
      var cy = 96 + m * 160;
      diamond(N / 2, cy, 96, 72, INDIGO, CREAM);
      diamond(N / 2, cy, 58, 44, SAFFRON, COAL);
      diamond(N / 2, cy, 26, 20, TERRA, CREAM);
      hookRow(cy - 92, CREAM);
      hookRow(cy + 80, CREAM);
      // side motifs
      diamond(74, cy, 26, 34, SAFFRON, CREAM);
      diamond(N - 74, cy, 26, 34, SAFFRON, CREAM);
    }

    // weave: horizontal thread modulation + wear
    var img = x.getImageData(0, 0, N, N), d = img.data;
    for (var yy = 0; yy < N; yy++) {
      for (var xx = 0; xx < N; xx++) {
        var idx = (yy * N + xx) * 4;
        var thread = 0.82 + 0.18 * Math.abs(Math.sin(yy * Math.PI * 0.5));
        var warp = 0.9 + 0.1 * Math.abs(Math.sin(xx * Math.PI * 0.5));
        var dust = 0.72 + U.fbmTile(xx / N * 7, yy / N * 7, 7, 4, seed) * 0.5;
        var wear = U.smoothstep(U.fbmTile(xx / N * 3, yy / N * 3, 3, 3, seed + 8) * 1.5 - 0.7);
        var k = thread * warp * dust;
        d[idx] = U.clamp(d[idx] * k * U.lerp(1, 1.35, wear), 0, 255);
        d[idx + 1] = U.clamp(d[idx + 1] * k * U.lerp(1, 1.3, wear), 0, 255);
        d[idx + 2] = U.clamp(d[idx + 2] * k * U.lerp(1, 1.25, wear), 0, 255);
      }
    }
    x.putImageData(img, 0, 0);

    paintH(h, function (px, py, u, v) {
      var thread = 0.5 + 0.5 * Math.abs(Math.sin(py * Math.PI * 0.5));
      var warp = 0.5 + 0.5 * Math.abs(Math.sin(px * Math.PI * 0.5));
      return 0.3 + thread * 0.35 + warp * 0.2 + U.fbmTile(u * 12, v * 12, 12, 2, seed) * 0.15;
    });
    return bundle(c, h, { repeat: 1, bump: 1.1, rLo: 0.86, rHi: 1.0 });
  };

  /* ---- damask wallpaper, mostly peeled ---- */
  TX.wallpaper = function (seed) {
    var N = 512, c = mk(N), h = mk(N);
    var x = ctxOf(c);
    // base
    var grad = x.createLinearGradient(0, 0, 0, N);
    grad.addColorStop(0, '#4a4133'); grad.addColorStop(1, '#332c22');
    x.fillStyle = grad; x.fillRect(0, 0, N, N);
    // vertical stripes
    x.fillStyle = 'rgba(255,240,205,0.05)';
    for (var i = 0; i < 8; i++) x.fillRect(i * 64, 0, 30, N);

    // ogee motif
    function motif(cx, cy, s, alpha) {
      x.save(); x.translate(cx, cy); x.scale(s, s);
      x.strokeStyle = 'rgba(214,186,128,' + alpha + ')';
      x.fillStyle = 'rgba(184,152,96,' + (alpha * 0.32) + ')';
      x.lineWidth = 2.4;
      x.beginPath();
      x.moveTo(0, -34);
      x.bezierCurveTo(26, -26, 30, 4, 0, 34);
      x.bezierCurveTo(-30, 4, -26, -26, 0, -34);
      x.fill(); x.stroke();
      for (var k = 0; k < 4; k++) {
        x.save(); x.rotate(k * Math.PI / 2);
        x.beginPath(); x.moveTo(0, 0);
        x.bezierCurveTo(14, -12, 24, -6, 20, 10);
        x.stroke(); x.restore();
      }
      x.restore();
    }
    for (var gy = -1; gy < 5; gy++) {
      for (var gx = -1; gx < 5; gx++) {
        motif(gx * 128 + (gy % 2 ? 64 : 0) + 64, gy * 128 + 64, 1.15, 0.55);
      }
    }

    // age, stains, peel
    var img = x.getImageData(0, 0, N, N), d = img.data;
    for (var yy = 0; yy < N; yy++) {
      for (var xx = 0; xx < N; xx++) {
        var idx = (yy * N + xx) * 4;
        var u = xx / N, v = yy / N;
        var stain = U.smoothstep(U.fbmTile(u * 4, v * 4, 4, 4, seed) * 1.5 - 0.55);
        var k = 0.62 + U.fbmTile(u * 9, v * 9, 9, 3, seed + 2) * 0.55;
        d[idx] = U.clamp(d[idx] * k * U.lerp(1, 0.62, stain), 0, 255);
        d[idx + 1] = U.clamp(d[idx + 1] * k * U.lerp(1, 0.5, stain), 0, 255);
        d[idx + 2] = U.clamp(d[idx + 2] * k * U.lerp(1, 0.42, stain), 0, 255);
      }
    }
    x.putImageData(img, 0, 0);

    // peeled strips showing plaster
    var rnd = U.rng(seed + 77);
    for (var p = 0; p < 5; p++) {
      var px = rnd() * N, w = 16 + rnd() * 46, top = rnd() * N * 0.5;
      x.fillStyle = 'rgba(122,113,96,0.9)';
      x.beginPath(); x.moveTo(px, top);
      x.lineTo(px + w, top + 18);
      x.lineTo(px + w * 0.7, N);
      x.lineTo(px - 6, N);
      x.closePath(); x.fill();
    }

    paintH(h, function (px, py, u, v) {
      return 0.62 + U.fbmTile(u * 14, v * 14, 14, 3, seed) * 0.28 +
        U.fbmTile(u * 3, v * 3, 3, 2, seed + 4) * 0.1;
    });
    return bundle(c, h, { repeat: 1, bump: 1.5, rLo: 0.78, rHi: 1.0 });
  };

  /* ---- pitted, rusted iron ---- */
  TX.metal = function (seed) {
    var N = 256, c = mk(N), h = mk(N);
    paint(c, function (x, y, u, v) {
      var base = 46 + U.fbmTile(u * 10, v * 10, 10, 4, seed) * 30;
      var rust = U.smoothstep(U.fbmTile(u * 5, v * 5, 5, 4, seed + 3) * 1.5 - 0.5);
      var r = U.lerp(base, 108, rust), g = U.lerp(base, 54, rust), b = U.lerp(base, 26, rust);
      return [r, g, b];
    });
    paintH(h, function (x, y, u, v) {
      var pit = U.fbmTile(u * 26, v * 26, 26, 3, seed + 9);
      return 0.6 + pit * 0.35 - U.smoothstep(pit * 1.6 - 1.1) * 0.5;
    });
    return bundle(c, h, { repeat: 1, bump: 2.2, rLo: 0.35, rHi: 0.9 });
  };

  /* ---- carved door panel ---- */
  TX.doorwood = function (seed) {
    var N = 256, c = mk(N), h = mk(N);
    paint(c, function (x, y, u, v) {
      var grain = U.fbmTile(u * 2.4, v * 0.6, 3, 3, seed);
      var rings = Math.pow(Math.abs(Math.sin((v * 7 + grain * 5) * Math.PI)), 0.5);
      var base = 40 + rings * 26 + U.fbmTile(u * 16, v * 16, 16, 2, seed + 1) * 12;
      return [base * 1.32, base * 0.88, base * 0.56];
    });
    var hx = ctxOf(h);
    paintH(h, function (x, y, u, v) {
      var grain = U.fbmTile(u * 2.4, v * 0.6, 3, 3, seed);
      return 0.6 + Math.pow(Math.abs(Math.sin((v * 7 + grain * 5) * Math.PI)), 0.5) * 0.18;
    });
    // recessed panels
    hx.strokeStyle = 'rgba(0,0,0,0.9)'; hx.lineWidth = 7;
    hx.strokeRect(26, 22, N - 52, 96);
    hx.strokeRect(26, 140, N - 52, 94);
    hx.strokeStyle = 'rgba(255,255,255,0.35)'; hx.lineWidth = 2;
    hx.strokeRect(34, 30, N - 68, 80);
    hx.strokeRect(34, 148, N - 68, 78);
    return bundle(c, h, { repeat: 1, bump: 3.2, rLo: 0.5, rHi: 0.92 });
  };

  /* ---- ceiling: dark boards with beams ---- */
  TX.ceiling = function (seed) {
    var N = 256, c = mk(N), h = mk(N);
    paint(c, function (x, y, u, v) {
      var board = Math.floor(v * 8);
      var ly = (v * 8) % 1;
      var edge = U.smoothstep(U.clamp01(Math.min(ly, 1 - ly) * 9));
      var grain = U.fbmTile(u * 3 + board, v * 2, 4, 3, seed + board * 13);
      var base = (22 + grain * 20) * (0.8 + (board % 3) * 0.1);
      base *= (0.3 + edge * 0.7);
      return [base * 1.22, base * 0.96, base * 0.7];
    });
    paintH(h, function (x, y, u, v) {
      var ly = (v * 8) % 1;
      var edge = U.smoothstep(U.clamp01(Math.min(ly, 1 - ly) * 8));
      return 0.2 + edge * 0.6 + U.fbmTile(u * 20, v * 20, 20, 2, seed) * 0.12;
    });
    return bundle(c, h, { repeat: 1, bump: 1.8, rLo: 0.78, rHi: 1.0 });
  };

  /* ---- muska (amulet) emblem, drawn on a small emissive plate ---- */
  TX.muska = function () {
    var N = 128, c = mk(N), x = ctxOf(c);
    x.fillStyle = '#20160c'; x.fillRect(0, 0, N, N);
    x.strokeStyle = '#e0bb62'; x.lineWidth = 3;
    x.beginPath(); x.moveTo(64, 12); x.lineTo(116, 44); x.lineTo(116, 116);
    x.lineTo(12, 116); x.lineTo(12, 44); x.closePath(); x.stroke();
    x.lineWidth = 1.6;
    for (var i = 0; i < 5; i++) {
      x.beginPath(); x.moveTo(24, 56 + i * 12); x.lineTo(104, 56 + i * 12); x.stroke();
    }
    x.beginPath(); x.arc(64, 40, 12, 0, U.TAU); x.stroke();
    return tex(c, 1, true);
  };

  /* ---- a faded portrait, for the frames on the walls ---- */
  TX.portrait = function (seed) {
    var N = 128, c = mk(N), x = ctxOf(c);
    var rnd = U.rng(seed + 313);
    // sepia ground
    var g = x.createRadialGradient(N / 2, N * 0.42, 4, N / 2, N * 0.5, N * 0.75);
    g.addColorStop(0, '#6a5238'); g.addColorStop(1, '#1d160f');
    x.fillStyle = g; x.fillRect(0, 0, N, N);
    // a shoulder line and a head: a person, barely
    x.fillStyle = '#0e0a07';
    x.beginPath();
    x.moveTo(N * 0.10, N); x.quadraticCurveTo(N * 0.5, N * 0.56, N * 0.90, N);
    x.closePath(); x.fill();
    x.beginPath();
    x.ellipse(N / 2, N * 0.45, N * 0.15, N * 0.19, 0, 0, U.TAU);
    x.fillStyle = '#4a3826'; x.fill();
    // where the face should be, there is nothing
    x.beginPath();
    x.ellipse(N / 2, N * 0.47, N * 0.10, N * 0.13, 0, 0, U.TAU);
    x.fillStyle = 'rgba(10,7,5,0.85)'; x.fill();
    // foxing and scratches
    var img = x.getImageData(0, 0, N, N), d = img.data;
    for (var i = 0; i < N * N; i++) {
      var u = (i % N) / N, v = ((i / N) | 0) / N;
      var k = 0.62 + U.fbmTile(u * 6, v * 6, 6, 4, seed) * 0.7;
      d[i * 4] = U.clamp(d[i * 4] * k, 0, 255);
      d[i * 4 + 1] = U.clamp(d[i * 4 + 1] * k * 0.97, 0, 255);
      d[i * 4 + 2] = U.clamp(d[i * 4 + 2] * k * 0.9, 0, 255);
    }
    x.putImageData(img, 0, 0);
    x.strokeStyle = 'rgba(0,0,0,0.35)';
    for (var s2 = 0; s2 < 6; s2++) {
      x.beginPath();
      x.moveTo(rnd() * N, rnd() * N);
      x.lineTo(rnd() * N, rnd() * N);
      x.lineWidth = 0.6; x.stroke();
    }
    return tex(c, 1, true);
  };

  /* ---- paper for notes ---- */
  TX.paper = function (seed) {
    var N = 256, c = mk(N), h = mk(N);
    paint(c, function (x, y, u, v) {
      var n = U.fbmTile(u * 7, v * 7, 7, 4, seed);
      var age = U.smoothstep(U.fbmTile(u * 3, v * 3, 3, 3, seed + 4) * 1.4 - 0.45);
      var base = 150 + n * 50;
      return [base * U.lerp(1, 0.78, age), base * U.lerp(0.94, 0.62, age), base * U.lerp(0.78, 0.4, age)];
    });
    var cx = ctxOf(c);
    cx.strokeStyle = 'rgba(40,28,18,0.5)'; cx.lineWidth = 2;
    for (var i = 0; i < 9; i++) {
      cx.beginPath();
      var yy = 40 + i * 20;
      cx.moveTo(28, yy);
      for (var s = 0; s < 12; s++) cx.lineTo(28 + s * 16, yy + Math.sin(s * 1.7 + i) * 2.4);
      cx.stroke();
    }
    paintH(h, function (x, y, u, v) { return 0.55 + U.fbmTile(u * 20, v * 20, 20, 2, seed) * 0.25; });
    return bundle(c, h, { repeat: 1, bump: 0.8, rLo: 0.85, rHi: 1.0 });
  };

  /* ---- fabric / drapery ---- */
  TX.cloth = function (seed) {
    var N = 256, c = mk(N), h = mk(N);
    paint(c, function (x, y, u, v) {
      var w = 0.7 + 0.3 * Math.abs(Math.sin(x * 0.8)) * Math.abs(Math.sin(y * 0.8));
      var n = U.fbmTile(u * 5, v * 5, 5, 3, seed);
      var base = (26 + n * 26) * w;
      return [base * 1.05, base * 0.9, base * 0.86];
    });
    paintH(h, function (x, y, u, v) {
      return 0.4 + 0.3 * Math.abs(Math.sin(x * 0.8)) + 0.3 * U.fbmTile(u * 8, v * 8, 8, 3, seed);
    });
    return bundle(c, h, { repeat: 1, bump: 1.4, rLo: 0.9, rHi: 1.0 });
  };

  /* ------------------------ radial sprite helpers ------------------------ */
  TX.glowSprite = function (color, softness) {
    var N = 128, c = mk(N), x = ctxOf(c);
    var g = x.createRadialGradient(N / 2, N / 2, 0, N / 2, N / 2, N / 2);
    g.addColorStop(0, color);
    g.addColorStop(softness || 0.25, color.replace('rgb', 'rgba').replace(')', ',0.45)'));
    g.addColorStop(1, 'rgba(0,0,0,0)');
    x.fillStyle = g; x.fillRect(0, 0, N, N);
    var t = new THREE.CanvasTexture(c);
    t.encoding = THREE.sRGBEncoding;
    return t;
  };

  TX.smokeSprite = function (seed) {
    var N = 128, c = mk(N), x = ctxOf(c);
    var img = x.createImageData(N, N), d = img.data, i = 0;
    for (var y = 0; y < N; y++) {
      for (var px = 0; px < N; px++) {
        var u = px / N, v = y / N;
        var dx = u - 0.5, dy = v - 0.5;
        var r = Math.sqrt(dx * dx + dy * dy) * 2;
        var n = U.fbm(u * 5, v * 5, 4, seed || 1);
        var a = U.clamp01((1 - r) * 1.25) * (0.35 + n * 0.9);
        a = U.clamp01(a) * U.clamp01(1 - r);
        d[i++] = 200; d[i++] = 200; d[i++] = 210; d[i++] = a * 255;
      }
    }
    x.putImageData(img, 0, 0);
    var t = new THREE.CanvasTexture(c);
    t.encoding = THREE.sRGBEncoding;
    return t;
  };

  TX.dustSprite = function () {
    var N = 32, c = mk(N), x = ctxOf(c);
    var g = x.createRadialGradient(16, 16, 0, 16, 16, 16);
    g.addColorStop(0, 'rgba(255,250,235,1)');
    g.addColorStop(0.35, 'rgba(255,248,230,0.35)');
    g.addColorStop(1, 'rgba(255,248,230,0)');
    x.fillStyle = g; x.fillRect(0, 0, N, N);
    var t = new THREE.CanvasTexture(c);
    t.encoding = THREE.sRGBEncoding;
    return t;
  };

  /**
   * A tiny equirectangular environment. Metals are pure specular: with no
   * environment to reflect they render black, which is why the pistol and
   * every iron band looked like a silhouette. This gives them something to
   * catch without lifting the darkness.
   */
  TX.envMap = function () {
    var W = 256, H = 128;
    var c = document.createElement('canvas');
    c.width = W; c.height = H;
    var x = c.getContext('2d');
    var g = x.createLinearGradient(0, 0, 0, H);
    g.addColorStop(0.00, '#20293a');   // cold ceiling bounce
    g.addColorStop(0.42, '#141821');
    g.addColorStop(0.52, '#0d0f14');   // horizon
    g.addColorStop(0.78, '#241a12');   // warm floor bounce
    g.addColorStop(1.00, '#2e2016');
    x.fillStyle = g; x.fillRect(0, 0, W, H);
    // a couple of soft warm blobs standing in for candlelight in the room
    for (var i = 0; i < 5; i++) {
      var px = (i * 0.21 + 0.06) * W, py = H * (0.50 + Math.sin(i * 2.1) * 0.10);
      var rg = x.createRadialGradient(px, py, 0, px, py, W * 0.10);
      rg.addColorStop(0, 'rgba(255,168,72,0.42)');
      rg.addColorStop(1, 'rgba(255,168,72,0)');
      x.fillStyle = rg; x.fillRect(px - W * 0.1, py - W * 0.1, W * 0.2, W * 0.2);
    }
    var t = new THREE.CanvasTexture(c);
    t.mapping = THREE.EquirectangularReflectionMapping;
    t.encoding = THREE.sRGBEncoding;
    t.needsUpdate = true;
    return t;
  };

  /** Flashlight cookie: a soft disc with a faint reflector artefact. */
  TX.lightCookie = function () {
    var N = 256, c = mk(N), x = ctxOf(c);
    x.fillStyle = '#000'; x.fillRect(0, 0, N, N);
    var g = x.createRadialGradient(N / 2, N / 2, 0, N / 2, N / 2, N / 2);
    g.addColorStop(0, '#ffffff');
    g.addColorStop(0.55, '#e8e2d0');
    g.addColorStop(0.82, '#5d5748');
    g.addColorStop(1, '#000000');
    x.fillStyle = g; x.beginPath(); x.arc(N / 2, N / 2, N / 2, 0, U.TAU); x.fill();
    // reflector spokes
    x.globalCompositeOperation = 'multiply';
    x.strokeStyle = 'rgba(190,190,190,1)'; x.lineWidth = 3;
    for (var i = 0; i < 6; i++) {
      x.beginPath();
      var a = i * U.TAU / 6;
      x.moveTo(N / 2, N / 2);
      x.lineTo(N / 2 + Math.cos(a) * N / 2, N / 2 + Math.sin(a) * N / 2);
      x.stroke();
    }
    var t = new THREE.CanvasTexture(c);
    t.encoding = THREE.LinearEncoding;
    return t;
  };

  TX.mk = mk;
  TX.ctxOf = ctxOf;
  TX.normalFromHeight = normalFromHeight;
  TX.bundle = bundle;

  global.GTX = TX;
})(window);
