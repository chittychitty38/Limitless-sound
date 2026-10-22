#pragma once

#include "KitTypes.h"

// Measuring hits and sorting them into velocity zones ("lanes") and round robins.
namespace pd
{
struct ZoneSettings
{
    enum class Source { FileNames, Loudness };   // what decides which zone a hit lives in
    enum class Ranges { Even, Loudness };        // how 1..127 is split between the zones

    Source source = Source::FileNames;           // falls back to Loudness when names carry no layer numbers
    Ranges ranges = Ranges::Even;
    int zoneCount = 0;                           // Loudness source only: 0 = automatic
    float levelMatch = 0.0f;                     // 0..1: pull the round robins of a zone to the same level
};

struct Zone
{
    int lo = 1, hi = 127;                        // velocity lane
    std::vector<int> hits;                       // indices into Articulation::hits, in round robin order
    float refDb = -120.0f;                       // median peak of the zone
};

struct ArticLayout
{
    std::vector<Zone> zones;                     // softest first
    std::vector<float> hitGain;                  // per hit, level match
    std::vector<int> hitZone;                    // per hit
    std::vector<int> hitRound;                   // per hit, 0-based position in its zone
    bool fromFileNames = false;
};

// Fills peakDb, rmsDb and length.
void measureHit (Hit&, int referenceMic);

// Fundamental of a drum, from the ring after the attack. 0 when nothing clear was found.
float detectPitchHz (const juce::AudioBuffer<float>&, double sampleRate);

// Runs pitch detection on the loudest hits of the first tunable articulation.
float detectVariantPitch (const VariantData&, int referenceMic);

ArticLayout layoutArticulation (const Articulation&, const ZoneSettings&);

// Zone index for a velocity, or -1.
int zoneForVelocity (const ArticLayout&, int velocity);
} // namespace pd
