// Offline renderer for Panda Drums.
//
//   PandaDrumsRender screenshots <dir>      one PNG per page, plus the app icon
//   PandaDrumsRender video <dir> [seconds]  frames/0001.png... and groove.wav of the panda
//                                           playing a groove, frame-exact; join them with
//                                           ffmpeg -framerate 30 -i frames/%04d.png -i groove.wav ...
//   PandaDrumsRender icon <file.png>        the app icon on its own
//   PandaDrumsRender promo <dir>            the promo performance: the panda plays through five
//                                           keys (the key panel opens for each) and a tour of
//                                           the pages, then cheers; frames at 2560 wide, drums.wav
//                                           and timeline.json for the compositor (art/promo.py)
#include "PluginEditor.h"
#include "gui/PandaArt.h"
#include "gui/UiKit.h"

namespace
{
constexpr double sampleRate = 48000.0;
constexpr int blockSize = 480;
const int fps = juce::jlimit (10, 120, juce::SystemStats::getEnvironmentVariable ("PD_FPS", "30").getIntValue());
const float frameScale = juce::jlimit (1.0f, 3.0f, juce::SystemStats::getEnvironmentVariable ("PD_SCALE", "1").getFloatValue());   // video frames' pixel scale

bool writePng (const juce::Image& img, const juce::File& f)
{
    f.getParentDirectory().createDirectory();
    f.deleteFile();
    juce::FileOutputStream os (f);
    return os.openedOk() && juce::PNGImageFormat().writeImageToStream (img, os);
}

juce::Image snapshot (juce::Component& c, float scale = 1.0f)
{
    return c.createComponentSnapshot (c.getLocalBounds(), true, scale);
}

void writeIcon (const juce::File& f, int size)
{
    juce::Image img (juce::Image::ARGB, size, size, true);
    juce::Graphics g (img);
    auto r = juce::Rectangle<float> (0.0f, 0.0f, (float) size, (float) size);
    auto s = (float) size / 1024.0f;
    g.setColour (pd::theme::colour::pink);
    g.fillRoundedRectangle (r.reduced (40.0f * s), 220.0f * s);
    g.setGradientFill (juce::ColourGradient (juce::Colours::white.withAlpha (0.35f), r.getCentreX(), r.getY(), juce::Colours::transparentWhite, r.getCentreX(), r.getCentreY(), false));
    g.fillRoundedRectangle (r.reduced (40.0f * s), 220.0f * s);
    g.setColour (pd::theme::colour::ink);
    g.drawRoundedRectangle (r.reduced (40.0f * s), 220.0f * s, 24.0f * s);
    {
        juce::Graphics::ScopedSaveState save (g);
        juce::Path clip;
        clip.addRoundedRectangle (r.reduced (52.0f * s), 210.0f * s);
        g.reduceClipRegion (clip);
        pd::art::drawPandaBadge (g, r.reduced (60.0f * s).translated (0.0f, 70.0f * s));
    }
    writePng (img, f);
}

struct Session
{
    PandaDrumsProcessor proc;
    std::unique_ptr<PandaDrumsEditor> editor;
    juce::int64 clock = 0;

    Session()
    {
        proc.setPlayConfigDetails (0, 2, sampleRate, blockSize);
        proc.prepareToPlay (sampleRate, blockSize);
        proc.loadSelectedVariantsNow();
        editor.reset (dynamic_cast<PandaDrumsEditor*> (proc.createEditor()));
        editor->setStageLive (false);
        editor->setSize (PandaDrumsEditor::designW, PandaDrumsEditor::designH);
    }

    // Runs the engine for a stretch, with MIDI notes at exact sample positions.
    void run (int samples, const std::vector<std::pair<juce::int64, juce::MidiMessage>>& notes, juce::AudioBuffer<float>* record)
    {
        for (int done = 0; done < samples;)
        {
            auto n = std::min (blockSize, samples - done);
            juce::AudioBuffer<float> buffer (2, n);
            juce::MidiBuffer midi;
            for (auto& [at, msg] : notes)
                if (at >= clock && at < clock + n)
                    midi.addEvent (msg, (int) (at - clock));
            buffer.clear();
            proc.processBlock (buffer, midi);
            if (record != nullptr)
            {
                auto pos = record->getNumSamples();
                record->setSize (2, pos + n, true, false, true);
                for (int c = 0; c < 2; ++c)
                    record->copyFrom (c, pos, buffer, c, 0, n);
            }
            clock += n;
            done += n;
        }
    }

    void pump (double now)
    {
        pd::ui::setTime (now);      // the controls' flashes and slides run on the frame's clock
        auto latency = proc.getShowtimeLatency();
        editor->pumpEvents (now, [latency] (const pd::HitEvent& e) { return (double) (e.time + latency) / sampleRate; });
    }
};

juce::MidiMessage on (int note, int vel) { return juce::MidiMessage::noteOn (10, note, (juce::uint8) vel); }

// One bar of rock: driving eighths on the hats (or the ride's bow), the kick on the one and the
// "and" of three, a rimshot backbeat on two and four, a crash and kick to open a phrase, and a
// fill down the toms into the next one.
void rockBar (const std::function<void (double step, int note, int vel)>& add, int bar, bool phraseStart, bool fill,
              bool ride, bool melody, juce::Random& r)
{
    for (int st = 0; st < 16; ++st)
    {
        if (fill && st >= 8)
            break;
        if (st == 0 && phraseStart)
        {
            add (0, bar % 2 == 0 ? 49 : 57, 125);
            add (0, 36, 125);
            continue;
        }
        if (st % 2 == 0)
            add (st, ride ? 51 : 42, st % 4 == 0 ? 118 : 96 + r.nextInt (12));
        if (st == 0 || st == 8 || st == 10 || (st == 6 && bar % 2 == 1))
            add (st, 36, st == 0 || st == 8 ? 122 : 108);
        if (st == 4 || st == 12)
            add (st, 38, 120 + r.nextInt (8));
        if (st == 14 && ! ride && bar % 4 == 1)
            add (st, 46, 112);                         // the hat opens into the next bar
        if (st == 15 && ! melody && bar % 2 == 0)
            add (st, 38, 42 + r.nextInt (16));         // one ghost to push the backbeat
    }
    if (fill)
    {
        // Sixteenths: snare, snare, then down the toms, hard, the kick under each beat.
        int notes[] = { 38, 38, 48, 48, 45, 45, 43, 43 };
        for (int st = 0; st < 8; ++st)
        {
            add (8 + st, notes[st], 108 + st * 2);
            if (st % 4 == 0)
                add (8 + st, 36, 118);
        }
    }
}

// A rock groove that shows everything off: hats then the ride, the backbeat, fills down the
// toms, crashes, and a melody on the chromatic floor tom in the song's key.
std::vector<std::pair<juce::int64, juce::MidiMessage>> groove (double bpm, int bars, double startSec)
{
    std::vector<std::pair<juce::int64, juce::MidiMessage>> out;
    auto sixteenth = 60.0 / bpm / 4.0;
    auto at = [&] (int bar, double step) { return (juce::int64) ((startSec + (bar * 16 + step) * sixteenth) * sampleRate); };
    juce::Random r (42);
    for (int bar = 0; bar < bars; ++bar)
    {
        auto melody = bar == 5;
        rockBar ([&] (double st, int note, int vel) { out.push_back ({ at (bar, st), on (note, vel) }); },
                 bar, bar % 4 == 0, bar % 4 == 3, bar >= 4, melody, r);
        if (melody)
        {
            // Chromatic floor tom: D F A G F E D C# D in the song's key.
            int line[] = { 74, 77, 81, 79, 77, 76, 74, 73 };
            for (int i = 0; i < 8; ++i)
                out.push_back ({ at (bar, i * 2 + 1), on (line[i], 116) });
        }
    }
    out.push_back ({ at (bars, 0), on (49, 127) });
    out.push_back ({ at (bars, 0), on (57, 125) });
    out.push_back ({ at (bars, 0), on (36, 127) });
    out.push_back ({ at (bars, 0), on (52, 120) });
    return out;
}

int screenshots (const juce::File& dir)
{
    Session s;
    s.proc.setKey ({ 2, 2 });   // D minor
    s.proc.setShowtime (true);
    s.editor->refreshAll();
    auto notes = groove (128.0, 2, 0.1);
    auto stopAt = (juce::int64) (1.32 * sampleRate);
    std::vector<std::pair<juce::int64, juce::MidiMessage>> part;
    for (auto& n : notes)
        if (n.first < stopAt)
            part.push_back (n);
    double t = 0.0;
    auto frames = (int) (1.42 * fps);
    for (int f = 0; f < frames; ++f)
    {
        s.run ((int) (sampleRate / fps), part, nullptr);
        t = (double) s.clock / sampleRate;
        s.pump (t);
        s.editor->getKitPage().stage.advanceTo (t);
    }
    if (s.editor->getKitPage().stage.onSelect)
        s.editor->getKitPage().stage.onSelect (1);
    writePng (snapshot (*s.editor), dir.getChildFile ("kit.png"));

    for (auto [page, name] : std::initializer_list<std::pair<int, const char*>> { { 1, "mixer.png" }, { 2, "lab.png" }, { 3, "mapping.png" } })
    {
        s.editor->showPage (page);
        if (page == 2)
            s.editor->getLabPage().onHit ({});
        writePng (snapshot (*s.editor), dir.getChildFile (name));
    }
    writeIcon (dir.getChildFile ("icon.png"), 1024);
    std::printf ("screenshots in %s\n", dir.getFullPathName().toRawUTF8());
    return 0;
}

int video (const juce::File& dir, double seconds)
{
    Session s;
    s.proc.setKey ({ 2, 2 });   // D minor: the kit tunes itself, the chromatic tom melody lands in key
    s.proc.setShowtime (true);  // hits are known 150 ms early, so the panda winds up and lands on time
    s.editor->refreshAll();
    auto bpm = 128.0;
    auto bars = std::max (1, (int) ((seconds - 1.5) / (240.0 / bpm)));
    auto notes = groove (bpm, bars, 0.3);
    auto stageOnly = juce::SystemStats::getEnvironmentVariable ("PD_STAGE", {}).isNotEmpty();
    if (stageOnly)
    {
        s.proc.setShowHitInfo (false);
        s.proc.setComicFx (false);
        s.editor->refreshAll();
    }
    juce::AudioBuffer<float> audio (2, 0);
    auto frames = (int) (seconds * fps);
    auto framesDir = dir.getChildFile ("frames");
    framesDir.deleteRecursively();
    framesDir.createDirectory();
    for (int f = 0; f < frames; ++f)
    {
        s.run ((int) (sampleRate / fps), notes, &audio);
        auto t = (double) s.clock / sampleRate;
        s.pump (t);
        auto& stage = s.editor->getKitPage().stage;
        stage.setTransport (bpm, std::max (0.0, (t - 0.3) / 60.0 * bpm), t > 0.3 && t < 0.3 + (bars + 0.5) * 240.0 / bpm);
        stage.advanceTo (t);
        // PD_STAGE=1: just the stage, no controls over it (the hit pop-ups off), for showing him play.
        writePng (stageOnly ? snapshot (stage, frameScale) : snapshot (*s.editor, frameScale),
                  framesDir.getChildFile (juce::String (f + 1).paddedLeft ('0', 4) + ".png"));
    }
    juce::WavAudioFormat wav;
    auto out = dir.getChildFile ("groove.wav");
    out.deleteFile();
    if (std::unique_ptr<juce::OutputStream> stream = out.createOutputStream())
    {
        auto opts = juce::AudioFormatWriterOptions().withSampleRate (sampleRate).withNumChannels (2).withBitsPerSample (24);
        if (auto writer = wav.createWriterFor (stream, opts))
            writer->writeFromAudioSampleBuffer (audio, 0, audio.getNumSamples());
    }
    std::printf ("%d frames and groove.wav in %s\n", frames, dir.getFullPathName().toRawUTF8());
    return 0;
}
// The promo: a groove that moves through five keys (the tom melody follows each one; the key
// panel opens and picks each key), a tour of the pages, a big ending and the panda's cheer.
// Writes JPEG frames of the whole window at 2x (so the compositor can zoom in), the drums, and
// timeline.json saying when each key and page starts, what every drum is tuned to, and where
// the kicks land (the compositor ducks its pad on them).
int promo (const juce::File& dir)
{
    Session s;
    s.proc.setShowtime (true);
    const double bpm = 124.0, bar = 240.0 / bpm, sixteenth = bar / 16.0, intro = 3.6;
    struct Section { int firstBar, bars; pd::Key key; int page; const char* caption; };
    const std::vector<Section> sections {
        { 0, 4,  { 2, 2 }, 0, "groove" },     // D minor
        { 4, 2,  { 0, 2 }, 0, "key" },        // C minor
        { 6, 2,  { 4, 1 }, 0, "key" },        // E major
        { 8, 2,  { 6, 2 }, 0, "key" },        // F# minor
        { 10, 2, { 9, 1 }, 0, "key" },        // A major
        { 12, 1, { 2, 2 }, 2, "lab" },
        { 13, 1, { 2, 2 }, 1, "mixer" },
        { 14, 1, { 2, 2 }, 3, "mapping" },
        { 15, 1, { 2, 2 }, 0, "fill" },
    };
    const int bars = 16;
    auto at = [&] (int b, double step) { return (juce::int64) ((intro + (b * 16 + step) * sixteenth) * sampleRate); };

    std::vector<std::pair<juce::int64, juce::MidiMessage>> notes;
    std::vector<double> kicks;
    auto add = [&] (juce::int64 t, int note, int vel)
    {
        notes.push_back ({ t, on (note, vel) });
        if (note == 36)
            kicks.push_back ((double) t / sampleRate);
    };
    // The title hit in the intro.
    add ((juce::int64) (2.2 * sampleRate), 36, 127);
    add ((juce::int64) (2.2 * sampleRate), 49, 124);
    juce::Random r (7);
    for (auto& sec : sections)
        for (int b = sec.firstBar; b < sec.firstBar + sec.bars; ++b)
        {
            auto last = b == sec.firstBar + sec.bars - 1;
            juce::String kind (sec.caption);
            auto melody = kind == "key" && last;
            auto fill = (kind == "groove" && last) || kind == "fill";
            rockBar ([&] (double st, int note, int vel) { add (at (b, st), note, vel); },
                     b, b == sec.firstBar, fill, b >= 8, melody, r);
            if (melody)
            {
                // The floor tom sings the key: 1 3 5 6 5 3 2 1 in major, 1 b3 5 4 b3 2 1 b7 in minor.
                std::vector<int> major { 0, 4, 7, 9, 7, 4, 2, 0 }, minor { 0, 3, 7, 5, 3, 2, 0, -2 };
                auto& line = sec.key.scale == 1 ? major : minor;
                auto base = 72 + sec.key.root;
                if (base - 2 < 72)
                    base += 12;
                for (int i = 0; i < 8; ++i)
                    add (at (b, i * 2 + 1), base + line[(size_t) i], 112);
            }
        }
    // The ending: everything at once, then he cheers.
    add (at (bars, 0), 36, 127);
    add (at (bars, 0), 49, 127);
    add (at (bars, 0), 57, 125);
    add (at (bars, 0), 52, 120);
    auto endTime = (double) at (bars, 0) / sampleRate;
    auto total = endTime + 4.2;

    juce::AudioBuffer<float> audio (2, 0);
    auto framesDir = dir.getChildFile ("frames");
    framesDir.deleteRecursively();
    framesDir.createDirectory();
    auto& stage = s.editor->getKitPage().stage;
    juce::JPEGImageFormat jpeg;
    jpeg.setQuality (0.93f);
    auto timeline = std::make_unique<juce::DynamicObject>();
    juce::Array<juce::var> sectionList;
    size_t current = (size_t) -1;
    auto frames = (int) (total * fps);
    auto& topBar = s.editor->getTopBar();
    bool panelOpen = false;
    for (int f = 0; f < frames; ++f)
    {
        auto t0 = (double) s.clock / sampleRate;
        // The key panel opens a moment before each new key, picks it, and closes.
        bool wantPanel = false;
        for (size_t i = 1; i < sections.size(); ++i)
        {
            auto start = intro + sections[i].firstBar * bar;
            if (juce::String (sections[i].caption) == "key" && t0 >= start - 1.1 && t0 < start + 0.45)
                wantPanel = true;
        }
        if (wantPanel != panelOpen)
        {
            if (wantPanel) topBar.showKeyPanel();
            else           topBar.closeKeyPanel();
            panelOpen = wantPanel;
        }
        // Change key and page when a section starts (just before its downbeat is heard).
        for (size_t i = 0; i < sections.size(); ++i)
        {
            auto start = intro + sections[i].firstBar * bar - 0.05;
            if (i != current && t0 >= start && (i + 1 == sections.size() || t0 < intro + sections[i + 1].firstBar * bar - 0.05))
            {
                current = i;
                s.proc.setKey (sections[i].key);
                s.editor->refreshAll();
                s.editor->showPage (sections[i].page);
                auto sec = std::make_unique<juce::DynamicObject>();
                sec->setProperty ("time", intro + sections[i].firstBar * bar);
                sec->setProperty ("end", intro + (sections[i].firstBar + sections[i].bars) * bar);
                sec->setProperty ("key", sections[i].key.name());
                sec->setProperty ("root", sections[i].key.root);
                sec->setProperty ("major", sections[i].key.scale == 1);
                sec->setProperty ("page", sections[i].page);
                sec->setProperty ("caption", sections[i].caption);
                auto pitches = std::make_unique<juce::DynamicObject>();
                if (auto kit = s.proc.getKit())
                    for (size_t p = 0; p < kit->pieces.size(); ++p)
                        if (isTunable (kit->pieces[p].type))
                            pitches->setProperty (kit->pieces[p].name, pd::pitchName (s.proc.getPitch ((int) p)).upToFirstOccurrenceOf (" ", false, false));
                sec->setProperty ("pitches", juce::var (pitches.release()));
                sectionList.add (juce::var (sec.release()));
            }
        }
        s.run ((int) (sampleRate / fps), notes, &audio);
        auto t = (double) s.clock / sampleRate;
        auto playing = t >= intro - 0.1 && t < endTime + 0.15;
        stage.setTransport (bpm, std::max (0.0, (t - intro) / 60.0 * bpm), playing);
        s.pump (t);
        stage.advanceTo (t);
        if (current < sections.size() && sections[current].page == 2)
        {
            pd::HitEvent e;
            e.piece = 1;
            s.editor->getLabPage().onHit (e);
        }
        if (t < intro - 0.2)
            continue;       // the compositor shows its titles here
        auto img = snapshot (*s.editor, 2.0f);
        auto file = framesDir.getChildFile (juce::String (f + 1).paddedLeft ('0', 4) + ".jpg");
        juce::FileOutputStream os (file);
        if (os.openedOk())
            jpeg.writeImageToStream (img, os);
    }

    juce::WavAudioFormat wav;
    auto out = dir.getChildFile ("drums.wav");
    out.deleteFile();
    if (std::unique_ptr<juce::OutputStream> stream = out.createOutputStream())
    {
        auto opts = juce::AudioFormatWriterOptions().withSampleRate (sampleRate).withNumChannels (2).withBitsPerSample (24);
        if (auto writer = wav.createWriterFor (stream, opts))
            writer->writeFromAudioSampleBuffer (audio, 0, audio.getNumSamples());
    }
    juce::Array<juce::var> kickList;
    for (auto k : kicks)
        kickList.add (k);
    timeline->setProperty ("fps", fps);
    timeline->setProperty ("bpm", bpm);
    timeline->setProperty ("intro", intro);
    timeline->setProperty ("end", endTime);
    timeline->setProperty ("total", total);
    timeline->setProperty ("frames", frames);
    timeline->setProperty ("sections", sectionList);
    timeline->setProperty ("kicks", kickList);
    dir.getChildFile ("timeline.json").replaceWithText (juce::JSON::toString (juce::var (timeline.release())));
    std::printf ("%d frames, drums.wav and timeline.json in %s\n", frames, dir.getFullPathName().toRawUTF8());
    return 0;
}

// Peak and loudness of every drum at full force through the whole mix, for balancing kits.
int levels()
{
    Session s;
    auto kit = s.proc.getKit();
    for (size_t p = 0; p < kit->pieces.size(); ++p)
    {
        juce::AudioBuffer<float> audio (2, 0);
        s.proc.play ((int) p, 0, 127);
        s.run ((int) sampleRate * 2, {}, &audio);
        auto peak = audio.getMagnitude (0, audio.getNumSamples());
        auto rms = std::max (audio.getRMSLevel (0, 0, (int) (0.3 * sampleRate)), audio.getRMSLevel (1, 0, (int) (0.3 * sampleRate)));
        std::printf ("%-10s peak %6.1f dBFS   rms(300ms) %6.1f dBFS\n", kit->pieces[p].name.toRawUTF8(),
                     juce::Decibels::gainToDecibels (peak), juce::Decibels::gainToDecibels (rms));
        pd::HitEvent e;
        while (s.proc.hitEvents.pop (e)) {}
    }
    return 0;
}
} // namespace

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI gui;
    juce::String mode = argc > 1 ? argv[1] : "";
    auto target = juce::File::getCurrentWorkingDirectory().getChildFile (argc > 2 ? argv[2] : "render");
    if (mode == "screenshots")
        return screenshots (target);
    if (mode == "video")
        return video (target, argc > 3 ? juce::String (argv[3]).getDoubleValue() : 12.0);
    if (mode == "levels")
        return levels();
    if (mode == "promo")
        return promo (target);
    if (mode == "icon")
    {
        writeIcon (target, 1024);
        return 0;
    }
    std::printf ("usage: PandaDrumsRender screenshots|video|promo|icon <path> [seconds]\n");
    return 1;
}
