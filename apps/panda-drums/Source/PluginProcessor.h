#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_audio_formats/juce_audio_formats.h>
#include "engine/Analysis.h"
#include "engine/FactoryKit.h"
#include "engine/KitLoader.h"
#include "engine/Mapping.h"
#include "engine/Mixer.h"
#include "engine/Sampler.h"
#include "engine/Tuning.h"
#include <set>

class PandaDrumsProcessor : public juce::AudioProcessor,
                            public juce::ChangeBroadcaster,
                            private juce::AsyncUpdater,
                            private juce::Timer
{
public:
    PandaDrumsProcessor();
    ~PandaDrumsProcessor() override;

    //== AudioProcessor ============================================================
    void prepareToPlay (double sampleRate, int samplesPerBlock) override;
    void releaseResources() override {}
    bool isBusesLayoutSupported (const BusesLayout&) const override;
    void processBlock (juce::AudioBuffer<float>&, juce::MidiBuffer&) override;
    using AudioProcessor::processBlock;

    juce::AudioProcessorEditor* createEditor() override;
    bool hasEditor() const override { return true; }
    const juce::String getName() const override { return "Panda Drums"; }
    bool acceptsMidi() const override { return true; }
    bool producesMidi() const override { return false; }
    bool isMidiEffect() const override { return false; }
    double getTailLengthSeconds() const override { return 3.0; }
    int getNumPrograms() override { return 1; }
    int getCurrentProgram() override { return 0; }
    void setCurrentProgram (int) override {}
    const juce::String getProgramName (int) override { return "Default"; }
    void changeProgramName (int, const juce::String&) override {}
    void getStateInformation (juce::MemoryBlock&) override;
    void setStateInformation (const void*, int) override;

    //== Parameters ================================================================
    juce::AudioProcessorValueTreeState params;
    static juce::String chParam (int ch, const char* what)   { return "ch" + juce::String (ch + 1) + what; }
    static juce::String pieceParam (int p, const char* what) { return "pc" + juce::String (p + 1) + what; }
    juce::RangedAudioParameter* param (const juce::String& id) { return params.getParameter (id); }
    void setParam (const juce::String& id, float plainValue);

    //== Kit =======================================================================
    std::shared_ptr<const pd::Kit> getKit() const { return kit; }
    std::shared_ptr<const pd::EngineSnapshot> getSnapshot() const { return exchange.latest(); }
    void loadFactoryKit();
    void loadKitFolder (const juce::File&);
    void reloadKit();
    bool isLoading() const { return pendingLoads->load() > 0; }
    juce::String getLoadMessage() const;
    juce::File getKitFolder() const { return kitFolder; }

    int getSelectedVariant (int piece) const;
    void selectVariant (int piece, int variant);
    void stepVariant (int piece, int direction);

    // Loads everything needed right now on the calling thread (tests, offline render).
    void loadSelectedVariantsNow();

    //== Pitch and key =============================================================
    pd::Key getKey() const { return key; }
    void setKey (pd::Key);
    bool autoTuneToKey = true;
    float getNaturalMidi (int piece) const;
    float getTune (int piece) const;
    float getPitch (int piece) const { return getNaturalMidi (piece) + getTune (piece); }
    void setTune (int piece, float semis);
    void stepPitch (int piece, int direction);
    void tuneKitToKey();
    bool pitchInKey (int piece) const;

    //== Chromatic play ============================================================
    struct Chromatic { bool on = true; juce::String pieceId = "tom3"; int low = 72, high = 95; bool snap = true; };
    Chromatic getChromatic() const { return chromatic; }
    void setChromatic (const Chromatic&);

    //== Velocity zones, round robins and the bad-sample list ======================
    pd::ZoneSettings getZoneSettings() const { return zoneSettings; }
    void setZoneSettings (const pd::ZoneSettings&);
    bool isBad (int piece, int artic, int hit) const;
    void setBad (int piece, int artic, int hit, bool bad);
    int countBad() const { return (int) badHits.size(); }
    void clearBad();
    juce::String buildReport() const;          // every hit: zone, round robin, level, bad or not
    juce::String buildBadList() const;

    //== Mapping ===================================================================
    pd::MidiMap getMap() const { return map; }
    void setMap (const pd::MidiMap&);
    std::array<pd::ResolvedNote, 128> getResolvedNotes() const;
    // MIDI learn: arm it, play a note, and the screen picks the note up from learnedNote.
    std::atomic<bool> learnArmed { false };
    std::atomic<int> learnedNote { -1 };

    //== Mixer =====================================================================
    float getBleedDb (int piece, int mic) const;
    void setBleedDb (int piece, int mic, float db);
    float takeChannelPeak (int mic) { return mixer.takeChannelPeak (mic); }
    float takeMasterPeak (int side) { return mixer.takeMasterPeak (side); }

    //== Panda & screen ============================================================
    pd::EventFifo<pd::HitEvent, 1024> hitEvents;
    pd::EventFifo<pd::PlayRequest, 64> playRequests;
    void play (int piece, int artic, int velocity, int hit = -1, float semis = 0.0f);
    void playNote (int note, int velocity);        // as if the note came in over MIDI

    // Showtime: delays the sound a little (the DAW compensates) so the panda can wind up
    // before each hit lands, exactly in time.
    bool getShowtime() const { return showtime; }
    void setShowtime (bool);
    int getShowtimeLatency() const { return showtime ? (int) std::lround (0.075 * currentSampleRate) : 0; }

    struct Transport { double bpm = 120.0, ppq = 0.0; bool playing = false; };
    Transport getTransport() const;
    juce::int64 getClock() const { return blockClock.load(); }
    double getClockWallMs() const { return blockWallMs.load(); }
    double getSampleRate() const { return currentSampleRate; }
    int getBlockSize() const { return currentBlock; }
    int getActiveVoices() const { return activeVoices.load(); }

    juce::ValueTree uiState { "UI" };          // window size, page (read freely; write with setUiProperty)
    void setUiProperty (const juce::Identifier&, const juce::var&);
    bool showHitInfo = true;
    bool comicFx = true;
    void setShowHitInfo (bool);
    void setComicFx (bool);
    void setAutoTuneToKey (bool);

private:
    static juce::AudioProcessorValueTreeState::ParameterLayout createLayout();
    void handleAsyncUpdate() override;
    void timerCallback() override;
    void rebuildSnapshot();
    void markStateDirty();
    juce::ValueTree buildExtraState() const;
    void resetForNewKit();
    void setKit (std::shared_ptr<pd::Kit>, const std::map<juce::String, juce::String>& variantNames = {});
    void requestLoad (int piece, int variant);
    static std::shared_ptr<const pd::VariantData> loadNow (const pd::Kit&, int piece, int variant, std::shared_ptr<std::atomic<bool>> keepGoing);
    void updateEngineParams();
    std::vector<std::shared_ptr<const pd::VariantData>> selectedData() const;

    std::shared_ptr<pd::Kit> kit;
    juce::File kitFolder;
    std::vector<int> selected;
    pd::SnapshotExchange exchange;
    juce::uint32 generation = 0;

    pd::Key key;
    Chromatic chromatic;
    pd::ZoneSettings zoneSettings;
    pd::MidiMap map;
    std::set<juce::String> badHits;
    std::array<std::array<std::atomic<float>, pd::maxMics>, pd::maxPieces> bleed;
    juce::ValueTree pendingState;

    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>> (true);
    std::shared_ptr<std::atomic<int>> pendingLoads = std::make_shared<std::atomic<int>> (0);
    std::atomic<int> scanRequest { 0 };        // only the newest kit scan is applied
    bool retunePending = false;                // put the kit in key once the new drum has loaded

    // Saved state, rebuilt on the message thread so hosts can save from any thread.
    juce::ValueTree cachedState;
    juce::CriticalSection stateLock;
    juce::String loadMessage;
    mutable juce::CriticalSection messageLock;

    // Audio thread.
    pd::Sampler sampler;
    pd::Mixer mixer;
    pd::EngineParams engineParams;
    pd::MixParams mixParams;
    juce::AudioBuffer<float> micBuses, mixBuffer, delayBuffer;
    int delayWrite = 0;
    std::atomic<int> delayLatency { 0 };       // set by the message thread, applied by the audio thread
    int audioLatency = 0;
    juce::int64 clock = 0;
    double currentSampleRate = 44100.0;
    int currentBlock = 512;
    bool showtime = false;

    std::atomic<juce::int64> blockClock { 0 };
    std::atomic<double> blockWallMs { 0.0 };
    std::atomic<double> hostBpm { 120.0 }, hostPpq { 0.0 };
    std::atomic<bool> hostPlaying { false };
    std::atomic<int> activeVoices { 0 };

    // Parameter pointers, so the audio thread doesn't look them up by name.
    std::atomic<float>* masterDb = nullptr;
    std::atomic<float>* masterPanda = nullptr;
    std::atomic<float>* velCurve = nullptr;
    std::atomic<float>* dynamics = nullptr;
    std::atomic<float>* humanize = nullptr;
    std::atomic<float>* rrMode = nullptr;
    struct ChannelPtrs { std::atomic<float> *vol, *pan, *mute, *solo, *panda; };
    struct PiecePtrs { std::atomic<float> *vol, *tune, *decay; };
    std::array<ChannelPtrs, pd::maxMics> chPtr {};
    std::array<PiecePtrs, pd::maxPieces> pcPtr {};

    // Last, so it's destroyed first: its jobs finish while everything they touch still exists.
    juce::ThreadPool loaderPool { 2 };

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PandaDrumsProcessor)
};
