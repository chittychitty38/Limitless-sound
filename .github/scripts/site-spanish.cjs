// The Spanish page (docs/es/index.html) keeps up with the English one: no English left on it, and
// the same styles. site-a11y.cjs runs both on every page it checks.
//
// No English left: site-a11y.cjs reads every word a reader or a screen reader meets on each page,
// as it's shown (text, the title, meta descriptions, aria-label, alt, title), with the release links
// and the proof filled in or not. A word on the Spanish page is English when the English page uses it,
// or it's one of the common English words below, unless it's a name or a word Spanish uses too
// (KEEP). Words marked lang="en" (an English command, the proof's English details) and code don't
// count, and neither do numbers. The English page's proof results are data, not its words: they
// name languages and codes ("Español", "es") that mustn't count as English.
//
// Same styles: the two <style> blocks must match, apart from the Spanish page's fonts being one
// folder up, so the brand can't drift between them.

// Names, removed before a text is split into words (longest first, so "Limitless Sound Foundation"
// goes before "Limitless Sound").
const NAMES = [
  'Limitless Sound Foundation', 'Limitless Access Standard', 'Limitless Sound', 'Limitless Voice',
  'Limitless One-Hand', 'Limitless Zoom', 'Limitless Color', 'Limitless Control', 'Limitless Link',
  'Access Standard', 'GazeStage', 'One-Hand', 'Logic Pro', 'Pro Tools', 'Ableton Live', 'GarageBand', 'REAPER', 'FL Studio',
  'Xbox Adaptive Controller', 'Line 6 Helix', 'Apple Silicon', 'Apple', 'macOS', 'Mac', 'Windows',
  'SmartScreen', 'GitHub', 'Intel', 'MIDI', 'PDF', 'DAW', 'Common Voice', 'FLEURS', 'Jason Barnes',
  'Conyers', 'Georgia', 'Foundation', 'Microsoft', 'plug-ins', 'plug-in',
].sort((a, b) => b.length - a.length);

// Words Spanish uses too: loanwords musicians and the suite's Spanish use ("apps", "solo", "mute"),
// and Spanish words spelled like English ones ("no", "plan", "control").
const KEEP = new Set([
  'app', 'apps', 'suite', 'software', 'webcam', 'gamepad', 'sidechain', 'reamping', 'pad', 'xy', 'bus',
  'solo', 'mute', 'zoom', 'ok', 'id', 'kit', 'internet', 'chip', 'pc', 'mb',
  'no', 'plan', 'control', 'color', 'real', 'general', 'final', 'normal', 'total', 'error', 'pedal',
  'describe', 'legal',
]);

// Common English words that aren't Spanish words, for English the English page doesn't use.
const COMMON = new Set(`the and of to in is are was were be been being you your yours it its this that
these those with for from by on at as or not but if then than so all any every each more most can
will would should could may might must have had do does did done get gets got make makes made what
which who whom whose when where why how here there about into over under after before again also
just only our we us they them their she his her him my mine an off out up down new old one two three
please click open download downloads install installed settings computer music musician musicians
voice hand hands eyes head switch works work page loading results passed failed ready answered
command commands screenshot night yes stop play record read help home back top skip main content
language english spanish sections proof free offline online window`.split(/\s+/));
for (const w of KEEP) COMMON.delete(w);

// In the page: every text a reader or a screen reader meets, in the page's own language, with where
// it is. Runs in the browser.
function pageTexts() {
  const own = document.documentElement.lang.slice(0, 2);
  const foreign = (el) => !el || el.closest('script, style, code, kbd, samp, pre, [translate="no"]')
    || (el.closest('[lang]')?.lang || own).slice(0, 2) !== own;
  const where = (el) => (el.closest('#proof-runs') ? 'proof ' : '') + el.tagName.toLowerCase() + (el.id ? '#' + el.id : '')
    + (typeof el.className === 'string' && el.className ? '.' + el.className.split(' ')[0] : '');
  const out = [['title', document.title]];
  for (const m of document.querySelectorAll('meta[name="description"], meta[property="og:title"], meta[property="og:description"]'))
    out.push([`meta ${m.getAttribute('name') || m.getAttribute('property')}`, m.content]);
  const walk = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walk.nextNode(); n; n = walk.nextNode())
    if (n.nodeValue.trim() && !foreign(n.parentElement)) out.push([where(n.parentElement), n.nodeValue.trim()]);
  for (const attr of ['aria-label', 'alt', 'title', 'placeholder', 'aria-description'])
    for (const el of document.querySelectorAll(`[${attr}]`))
      if (el.getAttribute(attr).trim() && !foreign(el)) out.push([`${where(el)} ${attr}`, el.getAttribute(attr).trim()]);
  return out;
}

// The words of a text, lower case, without names, numbers or single letters.
const names = new RegExp(`(?<!\\p{L})(?:${NAMES.map((n) => n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})(?!\\p{L})`, 'giu');
function words(text) {
  return text.replace(names, ' ').toLowerCase().split(/[^\p{L}\p{M}]+/u).filter((w) => w.length > 1);
}

// English words left in the Spanish page's texts, given the English page's: ["where: «text»", ...].
function englishLeft(spanishTexts, englishTexts) {
  const english = new Set(COMMON);
  for (const [where, text] of englishTexts) if (!where.startsWith('proof ')) for (const w of words(text)) english.add(w);
  for (const w of KEEP) english.delete(w);
  const found = [];
  for (const [where, text] of spanishTexts) {
    const bad = [...new Set(words(text).filter((w) => english.has(w)))];
    if (bad.length) found.push(`${bad.join(', ')} in ${where}: «${text.replace(/\s+/g, ' ').slice(0, 90)}»`);
  }
  return found;
}

// Where the two pages' <style> blocks differ, apart from the Spanish fonts' path, or "".
function stylesDiffer(englishHtml, spanishHtml) {
  const style = (html) => (html.match(/<style>[\s\S]*?<\/style>/) || [''])[0].split('\n');
  const en = style(englishHtml);
  const es = style(spanishHtml.replaceAll('url("../fonts/', 'url("fonts/'));
  for (let i = 0; i < Math.max(en.length, es.length); i++)
    if (en[i] !== es[i]) return `line ${i + 1} of <style>: English «${(en[i] ?? '').trim()}», Spanish «${(es[i] ?? '').trim()}»`;
  return '';
}

module.exports = { pageTexts, englishLeft, stylesDiffer, words };
