/* ==========================================================================
   GÜLYABANI — post-processing
   A hand-rolled composer (no library add-ons): threshold bloom, then a
   single composite pass doing lens distortion, chromatic aberration,
   unsharp-mask sharpening, filmic grade, vignette, grain and the fear warp.
   Sharpening is deliberate: the brief asked for a crisp image, and a
   supersampled buffer plus unsharp mask reads far sharper than FXAA.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;

  var QUAD_VS = [
    'varying vec2 vUv;',
    'void main(){ vUv = uv; gl_Position = vec4(position.xy, 0.0, 1.0); }'
  ].join('\n');

  /* ------------------------------ bright pass ------------------------------ */
  var BRIGHT_FS = [
    'uniform sampler2D tDiffuse;',
    'uniform float threshold;',
    'uniform float knee;',
    'uniform float intensity;',
    'varying vec2 vUv;',
    'void main(){',
    '  vec3 c = texture2D(tDiffuse, vUv).rgb;',
    '  float l = dot(c, vec3(0.2126, 0.7152, 0.0722));',
    '  float soft = clamp(l - threshold + knee, 0.0, 2.0 * knee);',
    '  soft = soft * soft / (4.0 * knee + 1e-4);',
    '  float contrib = max(soft, l - threshold) / max(l, 1e-4);',
    '  gl_FragColor = vec4(c * contrib * intensity, 1.0);',
    '}'
  ].join('\n');

  /* -------------------------------- blur -------------------------------- */
  var BLUR_FS = [
    'uniform sampler2D tDiffuse;',
    'uniform vec2 dir;',        // texel-sized direction
    'varying vec2 vUv;',
    'void main(){',
    '  vec3 s = texture2D(tDiffuse, vUv).rgb * 0.227027;',
    '  s += texture2D(tDiffuse, vUv + dir * 1.3846153846).rgb * 0.3162162162;',
    '  s += texture2D(tDiffuse, vUv - dir * 1.3846153846).rgb * 0.3162162162;',
    '  s += texture2D(tDiffuse, vUv + dir * 3.2307692308).rgb * 0.0702702703;',
    '  s += texture2D(tDiffuse, vUv - dir * 3.2307692308).rgb * 0.0702702703;',
    '  gl_FragColor = vec4(s, 1.0);',
    '}'
  ].join('\n');

  /* ------------------------------ composite ------------------------------ */
  var COMP_FS = [
    'uniform sampler2D tDiffuse;',
    'uniform sampler2D tBloom;',
    'uniform vec2  resolution;',
    'uniform float time;',
    'uniform float bloomAmount;',
    'uniform float grain;',
    'uniform float vignette;',
    'uniform float aberration;',
    'uniform float distortion;',
    'uniform float sharpen;',
    'uniform float fear;',        // 0..1 — warps and desaturates
    'uniform float hurt;',        // 0..1 — red pulse
    'uniform float flash;',       // lightning / muzzle bloom
    'uniform float fade;',        // 1 = fully black
    'uniform float exposure;',
    'uniform float contrast;',
    'uniform float saturation;',
    'uniform float scanline;',
    'varying vec2 vUv;',

    'float hash13(vec3 p){',
    '  p = fract(p * 0.1031);',
    '  p += dot(p, p.zyx + 31.32);',
    '  return fract((p.x + p.y) * p.z);',
    '}',

    'vec3 sampleScene(vec2 uv){ return texture2D(tDiffuse, uv).rgb; }',

    'void main(){',
    '  vec2 uv = vUv;',
    '  vec2 c = uv - 0.5;',
    '  float r2 = dot(c, c);',

    // --- barrel distortion (lens) ---
    '  vec2 duv = uv + c * r2 * distortion;',

    // --- fear warp: the room breathes ---
    '  if (fear > 0.001) {',
    '    float w = fear * 0.012;',
    '    duv.x += sin(uv.y * 22.0 + time * 2.3) * w;',
    '    duv.y += cos(uv.x * 18.0 + time * 1.7) * w * 0.8;',
    '    duv += c * sin(time * 1.1) * fear * 0.006;',
    '  }',

    // --- chromatic aberration, stronger at the edges ---
    '  float ab = aberration * (0.35 + r2 * 2.2) * (1.0 + fear * 2.5);',
    '  vec2 off = c * ab;',
    '  vec3 col;',
    '  col.r = sampleScene(duv + off).r;',
    '  col.g = sampleScene(duv).g;',
    '  col.b = sampleScene(duv - off).b;',

    // --- unsharp mask: crisp edges without the FXAA smear ---
    '  if (sharpen > 0.001) {',
    '    vec2 t = 1.0 / resolution;',
    '    vec3 blur = sampleScene(duv + vec2(t.x, 0.0))',
    '              + sampleScene(duv - vec2(t.x, 0.0))',
    '              + sampleScene(duv + vec2(0.0, t.y))',
    '              + sampleScene(duv - vec2(0.0, t.y));',
    '    blur *= 0.25;',
    '    col += (col - blur) * sharpen;',
    '  }',

    // --- bloom ---
    '  vec3 bl = texture2D(tBloom, duv).rgb;',
    '  col += bl * bloomAmount;',

    // --- lightning / muzzle flash lift ---
    '  col += flash * vec3(0.86, 0.90, 1.0);',

    // --- filmic grade ---
    '  col *= exposure;',
    '  float lum = dot(col, vec3(0.2126, 0.7152, 0.0722));',
    '  col = mix(vec3(lum), col, saturation * (1.0 - fear * 0.55));',
    '  col = (col - 0.5) * contrast + 0.5;',
    // cool the shadows, warm the highlights: cheap two-tone grade
    '  float sh = 1.0 - smoothstep(0.0, 0.42, lum);',
    '  col = mix(col, col * vec3(0.80, 0.90, 1.16), sh * 0.55);',
    '  float hi = smoothstep(0.55, 1.0, lum);',
    '  col = mix(col, col * vec3(1.10, 1.02, 0.86), hi * 0.35);',

    // --- pain ---
    '  if (hurt > 0.001) {',
    '    col = mix(col, vec3(0.42, 0.02, 0.01), hurt * (0.35 + r2 * 1.4));',
    '  }',

    // --- vignette ---
    '  float vig = smoothstep(0.85, 0.16, r2 * (1.0 + fear * 0.6));',
    '  col *= mix(1.0, vig, vignette);',

    // --- film grain (animated, luminance-weighted so it lives in shadow) ---
    '  if (grain > 0.001) {',
    '    float n = hash13(vec3(gl_FragCoord.xy, floor(time * 24.0)));',
    '    float n2 = hash13(vec3(gl_FragCoord.yx * 1.7, floor(time * 24.0) + 11.0));',
    '    float g = (n - 0.5) * 0.75 + (n2 - 0.5) * 0.25;',
    '    float lw = 1.0 - smoothstep(0.0, 0.7, dot(col, vec3(0.333)));',
    '    col += g * grain * (0.35 + lw * 1.15);',
    '  }',

    // --- faint interlace, only when fear is high ---
    '  if (scanline > 0.001) {',
    '    col *= 1.0 - scanline * 0.16 * step(0.5, fract(gl_FragCoord.y * 0.5));',
    '  }',

    '  col *= (1.0 - fade);',
    '  gl_FragColor = vec4(max(col, 0.0), 1.0);',
    '}'
  ].join('\n');

  /* ========================================================================= */

  function PostFX(renderer, quality) {
    this.renderer = renderer;
    this.quality = quality === undefined ? 1 : quality;

    var geo = new THREE.PlaneGeometry(2, 2);
    this.scene = new THREE.Scene();
    this.cam = new THREE.OrthographicCamera(-1, 1, 1, -1, 0, 1);
    this.quad = new THREE.Mesh(geo, null);
    this.quad.frustumCulled = false;
    this.scene.add(this.quad);

    var rtOpts = {
      minFilter: THREE.LinearFilter,
      magFilter: THREE.LinearFilter,
      format: THREE.RGBAFormat,
      type: THREE.UnsignedByteType,
      encoding: THREE.sRGBEncoding,
      depthBuffer: true,
      stencilBuffer: false
    };
    this.sceneRT = new THREE.WebGLRenderTarget(2, 2, rtOpts);
    this.sceneRT.texture.generateMipmaps = false;

    var half = {
      minFilter: THREE.LinearFilter, magFilter: THREE.LinearFilter,
      format: THREE.RGBAFormat, type: THREE.UnsignedByteType,
      encoding: THREE.sRGBEncoding, depthBuffer: false, stencilBuffer: false
    };
    this.brightRT = new THREE.WebGLRenderTarget(2, 2, half);
    this.blurA = new THREE.WebGLRenderTarget(2, 2, half);
    this.blurB = new THREE.WebGLRenderTarget(2, 2, half);
    this.blurA2 = new THREE.WebGLRenderTarget(2, 2, half);
    this.blurB2 = new THREE.WebGLRenderTarget(2, 2, half);

    this.matBright = new THREE.ShaderMaterial({
      uniforms: {
        tDiffuse: { value: null },
        threshold: { value: 0.62 },
        knee: { value: 0.28 },
        intensity: { value: 1.0 }
      },
      vertexShader: QUAD_VS, fragmentShader: BRIGHT_FS,
      depthTest: false, depthWrite: false
    });

    this.matBlur = new THREE.ShaderMaterial({
      uniforms: { tDiffuse: { value: null }, dir: { value: new THREE.Vector2() } },
      vertexShader: QUAD_VS, fragmentShader: BLUR_FS,
      depthTest: false, depthWrite: false
    });

    this.matComp = new THREE.ShaderMaterial({
      uniforms: {
        tDiffuse: { value: null },
        tBloom: { value: null },
        resolution: { value: new THREE.Vector2(1, 1) },
        time: { value: 0 },
        bloomAmount: { value: 0.55 },
        grain: { value: 0.055 },
        vignette: { value: 0.9 },
        aberration: { value: 0.0022 },
        distortion: { value: 0.055 },
        sharpen: { value: 0.5 },
        fear: { value: 0 },
        hurt: { value: 0 },
        flash: { value: 0 },
        fade: { value: 0 },
        exposure: { value: 1.0 },
        contrast: { value: 1.07 },
        saturation: { value: 0.92 },
        scanline: { value: 0 }
      },
      vertexShader: QUAD_VS, fragmentShader: COMP_FS,
      depthTest: false, depthWrite: false
    });

    this.u = this.matComp.uniforms;
  }

  PostFX.prototype.setSize = function (w, h) {
    w = Math.max(2, w | 0); h = Math.max(2, h | 0);
    this.width = w; this.height = h;
    this.sceneRT.setSize(w, h);
    var bw = Math.max(2, (w / 2) | 0), bh = Math.max(2, (h / 2) | 0);
    this.brightRT.setSize(bw, bh);
    this.blurA.setSize(bw, bh);
    this.blurB.setSize(bw, bh);
    var qw = Math.max(2, (w / 4) | 0), qh = Math.max(2, (h / 4) | 0);
    this.blurA2.setSize(qw, qh);
    this.blurB2.setSize(qw, qh);
    this.u.resolution.value.set(w, h);
  };

  PostFX.prototype.setQuality = function (q) {
    this.quality = q;
  };

  PostFX.prototype._pass = function (mat, target) {
    this.quad.material = mat;
    this.renderer.setRenderTarget(target || null);
    this.renderer.clear(true, true, false);
    this.renderer.render(this.scene, this.cam);
  };

  /** Render the composed frame. `renderScene` draws the world into sceneRT. */
  PostFX.prototype.render = function (renderScene) {
    var r = this.renderer;

    r.setRenderTarget(this.sceneRT);
    r.clear();
    renderScene(this.sceneRT);

    if (this.quality > 0) {
      // bright pass
      this.matBright.uniforms.tDiffuse.value = this.sceneRT.texture;
      this._pass(this.matBright, this.brightRT);

      // blur level 1 (half res)
      var bw = this.brightRT.width, bh = this.brightRT.height;
      this.matBlur.uniforms.tDiffuse.value = this.brightRT.texture;
      this.matBlur.uniforms.dir.value.set(1 / bw, 0);
      this._pass(this.matBlur, this.blurA);
      this.matBlur.uniforms.tDiffuse.value = this.blurA.texture;
      this.matBlur.uniforms.dir.value.set(0, 1 / bh);
      this._pass(this.matBlur, this.blurB);

      if (this.quality > 1) {
        // blur level 2 (quarter res) for a wider, softer halo
        var qw = this.blurA2.width, qh = this.blurA2.height;
        this.matBlur.uniforms.tDiffuse.value = this.blurB.texture;
        this.matBlur.uniforms.dir.value.set(1 / qw, 0);
        this._pass(this.matBlur, this.blurA2);
        this.matBlur.uniforms.tDiffuse.value = this.blurA2.texture;
        this.matBlur.uniforms.dir.value.set(0, 1 / qh);
        this._pass(this.matBlur, this.blurB2);
        this.u.tBloom.value = this.blurB2.texture;
      } else {
        this.u.tBloom.value = this.blurB.texture;
      }
    } else {
      this.u.tBloom.value = this.blurB.texture;
    }

    this.u.tDiffuse.value = this.sceneRT.texture;
    this._pass(this.matComp, null);
    r.setRenderTarget(null);
  };

  PostFX.prototype.dispose = function () {
    [this.sceneRT, this.brightRT, this.blurA, this.blurB, this.blurA2, this.blurB2]
      .forEach(function (t) { t.dispose(); });
    this.matBright.dispose(); this.matBlur.dispose(); this.matComp.dispose();
    this.quad.geometry.dispose();
  };

  global.GPostFX = PostFX;
})(window);
