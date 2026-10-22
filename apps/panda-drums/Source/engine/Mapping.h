#pragma once

#include "KitTypes.h"

// Which MIDI note plays which drum.
//
// Maps name drums by role ("snare.rim", "tom2", "hihat.pedal") rather than by position, so the
// same map works for any kit: a role the kit doesn't have just isn't played.
namespace pd
{
struct MapEntry
{
    int note = -1;
    juce::String target;   // "piece" or "piece.articulation"
};

struct MidiMap
{
    juce::String name;
    std::vector<MapEntry> entries;

    juce::var toVar() const;
    static MidiMap fromVar (const juce::var&);
    juce::String targetFor (int note) const;
    void set (int note, const juce::String& target);    // a note plays one thing; a target can have many notes
    void clearTarget (const juce::String& target);
    std::vector<int> notesFor (const juce::String& target) const;
};

// Built-in maps. The first one is the default.
const std::vector<MidiMap>& presetMaps();

// Resolved for the audio thread: note -> piece and articulation index of the current kit.
struct ResolvedNote { int piece = -1; int artic = -1; };

struct ArticRef { int piece; int artic; juce::String target; juce::String label; };

// Every playable target of a kit: "Snare · Rimshot" -> "snare.rim".
std::vector<ArticRef> playableTargets (const Kit&, const std::vector<std::shared_ptr<const VariantData>>& selected);

std::array<ResolvedNote, 128> resolveMap (const MidiMap&, const Kit&, const std::vector<std::shared_ptr<const VariantData>>& selected);
} // namespace pd
