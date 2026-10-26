// Tests for the Limitless Undo plugin itself, with a small stand-in plugin inside it.
//
//   undo_plugin_tests              runs the tests here
//   undo_plugin_tests --link-demo  connects to a running Limitless Keys (its
//                                  undo-link.json), makes one change and waits for
//                                  Keys to undo it. tests/test_plugin_link.py drives it.

#include "../source/PluginProcessor.h"

#include <cstdio>

static int failures = 0;

#define CHECK(cond)                                                              \
    do {                                                                         \
        if (! (cond)) {                                                          \
            std::printf ("  FAILED %s:%d  %s\n", __FILE__, __LINE__, #cond);    \
            ++failures;                                                          \
        }                                                                        \
    } while (0)

// A plugin to put inside: a gain and a mix knob.
class FakePlugin : public juce::AudioPluginInstance
{
public:
    FakePlugin()
        : AudioPluginInstance (BusesProperties().withInput ("In", juce::AudioChannelSet::stereo(), true)
                                                .withOutput ("Out", juce::AudioChannelSet::stereo(), true))
    {
        auto g = std::make_unique<juce::AudioParameterFloat> (juce::ParameterID { "gain", 1 }, "Gain",
                                                               juce::NormalisableRange<float> (-24.0f, 24.0f), 0.0f,
                                                               juce::AudioParameterFloatAttributes().withLabel ("dB"));
        gain = g.get();
        addHostedParameter (std::move (g));
        auto m = std::make_unique<juce::AudioParameterFloat> (juce::ParameterID { "mix", 1 }, "Mix", 0.0f, 1.0f, 0.5f);
        mix = m.get();
        addHostedParameter (std::move (m));
    }

    void fillInPluginDescription (juce::PluginDescription& d) const override
    {
        d.name = d.descriptiveName = "Fake EQ";
        d.pluginFormatName = "Test";
        d.fileOrIdentifier = "fake";
    }

    const juce::String getName() const override { return "Fake EQ"; }
    void prepareToPlay (double, int) override {}
    void releaseResources() override {}
    using AudioPluginInstance::processBlock;
    void processBlock (juce::AudioBuffer<float>& b, juce::MidiBuffer&) override
    {
        b.applyGain (juce::Decibels::decibelsToGain (gain->get()));
    }
    double getTailLengthSeconds() const override { return 0; }
    bool acceptsMidi() const override { return false; }
    bool producesMidi() const override { return false; }
    juce::AudioProcessorEditor* createEditor() override { return nullptr; }
    bool hasEditor() const override { return false; }
    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}
    void getStateInformation (juce::MemoryBlock& m) override { m.setSize (4); }
    void setStateInformation (const void*, int) override {}

    juce::AudioParameterFloat* gain = nullptr;
    juce::AudioParameterFloat* mix = nullptr;
};

static void pump (int ms)
{
    auto end = juce::Time::getMillisecondCounter() + (juce::uint32) ms;
    while (juce::Time::getMillisecondCounter() < end)
        juce::MessageManager::getInstance()->runDispatchLoopUntil (10);
}

// Turning a knob the way a plugin's own window does.
static void turn (juce::AudioParameterFloat& p, float value)
{
    auto& base = static_cast<juce::AudioProcessorParameter&> (p);
    auto from = base.getValue(), to = p.convertTo0to1 (value);
    p.beginChangeGesture();
    for (int i = 1; i <= 5; ++i)
        p.setValueNotifyingHost (from + (to - from) * (float) i / 5.0f);
    p.endChangeGesture();
}

static FakePlugin* load (LimitlessUndoProcessor& proc)
{
    auto fake = std::make_unique<FakePlugin>();
    auto* raw = fake.get();
    proc.adoptForTesting (std::move (fake));
    return raw;
}

static void knobTurnIsUndone()
{
    LimitlessUndoProcessor proc;
    auto* fake = load (proc);
    CHECK (proc.hostedName() == "Fake EQ");
    CHECK (proc.getParameters()[0]->getName (32) == "Gain");      // the DAW sees the plugin's names

    turn (*fake->gain, 6.0f);
    pump (120);
    CHECK (proc.undoCount() == 1);
    CHECK (proc.describeNext (true) == "Gain back to 0.0 dB" || proc.describeNext (true).startsWith ("Gain back to 0"));

    CHECK (proc.undo());
    CHECK (std::abs (fake->gain->get() - 0.0f) < 0.01f);
    pump (120);
    CHECK (proc.undoCount() == 0 && proc.redoCount() == 1);       // undoing wasn't a new change

    CHECK (proc.redo());
    CHECK (std::abs (fake->gain->get() - 6.0f) < 0.01f);
}

static void automationIsNotUndone()
{
    LimitlessUndoProcessor proc;
    auto* fake = load (proc);
    auto* slot = proc.getParameters()[1];
    for (int i = 0; i < 20; ++i)
    {
        slot->setValue ((float) i / 20.0f);    // the DAW playing automation on Mix
        pump (5);
    }
    pump (500);
    CHECK (std::abs (fake->mix->get() - 19.0f / 20.0f) < 0.01f);
    CHECK (proc.undoCount() == 0);
}

static void compareHoldsBeforeThenAfter()
{
    LimitlessUndoProcessor proc;
    auto* fake = load (proc);
    turn (*fake->mix, 0.9f);
    pump (120);
    proc.compare (true);
    CHECK (std::abs (fake->mix->get() - 0.5f) < 0.01f);
    proc.compare (false);
    CHECK (std::abs (fake->mix->get() - 0.9f) < 0.01f);
    CHECK (proc.undoCount() == 1);
}

static void historyIsSavedWithTheSession()
{
    LimitlessUndoProcessor proc;
    auto* fake = load (proc);
    turn (*fake->gain, -3.0f);
    pump (120);
    juce::MemoryBlock state;
    proc.getStateInformation (state);
    auto xml = juce::AudioProcessor::getXmlFromBinary (state.getData(), (int) state.getSize());
    CHECK (xml != nullptr && xml->hasTagName ("LimitlessUndo"));
    CHECK (xml != nullptr && xml->getChildElementAllSubText ("HISTORY", {}).contains ("Gain"));
    CHECK (xml != nullptr && xml->getChildByName ("PLUGIN") != nullptr);
}

static void audioPassesThroughThePluginInside()
{
    LimitlessUndoProcessor proc;
    proc.prepareToPlay (48000, 64);
    juce::AudioBuffer<float> buffer (2, 64);
    juce::MidiBuffer midi;
    buffer.clear();
    buffer.setSample (0, 0, 0.5f);
    proc.processBlock (buffer, midi);
    CHECK (std::abs (buffer.getSample (0, 0) - 0.5f) < 1.0e-6f);    // empty: straight through

    auto* fake = load (proc);
    *fake->gain = 6.0f;
    buffer.setSample (0, 0, 0.5f);
    proc.processBlock (buffer, midi);
    CHECK (std::abs (buffer.getSample (0, 0) - 0.5f * juce::Decibels::decibelsToGain (6.0f)) < 1.0e-4f);
}

static int linkDemo()
{
    LimitlessUndoProcessor proc;
    auto* fake = load (proc);
    for (int i = 0; i < 100 && ! proc.isLinked(); ++i)
        pump (50);
    if (! proc.isLinked())
    {
        std::printf ("not linked\n");
        return 1;
    }
    std::printf ("linked\n");
    std::fflush (stdout);
    turn (*fake->gain, 9.0f);
    pump (200);
    std::printf ("changed\n");
    std::fflush (stdout);
    for (int i = 0; i < 200; ++i)
    {
        pump (50);
        if (std::abs (fake->gain->get()) < 0.01f)
        {
            std::printf ("restored\n");
            return 0;
        }
    }
    std::printf ("not restored\n");
    return 1;
}

int main (int argc, char** argv)
{
    juce::ScopedJuceInitialiser_GUI juce;

    if (argc > 1 && juce::String (argv[1]) == "--link-demo")
        return linkDemo();

    std::vector<std::pair<const char*, std::function<void()>>> tests {
        { "a knob turn is undone and redone", knobTurnIsUndone },
        { "automation is never undone", automationIsNotUndone },
        { "hold to hear before, let go for after", compareHoldsBeforeThenAfter },
        { "history is saved with the session", historyIsSavedWithTheSession },
        { "audio passes through the plugin inside", audioPassesThroughThePluginInside },
    };
    for (auto& [name, fn] : tests)
    {
        int before = failures;
        fn();
        std::printf ("%s %s\n", failures == before ? "ok  " : "FAIL", name);
    }
    std::printf ("%d failure(s)\n", failures);
    return failures == 0 ? 0 : 1;
}
