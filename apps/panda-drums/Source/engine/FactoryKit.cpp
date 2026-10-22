#include "FactoryKit.h"
#include "Analysis.h"
#include <juce_audio_basics/juce_audio_basics.h>

namespace pd
{
namespace
{
enum Mic { mKick, mSnareTop, mSnareBottom, mTom1, mTom2, mFloor, mHat, mOH, mRoom, mFar, numMics };

struct VariantSpec
{
    const char* name;
    float size, depth;
    float f0;          // drums: fundamental; cymbals: overall pitch factor
    float decay;       // seconds
    float bright;      // 0..1 colour of the drum itself
};

struct PieceSpec
{
    const char* id;
    const char* name;
    PieceType type;
    float pan;
    int closeMic;      // -1: cymbals live in the overheads
    float ohLevel, roomLevel;
    int defaultVariant;
    float trimDb;      // balances the factory mix (full-force hits peak around -6 dBFS)
    std::vector<VariantSpec> variants;
    std::vector<std::pair<const char*, const char*>> artics;
};

const std::vector<PieceSpec>& specs()
{
    static const std::vector<PieceSpec> s {
        { "kick", "Kick", PieceType::Kick, 0.0f, mKick, 0.22f, 0.55f, 1, -9.0f, {
            { "20\" Bop",        20, 14, 64.0f, 0.24f, 0.75f },
            { "22\" Studio",     22, 16, 53.0f, 0.34f, 0.6f },
            { "24\" Vintage",    24, 14, 46.0f, 0.46f, 0.45f },
            { "26\" Panda Boom", 26, 16, 40.0f, 0.62f, 0.4f } },
          { { "hit", "Hit" } } },
        { "snare", "Snare", PieceType::Snare, 0.18f, mSnareTop, 0.6f, 0.6f, 1, -12.5f, {
            { "13x3.5 Piccolo",  13, 3.5f, 300.0f, 0.10f, 0.9f },
            { "14x5.5 Maple",    14, 5.5f, 205.0f, 0.13f, 0.6f },
            { "14x6.5 Brass",    14, 6.5f, 190.0f, 0.17f, 0.85f },
            { "14x8 Fat Wood",   14, 8.0f, 168.0f, 0.15f, 0.4f } },
          { { "center", "Center" }, { "rim", "Rimshot" }, { "sidestick", "Sidestick" } } },
        { "tom1", "Tom 1", PieceType::Tom, 0.3f, mTom1, 0.4f, 0.5f, 1, -9.5f, {
            { "8\" Rack",  8,  7, 215.0f, 0.30f, 0.6f },
            { "10\" Rack", 10, 8, 178.0f, 0.36f, 0.55f },
            { "12\" Rack", 12, 8, 150.0f, 0.42f, 0.5f } },
          { { "center", "Center" } } },
        { "tom2", "Tom 2", PieceType::Tom, -0.12f, mTom2, 0.4f, 0.5f, 1, -9.5f, {
            { "12\" Rack", 12, 9,  148.0f, 0.42f, 0.5f },
            { "13\" Rack", 13, 10, 132.0f, 0.46f, 0.5f },
            { "14\" Rack", 14, 11, 118.0f, 0.50f, 0.45f } },
          { { "center", "Center" } } },
        { "tom3", "Floor Tom", PieceType::Tom, -0.5f, mFloor, 0.4f, 0.55f, 1, -9.5f, {
            { "14\" Floor", 14, 14, 104.0f, 0.55f, 0.5f },
            { "16\" Floor", 16, 16, 88.0f,  0.64f, 0.45f },
            { "18\" Floor", 18, 16, 76.0f,  0.74f, 0.4f } },
          { { "center", "Center" } } },
        { "hihat", "Hi-Hat", PieceType::HiHat, 0.55f, mHat, 0.7f, 0.35f, 1, -5.5f, {
            { "13\" Bright",  13, 0, 1.12f, 1.0f, 0.9f },
            { "14\" Classic", 14, 0, 1.0f,  1.0f, 0.7f },
            { "15\" Heavy",   15, 0, 0.9f,  1.0f, 0.5f } },
          { { "closed", "Closed" }, { "open", "Open" }, { "pedal", "Pedal" } } },
        { "crash1", "Crash 1", PieceType::Crash, 0.5f, -1, 1.0f, 0.5f, 1, -4.0f, {
            { "16\" Thin",   16, 0, 1.15f, 1.3f, 0.85f },
            { "18\" Medium", 18, 0, 1.0f,  1.7f, 0.7f },
            { "19\" Dark",   19, 0, 0.88f, 2.0f, 0.5f } },
          { { "hit", "Hit" }, { "choke", "Choke" } } },
        { "crash2", "Crash 2", PieceType::Crash, -0.45f, -1, 1.0f, 0.5f, 1, -4.0f, {
            { "18\" Medium",     18, 0, 0.98f, 1.7f, 0.7f },
            { "19\" Dark",       19, 0, 0.86f, 2.0f, 0.5f },
            { "20\" Crash-Ride", 20, 0, 0.8f,  2.4f, 0.55f } },
          { { "hit", "Hit" }, { "choke", "Choke" } } },
        { "ride", "Ride", PieceType::Ride, -0.62f, -1, 1.0f, 0.45f, 1, -5.5f, {
            { "20\" Dry",     20, 0, 1.1f,  1.6f, 0.6f },
            { "21\" Classic", 21, 0, 1.0f,  2.2f, 0.7f },
            { "22\" Washy",   22, 0, 0.92f, 2.8f, 0.8f } },
          { { "bow", "Bow" }, { "bell", "Bell" } } },
        { "china", "China", PieceType::China, -0.8f, -1, 1.0f, 0.5f, 0, -4.0f, {
            { "16\" China", 16, 0, 1.1f, 1.1f, 0.8f },
            { "18\" China", 18, 0, 0.95f, 1.4f, 0.75f } },
          { { "hit", "Hit" } } },
        { "splash", "Splash", PieceType::Splash, 0.32f, -1, 1.0f, 0.45f, 1, -3.5f, {
            { "8\" Splash",  8,  0, 1.35f, 0.55f, 0.9f },
            { "10\" Splash", 10, 0, 1.2f,  0.7f,  0.85f },
            { "12\" Splash", 12, 0, 1.08f, 0.9f,  0.8f } },
          { { "hit", "Hit" } } },
    };
    return s;
}

//==============================================================================
struct Ctx
{
    double sr = FactoryKit::renderRate;
    float vz = 1.0f;       // 0..1, how hard (layer)
    float amp = 1.0f;
    juce::Random rng;
    float jitter (float amount) { return (rng.nextFloat() * 2.0f - 1.0f) * amount; }
    float noise() { return rng.nextFloat() * 2.0f - 1.0f; }
};

struct OnePole
{
    float a = 0.0f, z = 0.0f;
    void lowpass (float hz, double sr) { a = (float) std::exp (-2.0 * juce::MathConstants<double>::pi * hz / sr); }
    float lp (float x) { z = (1.0f - a) * x + a * z; return z; }
    float hp (float x) { return x - lp (x); }
};

struct Biquad
{
    float b0 = 1, b1 = 0, b2 = 0, a1 = 0, a2 = 0, z1 = 0, z2 = 0;
    void bandpass (float hz, float q, double sr)
    {
        auto w = 2.0 * juce::MathConstants<double>::pi * hz / sr;
        auto alpha = std::sin (w) / (2.0 * q);
        auto a0 = 1.0 + alpha;
        b0 = (float) (alpha / a0); b1 = 0.0f; b2 = (float) (-alpha / a0);
        a1 = (float) (-2.0 * std::cos (w) / a0); a2 = (float) ((1.0 - alpha) / a0);
    }
    void highpass (float hz, float q, double sr)
    {
        auto w = 2.0 * juce::MathConstants<double>::pi * hz / sr;
        auto alpha = std::sin (w) / (2.0 * q), c = std::cos (w);
        auto a0 = 1.0 + alpha;
        b0 = (float) ((1.0 + c) / 2.0 / a0); b1 = (float) (-(1.0 + c) / a0); b2 = b0;
        a1 = (float) (-2.0 * c / a0); a2 = (float) ((1.0 - alpha) / a0);
    }
    float process (float x)
    {
        auto y = b0 * x + z1;
        z1 = b1 * x - a1 * y + z2;
        z2 = b2 * x - a2 * y;
        return y;
    }
};

constexpr float twoPi = juce::MathConstants<float>::twoPi;

// A bank of decaying sine partials, run by complex rotation (cheap and exact enough).
struct Partials
{
    struct P { double re, im, cr, ci; float amp; };
    std::vector<P> ps;
    void add (double hz, float amp, double tau, double phase, double sr)
    {
        auto r = std::exp (-1.0 / (tau * sr));
        auto w = 2.0 * juce::MathConstants<double>::pi * hz / sr;
        ps.push_back ({ std::cos (phase), std::sin (phase), r * std::cos (w), r * std::sin (w), amp });
    }
    float next()
    {
        float s = 0.0f;
        for (auto& p : ps)
        {
            auto re = p.re * p.cr - p.im * p.ci;
            auto im = p.re * p.ci + p.im * p.cr;
            p.re = re; p.im = im;
            s += (float) im * p.amp;
        }
        return s;
    }
};

std::vector<float> kick (const VariantSpec& v, Ctx& c)
{
    auto f0 = v.f0 * (1.0f + c.jitter (0.012f));
    auto tau = v.decay * (0.8f + 0.35f * c.vz) * (1.0f + c.jitter (0.05f));
    auto n = (int) (std::min (1.1f, tau * 5.0f + 0.05f) * c.sr);
    std::vector<float> out ((size_t) n);
    OnePole hp;
    hp.lowpass (2500.0f, c.sr);
    auto bend = 1.6f + 2.4f * c.vz * v.bright;
    auto drive = 1.0f + 1.4f * c.vz;
    double ph = 0.0;
    for (int i = 0; i < n; ++i)
    {
        auto t = (float) (i / c.sr);
        auto f = f0 * (1.0f + bend * std::exp (-t / 0.017f));
        ph += twoPi * f / c.sr;
        auto body = (float) std::sin (ph) * std::exp (-t / tau);
        auto click = hp.hp (c.noise()) * std::exp (-t / 0.003f) * (0.15f + 0.7f * c.vz * v.bright);
        auto knock = std::sin (twoPi * 1150.0f * t) * std::exp (-t / 0.006f) * 0.22f * c.vz;
        auto x = body * (1.0f - std::exp (-t / 0.0006f)) + click + knock;
        out[(size_t) i] = std::tanh (x * drive) / std::tanh (drive) * c.amp;
    }
    return out;
}

// Snare: two head modes, the wires, and a ring. Returns top and bottom mic.
std::pair<std::vector<float>, std::vector<float>> snare (const VariantSpec& v, Ctx& c, const juce::String& artic)
{
    auto rim = artic == "rim", stick = artic == "sidestick";
    auto f0 = v.f0 * (1.0f + c.jitter (0.01f));
    auto len = stick ? 0.28f : 0.36f + v.decay * 2.0f;
    auto n = (int) (len * c.sr);
    std::vector<float> top ((size_t) n), bottom ((size_t) n);

    Biquad wires, crackBp, stickBp;
    wires.bandpass (5200.0f + 1800.0f * v.bright, 0.6f, c.sr);
    crackBp.highpass (2800.0f, 0.7f, c.sr);
    stickBp.bandpass (2100.0f + c.jitter (80.0f), 4.0f, c.sr);
    auto wireTau = (0.11f + 0.08f * c.vz) * (0.8f + 0.5f * v.decay / 0.15f) * (1.0f + c.jitter (0.06f));
    auto bodyTau = v.decay * (0.85f + 0.3f * c.vz);
    auto ringHz = f0 * 4.37f;

    for (int i = 0; i < n; ++i)
    {
        auto t = (float) (i / c.sr);
        float x, xb;
        if (stick)
        {
            auto click = stickBp.process (c.noise()) * std::exp (-t / 0.010f) * 2.2f;
            auto wood = std::sin (twoPi * 505.0f * t) * std::exp (-t / 0.028f) * 0.55f
                      + std::sin (twoPi * 1240.0f * t) * std::exp (-t / 0.014f) * 0.35f
                      + std::sin (twoPi * f0 * t) * std::exp (-t / 0.05f) * 0.2f;
            x = (click + wood) * 0.55f;
            xb = x * 0.25f;
        }
        else
        {
            auto bend = 1.0f + 0.45f * std::exp (-t / 0.008f);
            auto m1 = std::sin (twoPi * f0 * bend * t) * std::exp (-t / bodyTau);
            auto m2 = std::sin (twoPi * f0 * 1.59f * t) * std::exp (-t / (bodyTau * 0.55f)) * 0.5f;
            auto m3 = std::sin (twoPi * f0 * 2.14f * t) * std::exp (-t / (bodyTau * 0.4f)) * 0.25f * c.vz;
            auto body = (m1 + m2 + m3) * (rim ? 1.25f : 1.0f);
            auto w = wires.process (c.noise()) * std::exp (-t / wireTau) * (0.9f + 0.7f * c.vz) * (rim ? 0.8f : 1.0f);
            auto crack = crackBp.process (c.noise()) * std::exp (-t / (rim ? 0.007f : 0.0035f)) * (rim ? 1.4f : 0.5f) * (0.3f + 0.7f * c.vz);
            auto ring = std::sin (twoPi * ringHz * t) * std::exp (-t / 0.22f) * 0.06f * v.bright
                      + (rim ? std::sin (twoPi * 905.0f * t) * std::exp (-t / 0.13f) * 0.3f : 0.0f);
            x = (body * 0.8f + w * 1.1f + crack + ring) * 0.55f;
            xb = (body * 0.35f + w * 1.9f + crack * 0.4f) * 0.25f;
        }
        auto fadeIn = 1.0f - std::exp (-t / 0.0004f);
        top[(size_t) i] = std::tanh (x * fadeIn * 1.4f) / std::tanh (1.4f) * c.amp;
        bottom[(size_t) i] = std::tanh (xb * fadeIn * 1.2f) / std::tanh (1.2f) * c.amp;
    }
    return { top, bottom };
}

std::vector<float> tom (const VariantSpec& v, Ctx& c)
{
    auto f0 = v.f0 * (1.0f + c.jitter (0.01f));
    auto tau = v.decay * (0.8f + 0.35f * c.vz) * (1.0f + c.jitter (0.05f));
    auto n = (int) (std::min (1.6f, tau * 3.2f + 0.05f) * c.sr);
    std::vector<float> out ((size_t) n);
    Biquad stick;
    stick.bandpass (1300.0f, 1.2f, c.sr);
    double ph = 0.0, ph2 = 0.0;
    for (int i = 0; i < n; ++i)
    {
        auto t = (float) (i / c.sr);
        auto f = f0 * (1.0f + (0.25f + 0.25f * c.vz) * std::exp (-t / 0.045f));
        ph += twoPi * f / c.sr;
        ph2 += twoPi * f * 1.52f / c.sr;
        auto body = (float) std::sin (ph) * std::exp (-t / tau) + (float) std::sin (ph2) * std::exp (-t / (tau * 0.35f)) * 0.3f;
        auto hit = stick.process (c.noise()) * std::exp (-t / 0.007f) * (0.25f + 0.6f * c.vz);
        auto x = body * (1.0f - std::exp (-t / 0.0005f)) + hit;
        out[(size_t) i] = std::tanh (x * 1.3f) / std::tanh (1.3f) * c.amp;
    }
    return out;
}

// Cymbals: dozens of inharmonic partials (fixed per cymbal) plus shaped noise.
std::vector<float> cymbal (const PieceSpec& ps, const VariantSpec& v, int variantIndex, Ctx& c, const juce::String& artic)
{
    auto type = ps.type;
    auto pitch = v.f0;
    juce::Random fixed ((juce::int64) (std::hash<std::string>{} (std::string (ps.id)) + (size_t) variantIndex * 7919));

    float tau = v.decay * (0.75f + 0.45f * c.vz) * (1.0f + c.jitter (0.06f));
    float noiseAmt = 0.55f, noiseHp = 4500.0f, partialAmt = 1.0f;
    float lo = 420.0f, hi = 12500.0f;
    int count = 44;
    float attackNoise = 0.6f;

    bool closedHat = false, pedalHat = false, openHat = false, bell = false, bow = false;
    if (type == PieceType::HiHat)
    {
        closedHat = artic == "closed";
        pedalHat = artic == "pedal";
        openHat = artic == "open";
        tau = closedHat ? 0.05f + 0.03f * c.vz : pedalHat ? 0.035f : 0.55f + 0.2f * c.vz;
        lo = 3000.0f; hi = 14000.0f; noiseHp = 6500.0f; noiseAmt = 0.9f; count = 30;
    }
    else if (type == PieceType::Ride)
    {
        bell = artic == "bell";
        bow = ! bell;
        if (bell) { lo = 650.0f; hi = 6000.0f; count = 14; noiseAmt = 0.1f; tau *= 1.1f; }
        else      { noiseAmt = 0.3f; attackNoise = 0.35f; }
    }
    else if (type == PieceType::China)
    {
        noiseAmt = 0.9f; lo = 500.0f; hi = 9000.0f; count = 60; noiseHp = 3000.0f;
    }
    else if (type == PieceType::Splash)
    {
        lo = 900.0f; hi = 14000.0f;
    }

    auto len = std::min (type == PieceType::Ride ? 2.4f : 2.2f, tau * 3.2f + 0.08f);
    auto n = (int) (len * c.sr);
    std::vector<float> out ((size_t) n);

    Partials bank;
    for (int k = 0; k < count; ++k)
    {
        auto f = lo * std::pow (hi / lo, fixed.nextFloat()) * pitch;
        if (bell)
        {
            static const float bellRatios[] = { 1.0f, 2.32f, 3.51f, 4.88f, 5.3f, 6.94f };
            f = 720.0f * pitch * bellRatios[k % 6] * (1.0f + 0.004f * (float) (k / 6));
        }
        if (f > c.sr * 0.45)
            continue;
        auto a = (0.4f + 0.6f * fixed.nextFloat()) / std::sqrt (f / 1000.0f);
        a *= std::pow (f / 2000.0f, (c.vz * 0.9f - 0.45f));     // harder hits are brighter
        auto partTau = tau * std::pow (1000.0f / f, bell ? 0.15f : 0.45f);
        if (bow && f > 2500.0f && f < 6500.0f)
            a *= 1.6f;                                             // the "ping" of the bow
        bank.add (f, a, partTau, c.rng.nextFloat() * twoPi, c.sr);
    }

    OnePole hp, lpNoise;
    hp.lowpass (noiseHp, c.sr);
    Biquad pedalBp;
    pedalBp.bandpass (3400.0f, 1.5f, c.sr);
    float norm = 0.0f;
    for (auto& p : bank.ps) norm += p.amp;
    norm = norm > 0.0f ? 2.6f / norm : 0.0f;

    for (int i = 0; i < n; ++i)
    {
        auto t = (float) (i / c.sr);
        // The noise gets darker as the cymbal settles.
        lpNoise.lowpass (4000.0f + 11000.0f * std::exp (-t / (0.25f * tau + 0.02f)) * (0.5f + 0.5f * c.vz), c.sr);
        auto nz = hp.hp (c.noise());
        nz = lpNoise.lp (nz);
        auto swell = openHat ? (1.0f - 0.25f * std::exp (-t / 0.03f)) : 1.0f;
        auto x = bank.next() * norm * partialAmt
               + nz * noiseAmt * std::exp (-t / (tau * 0.7f)) * swell
               + nz * attackNoise * std::exp (-t / 0.012f) * c.vz;
        if (pedalHat)
            x = x * 0.5f + pedalBp.process (c.noise()) * std::exp (-t / 0.018f) * 1.4f;
        if (type == PieceType::China)
            x = std::tanh (x * 2.2f) * 0.7f;
        x *= 1.0f - std::exp (-t / 0.0003f);
        out[(size_t) i] = x * c.amp * (type == PieceType::HiHat ? 0.55f : 0.42f);
    }
    return out;
}

//==============================================================================
void trimTail (std::vector<float>& x, float relDb = -50.0f)
{
    float peak = 0.0f;
    for (auto v : x) peak = std::max (peak, std::abs (v));
    if (peak <= 0.0f) { x.clear(); return; }
    auto thr = peak * juce::Decibels::decibelsToGain (relDb);
    auto last = (int) x.size() - 1;
    while (last > 0 && std::abs (x[(size_t) last]) < thr) --last;
    auto keep = std::min ((int) x.size(), last + 256);
    x.resize ((size_t) keep);
    auto fade = std::min (256, keep);
    for (int i = 0; i < fade; ++i)
        x[(size_t) (keep - 1 - i)] *= (float) i / (float) fade;
}

std::vector<float> overhead (const std::vector<float>& dry, float level, double sr, bool cymbal)
{
    auto delay = (int) (0.0028 * sr);
    std::vector<float> out (dry.size() + (size_t) delay, 0.0f);
    Biquad hp;
    hp.highpass (cymbal ? 200.0f : 450.0f, 0.7f, sr);
    OnePole air;
    air.lowpass (13000.0f, sr);
    for (size_t i = 0; i < dry.size(); ++i)
        out[i + (size_t) delay] = air.lp (hp.process (dry[i])) * level;
    return out;
}

std::vector<float> room (const std::vector<float>& dry, float level, bool far, double sr)
{
    juce::Reverb verb;
    juce::Reverb::Parameters p;
    p.roomSize = far ? 0.82f : 0.5f;
    p.damping = far ? 0.55f : 0.35f;
    p.wetLevel = 1.0f;
    p.dryLevel = 0.0f;
    p.width = 0.0f;
    verb.setParameters (p);
    verb.setSampleRate (sr);

    auto pre = (int) ((far ? 0.024 : 0.009) * sr);
    auto tail = (int) ((far ? 0.9 : 0.55) * sr);
    std::vector<float> buf (dry.size() + (size_t) (pre + tail), 0.0f);
    for (size_t i = 0; i < dry.size(); ++i)
        buf[i + (size_t) pre] = dry[i];
    verb.processMono (buf.data(), (int) buf.size());

    OnePole lp;
    lp.lowpass (far ? 5500.0f : 9000.0f, sr);
    // A little of the direct sound arrives too, later and duller for the far mics.
    for (size_t i = 0; i < buf.size(); ++i)
    {
        auto j = i - (size_t) pre;
        auto direct = i >= (size_t) pre && j < dry.size() ? dry[j] * (far ? 0.12f : 0.3f) : 0.0f;
        buf[i] = lp.lp (buf[i] * 0.55f + direct) * level;
    }
    trimTail (buf, -45.0f);
    return buf;
}

SampleBuffer toBuffer (std::vector<float> x)
{
    if (x.empty())
        return nullptr;
    auto b = std::make_shared<juce::AudioBuffer<float>> (1, (int) x.size());
    std::copy (x.begin(), x.end(), b->getWritePointer (0));
    return b;
}
} // namespace

//==============================================================================
std::shared_ptr<Kit> FactoryKit::create()
{
    auto kit = std::make_shared<Kit>();
    kit->name = "Panda Factory Kit";
    kit->isFactory = true;
    kit->mics = {
        { "kickin", "Kick In", MicGroup::Close },
        { "snaretop", "Snare Top", MicGroup::Close },
        { "snarebottom", "Snare Bottom", MicGroup::Close },
        { "tom1", "Tom 1", MicGroup::Close },
        { "tom2", "Tom 2", MicGroup::Close },
        { "floortom", "Floor Tom", MicGroup::Close },
        { "hihat", "Hi-Hat", MicGroup::Close },
        { "overheads", "Overheads", MicGroup::Overhead },
        { "room", "Room", MicGroup::RoomClose },
        { "farroom", "Far Room", MicGroup::RoomFar },
    };
    auto& all = specs();
    for (size_t p = 0; p < all.size(); ++p)
    {
        auto& s = all[p];
        Piece piece;
        piece.id = s.id;
        piece.name = s.name;
        piece.type = s.type;
        piece.pan = s.pan;
        piece.referenceMic = s.closeMic >= 0 ? s.closeMic : mOH;
        for (size_t v = 0; v < s.variants.size(); ++v)
        {
            Variant var;
            var.name = s.variants[v].name;
            var.sizeInches = s.variants[v].size;
            var.depthInches = s.variants[v].depth;
            var.naturalHz = isTunable (s.type) ? s.variants[v].f0 : 0.0f;
            var.factoryId = (int) (p * 100 + v);
            piece.variants.push_back (var);
        }
        kit->pieces.push_back (piece);
    }
    return kit;
}

int FactoryKit::defaultVariant (const Kit& kit, int piece)
{
    if (! kit.isFactory || ! juce::isPositiveAndBelow (piece, (int) specs().size()))
        return 0;
    return specs()[(size_t) piece].defaultVariant;
}

std::shared_ptr<const VariantData> FactoryKit::render (const Kit& kit, int pieceIndex, int variantIndex)
{
    auto& all = specs();
    if (! juce::isPositiveAndBelow (pieceIndex, (int) all.size()) || ! juce::isPositiveAndBelow (pieceIndex, (int) kit.pieces.size()))
        return nullptr;
    auto& ps = all[(size_t) pieceIndex];
    if (! juce::isPositiveAndBelow (variantIndex, (int) ps.variants.size()))
        return nullptr;
    auto& vs = ps.variants[(size_t) variantIndex];

    auto data = std::make_shared<VariantData>();
    for (auto& [id, name] : ps.artics)
    {
        Articulation a;
        a.id = id;
        a.name = name;
        a.isOpen = juce::String (id) == "open";
        a.closes = ps.type == PieceType::HiHat && (juce::String (id) == "closed" || juce::String (id) == "pedal");
        a.chokesAll = juce::String (id) == "choke";
        if (a.chokesAll)
        {
            data->artics.push_back (a);   // a grab: no sound of its own
            continue;
        }

        for (int layer = 0; layer < layers; ++layer)
            for (int round = 0; round < rounds; ++round)
            {
                Ctx c;
                c.rng.setSeed ((juce::int64) (pieceIndex * 1000003 + variantIndex * 10007 + layer * 101 + round * 7 + (int) std::hash<std::string>{} (id) % 997));
                c.vz = (float) (layer + 1) / (float) layers;
                auto layerDb = -27.0f + 24.0f * std::pow (c.vz, 0.85f) + c.jitter (0.8f) + ps.trimDb;   // 3 dB of headroom for stacked hits
                c.amp = juce::Decibels::decibelsToGain (layerDb);
                if (juce::String (id) == "pedal") c.amp *= 0.55f;
                if (juce::String (id) == "sidestick") c.amp *= 0.8f;

                std::vector<float> close, bottom, dry;
                switch (ps.type)
                {
                    case PieceType::Kick:  close = kick (vs, c); break;
                    case PieceType::Snare: { auto tb = snare (vs, c, id); close = tb.first; bottom = tb.second; break; }
                    case PieceType::Tom:   close = tom (vs, c); break;
                    case PieceType::HiHat:
                    case PieceType::Crash:
                    case PieceType::Ride:
                    case PieceType::China:
                    case PieceType::Splash:
                    case PieceType::Perc:  dry = cymbal (ps, vs, variantIndex, c, id); break;
                }
                auto isCym = isCymbal (ps.type);
                if (! isCym)
                    dry = close;
                if (ps.type == PieceType::HiHat)
                    close = dry;

                Hit h;
                h.sampleRate = renderRate;
                h.mics.resize (kit.mics.size());
                h.fileLayer = layer + 1;
                h.fileRR = round + 1;
                h.name = juce::String (ps.name) + " " + vs.name + " " + a.name + " v" + juce::String (layer + 1) + " rr" + juce::String (round + 1);

                auto oh = overhead (dry, ps.ohLevel, renderRate, isCym);
                auto rm = room (dry, ps.roomLevel, false, renderRate);
                // Cymbals are left out of the far room to keep the factory kit small; the drums carry it.
                auto fr = isCym && ps.type != PieceType::HiHat ? std::vector<float>() : room (dry, ps.roomLevel * 0.9f, true, renderRate);
                trimTail (oh);
                if (ps.closeMic >= 0)
                {
                    trimTail (close);
                    h.mics[(size_t) ps.closeMic] = toBuffer (close);
                }
                if (! bottom.empty())
                {
                    trimTail (bottom);
                    h.mics[mSnareBottom] = toBuffer (bottom);
                }
                h.mics[mOH] = toBuffer (oh);
                h.mics[mRoom] = toBuffer (rm);
                h.mics[mFar] = toBuffer (fr);

                for (auto& m : h.mics)
                    if (m != nullptr)
                        data->bytes += (size_t) m->getNumSamples() * sizeof (float);
                measureHit (h, ps.closeMic >= 0 ? ps.closeMic : mOH);
                a.hits.push_back (std::move (h));
            }
        data->artics.push_back (std::move (a));
    }
    return data;
}
} // namespace pd
