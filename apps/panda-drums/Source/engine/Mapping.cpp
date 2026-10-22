#include "Mapping.h"

namespace pd
{
juce::var MidiMap::toVar() const
{
    auto* o = new juce::DynamicObject();
    o->setProperty ("name", name);
    auto* notes = new juce::DynamicObject();
    for (auto& e : entries)
        if (juce::isPositiveAndBelow (e.note, 128) && e.target.isNotEmpty())
            notes->setProperty (juce::String (e.note), e.target);
    o->setProperty ("notes", juce::var (notes));
    o->setProperty ("format", "panda-drums-map-1");
    return juce::var (o);
}

MidiMap MidiMap::fromVar (const juce::var& v)
{
    MidiMap m;
    m.name = v.getProperty ("name", "Imported").toString();
    if (auto* notes = v.getProperty ("notes", {}).getDynamicObject())
        for (auto& p : notes->getProperties())
        {
            auto note = p.name.toString().getIntValue();
            if (juce::isPositiveAndBelow (note, 128))
                m.set (note, p.value.toString());
        }
    return m;
}

juce::String MidiMap::targetFor (int note) const
{
    for (auto& e : entries)
        if (e.note == note)
            return e.target;
    return {};
}

void MidiMap::set (int note, const juce::String& target)
{
    entries.erase (std::remove_if (entries.begin(), entries.end(), [note] (auto& e) { return e.note == note; }), entries.end());
    if (target.isNotEmpty())
        entries.push_back ({ note, target });
    std::sort (entries.begin(), entries.end(), [] (auto& a, auto& b) { return a.note < b.note; });
}

void MidiMap::clearTarget (const juce::String& target)
{
    entries.erase (std::remove_if (entries.begin(), entries.end(), [&] (auto& e) { return e.target == target; }), entries.end());
}

std::vector<int> MidiMap::notesFor (const juce::String& target) const
{
    std::vector<int> out;
    for (auto& e : entries)
        if (e.target == target)
            out.push_back (e.note);
    return out;
}

const std::vector<MidiMap>& presetMaps()
{
    static const std::vector<MidiMap> maps = []
    {
        auto make = [] (const char* name, std::initializer_list<std::pair<int, const char*>> list)
        {
            MidiMap m;
            m.name = name;
            for (auto& [n, t] : list)
                m.set (n, t);
            return m;
        };

        std::vector<MidiMap> v;
        // General MIDI, plus the extra articulations on notes GM leaves free.
        v.push_back (make ("Panda (General MIDI +)", {
            { 35, "kick" }, { 36, "kick" },
            { 37, "snare.sidestick" }, { 38, "snare.center" }, { 40, "snare.rim" }, { 33, "snare.ghost" }, { 31, "snare.flam" }, { 32, "snare.roll" },
            { 50, "tom1" }, { 48, "tom1" }, { 47, "tom2" }, { 45, "tom2" }, { 43, "tom3" }, { 41, "tom4|tom3" },
            { 42, "hihat.closed" }, { 44, "hihat.pedal" }, { 46, "hihat.open" }, { 23, "hihat.half" }, { 21, "hihat.footsplash" },
            { 49, "crash1" }, { 57, "crash2" }, { 55, "splash" }, { 52, "china" },
            { 51, "ride.bow" }, { 59, "ride.bow" }, { 53, "ride.bell" },
            { 28, "crash1.choke" }, { 29, "crash2.choke" } }));

        v.push_back (make ("General MIDI", {
            { 35, "kick" }, { 36, "kick" }, { 37, "snare.sidestick" }, { 38, "snare.center" }, { 40, "snare.rim" },
            { 41, "tom4|tom3" }, { 43, "tom3" }, { 45, "tom2" }, { 47, "tom2" }, { 48, "tom1" }, { 50, "tom1" },
            { 42, "hihat.closed" }, { 44, "hihat.pedal" }, { 46, "hihat.open" },
            { 49, "crash1" }, { 57, "crash2" }, { 52, "china" }, { 55, "splash" },
            { 51, "ride.bow" }, { 59, "ride.bow" }, { 53, "ride.bell" } }));

        // Toontrack layout (Superior Drummer 3 / EZdrummer): hi-hat edges on 22 and 26.
        v.push_back (make ("Toontrack style (SD3 / EZdrummer)", {
            { 36, "kick" }, { 35, "kick" }, { 38, "snare.center" }, { 40, "snare.rim" }, { 37, "snare.sidestick" },
            { 48, "tom1" }, { 47, "tom2" }, { 45, "tom3|tom2" }, { 43, "tom3" }, { 41, "tom4|tom3" },
            { 42, "hihat.closed" }, { 22, "hihat.closed" }, { 46, "hihat.open" }, { 26, "hihat.open" },
            { 23, "hihat.half" }, { 24, "hihat.half" }, { 25, "hihat.open" }, { 44, "hihat.pedal" }, { 21, "hihat.footsplash" },
            { 49, "crash1" }, { 55, "splash" }, { 57, "crash2" }, { 52, "china" },
            { 51, "ride.bow" }, { 59, "ride.bow" }, { 53, "ride.bell" } }));

        // Roland V-Drums default note numbers, heads and rims.
        v.push_back (make ("Roland V-Drums (e-kit)", {
            { 36, "kick" }, { 38, "snare.center" }, { 40, "snare.rim" }, { 37, "snare.sidestick" },
            { 48, "tom1" }, { 50, "tom1.rim" }, { 45, "tom2" }, { 47, "tom2.rim" }, { 43, "tom3" }, { 58, "tom3.rim" }, { 41, "tom4|tom3" }, { 39, "tom4.rim|tom3.rim" },
            { 42, "hihat.closed" }, { 22, "hihat.closed" }, { 46, "hihat.open" }, { 26, "hihat.open" }, { 44, "hihat.pedal" },
            { 49, "crash1" }, { 55, "crash1" }, { 57, "crash2" }, { 52, "crash2" },
            { 51, "ride.bow" }, { 59, "ride.bow" }, { 53, "ride.bell" } }));
        return v;
    }();
    return maps;
}

namespace
{
int findPieceLoose (const Kit& kit, const juce::String& id)
{
    auto i = kit.findPiece (id);
    if (i >= 0)
        return i;
    // "crash1" also means a lone "crash"; "crash" also means "crash1".
    auto base = id.trimCharactersAtEnd ("0123456789");
    if (base != id && id.getTrailingIntValue() == 1)
        return kit.findPiece (base);
    if (base == id)
        return kit.findPiece (id + "1");
    return -1;
}

int findArtic (const VariantData& d, const juce::String& id)
{
    for (size_t a = 0; a < d.artics.size(); ++a)
        if (d.artics[a].id.equalsIgnoreCase (id))
            return (int) a;
    // "center" and "hit" are the same thing on drums recorded with one articulation.
    if (id == "center" || id == "hit" || id == "closed" || id == "bow")
        return d.artics.empty() ? -1 : 0;
    return -1;
}
} // namespace

std::vector<ArticRef> playableTargets (const Kit& kit, const std::vector<std::shared_ptr<const VariantData>>& selected)
{
    std::vector<ArticRef> out;
    for (size_t p = 0; p < kit.pieces.size() && p < selected.size(); ++p)
    {
        if (selected[p] == nullptr)
            continue;
        auto& d = *selected[p];
        for (size_t a = 0; a < d.artics.size(); ++a)
        {
            auto target = a == 0 ? kit.pieces[p].id : kit.pieces[p].id + "." + d.artics[a].id;
            auto label = kit.pieces[p].name + (d.artics.size() > 1 ? utf8 (" \xc2\xb7 ") + d.artics[a].name : juce::String());
            out.push_back ({ (int) p, (int) a, target, label });
        }
    }
    return out;
}

std::array<ResolvedNote, 128> resolveMap (const MidiMap& map, const Kit& kit, const std::vector<std::shared_ptr<const VariantData>>& selected)
{
    std::array<ResolvedNote, 128> out {};
    for (auto& e : map.entries)
    {
        if (! juce::isPositiveAndBelow (e.note, 128))
            continue;
        // "tom4|tom3": the first one the kit has.
        for (auto& option : juce::StringArray::fromTokens (e.target, "|", {}))
        {
            auto pieceId = option.upToFirstOccurrenceOf (".", false, false);
            auto articId = option.fromFirstOccurrenceOf (".", false, false);
            auto p = findPieceLoose (kit, pieceId);
            if (p < 0 || p >= (int) selected.size() || selected[(size_t) p] == nullptr)
                continue;
            auto a = articId.isEmpty() ? 0 : findArtic (*selected[(size_t) p], articId);
            if (a < 0)
                continue;
            out[(size_t) e.note] = { p, a };
            break;
        }
    }
    return out;
}
} // namespace pd
