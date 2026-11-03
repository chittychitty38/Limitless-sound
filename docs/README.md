# Limitless Sound website

The public site is this folder: `index.html` in English and `es/index.html` in Spanish, with
`site.js` doing what both do once loaded (the input strip, the download for this computer, each
app's newest release, the proof's scoreboard), each page giving it its own words in `window.LS`.

**Netlify** serves it, built by `.github/scripts/netlify-build.mjs` for every push to `main`, with
a preview for every pull request. `netlify.toml` at the repository's root holds everything:
- the build adds `releases.json` (each app's newest release, so a visit needn't ask GitHub's API),
  points each page's canonical, language and link-preview addresses at the site, and writes
  `robots.txt` and `sitemap.xml`;
- `/proof/latest.json` comes live from the `proof-results` branch;
- short links: `/apple-silicon`, `/intel-mac` and `/windows` download the suite, and `/download`,
  `/proof`, `/roadmap`, `/plan`, `/standard`, `/feedback` and `/code` go where they say;
- security headers (only the site's own scripts, styles, fonts and images) and long caching for
  fonts and images;
- `404.html`, in English and Spanish.

To connect it, once: in Netlify, **Add new site › Import an existing project › GitHub ›
Limitless-sound**, branch `main`. Netlify reads the rest from `netlify.toml`. Then **Site
configuration › Change site name** for the address. For each release to reach the page within
minutes, add a build hook (**Site configuration › Build & deploy › Build hooks**, branch `main`)
as the repository secret `NETLIFY_BUILD_HOOK`: `.github/workflows/site-refresh.yml` calls it after
each build on `main`.

GitHub Pages still serves a copy at https://chittychitty38.github.io/Limitless-sound/ from the
`gh-pages` branch, which is copied from this folder by hand. There the page asks GitHub's API for
the releases, and the proof is the copy at the site's root.

Change both pages together. Their `<style>` blocks must stay the same (the Spanish one's fonts are
one folder up), and the Spanish page must have no English left, apart from names, code and words
marked `lang="en"`. The Website workflow checks both, with axe-core, in light and dark, at desktop
and phone width, with the text twice as large too, then builds the site as Netlify does:
`node .github/scripts/site-a11y.cjs` (needs `playwright` and `axe-core`; see
`.github/workflows/site.yml`). Its Spanish words follow Limitless Sound's own page and the
installers: neutral Spanish with tú, "equipo" for computer, "pulsador" for a switch, "apps".

It is plain HTML with no build step of its own, in the Limitless Sound Foundation branding (heart
logo in `logo.png`, with `logo-92.webp` and `logo-520.webp` for the page; original in
`las-logo-original.jpeg`; link-preview cards `og.jpg` and `og-es.jpg`). Fonts: Bricolage
Grotesque, Instrument Serif, JetBrains Mono and Atkinson Hyperlegible Next, all self-hosted (SIL
OFL, see `fonts/OFL.txt`), the four the first screen needs preloaded.
