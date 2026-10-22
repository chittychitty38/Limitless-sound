#pragma once

#include <juce_core/juce_core.h>
#include <array>

namespace pd
{
// What the engine tells the screen about every hit it plays: which drum, which velocity
// zone and which round robin, so the hit popup, the Lab and the panda can all follow along.
struct HitEvent
{
    enum Flags : juce::uint8 { audition = 1, chromatic = 2, choke = 4 };

    juce::int16 piece = -1, artic = -1, hit = -1;
    juce::int16 zone = -1, zoneCount = 0;       // 0-based zone, number of zones
    juce::int16 round = -1, roundCount = 0;     // 0-based round robin in the zone, number of them
    juce::int16 velocityIn = 0, velocityUsed = 0, note = -1;
    float gainDb = 0.0f;                        // level match + dynamics
    float semis = 0.0f;                         // pitch it played at, relative to natural
    juce::int64 time = 0;                       // engine sample clock at the hit
    juce::uint8 flags = 0;
};

// What the screen asks the engine to play (clicking a drum, auditioning a sample in the Lab).
struct PlayRequest
{
    juce::int16 piece = -1, artic = 0, hit = -1;   // hit -1 = choose as if played from MIDI
    juce::int16 velocity = 100;
    float semis = 0.0f;                            // extra pitch, for previewing the chromatic keys
};

// Single producer, single consumer, no locks, no allocation.
template <typename T, int Size>
class EventFifo
{
public:
    bool push (const T& t)
    {
        auto w = fifo.write (1);
        if (w.blockSize1 > 0) { items[(size_t) w.startIndex1] = t; return true; }
        if (w.blockSize2 > 0) { items[(size_t) w.startIndex2] = t; return true; }
        return false;
    }

    bool pop (T& t)
    {
        auto r = fifo.read (1);
        if (r.blockSize1 > 0) { t = items[(size_t) r.startIndex1]; return true; }
        if (r.blockSize2 > 0) { t = items[(size_t) r.startIndex2]; return true; }
        return false;
    }

    void clear() { fifo.reset(); }

private:
    juce::AbstractFifo fifo { Size };
    std::array<T, (size_t) Size> items {};
};
} // namespace pd
