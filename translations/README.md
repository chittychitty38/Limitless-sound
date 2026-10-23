# Native speakers' read

Every Spanish and Portuguese word in Limitless Sound was written without a native speaker. These
two pages ask one to use the suite for half an hour and say what reads wrong:

- [es.md](es.md), in Spanish, for a Spanish-speaking musician (the whole suite is in Spanish).
- [pt.md](pt.md), in Brazilian Portuguese, for Limitless Voice's Portuguese preview. It also asks
  whether a preview that hears about 6 commands in 10 is worth keeping.

Send the page's link. Each walks through installing, switching the language, what to try, the
specific words we doubt, and how to report.

Reports come back as GitHub issues from two forms, each in English, Spanish and Portuguese:

- **Words to fix** (`translation` label): language, app, where, what it says, what it should say.
- **Voice didn't understand me** (`voice` label): what was said word for word, what Voice showed
  it heard, what happened, the DAW, the microphone, and optionally the speaker's accent.

To apply them, ask a Claude Code session: "Apply the open translation and voice issues." Words go
into `apps/voice/limitless_voice/languages/es.yaml` or `pt.yaml` (Voice), `words.py` (One-Hand,
Zoom), or a page's `strings-es` table (Limitless Sound, Control, GazeStage, Color, the website). A
new word must still fit at double text size: each app's language test checks. A misheard command
becomes a test case in `stress/`, where it's measured on every change.
