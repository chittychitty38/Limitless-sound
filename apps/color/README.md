# Limitless Color

Limitless Color recolors your whole screen so colorblind musicians can see Logic Pro, Pro Tools, plugins and everything else the way they need to.

You describe what looks wrong, for example "what's supposed to be red looks like a weird green or yellow". The assistant changes the colors and asks what you see now, and you keep going until it looks right. You can also move the faders yourself, or pin a control like Solo, Mute or the meters to an exact color.

## Runs on

| | Versions | How the screen is recolored |
|---|---|---|
| **Mac** | macOS 13 Ventura or newer, Apple Silicon and Intel | Captures the screen and redraws it through your profile on the graphics chip. Exact match to the tuner, about one frame of delay. The mouse pointer is never delayed. |
| **Windows** | Windows 10 and 11, 64-bit | Uses Windows' own full-screen color filter. No delay and almost no extra work for the computer. It closely matches simple corrections. Pinned colors and big hue moves are approximate (the app says how close the match is). |

**Microphone:** any mic your computer already uses, whether built in, USB or a headset. Press **Talk** and the app starts your computer's own dictation, so there's nothing extra to set up.

**Claude:** optional. Without it, a built-in helper understands the common ways people describe red-green and blue-yellow problems, in English and Spanish, typed or dictated, works offline and costs nothing. With an Anthropic API key, Claude gives smarter answers. The key is kept in the Mac Keychain or Windows Credential Manager.

**Language:** English or Spanish. Color speaks the language chosen in Limitless Sound, or the computer's own when Limitless Sound isn't running.

## Install

Download the latest installer from the repository's **Releases** page (tags named `color-v…`), or from the newest **Limitless Color** run under **Actions**. Mac has two downloads: `Limitless-Color-mac-apple-silicon.dmg` for M1 and newer, `Limitless-Color-mac-intel.dmg` for older Macs. Windows: `Limitless-Color-Setup-windows.exe`.

**Mac:** open the `.dmg` and drag Limitless Color to Applications. The app isn't signed with an Apple developer certificate yet, so the first time:

1. Open Limitless Color. macOS will say it can't be opened.
2. Go to **System Settings › Privacy & Security**, scroll down, and click **Open Anyway**.
3. The setup guide opens. It walks you through a one-minute eye check, tunes your colors automatically, and then helps you allow **Screen Recording** in System Settings. It notices by itself when you've turned it on. If macOS offers to **Quit & Reopen**, choose it and the guide carries on. The app only looks at the screen to recolor it. Nothing is recorded or sent anywhere.

macOS 15 may ask again about once a month whether Limitless Color can keep recording the screen. Choose **Allow**.

**Windows:** run the installer. Windows may show "Windows protected your PC". Click **More info**, then **Run anyway**. No administrator rights are needed.

## First launch

A short setup guide opens the first time (about two minutes):

1. **Welcome.**
2. **Quick eye check.** Six pairs of circles. Or choose your kind of color vision and how strong it is yourself.
3. **Your colors, tuned.** The app tries thousands of settings for your kind of color vision and picks the one that makes Record and Play, Solo and Mute, the meter stages and the track colors clearly different, while keeping everything else looking natural. You see before and after side by side, and can ask for stronger or gentler.
4. **Screen access** (Mac only).
5. **Switch on.** Try Hold to compare, and choose whether it starts when you log in.

You can run the guide again from the bottom of the window.

## Use

- **Screen colors: On/Off.** Applies your profile to the whole screen. Closing the tuner window keeps the colors on. Use the menu bar (Mac) or tray (Windows) icon to switch off or quit.
- **Hold to compare.** Shows the original colors while you hold it. It works like bypass on a plugin.
- **Command + Option + C** (Mac) or **Ctrl + Alt + C** (Windows) switches the colors from any app.
- **Can you tell them apart?** A live check of the controls you should never mix up, estimated for your kind of color vision. **Make it clear for me** tunes everything automatically, keeping any colors you pinned.
- **Quick eye check.** Six pairs of circles, about a minute. It works out which kind of color vision difference you have and tunes your colors for it.
- **Use a screenshot of my session.** Tunes against a picture of your real session instead of the sample.
- **Save .cube profile.** Saves your profile to Documents › Limitless Color as a standard color lookup file, to back up or share.
- **Limitless Sound settings.** When the Limitless Sound hub runs, the tuner window follows the text size, high contrast and reduced motion you set there, the moment you change them. They change only the window around your colors, never the swatches, the preview or the screen filter. If your computer is set to reduce motion, the window reduces motion too.
- **English or Spanish.** The window, the menu bar or tray menu, the setup guide, the assistant and everything Color says to the other apps follow the language you choose in Limitless Sound, the moment you change it, without moving the focus. Without Limitless Sound, Color uses your computer's language. The built-in helper understands both languages either way: Spanish as it's spoken in Mexico, Spain, Argentina, Colombia and elsewhere, with tú, vos or usted, and dictation without accents. With spoken feedback on in Limitless Sound, switching your colors with the shortcut or the menu says so, in your language.

## How it's built

```
crates/color-core     Shared color math in Rust: color vision simulation (Machado 2009),
                      correction, pinned colors, 3D lookup tables, the Windows matrix fit,
                      automatic tuning, the assistant's prompt and the offline helper. Unit tested.
app/src-tauri         The desktop app (Tauri 2): tuner window, tray menu, shortcut,
                      start at login, screen filters, Claude calls.
app/macos-overlay     The Mac screen filter helper (Swift: ScreenCaptureKit + Metal).
app/ui                The tuner window (one HTML file, no build step).
../../.github/workflows/color.yml
                      Tests, builds and smoke-tests the Mac .dmg (Apple Silicon and Intel)
                      and the Windows installer; a new version in tauri.conf.json
                      reaching main publishes a color-v<version> release.
```

The tuner preview in the window (JavaScript) and the screen filter (Rust) run the same math. A test in `color-core` checks that they give identical colors.

The Spanish is one table in the window's page (`app/ui/index.html`, `strings-es`, English text → Spanish). The window, the app's menus and messages, and the built-in helper all read it. `node --test app/test/*.test.mjs` fails on any English word without Spanish.

The built-in helper is measured on people's own descriptions (`crates/color-core/tests/descriptions`): English and Spanish, each in three sets, the ones its rules were written against, a held-out set and a blind one written by someone who never saw the rules. `cargo run -p color-core --example helper_report` prints how often it does the right thing, and `cargo test` holds each set to a floor.

| Does the right thing | Seen | Held out | Blind |
|---|---|---|---|
| English | 100% (113) | 100% (63) | 96.7% (60) |
| Spanish | 100% (210) | 99.0% (100) | 98.3% (120) |

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
