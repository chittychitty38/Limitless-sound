// Builds the website for Netlify (netlify.toml): docs/ as it is, plus what a static page can't
// know by itself. Netlify runs it for every push to main and every pull request:
//   node .github/scripts/netlify-build.mjs
// - releases.json: each app's newest release and the suite's, so a visit needn't ask GitHub's
//   API (60 questions an hour per address, and 100 releases of JSON for each).
// - The addresses in each page's head (canonical, languages, link previews) are this site's own:
//   Netlify sets URL to it. Run elsewhere, they stay GitHub Pages'.
// - robots.txt and sitemap.xml.
//
// With --standalone, the result needs nothing else to run: drop the folder (or its zip) on
// https://app.netlify.com/drop, no repository connected. The latest proof and its badge are copied
// in instead of fetched live, and netlify.toml's short links and headers are written as _redirects
// and _headers, which a dropped folder is served by. Give it the address it will have:
//   URL=https://limitlesssound.netlify.app node .github/scripts/netlify-build.mjs --standalone
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync, readdirSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';

const OUT = '_site';
const REPO = 'chittychitty38/Limitless-sound';
const PAGES = 'https://chittychitty38.github.io/Limitless-sound/';
const SITE = (process.env.URL || PAGES).replace(/\/*$/, '/');
const APPS = ['voice', 'one-hand', 'zoom', 'color', 'control', 'gazestage'];
const STANDALONE = process.argv.includes('--standalone');

rmSync(OUT, { recursive: true, force: true });
cpSync('docs', OUT, { recursive: true, filter: (src) => !src.endsWith('.md') });

// Every release tag, newest first: GitHub's releases, or every tag when the API won't answer
// (git asks no API, so it has no hourly limit).
async function tags() {
  try {
    const headers = { 'User-Agent': 'limitless-sound-site-build' };
    if (process.env.GITHUB_TOKEN) headers.Authorization = `Bearer ${process.env.GITHUB_TOKEN}`;
    const res = await fetch(`https://api.github.com/repos/${REPO}/releases?per_page=100`, { headers });
    if (res.ok) return (await res.json()).filter((r) => !r.draft && !r.prerelease).map((r) => r.tag_name);
    console.log(`GitHub's API answered ${res.status}; reading the tags with git instead`);
  } catch (e) {
    console.log(`GitHub's API didn't answer (${e.message}); reading the tags with git instead`);
  }
  const out = execFileSync('git', ['ls-remote', '--tags', '--refs', `https://github.com/${REPO}.git`], { encoding: 'utf8' });
  return out.split('\n').map((line) => line.split('refs/tags/')[1]).filter(Boolean);
}

const newer = (a, b) => {
  const x = a.split('.').map(Number), y = b.split('.').map(Number);
  for (let i = 0; i < 3; i++) if ((x[i] || 0) !== (y[i] || 0)) return (x[i] || 0) > (y[i] || 0);
  return false;
};
const newest = (all, prefix) => all
  .filter((t) => t.startsWith(prefix) && /^\d+\.\d+\.\d+$/.test(t.slice(prefix.length)))
  .map((t) => t.slice(prefix.length))
  .reduce((best, v) => (!best || newer(v, best) ? v : best), '');

try {
  const all = await tags();
  const releases = { suite: newest(all, 'v'), apps: {} };
  for (const app of APPS) {
    const v = newest(all, `${app}-v`);
    if (v) releases.apps[app] = { version: v, url: `https://github.com/${REPO}/releases/tag/${app}-v${v}` };
  }
  if (!releases.suite || !Object.keys(releases.apps).length) throw new Error('no releases found');
  writeFileSync(join(OUT, 'releases.json'), JSON.stringify(releases, null, 1) + '\n');
  console.log(`releases.json: suite ${releases.suite}; ${APPS.map((a) => `${a} ${releases.apps[a]?.version ?? '?'}`).join(', ')}`);
} catch (e) {
  // The page then asks GitHub itself, and keeps the versions written in it if that fails too.
  console.log(`No releases.json (${e.message})`);
}

// Each page's head names this site.
const pages = ['index.html', 'es/index.html', '404.html'];
for (const page of pages) {
  const file = join(OUT, page);
  const html = readFileSync(file, 'utf8');
  const end = html.indexOf('</head>');
  writeFileSync(file, html.slice(0, end).replaceAll(PAGES, SITE) + html.slice(end));
}

writeFileSync(join(OUT, 'robots.txt'), `User-agent: *\nAllow: /\nSitemap: ${SITE}sitemap.xml\n`);
const alt = `<xhtml:link rel="alternate" hreflang="en" href="${SITE}"/><xhtml:link rel="alternate" hreflang="es" href="${SITE}es/"/>`;
writeFileSync(join(OUT, 'sitemap.xml'), `<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9" xmlns:xhtml="http://www.w3.org/1999/xhtml">
<url><loc>${SITE}</loc>${alt}</url>
<url><loc>${SITE}es/</loc>${alt}</url>
</urlset>
`);
if (STANDALONE) {
  // The proof as it was last published, from the proof-results branch.
  const proof = async (name) => {
    try {
      const res = await fetch(`https://raw.githubusercontent.com/${REPO}/proof-results/${name}`);
      if (res.ok) return Buffer.from(await res.arrayBuffer());
    } catch { /* try git */ }
    try {
      execFileSync('git', ['fetch', '-q', '--depth=1', 'origin', 'proof-results']);
      return execFileSync('git', ['show', `FETCH_HEAD:${name}`]);
    } catch { return null; }
  };
  mkdirSync(join(OUT, 'proof'), { recursive: true });
  for (const name of ['latest.json', 'badge.svg']) {
    const body = await proof(name);
    if (body) writeFileSync(join(OUT, 'proof', name), body);
    console.log(`proof/${name}: ${body ? `${body.length} bytes` : 'not found, the page says no results yet'}`);
  }
  // netlify.toml's rules as the files a dropped folder is served by. Its proxy to the live proof
  // stays out: the proof is copied in above.
  const toml = readFileSync('netlify.toml', 'utf8');
  const field = (block, key) => (block.match(new RegExp(`^\\s*${key} = "([^"]*)"`, 'm')) || [])[1];
  const redirects = toml.split('[[redirects]]').slice(1)
    .map((b) => ({ from: field(b, 'from'), to: field(b, 'to'), status: (b.match(/status = (\d+)/) || [])[1] }))
    .filter((r) => r.status !== '200');
  writeFileSync(join(OUT, '_redirects'), redirects.map((r) => `${r.from}  ${r.to}  ${r.status}`).join('\n') + '\n');
  const headers = toml.split('[[headers]]').slice(1).map((b) => {
    const values = b.split('[headers.values]')[1].trim().split('\n').map((l) => l.match(/^\s*([\w-]+) = "([^"]*)"/)).filter(Boolean);
    return `${field(b, 'for')}\n${values.map((m) => `  ${m[1]}: ${m[2]}`).join('\n')}`;
  });
  writeFileSync(join(OUT, '_headers'), headers.join('\n') + '\n');
  console.log(`_redirects: ${redirects.length} short links; _headers: ${headers.length} rules`);
}

console.log(`Built ${OUT}/ for ${SITE}: ${readdirSync(OUT).length} entries`);
