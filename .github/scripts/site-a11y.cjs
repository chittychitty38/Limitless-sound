// Checks the website (docs/index.html) against WCAG 2.2 A and AA with axe-core, in light and
// dark, desktop and phone width, with GitHub's API unreachable (the page's own fallbacks).
// Any problem fails. The site is the front door for musicians with disabilities.
//   node .github/scripts/site-a11y.cjs
const { chromium } = require('playwright');
const { readFileSync } = require('fs');
const { join } = require('path');

const axe = readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const page = 'file://' + join(__dirname, '..', '..', 'docs', 'index.html');

(async () => {
  const browser = await chromium.launch();
  let problems = 0;
  for (const [scheme, width] of [['light', 1280], ['dark', 1280], ['light', 390], ['dark', 390]]) {
    const ctx = await browser.newContext({ colorScheme: scheme, viewport: { width, height: 900 } });
    const p = await ctx.newPage();
    await p.route('https://api.github.com/**', (r) => r.fulfill({ status: 503, body: '' }));
    await p.goto(page);
    await p.waitForTimeout(500);
    await p.addScriptTag({ content: axe });
    const r = await p.evaluate(() => axe.run(document, { runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'] }));
    console.log(`${scheme}, ${width} px: ${r.violations.length ? r.violations.length + ' problem(s)' : 'no problems'}, ${r.passes.length} rules passed`);
    for (const v of r.violations) {
      problems++;
      console.log(`  [${v.impact}] ${v.id}: ${v.help}`);
      for (const n of v.nodes) console.log(`    ${n.target.join(' ')}: ${(n.failureSummary || '').split('\n').slice(1).join(' ').trim()}`);
    }
    await ctx.close();
  }
  await browser.close();
  process.exit(problems ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(1); });
