#include "Sampler.h"

namespace pd
{
//==============================================================================
void EngineSnapshot::prepareCounters() const
{
    rrNext.assign (pieces.size(), {});
    rrLast.assign (pieces.size(), {});
    for (size_t p = 0; p < pieces.size(); ++p)
    {
        auto& layouts = pieces[p].layouts;
        rrNext[p].resize (layouts.size());
        rrLast[p].resize (layouts.size());
        for (size_t a = 0; a < layouts.size(); ++a)
        {
            rrNext[p][a].assign (layouts[a].zones.size(), 0);
            rrLast[p][a].assign (layouts[a].zones.size(), -1);
        }
    }
}

//==============================================================================
void SnapshotExchange::publish (std::shared_ptr<const EngineSnapshot> s)
{
    alive.push_back (s);
    latestShared = s;
    newest.store (s.get());
    collectGarbage();
}

const EngineSnapshot* SnapshotExchange::acquire()
{
    reading.store (true);
    auto* p = newest.load();
    inUse.store (p);
    reading.store (false);
    return p;
}

void SnapshotExchange::collectGarbage()
{
    if (reading.load())
        return;
    auto* used = inUse.load();
    auto* fresh = newest.load();
    if (reading.load())
        return;
    alive.erase (std::remove_if (alive.begin(), alive.end(), [&] (auto& s) { return s.get() != used && s.get() != fresh; }),
                 alive.end());
}

std::shared_ptr<const EngineSnapshot> SnapshotExchange::latest() const { return latestShared; }

//==============================================================================
Sampler::Sampler() { voices.resize (160); }

void Sampler::prepare (double sr, int)
{
    sampleRate = sr;
    reset();
}

void Sampler::reset()
{
    for (auto& v : voices)
        v.active = false;
    numActive = 0;
}

float Sampler::curveVelocity (int velocity, float curve)
{
    auto v = juce::jlimit (1, 127, velocity) / 127.0f;
    // curve > 0: soft playing comes out louder ("hard" kit); curve < 0: you have to dig in.
    auto exponent = std::pow (2.0f, -curve * 1.2f);
    return juce::jlimit (1.0f, 127.0f, 127.0f * std::pow (v, exponent));
}

float Sampler::dynamicsGainDb (const ArticLayout& l, int zone, float velocity, float amount)
{
    if (! juce::isPositiveAndBelow (zone, (int) l.zones.size()))
        return 0.0f;
    auto& z = l.zones[(size_t) zone];
    auto span = (float) std::max (1, z.hi - z.lo);
    auto frac = juce::jlimit (0.0f, 1.0f, (velocity - (float) z.lo) / span);

    // How far below this zone's level the bottom of the lane sits: down to the zone under it,
    // so walking up the velocities is one smooth build instead of steps.
    float rangeDb;
    if (l.zones.size() == 1)
        rangeDb = 30.0f * (1.0f - (float) z.lo / 127.0f) + 6.0f;
    else if (zone > 0)
        rangeDb = juce::jlimit (1.5f, 12.0f, z.refDb - l.zones[(size_t) zone - 1].refDb);
    else
        rangeDb = 8.0f;
    return -(1.0f - frac) * rangeDb * amount;
}

void Sampler::chokePiece (int piece, bool onlyOpen, float seconds)
{
    auto step = 1.0f / std::max (1.0f, (float) (seconds * sampleRate));
    for (auto& v : voices)
        if (v.active && v.piece == piece && (! onlyOpen || v.isOpen))
            v.fadeStep = std::max (v.fadeStep, step);
}

Sampler::Voice& Sampler::allocateVoice (int piece)
{
    // Each drum keeps a handful of hits ringing; past that the oldest one fades out quickly.
    int count = 0;
    Voice* oldestOfPiece = nullptr;
    for (auto& v : voices)
        if (v.active && v.piece == piece && v.fadeStep <= 0.0f)
        {
            ++count;
            if (oldestOfPiece == nullptr || v.order < oldestOfPiece->order)
                oldestOfPiece = &v;
        }
    if (count >= 10 && oldestOfPiece != nullptr)
        oldestOfPiece->fadeStep = 1.0f / (float) (0.006 * sampleRate);

    for (auto& v : voices)
        if (! v.active)
            return v;

    // Full: take the oldest, preferring one already fading out.
    Voice* best = &voices.front();
    for (auto& v : voices)
    {
        auto bestFading = best->fadeStep > 0.0f, fading = v.fadeStep > 0.0f;
        if ((fading && ! bestFading) || (fading == bestFading && v.order < best->order))
            best = &v;
    }
    return *best;
}

void Sampler::startHit (const EngineSnapshot& snap, const EngineParams& params, int piece, int artic, int hitOverride,
                        int velocity, float extraSemis, int note, juce::int64 time, juce::uint8 flags,
                        EventFifo<HitEvent, 1024>& events)
{
    if (! juce::isPositiveAndBelow (piece, (int) snap.pieces.size()))
        return;
    auto& prt = snap.pieces[(size_t) piece];
    if (prt.data == nullptr || ! juce::isPositiveAndBelow (artic, (int) prt.data->artics.size()))
        return;
    auto& art = prt.data->artics[(size_t) artic];
    auto& lay = prt.layouts[(size_t) artic];

    if (art.chokesAll)
        chokePiece (piece, false, 0.012f);
    if (art.closes)
        chokePiece (piece, true, 0.035f);
    if (art.hits.empty() || lay.zones.empty())
    {
        if (art.chokesAll)
        {
            HitEvent e;
            e.piece = (juce::int16) piece; e.artic = (juce::int16) artic; e.note = (juce::int16) note;
            e.time = time; e.flags = (juce::uint8) (flags | HitEvent::choke);
            events.push (e);
        }
        return;
    }

    auto curved = curveVelocity (velocity, params.velocityCurve);
    if (params.humanize > 0.0f && hitOverride < 0)
        curved = juce::jlimit (1.0f, 127.0f, curved + (random.nextFloat() * 2.0f - 1.0f) * 14.0f * params.humanize);

    auto& disabled = prt.disabled[(size_t) artic];
    auto enabled = [&] (int h) { return ! juce::isPositiveAndBelow (h, (int) disabled.size()) || disabled[(size_t) h] == 0; };

    int zone = -1, chosen = -1;
    if (hitOverride >= 0 && hitOverride < (int) art.hits.size())
    {
        chosen = hitOverride;
        zone = lay.hitZone[(size_t) chosen];
    }
    else
    {
        auto wanted = zoneForVelocity (lay, (int) std::lround (curved));
        auto zones = (int) lay.zones.size();
        auto& next = snap.rrNext[(size_t) piece][(size_t) artic];
        auto& last = snap.rrLast[(size_t) piece][(size_t) artic];

        // The zone the velocity asks for; if every sample in it is marked bad, the nearest one that isn't.
        for (int d = 0; d < zones && chosen < 0; ++d)
            for (int zz : { wanted - d, wanted + d })
            {
                if (! juce::isPositiveAndBelow (zz, zones) || chosen >= 0)
                    continue;
                auto& hits = lay.zones[(size_t) zz].hits;
                auto n = (int) hits.size();
                int pick = -1;
                if (params.rrMode == 0)
                {
                    for (int k = 0; k < n; ++k)
                    {
                        auto idx = (next[(size_t) zz] + k) % n;
                        if (enabled (hits[(size_t) idx])) { pick = idx; break; }
                    }
                }
                else
                {
                    int options[64];
                    int count = 0;
                    for (int k = 0; k < n && count < 64; ++k)
                        if (enabled (hits[(size_t) k]) && (params.rrMode == 2 || k != last[(size_t) zz] || n == 1))
                            options[count++] = k;
                    if (count == 0)
                        for (int k = 0; k < n && count < 64; ++k)
                            if (enabled (hits[(size_t) k])) options[count++] = k;
                    if (count > 0)
                        pick = options[random.nextInt (count)];
                }
                if (pick >= 0)
                {
                    zone = zz;
                    chosen = hits[(size_t) pick];
                    next[(size_t) zz] = (pick + 1) % n;
                    last[(size_t) zz] = pick;
                }
            }
    }
    if (chosen < 0)
        return;

    auto& hit = art.hits[(size_t) chosen];
    auto& pp = params.pieces[(size_t) std::min (piece, maxPieces - 1)];
    auto gainDb = juce::Decibels::gainToDecibels (lay.hitGain[(size_t) chosen])
                + (hitOverride >= 0 ? 0.0f : dynamicsGainDb (lay, zone, curved, params.dynamics));
    auto semis = juce::jlimit (-24.0f, 24.0f, pp.semis + extraSemis);

    auto& v = allocateVoice (piece);
    v.active = true;
    v.piece = piece;
    v.artic = artic;
    v.hit = &hit;
    v.pos = 0.0;
    v.rate = hit.sampleRate / sampleRate * std::pow (2.0, (double) semis / 12.0);
    v.gain = juce::Decibels::decibelsToGain (gainDb) * pp.gain;
    v.fade = 1.0f;
    v.fadeStep = 0.0f;
    v.isOpen = art.isOpen;
    v.order = ++orderCounter;
    v.panL = std::min (1.0f, 1.0f - prt.pan);
    v.panR = std::min (1.0f, 1.0f + prt.pan);
    v.env = 1.0f;
    if (pp.decay < 0.999f)
    {
        // Shorter decay: let the attack through, then close it down.
        auto tau = 0.03 + 2.5 * std::pow ((double) pp.decay, 2.5);
        v.envDelay = (int) (0.02 * sampleRate);
        v.envCoef = (float) std::exp (-1.0 / (tau * sampleRate));
    }
    else
    {
        v.envDelay = 0;
        v.envCoef = 1.0f;
    }

    HitEvent e;
    e.piece = (juce::int16) piece;
    e.artic = (juce::int16) artic;
    e.hit = (juce::int16) chosen;
    e.zone = (juce::int16) zone;
    e.zoneCount = (juce::int16) lay.zones.size();
    e.round = (juce::int16) lay.hitRound[(size_t) chosen];
    e.roundCount = (juce::int16) lay.zones[(size_t) zone].hits.size();
    e.velocityIn = (juce::int16) velocity;
    e.velocityUsed = (juce::int16) std::lround (curved);
    e.note = (juce::int16) note;
    e.gainDb = gainDb;
    e.semis = semis;
    e.time = time;
    e.flags = flags;
    events.push (e);
}

namespace
{
inline float hermite (const float* d, int len, double pos)
{
    auto i = (int) pos;
    auto f = (float) (pos - (double) i);
    auto xm1 = i > 0 ? d[i - 1] : 0.0f;
    auto x0 = d[i];
    auto x1 = i + 1 < len ? d[i + 1] : 0.0f;
    auto x2 = i + 2 < len ? d[i + 2] : 0.0f;
    auto c = (x1 - xm1) * 0.5f;
    auto v = x0 - x1;
    auto w = c + v;
    auto a = w + v + (x2 - x0) * 0.5f;
    auto b = w + a;
    return ((a * f - b) * f + c) * f + x0;
}
} // namespace

void Sampler::renderVoice (Voice& v, const EngineSnapshot& snap, const EngineParams& params,
                           juce::AudioBuffer<float>& buses, int start, int num)
{
    auto& hit = *v.hit;
    auto mics = std::min ({ (int) hit.mics.size(), maxMics, (int) snap.micIsStereo.size() });
    auto piece = std::min (v.piece, maxPieces - 1);
    // Unpitched and on a whole sample: copy instead of interpolating.
    auto integral = std::abs (v.rate - 1.0) < 1.0e-12 && std::abs (v.pos - std::floor (v.pos)) < 1.0e-12;

    for (int m = 0; m < mics; ++m)
    {
        auto& buf = hit.mics[(size_t) m];
        if (buf == nullptr)
            continue;
        auto g = v.gain * params.bleed[(size_t) piece][(size_t) m];
        if (g < 1.0e-6f)
            continue;

        auto len = buf->getNumSamples();
        auto* s0 = buf->getReadPointer (0);
        auto* s1 = buf->getNumChannels() > 1 ? buf->getReadPointer (1) : nullptr;
        auto spread = s1 == nullptr && snap.micIsStereo[(size_t) m] != 0;   // mono overhead / room: place the drum
        auto gl = spread ? v.panL : 1.0f, gr = spread ? v.panR : 1.0f;
        auto* L = buses.getWritePointer (2 * m, start);
        auto* R = buses.getWritePointer (2 * m + 1, start);

        auto pos = v.pos;
        auto fade = v.fade, env = v.env;
        auto envDelay = v.envDelay;
        for (int i = 0; i < num; ++i)
        {
            if (pos >= (double) (len - 1))
                break;
            float a, b;
            if (integral)
            {
                auto idx = (int) pos;
                a = s0[idx];
                b = s1 != nullptr ? s1[idx] : a;
            }
            else
            {
                a = hermite (s0, len, pos);
                b = s1 != nullptr ? hermite (s1, len, pos) : a;
            }
            auto amp = g * fade * env;
            L[i] += a * amp * gl;
            R[i] += b * amp * gr;
            pos += v.rate;
            if (v.fadeStep > 0.0f && (fade -= v.fadeStep) <= 0.0f)
                break;
            if (envDelay > 0) --envDelay;
            else env *= v.envCoef;
        }
    }

    // Move the voice on by the block, the same way every mic did.
    v.pos += v.rate * num;
    if (v.fadeStep > 0.0f)
        v.fade -= v.fadeStep * (float) num;
    auto envSamples = std::max (0, num - v.envDelay);
    v.envDelay = std::max (0, v.envDelay - num);
    if (v.envCoef < 1.0f && envSamples > 0)
        v.env *= std::pow (v.envCoef, (float) envSamples);
    if (v.pos >= (double) (hit.length - 1) || v.fade <= 0.0f || v.env < 1.0e-4f)
        v.active = false;
}

void Sampler::process (const EngineSnapshot& snap, const EngineParams& params, const juce::MidiBuffer& midi,
                       juce::AudioBuffer<float>& buses, int numSamples, juce::int64 clock,
                       EventFifo<PlayRequest, 64>& requests, EventFifo<HitEvent, 1024>& events)
{
    // A different kit: everything still ringing belongs to samples that are going away.
    if (snap.kit.get() != lastKit || snap.generation < lastGeneration)
    {
        reset();
        lastKit = snap.kit.get();
    }
    lastGeneration = snap.generation;

    PlayRequest req;
    while (requests.pop (req))
    {
        if (req.piece == -2)
        {
            reset();
            continue;
        }
        startHit (snap, params, req.piece, req.artic, req.hit, req.velocity, req.semis, -1, clock,
                  (juce::uint8) ((req.hit >= 0 ? HitEvent::audition : 0) | (std::abs (req.semis) > 0.001f ? HitEvent::chromatic : 0)), events);
    }

    auto renderAll = [&] (int start, int num)
    {
        if (num <= 0) return;
        for (auto& v : voices)
            if (v.active)
                renderVoice (v, snap, params, buses, start, num);
    };

    int pos = 0;
    for (const auto meta : midi)
    {
        auto t = juce::jlimit (0, numSamples, meta.samplePosition);
        renderAll (pos, t - pos);
        pos = std::max (pos, t);
        auto msg = meta.getMessage();

        if (msg.isNoteOn())
        {
            auto note = msg.getNoteNumber();
            if (snap.chromaticOn && note >= snap.chromaticLow && note <= snap.chromaticHigh
                && juce::isPositiveAndBelow (snap.chromaticPiece, (int) snap.pieces.size()))
            {
                // Chromatic zone: the drum plays the note you pressed.
                auto p = snap.chromaticPiece;
                auto natural = snap.pieces[(size_t) p].naturalMidi;
                auto target = chromaticTarget (note, natural, snap.chromaticLow, snap.chromaticHigh);
                if (snap.chromaticSnap)
                    target = (float) nearestInKey (snap.key, target);
                auto extra = target - natural - params.pieces[(size_t) std::min (p, maxPieces - 1)].semis;
                startHit (snap, params, p, 0, -1, msg.getVelocity(), extra, note, clock + t, HitEvent::chromatic, events);
            }
            else if (auto r = snap.notes[(size_t) note]; r.piece >= 0)
                startHit (snap, params, r.piece, r.artic, -1, msg.getVelocity(), 0.0f, note, clock + t, 0, events);
        }
        else if (msg.isAftertouch() && msg.getAfterTouchValue() >= 64)
        {
            // E-kits grab cymbals with polyphonic aftertouch.
            if (auto r = snap.notes[(size_t) msg.getNoteNumber()]; r.piece >= 0 && isCymbal (snap.pieces[(size_t) r.piece].type))
            {
                chokePiece (r.piece, false, 0.015f);
                HitEvent e;
                e.piece = (juce::int16) r.piece; e.artic = (juce::int16) r.artic; e.note = (juce::int16) msg.getNoteNumber();
                e.time = clock + t; e.flags = HitEvent::choke;
                events.push (e);
            }
        }
        else if (msg.isAllNotesOff() || msg.isAllSoundOff())
        {
            for (auto& v : voices)
                if (v.active)
                    v.fadeStep = 1.0f / (float) (0.01 * sampleRate);
        }
    }
    renderAll (pos, numSamples - pos);

    numActive = 0;
    for (auto& v : voices)
        numActive += v.active ? 1 : 0;
}
} // namespace pd
