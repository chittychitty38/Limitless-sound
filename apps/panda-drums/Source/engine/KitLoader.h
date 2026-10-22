#pragma once

#include "KitTypes.h"
#include <juce_audio_formats/juce_audio_formats.h>

// Reads a kit from a folder of samples.
//
//   My Kit/
//     panda-kit.json                      optional: names, sizes, pitches, which mics are which
//     Kick/                               one folder per piece
//       22 Vintage/                       optional: one folder per drum you can swap to
//         Kick_In_V3_RR2.wav              velocity layer and round robin in the name
//         Kick_OH_V3_RR2.wav              same hit, another mic
//     Snare/14x6.5 Brass/Rimshot/...      optional: one folder per articulation
//
// Names are read loosely: "v3", "vel03", "layer 3", "L3" are layers; "rr2", "RR02", "rob2",
// "take 2" are round robins; what is left is the mic ("In", "Top", "OH", "Room Far"...).
// Without layer numbers the engine sorts the hits into zones by loudness.
namespace pd
{
struct ParsedName
{
    int layer = -1, rr = -1;
    juce::String mic;            // "" when the name has nothing left that looks like a mic
    juce::String artic;          // articulation word found in the name, "" if none
};

ParsedName parseSampleName (const juce::String& fileStem, const juce::StringArray& wordsToIgnore);

// Articulation id and display name for a folder or word, or empty when it isn't one.
std::pair<juce::String, juce::String> articulationFromWord (const juce::String&);

class KitLoader
{
public:
    // Scans the folder and builds the kit's structure (no audio is read yet).
    static std::shared_ptr<Kit> scan (const juce::File& root, juce::String& error);

    // Reads every sample of one variant. Safe to call from a background thread.
    static std::shared_ptr<const VariantData> loadVariant (const Kit&, int piece, int variant,
                                                           std::function<bool (float)> progress = {});

    // Writes panda-kit.json describing what was found, for checking mics and sizes by hand.
    static bool writeManifestTemplate (const Kit&, const juce::File&);
};
} // namespace pd
