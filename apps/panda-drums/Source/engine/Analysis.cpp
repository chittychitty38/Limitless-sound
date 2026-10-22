#include "Analysis.h"
#include <algorithm>
#include <numeric>
#include <set>

namespace pd
{
namespace
{
const juce::AudioBuffer<float>* referenceBuffer (const Hit& h, int referenceMic)
{
    if (juce::isPositiveAndBelow (referenceMic, (int) h.mics.size()) && h.mics[(size_t) referenceMic] != nullptr)
        return h.mics[(size_t) referenceMic].get();
    // No reference mic recorded: use the loudest one there is.
    const juce::AudioBuffer<float>* best = nullptr;
    float bestPeak = -1.0f;
    for (auto& m : h.mics)
        if (m != nullptr)
        {
            auto p = m->getMagnitude (0, m->getNumSamples());
            if (p > bestPeak) { bestPeak = p; best = m.get(); }
        }
    return best;
}

float median (std::vector<float> v)
{
    if (v.empty())
        return -120.0f;
    std::sort (v.begin(), v.end());
    auto n = v.size();
    return n % 2 == 1 ? v[n / 2] : 0.5f * (v[n / 2 - 1] + v[n / 2]);
}

// Round robin order inside a zone: by the number in the file name, then by name.
void sortRounds (std::vector<int>& idx, const Articulation& a)
{
    std::stable_sort (idx.begin(), idx.end(), [&] (int x, int y)
    {
        auto& hx = a.hits[(size_t) x];
        auto& hy = a.hits[(size_t) y];
        if (hx.fileRR != hy.fileRR && hx.fileRR >= 0 && hy.fileRR >= 0)
            return hx.fileRR < hy.fileRR;
        return hx.name.compareNatural (hy.name) < 0;
    });
}
} // namespace

void measureHit (Hit& h, int referenceMic)
{
    h.length = 0;
    for (auto& m : h.mics)
        if (m != nullptr)
            h.length = std::max (h.length, m->getNumSamples());

    auto* buf = referenceBuffer (h, referenceMic);
    if (buf == nullptr || buf->getNumSamples() == 0)
    {
        h.peakDb = h.rmsDb = -120.0f;
        return;
    }

    auto n = buf->getNumSamples();
    auto peakWindow = std::min (n, (int) (h.sampleRate * 0.1));
    float peak = 0.0f;
    int peakAt = 0;
    for (int c = 0; c < buf->getNumChannels(); ++c)
    {
        auto* d = buf->getReadPointer (c);
        for (int i = 0; i < peakWindow; ++i)
            if (std::abs (d[i]) > peak) { peak = std::abs (d[i]); peakAt = i; }
    }

    // RMS of the first 50 ms from just before the peak: what the ear calls "how hard".
    auto start = std::max (0, peakAt - (int) (h.sampleRate * 0.002));
    auto len = std::min (n - start, (int) (h.sampleRate * 0.05));
    double sum = 0.0;
    for (int c = 0; c < buf->getNumChannels(); ++c)
    {
        auto* d = buf->getReadPointer (c, start);
        for (int i = 0; i < len; ++i)
            sum += (double) d[i] * d[i];
    }
    auto rms = len > 0 ? std::sqrt (sum / (double) (len * buf->getNumChannels())) : 0.0;
    h.peakDb = juce::Decibels::gainToDecibels (peak, -120.0f);
    h.rmsDb = juce::Decibels::gainToDecibels ((float) rms, -120.0f);
}

float detectPitchHz (const juce::AudioBuffer<float>& buf, double sr)
{
    auto n = buf.getNumSamples();
    if (n < (int) (sr * 0.08))
        return 0.0f;

    // Mono, starting 25 ms after the peak so the stick noise is out of the way.
    std::vector<float> x ((size_t) n, 0.0f);
    for (int c = 0; c < buf.getNumChannels(); ++c)
    {
        auto* d = buf.getReadPointer (c);
        for (int i = 0; i < n; ++i)
            x[(size_t) i] += d[i];
    }
    int peakAt = 0;
    float peak = 0.0f;
    for (int i = 0; i < std::min (n, (int) (sr * 0.1)); ++i)
        if (std::abs (x[(size_t) i]) > peak) { peak = std::abs (x[(size_t) i]); peakAt = i; }

    auto start = peakAt + (int) (sr * 0.025);
    auto win = std::min (n - start, (int) (sr * 0.25));
    auto minLag = (int) (sr / 600.0), maxLag = (int) (sr / 32.0);
    if (win < maxLag * 2)
    {
        maxLag = win / 2;
        if (maxLag <= minLag + 2)
            return 0.0f;
    }

    // Gentle low-pass so the overtones of the shell don't win.
    std::vector<float> y ((size_t) win);
    float z = 0.0f;
    auto a = (float) std::exp (-2.0 * juce::MathConstants<double>::pi * 900.0 / sr);
    for (int i = 0; i < win; ++i)
    {
        z = (1.0f - a) * x[(size_t) (start + i)] + a * z;
        y[(size_t) i] = z;
    }

    auto len = win - maxLag;
    std::vector<float> r ((size_t) (maxLag + 1), 0.0f);
    double e0 = 0.0;
    for (int i = 0; i < len; ++i)
        e0 += (double) y[(size_t) i] * y[(size_t) i];
    if (e0 <= 1e-12)
        return 0.0f;

    for (int lag = minLag; lag <= maxLag; ++lag)
    {
        double s = 0.0, e1 = 0.0;
        for (int i = 0; i < len; ++i)
        {
            s += (double) y[(size_t) i] * y[(size_t) (i + lag)];
            e1 += (double) y[(size_t) (i + lag)] * y[(size_t) (i + lag)];
        }
        r[(size_t) lag] = (float) (s / std::sqrt (e0 * e1 + 1e-20));
    }

    // Best peak, but take the shortest lag that is nearly as good, so we don't jump an octave down.
    float best = 0.0f;
    for (int lag = minLag + 1; lag < maxLag; ++lag)
        best = std::max (best, r[(size_t) lag]);
    if (best < 0.5f)
        return 0.0f;

    for (int lag = minLag + 1; lag < maxLag; ++lag)
    {
        auto v = r[(size_t) lag];
        if (v >= 0.8f * best && v >= r[(size_t) lag - 1] && v >= r[(size_t) lag + 1])
        {
            auto l = r[(size_t) lag - 1], c = v, rr = r[(size_t) lag + 1];
            auto denom = l - 2.0f * c + rr;
            auto shift = std::abs (denom) > 1e-9f ? 0.5f * (l - rr) / denom : 0.0f;
            return (float) (sr / ((double) lag + juce::jlimit (-0.5f, 0.5f, shift)));
        }
    }
    return 0.0f;
}

float detectVariantPitch (const VariantData& v, int referenceMic)
{
    if (v.artics.empty())
        return 0.0f;
    auto& a = v.artics.front();
    if (a.hits.empty())
        return 0.0f;

    // Median pitch of the loudest few hits.
    std::vector<int> idx ((size_t) a.hits.size());
    std::iota (idx.begin(), idx.end(), 0);
    std::sort (idx.begin(), idx.end(), [&] (int x, int y) { return a.hits[(size_t) x].peakDb > a.hits[(size_t) y].peakDb; });

    std::vector<float> found;
    for (size_t i = 0; i < std::min<size_t> (5, idx.size()); ++i)
    {
        auto& h = a.hits[(size_t) idx[i]];
        if (auto* b = referenceBuffer (h, referenceMic))
            if (auto hz = detectPitchHz (*b, h.sampleRate); hz > 0.0f)
                found.push_back (hz);
    }
    return found.empty() ? 0.0f : median (found);
}

ArticLayout layoutArticulation (const Articulation& a, const ZoneSettings& s)
{
    ArticLayout out;
    auto n = (int) a.hits.size();
    out.hitGain.assign ((size_t) n, 1.0f);
    out.hitZone.assign ((size_t) n, 0);
    out.hitRound.assign ((size_t) n, 0);
    if (n == 0)
        return out;

    int tagged = 0;
    for (auto& h : a.hits)
        tagged += h.fileLayer >= 0 ? 1 : 0;

    std::vector<std::vector<int>> groups;
    if (s.source == ZoneSettings::Source::FileNames && tagged == n)
    {
        // One zone per layer number in the file names...
        std::map<int, std::vector<int>> byLayer;
        for (int i = 0; i < n; ++i)
            byLayer[a.hits[(size_t) i].fileLayer].push_back (i);
        for (auto& kv : byLayer)
            groups.push_back (kv.second);

        // ...ordered by how loud they really are, so "v1 = loudest" naming still works.
        std::stable_sort (groups.begin(), groups.end(), [&] (const auto& x, const auto& y)
        {
            std::vector<float> lx, ly;
            for (auto i : x) lx.push_back (a.hits[(size_t) i].rmsDb);
            for (auto i : y) ly.push_back (a.hits[(size_t) i].rmsDb);
            return median (lx) < median (ly);
        });
        out.fromFileNames = true;
    }
    else
    {
        // Sort every hit by loudness and cut the line into equal groups.
        std::vector<int> idx ((size_t) n);
        std::iota (idx.begin(), idx.end(), 0);
        std::stable_sort (idx.begin(), idx.end(), [&] (int x, int y) { return a.hits[(size_t) x].rmsDb < a.hits[(size_t) y].rmsDb; });

        int zones = s.zoneCount;
        if (zones <= 0)
        {
            // Automatic: as many zones as there are distinct layer numbers or round robin
            // numbers suggest, otherwise about four round robins per zone.
            std::set<int> rrs;
            for (auto& h : a.hits)
                if (h.fileRR >= 0) rrs.insert (h.fileRR);
            if (tagged > 0)
            {
                std::set<int> layers;
                for (auto& h : a.hits)
                    if (h.fileLayer >= 0) layers.insert (h.fileLayer);
                zones = (int) layers.size();
            }
            else if (rrs.size() > 1)
                zones = n / (int) rrs.size();
            else
                zones = n / 4;
        }
        zones = juce::jlimit (1, std::min (n, 32), zones);

        for (int z = 0; z < zones; ++z)
        {
            auto from = (int) std::lround ((double) z * n / zones);
            auto to = (int) std::lround ((double) (z + 1) * n / zones);
            groups.emplace_back (idx.begin() + from, idx.begin() + to);
        }
    }

    auto zones = (int) groups.size();
    out.zones.resize ((size_t) zones);
    for (int z = 0; z < zones; ++z)
    {
        auto& zone = out.zones[(size_t) z];
        zone.hits = groups[(size_t) z];
        sortRounds (zone.hits, a);
        std::vector<float> peaks;
        for (auto i : zone.hits)
            peaks.push_back (a.hits[(size_t) i].rmsDb);
        zone.refDb = median (peaks);

        for (size_t r = 0; r < zone.hits.size(); ++r)
        {
            auto i = (size_t) zone.hits[r];
            out.hitZone[i] = z;
            out.hitRound[i] = (int) r;
            // Level match ("stabilize"): every round robin lands at the zone's median level.
            auto diff = juce::jlimit (-9.0f, 9.0f, zone.refDb - a.hits[i].rmsDb);
            out.hitGain[i] = juce::Decibels::decibelsToGain (diff * juce::jlimit (0.0f, 1.0f, s.levelMatch));
        }
    }

    // Velocity lanes.
    if (s.ranges == ZoneSettings::Ranges::Loudness && zones > 1)
    {
        // Place each zone on the 1..127 line by its level (40 dB of range) and split halfway between.
        auto top = out.zones.back().refDb;
        std::vector<float> centre ((size_t) zones);
        for (int z = 0; z < zones; ++z)
            centre[(size_t) z] = juce::jlimit (1.0f, 127.0f, 127.0f * (1.0f + (out.zones[(size_t) z].refDb - top) / 40.0f));
        for (int z = 1; z < zones; ++z)   // keep them in order and at least one step apart
            centre[(size_t) z] = std::max (centre[(size_t) z], centre[(size_t) z - 1] + 1.0f);
        int lo = 1;
        for (int z = 0; z < zones; ++z)
        {
            auto hi = z == zones - 1 ? 127 : (int) std::floor (0.5f * (centre[(size_t) z] + centre[(size_t) z + 1]));
            hi = juce::jlimit (lo, 127 - (zones - 1 - z), hi);
            out.zones[(size_t) z].lo = lo;
            out.zones[(size_t) z].hi = hi;
            lo = hi + 1;
        }
    }
    else
    {
        for (int z = 0; z < zones; ++z)
        {
            out.zones[(size_t) z].lo = 1 + (int) std::lround ((double) z * 127.0 / zones);
            out.zones[(size_t) z].hi = (int) std::lround ((double) (z + 1) * 127.0 / zones);
        }
        out.zones.front().lo = 1;
        out.zones.back().hi = 127;
    }
    return out;
}

int zoneForVelocity (const ArticLayout& l, int velocity)
{
    for (int z = 0; z < (int) l.zones.size(); ++z)
        if (velocity >= l.zones[(size_t) z].lo && velocity <= l.zones[(size_t) z].hi)
            return z;
    return l.zones.empty() ? -1 : (velocity < l.zones.front().lo ? 0 : (int) l.zones.size() - 1);
}
} // namespace pd
