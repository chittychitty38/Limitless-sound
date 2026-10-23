# Default keyboard shortcuts: Ableton Live 12, GarageBand 10, REAPER 7, FL Studio

Research for Limitless Voice DAW command packs. Compiled 2026-10-23.

## How this was verified (read first)

The session proxy blocked every vendor host for direct download (ableton.com, help.ableton.com,
support.apple.com, reaper.fm, image-line.com, and web.archive.org). Each entry was therefore verified in one of three ways:

| Tag | Meaning |
|---|---|
| **OK** | Read verbatim in a byte-for-byte copy of the official page (a saved HTML of the vendor page, mirrored on GitHub). |
| **EX** | Read only as a search-engine excerpt of the official URL. The full table wasn't visible, so confidence is lower. |
| **OLD** | Found only in an older official manual version. The entry was not re-checked against the version requested. |
| **UNCONFIRMED** | Not found in any official source. Do not ship it without testing on the real app. |
| **none** | The official reference lists no default key. A menu path or mouse route is given where one was found. |

Copies of the official pages that were read verbatim:
- Ableton (Live 12.4 web page, saved HTML): https://raw.githubusercontent.com/templeoflum/classes/HEAD/music%20production/ableton-atlas/manual-research/live-keyboard-shortcuts.html
- Ableton (earlier Live 12 Reference Manual PDF, text extraction): https://raw.githubusercontent.com/djaboxx/iron-static/HEAD/docs/api/ableton/41-live-keyboard-shortcuts.md
- FL Studio (Image-Line manual HTML, "FL Studio 2026" edition): https://raw.githubusercontent.com/sadoway7/flaik/HEAD/memory/07_Manual/basics_shortcuts.htm, plus `menu_edit.htm`, `menu_view.htm`, `menu_options.htm`, `menu_file.htm`, `menu_tools.htm`, `playlist.htm`, `mixer.htm` and `toolbar_panels.htm` in the same folder

Coverage: **Ableton** and **FL Studio** are well covered (read verbatim). **REAPER** is partly covered: the official Quick Start and the v7 What's New guide only reached me as excerpts, and the full v7 key list wasn't reachable. **GarageBand** is poorly covered: Apple's "Main window shortcuts" page never showed up in search, so most of its rows are UNCONFIRMED.

---

## 1. Ableton Live 12

Sources:
- [A] Live Keyboard Shortcuts (Live 12 manual): https://www.ableton.com/en/manual/live-keyboard-shortcuts/. The section is named in the Notes column. The chapter number is 41 or 42 depending on the manual revision, so it is omitted.
- [A-rel] Live 12 release notes: https://www.ableton.com/en/release-notes/live-12/ (EX)
- [A-124] What's new in Live 12.4: https://help.ableton.com/hc/en-us/articles/26963870210076-What-s-new-in-Live-12-4 (EX)
- [A-arr] Arrangement View chapter: https://www.ableton.com/en/live-manual/12/arrangement-view/ (EX)
- [A-kb] Help article "Keyboard shortcuts not working": https://help.ableton.com/hc/en-us/articles/360000093570-Keyboard-shortcuts-not-working (EX)

Mac/Windows rule: almost always Ctrl→Cmd and Alt→Option. The exceptions are flagged in the Notes column.

| Action | Mac | Windows | Source | Notes |
|---|---|---|---|---|
| Play/stop toggle | Space | Space | [A] Transport — OK | "Play from Start Marker/Stop" restarts from the start marker. Shift+Space = "Continue Play from Stop Point". |
| Stop | none (Space) | none (Space) | [A] — OK | No stop-only key. Space **starts** playback if Live is already stopped. |
| Record | F9 | F9 | [A] Transport — OK | Shift+F9 = Arm Recording in Arrangement. Cmd/Ctrl+Shift+F9 = Record to Session View. |
| Capture recording (Capture MIDI) | **Live 12.0–12.3:** Cmd+Shift+C. **Live 12.4+:** none | **12.0–12.3:** Ctrl+Shift+C. **12.4+:** none | older Live 12 PDF — OK; [A-rel], [A-124] — EX | **Version trap.** Live 12.4 (12.4.5 beta per the beta notes) removed the Capture MIDI shortcut and gave Ctrl/Cmd+Shift+C to **Copy Time** (Arrangement). The current manual no longer lists Capture MIDI. Use the Capture MIDI button or a Key Map instead. |
| Loop/cycle toggle | Cmd+L | Ctrl+L | [A] Arrangement View "Toggle Loop Brace" — OK; [A-arr] — EX | [A-arr] describes this as the Loop Selection command. With a time or clip selection, it sets the loop to the selection and turns looping on. **With nothing selected, the loop brace is reset to cover the whole Arrangement.** |
| Metronome toggle | O | O | [A] Transport — OK | Single letter. See the Computer MIDI Keyboard risk below. |
| Go to start | Home (or Fn+Left) | Home | [A] Transport "Move Insert Marker to Beginning" — OK | |
| Forward one bar | none | none | [A] — OK (absent) | Not in the shortcut chapter. |
| Back one bar | none | none | [A] — OK (absent) | |
| Go to bar N | none | none | [A] — OK (absent) | No "go to position" dialog is documented. |
| New track | see the next two rows | | | |
| New audio track | Cmd+T | Ctrl+T | [A] Commands for Tracks — OK | |
| New MIDI track | Cmd+Shift+T | Ctrl+Shift+T | [A] Commands for Tracks — OK | Return track = Cmd/Ctrl+Alt(Option)+T. |
| Duplicate track | Cmd+D | Ctrl+D | [A] Editing "Duplicate" — OK (generic) | Generic Duplicate acting on the current selection. The chapter does not spell out the track case, so test it. |
| Select next track | UNCONFIRMED | UNCONFIRMED | — | Arrow keys are documented only for Session clip slots and scenes. |
| Select previous track | UNCONFIRMED | UNCONFIRMED | — | |
| Solo selected track | S | S | [A] Commands for Tracks — OK | Single letter. Latches if held (see risks). |
| Mute selected track | 0 (zero) | 0 (zero) | [A] Commands for Tracks "Deactivate Selected Track" — OK | This is Live's Track Activator, which is its mute. 0 also deactivates a selected clip or notes, depending on focus. F1…F8 toggle tracks 1–8. |
| Record-arm selected track | C | C | [A] Commands for Tracks — OK | Single letter. Also lowers velocity when the Computer MIDI Keyboard is on. |
| Split at playhead | Cmd+E | Ctrl+E | [A] Arrangement View "Split Clip at Selection" — OK | Splits at the **selection/insert marker**, not necessarily at the playhead. In the MIDI note editor the same key chops notes. |
| Join/consolidate | Cmd+J | Ctrl+J | [A] Arrangement View "Consolidate Selection into Clip" — OK | In the MIDI note editor = Join Notes. |
| Duplicate/repeat clip | Cmd+D | Ctrl+D | [A] Editing — OK | Cmd/Ctrl+Shift+D = Duplicate Time. |
| Quantize | Cmd+U | Ctrl+U | [A] Clip View Sample/MIDI Editor — OK | Cmd/Ctrl+Shift+U = Quantize Settings. |
| Delete | Delete | Delete | [A] Editing — OK | The Mac "Delete" key is the Backspace key. |
| Set loop to selection | Cmd+L | Ctrl+L | [A], [A-arr] — OK/EX | Same command as the loop toggle. Select Loop Brace Contents = Cmd/Ctrl+Shift+L (the reverse operation). |
| Show mixer | Cmd+Option+M | Ctrl+Alt+M | [A] Showing and Hiding Views — OK | |
| Show browser | Cmd+Option+B | Ctrl+Alt+B | [A] — OK | Alternative: Cmd/Ctrl+Alt(Option)+5. |
| Show inspector/Info View | Shift+? | Shift+? | [A] — OK | "?" sits on a different physical key per layout (see the layout risk). |
| Show editor (Clip/Detail View) | Cmd+Option+3 | Ctrl+Alt+3 | [A] "Hide/Show Clip View" — OK | Shift+Tab or F12 toggles Device/Clip View. Cmd/Ctrl+Alt(Option)+E = full-size Clip View. |
| Show automation | A | A | [A] Breakpoint Envelopes "Toggle Automation Mode" — OK | Single letter. Latches if held. |
| Zoom in | + | + | [A] "Zoom In Time Ruler" — OK | **Not** Cmd/Ctrl + "+", which zooms the whole UI ("Zoom In Window"). |
| Zoom out | - | - | [A] "Zoom Out Time Ruler" — OK | **Not** Cmd/Ctrl + "-". |
| Zoom vertically in/out | Option + "+" / Option + "-" | Alt + "+" / Alt + "-" | [A] Arrangement View "Adjust Height of Selected Tracks/Clips" — OK | H = Optimize Arrangement Height. |
| Zoom to fit/selection | Z (to selection), X (back), W (fit width) | Z / X / W | [A] Arrangement View — OK | Single letters. Z latches if held. |
| Bounce/export mix | Cmd+Shift+R | Ctrl+Shift+R | [A] Working with Sets "Export Audio/Video" — OK | Opens a dialog. Cmd/Ctrl+B is "Bounce to New Track" (in-place), not export. |
| Undo | Cmd+Z | Ctrl+Z | [A] Editing — OK | |
| Redo | **Cmd+Shift+Z** | **Ctrl+Y** | [A] Editing — OK | Differs by OS. |
| Save | Cmd+S | Ctrl+S | [A] Working with Sets — OK | |
| Tap tempo | none | none | [A] — OK (absent) | Not in the chapter. Key Map Mode (Cmd/Ctrl+K) assigns keys to controls. Whether the Tap button can be key-mapped is UNCONFIRMED. |
| Add marker (locator) | none | none | [A] (absent); [A-arr] — EX | Use the Create menu > Add Locator, the Set Locator button, or the scrub-area context menu. |
| Next/previous marker | none | none | [A] (absent); [A-arr] — EX | Previous/Next Locator buttons. [A-arr] says they can be MIDI- or key-mapped. |

### Ableton risks
- **Computer MIDI Keyboard** (toggled with M, [A] Key/MIDI Map Mode section): when it is on, letter keys play notes, so single-letter shortcuts such as O, S, C, A, Z, X and W do not fire. Z/X change the octave and C/V change the velocity. From Live 12, holding **Shift** makes single-letter shortcuts work while it is on (manual: "Shift+S to solo a track"; [A-kb]). Whether Shift+letter also works while it is **off** is UNCONFIRMED. Never send a bare M to "fix" this, because the current state is unknown.
- **Momentary latching** ([A] Momentary Latching Shortcuts): holding A, B, S, Z, F1–F8 or Tab for about 500 ms temporarily toggles the action, and it reverts on release. Voice must send short taps, not long key-downs. This can be disabled in Options.txt with `-DisableHotKeyLatching`.
- **Context dependence**: the same keys act on whichever view has focus. For example, Cmd/Ctrl+E means split in the Arrangement, chop in the note editor, and Add/Remove Stop Button in Session. Cmd/Ctrl+J means consolidate or join. Cmd/Ctrl+Shift+E means Export MIDI File, Split Arrangement Clip in the note editor, or Hide/Show Tag Editor in the browser.
- **The "Use Tab to Move Focus" option** changes Tab from switching Session/Arrangement to focus navigation ([A] General Keyboard Navigation).
- **Version drift**: the Capture MIDI shortcut exists only before 12.4.
- **Mac function keys**: F9/F10/F11/F12 act as media or Mission Control keys unless the Mac is set to standard function keys. Whether synthetic key events bypass this is UNCONFIRMED (this is general macOS behaviour, not from Ableton's docs).
- **Keyboard layout**: the manual names keys by character (+, -, ?, [, ], ., ,). Those characters sit on different physical keys on a Spanish layout. Ableton's community forum has user reports, plus one Ableton support reply, that some Cmd+Option shortcuts fail with the macOS "Spanish – ISO" input source and work with English input (https://forum.ableton.com/viewtopic.php?t=244779). That is a forum post, not official documentation, so treat layout behaviour as UNCONFIRMED and test it.

---

## 2. GarageBand 10 (Mac only)

All entries are EX (Apple search excerpts). Apple's "Main window shortcuts in GarageBand on Mac" page, which holds the full list, could not be retrieved. Third-party cheat sheets (K, C, Y, B, E, Cmd-T, Cmd-J and so on) were deliberately **not** used.

| Action | Mac | Windows | Source | Notes |
|---|---|---|---|---|
| Play/stop toggle | Space | n/a | https://support.apple.com/en-bn/guide/garageband/gbnd1f470623/mac — EX | "You can also start or stop playback by pressing the Space bar." |
| Stop | Space | n/a | same — EX | Clicking Stop a second time moves the playhead to the start (mouse only). |
| Record | R | n/a | https://support.apple.com/en-gb/guide/garageband/gbnd40fcef0f/10.4.7/mac/11.5 — EX | Space stops recording. |
| Capture recording | UNCONFIRMED | n/a | — | No documented equivalent was found. |
| Loop/cycle toggle | UNCONFIRMED | n/a | — | The "Use the cycle area" page was not reachable. |
| Metronome toggle | UNCONFIRMED | n/a | https://support.apple.com/en-gb/guide/garageband/gbnda8165874/10.4.7/mac/11.5 — EX | Apple's page says to click the Metronome button. K is Apple's key on **iPad/iPhone only**. |
| Go to start | UNCONFIRMED | n/a | — | Return is Apple's key on iPad/iPhone. The Mac key was not confirmed. |
| Forward/back one bar | UNCONFIRMED | n/a | transport page — EX | The Forward/Rewind buttons move one bar (mouse). |
| Go to bar N | UNCONFIRMED | n/a | — | |
| New track | Option-Command-N | n/a | https://support.apple.com/guide/garageband/create-tracks-gbnd22a07333/10.4.4/mac/11.0 — EX | Opens the New Track dialog. The track type is chosen in the dialog. |
| New audio / instrument track | via the Option-Command-N dialog | n/a | same — EX | No direct per-type key was found. |
| Duplicate track | menu: Track > New Track with Duplicate Settings | n/a | same page — EX | Shortcut UNCONFIRMED. |
| Select next/previous track | UNCONFIRMED | n/a | — | |
| Solo / mute / record-arm | UNCONFIRMED | n/a | https://support.apple.com/bg-bg/guide/garageband/gbnd1157ae2a/mac — EX | Apple documents the track-header buttons only. |
| Split at playhead | UNCONFIRMED | n/a | — | Command-T is documented for iPad/iPhone only. |
| Join | UNCONFIRMED | n/a | — | Command-J is documented for iPad/iPhone only. |
| Duplicate region | UNCONFIRMED | n/a | — | |
| Quantize | none | n/a | https://support.apple.com/en-hk/guide/garageband/gbnd221a8f4a/mac — EX | Use the Time Quantize pop-up in the editor inspector (mouse). |
| Delete | UNCONFIRMED | n/a | — | |
| Set loop to selection | UNCONFIRMED | n/a | — | |
| Show mixer | n/a | n/a | https://support.apple.com/guide/garageband/the-garageband-main-window-gbnd7f48d68b/10.4.4/mac/11.0 — EX | The main window overview lists no mixer window; mixing is done in the track headers. |
| Show browser/Library | UNCONFIRMED | n/a | — | Library button in the control bar. |
| Show inspector (Smart Controls) | UNCONFIRMED | n/a | — | |
| Show editor | UNCONFIRMED | n/a | — | |
| Show automation | A | n/a | https://support.apple.com/en-mide/guide/garageband/gbnd939b92d8/10.4.7/mac/11.5 — EX | "Choose Mix > Show Automation (or press A)." |
| Zoom in/out | UNCONFIRMED | n/a | https://support.apple.com/en-ph/guide/garageband/gbndd75e5c48/mac — EX | Apple describes the horizontal zoom slider in the ruler (mouse). |
| Zoom vertical / to fit | UNCONFIRMED | n/a | — | |
| Bounce/export mix | menu: Share > Export Song to Disk | n/a | https://support.apple.com/guide/garageband/export-songs-to-disk-gbnd7cbf5ed9/10.4.4/mac/11.0 — EX | Shortcut UNCONFIRMED. |
| Undo / Redo / Save | Command-Z / Shift-Command-Z / Command-S | n/a | https://support.apple.com/en-us/102650 — EX | These are macOS-wide conventions and were not checked against GarageBand's own list. |
| Tap tempo | UNCONFIRMED | n/a | — | |
| Add marker / next-previous marker | UNCONFIRMED | n/a | — | No marker feature was found in the docs searched. |
| (extra) Musical Typing window | Command-K | n/a | https://support.apple.com/guide/garageband/play-software-instruments-gbndd5278cd1/10.4.4/mac/11.0 — EX | |
| (extra) Editors | Option-Up/Down = transpose a semitone. Option-Shift-Up/Down = an octave. Option-Space = preview audio. | n/a | https://support.apple.com/guide/garageband/editors-shortcuts-gbnd957b4cc6/10.4.4/mac/11.0 — EX | |

### GarageBand risks
- **Musical Typing** (Command-K): turns letter keys into notes, with Z/X for octave and C/V for velocity (Apple page above). Whether it swallows single-letter shortcuts such as R and A while open is UNCONFIRMED.
- Most of the pack cannot be confirmed from here. Before shipping, check it on a real Mac against Apple's "Main window shortcuts in GarageBand on Mac" page (linked from https://support.apple.com/en-au/guide/garageband/gbnd715f33a0/10.4.7/mac/11.5) or against GarageBand's own menus.
- **Layout**: macOS app menu shortcuts are generally matched by character, but this is UNCONFIRMED for GarageBand.

---

## 3. REAPER 7

Sources:
- [QS] REAPER Quick Start (current, "about 75 common things"): https://www.reaper.fm/guides/REAPER%20Quick%20Start.pdf (EX)
- [W7] REAPER 7.0 What's New: https://dlz.reaper.fm/userguide/WhatsNewReaper7Summary_r2.pdf (EX)
- [UG5] User Guide v5.974 (older): http://dlcf.reaper.fm/userguide/ReaperUserGuide5974c.pdf (EX, OLD)
- [U667] Update summary 6.67+ (retroactive record): https://dlz.reaper.fm/userguide/REAPER%20main%20changes%20667%20to%20671.pdf (EX)
- The current v7 User Guide (v7.81, at https://www.reaper.fm/userguide.php) could not be read.

**Mac column**: REAPER's documentation is written with Windows keys. The user guides give the Mac mapping as Control→Command and Alt→Option ([UG5], OLD). Every Mac entry below is that mapping applied by me, so treat the whole Mac column as **UNCONFIRMED-derived**. No v7 Mac-specific list was found.

| Action | Mac (derived) | Windows | Source | Notes |
|---|---|---|---|---|
| Play/stop toggle | Space | Space | [QS] — EX | |
| Stop | Space | Space | [QS] — EX | No stop-only key. Enter = pause [QS]. |
| Record | Cmd+R | Ctrl+R | [QS] — EX | "Record start/stop [Ctrl+R]/[Space]". |
| Capture recording | none found | none found | [U667] — EX | Retroactive MIDI actions ("MIDI: Insert … retroactively recorded …") exist since 6.67. Default key UNCONFIRMED. |
| Loop/cycle toggle | R | R | [QS] "Toggle loop playback [R]" — EX | Single letter. |
| Metronome toggle | UNCONFIRMED | UNCONFIRMED | — | No default key found. Use the metronome button on the transport. |
| Go to start | W or Home | W or Home | [QS] — EX | |
| Forward/back one bar | UNCONFIRMED | UNCONFIRMED | — | |
| Go to bar N | Cmd+J (derived) | Ctrl+J | [QS] "Go to marker … [Ctrl+J]"; [UG5] describes the Jump To dialog — EX/OLD | Opens the Jump To dialog. Type e.g. `33.1` (bar.beat) or `M1` (marker 1), then Enter. |
| New track | Cmd+T | Ctrl+T | [QS] — EX | REAPER tracks are generic (audio or MIDI). |
| New audio track | Cmd+T | Ctrl+T | [QS] — EX | Same as new track. |
| New instrument track | menu: Insert > Virtual instrument on new track | same | [QS] — EX | Shortcut UNCONFIRMED. |
| Duplicate track | UNCONFIRMED | UNCONFIRMED | — | |
| Select next track | Cmd+Option+Down | Ctrl+Alt+Down | [QS], [UG5] — EX | |
| Select previous track | Cmd+Option+Up | Ctrl+Alt+Up | [QS], [UG5] — EX | |
| Solo / mute / record-arm selected track | none found | none found | [QS], [W7] — EX | [QS] says to click the buttons. [W7] suggests *assigning* a key to "Track: Toggle mute for selected tracks", which implies there is no default. |
| Split at playhead | S | S | [QS], [W7] — EX | Splits at the **edit cursor** (all items if none are selected) [W7]. |
| Join/glue | menu: right-click > Glue selected items | same | [QS] — EX | Shortcut UNCONFIRMED. |
| Duplicate item | UNCONFIRMED | UNCONFIRMED | [QS] — EX | [QS] gives only Ctrl+drag (mouse). |
| Quantize | UNCONFIRMED | UNCONFIRMED | — | |
| Delete | UNCONFIRMED | UNCONFIRMED | — | Not seen in the sources. |
| Set loop to selection | UNCONFIRMED | UNCONFIRMED | — | |
| Show mixer | Cmd+M | Ctrl+M | [QS] — EX | |
| Show browser (Media Explorer) | menu: View > Media Explorer | same | [QS] — EX | Shortcut UNCONFIRMED. |
| Show inspector | n/a / UNCONFIRMED | n/a / UNCONFIRMED | — | |
| Show editor (MIDI editor) | UNCONFIRMED | UNCONFIRMED | — | |
| Show automation | UNCONFIRMED | UNCONFIRMED | — | |
| Zoom in/out (horizontal) | **CONFLICT – UNCONFIRMED** | **CONFLICT – UNCONFIRMED** | [QS] vs [UG5] — EX | The [QS] excerpt and [UG5] give + and - in opposite directions. The excerpt may be garbled, so test before shipping. |
| Zoom vertically | PageUp = in; PageDown UNCONFIRMED | same | [QS] — EX | |
| Zoom to fit | Cmd+PageDown | Ctrl+PageDown | [QS] "Zoom to project" — EX | |
| Bounce/export mix | Cmd+Option+R | Ctrl+Alt+R | [QS] File > Render — EX | Opens the Render dialog. |
| Undo | Cmd+Z | Ctrl+Z | [UG5] — OLD | |
| Redo | Cmd+Shift+Z | Ctrl+Shift+Z | [UG5] — OLD | |
| Save | Cmd+S | Ctrl+S | [QS] — EX | |
| Tap tempo | none found | none found | [QS] — EX | [QS] says to click the BPM button on the transport. |
| Add marker | M | M | [QS] — EX | Shift+M = named marker. |
| Next/previous marker | UNCONFIRMED | UNCONFIRMED | — | Alternative: Ctrl/Cmd+J, then type `M<n>`. |

### REAPER risks
- **The keymap is fully user-editable**, and many users replace it. In particular, OSARA (the screen-reader extension) ships its own Windows and Mac keymaps (https://github.com/jcsteh/osara, `config/windows/reaper-kb.ini` and `config/mac/reaper-kb.ini`). A default-keymap pack will misfire on those setups.
- **Mac/Windows**: the Mac column is derived, not documented. Before shipping, read the real list on the target machine via Help > Key bindings and mouse modifiers (Shift+F1 per the user guide, EX).
- **Context sections**: single letters (S, M, R, W) belong to the Main (arrange) section. The MIDI editor and Media Explorer have separate action sections, so the same key can do something else there.
- **Keyboard layout**: UNCONFIRMED whether REAPER binds by character or by virtual key.

---

## 4. FL Studio (2024 / 21; read from the current "FL Studio 2026" manual)

Sources:
- [FL] Keyboard & Mouse Shortcuts: https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/basics_shortcuts.htm (OK, read via the mirror)
- [FL-menu] Edit / View / Options / File / Tools menus: https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/menu_edit.htm (and `menu_view.htm`, `menu_options.htm`, `menu_file.htm`, `menu_tools.htm`) (OK)
- [FL-pl] Playlist: https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/playlist.htm (OK)
- [FL-tb] Toolbar/transport: https://www.image-line.com/fl-studio-learning/fl-studio-online-manual/html/toolbar_panels.htm (OK)

Version caveat: the copy read is the newest (2026) edition of the manual. The 2024 and 21 editions were not checked separately.

Mac column: from Image-Line's own equivalence table in [FL]. Ctrl→Cmd, Alt→Option, Backspace→delete, Delete→fn+delete, Insert→fn+return. The table does not map Home or PgUp/PgDn.

| Action | Mac | Windows | Source | Notes |
|---|---|---|---|---|
| Play/stop toggle | Space | Space | [FL] Record/Playback/Transport — OK | Cmd/Ctrl+Space = Start/Pause (see the Mac Spotlight risk). |
| Stop | Space | Space | [FL-tb] — OK | No stop-only key. |
| Record | R | R | [FL] "Switch On/Off recording" — OK | R only **arms** record mode. Play (Space) then starts recording [FL-tb]. |
| Capture recording | none | none | [FL-menu] Tools — OK | Tools > Dump score log to selected pattern (always-on MIDI logger, last 30 min). Tools > Audio Logger (2026 edition). |
| Loop/cycle toggle | none | none | [FL], [FL-pl] — OK | No loop toggle. A Playlist time selection plays in a loop; a "Song loop" marker is set by right-clicking a time marker. **L = Pattern/Song mode switch, not loop.** |
| Metronome toggle | Cmd+M | Ctrl+M | [FL], [FL-menu] Options — OK | **In the Piano roll, Ctrl/Cmd+M = Import MIDI file** [FL]. |
| Go to start | UNCONFIRMED (Home is not in the Mac table) | Home | [FL] Playlist "Move playback marker to start" — OK | Playlist context. |
| Forward one bar | Numpad * | Numpad * | [FL] "Next bar (Song mode)" — OK | Numpad only. Song mode only. |
| Back one bar | Numpad / | Numpad / | [FL] "Previous bar (Song mode)" — OK | Numpad 0 = fast forward. |
| Go to bar N | none | none | [FL] — OK (absent) | |
| New track / new audio track / new instrument track | none | none | [FL] — OK (absent) | Instruments are added via the Channel Rack or the Plugin Picker (F8, drag-and-drop). Playlist tracks already exist. |
| Duplicate track | Opt+C (channel) | Alt+C (channel) | [FL] Channel Rack "Clone selected Channels" — OK | Clones a Channel Rack channel, not a Playlist track. |
| Select next track | Down arrow | Down arrow | [FL] Channel Rack "Select Channel below" — OK | Channel Rack only. None is listed for the Mixer. |
| Select previous track | Up arrow | Up arrow | [FL] Channel Rack — OK | |
| Solo selected track | S (Mixer) | S (Mixer) | [FL] Mixer "Solo Current track" — OK | S is the Slip edit tool in the Playlist and Slide toggle in the Piano roll. Channel Rack: Cmd/Ctrl+1…0 solos channels 1–10. |
| Mute selected track | none (Mixer) | none (Mixer) | [FL] — OK (absent) | Channel Rack: 1…9, 0 mute/unmute channels 1–10. Playlist: Opt/Alt+M mutes selected **clips**. |
| Record-arm selected track | none | none | [FL] — OK (absent) | Mixer arming is mouse-only in the docs. |
| Split at playhead | fn+return (Insert) | Insert | [FL] Playlist "Slice Clip at cursor position" — OK | Whether "cursor" means the mouse or the playhead is not stated. Test it. |
| Join/consolidate | Cmd+Opt+C | Ctrl+Alt+C | [FL], [FL-pl] "Consolidate selected Clips starting from first Clip" — OK | +Shift = from song start. Piano roll: Cmd/Ctrl+G = Glue notes. |
| Duplicate/repeat region | Cmd+B | Ctrl+B | [FL] Playlist/Piano roll "Duplicate selection to the right" — OK | **Cmd/Ctrl+D = Deselect**, not duplicate. |
| Quantize | Piano roll: Cmd+Q (quick), Opt+Q (tool). Playlist: Shift+Q | Ctrl+Q / Alt+Q / Shift+Q | [FL] — OK | Playlist Shift+Q quantizes clip start times. |
| Delete | fn+delete | Delete | [FL] — OK | In the Playlist, Del = "Delete selected clip/pattern **source data**". |
| Set loop to selection | none | none | [FL-pl] — OK | Ctrl+left-drag in the ruler makes a time selection that loops (mouse). |
| Show mixer | F9 | F9 | [FL], [FL-menu] View — OK | |
| Show browser | Opt+F8 | Alt+F8 | [FL], [FL-menu] View — OK | |
| Show inspector | none | none | — | F11 = Project/Song info, not an inspector. |
| Show editor (piano roll) | F7 | F7 | [FL] — OK | F5 Playlist, F6 Channel Rack. |
| Show automation | none | none | [FL] — OK (absent) | |
| Zoom in/out | PgUp/PgDn (Mac key UNCONFIRMED) | PgUp / PgDn | [FL], [FL-pl] — OK | Playlist and Piano roll. |
| Zoom vertically | none | none | [FL-pl] — OK | Mouse only (track-height control). |
| Zoom to fit/selection | Shift+4 (show all), Shift+5 (to selection) | same | [FL] — OK | [FL] also lists "5 = Zoom on selection", and [FL-pl] says Shift+Z. The manual contradicts itself, so test it. |
| Bounce/export mix | Cmd+R (WAV), Cmd+Shift+R (MP3) | Ctrl+R / Ctrl+Shift+R | [FL], [FL-menu] File — OK | Opens the render dialog. |
| Undo | Cmd+Z | Ctrl+Z | [FL], [FL-menu] Edit — OK | **Ctrl/Cmd+Z is a toggle ("Undo/Redo last edit")**. Cmd/Ctrl+Opt/Alt+Z steps back through the history. |
| Redo | (Cmd+Z when at the latest step) | (Ctrl+Z) | [FL-menu] Edit — OK | No separate redo key is listed. |
| Save | Cmd+S | Ctrl+S | [FL] — OK | **Cmd/Ctrl+N = "Save new version"**, not new project. |
| Tap tempo | none | none | [FL-menu] View — OK | View > Tempo tapper. |
| Add marker | Opt+T | Alt+T | [FL], [FL-pl] "Add Time marker" — OK | [FL] also lists Ctrl/Cmd+T in the Playlist, but that key is the global typing-keyboard toggle. Use Alt/Opt+T. |
| Next/previous marker | Opt + Numpad / or * | Alt + Numpad / or * | [FL] "Jump to Next/Previous song marker" — OK | The manual writes "Alt/Opt+/*" without saying which key goes which way. Test it. |

### FL Studio risks
- **Typing keyboard to piano (Ctrl/Cmd+T)**: [FL] says single-key shortcuts only work while it is **off**. Its state is unknown to Voice, so never toggle it blindly.
- **Strongly context-dependent** ([FL] says so explicitly). Single letters select tools in the Playlist and Piano roll (B, C, D, E, P, S, T, Y, Z). S, M and Ctrl+M change meaning per window. Number keys mute channels in the Channel Rack.
- **macOS: Cmd+Space opens Spotlight.** [FL-tb] tells Mac users to change the Spotlight shortcut for Start/Pause to work.
- **Numpad-only shortcuts** (bar jump, fast forward, marker jump) don't exist on most Mac and laptop keyboards. Whether synthetic keypad keycodes work is UNCONFIRMED.
- **Easy-to-confuse keys**: Ctrl+D (deselect), Ctrl+N (save new version), Ctrl+Z (undo/redo toggle), and Del in the Playlist (deletes source data).
- **Layout**: UNCONFIRMED. The toolbar page mentions "Standard keyboard layouts" only for the typing-to-piano note layout.

---

## UNCONFIRMED summary (do not ship without testing)
- **Ableton**: select next/previous track. Tap-tempo mappability. Whether Shift+letter works while the Computer MIDI Keyboard is off.
- **GarageBand**: almost everything except Space, R, Option-Command-N, A, Command-K, the editor transpose keys, and the macOS-standard undo/redo/save. Cycle, metronome, go to start, split, join, Library, Smart Controls, editor, solo/mute and zoom are all UNCONFIRMED.
- **REAPER**: the entire Mac column. Metronome, duplicate track, glue/duplicate/quantize/delete keys, MIDI editor and automation keys, horizontal zoom direction (sources conflict), next/previous marker, and bar nudge. Undo/redo were confirmed only in v5 docs.
- **FL Studio**: Mac keys for Home and PgUp/PgDn. Insert-slice target (mouse vs playhead). Direction of the marker-jump keys. Zoom-to-selection key (the manual contradicts itself). Whether the 2024/21 editions differ from the 2026 manual.
