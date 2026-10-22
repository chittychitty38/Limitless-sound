# The panda plays a song

Turn a finished song into the drum part the panda plays, then film him playing it.

```
# 1. The drum part, from the song itself (drums separated, transcribed, put on the song's click).
MDX=kuielab_a_drums.onnx ADTOF=ADTOF-pytorch python transcribe_drums.py song.mp3 part.json

# 2. Watch him play it: frames of the stage at 60 fps (frame n shows him n/60 s in), the song
#    under them. At this scale the stage's picture fills a 1920 x 1080 crop edge to edge.
PD_STAGE=1 PD_SCALE=1.592 PD_FPS=60 PandaDrumsRender song part.json take/
ffmpeg -framerate 60 -start_number 1 -i take/frames/%05d.png -itsoffset -0.0167 -i song.mp3 \
       -vf crop=1920:1080:59:12 -pix_fmt yuv420p -shortest take.mp4

# 3. Or the promo, cut to the song (a script says its key and when each page shows).
PandaDrumsRender songpromo part.json script.json promo/
PROMO_JOBS=4 python ../../art/promo_song.py promo/ ../../docs/hero.jpg song.mp3 promo.mp4
```

`song` and `songpromo` both play the song from its start, so a long take can be rendered in
parallel pieces: `song part.json piece/ <from> <to>` draws only that stretch (numbering its
frames from 1), and a `songpromo` script's `from` and `end` do the same for the promo.

- `transcribe_drums.py` needs numpy, librosa, soundfile, onnxruntime, torch and scikit-learn,
  KUIELab's MDX-Net drums model (`kuielab_a_drums.onnx`, from the TRvlvr/model_repo releases)
  and a checkout of xavriley/ADTOF-pytorch (its weights are in it). How it reads the part is
  written at the top of the script: the click fitted to the drums over the whole song, every hit
  timed to the drums' own attacks, and a drummer's sense of what can and can't be played (a
  crash takes the place of the hat under it, no ride under a snare roll, the off-beat crack of a
  snare in the cymbals isn't a cymbal).
- `PandaDrumsRender song` sends the notes in early by the latency Showtime reports, as a host's
  delay compensation does, so every stroke lands on the song's own drums. `PD_TRACE=1` writes
  `trace.csv` instead of frames: his fists, stick tips, head and shoulders every frame (run it
  at `PD_FPS=240`); `PD_RIG_LOG=1` logs every stroke, which hand played it and how far from the
  head the stick landed.
- `this_sucks.json` and `this_sucks_script.json` are the part and the promo's script for "This
  Sucks" (165 bpm on the click, played half-time, C major).
