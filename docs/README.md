# Limitless Sound website

The public page at https://chittychitty38.github.io/Limitless-sound/ is `index.html` in this
folder, served by GitHub Pages from the `gh-pages` branch, a copy of this folder. The same page in
Spanish is `es/index.html` (https://chittychitty38.github.io/Limitless-sound/es/): copy the `es`
folder to `gh-pages` too.

Change both pages together. Their `<style>` blocks must stay the same (the Spanish one's fonts are
one folder up), and the Spanish page must have no English left, apart from names, code and words
marked `lang="en"`. The Website workflow checks both, with axe-core, in light and dark, at desktop
and phone width: `node .github/scripts/site-a11y.cjs` (needs `playwright` and `axe-core`; see
`.github/workflows/site.yml`). Its Spanish words follow Limitless Sound's own page and the
installers: neutral Spanish with tú, "equipo" for computer, "pulsador" for a switch, "apps".
It is plain HTML with no build step, in the Limitless Sound Foundation branding (heart logo in `logo.png`, original in `las-logo-original.jpeg`). Fonts: Bricolage Grotesque, Instrument Serif, JetBrains Mono and Atkinson Hyperlegible Next, all self-hosted (SIL OFL, see `fonts/OFL.txt`).
