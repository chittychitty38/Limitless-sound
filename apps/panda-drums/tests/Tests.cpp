// Panda Drums unit tests: file names, velocity zones, round robins, keys, maps, the
// factory kit, loading a kit folder, the processor and the editor. Exit code = failures.
#include "PluginEditor.h"

using namespace pd;

namespace
{
Hit fakeHit (int layer, int rr, float level, const juce::String& name)
{
    Hit h;
    h.fileLayer = layer;
    h.fileRR = rr;
    h.rmsDb = h.peakDb = level;
    h.name = name;
    h.length = 100;
    return h;
}

void writeWav (const juce::File& f, float freq, float amp, double seconds, int channels = 1)
{
    f.getParentDirectory().createDirectory();
    juce::AudioBuffer<float> b (channels, (int) (44100 * seconds));
    for (int c = 0; c < channels; ++c)
        for (int i = 0; i < b.getNumSamples(); ++i)
            b.setSample (c, i, amp * std::sin (juce::MathConstants<float>::twoPi * freq * (float) i / 44100.0f) * std::exp (-(float) i / 8000.0f));
    juce::WavAudioFormat wav;
    f.deleteFile();
    std::unique_ptr<juce::OutputStream> os = f.createOutputStream();
    auto opts = juce::AudioFormatWriterOptions().withSampleRate (44100.0).withNumChannels (channels).withBitsPerSample (24);
    if (auto w = wav.createWriterFor (os, opts))
        w->writeFromAudioSampleBuffer (b, 0, b.getNumSamples());
}
} // namespace

class NameTests : public juce::UnitTest
{
public:
    NameTests() : UnitTest ("File names", "Panda") {}
    void runTest() override
    {
        beginTest ("layers, round robins and mics");
        auto p = parseSampleName ("Kick_In_V3_RR2", { "Kick" });
        expectEquals (p.layer, 3);
        expectEquals (p.rr, 2);
        expectEquals (p.mic, juce::String ("In"));

        p = parseSampleName ("SNR Top Rimshot vel05 rr07", { "Snare", "SNR" });
        expectEquals (p.layer, 5);
        expectEquals (p.rr, 7);
        expectEquals (p.mic, juce::String ("Top"));
        expect (p.artic.startsWith ("rim|"));

        p = parseSampleName ("Tom 1 Close 4 2", { "Tom 1" });
        expectEquals (p.layer, 4);
        expectEquals (p.rr, 2);
        expectEquals (p.mic, juce::String ("Close"));

        p = parseSampleName ("Kick-Room-Far-take3", { "Kick" });
        expectEquals (p.rr, 3);
        expectEquals (p.layer, -1);
        expectEquals (p.mic, juce::String ("Room Far"));

        beginTest ("articulation words");
        expectEquals (articulationFromWord ("Rimshot").first, juce::String ("rim"));
        expectEquals (articulationFromWord ("x-stick").first, juce::String ("sidestick"));
        expectEquals (articulationFromWord ("Half Open").first, juce::String ("half"));
        expect (articulationFromWord ("Vintage").first.isEmpty());
    }
};

class ZoneTests : public juce::UnitTest
{
public:
    ZoneTests() : UnitTest ("Velocity zones", "Panda") {}
    void runTest() override
    {
        Articulation a;
        // 4 layers x 3 round robins, named "v1 = loudest" on purpose.
        for (int layer = 1; layer <= 4; ++layer)
            for (int rr = 1; rr <= 3; ++rr)
                a.hits.push_back (fakeHit (layer, rr, -6.0f * (float) layer + (rr == 2 ? 2.0f : 0.0f), "v" + juce::String (layer) + "rr" + juce::String (rr)));

        beginTest ("zones from file names, ordered by real loudness");
        ZoneSettings s;
        auto l = layoutArticulation (a, s);
        expectEquals ((int) l.zones.size(), 4);
        expect (l.fromFileNames);
        expect (a.hits[(size_t) l.zones.back().hits.front()].fileLayer == 1, "loudest zone holds layer 1");
        expectEquals (l.zones.front().lo, 1);
        expectEquals (l.zones.back().hi, 127);
        for (size_t z = 1; z < l.zones.size(); ++z)
            expectEquals (l.zones[z].lo, l.zones[z - 1].hi + 1);
        for (auto& z : l.zones)
        {
            expectEquals ((int) z.hits.size(), 3);
            expectEquals (a.hits[(size_t) z.hits[0]].fileRR, 1);
            expectEquals (a.hits[(size_t) z.hits[2]].fileRR, 3);
        }

        beginTest ("level match pulls round robins to the zone level");
        s.levelMatch = 1.0f;
        l = layoutArticulation (a, s);
        auto loudRR = l.zones.back().hits[1];   // rr 2 is 2 dB hot
        expectWithinAbsoluteError (juce::Decibels::gainToDecibels (l.hitGain[(size_t) loudRR]), -2.0f, 0.01f);

        beginTest ("zones by loudness");
        s.source = ZoneSettings::Source::Loudness;
        s.zoneCount = 2;
        s.levelMatch = 0.0f;
        l = layoutArticulation (a, s);
        expectEquals ((int) l.zones.size(), 2);
        expectEquals ((int) l.zones[0].hits.size(), 6);
        expect (l.zones[0].refDb < l.zones[1].refDb);

        beginTest ("lanes by loudness stay in order and cover 1-127");
        s.source = ZoneSettings::Source::FileNames;
        s.ranges = ZoneSettings::Ranges::Loudness;
        l = layoutArticulation (a, s);
        expectEquals (l.zones.front().lo, 1);
        expectEquals (l.zones.back().hi, 127);
        for (size_t z = 1; z < l.zones.size(); ++z)
            expect (l.zones[z].lo == l.zones[z - 1].hi + 1 && l.zones[z].hi >= l.zones[z].lo);
        expectEquals (zoneForVelocity (l, 127), 3);
        expectEquals (zoneForVelocity (l, 1), 0);

        beginTest ("velocity build is continuous across lanes");
        s.ranges = ZoneSettings::Ranges::Even;
        l = layoutArticulation (a, s);
        auto top = Sampler::dynamicsGainDb (l, 2, (float) l.zones[2].hi, 1.0f);
        auto bottom = Sampler::dynamicsGainDb (l, 2, (float) l.zones[2].lo, 1.0f);
        expectWithinAbsoluteError (top, 0.0f, 0.001f);
        expectWithinAbsoluteError (bottom, -(l.zones[2].refDb - l.zones[1].refDb), 0.01f);
    }
};

class KeyTests : public juce::UnitTest
{
public:
    KeyTests() : UnitTest ("Keys and tuning", "Panda") {}
    void runTest() override
    {
        Key cMajor { 0, 1 }, dMinor { 2, 2 }, off { 0, 0 };
        beginTest ("in key");
        expect (cMajor.contains (60) && ! cMajor.contains (61));
        expect (dMinor.contains (65) && ! dMinor.contains (66));   // F yes, F# no
        expect (off.contains (61));
        expectEquals (dMinor.name(), juce::String ("D minor"));

        beginTest ("nearest and stepping");
        expectEquals (nearestInKey (cMajor, 61.2f), 62);
        expectEquals (nearestInKey (cMajor, 60.4f), 60);
        expectEquals (stepInKey (cMajor, 60.0f, 1), 62);
        expectEquals (stepInKey (cMajor, 60.0f, -1), 59);
        expectEquals (stepInKey (off, 60.0f, 1), 61);

        beginTest ("whole kit to key keeps order and distinct notes");
        std::vector<float> naturals { 33.0f, 48.3f, 49.0f, 53.5f, 55.4f };
        auto shifts = tuneToKey (dMinor, naturals);
        std::vector<float> pitches;
        for (size_t i = 0; i < naturals.size(); ++i)
        {
            auto p = naturals[i] + shifts[i];
            expect (dMinor.contains ((int) std::lround (p)), "in key");
            expect (std::abs (shifts[i]) <= 7.0f);
            pitches.push_back (p);
        }
        for (size_t i = 1; i < pitches.size(); ++i)
            expect (pitches[i] > pitches[i - 1], "still rising");

        beginTest ("chromatic zone keeps the melody's shape");
        auto a = chromaticTarget (72, 41.0f, 72, 95);
        auto b = chromaticTarget (84, 41.0f, 72, 95);
        expectEquals (b - a, 12.0f);
        expect (std::abs (chromaticTarget (74, 41.0f, 72, 95) - 41.0f) <= 6.0f, "first octave sits on the drum");
        expect (std::abs (chromaticTarget (84, 41.0f, 72, 95) - 41.0f) <= 12.0f);
    }
};

class MapTests : public juce::UnitTest
{
public:
    MapTests() : UnitTest ("MIDI maps", "Panda") {}
    void runTest() override
    {
        auto kit = FactoryKit::create();
        std::vector<std::shared_ptr<const VariantData>> data;
        for (size_t p = 0; p < kit->pieces.size(); ++p)
        {
            auto d = std::make_shared<VariantData>();
            Articulation a;
            a.id = kit->pieces[p].type == PieceType::Snare ? "center" : "hit";
            d->artics.push_back (a);
            if (kit->pieces[p].type == PieceType::Snare)
            {
                Articulation rim; rim.id = "rim"; d->artics.push_back (rim);
                Articulation ss;  ss.id = "sidestick"; d->artics.push_back (ss);
            }
            data.push_back (d);
        }

        beginTest ("general MIDI resolves on the factory kit");
        auto r = resolveMap (presetMaps()[1], *kit, data);
        expectEquals (r[36].piece, kit->findPiece ("kick"));
        expectEquals (r[38].piece, kit->findPiece ("snare"));
        expectEquals (r[40].artic, 1);
        expectEquals (r[37].artic, 2);
        expectEquals (r[41].piece, kit->findPiece ("tom3"), "tom4|tom3 falls back to tom3");
        expectEquals (r[49].piece, kit->findPiece ("crash1"));

        beginTest ("save and load");
        auto m = presetMaps()[2];
        auto back = MidiMap::fromVar (juce::JSON::parse (juce::JSON::toString (m.toVar())));
        expectEquals ((int) back.entries.size(), (int) m.entries.size());
        expectEquals (back.targetFor (22), m.targetFor (22));

        beginTest ("learn replaces a note");
        m.set (38, "tom1");
        expectEquals (m.targetFor (38), juce::String ("tom1"));
    }
};

class EngineTests : public juce::UnitTest
{
public:
    EngineTests() : UnitTest ("Engine", "Panda") {}
    void runTest() override
    {
        PandaDrumsProcessor proc;
        proc.setPlayConfigDetails (0, 2, 48000.0, 256);
        proc.prepareToPlay (48000.0, 256);
        proc.loadSelectedVariantsNow();
        auto snap = proc.getSnapshot();
        expect (snap != nullptr);
        auto snare = proc.getKit()->findPiece ("snare");

        auto play = [&] (int note, int vel)
        {
            juce::AudioBuffer<float> buf (2, 256);
            juce::MidiBuffer midi;
            midi.addEvent (juce::MidiMessage::noteOn (1, note, (juce::uint8) vel), 10);
            proc.processBlock (buf, midi);
            float peak = buf.getMagnitude (0, 256);
            for (int i = 0; i < 20; ++i)
            {
                juce::MidiBuffer none;
                proc.processBlock (buf, none);
                peak = std::max (peak, buf.getMagnitude (0, 256));
            }
            HitEvent e, last;
            while (proc.hitEvents.pop (e)) last = e;
            return std::make_pair (peak, last);
        };

        beginTest ("a snare note makes sound and reports its zone and round robin");
        auto [peak, e] = play (38, 127);
        expect (peak > 0.01f, "audible");
        expectEquals ((int) e.piece, snare);
        expectEquals ((int) e.zone, (int) e.zoneCount - 1);
        expectEquals ((int) e.roundCount, FactoryKit::rounds);

        beginTest ("round robins cycle in order");
        auto r1 = play (38, 127).second.round;
        auto r2 = play (38, 127).second.round;
        expectEquals ((int) r2, ((int) r1 + 1) % FactoryKit::rounds);

        beginTest ("soft notes land in the soft zone");
        expectEquals ((int) play (38, 5).second.zone, 0);

        beginTest ("a sample marked bad is never played");
        auto next = play (38, 127).second;
        proc.setBad (snare, 0, (next.hit + 0) , true);
        for (int i = 0; i < 9; ++i)
            expect (play (38, 127).second.hit != next.hit);
        proc.clearBad();

        beginTest ("in key: the whole kit retunes");
        proc.setKey ({ 2, 2 });
        for (size_t p = 0; p < proc.getKit()->pieces.size(); ++p)
            if (isTunable (proc.getKit()->pieces[p].type))
                expect (proc.pitchInKey ((int) p), proc.getKit()->pieces[p].name + " in key");

        beginTest ("chromatic notes play the drum at that note");
        auto [cpeak, ce] = play (74, 110);   // D
        expect (cpeak > 0.001f);
        expect ((ce.flags & HitEvent::chromatic) != 0);
        auto played = proc.getNaturalMidi (ce.piece) + ce.semis;
        expectEquals (((int) std::lround (played)) % 12, 2);

        beginTest ("a swapped drum lands on a note of the key, and a smaller drum sits higher");
        auto tom = proc.getKit()->findPiece ("tom1");
        auto before = proc.getPitch (tom);
        proc.selectVariant (tom, 0);    // 8" instead of 10"
        proc.loadSelectedVariantsNow();
        expect (proc.pitchInKey (tom));
        expect (proc.getPitch (tom) > before);

        beginTest ("state round trip");
        proc.setBad (snare, 1, 2, true);
        auto m = proc.getMap();
        m.set (60, "snare.rim");
        proc.setMap (m);
        proc.setBleedDb (proc.getKit()->findPiece ("kick"), proc.getKit()->findMic ("overheads"), -9.0f);
        juce::MemoryBlock state;
        proc.getStateInformation (state);

        PandaDrumsProcessor other;
        other.prepareToPlay (48000.0, 256);
        other.setStateInformation (state.getData(), (int) state.getSize());
        expectEquals (other.getKey().root, 2);
        expectEquals (other.getKey().scale, 2);
        expectEquals (other.getMap().targetFor (60), juce::String ("snare.rim"));
        expectEquals (other.countBad(), 1);
        expectEquals (other.getSelectedVariant (tom), 0);
        expectWithinAbsoluteError (other.getBleedDb (other.getKit()->findPiece ("kick"), other.getKit()->findMic ("overheads")), -9.0f, 0.01f);
    }
};

class LoaderTests : public juce::UnitTest
{
public:
    LoaderTests() : UnitTest ("Kit folders", "Panda") {}
    void runTest() override
    {
        auto root = juce::File::getSpecialLocation (juce::File::tempDirectory).getChildFile ("panda-kit-test");
        root.deleteRecursively();
        // Kick: two sizes, two mics, 3 layers x 2 round robins. Snare: articulation folders.
        for (auto size : { "22 Vintage", "24 Boom" })
            for (int layer = 1; layer <= 3; ++layer)
                for (int rr = 1; rr <= 2; ++rr)
                {
                    auto amp = 0.2f * (float) layer + 0.02f * (float) rr;
                    writeWav (root.getChildFile ("Kick").getChildFile (size).getChildFile ("Kick_In_V" + juce::String (layer) + "_RR" + juce::String (rr) + ".wav"), 55.0f, amp, 0.4);
                    writeWav (root.getChildFile ("Kick").getChildFile (size).getChildFile ("Kick_OH_V" + juce::String (layer) + "_RR" + juce::String (rr) + ".wav"), 55.0f, amp * 0.3f, 0.4, 2);
                }
        for (auto art : { "Center", "Rimshot" })
            for (int rr = 1; rr <= 4; ++rr)
                writeWav (root.getChildFile ("Snare").getChildFile (art).getChildFile ("Snare Top " + juce::String (rr) + ".wav"), 200.0f, 0.1f * (float) rr, 0.3);

        beginTest ("scan finds pieces, sizes and mics");
        juce::String error;
        auto kit = KitLoader::scan (root, error);
        expect (kit != nullptr, error);
        if (kit == nullptr) return;
        expectEquals ((int) kit->pieces.size(), 2);
        auto kick = kit->findPiece ("kick");
        expect (kick >= 0);
        expectEquals ((int) kit->pieces[(size_t) kick].variants.size(), 2);
        expectEquals (kit->pieces[(size_t) kick].variants[0].sizeInches, 22.0f);
        expect (kit->findMic ("kickin") >= 0, "Kick In");
        expect (kit->findMic ("overheads") >= 0, "Overheads");
        expect (kit->mics[(size_t) kit->findMic ("overheads")].group == MicGroup::Overhead);

        beginTest ("loading groups every mic of one strike into one hit");
        auto data = KitLoader::loadVariant (*kit, kick, 0);
        expect (data != nullptr);
        if (data == nullptr) return;
        expectEquals ((int) data->artics.size(), 1);
        expectEquals ((int) data->artics[0].hits.size(), 6);
        auto& h = data->artics[0].hits[0];
        expect (h.mics[(size_t) kit->findMic ("kickin")] != nullptr && h.mics[(size_t) kit->findMic ("overheads")] != nullptr);
        expectEquals (h.mics[(size_t) kit->findMic ("overheads")]->getNumChannels(), 2);
        auto l = layoutArticulation (data->artics[0], {});
        expectEquals ((int) l.zones.size(), 3);
        expect (data->detectedHz > 45.0f && data->detectedHz < 65.0f, "kick pitch found: " + juce::String (data->detectedHz));

        beginTest ("articulation folders, round robins without layers zone by loudness");
        auto snareData = KitLoader::loadVariant (*kit, kit->findPiece ("snare"), 0);
        expectEquals ((int) snareData->artics.size(), 2);
        expectEquals (snareData->artics[1].id, juce::String ("rim"));
        auto sl = layoutArticulation (snareData->artics[0], {});
        expect (! sl.fromFileNames);

        beginTest ("panda-kit.json template");
        expect (KitLoader::writeManifestTemplate (*kit, root.getChildFile ("panda-kit.json")));
        auto again = KitLoader::scan (root, error);
        expectEquals ((int) again->pieces.size(), 2);
        root.deleteRecursively();
    }
};

class ArtTests : public juce::UnitTest
{
public:
    ArtTests() : UnitTest ("3D art", "Panda") {}
    void runTest() override
    {
        auto& skin = Skin::get();
        beginTest ("the manifest loads");
        expect (skin.isLoaded());

        beginTest ("every layer the stage draws is there, at 1x and 2x");
        juce::StringArray names { "stage", skin.at ("kit/hihat/top_file").toString(), skin.at ("kit/hihat/bottom_file").toString(),
                                  skin.at ("kit/hihat/stand_file").toString(), skin.at ("kit/snare/stand_file").toString(),
                                  skin.at ("kit/kick/pedal_file").toString() };
        for (auto* kind : { "kick", "tom", "tom_alt", "floor", "snare" })
            for (auto* wrap : { "purple", "brass", "maple", "chrome", "walnut", "black" })
                names.add (skin.at (juce::String ("kit/") + kind + "/wraps/" + wrap).toString());
        for (auto* kind : { "crash", "crash_alt", "ride", "china", "splash" })
            names.add (skin.at (juce::String ("kit/") + kind + "/file").toString());
        for (auto* kind : { "crash", "ride", "china", "splash" })
        {
            auto stands = skin.at (juce::String ("kit/stands/") + kind);
            expect (stands.size() >= 2, kind);
            for (int i = 0; i < stands.size(); ++i)
                names.add (stands[i].getProperty ("file", {}).toString());
        }
        for (auto* pose : { "idle", "blink", "kick", "snare", "hi_hat", "tom_left", "tom_right", "crash_left", "crash_right", "fill", "cheer" })
        {
            names.add (skin.at (juce::String ("panda/poses/") + pose + "/file").toString());
            expect (skin.at (juce::String ("panda/poses/") + pose + "/own_face") || skin.at (juce::String ("panda/poses/") + pose + "/face").size() == 3, pose);
        }
        for (auto* face : { "neutral", "happy", "open_mouth", "smile", "focused", "excited", "wink", "laugh",
                            "surprised", "tongue_out", "angry", "sad", "blink" })
            names.add (skin.at (juce::String ("panda/faces/") + face + "/file").toString());
        for (auto* fx : { "blur_1", "blur_2", "blur_3", "hit_spark", "heart_red", "heart_pink", "heart_yellow" })
            names.add (skin.at (juce::String ("panda/fx/") + fx).toString());
        for (auto& n : names)
            expect (skin.imagesLoad (skin.sprite (n)), "missing layer: " + n);

        beginTest ("slots and anchors for every kind of drum");
        for (auto* kind : { "kick", "rack1", "rack2", "rack3", "rack4", "floor", "snare", "hihat", "crash", "ride", "china", "splash", "perc" })
        {
            auto slots = skin.at (juce::String ("slots/") + kind);
            expect (slots.size() > 0, kind);
            for (int i = 0; i < slots.size(); ++i)
                expect (Skin::number (slots[i].getProperty ("ppi", {})) > 1.0f, kind);
        }
        for (auto* kind : { "kick", "tom", "floor", "snare" })
            expect (Skin::ellipse (skin.at (juce::String ("kit/") + kind + "/head")).getWidth() > 10.0f, kind);
        expect (Skin::number (skin.at ("panda/head/radius")) > 50.0f);
        expect (skin.at ("stage/bulbs").size() > 5);
    }
};

class EditorTests : public juce::UnitTest
{
public:
    EditorTests() : UnitTest ("Editor", "Panda") {}
    void runTest() override
    {
        PandaDrumsProcessor proc;
        proc.prepareToPlay (48000.0, 256);
        proc.loadSelectedVariantsNow();
        std::unique_ptr<PandaDrumsEditor> ed (dynamic_cast<PandaDrumsEditor*> (proc.createEditor()));
        ed->setSize (PandaDrumsEditor::designW, PandaDrumsEditor::designH);
        beginTest ("every page draws");
        for (int page = 0; page < 4; ++page)
        {
            ed->showPage (page);
            auto img = ed->createComponentSnapshot (ed->getLocalBounds());
            expect (img.isValid());
        }
        beginTest ("hits reach the stage and the lab");
        ed->showPage (0);
        HitEvent e;
        e.piece = 1; e.zone = 2; e.zoneCount = 5; e.round = 1; e.roundCount = 3; e.velocityIn = 90;
        proc.hitEvents.push (e);
        ed->pumpEvents (1.0, [] (const HitEvent&) { return 1.0; });
        ed->getKitPage().stage.advanceTo (1.05);
        expect (ed->createComponentSnapshot (ed->getLocalBounds()).isValid());
    }
};

static NameTests nameTests;
static ZoneTests zoneTests;
static KeyTests keyTests;
static MapTests mapTests;
static EngineTests engineTests;
static LoaderTests loaderTests;
static ArtTests artTests;
static EditorTests editorTests;

int main()
{
    juce::ScopedJuceInitialiser_GUI gui;
    juce::UnitTestRunner runner;
    runner.setAssertOnFailure (false);
    runner.runTestsInCategory ("Panda");
    int failures = 0;
    for (int i = 0; i < runner.getNumResults(); ++i)
        failures += runner.getResult (i)->failures;
    std::printf ("\n%s: %d failure(s)\n", failures == 0 ? "ALL PASSED" : "FAILED", failures);
    return failures == 0 ? 0 : 1;
}
