// Checks the website against WCAG 2.2 A and AA with axe-core: the English page (docs/index.html)
// and the Spanish one (docs/es/index.html), each in light and dark, at desktop and phone width,
// served the way GitHub Pages serves them. Each runs twice: with GitHub's API and last night's
// proof unreachable (the page's own fallbacks), and with the answers in site-sample.json, so the
// newest-release links and the proof results are checked as they're shown. In every run, the page
// must not scroll sideways (WCAG 1.4.10, down to 320 px), and its link to the other language must be
// there, reachable by keyboard and right. The Spanish page must have no English left and the same
// styles as the English one (site-spanish.cjs).
// Any problem fails. The site is the front door for musicians with disabilities.
//   node .github/scripts/site-a11y.cjs
const { chromium } = require('playwright');
const { readFileSync, statSync } = require('fs');
const { join, extname, resolve, sep } = require('path');
const http = require('http');
const spanish = require('./site-spanish.cjs');

const axe = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const docs = resolve(__dirname, '..', '..', 'docs');
const sample = JSON.parse(readFileSync(join(__dirname, 'site-sample.json'), 'utf8'));
const pages = [
  { lang: 'en', path: '', other: 'es/', otherLang: 'es', otherName: 'Español' },
  { lang: 'es', path: 'es/', other: '', otherLang: 'en', otherName: 'English' },
];
const modes = [['light', 1280], ['dark', 1280], ['light', 390], ['dark', 390], ['dark', 320]];
const types = { '.html': 'text/html; charset=utf-8', '.png': 'image/png', '.jpeg': 'image/jpeg', '.woff2': 'font/woff2', '.pdf': 'application/pdf' };

// docs/ as GitHub Pages serves it: a folder's index.html at its own address.
function serve() {
  const server = http.createServer((req, res) => {
    let file = join(docs, decodeURIComponent(new URL(req.url, 'http://localhost').pathname));
    if (file.endsWith(sep)) file = join(file, 'index.html');
    try {
      if (!file.startsWith(docs + sep) || !statSync(file).isFile()) throw new Error();
      res.writeHead(200, { 'Content-Type': types[extname(file)] || 'application/octet-stream' });
      res.end(readFileSync(file));
    } catch { res.writeHead(404); res.end(); }
  });
  return new Promise((ok) => server.listen(0, '127.0.0.1', () => ok(server)));
}

(async () => {
  const server = await serve();
  const base = `http://127.0.0.1:${server.address().port}/`;
  const browser = await chromium.launch();
  let problems = 0;
  const fail = (msg) => { problems++; console.log(`  ${msg}`); };

  const styles = spanish.stylesDiffer(readFileSync(join(docs, 'index.html'), 'utf8'), readFileSync(join(docs, 'es', 'index.html'), 'utf8'));
  console.log(`es: the same styles as en: ${styles ? 'no' : 'yes'}`);
  if (styles) fail(`the Spanish page's styles differ from the English page's, at ${styles}`);

  for (const online of [false, true]) {
    let englishTexts = [];
    for (const pg of pages) {
      for (const [scheme, width] of modes) {
        const ctx = await browser.newContext({ colorScheme: scheme, viewport: { width, height: 900 } });
        const p = await ctx.newPage();
        await p.route('https://api.github.com/**', (r) => online
          ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sample.releases) })
          : r.fulfill({ status: 503, body: '' }));
        // Last night's proof is published at the site's root (gh-pages proof/latest.json), and only there.
        await p.route((u) => u.pathname === '/proof/latest.json', (r) => online
          ? r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(sample.proof) })
          : r.fulfill({ status: 404, body: '' }));
        await p.goto(base + pg.path);
        await p.waitForTimeout(500);
        await p.addScriptTag({ content: axe });
        const r = await p.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }));
        const before = problems;
        console.log(`${pg.lang}, ${online ? 'GitHub reachable' : 'GitHub unreachable'}, ${scheme}, ${width} px: ${r.passes.length} rules passed`);
        for (const v of r.violations) {
          fail(`[${v.impact}] ${v.id}: ${v.help}`);
          for (const n of v.nodes) console.log(`    ${n.target.join(' ')}: ${(n.failureSummary || '').split('\n').slice(1).join(' ').trim()}`);
        }

        const page = await p.evaluate(() => ({
          lang: document.documentElement.lang,
          sideways: document.documentElement.scrollWidth - document.documentElement.clientWidth,
          alternates: [...document.querySelectorAll('link[rel="alternate"][hreflang]')].map((l) => l.hreflang).sort().join(' '),
          langLinks: [...document.querySelectorAll('a[hreflang]')].filter((a) => a.getClientRects().length && /^(English|Español)$/.test(a.textContent.trim()))
            .map((a) => ({ text: a.textContent.trim(), lang: a.lang, hreflang: a.hreflang, href: a.href })),
          links: [...document.querySelectorAll('a[data-app]')].map((a) => [a.dataset.app, a.href, a.querySelector('.ver')?.textContent]),
          suite: [...document.querySelectorAll('[data-suite]')].map((s) => s.textContent),
          runs: document.querySelectorAll('#proof-runs .proofrun').length,
          proofLink: document.getElementById('proof-run')?.href,
        }));
        if (page.lang !== pg.lang) fail(`<html lang="${page.lang}">, not "${pg.lang}"`);
        if (page.sideways > 0) fail(`scrolls sideways by ${page.sideways} px`);
        if (page.alternates !== 'en es x-default') fail(`<link rel="alternate" hreflang>: ${page.alternates || 'none'}, not en, es and x-default`);
        const want = base + pg.other;
        if (page.langLinks.length !== 1) fail(`${page.langLinks.length} visible links to the other language, not 1`);
        for (const l of page.langLinks) {
          if (l.text !== pg.otherName || l.lang !== pg.otherLang || l.hreflang !== pg.otherLang || l.href !== want)
            fail(`language link ${JSON.stringify(l)}, not "${pg.otherName}" with lang and hreflang "${pg.otherLang}" to ${want}`);
        }
        // Keyboard: Tab from the top reaches the language link within the first few stops.
        let reached = false;
        for (let i = 0; i < 12 && !reached; i++) {
          await p.keyboard.press('Tab');
          reached = await p.evaluate((name) => document.activeElement?.textContent.trim() === name, pg.otherName);
        }
        if (!reached) fail(`Tab doesn't reach "${pg.otherName}" in 12 presses`);

        // Every word is in the page's language (the text doesn't change with the width or the colors).
        if (scheme === modes[0][0] && width === modes[0][1]) {
          const texts = await p.evaluate(spanish.pageTexts);
          if (pg.lang === 'en') englishTexts = texts;
          else for (const left of spanish.englishLeft(texts, englishTexts)) fail(`English on the Spanish page: ${left}`);
        }

        if (online) {
          for (const [app, href, ver] of page.links) {
            const rel = sample.releases.find((x) => !x.draft && x.tag_name.startsWith(app + '-v'));
            if (href !== rel.html_url || ver !== rel.tag_name.slice(app.length + 2)) fail(`${app}'s Download link is ${href} (${ver}), not the newest release`);
          }
          if (page.suite.some((v) => v !== '0.2.6')) fail(`the suite's version reads ${page.suite.join(', ')}, not 0.2.6`);
          if (page.runs !== sample.proof.runs.length) fail(`${page.runs} proof runs shown, not ${sample.proof.runs.length}`);
          if (page.proofLink !== sample.proof.run) fail(`"every run" links to ${page.proofLink}, not ${sample.proof.run}`);
        }
        if (problems === before) console.log('  no problems');
        await ctx.close();
      }
    }
  }
  await browser.close();
  server.close();
  console.log(problems ? `${problems} problem(s)` : 'No problems.');
  process.exit(problems ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
