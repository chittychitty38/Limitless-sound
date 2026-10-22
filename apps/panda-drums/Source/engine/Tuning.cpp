#include "Tuning.h"
#include "KitTypes.h"
#include <algorithm>
#include <limits>
#include <numeric>

namespace pd
{
const std::vector<Scale>& scales()
{
    static const std::vector<Scale> s {
        { "Off (chromatic)",  { 0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11 } },
        { "Major",            { 0, 2, 4, 5, 7, 9, 11 } },
        { "Minor",            { 0, 2, 3, 5, 7, 8, 10 } },
        { "Harmonic minor",   { 0, 2, 3, 5, 7, 8, 11 } },
        { "Dorian",           { 0, 2, 3, 5, 7, 9, 10 } },
        { "Phrygian",         { 0, 1, 3, 5, 7, 8, 10 } },
        { "Lydian",           { 0, 2, 4, 6, 7, 9, 11 } },
        { "Mixolydian",       { 0, 2, 4, 5, 7, 9, 10 } },
        { "Major pentatonic", { 0, 2, 4, 7, 9 } },
        { "Minor pentatonic", { 0, 3, 5, 7, 10 } },
        { "Blues",            { 0, 3, 5, 6, 7, 10 } },
    };
    return s;
}

juce::String Key::name() const
{
    if (isOff())
        return "Off";
    auto n = midiNoteName (root, false);
    auto& sc = scales()[(size_t) juce::jlimit (0, (int) scales().size() - 1, scale)];
    return n + " " + juce::String (sc.name).toLowerCase();
}

bool Key::contains (int note) const
{
    if (isOff())
        return true;
    auto& sc = scales()[(size_t) juce::jlimit (0, (int) scales().size() - 1, scale)];
    auto pc = ((note - root) % 12 + 12) % 12;
    return std::find (sc.steps.begin(), sc.steps.end(), pc) != sc.steps.end();
}

int nearestInKey (const Key& k, float pitch)
{
    auto base = (int) std::lround (pitch);
    for (int d = 0; d <= 12; ++d)
    {
        // Prefer the closer side; on a tie, the lower note (less stretching of the head).
        int a = base - d, b = base + d;
        auto da = std::abs (pitch - (float) a), db = std::abs (pitch - (float) b);
        if (k.contains (a) && k.contains (b))
            return da <= db ? a : b;
        if (k.contains (a)) return a;
        if (k.contains (b)) return b;
    }
    return base;
}

int stepInKey (const Key& k, float pitch, int direction)
{
    auto n = direction > 0 ? (int) std::floor (pitch + 0.05f) + 1 : (int) std::ceil (pitch - 0.05f) - 1;
    for (int i = 0; i < 24 && ! k.contains (n); ++i)
        n += direction > 0 ? 1 : -1;
    return n;
}

std::vector<float> tuneToKey (const Key& k, const std::vector<float>& natural, float maxShift)
{
    auto count = natural.size();
    std::vector<float> out (count, 0.0f);
    if (count == 0)
        return out;

    // Order drums by pitch, then pick one note each, strictly rising, with the least total retuning.
    std::vector<size_t> order (count);
    std::iota (order.begin(), order.end(), 0);
    std::sort (order.begin(), order.end(), [&] (size_t a, size_t b) { return natural[a] < natural[b]; });

    std::vector<std::vector<int>> cand (count);
    for (size_t i = 0; i < count; ++i)
    {
        auto p = natural[order[i]];
        for (int n = (int) std::floor (p - maxShift); n <= (int) std::ceil (p + maxShift); ++n)
            if (k.contains (n))
                cand[i].push_back (n);
        if (cand[i].empty())
            cand[i].push_back (nearestInKey (k, p));
    }

    const float inf = std::numeric_limits<float>::max();
    std::vector<std::vector<float>> cost (count);
    std::vector<std::vector<int>> from (count);
    for (size_t i = 0; i < count; ++i)
    {
        cost[i].assign (cand[i].size(), inf);
        from[i].assign (cand[i].size(), -1);
        auto p = natural[order[i]];
        for (size_t c = 0; c < cand[i].size(); ++c)
        {
            auto own = std::abs ((float) cand[i][c] - p);
            if (i == 0) { cost[i][c] = own; continue; }
            for (size_t q = 0; q < cand[i - 1].size(); ++q)
                if (cost[i - 1][q] < inf && cand[i - 1][q] < cand[i][c] && cost[i - 1][q] + own < cost[i][c])
                {
                    cost[i][c] = cost[i - 1][q] + own;
                    from[i][c] = (int) q;
                }
        }
    }

    auto last = count - 1;
    auto best = std::min_element (cost[last].begin(), cost[last].end());
    if (*best >= inf)
    {
        // Too crowded to keep them apart: just take the nearest note for each.
        for (size_t i = 0; i < count; ++i)
            out[i] = (float) nearestInKey (k, natural[i]) - natural[i];
        return out;
    }
    auto c = (int) std::distance (cost[last].begin(), best);
    for (auto i = (int) last; i >= 0; --i)
    {
        out[order[(size_t) i]] = (float) cand[(size_t) i][(size_t) c] - natural[order[(size_t) i]];
        c = from[(size_t) i][(size_t) c];
        if (c < 0 && i > 0)
            break;
    }
    return out;
}

float chromaticTarget (int note, float naturalMidi, int zoneLow, int zoneHigh)
{
    // The first octave of the zone sits around the drum's own pitch; higher octaves go up.
    auto anchor = std::min ((float) zoneLow + 6.0f, 0.5f * (float) (zoneLow + zoneHigh));
    auto octaves = std::round ((anchor - naturalMidi) / 12.0f);
    return (float) note - 12.0f * octaves;
}
} // namespace pd
