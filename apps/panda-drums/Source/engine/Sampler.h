#pragma once

#include "Analysis.h"
#include "Events.h"
#include "Mapping.h"
#include "Tuning.h"
#include <juce_audio_basics/juce_audio_basics.h>

namespace pd
{
constexpr int maxPieces = 16;
constexpr int maxMics = 16;

// Everything the audio thread needs to play the kit, built on the message thread and handed
// over whole. Nothing in here changes after it is published, except the round robin counters,
// which only the audio thread touches.
struct EngineSnapshot
{
    struct PieceRT
    {
        PieceType type = PieceType::Perc;
        int variant = 0;
        std::shared_ptr<const VariantData> data;          // null while loading
        std::vector<ArticLayout> layouts;                  // one per articulation
        std::vector<std::vector<char>> disabled;           // marked bad, per articulation per hit
        float naturalMidi = 48.0f;                         // pitch before tuning
        float pan = 0.0f;
    };

    std::shared_ptr<const Kit> kit;
    std::vector<PieceRT> pieces;
    std::array<ResolvedNote, 128> notes {};
    std::vector<char> micIsStereo;                         // per mic: false = a mono close mic

    bool chromaticOn = false;
    int chromaticPiece = -1, chromaticLow = 72, chromaticHigh = 95;
    bool chromaticSnap = true;
    Key key;

    juce::uint32 generation = 0;

    // Audio thread only: next round robin per piece / articulation / zone, and the last one used.
    mutable std::vector<std::vector<std::vector<int>>> rrNext, rrLast;
    void prepareCounters() const;
};

// Hands a snapshot from the message thread to the audio thread without locks, and frees old
// ones on the message thread once the audio thread has moved on.
class SnapshotExchange
{
public:
    void publish (std::shared_ptr<const EngineSnapshot>);   // message thread
    const EngineSnapshot* acquire();                         // audio thread, once per block
    void collectGarbage();                                   // message thread
    std::shared_ptr<const EngineSnapshot> latest() const;    // message thread

private:
    std::vector<std::shared_ptr<const EngineSnapshot>> alive;
    std::atomic<const EngineSnapshot*> newest { nullptr };
    std::atomic<const EngineSnapshot*> inUse { nullptr };
    std::atomic<bool> reading { false };
    std::shared_ptr<const EngineSnapshot> latestShared;
};

struct PieceParams { float gain = 1.0f; float semis = 0.0f; float decay = 1.0f; };

struct EngineParams
{
    std::array<PieceParams, maxPieces> pieces {};
    std::array<std::array<float, maxMics>, maxPieces> bleed {};   // linear gain of each drum in each mic
    float velocityCurve = 0.0f;                                   // -1 soft ... +1 hard
    float dynamics = 1.0f;                                        // 0..1 velocity build inside a zone
    float humanize = 0.0f;                                        // 0..1 random velocity
    int rrMode = 0;                                               // 0 cycle, 1 random no repeat, 2 random
};

class Sampler
{
public:
    Sampler();

    void prepare (double sampleRate, int maxBlock);
    void reset();

    // Renders the hits into one stereo buffer per mic (micBuses has 2 * maxMics channels).
    void process (const EngineSnapshot&, const EngineParams&, const juce::MidiBuffer&,
                  juce::AudioBuffer<float>& micBuses, int numSamples, juce::int64 clock,
                  EventFifo<PlayRequest, 64>& requests, EventFifo<HitEvent, 1024>& events);

    int activeVoices() const { return numActive; }

    // Shared with the tests.
    static float curveVelocity (int velocity, float curve);
    static float dynamicsGainDb (const ArticLayout&, int zone, float velocity, float amount);

private:
    struct Voice
    {
        bool active = false;
        int piece = -1, artic = -1;
        const Hit* hit = nullptr;
        double pos = 0.0, rate = 1.0;
        float gain = 1.0f;
        float fade = 1.0f, fadeStep = 0.0f;               // fadeStep > 0 while being choked or stolen
        float env = 1.0f, envCoef = 1.0f;
        int envDelay = 0;
        bool isOpen = false;
        juce::uint32 order = 0;
        float panL = 1.0f, panR = 1.0f;
    };

    void startHit (const EngineSnapshot&, const EngineParams&, int piece, int artic, int hitOverride,
                   int velocity, float extraSemis, int note, juce::int64 time, juce::uint8 flags,
                   EventFifo<HitEvent, 1024>&);
    void chokePiece (int piece, bool onlyOpen, float seconds);
    Voice& allocateVoice (int piece);
    void renderVoice (Voice&, const EngineSnapshot&, const EngineParams&, juce::AudioBuffer<float>&, int start, int num);

    std::vector<Voice> voices;
    double sampleRate = 44100.0;
    juce::uint32 orderCounter = 0;
    int numActive = 0;
    juce::Random random;
    juce::uint32 lastGeneration = 0;
    const Kit* lastKit = nullptr;
};
} // namespace pd
