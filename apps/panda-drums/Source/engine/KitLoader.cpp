#include "KitLoader.h"
#include "Analysis.h"
#include <set>

namespace pd
{
namespace
{
const juce::String audioWildcard = "*.wav;*.wave;*.aif;*.aiff;*.flac;*.ogg";

bool isAudioFile (const juce::File& f)
{
    return f.hasFileExtension ("wav;wave;aif;aiff;flac;ogg") && ! f.getFileName().startsWith (".");
}

juce::Array<juce::File> sortedChildren (const juce::File& dir, int what, const juce::String& pattern = "*")
{
    auto list = dir.findChildFiles (what, false, pattern);
    list.removeIf ([] (const juce::File& f) { return f.getFileName().startsWith ("."); });
    struct Natural { static int compareElements (const juce::File& a, const juce::File& b) { return a.getFileName().compareNatural (b.getFileName()); } } cmp;
    list.sort (cmp);
    return list;
}

juce::StringArray tokens (const juce::String& s)
{
    auto t = s.replaceCharacters ("_-.,()[]{}+", "           ");
    juce::StringArray out;
    out.addTokens (t, " ", "\"");
    out.removeEmptyStrings();
    return out;
}

juce::String alnumId (const juce::String& s)
{
    return s.toLowerCase().retainCharacters ("abcdefghijklmnopqrstuvwxyz0123456789");
}

juce::String titleCase (const juce::String& s)
{
    auto t = tokens (s);
    for (auto& w : t)
    {
        if (w.length() <= 3 && w.toUpperCase() == w)     // OH, AKG, SM7 stay as written
            continue;
        if (w.equalsIgnoreCase ("oh"))
            w = "OH";
        else
            w = w.substring (0, 1).toUpperCase() + w.substring (1);
    }
    return t.joinIntoString (" ");
}

// "in", "top"... mean "the close mic of this drum".
bool isGenericMicWord (const juce::String& w)
{
    static const juce::StringArray generic { "in", "inside", "out", "outside", "top", "bottom", "btm", "bot", "sub",
                                             "close", "spot", "dry", "direct", "mic", "di", "front", "back", "under", "over" };
    return generic.contains (w.toLowerCase());
}

bool isPlainCloseWord (const juce::String& w)
{
    static const juce::StringArray plain { "close", "spot", "dry", "direct", "mic" };
    return plain.contains (w.toLowerCase());
}

// Turns what was left of a file name into a mic name, e.g. "In" under Kick -> "Kick In".
juce::String micDisplayName (const juce::String& pieceName, const juce::String& raw)
{
    auto t = tokens (raw);
    if (t.isEmpty())
        return pieceName;
    if (isGenericMicWord (t[0]))
    {
        if (t.size() == 1 && isPlainCloseWord (t[0]))
            return pieceName;
        return pieceName + " " + titleCase (raw);
    }
    auto low = raw.toLowerCase();
    if (low == "oh" || low == "ohs" || low == "overhead" || low == "overheads")
        return "Overheads";
    return titleCase (raw);
}

// Stereo pairs recorded as two files: "OH L" / "OH R".
int stereoSide (juce::String& micName)
{
    auto t = tokens (micName);
    if (t.size() >= 2)
    {
        auto last = t[t.size() - 1].toLowerCase();
        int side = (last == "l" || last == "left") ? 0 : (last == "r" || last == "right") ? 1 : -1;
        if (side >= 0)
        {
            t.remove (t.size() - 1);
            micName = t.joinIntoString (" ");
            return side;
        }
    }
    return -1;
}

std::pair<float, float> sizeFromName (const juce::String& s)
{
    // "22 Vintage" -> 22, "14x6.5 Brass" -> 14 x 6.5, "18in crash" -> 18
    auto t = s.toLowerCase().replace ("\"", " ").replace ("''", " ");
    for (int i = 0; i < t.length(); ++i)
    {
        if (! juce::CharacterFunctions::isDigit (t[i]) || (i > 0 && juce::CharacterFunctions::isLetterOrDigit (t[i - 1])))
            continue;
        auto num = t.substring (i).initialSectionContainingOnly ("0123456789.");
        auto v = num.getFloatValue();
        if (v >= 6.0f && v <= 30.0f)
        {
            auto rest = t.substring (i + num.length()).trimStart();
            float depth = 0.0f;
            if (rest.startsWithChar ('x'))
                depth = rest.substring (1).trimStart().initialSectionContainingOnly ("0123456789.").getFloatValue();
            return { v, depth };
        }
        i += num.length();
    }
    return { 0.0f, 0.0f };
}

juce::var readJson (const juce::File& f)
{
    if (! f.existsAsFile())
        return {};
    return juce::JSON::parse (f.loadFileAsString());
}

juce::String str (const juce::var& o, const char* key, const juce::String& fallback = {})
{
    auto v = o.getProperty (key, {});
    return v.isVoid() ? fallback : v.toString();
}

struct ManifestPiece
{
    juce::var json;
    juce::var variantFor (const juce::String& folderName) const
    {
        if (auto* arr = json.getProperty ("variants", {}).getArray())
            for (auto& v : *arr)
                if (str (v, "folder").equalsIgnoreCase (folderName))
                    return v;
        return {};
    }
};

// Folders a piece's variant reads from: the variant folder plus its articulation folders.
struct VariantFolders
{
    juce::File dir;
    bool isWholePieceFolder = false;
};

std::vector<VariantFolders> findVariants (const juce::File& pieceDir)
{
    std::vector<VariantFolders> out;
    for (auto& sub : sortedChildren (pieceDir, juce::File::findDirectories))
        if (articulationFromWord (sub.getFileName()).first.isEmpty())
            if (! sortedChildren (sub, juce::File::findFiles, audioWildcard).isEmpty()
                || ! sub.findChildFiles (juce::File::findFiles, true, audioWildcard).isEmpty())
                out.push_back ({ sub, false });
    if (out.empty())
        out.push_back ({ pieceDir, true });
    return out;
}

// Every audio file of a variant with the articulation folder it was found in.
std::vector<std::pair<juce::File, juce::String>> variantFiles (const VariantFolders& v)
{
    std::vector<std::pair<juce::File, juce::String>> out;
    for (auto& f : sortedChildren (v.dir, juce::File::findFiles, audioWildcard))
        if (isAudioFile (f))
            out.push_back ({ f, {} });
    for (auto& sub : sortedChildren (v.dir, juce::File::findDirectories))
    {
        auto art = articulationFromWord (sub.getFileName());
        if (art.first.isEmpty() && ! v.isWholePieceFolder)
            art = { alnumId (sub.getFileName()), titleCase (sub.getFileName()) };   // unknown word: still an articulation
        if (art.first.isEmpty())
            continue;
        for (auto& f : sub.findChildFiles (juce::File::findFiles, true, audioWildcard))
            if (isAudioFile (f))
                out.push_back ({ f, art.first + "|" + art.second });
    }
    return out;
}

// Words in a file name that only repeat the drum's own name: "Tom 1", "22 Vintage", "tom1".
juce::StringArray ignoreWordsFor (const Piece& p, const Variant& v)
{
    juce::StringArray w { p.name, p.id, v.name, pieceTypeName (p.type) };
    if (v.folder.exists())
    {
        w.add (v.folder.getFileName());
        if (v.folderIsPiece)
            w.add (v.folder.getFileName());
        else
            w.add (v.folder.getParentDirectory().getFileName());
    }
    w.removeEmptyStrings();
    w.removeDuplicates (true);
    return w;
}

juce::String micIdFor (const Piece& p, const juce::String& rawMic, juce::String* displayOut = nullptr, int* sideOut = nullptr)
{
    auto display = micDisplayName (p.name, rawMic);
    auto side = stereoSide (display);
    if (display.isEmpty())
        display = p.name;
    if (displayOut != nullptr) *displayOut = display;
    if (sideOut != nullptr) *sideOut = side;
    return alnumId (display);
}

std::unique_ptr<juce::AudioFormatManager> makeFormats()
{
    auto fm = std::make_unique<juce::AudioFormatManager>();
    fm->registerBasicFormats();
    return fm;
}

void defaultPan (Piece& p, int index, int count)
{
    // Audience view, like the stage: hi-hat and snare on the right, floor tom and ride on the left.
    switch (p.type)
    {
        case PieceType::Kick:   p.pan = 0.0f; break;
        case PieceType::Snare:  p.pan = 0.15f; break;
        case PieceType::HiHat:  p.pan = 0.55f; break;
        case PieceType::Ride:   p.pan = -0.6f; break;
        case PieceType::China:  p.pan = -0.8f; break;
        case PieceType::Splash: p.pan = 0.35f; break;
        case PieceType::Crash:  p.pan = (index % 2 == 0) ? 0.5f : -0.5f; break;
        case PieceType::Tom:    p.pan = count > 1 ? juce::jmap ((float) index, 0.0f, (float) (count - 1), 0.35f, -0.55f) : 0.0f; break;
        case PieceType::Perc:   p.pan = 0.2f; break;
    }
}
} // namespace

std::pair<juce::String, juce::String> articulationFromWord (const juce::String& word)
{
    auto w = alnumId (word);
    static const std::vector<std::pair<juce::StringArray, std::pair<const char*, const char*>>> table {
        { { "center", "centre", "hit", "head", "snares", "normal", "main" }, { "center", "Center" } },
        { { "rim", "rimshot", "rimshots", "rs" },                            { "rim", "Rimshot" } },
        { { "sidestick", "side", "cross", "crossstick", "xstick", "stick", "ss" }, { "sidestick", "Sidestick" } },
        { { "edge", "crashedge" },                                           { "edge", "Edge" } },
        { { "bell", "cup" },                                                 { "bell", "Bell" } },
        { { "bow", "ride", "ridebow" },                                      { "bow", "Bow" } },
        { { "tip", "closedtip", "tight" },                                   { "closed", "Closed" } },
        { { "closed", "closededge", "shank" },                               { "closed", "Closed" } },
        { { "open", "opened", "open1", "open2", "loose" },                   { "open", "Open" } },
        { { "half", "halfopen", "semi", "semiopen" },                        { "half", "Half Open" } },
        { { "pedal", "foot", "chick", "pedalclosed" },                       { "pedal", "Pedal" } },
        { { "splashfoot", "footsplash" },                                    { "footsplash", "Foot Splash" } },
        { { "choke", "grab", "choked", "mute" },                             { "choke", "Choke" } },
        { { "flam" },                                                        { "flam", "Flam" } },
        { { "roll", "buzz", "press" },                                       { "roll", "Roll" } },
        { { "ghost" },                                                       { "ghost", "Ghost" } },
        { { "rimclick", "rimonly" },                                         { "rimclick", "Rim Click" } },
    };
    for (auto& row : table)
        if (row.first.contains (w))
            return { row.second.first, row.second.second };
    return {};
}

ParsedName parseSampleName (const juce::String& stem, const juce::StringArray& ignore)
{
    ParsedName out;

    // Take out the drum's own name first ("Tom 1", "tom1", "22 Vintage") so its numbers
    // aren't read as layers or round robins. Matching ignores case; what's left keeps it.
    auto t = tokens (stem);
    for (auto& phrase : ignore)
    {
        auto words = tokens (phrase);
        auto joined = alnumId (phrase);
        for (int i = 0; i < t.size();)
        {
            auto matches = words.size() > 0 && i + words.size() <= t.size() && ! words.joinIntoString ("").containsOnly ("0123456789");
            for (int k = 0; matches && k < words.size(); ++k)
                matches = t[i + k].equalsIgnoreCase (words[k]);
            if (matches)
            {
                t.removeRange (i, words.size());
                continue;
            }
            if (joined.isNotEmpty() && ! joined.containsOnly ("0123456789") && alnumId (t[i]) == joined)
            {
                t.remove (i);
                continue;
            }
            ++i;
        }
    }

    auto tagged = [] (const juce::String& low, const juce::StringArray& prefixes) -> int
    {
        for (auto& p : prefixes)
            if (low.startsWith (p) && low.length() > p.length() && low.substring (p.length()).containsOnly ("0123456789"))
                return low.substring (p.length()).getIntValue();
        return -1;
    };
    static const juce::StringArray layerPrefixes { "velocity", "layer", "velo", "vel", "lay", "dyn", "v", "l" };
    static const juce::StringArray rrPrefixes { "roundrobin", "robin", "take", "rob", "var", "alt", "tk", "rr", "r", "t" };

    juce::StringArray rest;
    std::vector<int> bareNumbers;
    for (int i = 0; i < t.size(); ++i)
    {
        auto low = t[i].toLowerCase();
        auto nextIsNumber = i + 1 < t.size() && t[i + 1].containsOnly ("0123456789");

        if (nextIsNumber && out.layer < 0 && layerPrefixes.contains (low)) { out.layer = t[++i].getIntValue(); continue; }
        if (nextIsNumber && out.rr < 0 && rrPrefixes.contains (low))       { out.rr = t[++i].getIntValue(); continue; }
        if (auto n = tagged (low, rrPrefixes); n >= 0 && out.rr < 0)       { out.rr = n; continue; }
        if (auto n = tagged (low, layerPrefixes); n >= 0 && out.layer < 0) { out.layer = n; continue; }
        if (low.containsOnly ("0123456789"))                               { bareNumbers.push_back (low.getIntValue()); continue; }
        if (ignore.contains (low))
            continue;
        if (auto art = articulationFromWord (low); art.first.isNotEmpty() && out.artic.isEmpty() && ! isGenericMicWord (low))
        {
            out.artic = art.first + "|" + art.second;
            continue;
        }
        rest.add (t[i]);
    }

    // Bare numbers: "Snare Top 3 2" -> layer 3, round robin 2. A single number is a round robin.
    if (out.layer < 0 && out.rr < 0 && bareNumbers.size() >= 2)
    {
        out.layer = bareNumbers[bareNumbers.size() - 2];
        out.rr = bareNumbers.back();
    }
    else if (out.rr < 0 && ! bareNumbers.empty())
        out.rr = bareNumbers.back();
    else if (out.layer < 0 && ! bareNumbers.empty())
        out.layer = bareNumbers.back();

    out.mic = rest.joinIntoString (" ");
    return out;
}

std::shared_ptr<Kit> KitLoader::scan (const juce::File& root, juce::String& error)
{
    if (! root.isDirectory())
    {
        error = "That folder doesn't exist.";
        return nullptr;
    }

    auto kit = std::make_shared<Kit>();
    kit->root = root;
    kit->name = root.getFileName();

    auto manifest = readJson (root.getChildFile ("panda-kit.json"));
    if (manifest.isObject())
        kit->name = str (manifest, "name", kit->name);

    // Pieces: one per folder with audio in it.
    std::map<juce::String, juce::var> manifestPieces;
    if (auto* arr = manifest.getProperty ("pieces", {}).getArray())
        for (auto& p : *arr)
            manifestPieces[str (p, "folder").toLowerCase()] = p;

    std::vector<std::pair<juce::File, PieceType>> folders;
    for (auto& dir : sortedChildren (root, juce::File::findDirectories))
    {
        if (dir.findChildFiles (juce::File::findFiles, true, audioWildcard).isEmpty())
            continue;
        auto mp = manifestPieces.count (dir.getFileName().toLowerCase()) ? manifestPieces[dir.getFileName().toLowerCase()] : juce::var();
        auto type = pieceTypeFromName (mp.isObject() ? str (mp, "type", dir.getFileName()) : dir.getFileName(), PieceType::Perc);
        folders.push_back ({ dir, type });
    }
    if (folders.empty())
    {
        error = "No samples found. Put one folder per drum (Kick, Snare, Tom 1...) inside the kit folder.";
        return nullptr;
    }

    // Toms: rack toms in name order, floor toms last.
    std::stable_sort (folders.begin(), folders.end(), [] (auto& a, auto& b)
    {
        if (a.second == PieceType::Tom && b.second == PieceType::Tom)
        {
            auto fa = a.first.getFileName().containsIgnoreCase ("floor"), fb = b.first.getFileName().containsIgnoreCase ("floor");
            if (fa != fb) return fb;
        }
        return false;
    });

    std::map<PieceType, int> typeCount, typeIndex;
    for (auto& f : folders) typeCount[f.second]++;

    std::map<juce::String, MicDef> micsById;
    std::vector<juce::String> micOrder;

    for (auto& [dir, type] : folders)
    {
        auto mp = manifestPieces.count (dir.getFileName().toLowerCase()) ? manifestPieces[dir.getFileName().toLowerCase()] : juce::var();
        Piece p;
        p.type = type;
        auto n = ++typeIndex[type];
        auto base = juce::String (pieceTypeName (type));
        p.id = str (mp, "id", typeCount[type] > 1 || type == PieceType::Tom ? base + juce::String (n) : base);
        p.name = str (mp, "name", titleCase (dir.getFileName()));
        defaultPan (p, n - 1, typeCount[type]);
        if (mp.hasProperty ("pan"))
            p.pan = (float) mp.getProperty ("pan", 0.0);

        for (auto& vf : findVariants (dir))
        {
            Variant v;
            v.folder = vf.dir;
            v.folderIsPiece = vf.isWholePieceFolder;
            v.name = vf.isWholePieceFolder ? p.name : titleCase (vf.dir.getFileName());
            auto size = sizeFromName (vf.isWholePieceFolder ? dir.getFileName() : vf.dir.getFileName());
            v.sizeInches = size.first;
            v.depthInches = size.second;
            if (auto mv = ManifestPiece { mp }.variantFor (vf.dir.getFileName()); mv.isObject())
            {
                v.name = str (mv, "name", v.name);
                v.sizeInches = (float) mv.getProperty ("size", v.sizeInches);
                v.depthInches = (float) mv.getProperty ("depth", v.depthInches);
                v.naturalHz = (float) mv.getProperty ("pitchHz", 0.0);
            }
            p.variants.push_back (v);

            // Mics this variant was recorded with.
            auto ignore = ignoreWordsFor (p, v);
            for (auto& [file, art] : variantFiles (vf))
            {
                auto parsed = parseSampleName (file.getFileNameWithoutExtension(), ignore);
                juce::String display;
                auto id = micIdFor (p, parsed.mic, &display);
                if (! micsById.count (id))
                {
                    micsById[id] = { id, display, micGroupFromName (display) };
                    micOrder.push_back (id);
                }
            }
        }
        kit->pieces.push_back (p);
    }

    // Mic order on the mixer: close mics in kit order, then overheads, rooms, far rooms.
    auto rank = [] (MicGroup g) { return g == MicGroup::Close ? 0 : g == MicGroup::Other ? 1 : g == MicGroup::Overhead ? 2 : g == MicGroup::RoomClose ? 3 : 4; };
    std::stable_sort (micOrder.begin(), micOrder.end(), [&] (auto& a, auto& b) { return rank (micsById[a].group) < rank (micsById[b].group); });

    if (auto* arr = manifest.getProperty ("mics", {}).getArray())   // the manifest's names and groups win
        for (auto& m : *arr)
        {
            auto id = alnumId (str (m, "id", str (m, "name")));
            if (micsById.count (id))
            {
                micsById[id].name = str (m, "name", micsById[id].name);
                if (m.hasProperty ("group"))
                    micsById[id].group = micGroupFromName (str (m, "group"));
            }
        }

    for (auto& id : micOrder)
        kit->mics.push_back (micsById[id]);
    if (kit->mics.size() > 16)
    {
        error = "This kit has " + juce::String ((int) kit->mics.size()) + " mics; Panda Drums mixes up to 16. The first 16 are used.";
        kit->mics.resize (16);
    }

    // Reference mic: the close mic named after the piece, or the first close mic it was recorded on.
    for (auto& p : kit->pieces)
    {
        auto own = kit->findMic (alnumId (p.name));
        if (own < 0)
            for (size_t m = 0; m < kit->mics.size(); ++m)
                if (kit->mics[m].group == MicGroup::Close && kit->mics[m].id.startsWith (alnumId (p.name)))
                { own = (int) m; break; }
        p.referenceMic = own;
    }
    return kit;
}

std::shared_ptr<const VariantData> KitLoader::loadVariant (const Kit& kit, int pieceIndex, int variantIndex,
                                                           std::function<bool (float)> progress)
{
    if (! juce::isPositiveAndBelow (pieceIndex, (int) kit.pieces.size()))
        return nullptr;
    auto& piece = kit.pieces[(size_t) pieceIndex];
    if (! juce::isPositiveAndBelow (variantIndex, (int) piece.variants.size()))
        return nullptr;
    auto& variant = piece.variants[(size_t) variantIndex];

    VariantFolders vf { variant.folder, variant.folderIsPiece };
    auto files = variantFiles (vf);
    auto ignore = ignoreWordsFor (piece, variant);
    auto formats = makeFormats();

    // Hit identity = the file name without the mic part, so every mic of one strike lands together.
    struct Pending { juce::String articId, articName; int layer = -1, rr = -1; std::map<int, std::array<juce::File, 2>> mics; std::map<int, juce::File> monoMics; juce::String name; };
    std::map<juce::String, Pending> hits;
    std::vector<juce::String> hitOrder;

    for (auto& [file, folderArt] : files)
    {
        auto parsed = parseSampleName (file.getFileNameWithoutExtension(), ignore);
        juce::String display;
        int side = -1;
        auto micId = micIdFor (piece, parsed.mic, &display, &side);
        auto mic = kit.findMic (micId);
        if (mic < 0)
            continue;

        auto art = folderArt.isNotEmpty() ? folderArt : parsed.artic.isNotEmpty() ? parsed.artic : juce::String ("center|Center");
        if (piece.type == PieceType::Kick || piece.type == PieceType::Crash || piece.type == PieceType::Splash || piece.type == PieceType::China)
            if (folderArt.isEmpty() && parsed.artic.isEmpty())
                art = "hit|Hit";
        if (piece.type == PieceType::HiHat && folderArt.isEmpty() && parsed.artic.isEmpty())
            art = "closed|Closed";
        if (piece.type == PieceType::Ride && folderArt.isEmpty() && parsed.artic.isEmpty())
            art = "bow|Bow";

        auto key = art + "#" + juce::String (parsed.layer) + "#" + juce::String (parsed.rr);
        if (parsed.layer < 0 && parsed.rr < 0)
        {
            // No numbers at all: the n-th file of each mic is the n-th hit.
            int n = 0;
            while (hits.count (art + "#n" + juce::String (n)) && (side < 0 ? hits[art + "#n" + juce::String (n)].monoMics.count (mic) : hits[art + "#n" + juce::String (n)].mics.count (mic) && hits[art + "#n" + juce::String (n)].mics[mic][(size_t) side] != juce::File()))
                ++n;
            key = art + "#n" + juce::String (n);
        }
        auto& h = hits[key];
        if (h.articId.isEmpty())
        {
            h.articId = art.upToFirstOccurrenceOf ("|", false, false);
            h.articName = art.fromFirstOccurrenceOf ("|", false, false);
            h.layer = parsed.layer;
            h.rr = parsed.rr;
            h.name = file.getFileNameWithoutExtension();
            hitOrder.push_back (key);
        }
        if (side >= 0) h.mics[mic][(size_t) side] = file;
        else           h.monoMics[mic] = file;
    }

    auto data = std::make_shared<VariantData>();
    std::map<juce::String, size_t> articIndex;
    int done = 0;

    for (auto& key : hitOrder)
    {
        auto& ph = hits[key];
        if (! articIndex.count (ph.articId))
        {
            articIndex[ph.articId] = data->artics.size();
            Articulation a;
            a.id = ph.articId;
            a.name = ph.articName;
            a.isOpen = a.id == "open" || a.id == "half" || a.id == "footsplash";
            a.closes = piece.type == PieceType::HiHat && (a.id == "closed" || a.id == "pedal");
            a.chokesAll = a.id == "choke";
            data->artics.push_back (a);
        }
        Hit hit;
        hit.mics.resize (kit.mics.size());
        hit.fileLayer = ph.layer;
        hit.fileRR = ph.rr;
        hit.name = ph.name;

        auto read = [&] (const juce::File& f, juce::AudioBuffer<float>& into, int channelOffset) -> bool
        {
            std::unique_ptr<juce::AudioFormatReader> r (formats->createReaderFor (f));
            if (r == nullptr || r->lengthInSamples <= 0 || r->lengthInSamples > (juce::int64) (r->sampleRate * 60))
                return false;
            auto len = (int) r->lengthInSamples;
            if (into.getNumSamples() < len)
                into.setSize (into.getNumChannels(), len, true, true);
            juce::AudioBuffer<float> tmp ((int) r->numChannels, len);
            r->read (&tmp, 0, len, 0, true, true);
            auto chans = into.getNumChannels() - channelOffset;
            for (int c = 0; c < std::min (chans, (int) r->numChannels); ++c)
                into.copyFrom (channelOffset + c, 0, tmp, c, 0, len);
            hit.sampleRate = r->sampleRate;
            return true;
        };

        for (auto& [mic, file] : ph.monoMics)
        {
            std::unique_ptr<juce::AudioFormatReader> r (formats->createReaderFor (file));
            if (r == nullptr) continue;
            auto b = std::make_shared<juce::AudioBuffer<float>> (juce::jlimit (1, 2, (int) r->numChannels), 0);
            r.reset();
            if (read (file, *b, 0))
                hit.mics[(size_t) mic] = b;
        }
        for (auto& [mic, pair] : ph.mics)
        {
            auto b = std::make_shared<juce::AudioBuffer<float>> (2, 0);
            bool ok = false;
            for (int s = 0; s < 2; ++s)
                if (pair[(size_t) s] != juce::File())
                {
                    juce::AudioBuffer<float> one (1, 0);
                    if (read (pair[(size_t) s], one, 0))
                    {
                        if (b->getNumSamples() < one.getNumSamples())
                            b->setSize (2, one.getNumSamples(), true, true);
                        b->copyFrom (s, 0, one, 0, 0, one.getNumSamples());
                        ok = true;
                    }
                }
            if (ok)
                hit.mics[(size_t) mic] = b;
        }

        for (auto& m : hit.mics)
            if (m != nullptr)
                data->bytes += (size_t) m->getNumSamples() * (size_t) m->getNumChannels() * sizeof (float);

        measureHit (hit, piece.referenceMic);
        if (hit.length > 0)
            data->artics[articIndex[ph.articId]].hits.push_back (std::move (hit));

        ++done;
        if (progress && ! progress ((float) done / (float) hitOrder.size()))
            return nullptr;
    }

    // Center first, then the order articulations usually come in.
    static const juce::StringArray order { "hit", "center", "closed", "bow", "rim", "sidestick", "open", "half", "pedal", "bell", "edge", "choke" };
    std::stable_sort (data->artics.begin(), data->artics.end(), [] (auto& a, auto& b)
    {
        auto ia = order.indexOf (a.id), ib = order.indexOf (b.id);
        return (ia < 0 ? 99 : ia) < (ib < 0 ? 99 : ib);
    });

    if (isTunable (piece.type))
        data->detectedHz = detectVariantPitch (*data, piece.referenceMic);
    return data;
}

bool KitLoader::writeManifestTemplate (const Kit& kit, const juce::File& f)
{
    auto* root = new juce::DynamicObject();
    root->setProperty ("name", kit.name);

    juce::Array<juce::var> mics;
    for (auto& m : kit.mics)
    {
        auto* o = new juce::DynamicObject();
        o->setProperty ("id", m.id);
        o->setProperty ("name", m.name);
        o->setProperty ("group", micGroupName (m.group));
        mics.add (juce::var (o));
    }
    root->setProperty ("mics", mics);

    juce::Array<juce::var> pieces;
    for (auto& p : kit.pieces)
    {
        auto* o = new juce::DynamicObject();
        o->setProperty ("folder", p.variants.empty() ? p.name : (p.variants.front().folder.getParentDirectory() == kit.root ? p.variants.front().folder.getFileName() : p.variants.front().folder.getParentDirectory().getFileName()));
        o->setProperty ("id", p.id);
        o->setProperty ("name", p.name);
        o->setProperty ("type", pieceTypeName (p.type));
        o->setProperty ("pan", p.pan);
        juce::Array<juce::var> vars;
        for (auto& v : p.variants)
        {
            auto* vo = new juce::DynamicObject();
            vo->setProperty ("folder", v.folder.getFileName());
            vo->setProperty ("name", v.name);
            vo->setProperty ("size", v.sizeInches);
            if (v.depthInches > 0) vo->setProperty ("depth", v.depthInches);
            vo->setProperty ("pitchHz", v.naturalHz);
            vars.add (juce::var (vo));
        }
        o->setProperty ("variants", vars);
        pieces.add (juce::var (o));
    }
    root->setProperty ("pieces", pieces);
    return f.replaceWithText (juce::JSON::toString (juce::var (root)));
}
} // namespace pd
