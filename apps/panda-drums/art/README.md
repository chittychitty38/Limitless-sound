# The panda, the kit, the room and the controls

Everything on screen comes from the Panda Drums GUI asset pack. The Kit page is drawn from its
art: `source_sprite_sheet.png` has every piece on a transparent background (the twelve faces,
eleven poses, paws with sticks and motion streaks, the kit, the hardware, the room, the lights,
sparks and hearts). Every control (panels, buttons, the knob, toggles, instrument tiles,
readouts, icons) is one of the pack's `ui` pieces. Three scripts turn them into what the plugin
draws: `Resources/art` and `Resources/ui` hold the result.

![The Panda Drums art](../docs/hero.jpg)

## Build the layers

Needs Python 3.11+ with numpy, Pillow, OpenCV and torch (CPU is fine), and two model files from
GitHub releases: Real-ESRGAN's `RealESRGAN_x4plus.pth` (xinntao/Real-ESRGAN) and LaMa's
`big-lama.pt` (Sanster/models).

```
python sheet_cut.py source_sprite_sheet.png RealESRGAN_x4plus.pth pieces/     # cut + 4x upscale
LAMA=big-lama.pt python sheet_stage.py pieces/ out/                           # lay out the stage
rm -r ../Resources/art && cp -r out ../Resources/art
python ui_prep.py <pack>/ui RealESRGAN_x4plus.pth ui/                         # the controls
rm -r ../Resources/ui && cp -r ui ../Resources/ui
```

- `sheet_cut.py` cuts each piece out by its box on the sheet, bleeds its colours under the
  transparent edge (so it never gets a dark fringe when scaled) and upscales it 4x with
  Real-ESRGAN, colour and alpha separately.
- `sheet_stage.py` builds the room (the background plate, its bamboo kept at the sides, the
  rug, the spotlights' beams softened into light), puts each drum and cymbal where the plugin's
  slots are at its size in inches, stands under the cymbals, the hi-hat on its stand, the snare
  on its stand and the pedal on the kick. Each pose came with a drum or a cymbal: those are
  taken out and LaMa paints back the panda's arm or leg that was behind them. Every pose is
  lined up on the panda's head and cut in two, head and body, so the head can nod, tilt and lean
  on its own; the body keeps a neck under the chin, narrower than the head, so nothing shows
  when it moves. Each face is cut down to its features (brows, glasses, eyes, nose, mouth,
  cheeks) with a soft edge, and each pose gets the transform that lays a face over its own,
  lined up on the glasses. The layers are written at 1x and 2x the 1280 x 736 stage with
  `manifest.json`: where each layer sits, the drum heads and cymbal discs (for the flashes and
  ripples), the slots, the poses' necks, the faces, the bulbs, beams and rug.
- `ui_prep.py` upscales every control of the pack 4x and writes it at 1x and 2x. It takes the
  knob apart (face, needle, centre dot) so the needle turns smoothly, paints the lettering out of
  the key and kit selectors and a tile so any key, kit or drum name fits on them, stands the
  readouts on end for the faders and lifts the thumbs off the toggles so they can slide.
  `ui.json` says where each piece's corners, lettering, arrows, dot and thumb are. The pack's
  lettering is DejaVu Sans Bold (`Resources/fonts`), so every label the plugin writes matches it.

## How the plugin draws the controls

`Source/gui/UiKit.cpp` stretches each piece the way its shape allows: a panel keeps its rounded
corners, a button keeps its corners and its lettering, a tile its label and arrows, a readout
its dot. A stretched piece is rendered once at the screen's pixel size and kept, so the slices
meet without seams. `Theme.cpp`'s look-and-feel draws every button, knob, toggle, slider, menu,
tooltip and the key panel from them.

| Control | Pack piece |
|---|---|
| Top bar, tabs | `top_navigation_bar`, `tab_inactive`, `tab_*_active` |
| Key and kit | `key_selector`, `kit_selector` (lettered for D minor and the factory kit), `dropdown` |
| Knobs | `knob_*` face, needle and dot |
| Drum strip | `bottom_instrument_strip`, `instrument_tile_*`; notes on `readout_zone` (in key, with a heart) |
| Last hit | `hit_info_panel`, `readout_hit` / `readout_midi` / `readout_zone`, `mark_bad`, `replay` |
| Drum panel | `drum_edit_panel`, `velocity_sweep`, `every_rr` |
| Stage | `popup_panel` with `toggle_*`; hit pop-ups on readouts; swap and tune on `instrument_selector` |
| Mixer | `mixer_channel`, faders on standing readouts with the toggle thumb, `modal_dialog` |
| Lab, Mapping | `lab_panel`, `mapping_panel`, readouts for zones and notes, `popup_panel` cells |
| Menus, tooltips, key panel | `popup_panel` + `primary_action`, `tooltip`, `modal_dialog` |

## How the plugin animates them

`Source/gui/Skin.cpp` loads the layers from the binary data; `PandaStage::paintSkin` draws them.

| Part | What it does |
|---|---|
| Room | Drawn once as the background; the heart lights glow, twinkle and flare with the kick. |
| Drums | Scaled to the drum's size in inches, the shell stretched for deeper or shallower drums; the head flashes and a ring runs across it on every hit. |
| Cymbals | Swing on their stands; a flash of light across the bronze. The hi-hat opens with the pedal. |
| Room | The spotlights' beams sway and flare with the cymbals; the rug's ring lights up with the kick; specks of light drift up through the beams. |
| Panda | Switches to the pose for what he's playing: hi-hat, snare, left or right tom, left or right crash, kick, a fill when the toms come fast, and the cheer when the song stops. Each new pose lands with a little punch, cut like a cartoon (no blend, no double image); he bounces with the kick and breathes. His head moves on its own: it nods to the beat, leans toward each drum he hits and dips into it. |
| Face | One of the twelve faces (and a blink) over every pose but the cheer: focused, happy and excited as the playing builds, laughing on a big crash, surprised by the first hit after a rest, a scowl on a solid china hit, sad when you mark a hit bad, a wink or a tongue when idle. |
| Effects | A stick streak where the stick came down, a spark on hard hits, hearts on big crashes. |

## Promo video

`promo.py` cuts the 46-second "Purafied – Panda Drums" promo:

```
PandaDrumsRender promo promo/                                   # the performance, from the plugin
python promo.py promo/ ../docs/hero.jpg Purafied-Panda-Drums-promo.mp4
```

The render tool plays a groove through D minor, C minor, E major, F# minor and A major (the key
panel opens and picks each key, the kit retunes, the floor tom sings a line in the key), tours
the Lab, Mixer and Mapping pages and ends on the panda's cheer. It writes the window's frames at
2x, the drums, and `timeline.json` (when each key starts, what every drum is tuned to, where the
kicks land). `promo.py` cuts it on the beat (the whole window, close on the panda, the hit
readouts, the key panel, the tiles' notes, each page) with a punch-in on every kick. Its
captions, key cards, notes, page badges and outro are made of the pack's panels, buttons,
readouts and hearts, in its lettering; a pad and bass follow the same keys and duck under the
kick, so you hear the drums sit in each key. CI builds it with every run (the
Panda-Drums-preview artifact) and a release tag publishes it.
