#include "Mixer.h"

namespace pd
{
void PandaFx::prepare (double sr)
{
    sampleRate = sr;
    attack = (float) std::exp (-1.0 / (0.004 * sr));
    release = (float) std::exp (-1.0 / (0.12 * sr));
    reset();
}

void PandaFx::reset()
{
    env = 0.0f;
    lowL = lowR = 0.0f;
}

void PandaFx::process (float* L, float* R, int num, float amount)
{
    if (amount <= 0.001f)
        return;

    // Compressor: threshold falls and ratio rises with the knob; stereo linked.
    auto thresholdDb = -6.0f - 20.0f * amount;
    auto ratio = 1.0f + 5.0f * amount;
    auto makeupDb = -thresholdDb * (1.0f - 1.0f / ratio) * 0.45f;
    auto makeup = juce::Decibels::decibelsToGain (makeupDb);

    // Saturation: drive into tanh with unity gain for quiet signals, plus a little low-end weight.
    auto drive = 1.0f + 3.0f * amount;
    auto outGain = (1.0f + 0.5f * amount) / drive;
    auto lowCoef = (float) std::exp (-2.0 * juce::MathConstants<double>::pi * 120.0 / sampleRate);
    auto lowBoost = 0.35f * amount;

    for (int i = 0; i < num; ++i)
    {
        auto l = L[i], r = R[i];
        auto level = std::max (std::abs (l), std::abs (r));
        env = level > env ? attack * env + (1.0f - attack) * level : release * env + (1.0f - release) * level;
        auto envDb = juce::Decibels::gainToDecibels (env, -100.0f);
        auto overDb = envDb - thresholdDb;
        auto gain = overDb > 0.0f ? juce::Decibels::decibelsToGain (-overDb * (1.0f - 1.0f / ratio)) : 1.0f;
        l *= gain * makeup;
        r *= gain * makeup;

        lowL = lowCoef * lowL + (1.0f - lowCoef) * l;
        lowR = lowCoef * lowR + (1.0f - lowCoef) * r;
        l += lowL * lowBoost;
        r += lowR * lowBoost;

        L[i] = std::tanh (l * drive) * outGain;
        R[i] = std::tanh (r * drive) * outGain;
    }
}

void Mixer::prepare (double sampleRate, int)
{
    for (auto& f : fx)
        f.prepare (sampleRate);
    masterFx.prepare (sampleRate);
    for (int i = 0; i < maxMics; ++i)
    {
        gainL[(size_t) i].reset (sampleRate, 0.02);
        gainR[(size_t) i].reset (sampleRate, 0.02);
    }
    masterGain.reset (sampleRate, 0.02);
}

void Mixer::reset()
{
    for (auto& f : fx)
        f.reset();
    masterFx.reset();
}

void Mixer::process (juce::AudioBuffer<float>& buses, int numMics, const std::vector<char>& micIsStereo,
                     const MixParams& p, juce::AudioBuffer<float>& out, int num)
{
    out.clear (0, num);
    auto* outL = out.getWritePointer (0);
    auto* outR = out.getWritePointer (out.getNumChannels() > 1 ? 1 : 0);

    bool anySolo = false;
    for (int m = 0; m < numMics; ++m)
        anySolo = anySolo || p.channels[(size_t) m].solo;

    for (int m = 0; m < std::min (numMics, maxMics); ++m)
    {
        auto& c = p.channels[(size_t) m];
        auto audible = ! c.mute && (! anySolo || c.solo);
        auto stereo = juce::isPositiveAndBelow (m, (int) micIsStereo.size()) && micIsStereo[(size_t) m] != 0;

        // Mono close mics pan with constant power; stereo mics balance.
        float gl, gr;
        if (stereo)
        {
            gl = std::min (1.0f, 1.0f - c.pan);
            gr = std::min (1.0f, 1.0f + c.pan);
        }
        else
        {
            auto angle = (c.pan + 1.0f) * juce::MathConstants<float>::pi * 0.25f;
            gl = std::cos (angle) * juce::MathConstants<float>::sqrt2;
            gr = std::sin (angle) * juce::MathConstants<float>::sqrt2;
            gl = std::min (gl, 1.0f);
            gr = std::min (gr, 1.0f);
        }
        auto target = audible ? c.gain : 0.0f;
        gainL[(size_t) m].setTargetValue (target * gl);
        gainR[(size_t) m].setTargetValue (target * gr);

        auto* L = buses.getWritePointer (2 * m);
        auto* R = buses.getWritePointer (2 * m + 1);
        fx[(size_t) m].process (L, R, num, c.panda);

        float peak = 0.0f;
        for (int i = 0; i < num; ++i)
        {
            auto a = gainL[(size_t) m].getNextValue(), b = gainR[(size_t) m].getNextValue();
            auto l = L[i] * a, r = R[i] * b;
            outL[i] += l;
            if (outR != outL) outR[i] += r;
            peak = std::max (peak, std::max (std::abs (l), std::abs (r)));
        }
        auto& slot = channelPeak[(size_t) m];
        auto prev = slot.load();
        while (peak > prev && ! slot.compare_exchange_weak (prev, peak)) {}
    }

    masterFx.process (outL, outR, num, p.masterPanda);
    masterGain.setTargetValue (p.master);
    // Safety: anything that would clip is rounded off just under 0 dBFS; below -1 dBFS it's untouched.
    auto safe = [] (float x)
    {
        auto a = std::abs (x);
        if (a <= 0.89f) return x;
        return std::copysign (0.89f + 0.11f * std::tanh ((a - 0.89f) / 0.11f), x);
    };
    float pl = 0.0f, pr = 0.0f;
    for (int i = 0; i < num; ++i)
    {
        auto g = masterGain.getNextValue();
        outL[i] = safe (outL[i] * g);
        if (outR != outL) outR[i] = safe (outR[i] * g);
        pl = std::max (pl, std::abs (outL[i]));
        pr = std::max (pr, std::abs (outR[i]));
    }
    for (int s = 0; s < 2; ++s)
    {
        auto v = s == 0 ? pl : pr;
        auto prev = masterPeak[(size_t) s].load();
        while (v > prev && ! masterPeak[(size_t) s].compare_exchange_weak (prev, v)) {}
    }
}
} // namespace pd
