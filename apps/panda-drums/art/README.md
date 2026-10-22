# The panda, the kit and the room

The Kit page is drawn from the Panda Drums art: `source_sprite_sheet.png` has every piece on a
transparent background (the twelve faces, eleven poses, paws with sticks and motion streaks, the
kit, the hardware, the room, the lights, sparks and hearts). Two scripts turn it into the layers
the plugin animates; `Resources/art` holds the result.

![The Panda Drums art](../docs/hero.jpg)

## Build the layers

Needs Python 3.11+ with numpy, Pillow, OpenCV and torch (CPU is fine), and two model files from
GitHub releases: Real-ESRGAN's `RealESRGAN_x4plus.pth` (xinntao/Real-ESRGAN) and LaMa's
`big-lama.pt` (Sanster/models).

```
python sheet_cut.py source_sprite_sheet.png RealESRGAN_x4plus.pth pieces/     # cut + 4x upscale
LAMA=big-lama.pt python sheet_stage.py pieces/ out/                           # lay out the stage
rm -r ../Resources/art && cp -r out ../Resources/art
```

- `sheet_cut.py` cuts each piece out by its box on the sheet, bleeds its colours under the
  transparent edge (so it never gets a dark fringe when scaled) and upscales it 4x with
  Real-ESRGAN, colour and alpha separately.
- `sheet_stage.py` builds the room (the background plate, its bamboo kept at the sides, the
  rug), puts each drum and cymbal where the plugin's slots are at its size in inches, stands
  under the cymbals, the hi-hat on its stand, the snare on its stand and the pedal on the kick.
  Each pose came with a drum or a cymbal: those are taken out and LaMa paints back the panda's
  arm or leg that was behind them. Every pose is lined up on the panda's head. Each face is cut
  down to its features (brows, glasses, eyes, nose, mouth, cheeks) with a soft edge, and each
  pose gets the transform that lays a face over its own, lined up on the glasses. The layers are
  written at 1x and 2x the 1280 x 736 stage with `manifest.json`: where each layer sits, the
  drum heads and cymbal discs (for the flashes and ripples), the slots, the poses and faces.

## How the plugin animates them

`Source/gui/Skin.cpp` loads the layers from the binary data; `PandaStage::paintSkin` draws them.

| Part | What it does |
|---|---|
| Room | Drawn once as the background; the heart lights glow, twinkle and flare with the kick. |
| Drums | Scaled to the drum's size in inches, the shell stretched for deeper or shallower drums; the head flashes and a ring runs across it on every hit. |
| Cymbals | Swing on their stands; a flash of light across the bronze. The hi-hat opens with the pedal. |
| Panda | Switches to the pose for what he's playing: hi-hat, snare, left or right tom, left or right crash, kick, a fill when the toms come fast, and the cheer when the song stops. Each new pose lands with a little punch; he bounces with the kick and bobs to the beat. |
| Face | One of the twelve faces (and a blink) over every pose but the cheer: focused, happy and excited as the playing builds, laughing on a big crash, surprised by the first hit after a rest, a scowl on a solid china hit, sad when you mark a hit bad, a wink or a tongue when idle. |
| Effects | A stick streak where the stick came down, a spark on hard hits, hearts on big crashes. |

## Promo video

`promo.py` cuts the 46-second "Purafied – Panda Drums" promo:

```
PandaDrumsRender promo promo/                                   # the performance, from the plugin
python promo.py promo/ ../docs/hero.jpg Purafied-Panda-Drums-promo.mp4
```

The render tool plays a groove through D minor, C minor, E major, F# minor and A major (the kit
retunes to each and the floor tom sings a line in the key), tours the Lab, Mixer and Mapping
pages and ends on the panda's cheer. It writes the window's frames at 1.5x, the drums, and
`timeline.json` (when each key starts, what every drum is tuned to, where the kicks land).
`promo.py` adds the titles, captions and key cards, and a pad and bass that follow the same
keys and duck under the kick, so you hear the drums sit in each key. CI builds it with every
run (the Panda-Drums-preview artifact) and a release tag publishes it.
