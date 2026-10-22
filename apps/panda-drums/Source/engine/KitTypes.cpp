#include "KitTypes.h"

namespace pd
{
const char* pieceTypeName (PieceType t)
{
    switch (t)
    {
        case PieceType::Kick:   return "kick";
        case PieceType::Snare:  return "snare";
        case PieceType::Tom:    return "tom";
        case PieceType::HiHat:  return "hihat";
        case PieceType::Crash:  return "crash";
        case PieceType::Ride:   return "ride";
        case PieceType::China:  return "china";
        case PieceType::Splash: return "splash";
        case PieceType::Perc:   return "perc";
    }
    return "perc";
}

PieceType pieceTypeFromName (const juce::String& s, PieceType fallback)
{
    auto n = s.toLowerCase().removeCharacters (" -_.0123456789");
    if (n.contains ("kick") || n.contains ("bassdrum") || n == "bd" || n == "kd")          return PieceType::Kick;
    if (n.contains ("snare") || n == "sn" || n == "sd")                                    return PieceType::Snare;
    if (n.contains ("hihat") || n.contains ("hat") || n == "hh")                           return PieceType::HiHat;
    if (n.contains ("tom") || n == "ft" || n == "rt")                                      return PieceType::Tom;
    if (n.contains ("china") || n.contains ("trash"))                                      return PieceType::China;
    if (n.contains ("splash"))                                                             return PieceType::Splash;
    if (n.contains ("ride"))                                                               return PieceType::Ride;
    if (n.contains ("crash") || n.contains ("cymbal") || n.contains ("stack"))             return PieceType::Crash;
    if (n.contains ("perc") || n.contains ("cowbell") || n.contains ("clap") || n.contains ("tamb"))
        return PieceType::Perc;
    return fallback;
}

const char* micGroupName (MicGroup g)
{
    switch (g)
    {
        case MicGroup::Close:     return "close";
        case MicGroup::Overhead:  return "overhead";
        case MicGroup::RoomClose: return "room";
        case MicGroup::RoomFar:   return "far room";
        case MicGroup::Other:     return "other";
    }
    return "other";
}

MicGroup micGroupFromName (const juce::String& s)
{
    auto n = s.toLowerCase();
    if (n.contains ("overhead") || n == "oh" || n.startsWith ("oh ") || n.contains (" oh") || n.contains ("cymbal mic"))
        return MicGroup::Overhead;
    if (n.contains ("far") || n.contains ("hall") || n.contains ("distant"))
        return MicGroup::RoomFar;
    if (n.contains ("room") || n.contains ("amb") || n == "rm" || n.contains ("mono room") || n.contains ("crush") || n.contains ("trash"))
        return MicGroup::RoomClose;
    if (n == "close" || n.contains ("in") || n.contains ("out") || n.contains ("top") || n.contains ("bottom")
        || n.contains ("sub") || n.contains ("spot") || n.contains ("kick") || n.contains ("snare")
        || n.contains ("tom") || n.contains ("hat") || n.contains ("ride"))
        return MicGroup::Close;
    return MicGroup::Other;
}

int Kit::findPiece (const juce::String& id) const
{
    for (size_t i = 0; i < pieces.size(); ++i)
        if (pieces[i].id.equalsIgnoreCase (id))
            return (int) i;
    return -1;
}

int Kit::findMic (const juce::String& id) const
{
    for (size_t i = 0; i < mics.size(); ++i)
        if (mics[i].id.equalsIgnoreCase (id))
            return (int) i;
    return -1;
}

std::shared_ptr<const VariantData> Kit::getLoaded (int piece, int variant) const
{
    std::lock_guard<std::mutex> l (cacheLock);
    auto it = cache.find ({ piece, variant });
    return it == cache.end() ? nullptr : it->second;
}

void Kit::setLoaded (int piece, int variant, std::shared_ptr<const VariantData> d)
{
    // First one wins: a variant that is playing must never be swapped out from under its voices.
    std::lock_guard<std::mutex> l (cacheLock);
    cache.emplace (std::make_pair (piece, variant), std::move (d));
}

size_t Kit::loadedBytes() const
{
    std::lock_guard<std::mutex> l (cacheLock);
    size_t total = 0;
    for (auto& kv : cache)
        if (kv.second != nullptr)
            total += kv.second->bytes;
    return total;
}

juce::String hitKey (const Kit& kit, int piece, int variant, int artic, int hit)
{
    if (! juce::isPositiveAndBelow (piece, (int) kit.pieces.size()))
        return {};
    auto& p = kit.pieces[(size_t) piece];
    juce::String v = juce::isPositiveAndBelow (variant, (int) p.variants.size()) ? p.variants[(size_t) variant].name : juce::String (variant);
    juce::String a (artic);
    if (auto data = kit.getLoaded (piece, variant))
        if (juce::isPositiveAndBelow (artic, (int) data->artics.size()))
        {
            a = data->artics[(size_t) artic].id;
            auto& hits = data->artics[(size_t) artic].hits;
            if (juce::isPositiveAndBelow (hit, (int) hits.size()) && hits[(size_t) hit].name.isNotEmpty())
                return p.id + "/" + v + "/" + a + "/" + hits[(size_t) hit].name;
        }
    return p.id + "/" + v + "/" + a + "/" + juce::String (hit + 1);
}

float hzToMidi (float hz)   { return hz > 0.0f ? 69.0f + 12.0f * std::log2 (hz / 440.0f) : 0.0f; }
float midiToHz (float midi) { return 440.0f * std::pow (2.0f, (midi - 69.0f) / 12.0f); }

juce::String midiNoteName (int note, bool withOctave)
{
    static const char* names[] = { "C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B" };
    auto n = juce::String (names[((note % 12) + 12) % 12]);
    if (withOctave)
        n << (int) std::floor (note / 12.0) - 2;
    return n;
}

juce::String pitchName (float midi)
{
    auto nearest = (int) std::lround (midi);
    auto cents = (int) std::lround ((midi - (float) nearest) * 100.0f);
    auto s = midiNoteName (nearest);
    if (cents != 0)
        s << (cents > 0 ? " +" : " ") << cents << "c";
    return s;
}
} // namespace pd
