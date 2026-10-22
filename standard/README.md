# The Limitless Access Standard (draft 0.1)

**Any musician, any body, any input, any tool.**

MIDI let any keyboard play any synth. The Limitless Access Standard does the same for
access: any input a musician can use (eyes, voice, one hand, a foot, a single switch, an
adaptive controller) can drive any instrument, plug-in, amp modeler or recording app that
carries the mark. A musician sets up their access once, and every product they pick up
already fits them.

It is built on the open [Limitless Link protocol](../shared/PROTOCOL.md), which the six
Limitless Sound apps already speak. Anyone can implement it, free. The mark is how a
musician can tell, at a glance in a store, that a product will work for them.

> This is a voluntary, compassionate standard written with disabled musicians. It is not a
> legal accessibility certification and does not claim compliance with the ADA, Section 508,
> the European Accessibility Act or any other law.

## The four levels

Each level includes the ones before it. Levels 1 and 2 are tested automatically by the
[test kit](conformance/). Levels 3 and 4 need people, so they are attested with evidence.

### Level 1: Connected

The product joins the suite, so any input can trigger it.

| Check | Requirement |
|---|---|
| C1 | Connects to the hub and says `hello` with a stable tool id. Works exactly the same when no hub is running. |
| C2 | Announces its actions: everything a musician would reach for (play, record, next preset, tuner, tone). |
| C3 | Every action has a short id, a plain-language label of 60 characters or less (what a screen reader will say), and uses only the shared `daw.*` intents for transport-style actions, so "record" means the same thing everywhere. |
| C4 | Answers every action within 3 seconds. A refusal always says why, in words a person can hear. |

### Level 2: Adaptive

The product honors the musician's shared settings, so they set them once for everything.

| Check | Requirement |
|---|---|
| A1 | Applies a change to the shared settings within 3 seconds and reports it as the state `prefs.applied` (see [Shared preferences](../shared/PROTOCOL.md#shared-preferences)). |
| A2 | Honors at least text size (`textScale`), high contrast (`highContrast`) and reduced motion (`reduceMotion`). Products with pointer or switch selection should also honor `dwellMs` and `scanMs`. |

### Level 3: Hands-free

| Check | Requirement |
|---|---|
| H1 | The product's core job can be done start to finish with no hands: by eyes, by voice, or by one switch. For an amp modeler that means picking a tone and shaping it; for a DAW, recording a take; for an instrument, playing a part. |
| H2 | Evidence: an unedited video or written walkthrough, linked in the report. |

### Level 4: Co-designed

| Check | Requirement |
|---|---|
| D1 | Tested with at least three disabled musicians with different access needs, paid for their time, with their consent to be named or kept anonymous, and their feedback answered in a public changelog. |

## Testing a product

```sh
# A private test hub; start your product with the LIMITLESS_SOUND_HOME it prints.
python3 standard/conformance/las_check.py --tool myamp --try-all --level adaptive --json report.json

# A product already running alongside Limitless Sound on this computer.
python3 standard/conformance/las_check.py --live --tool zoom --try in,out

# Levels 3 and 4.
python3 standard/conformance/las_check.py --tool myamp --try-all \
    --attest hands-free --evidence https://example.org/walkthrough
```

`--try-all` presses every action the product announces, so use `--try` with a list of safe
actions for anything that deletes, sends or spends. The exit code is 0 when the level asked
for with `--level` passes, so the kit can run in a product's own CI. The test kit needs only
Python 3.10 or later.

## The mark

A product that passes can carry the mark for its level: **Limitless Access: Connected**,
**Adaptive**, **Hands-free** or **Co-designed**, with the version of the standard.

Draft terms, to be settled with the first partners:

- **The protocol is free and open** to implement, forever. Only the mark is licensed.
- **Mark license:** a flat yearly fee scaled to company size, free for independent
  developers and nonprofits.
- **Giving back:** 10% of every mark fee goes straight to disabled musicians: gear grants,
  paid studio time, and paid testing seats for Level 4.
- **Proof stays public:** every certified product's report JSON and evidence is published,
  and a musician can flag a product that no longer passes for re-testing.
- **Run by the people it serves:** a council with a majority of disabled musicians decides
  changes to the standard and to these terms.

## For hardware and existing products

A guitar, amp, pedal, drum module or controller can join through a small bridge app that
speaks the protocol and talks to the device over MIDI, USB or Bluetooth. The bridge carries
the mark for that device. Limitless Control (Xbox Adaptive Controller) is the first example.

## Versions

| Version | Status |
|---|---|
| 0.1 | Draft. Levels 1 to 4, test kit for 1 and 2. Open for comment from musicians and makers. |
