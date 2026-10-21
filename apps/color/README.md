# Limitless Color

Limitless Color recolors your whole screen so colorblind musicians can see Logic Pro, Pro Tools, plugins and everything else the way they need to.

You describe what looks wrong, for example "what's supposed to be red looks like a weird green or yellow". The assistant changes the colors and asks what you see now, and you keep going until it looks right. You can also move the faders yourself, or pin a control like Solo, Mute or the meters to an exact color.

## Runs on

| | Versions | How the screen is recolored |
|---|---|---|
| **Mac** | macOS 13 Ventura or newer, Apple Silicon and Intel | Captures the screen and redraws it through your profile on the graphics chip. Exact match to the tuner, about one frame of delay. The mouse pointer is never delayed. |
| **Windows** | Windows 10 and 11, 64-bit | Uses Windows' own full-screen color filter. No delay and almost no extra work for the computer. It closely matches simple corrections. Pinned colors and big hue moves are approximate (the app says how close the match is). |

**Microphone:** any mic your computer already uses, whether built in, USB or a headset. Press **Talk** and the app starts your computer's own dictation, so there's nothing extra to set up.

**Claude:** optional. Without it, a built-in helper understands the common ways people describe red-green and blue-yellow problems, works offline and costs nothing. With an Anthropic API key, Claude gives smarter answers. The key is kept in the Mac Keychain or Windows Credential Manager.

## Install

Download the latest installer from the repository's **Releases** page (tags named `color-v…`), or from the newest **Limitless Color** run under **Actions**. Mac has two downloads: **apple-silicon** for M1 and newer, **intel** for older Macs.

**Mac:** open the `.dmg` and drag Limitless Color to Applications. The app isn't signed with an Apple developer certificate yet, so the first time:

1. Open Limitless Color. macOS will say it can't be opened.
2. Go to **System Settings › Privacy & Security**, scroll down, and click **Open Anyway**.
3. When you switch screen colors on, macOS asks for **Screen Recording** permission. Turn it on for Limitless Color, then switch the colors off and on again. The app only looks at the screen to recolor it. Nothing is recorded or sent anywhere.

macOS 15 may ask again about once a month whether Limitless Color can keep recording the screen. Choose **Allow**.

**Windows:** run the installer. Windows may show "Windows protected your PC". Click **More info**, then **Run anyway**. No administrator rights are needed.

## Use

- **Screen colors: On/Off.** Applies your profile to the whole screen. Closing the tuner window keeps the colors on. Use the menu bar (Mac) or tray (Windows) icon to switch off or quit.
- **Hold to compare.** Shows the original colors while you hold it. It works like bypass on a plugin.
- **Command + Option + C** (Mac) or **Ctrl + Alt + C** (Windows) switches the colors from any app.
- **Quick eye check.** Six pairs of circles, about a minute. It works out which kind of color vision difference you have and sets a starting correction.
- **Use a screenshot of my session.** Tunes against a picture of your real session instead of the sample.
- **Save .cube profile.** Saves your profile to Documents › Limitless Color as a standard color lookup file, to back up or share.

## How it's built

```
crates/color-core     Shared color math in Rust: color vision simulation (Machado 2009),
                      correction, pinned colors, 3D lookup tables, the Windows matrix fit,
                      the assistant's prompt and the offline helper. Unit tested.
app/src-tauri         The desktop app (Tauri 2): tuner window, tray menu, shortcut,
                      start at login, screen filters, Claude calls.
app/macos-overlay     The Mac screen filter helper (Swift: ScreenCaptureKit + Metal).
app/ui                The tuner window (one HTML file, no build step).
tools/build_ui.py     Builds app/ui/index.html from the browser Color Tuner page.
../../.github/workflows/color.yml
                      Tests, builds and smoke-tests the Mac .dmg (Apple Silicon and Intel)
                      and the Windows installer; color-v* tags publish a release.
```

The tuner preview in the window (JavaScript) and the screen filter (Rust) run the same math. A test in `color-core` checks that they give identical colors.

### Build it yourself

You need Rust and Node.js. On a Mac you also need the Xcode command line tools.

```sh
cargo test -p color-core

# Mac: build the screen filter helper first
mkdir -p app/src-tauri/binaries
swiftc -O -target arm64-apple-macos13 app/macos-overlay/main.swift \
  -o app/src-tauri/binaries/limitless-overlay-aarch64-apple-darwin

cd app && npx @tauri-apps/cli@2.9.4 dev      # run it
cd app && npx @tauri-apps/cli@2.9.4 build    # make an installer
```

## Known limits and next steps

- **Windows accuracy.** The built-in filter is a single color matrix. A future "accurate mode" can capture the screen and redraw it, as the Mac version does, for exact pinned colors.
- **Signing.** An Apple Developer ID and a Windows code-signing certificate would remove the first-launch warnings. Until the Mac app is signed, macOS may ask for Screen Recording permission again after each update.
- **Not tested on real hardware yet.** The color engine is tested. The Mac helper and the Windows filter compile in CI but need a first run on a real Mac and PC.
