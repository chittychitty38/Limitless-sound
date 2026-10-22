// Offline renderer for Panda Drums.
//
//   PandaDrumsRender screenshots <dir>      one PNG per page, plus the app icon
//   PandaDrumsRender video <dir> [seconds]  frames/0001.png... and groove.wav of the panda
//                                           playing a groove, frame-exact; join them with
//                                           ffmpeg -framerate 30 -i frames/%04d.png -i groove.wav ...
//   PandaDrumsRender icon <file.png>        the app icon on its own
#include "PluginEditor.h"
#include "gui/PandaArt.h"

namespace
{
constexpr double sampleRate = 48000.0;
constexpr int blockSize = 480;
constexpr int fps = 30;

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
        auto latency = proc.getShowtimeLatency();
        editor->pumpEvents (now, [latency] (const pd::HitEvent& e) { return (double) (e.time + latency) / sampleRate; });
    }
};

juce::MidiMessage on (int note, int vel) { return juce::MidiMessage::noteOn (10, note, (juce::uint8) vel); }

// A groove that shows everything off: hats and backbeat, ghost notes, a tom fill, crashes,
// and a melody on the chromatic floor tom in the song's key.
std::vector<std::pair<juce::int64, juce::MidiMessage>> groove (double bpm, int bars, double startSec)
{
    std::vector<std::pair<juce::int64, juce::MidiMessage>> out;
    auto sixteenth = 60.0 / bpm / 4.0;
    auto at = [&] (int bar, double step) { return (juce::int64) ((startSec + (bar * 16 + step) * sixteenth) * sampleRate); };
    juce::Random r (42);
    for (int bar = 0; bar < bars; ++bar)
    {
        auto fill = bar % 4 == 3;
        auto melody = bar == 5;
        if (bar % 4 == 0)
        {
            out.push_back ({ at (bar, 0), on (bar == 0 ? 49 : 57, 122) });
            out.push_back ({ at (bar, 0), on (36, 125) });
        }
        for (int s = 0; s < 16; ++s)
        {
            if (fill && s >= 8)
                break;
            if (s % 2 == 0 && ! (bar % 4 == 0 && s == 0))
                out.push_back ({ at (bar, s), on (bar >= 4 ? 51 : 42, s % 4 == 0 ? 112 : 78 + r.nextInt (16)) });
            if (s == 0 || s == 7 || s == 10)
                if (! (bar % 4 == 0 && s == 0))
                    out.push_back ({ at (bar, s), on (36, s == 0 ? 118 : 100) });
            if (s == 4 || s == 12)
                out.push_back ({ at (bar, s), on (38, 108 + r.nextInt (19)) });
            if ((s == 6 || s == 15) && ! melody)
                out.push_back ({ at (bar, s), on (38, 28 + r.nextInt (20)) });
        }
        if (fill)
        {
            int toms[] = { 48, 48, 45, 45, 43, 43, 41, 41 };
            for (int s = 0; s < 8; ++s)
                out.push_back ({ at (bar, 8 + s), on (toms[s], 100 + s * 3) });
        }
        if (bar % 4 == 1)
            out.push_back ({ at (bar, 14), on (46, 100) });
        if (melody)
        {
            // Chromatic floor tom: D F A G F E D C# D in the song's key.
            int line[] = { 74, 77, 81, 79, 77, 76, 74, 73 };
            for (int i = 0; i < 8; ++i)
                out.push_back ({ at (bar, i * 2 + 1), on (line[i], 112) });
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
    auto notes = groove (100.0, 2, 0.1);
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
    s.proc.setShowtime (true);  // hits are known 75 ms early, so the panda winds up and lands on time
    s.editor->refreshAll();
    auto bpm = 100.0;
    auto bars = std::max (1, (int) ((seconds - 1.5) / (240.0 / bpm)));
    auto notes = groove (bpm, bars, 0.3);
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
        s.editor->getKitPage().stage.advanceTo (t);
        writePng (snapshot (*s.editor), framesDir.getChildFile (juce::String (f + 1).paddedLeft ('0', 4) + ".png"));
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
    if (mode == "icon")
    {
        writeIcon (target, 1024);
        return 0;
    }
    std::printf ("usage: PandaDrumsRender screenshots|video|icon <path> [seconds]\n");
    return 1;
}
