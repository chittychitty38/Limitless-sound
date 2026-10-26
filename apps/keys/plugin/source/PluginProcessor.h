// Limitless Undo: holds one AU or VST3 plugin, passes audio and automation
// through it, and keeps an undo history of every change you make to it.

#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_audio_utils/juce_audio_utils.h>

#include <array>
#include <atomic>
#include <functional>
#include <optional>

#include "../core/UndoHistory.h"
#include "KeysLink.h"

class LimitlessUndoProcessor : public juce::AudioProcessor,
                               public juce::ChangeBroadcaster,
                               private juce::AudioProcessorListener,
                               private juce::Timer
{
public:
    // How many of the hosted plugin's parameters the DAW can see and automate.
    static constexpr int numSlots = 512;
    static constexpr bool isInstrument = LIMITLESS_UNDO_INSTRUMENT;

    LimitlessUndoProcessor();
    ~LimitlessUndoProcessor() override;

    // AudioProcessor ----------------------------------------------------------------
    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override;
    bool isBusesLayoutSupported (const BusesLayout&) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }

    const juce::String getName() const override { return JucePlugin_Name; }
    bool acceptsMidi() const override { return isInstrument; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override;

    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return {}; }
    void changeProgramName (int, const juce::String&) override {}

    void getStateInformation (juce::MemoryBlock&) override;
    void setStateInformation (const void*, int) override;
    void updateTrackProperties (const TrackProperties&) override;

    // The plugin inside ------------------------------------------------------------------
    juce::AudioPluginFormatManager formatManager;
    void loadPlugin (const juce::PluginDescription&, std::function<void (juce::String)> done,
                     std::shared_ptr<juce::MemoryBlock> state = {}, juce::String historyText = {});
    void unloadPlugin();
    juce::AudioPluginInstance* getHosted() const { return hosted.get(); }
    juce::String hostedName() const;

    // The editor drops the hosted plugin's window when this is called, just before
    // that plugin goes away.
    std::function<void()> onHostedChanging;

    // Undo ------------------------------------------------------------------------------
    bool undo();
    bool redo();
    void compare (bool hearBefore);
    bool isComparing() const { return comparing.has_value(); }
    int undoCount() const;
    int redoCount() const;
    juce::String describeNext (bool forUndo) const;

    // When off, knob moves inside aren't passed to the DAW: they stay out of the
    // DAW's own undo (and out of its automation recording).
    bool sendToHost = true;

    bool isLinked() const { return link.isConnected(); }
    juce::String trackName;

    // For the slots the DAW sees.
    void slotSetByHost (int index, float value);

    // Puts an already-made plugin inside, for tests.
    void adoptForTesting (std::unique_ptr<juce::AudioPluginInstance> p) { adopt (std::move (p), nullptr); }

private:
    class Slot;

    void audioProcessorParameterChanged (juce::AudioProcessor*, int index, float value) override;
    void audioProcessorChanged (juce::AudioProcessor*, const juce::AudioProcessorListener::ChangeDetails&) override;
    void audioProcessorParameterChangeGestureBegin (juce::AudioProcessor*, int index) override;
    void audioProcessorParameterChangeGestureEnd (juce::AudioProcessor*, int index) override;
    void timerCallback() override;

    void adopt (std::unique_ptr<juce::AudioPluginInstance>, const juce::MemoryBlock* state);
    void matchLayout (juce::AudioPluginInstance&);
    void sendStep (limitless::Step&);
    void applyStep (const limitless::Step&, bool toBefore);
    void label (limitless::Step&);
    juce::String valueText (int index, float value) const;
    double now() const { return juce::Time::getMillisecondCounterHiRes() / 1000.0; }

    // Talking to Limitless Keys
    void linkConnected();
    void linkMessage (const juce::var&);
    juce::var stepVar (const limitless::Step&) const;
    void sendSync();
    void sendMeta();

    // Changes from any thread, waiting for the message thread.
    enum class Kind : uint8_t { value, gestureBegin, gestureEnd, host };
    struct Event { int index; float value; Kind kind; double time; };
    static constexpr int fifoSize = 8192;
    juce::AbstractFifo fifo { fifoSize };
    std::array<Event, fifoSize> events {};
    juce::SpinLock pushLock;
    void push (int index, float value, Kind kind);

    std::unique_ptr<juce::AudioPluginInstance> hosted;
    juce::CriticalSection hostedLock;   // held by the audio thread while it uses the plugin
    juce::CriticalSection swapLock;     // held while the plugin is swapped; never by the audio thread
    juce::AudioBuffer<float> scratch;
    double sampleRate = 0.0;
    int blockSize = 0;
    std::vector<Slot*> slots;

    limitless::UndoHistory history;     // only touched with historyLock held
    juce::CriticalSection historyLock;
    std::atomic<int> slotCallers { 0 };
    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>> (true);
    std::optional<uint64_t> comparing;
    juce::String instanceId = juce::Uuid().toString();
    KeysLink link;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (LimitlessUndoProcessor)
};
