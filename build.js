#!/usr/bin/env node
/* ==========================================================================
   GÜLYABANI — bundler
   Inlines the stylesheet, the 3D library and every source file into a
   single page. Produces two artefacts from the same parts:

     dist/gulyabani.html  a complete standalone document. Double-click it,
                          or drop it on any static host. Works offline: the
                          game has no image, audio or model assets at all.
     dist/embed.html      body-level content only, for hosts that supply
                          their own document skeleton.

   No dependencies. Run with: node build.js
   ========================================================================== */
'use strict';

const fs = require('fs');
const path = require('path');

const ROOT = __dirname;
const OUT = path.join(ROOT, 'dist');

const SOURCES = [
  'src/core/util.js',
  'src/core/textures.js',
  'src/core/audio.js',
  'src/core/postfx.js',
  'src/world/level.js',
  'src/world/props.js',
  'src/game/player.js',
  'src/game/weapon.js',
  'src/game/ghost.js',
  'src/game/hud.js',
  'src/game/game.js',
  'src/main.js'
];

const FONT_URL =
  'https://fonts.googleapis.com/css2?family=Cinzel:wght@400;700;900' +
  '&family=Barlow+Condensed:wght@300;400;600&display=swap';

function read(rel) {
  return fs.readFileSync(path.join(ROOT, rel), 'utf8');
}

/** Guard against a literal </script> inside a source ending the tag early. */
function safe(js) {
  return js.replace(/<\/script>/gi, '<\\/script>');
}

function extractBody(html) {
  const open = html.indexOf('<body>');
  const close = html.lastIndexOf('</body>');
  if (open < 0 || close < 0) throw new Error('index.html has no <body>');
  return html.slice(open + 6, close);
}

/** Strip the markup that only exists to load external files. */
function stripLoaders(markup) {
  return markup
    .replace(/<script src="vendor\/three\.min\.js"[\s\S]*?<\/script>/i, '')
    .replace(/<script>\s*\/\/ Fallback[\s\S]*?<\/script>/i, '')
    .replace(/<script src="src\/[^"]+"><\/script>\s*/g, '')
    .trim();
}

function build() {
  const index = read('index.html');
  const css = read('src/style.css');
  const three = read('vendor/three.min.js');
  const markup = stripLoaders(extractBody(index));

  const bundle = SOURCES.map(function (f) {
    return '/* ===== ' + f + ' ===== */\n' + read(f);
  }).join('\n');

  const banner =
    '<!--\n' +
    '  GÜLYABANI — a survival-horror first-person game.\n' +
    '  Eight rounds, one door, and something walking behind you.\n\n' +
    '  Single-file build. Every texture is drawn on a canvas and every sound\n' +
    '  is synthesised with the Web Audio API at load time, so there are no\n' +
    '  external assets and the page runs with no network at all.\n' +
    '  Source: src/  ·  rebuild with: node build.js\n' +
    '-->\n';

  const head =
    '<title>GÜLYABANI</title>\n' +
    '<meta name="description" content="Ein Survival-Horror-Ego-Shooter. Acht Kugeln. Eine Tür. Etwas geht hinter dir.">\n' +
    '<link rel="preconnect" href="https://fonts.googleapis.com">\n' +
    '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>\n' +
    '<link href="' + FONT_URL + '" rel="stylesheet">\n' +
    '<style>\n' + css + '\n</style>\n';

  const scripts =
    '<script>\n' + safe(three) + '\n</script>\n' +
    '<script>\n' + safe(bundle) + '\n</script>\n';

  const standalone =
    '<!DOCTYPE html>\n<html lang="de">\n<head>\n' +
    '<meta charset="utf-8">\n' +
    '<meta name="viewport" content="width=device-width, initial-scale=1, maximum-scale=1, user-scalable=no, viewport-fit=cover">\n' +
    '<meta name="theme-color" content="#000000">\n' +
    head +
    '</head>\n<body>\n' + banner + markup + '\n' + scripts + '</body>\n</html>\n';

  // Body-level variant: the host provides <html>/<head>/<body>, so the font
  // request moves into the stylesheet as an @import.
  const embed =
    banner +
    '<title>GÜLYABANI</title>\n' +
    '<style>\n@import url("' + FONT_URL + '");\n' + css + '\n</style>\n' +
    markup + '\n' + scripts;

  fs.mkdirSync(OUT, { recursive: true });
  fs.writeFileSync(path.join(OUT, 'gulyabani.html'), standalone);
  fs.writeFileSync(path.join(OUT, 'embed.html'), embed);

  const kb = function (s) { return (Buffer.byteLength(s) / 1024).toFixed(0) + ' KB'; };
  process.stdout.write(
    'built dist/gulyabani.html  ' + kb(standalone) + '\n' +
    'built dist/embed.html      ' + kb(embed) + '\n' +
    '  library ' + kb(three) + '  ·  game ' + kb(bundle) + '  ·  styles ' + kb(css) + '\n'
  );
}

build();
