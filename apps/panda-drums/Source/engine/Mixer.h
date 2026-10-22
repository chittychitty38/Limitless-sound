#pragma once

#include "Sampler.h"
#include <juce_audio_basics/juce_audio_basics.h>

// One channel strip per mic, summed to the stereo output.
namespace pd
{
struct ChannelParams
{
    float gain = 1.0f;       // linear
    float pan = 0.0f;        // -1..1
    bool mute = false, solo = false;
    float panda = 0.0f;      // 0..1 amount of the Panda FX chain
};

struct MixParams
{
    std::array<ChannelParams, maxMics> channels {};
    float master = 1.0f;
    float masterPanda = 0.0f;
};

// The Panda FX chain: a punchy compressor into tape-style saturation, on one knob.
// A stand-in until the real Panda chain is designed; the knob and its place in every
// channel stay the same when it is swapped.
class PandaFx
{
public:
    void prepare (double sampleRate);
    void reset();
    void process (float* L, float* R, int num, float amount);

private:
    double sampleRate = 44100.0;
    float env = 0.0f;
    float attack = 0.0f, release = 0.0f;
    float lowL = 0.0f, lowR = 0.0f;
};

class Mixer
{
public:
    void prepare (double sampleRate, int maxBlock);
    void reset();

    // micBuses: 2 channels per mic. Writes the stereo mix to out (which is cleared first).
    void process (juce::AudioBuffer<float>& micBuses, int numMics, const std::vector<char>& micIsStereo,
                  const MixParams&, juce::AudioBuffer<float>& out, int numSamples);

    // Meters, read by the screen. Peak since the last read, linear.
    float takeChannelPeak (int mic) { return channelPeak[(size_t) mic].exchange (0.0f); }
    float takeMasterPeak (int side) { return masterPeak[(size_t) side].exchange (0.0f); }

private:
    std::array<PandaFx, maxMics> fx;
    PandaFx masterFx;
    std::array<juce::SmoothedValue<float>, maxMics> gainL, gainR;
    juce::SmoothedValue<float> masterGain;
    std::array<std::atomic<float>, maxMics> channelPeak {};
    std::array<std::atomic<float>, 2> masterPeak {};
};
} // namespace pd
