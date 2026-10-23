// Limitless Color in the suite's language: every word in its window, its menus and its answers
// to other apps has Spanish, and the Spanish keeps every placeholder and tag.
// Run with: node --test apps/color/app/test/
// (What color-core says, the assistant included, is checked by cargo test -p color-core.)
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';

const read = (file) => readFileSync(new URL(file, import.meta.url), 'utf8');
const page = read('../ui/index.html');
const TABLE = '<script type="application/json" id="strings-es">';
const es = JSON.parse(page.slice(page.indexOf(TABLE) + TABLE.length, page.indexOf('</script>', page.indexOf(TABLE))));

// Names read the same in every language.
const SAME_EVERYWHERE = new Set(['Limitless Color', 'Claude', 'Logic Pro', 'Pro Tools', 'sk-ant-…', 'Ctrl', 'Alt', 'Fn']);
const missing = (words) => [...new Set(words)].filter((w) => /[A-Za-z]{2}/.test(w) && !(w in es) && !SAME_EVERYWHERE.has(w));

// The page's own words: its title, the text in the body outside scripts and styles, and
// aria-labels, titles and placeholders.
function pageWords(html) {
  const words = [html.match(/<title>([^<]*)<\/title>/)[1]];
  let body = html.slice(html.indexOf('<body'));
  body = body.replace(/<!--[\s\S]*?-->/g, '').replace(/<(script|style|svg)\b[\s\S]*?<\/\1>/g, '');
  for (const m of body.matchAll(/\s(?:aria-label|title|placeholder)="([^"]*)"/g)) words.push(m[1]);
  for (const text of body.replace(/<[^>]*>/g, '\n').split('\n')) {
    const w = text.replace(/&nbsp;/g, ' ').replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>').trim();
    if (w) words.push(w);
  }
  return words;
}

// The strings in the first argument of each call to one of `names`, as in t("…"), en("…"),
// btn(cond ? "…" : "…", run). Only text that reads like words: a space, a capital or an ellipsis
// ("mac" in t(platform==="mac"?…) is code).
function calledWith(src, names) {
  const out = [];
  const start = new RegExp(`\\b(?:${names.join('|')})\\(`, 'g');
  for (const m of src.matchAll(start)) {
    let i = m.index + m[0].length, depth = 0, quote = null, arg = '';
    for (; i < src.length; i++) {
      const c = src[i];
      if (quote) {
        arg += c;
        if (c === '\\') { arg += src[++i]; continue; }
        if (c === quote) quote = null;
        continue;
      }
      if (c === '"' || c === "'" || c === '`') { quote = c; arg += c; continue; }
      if ('([{'.includes(c)) depth++;
      if (')]}'.includes(c)) { if (depth === 0) break; depth--; }
      if (c === ',' && depth === 0) break;
      arg += c;
    }
    for (const s of arg.matchAll(/"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'/g)) {
      const text = (s[1] ?? s[2]).replace(/\\(.)/g, '$1');
      if (/[A-Za-z]{2}/.test(text) && /\s|^[A-Z]|…/.test(text)) out.push(text);
    }
  }
  return out;
}

const script = page.slice(page.indexOf('<script>'), page.lastIndexOf('</script>'));
const rustDir = new URL('../src-tauri/src/', import.meta.url);
const rust = readdirSync(rustDir, { recursive: true }).filter((f) => f.endsWith('.rs')).map((f) => read(`../src-tauri/src/${f}`)).join('\n');

test('every word in the window has Spanish', () => {
  const words = pageWords(page);
  assert.ok(words.length > 60, 'the page\'s words');
  assert.deepEqual(missing(words), []);
});

test('every word the window\'s script shows has Spanish', () => {
  const words = calledWith(script, ['t', 'en', 'btn', 'p']);
  assert.ok(words.length > 200, `found ${words.length}`);
  assert.ok(words.includes('Welcome to Limitless Color') && words.includes('Red-green, green-weak') && words.includes('Kick'));
  assert.deepEqual(missing(words), []);
});

test('the menus, the window\'s title and every message from the app have Spanish', () => {
  const words = calledWith(rust, ['t', 'tf']);
  assert.ok(words.length > 40, `found ${words.length}`);
  for (const w of ['Screen colors on', 'Open Color Tuner…', 'Quit {name}', 'Limitless Color Tuner', 'Exact match to the tuner.']) {
    assert.ok(words.includes(w), w);
  }
  assert.deepEqual(missing(words), []);
});

test('Spanish keeps every placeholder and tag, and is Spanish', () => {
  // Words that are the same in both languages.
  const SAME = new Set(['Solo', 'Original', 'Zoom', 'Faders']);
  for (const [en, spanish] of Object.entries(es)) {
    const same = (re) => assert.deepEqual((spanish.match(re) || []).sort(), (en.match(re) || []).sort(), en);
    same(/\{\w+\}/g);
    same(/<\/?\w+[^>]*>/g);
    assert.ok(spanish.trim() && (spanish !== en || SAME.has(en)), `no Spanish for ${en}`);
    // Spanish quotes are «», as everywhere in the suite.
    assert.ok(!/["“”]/.test(spanish) || /"/.test(en), `quotes in ${spanish}`);
  }
});

test('the window says its language, and follows the app\'s', () => {
  assert.match(script, /document\.documentElement\.lang=lang/);
  assert.match(script, /if\(p\.language&&setLanguage\(p\.language\)\)relabel\(\)/, 'window-prefs carries the language');
  assert.match(rust, /WindowPrefs \{ language: language\(inner\)/, 'the app sends it with the window prefs and prefs.applied');
});
