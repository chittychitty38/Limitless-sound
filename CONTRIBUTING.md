# Working in this repository

## Folders

| App | Folder | Workflow | Release tag |
|---|---|---|---|
| Limitless Voice | `apps/voice/` | `.github/workflows/voice.yml` | `voice-v0.2.0` |
| Limitless One-Hand | `apps/one-hand/` | `.github/workflows/one-hand.yml` | `one-hand-v0.1.0` |
| Limitless Zoom | `apps/zoom/` | `.github/workflows/zoom.yml` | `zoom-v0.1.0` |
| Limitless Color | `apps/color/` | `.github/workflows/color.yml` | `color-v0.1.0` |
| Limitless Control | `apps/control/` | `.github/workflows/control.yml` | `control-v0.1.0` |
| GazeStage | `apps/gazestage/` | `.github/workflows/gazestage.yml` | `gazestage-v0.2.0` |
| Hub and clients | `shared/` | `.github/workflows/shared.yml` | `hub-v0.1.0` |

Each app folder is self-contained: its own requirements / package.json / Cargo workspace,
tests and packaging, exactly as when it was its own repository. There is no root Cargo
workspace or root package.json.

## CI conventions

Each app brings one workflow file, `.github/workflows/<folder>.yml`:

```yaml
name: <App name>
on:
  push:
    branches: [main]
    tags: ["<folder>-v*"]
    paths: ["apps/<folder>/**", ".github/workflows/<folder>.yml"]
  pull_request:
    paths: ["apps/<folder>/**", ".github/workflows/<folder>.yml"]
  workflow_dispatch:
defaults:
  run:
    working-directory: apps/<folder>
```

- `working-directory` covers `run:` steps only. Paths in `uses:` steps (`upload-artifact`,
  `action-gh-release`, `actions/setup-*` cache paths) are relative to the repository root,
  so write them as `apps/<folder>/dist/...`.
- Tag pushes ignore `paths`, so a `<folder>-v*` tag always builds.
- Runners: `macos-15` (Apple Silicon), `macos-15-intel` (Intel), `windows-latest`.
  `macos-13` is retired.
- Artifact names: `<Product>-mac-apple-silicon`, `<Product>-mac-intel`, `<Product>-windows`
  (and `-linux` if built). Installers: `.dmg` on Mac, a setup `.exe` on Windows.
- Releases: attach installers to the release for your `<folder>-v*` tag
  (`softprops/action-gh-release@v2`, `permissions: contents: write`).
- Run the app's tests and a smoke test of the built app before uploading.

## Joining the suite

Apps connect to the Limitless Sound hub with the Limitless Link client in
`shared/clients/` (see `shared/PROTOCOL.md`). Vendor the single client file into your app
(copy it at build time or commit a copy) so each app still builds on its own.

## Pull requests

Branch, push, open a PR against `main`. A PR is merged when its workflow is green.
