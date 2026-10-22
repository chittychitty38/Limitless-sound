#include "PluginProcessor.h"
#include "PluginEditor.h"

using namespace pd;

namespace
{
std::shared_ptr<Kit> sharedFactoryKit()
{
    // One factory kit per process, shared by every instance of the plugin.
    static std::mutex lock;
    static std::weak_ptr<Kit> weak;
    std::lock_guard<std::mutex> l (lock);
    auto k = weak.lock();
    if (k == nullptr)
    {
        k = FactoryKit::create();
        weak = k;
    }
    return k;
}

float defaultNaturalHz (PieceType t)
{
    switch (t)
    {
        case PieceType::Kick:  return 52.0f;
        case PieceType::Snare: return 200.0f;
        case PieceType::Tom:   return 130.0f;
        case PieceType::HiHat:
        case PieceType::Crash:
        case PieceType::Ride:
        case PieceType::China:
        case PieceType::Splash:
        case PieceType::Perc:  return 300.0f;
    }
    return 300.0f;
}

juce::NormalisableRange<float> dbRange() { return { -60.0f, 12.0f, 0.1f, 2.5f }; }
} // namespace

juce::AudioProcessorValueTreeState::ParameterLayout PandaDrumsProcessor::createLayout()
{
    using namespace juce;
    AudioProcessorValueTreeState::ParameterLayout layout;
    auto db = [] (float v, int) { return v <= -59.9f ? String ("-inf") : String (v, 1) + " dB"; };

    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "master", 1 }, "Master", dbRange(), 0.0f,
                                                       AudioParameterFloatAttributes().withStringFromValueFunction (db)));
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "masterPanda", 1 }, "Master Panda FX", NormalisableRange<float> (0.0f, 1.0f), 0.0f));
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "velCurve", 1 }, "Velocity Curve", NormalisableRange<float> (-1.0f, 1.0f), 0.0f));
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "dynamics", 1 }, "Velocity Build", NormalisableRange<float> (0.0f, 1.0f), 0.85f));
    layout.add (std::make_unique<AudioParameterFloat> (ParameterID { "humanize", 1 }, "Humanize", NormalisableRange<float> (0.0f, 1.0f), 0.0f));
    layout.add (std::make_unique<AudioParameterChoice> (ParameterID { "rrMode", 1 }, "Round Robin",
                                                        StringArray { "Cycle", "Random, no repeats", "Random" }, 0));

    for (int c = 0; c < maxMics; ++c)
    {
        auto n = "Channel " + String (c + 1) + " ";
        layout.add (std::make_unique<AudioParameterFloat> (ParameterID { chParam (c, "Vol"), 1 }, n + "Volume", dbRange(), 0.0f,
                                                           AudioParameterFloatAttributes().withStringFromValueFunction (db)));
        layout.add (std::make_unique<AudioParameterFloat> (ParameterID { chParam (c, "Pan"), 1 }, n + "Pan", NormalisableRange<float> (-1.0f, 1.0f), 0.0f));
        layout.add (std::make_unique<AudioParameterBool> (ParameterID { chParam (c, "Mute"), 1 }, n + "Mute", false));
        layout.add (std::make_unique<AudioParameterBool> (ParameterID { chParam (c, "Solo"), 1 }, n + "Solo", false));
        layout.add (std::make_unique<AudioParameterFloat> (ParameterID { chParam (c, "Panda"), 1 }, n + "Panda FX", NormalisableRange<float> (0.0f, 1.0f), 0.0f));
    }
    for (int p = 0; p < maxPieces; ++p)
    {
        auto n = "Drum " + String (p + 1) + " ";
        layout.add (std::make_unique<AudioParameterFloat> (ParameterID { pieceParam (p, "Vol"), 1 }, n + "Volume", dbRange(), 0.0f,
                                                           AudioParameterFloatAttributes().withStringFromValueFunction (db)));
        layout.add (std::make_unique<AudioParameterFloat> (ParameterID { pieceParam (p, "Tune"), 1 }, n + "Tune",
                                                           NormalisableRange<float> (-12.0f, 12.0f, 0.01f), 0.0f,
                                                           AudioParameterFloatAttributes().withStringFromValueFunction ([] (float v, int) { return String (v, 2) + " st"; })));
        layout.add (std::make_unique<AudioParameterFloat> (ParameterID { pieceParam (p, "Decay"), 1 }, n + "Decay", NormalisableRange<float> (0.05f, 1.0f), 1.0f));
    }
    return layout;
}

PandaDrumsProcessor::PandaDrumsProcessor()
    : AudioProcessor (BusesProperties().withOutput ("Output", juce::AudioChannelSet::stereo(), true)),
      params (*this, nullptr, "PandaDrums", createLayout())
{
    masterDb = params.getRawParameterValue ("master");
    masterPanda = params.getRawParameterValue ("masterPanda");
    velCurve = params.getRawParameterValue ("velCurve");
    dynamics = params.getRawParameterValue ("dynamics");
    humanize = params.getRawParameterValue ("humanize");
    rrMode = params.getRawParameterValue ("rrMode");
    for (int c = 0; c < maxMics; ++c)
        chPtr[(size_t) c] = { params.getRawParameterValue (chParam (c, "Vol")), params.getRawParameterValue (chParam (c, "Pan")),
                              params.getRawParameterValue (chParam (c, "Mute")), params.getRawParameterValue (chParam (c, "Solo")),
                              params.getRawParameterValue (chParam (c, "Panda")) };
    for (int p = 0; p < maxPieces; ++p)
        pcPtr[(size_t) p] = { params.getRawParameterValue (pieceParam (p, "Vol")), params.getRawParameterValue (pieceParam (p, "Tune")),
                              params.getRawParameterValue (pieceParam (p, "Decay")) };
    for (auto& row : bleed)
        for (auto& b : row)
            b.store (1.0f);

    map = presetMaps().front();
    key = Key { 0, 0 };   // off until the song's key is chosen
    loadFactoryKit();
}

PandaDrumsProcessor::~PandaDrumsProcessor()
{
    alive->store (false);
    cancelPendingUpdate();
    loaderPool.removeAllJobs (true, 20000);
}

//==============================================================================
bool PandaDrumsProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    auto out = layouts.getMainOutputChannelSet();
    return out == juce::AudioChannelSet::stereo() || out == juce::AudioChannelSet::mono();
}

void PandaDrumsProcessor::prepareToPlay (double sampleRate, int samplesPerBlock)
{
    currentSampleRate = sampleRate;
    currentBlock = samplesPerBlock;
    auto capacity = std::max (samplesPerBlock, 2048);
    micBuses.setSize (2 * maxMics, capacity);
    mixBuffer.setSize (2, capacity);
    delayBuffer.setSize (2, (int) (0.2 * sampleRate) + capacity);
    delayBuffer.clear();
    delayWrite = 0;
    sampler.prepare (sampleRate, samplesPerBlock);
    mixer.prepare (sampleRate, samplesPerBlock);
    setLatencySamples (getShowtimeLatency());
}

void PandaDrumsProcessor::updateEngineParams()
{
    auto toGain = [] (float db) { return db <= -59.9f ? 0.0f : juce::Decibels::decibelsToGain (db); };
    for (int p = 0; p < maxPieces; ++p)
    {
        auto& pp = engineParams.pieces[(size_t) p];
        pp.gain = toGain (pcPtr[(size_t) p].vol->load());
        pp.semis = pcPtr[(size_t) p].tune->load();
        pp.decay = pcPtr[(size_t) p].decay->load();
        for (int m = 0; m < maxMics; ++m)
            engineParams.bleed[(size_t) p][(size_t) m] = bleed[(size_t) p][(size_t) m].load();
    }
    engineParams.velocityCurve = velCurve->load();
    engineParams.dynamics = dynamics->load();
    engineParams.humanize = humanize->load();
    engineParams.rrMode = (int) rrMode->load();

    for (int c = 0; c < maxMics; ++c)
    {
        auto& ch = mixParams.channels[(size_t) c];
        ch.gain = toGain (chPtr[(size_t) c].vol->load());
        ch.pan = chPtr[(size_t) c].pan->load();
        ch.mute = chPtr[(size_t) c].mute->load() > 0.5f;
        ch.solo = chPtr[(size_t) c].solo->load() > 0.5f;
        ch.panda = chPtr[(size_t) c].panda->load();
    }
    mixParams.master = toGain (masterDb->load());
    mixParams.masterPanda = masterPanda->load();
}

void PandaDrumsProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;
    auto num = buffer.getNumSamples();

    if (auto* ph = getPlayHead())
        if (auto pos = ph->getPosition())
        {
            if (auto bpm = pos->getBpm()) hostBpm.store (*bpm);
            if (auto ppq = pos->getPpqPosition()) hostPpq.store (*ppq);
            hostPlaying.store (pos->getIsPlaying());
        }
    blockWallMs.store (juce::Time::getMillisecondCounterHiRes());
    blockClock.store (clock);

    if (learnArmed.load())
        for (const auto meta : midi)
            if (meta.getMessage().isNoteOn())
            {
                learnedNote.store (meta.getMessage().getNoteNumber());
                learnArmed.store (false);
                break;
            }

    if (num > micBuses.getNumSamples())   // a host sent more than it promised
    {
        micBuses.setSize (2 * maxMics, num, false, false, true);
        mixBuffer.setSize (2, num, false, false, true);
    }
    micBuses.clear (0, num);

    updateEngineParams();
    auto* snap = exchange.acquire();
    if (snap != nullptr)
    {
        sampler.process (*snap, engineParams, midi, micBuses, num, clock, playRequests, hitEvents);
        mixer.process (micBuses, (int) snap->micIsStereo.size(), snap->micIsStereo, mixParams, mixBuffer, num);
    }
    else
        mixBuffer.clear (0, num);

    // Showtime delay.
    auto latency = getLatencySamples();
    auto outChans = buffer.getNumChannels();
    for (int c = 0; c < outChans; ++c)
    {
        auto* src = mixBuffer.getReadPointer (std::min (c, 1));
        auto* dst = buffer.getWritePointer (c);
        if (latency <= 0)
        {
            if (outChans == 1)
                for (int i = 0; i < num; ++i) dst[i] = 0.5f * (mixBuffer.getSample (0, i) + mixBuffer.getSample (1, i));
            else
                juce::FloatVectorOperations::copy (dst, src, num);
            continue;
        }
        auto size = delayBuffer.getNumSamples();
        auto* d = delayBuffer.getWritePointer (std::min (c, 1));
        for (int i = 0; i < num; ++i)
        {
            auto w = (delayWrite + i) % size;
            d[w] = src[i];
            dst[i] = d[(w - latency + size) % size];
        }
    }
    if (latency > 0)
        delayWrite = (delayWrite + num) % delayBuffer.getNumSamples();

    clock += num;
    activeVoices.store (sampler.activeVoices());
    midi.clear();
}

//==============================================================================
void PandaDrumsProcessor::setParam (const juce::String& id, float value)
{
    if (auto* p = params.getParameter (id))
    {
        p->beginChangeGesture();
        p->setValueNotifyingHost (p->convertTo0to1 (value));
        p->endChangeGesture();
    }
}

void PandaDrumsProcessor::play (int piece, int artic, int velocity, int hit, float semis)
{
    PlayRequest r;
    r.piece = (juce::int16) piece;
    r.artic = (juce::int16) artic;
    r.hit = (juce::int16) hit;
    r.velocity = (juce::int16) juce::jlimit (1, 127, velocity);
    r.semis = semis;
    playRequests.push (r);
}

void PandaDrumsProcessor::playNote (int note, int velocity)
{
    auto snap = getSnapshot();
    if (snap == nullptr || ! juce::isPositiveAndBelow (note, 128))
        return;
    if (snap->chromaticOn && note >= snap->chromaticLow && note <= snap->chromaticHigh && snap->chromaticPiece >= 0)
    {
        auto p = snap->chromaticPiece;
        auto natural = getNaturalMidi (p);
        auto target = chromaticTarget (note, natural, snap->chromaticLow, snap->chromaticHigh);
        if (snap->chromaticSnap)
            target = (float) nearestInKey (key, target);
        play (p, 0, velocity, -1, target - natural - getTune (p));
        return;
    }
    if (auto r = snap->notes[(size_t) note]; r.piece >= 0)
        play (r.piece, r.artic, velocity);
}

PandaDrumsProcessor::Transport PandaDrumsProcessor::getTransport() const
{
    return { hostBpm.load(), hostPpq.load(), hostPlaying.load() };
}

void PandaDrumsProcessor::setShowtime (bool on)
{
    showtime = on;
    setLatencySamples (getShowtimeLatency());
    delayBuffer.clear();
}

//==============================================================================
void PandaDrumsProcessor::loadFactoryKit()
{
    kitFolder = juce::File();
    setKit (sharedFactoryKit());
}

void PandaDrumsProcessor::loadKitFolder (const juce::File& folder)
{
    {
        const juce::ScopedLock sl (messageLock);
        loadMessage = "Reading " + folder.getFileName() + "...";
    }
    ++pendingLoads;
    sendChangeMessage();
    auto token = alive;
    loaderPool.addJob ([this, token, folder]
    {
        juce::String error;
        auto k = KitLoader::scan (folder, error);
        juce::MessageManager::callAsync ([this, token, k, folder, error]
        {
            if (! token->load())
                return;
            --pendingLoads;
            {
                const juce::ScopedLock sl (messageLock);
                loadMessage = error;
            }
            if (k != nullptr)
            {
                kitFolder = folder;
                setKit (k);
            }
            sendChangeMessage();
        });
    });
}

void PandaDrumsProcessor::reloadKit()
{
    if (kitFolder.isDirectory())
        loadKitFolder (kitFolder);
}

juce::String PandaDrumsProcessor::getLoadMessage() const
{
    const juce::ScopedLock sl (messageLock);
    return loadMessage;
}

void PandaDrumsProcessor::setKit (std::shared_ptr<Kit> k, const std::map<juce::String, juce::String>& variantNames)
{
    kit = std::move (k);
    selected.assign (kit->pieces.size(), 0);
    for (size_t p = 0; p < kit->pieces.size(); ++p)
    {
        auto& piece = kit->pieces[p];
        selected[p] = FactoryKit::defaultVariant (*kit, (int) p);
        if (auto it = variantNames.find (piece.id); it != variantNames.end())
            for (size_t v = 0; v < piece.variants.size(); ++v)
                if (piece.variants[v].name == it->second)
                    selected[p] = (int) v;
        requestLoad ((int) p, selected[p]);
    }
    if (chromatic.pieceId.isEmpty() || kit->findPiece (chromatic.pieceId) < 0)
        for (auto& p : kit->pieces)
            if (p.type == PieceType::Tom)
                chromatic.pieceId = p.id;   // the lowest tom
    rebuildSnapshot();
    sendChangeMessage();
}

std::shared_ptr<const VariantData> PandaDrumsProcessor::loadNow (const Kit& k, int piece, int variant)
{
    return k.isFactory ? FactoryKit::render (k, piece, variant) : KitLoader::loadVariant (k, piece, variant);
}

void PandaDrumsProcessor::requestLoad (int piece, int variant)
{
    if (kit == nullptr || kit->getLoaded (piece, variant) != nullptr)
        return;
    ++pendingLoads;
    auto token = alive;
    auto k = kit;
    loaderPool.addJob ([this, token, k, piece, variant]
    {
        if (k->getLoaded (piece, variant) == nullptr)
            if (auto data = loadNow (*k, piece, variant))
                k->setLoaded (piece, variant, data);
        --pendingLoads;
        if (token->load())
            triggerAsyncUpdate();
    });
}

void PandaDrumsProcessor::loadSelectedVariantsNow()
{
    for (size_t p = 0; p < selected.size(); ++p)
        if (kit->getLoaded ((int) p, selected[p]) == nullptr)
            if (auto data = loadNow (*kit, (int) p, selected[p]))
                kit->setLoaded ((int) p, selected[p], data);
    rebuildSnapshot();
}

void PandaDrumsProcessor::handleAsyncUpdate()
{
    rebuildSnapshot();
    sendChangeMessage();
}

int PandaDrumsProcessor::getSelectedVariant (int piece) const
{
    return juce::isPositiveAndBelow (piece, (int) selected.size()) ? selected[(size_t) piece] : 0;
}

void PandaDrumsProcessor::selectVariant (int piece, int variant)
{
    if (kit == nullptr || ! juce::isPositiveAndBelow (piece, (int) kit->pieces.size()))
        return;
    auto count = (int) kit->pieces[(size_t) piece].variants.size();
    if (count == 0)
        return;
    variant = ((variant % count) + count) % count;
    selected[(size_t) piece] = variant;
    requestLoad (piece, variant);
    rebuildSnapshot();
    // In a key, the new drum goes straight onto a note of it (its own nearest one, so a bigger
    // drum still sounds bigger).
    if (isTunable (kit->pieces[(size_t) piece].type) && ! key.isOff())
    {
        if (autoTuneToKey)
            tuneKitToKey();
        else
            setTune (piece, (float) nearestInKey (key, getNaturalMidi (piece)) - getNaturalMidi (piece));
    }
    sendChangeMessage();
}

void PandaDrumsProcessor::stepVariant (int piece, int direction)
{
    selectVariant (piece, getSelectedVariant (piece) + (direction >= 0 ? 1 : -1));
}

std::vector<std::shared_ptr<const VariantData>> PandaDrumsProcessor::selectedData() const
{
    std::vector<std::shared_ptr<const VariantData>> out;
    if (kit != nullptr)
        for (size_t p = 0; p < kit->pieces.size(); ++p)
            out.push_back (kit->getLoaded ((int) p, selected[p]));
    return out;
}

void PandaDrumsProcessor::rebuildSnapshot()
{
    if (kit == nullptr)
        return;
    auto s = std::make_shared<EngineSnapshot>();
    s->kit = kit;
    s->generation = ++generation;
    s->key = key;

    auto data = selectedData();
    for (size_t p = 0; p < kit->pieces.size(); ++p)
    {
        auto& piece = kit->pieces[p];
        EngineSnapshot::PieceRT rt;
        rt.type = piece.type;
        rt.variant = selected[p];
        rt.data = data[p];
        rt.pan = piece.pan;
        if (rt.data != nullptr)
            for (size_t a = 0; a < rt.data->artics.size(); ++a)
            {
                auto& art = rt.data->artics[a];
                rt.layouts.push_back (layoutArticulation (art, zoneSettings));
                std::vector<char> off (art.hits.size(), 0);
                for (size_t h = 0; h < art.hits.size(); ++h)
                    off[h] = badHits.count (hitKey (*kit, (int) p, selected[p], (int) a, (int) h)) ? 1 : 0;
                rt.disabled.push_back (std::move (off));
            }
        s->pieces.push_back (std::move (rt));
    }
    for (size_t p = 0; p < s->pieces.size(); ++p)
        s->pieces[p].naturalMidi = getNaturalMidi ((int) p);

    s->notes = resolveMap (map, *kit, data);

    // A mic is stereo on the mixer unless it is a close mic recorded in mono.
    s->micIsStereo.assign (kit->mics.size(), 0);
    for (size_t m = 0; m < kit->mics.size(); ++m)
    {
        auto stereo = kit->mics[m].group != MicGroup::Close && kit->mics[m].group != MicGroup::Other;
        for (auto& d : data)
            if (d != nullptr && ! stereo)
                for (auto& a : d->artics)
                    for (auto& h : a.hits)
                        if (m < h.mics.size() && h.mics[m] != nullptr && h.mics[m]->getNumChannels() > 1)
                            stereo = true;
        s->micIsStereo[m] = stereo ? 1 : 0;
    }

    s->chromaticOn = chromatic.on;
    s->chromaticPiece = kit->findPiece (chromatic.pieceId);
    s->chromaticLow = chromatic.low;
    s->chromaticHigh = chromatic.high;
    s->chromaticSnap = chromatic.snap;

    s->prepareCounters();
    exchange.publish (s);
}

//==============================================================================
float PandaDrumsProcessor::getNaturalMidi (int piece) const
{
    if (kit == nullptr || ! juce::isPositiveAndBelow (piece, (int) kit->pieces.size()))
        return 48.0f;
    auto& p = kit->pieces[(size_t) piece];
    auto v = getSelectedVariant (piece);
    float hz = 0.0f;
    if (juce::isPositiveAndBelow (v, (int) p.variants.size()))
        hz = p.variants[(size_t) v].naturalHz;
    if (hz <= 0.0f)
        if (auto d = kit->getLoaded (piece, v))
            hz = d->detectedHz;
    if (hz <= 0.0f)
        hz = defaultNaturalHz (p.type);
    return hzToMidi (hz);
}

float PandaDrumsProcessor::getTune (int piece) const
{
    if (! juce::isPositiveAndBelow (piece, maxPieces))
        return 0.0f;
    return pcPtr[(size_t) piece].tune->load();
}

void PandaDrumsProcessor::setTune (int piece, float semis)
{
    if (juce::isPositiveAndBelow (piece, maxPieces))
        setParam (pieceParam (piece, "Tune"), juce::jlimit (-12.0f, 12.0f, semis));
}

void PandaDrumsProcessor::stepPitch (int piece, int direction)
{
    auto natural = getNaturalMidi (piece);
    auto target = (float) stepInKey (key, natural + getTune (piece), direction);
    if (std::abs (target - natural) <= 12.0f)
        setTune (piece, target - natural);
    sendChangeMessage();
}

bool PandaDrumsProcessor::pitchInKey (int piece) const
{
    auto pitch = getPitch (piece);
    auto nearest = (int) std::lround (pitch);
    return std::abs (pitch - (float) nearest) < 0.12f && key.contains (nearest);
}

void PandaDrumsProcessor::tuneKitToKey()
{
    if (kit == nullptr || key.isOff())
        return;
    std::vector<int> which;
    std::vector<float> naturals;
    for (size_t p = 0; p < kit->pieces.size() && p < (size_t) maxPieces; ++p)
        if (isTunable (kit->pieces[p].type))
        {
            which.push_back ((int) p);
            naturals.push_back (getNaturalMidi ((int) p));
        }
    auto shifts = tuneToKey (key, naturals);
    for (size_t i = 0; i < which.size(); ++i)
        setTune (which[i], shifts[i]);
}

void PandaDrumsProcessor::setKey (Key k)
{
    key = k;
    if (autoTuneToKey && ! key.isOff())
        tuneKitToKey();
    rebuildSnapshot();
    sendChangeMessage();
}

void PandaDrumsProcessor::setChromatic (const Chromatic& c)
{
    chromatic = c;
    chromatic.low = juce::jlimit (0, 127, chromatic.low);
    chromatic.high = juce::jlimit (chromatic.low, 127, chromatic.high);
    rebuildSnapshot();
    sendChangeMessage();
}

//==============================================================================
void PandaDrumsProcessor::setZoneSettings (const ZoneSettings& z)
{
    zoneSettings = z;
    rebuildSnapshot();
    sendChangeMessage();
}

bool PandaDrumsProcessor::isBad (int piece, int artic, int hit) const
{
    return kit != nullptr && badHits.count (hitKey (*kit, piece, getSelectedVariant (piece), artic, hit)) > 0;
}

void PandaDrumsProcessor::setBad (int piece, int artic, int hit, bool bad)
{
    if (kit == nullptr)
        return;
    auto k = hitKey (*kit, piece, getSelectedVariant (piece), artic, hit);
    if (bad) badHits.insert (k);
    else     badHits.erase (k);
    rebuildSnapshot();
    sendChangeMessage();
}

void PandaDrumsProcessor::clearBad()
{
    badHits.clear();
    rebuildSnapshot();
    sendChangeMessage();
}

juce::String PandaDrumsProcessor::buildBadList() const
{
    juce::String s;
    s << "Panda Drums - samples marked bad - " << (kit != nullptr ? kit->name : juce::String()) << "\n";
    s << juce::Time::getCurrentTime().toString (true, true) << "\n\n";
    for (auto& k : badHits)
        s << k << "\n";
    if (badHits.empty())
        s << "(none)\n";
    return s;
}

juce::String PandaDrumsProcessor::buildReport() const
{
    auto snap = getSnapshot();
    juce::String s;
    if (snap == nullptr || kit == nullptr)
        return s;
    s << "Panda Drums sample report - " << kit->name << " - " << juce::Time::getCurrentTime().toString (true, true) << "\n";
    s << "Zones from " << (zoneSettings.source == ZoneSettings::Source::FileNames ? "file names" : "loudness")
      << ", lanes " << (zoneSettings.ranges == ZoneSettings::Ranges::Even ? "even" : "by loudness")
      << ", level match " << juce::roundToInt (zoneSettings.levelMatch * 100.0f) << "%\n";
    s << "Mics: ";
    for (size_t m = 0; m < kit->mics.size(); ++m)
        s << (m > 0 ? ", " : "") << kit->mics[m].name << " (" << micGroupName (kit->mics[m].group) << ")";
    s << "\n";

    for (size_t p = 0; p < snap->pieces.size(); ++p)
    {
        auto& rt = snap->pieces[p];
        if (rt.data == nullptr)
            continue;
        auto& piece = kit->pieces[p];
        for (size_t a = 0; a < rt.data->artics.size(); ++a)
        {
            auto& art = rt.data->artics[a];
            auto& lay = rt.layouts[a];
            s << "\n" << piece.name.toUpperCase() << " - " << piece.variants[(size_t) rt.variant].name << " - " << art.name
              << "   (" << (int) art.hits.size() << " hits, " << (int) lay.zones.size() << " zones)\n";
            for (size_t z = 0; z < lay.zones.size(); ++z)
            {
                auto& zone = lay.zones[z];
                s << "  Zone " << (int) z + 1 << "  velocity " << zone.lo << "-" << zone.hi << "  level " << juce::String (zone.refDb, 1) << " dB\n";
                for (size_t r = 0; r < zone.hits.size(); ++r)
                {
                    auto h = zone.hits[r];
                    auto& hit = art.hits[(size_t) h];
                    s << "    RR " << (int) r + 1 << "  " << hit.name.paddedRight (' ', 34) << juce::String (hit.rmsDb, 1).paddedLeft (' ', 7) << " dB"
                      << "  match " << juce::String (juce::Decibels::gainToDecibels (lay.hitGain[(size_t) h]), 1) << " dB"
                      << (rt.disabled[a][(size_t) h] ? "   << BAD" : "") << "\n";
                }
            }
        }
    }
    return s;
}

//==============================================================================
void PandaDrumsProcessor::setMap (const MidiMap& m)
{
    map = m;
    rebuildSnapshot();
    sendChangeMessage();
}

std::array<ResolvedNote, 128> PandaDrumsProcessor::getResolvedNotes() const
{
    if (auto s = getSnapshot())
        return s->notes;
    return {};
}

float PandaDrumsProcessor::getBleedDb (int piece, int mic) const
{
    if (! juce::isPositiveAndBelow (piece, maxPieces) || ! juce::isPositiveAndBelow (mic, maxMics))
        return 0.0f;
    return juce::Decibels::gainToDecibels (bleed[(size_t) piece][(size_t) mic].load(), -60.0f);
}

void PandaDrumsProcessor::setBleedDb (int piece, int mic, float db)
{
    if (! juce::isPositiveAndBelow (piece, maxPieces) || ! juce::isPositiveAndBelow (mic, maxMics))
        return;
    bleed[(size_t) piece][(size_t) mic].store (db <= -59.9f ? 0.0f : juce::Decibels::decibelsToGain (db));
}

//==============================================================================
void PandaDrumsProcessor::getStateInformation (juce::MemoryBlock& dest)
{
    juce::ValueTree root ("PandaDrums");
    root.setProperty ("version", PANDA_VERSION_STRING, nullptr);
    root.appendChild (params.copyState(), nullptr);

    juce::ValueTree k ("Kit");
    k.setProperty ("path", kitFolder.getFullPathName(), nullptr);
    if (kit != nullptr)
        for (size_t p = 0; p < kit->pieces.size(); ++p)
        {
            juce::ValueTree v ("Variant");
            v.setProperty ("piece", kit->pieces[p].id, nullptr);
            v.setProperty ("name", kit->pieces[p].variants[(size_t) selected[p]].name, nullptr);
            k.appendChild (v, nullptr);
        }
    root.appendChild (k, nullptr);

    juce::ValueTree ky ("Key");
    ky.setProperty ("root", key.root, nullptr);
    ky.setProperty ("scale", key.scale, nullptr);
    ky.setProperty ("autoTune", autoTuneToKey, nullptr);
    root.appendChild (ky, nullptr);

    juce::ValueTree ch ("Chromatic");
    ch.setProperty ("on", chromatic.on, nullptr);
    ch.setProperty ("piece", chromatic.pieceId, nullptr);
    ch.setProperty ("low", chromatic.low, nullptr);
    ch.setProperty ("high", chromatic.high, nullptr);
    ch.setProperty ("snap", chromatic.snap, nullptr);
    root.appendChild (ch, nullptr);

    juce::ValueTree z ("Zones");
    z.setProperty ("source", (int) zoneSettings.source, nullptr);
    z.setProperty ("ranges", (int) zoneSettings.ranges, nullptr);
    z.setProperty ("count", zoneSettings.zoneCount, nullptr);
    z.setProperty ("levelMatch", zoneSettings.levelMatch, nullptr);
    root.appendChild (z, nullptr);

    juce::ValueTree m ("Map");
    m.setProperty ("json", juce::JSON::toString (map.toVar(), true), nullptr);
    root.appendChild (m, nullptr);

    juce::ValueTree bad ("Bad");
    for (auto& h : badHits)
    {
        juce::ValueTree e ("Hit");
        e.setProperty ("key", h, nullptr);
        bad.appendChild (e, nullptr);
    }
    root.appendChild (bad, nullptr);

    juce::ValueTree bl ("Bleed");
    if (kit != nullptr)
        for (size_t p = 0; p < kit->pieces.size() && p < (size_t) maxPieces; ++p)
            for (size_t mic = 0; mic < kit->mics.size() && mic < (size_t) maxMics; ++mic)
                if (std::abs (getBleedDb ((int) p, (int) mic)) > 0.05f)
                {
                    juce::ValueTree e ("B");
                    e.setProperty ("piece", kit->pieces[p].id, nullptr);
                    e.setProperty ("mic", kit->mics[mic].id, nullptr);
                    e.setProperty ("db", getBleedDb ((int) p, (int) mic), nullptr);
                    bl.appendChild (e, nullptr);
                }
    root.appendChild (bl, nullptr);

    juce::ValueTree prefs ("Prefs");
    prefs.setProperty ("showtime", showtime, nullptr);
    prefs.setProperty ("showHitInfo", showHitInfo, nullptr);
    prefs.setProperty ("comicFx", comicFx, nullptr);
    root.appendChild (prefs, nullptr);
    root.appendChild (uiState.createCopy(), nullptr);

    if (auto xml = root.createXml())
        copyXmlToBinary (*xml, dest);
}

void PandaDrumsProcessor::setStateInformation (const void* data, int size)
{
    auto xml = getXmlFromBinary (data, size);
    if (xml == nullptr)
        return;
    auto root = juce::ValueTree::fromXml (*xml);
    if (! root.hasType ("PandaDrums"))
        return;

    auto apply = [this, root]
    {
        if (auto p = root.getChildWithName (params.state.getType()); p.isValid())
            params.replaceState (p);

        auto ky = root.getChildWithName ("Key");
        key = Key { (int) ky.getProperty ("root", 0), (int) ky.getProperty ("scale", 0) };
        autoTuneToKey = (bool) ky.getProperty ("autoTune", true);

        auto ch = root.getChildWithName ("Chromatic");
        if (ch.isValid())
            chromatic = { (bool) ch.getProperty ("on", true), ch.getProperty ("piece", "tom3").toString(),
                          (int) ch.getProperty ("low", 72), (int) ch.getProperty ("high", 95), (bool) ch.getProperty ("snap", true) };

        auto z = root.getChildWithName ("Zones");
        if (z.isValid())
        {
            zoneSettings.source = (ZoneSettings::Source) (int) z.getProperty ("source", 0);
            zoneSettings.ranges = (ZoneSettings::Ranges) (int) z.getProperty ("ranges", 0);
            zoneSettings.zoneCount = (int) z.getProperty ("count", 0);
            zoneSettings.levelMatch = (float) z.getProperty ("levelMatch", 0.0);
        }

        auto m = root.getChildWithName ("Map");
        if (m.isValid())
        {
            auto parsed = juce::JSON::parse (m.getProperty ("json").toString());
            if (parsed.isObject())
                map = MidiMap::fromVar (parsed);
        }

        badHits.clear();
        for (auto e : root.getChildWithName ("Bad"))
            badHits.insert (e.getProperty ("key").toString());

        auto prefs = root.getChildWithName ("Prefs");
        showHitInfo = (bool) prefs.getProperty ("showHitInfo", true);
        comicFx = (bool) prefs.getProperty ("comicFx", true);
        setShowtime ((bool) prefs.getProperty ("showtime", false));
        if (auto ui = root.getChildWithName ("UI"); ui.isValid())
            uiState.copyPropertiesFrom (ui, nullptr);

        auto k = root.getChildWithName ("Kit");
        std::map<juce::String, juce::String> names;
        for (auto v : k)
            names[v.getProperty ("piece").toString()] = v.getProperty ("name").toString();
        juce::File folder (k.getProperty ("path").toString());

        auto bleedTree = root.getChildWithName ("Bleed").createCopy();
        auto applyBleed = [this, bleedTree]
        {
            for (auto& row : bleed)
                for (auto& b : row)
                    b.store (1.0f);
            if (kit == nullptr)
                return;
            for (auto e : bleedTree)
                setBleedDb (kit->findPiece (e.getProperty ("piece").toString()), kit->findMic (e.getProperty ("mic").toString()),
                            (float) e.getProperty ("db", 0.0));
        };

        if (folder.isDirectory())
        {
            juce::String error;
            if (auto scanned = KitLoader::scan (folder, error))
            {
                kitFolder = folder;
                setKit (scanned, names);
            }
            else
            {
                loadMessage = "Couldn't open the kit folder " + folder.getFullPathName() + ": " + error;
                kitFolder = juce::File();
                setKit (sharedFactoryKit(), names);
            }
        }
        else
        {
            kitFolder = juce::File();
            setKit (sharedFactoryKit(), names);
        }
        applyBleed();
        rebuildSnapshot();
        sendChangeMessage();
    };

    if (juce::MessageManager::existsAndIsCurrentThread())
        apply();
    else
        juce::MessageManager::callAsync ([token = alive, apply]
        {
            if (token->load())
                apply();
        });
}

//==============================================================================
juce::AudioProcessorEditor* PandaDrumsProcessor::createEditor()
{
    return new PandaDrumsEditor (*this);
}
