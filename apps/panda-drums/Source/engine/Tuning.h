#pragma once

#include <juce_core/juce_core.h>
#include <vector>

// Keys, scales and putting drums in key.
namespace pd
{
struct Scale
{
    const char* name;
    std::vector<int> steps;          // semitones above the root
};

const std::vector<Scale>& scales();  // index 0 = "Off (chromatic)"

struct Key
{
    int root = 0;                    // 0 = C ... 11 = B
    int scale = 1;                   // index into scales(); 1 = Major, 0 = off
    bool isOff() const { return scale <= 0; }
    juce::String name() const;       // "D minor", "Off"
    bool contains (int midiNote) const;
};

// Nearest note of the key to a pitch (any note when the key is off).
int nearestInKey (const Key&, float midiPitch);

// Next note of the key strictly above / below the pitch.
int stepInKey (const Key&, float midiPitch, int direction);

// Puts a set of drums in key with the least retuning, keeping them in the order they were
// (a lower drum stays lower) and on different notes. Returns semitone offsets.
std::vector<float> tuneToKey (const Key&, const std::vector<float>& naturalMidi, float maxShift = 7.0f);

// Chromatic play: the pitch a MIDI note plays on a drum. The whole keyboard zone is moved by
// whole octaves so its first octave lands on the drum's natural pitch; melodies keep their shape.
float chromaticTarget (int note, float naturalMidi, int zoneLow, int zoneHigh);
} // namespace pd
