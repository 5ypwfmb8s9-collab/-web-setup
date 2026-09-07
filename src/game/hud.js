/* ==========================================================================
   GÜLYABANI — heads-up display
   Diegetic-ish and deliberately sparse: three meters, eight brass pips, a
   compass that only helps once the seal is broken, and a directional bloom
   that tells you which way to not look.
   ========================================================================== */
(function (global) {
  'use strict';

  var U = global.GU;

  /* ------------------------------ the notes ------------------------------ */
  var NOTES = [
    {
      title: 'Erste Seite — Reisetagebuch',
      body: 'Der Wirt in Safranbolu wollte kein Geld für das Zimmer. Er wollte nur, dass ich vor dem Abendgebet wieder unten bin.\n\n„Der Konak oben am Hang ist leer", sagte er. „Er ist seit vierzig Jahren leer, und er ist trotzdem nie leer."\n\nIch habe gelacht. Er nicht.'
    },
    {
      title: 'Zweite Seite — Der Hausherr',
      body: 'Der letzte Bewohner war ein Uhrmacher. Man fand seine Werkstatt unberührt: acht Patronen auf dem Tisch, ordentlich in einer Reihe, und eine Pistole mit einem selbstgebauten Dämpfer aus Messing und Filz.\n\nEr hatte etwas an die Wand geschrieben, immer wieder, in derselben Handschrift:\n\nSESSİZ OL. SESSİZ OL. SESSİZ OL.\n\nSei leise.'
    },
    {
      title: 'Dritte Seite — Was die Alten sagen',
      body: 'Sie sagen, er sei so groß wie zwei Männer und ganz aus Fell und Ketten. Sie sagen, er trägt einen Stock, mit dem er auf den Boden schlägt, damit du weißt, dass er noch da ist.\n\nSie sagen auch: Er geht nur hinter dir. Immer hinter dir. Wenn du ihn vor dir siehst, bist du schon nicht mehr da, wo du glaubst zu sein.\n\nUnd sie sagen: Blei prallt an ihm ab wie Regen an einem Dach — außer, du triffst ihn zwischen die Augen.'
    },
    {
      title: 'Vierte Seite — Die Muskalar',
      body: 'Drei Amulette, in Leder genäht. Der Uhrmacher hat sie im Haus verteilt, weil er wusste, dass er sie nicht alle bei sich tragen durfte — zusammen brennen sie zu hell, und das Licht zieht ihn an.\n\nEins in der Kammer. Eins beim Ofen. Eins dort, wo er zuletzt geschlafen hat.\n\nWenn alle drei wieder zusammen sind, reißt das Siegel der Ausgangstür. Nicht früher.'
    },
    {
      title: 'Letzte Seite',
      body: 'Ich habe fünf Mal geschossen und fünf Mal getroffen und er ist fünf Mal aufgestanden. Jedes Mal langsamer. Jedes Mal näher.\n\nDrei Patronen noch.\n\nWenn du das liest: Renn nicht die ganze Zeit. Du wirst müde und er wird es nicht. Mach das Licht aus, wenn du es nicht brauchst. Schließ die Türen hinter dir.\n\nUnd wenn er dich packt — wehr dich. Er hat keine Kraft, er hat nur Zeit.'
    }
  ];

  var WHISPERS = [
    'dön…', 'geri dön…', 'burada kal…', 'seni görüyorum…',
    'ışığı söndür…', 'yorgunsun…', 'daha yakın…', 'nefes al…'
  ];

  /* ================================ HUD ================================ */
  function HUD() {
    this.el = {
      hud: U.$('#hud'),
      stamina: U.$('#m-stamina .fill'),
      staminaBox: U.$('#m-stamina'),
      sanity: U.$('#m-sanity .fill'),
      sanityBox: U.$('#m-sanity'),
      battery: U.$('#m-battery .fill'),
      batteryBox: U.$('#m-battery'),
      ammoPips: U.$('#ammo-pips'),
      ammoNum: U.$('#ammo-num b'),
      ammoMax: U.$('#ammo-num s'),
      ammoBox: U.$('#ammo'),
      stones: U.$('#stone-count'),
      muskas: U.$$('#muskas i'),
      objText: U.$('#obj-text'),
      timer: U.$('#timer'),
      compass: U.$('#compass-strip'),
      danger: U.$('#danger'),
      dirInd: U.$('#dir-indicator'),
      crosshair: U.$('#crosshair'),
      prompt: U.$('#prompt'),
      promptKey: U.$('#prompt b'),
      promptTxt: U.$('#prompt span'),
      subs: U.$('#subs'),
      toasts: U.$('#toasts'),
      vignette: U.$('#hud-vignette'),
      qte: U.$('#qte'),
      qteFill: U.$('.qte-fill'),
      note: U.$('#note'),
      noteTitle: U.$('#note-title'),
      noteBody: U.$('#note-body')
    };
    this.pips = [];
    this.subsOn = true;
    this._lastAmmo = -1;
    this._lastMuska = -1;
    this._subTimer = 0;
    this._buildPips(8);
    this._buildCompass();
  }

  HUD.NOTES = NOTES;
  HUD.WHISPERS = WHISPERS;

  HUD.prototype._buildPips = function (n) {
    this.el.ammoPips.innerHTML = '';
    this.pips = [];
    for (var i = 0; i < n; i++) {
      var e = document.createElement('i');
      this.el.ammoPips.appendChild(e);
      this.pips.push(e);
    }
    this.el.ammoMax.textContent = '/' + n;
  };

  HUD.prototype._buildCompass = function () {
    var strip = this.el.compass;
    strip.innerHTML = '';
    this.compassMarks = [];
    var marks = [
      { a: 0, t: 'K', card: true }, { a: 45, t: '·' },
      { a: 90, t: 'D', card: true }, { a: 135, t: '·' },
      { a: 180, t: 'G', card: true }, { a: 225, t: '·' },
      { a: 270, t: 'B', card: true }, { a: 315, t: '·' }
    ];
    for (var i = 0; i < marks.length; i++) {
      var s = document.createElement('span');
      s.textContent = marks[i].t;
      if (marks[i].card) s.className = 'card';
      strip.appendChild(s);
      this.compassMarks.push({ el: s, a: marks[i].a });
    }
    var ex = document.createElement('span');
    ex.textContent = '◆';
    ex.className = 'exit';
    ex.style.display = 'none';
    strip.appendChild(ex);
    this.exitMark = ex;
  };

  HUD.prototype.show = function (on) {
    this.el.hud.classList.toggle('hidden', !on);
  };

  /* ------------------------------- update ------------------------------- */
  HUD.prototype.update = function (s) {
    var e = this.el;

    e.stamina.style.transform = 'scaleX(' + s.stamina.toFixed(3) + ')';
    e.sanity.style.transform = 'scaleX(' + s.sanity.toFixed(3) + ')';
    e.battery.style.transform = 'scaleX(' + s.battery.toFixed(3) + ')';
    e.sanityBox.classList.toggle('low', s.sanity < 0.3);
    e.batteryBox.classList.toggle('low', s.battery < 0.22 && s.lightOn);
    e.staminaBox.classList.toggle('low', s.stamina < 0.2);

    if (s.ammo !== this._lastAmmo) {
      this._lastAmmo = s.ammo;
      e.ammoNum.textContent = s.ammo;
      for (var i = 0; i < this.pips.length; i++) {
        this.pips[i].classList.toggle('spent', i >= s.ammo);
      }
      e.ammoBox.classList.toggle('empty', s.ammo === 0);
    }
    e.stones.textContent = s.stones;

    if (s.muskas !== this._lastMuska) {
      this._lastMuska = s.muskas;
      for (var m = 0; m < this.el.muskas.length; m++) {
        this.el.muskas[m].classList.toggle('got', m < s.muskas);
      }
      e.objText.textContent = s.muskas >= 3
        ? 'Das Siegel ist gebrochen — finde die Tür'
        : 'Finde die Muskalar — ' + s.muskas + ' von 3';
    }

    e.timer.textContent = U.fmtTime(s.time);

    // crosshair opens with spread, disappears on the sights
    var sp = 5 + s.spread * 620;
    e.crosshair.style.setProperty('--sp', sp.toFixed(1) + 'px');
    e.crosshair.classList.toggle('ads', s.ads > 0.55);

    // proximity vignette + the arrow that finds it for you
    e.danger.style.opacity = U.clamp01((1 - s.ghostDist / 9) * 0.55).toFixed(3);
    e.vignette.classList.toggle('tense', s.ghostDist < 8);
    if (s.ghostDist < 13) {
      e.dirInd.style.opacity = U.clamp01(1 - s.ghostDist / 13).toFixed(3);
      e.dirInd.style.transform = 'translate(-50%,-50%) rotate(' + (s.ghostBearing * 180 / Math.PI).toFixed(1) + 'deg)';
    } else {
      e.dirInd.style.opacity = 0;
    }

    this._updateCompass(s);

    if (this._subTimer > 0) {
      this._subTimer -= s.dt;
      if (this._subTimer <= 0) e.subs.innerHTML = '';
    }
  };

  HUD.prototype._updateCompass = function (s) {
    var yawDeg = (-s.yaw * 180 / Math.PI) % 360;
    if (yawDeg < 0) yawDeg += 360;
    var W = 200, PPD = 200 / 140;   // pixels per degree across the strip
    for (var i = 0; i < this.compassMarks.length; i++) {
      var m = this.compassMarks[i];
      var d = m.a - yawDeg;
      while (d > 180) d -= 360;
      while (d < -180) d += 360;
      var px = W / 2 + d * PPD;
      m.el.style.left = px.toFixed(1) + 'px';
      m.el.style.opacity = Math.abs(d) > 80 ? 0 : 1;
    }
    if (s.exitBearing !== null && s.exitBearing !== undefined) {
      this.exitMark.style.display = '';
      var ed = (s.exitBearing * 180 / Math.PI);
      while (ed > 180) ed -= 360;
      while (ed < -180) ed += 360;
      this.exitMark.style.left = (W / 2 + ed * PPD).toFixed(1) + 'px';
      this.exitMark.style.opacity = Math.abs(ed) > 80 ? 0 : 1;
    } else {
      this.exitMark.style.display = 'none';
    }
  };

  /* ------------------------------ messaging ------------------------------ */
  HUD.prototype.toast = function (text, warn) {
    var d = document.createElement('div');
    d.className = 'toast' + (warn ? ' warn' : '');
    d.textContent = text;
    this.el.toasts.appendChild(d);
    setTimeout(function () { if (d.parentNode) d.parentNode.removeChild(d); }, 3600);
  };

  HUD.prototype.subtitle = function (text, isGhost, dur) {
    if (!this.subsOn) return;
    this.el.subs.innerHTML = '';
    var d = document.createElement('div');
    d.className = 'sub' + (isGhost ? ' ghost' : '');
    d.textContent = text;
    this.el.subs.appendChild(d);
    this._subTimer = dur || 3.2;
  };

  HUD.prototype.prompt = function (text, key) {
    if (!text) { this.el.prompt.classList.add('hidden'); return; }
    this.el.prompt.classList.remove('hidden');
    this.el.promptKey.textContent = key || 'E';
    this.el.promptTxt.textContent = text;
  };

  HUD.prototype.qte = function (on, progress) {
    this.el.qte.classList.toggle('hidden', !on);
    if (on) this.el.qteFill.style.width = (U.clamp01(progress) * 100).toFixed(1) + '%';
  };

  HUD.prototype.showNote = function (index) {
    var n = NOTES[index % NOTES.length];
    this.el.noteTitle.textContent = n.title;
    this.el.noteBody.textContent = n.body;
    this.el.note.classList.remove('hidden');
  };
  HUD.prototype.hideNote = function () {
    this.el.note.classList.add('hidden');
  };

  global.GHUD = HUD;
})(window);
