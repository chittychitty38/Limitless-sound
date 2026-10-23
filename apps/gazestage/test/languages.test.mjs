// GazeStage in the suite's language: every word in its window, its menu and its answers to other
// apps has Spanish, and the Spanish keeps every placeholder and tag.
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { SCALES, XY_PROFILES } from '../renderer/lib.js';
import { SYNTH_PRESETS } from '../renderer/synth.js';

const read = (file) => readFileSync(new URL(file, import.meta.url), 'utf8');
const page = read('../renderer/index.html');
const app = read('../renderer/app.js');
const main = read('../main.js');
const TABLE = '<script type="application/json" id="strings-es">';
const es = JSON.parse(page.slice(page.indexOf(TABLE) + TABLE.length, page.indexOf('</script>', page.indexOf(TABLE))));

// Names, Pro Tools' own words and port names read the same in every language.
const SAME_EVERYWHERE = new Set(['GazeStage', 'Pro Tools', 'MIDI', 'HUI']);
const missing = (words) => [...new Set(words)].filter((w) => /[A-Za-z]{2}/.test(w) && !(w in es) && !SAME_EVERYWHERE.has(w));

// The page's own words: text in the body outside scripts, styles and pictures, and aria-labels and
// titles. A sentence with bold words in it (data-html) is one entry, markup and all.
function pageWords(html) {
  let body = html.slice(html.indexOf('<body'));
  body = body.replace(/<!--[\s\S]*?-->/g, '').replace(/<(script|style|svg)\b[\s\S]*?<\/\1>/g, '');
  const words = [];
  body = body.replace(/<(\w+)\b[^>]*\sdata-html\b[^>]*>([\s\S]*?)<\/\1>/g, (_m, _tag, inner) => { words.push(inner.trim()); return ''; });
  for (const m of body.matchAll(/\s(?:aria-label|title)="([^"]*)"/g)) words.push(m[1]);
  for (const text of body.replace(/<[^>]*>/g, '\n').split('\n')) {
    const w = text.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').trim();
    if (w) words.push(w);
  }
  return words;
}

// Text the scripts put through t('…'), and the built-in menu items' English names (role(…, '…')).
function scriptWords(src) {
  const words = [...src.matchAll(/\bt\((['"])((?:\\.|(?!\1)[^\\])*)\1/g)].map((m) => m[2].replace(/\\(.)/g, '$1'));
  return words.concat([...src.matchAll(/\brole\('\w+', '([^']+)'/g)].map((m) => m[1]));
}

test('every word in the window has Spanish', () => {
  const words = pageWords(page);
  assert.ok(words.length > 100 && words.some((w) => w.includes('<b>')), 'the page\'s words, with the sentences in bold');
  assert.deepEqual(missing(words), []);
});

test('every word the window and the menu show, and every answer to other apps, has Spanish', () => {
  const words = scriptWords(app), menu = scriptWords(main);
  assert.ok(words.length > 150 && menu.length > 20);
  assert.deepEqual(missing(words), []);
  assert.deepEqual(missing(menu), []);
});

test('sounds, scales, the tone pad\'s names and its controller choices have Spanish', () => {
  const words = [...Object.values(SYNTH_PRESETS), ...Object.keys(SCALES), ...Object.values(XY_PROFILES).map((p) => p.name)];
  words.push(...[...app.matchAll(/xyName[XY]: '([^']+)'/g)].map((m) => m[1]));
  assert.ok(words.length >= 14);
  assert.deepEqual(missing(words), []);
});

test('Spanish keeps every placeholder and tag', () => {
  for (const [en, spanish] of Object.entries(es)) {
    const same = (re) => assert.deepEqual((spanish.match(re) || []).sort(), (en.match(re) || []).sort(), en);
    same(/\{\w+\}/g);
    same(/<\/?\w+[^>]*>/g);
  }
});

test('the menu reads the window\'s own table, and the window says its language', () => {
  assert.ok(main.includes(`'${TABLE}'`));
  assert.match(app, /document\.documentElement\.lang = lang/);
  assert.match(app, /language: lang/, 'reported in prefs.applied');
});
