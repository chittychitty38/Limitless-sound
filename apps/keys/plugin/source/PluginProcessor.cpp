#include "PluginProcessor.h"
#include "PluginEditor.h"

#if JUCE_WINDOWS
 #include <windows.h>
 static int processId() { return (int) GetCurrentProcessId(); }
#else
 #include <unistd.h>
 static int processId() { return (int) getpid(); }
#endif

// One of the parameters the DAW sees. It stands in for the hosted plugin's
// parameter at the same position, so the DAW can automate the plugin inside.
class LimitlessUndoProcessor::Slot : public juce::HostedAudioProcessorParameter
{
public:
    Slot (LimitlessUndoProcessor& o, int i) : owner (o), index (i) {}

    std::atomic<juce::AudioProcessorParameter*> target { nullptr };
    std::atomic<float> cached { 0.0f };
    bool inGesture = false;   // message thread only

    // Keeps the hosted parameter alive while it's being used from another thread.
    struct Use
    {
        explicit Use (const Slot& s) : slot (s) { ++slot.owner.slotCallers; p = slot.target.load(); }
        ~Use() { --slot.owner.slotCallers; }
        const Slot& slot;
        juce::AudioProcessorParameter* p = nullptr;
    };

    float getValue() const override
    {
        Use u (*this);
        return u.p != nullptr ? u.p->getValue() : cached.load();
    }

    void setValue (float v) override
    {
        cached = v;
        owner.slotSetByHost (index, v);
    }

    float getDefaultValue() const override
    {
        Use u (*this);
        return u.p != nullptr ? u.p->getDefaultValue() : 0.0f;
    }

    juce::String getName (int maximumLength) const override
    {
        Use u (*this);
        if (u.p != nullptr)
            return u.p->getName (maximumLength);
        return ("Slot " + juce::String (index + 1)).substring (0, maximumLength);
    }

    juce::String getLabel() const override
    {
        Use u (*this);
        return u.p != nullptr ? u.p->getLabel() : juce::String();
    }

    juce::String getText (float v, int maximumLength) const override
    {
        Use u (*this);
        return u.p != nullptr ? u.p->getText (v, maximumLength) : juce::String (v, 2);
    }

    float getValueForText (const juce::String& text) const override
    {
        Use u (*this);
        return u.p != nullptr ? u.p->getValueForText (text) : text.getFloatValue();
    }

    int getNumSteps() const override
    {
        Use u (*this);
        return u.p != nullptr ? u.p->getNumSteps() : AudioProcessorParameter::getNumSteps();
    }

    juce::String getParameterID() const override { return "slot" + juce::String (index + 1); }
    bool isAutomatable() const override { return true; }

private:
    LimitlessUndoProcessor& owner;
    const int index;
};

//==============================================================================

LimitlessUndoProcessor::LimitlessUndoProcessor()
    : AudioProcessor (isInstrument
                          ? BusesProperties().withOutput ("Output", juce::AudioChannelSet::stereo(), true)
                          : BusesProperties().withInput ("Input", juce::AudioChannelSet::stereo(), true)
                                             .withOutput ("Output", juce::AudioChannelSet::stereo(), true))
{
    juce::addDefaultFormatsToManager (formatManager);

    for (int i = 0; i < numSlots; ++i)
    {
        auto slot = std::make_unique<Slot> (*this, i);
        slots.push_back (slot.get());
        addParameter (slot.release());
    }

    link.onConnected = [this] { linkConnected(); };
    link.onMessage = [this] (const juce::var& m) { linkMessage (m); };
    sendMeta();
    link.start();
    startTimerHz (30);
}

LimitlessUndoProcessor::~LimitlessUndoProcessor()
{
    *alive = false;
    stopTimer();
    link.stop();
    unloadPlugin();
}

//==============================================================================

bool LimitlessUndoProcessor::isBusesLayoutSupported (const BusesLayout& layouts) const
{
    auto out = layouts.getMainOutputChannelSet();
    if (out != juce::AudioChannelSet::mono() && out != juce::AudioChannelSet::stereo())
        return false;
    if (isInstrument)
        return true;
    auto in = layouts.getMainInputChannelSet();
    return in == out || (in == juce::AudioChannelSet::mono() && out == juce::AudioChannelSet::stereo());
}

void LimitlessUndoProcessor::prepareToPlay (double sr, int block)
{
    sampleRate = sr;
    blockSize = block;
    const juce::ScopedLock sl (hostedLock);
    if (hosted != nullptr)
    {
        matchLayout (*hosted);
        hosted->prepareToPlay (sr, block);
        setLatencySamples (hosted->getLatencySamples());
        auto channels = juce::jmax (hosted->getTotalNumInputChannels(), hosted->getTotalNumOutputChannels(),
                                    getTotalNumInputChannels(), getTotalNumOutputChannels());
        scratch.setSize (channels, block);
    }
}

void LimitlessUndoProcessor::releaseResources()
{
    const juce::ScopedLock sl (hostedLock);
    if (hosted != nullptr)
        hosted->releaseResources();
}

double LimitlessUndoProcessor::getTailLengthSeconds() const
{
    const juce::ScopedLock sl (swapLock);
    return hosted != nullptr ? hosted->getTailLengthSeconds() : 0.0;
}

void LimitlessUndoProcessor::processBlock (juce::AudioBuffer<float>& buffer, juce::MidiBuffer& midi)
{
    juce::ScopedNoDenormals noDenormals;
    const juce::ScopedTryLock sl (hostedLock);
    auto* p = sl.isLocked() ? hosted.get() : nullptr;

    if (p == nullptr)
    {
        // No plugin inside yet: an effect lets the sound through, an instrument is quiet.
        if (isInstrument)
            buffer.clear();
        midi.clear();
        return;
    }

    const int ours = buffer.getNumChannels();
    const int theirIn = p->getTotalNumInputChannels();
    const int theirOut = p->getTotalNumOutputChannels();
    const int theirs = juce::jmax (theirIn, theirOut);
    const int n = buffer.getNumSamples();

    if (theirs == ours && theirIn == getTotalNumInputChannels())
    {
        p->processBlock (buffer, midi);
        return;
    }

    // The plugin inside wants a different number of channels: give it its own buffer.
    if (scratch.getNumChannels() < theirs || scratch.getNumSamples() < n)
        scratch.setSize (juce::jmax (theirs, scratch.getNumChannels()), juce::jmax (n, scratch.getNumSamples()),
                         false, false, true);
    juce::AudioBuffer<float> view (scratch.getArrayOfWritePointers(), theirs, n);
    for (int ch = 0; ch < theirs; ++ch)
    {
        if (ch < theirIn && ch < getTotalNumInputChannels())
            view.copyFrom (ch, 0, buffer, ch, 0, n);
        else if (ch < theirIn && getTotalNumInputChannels() > 0)
            view.copyFrom (ch, 0, buffer, 0, 0, n);   // mono in, more channels wanted
        else
            view.clear (ch, 0, n);
    }

    p->processBlock (view, midi);

    for (int ch = 0; ch < ours; ++ch)
    {
        if (ch < theirOut)
            buffer.copyFrom (ch, 0, view, ch, 0, n);
        else if (theirOut > 0)
            buffer.copyFrom (ch, 0, view, theirOut - 1, 0, n);   // mono out, stereo track
        else
            buffer.clear (ch, 0, n);
    }
}

juce::AudioProcessorEditor* LimitlessUndoProcessor::createEditor()
{
    return new LimitlessUndoEditor (*this);
}

//==============================================================================
// The plugin inside

juce::String LimitlessUndoProcessor::hostedName() const
{
    return hosted != nullptr ? hosted->getName() : juce::String();
}

void LimitlessUndoProcessor::loadPlugin (const juce::PluginDescription& desc, std::function<void (juce::String)> done,
                                         std::shared_ptr<juce::MemoryBlock> state, juce::String historyText)
{
    JUCE_ASSERT_MESSAGE_THREAD
    auto sr = sampleRate > 0 ? sampleRate : 44100.0;
    auto bs = blockSize > 0 ? blockSize : 512;
    auto stillAlive = alive;

    auto finish = [this, stillAlive, state, historyText, done] (std::unique_ptr<juce::AudioPluginInstance> instance,
                                                                const juce::String& error)
    {
        if (! stillAlive->load())
            return;
        if (instance == nullptr)
        {
            if (done)
                done (error.isNotEmpty() ? error : juce::String ("That plugin couldn't be opened."));
            return;
        }
        adopt (std::move (instance), state.get());
        if (historyText.isNotEmpty())
        {
            {
                const juce::ScopedLock hl (historyLock);
                history.deserialise (historyText.toStdString());
            }
            sendSync();
            sendChangeMessage();
        }
        if (done)
            done ({});
    };

    juce::AudioPluginFormat* format = nullptr;
    for (auto* f : formatManager.getFormats())
        if (f->getName() == desc.pluginFormatName)
            format = f;

    if (format != nullptr && ! format->requiresUnblockedMessageThreadDuringCreation (desc))
    {
        juce::String error;
        auto instance = formatManager.createPluginInstance (desc, sr, bs, error);
        finish (std::move (instance), error);
    }
    else
    {
        formatManager.createPluginInstanceAsync (desc, sr, bs, finish);
    }
}

void LimitlessUndoProcessor::matchLayout (juce::AudioPluginInstance& p)
{
    auto ours = getBusesLayout();
    if (p.checkBusesLayoutSupported (ours) && p.setBusesLayout (ours))
        return;

    // Just the main input and output (a plugin may also have a side-chain input).
    BusesLayout main;
    for (int b = 0; b < p.getBusCount (true); ++b)
        main.inputBuses.add (b == 0 && ! isInstrument ? ours.getMainInputChannelSet() : juce::AudioChannelSet::disabled());
    for (int b = 0; b < p.getBusCount (false); ++b)
        main.outputBuses.add (b == 0 ? ours.getMainOutputChannelSet() : juce::AudioChannelSet::disabled());
    if (! p.setBusesLayout (main))
        p.disableNonMainBuses();   // otherwise its own layout, and processBlock adapts
}

void LimitlessUndoProcessor::adopt (std::unique_ptr<juce::AudioPluginInstance> instance, const juce::MemoryBlock* state)
{
    JUCE_ASSERT_MESSAGE_THREAD
    unloadPlugin();

    if (state != nullptr && state->getSize() > 0)
        instance->setStateInformation (state->getData(), (int) state->getSize());

    matchLayout (*instance);
    if (sampleRate > 0)
    {
        instance->prepareToPlay (sampleRate, blockSize);
        auto channels = juce::jmax (instance->getTotalNumInputChannels(), instance->getTotalNumOutputChannels(),
                                    getTotalNumInputChannels(), getTotalNumOutputChannels());
        scratch.setSize (channels, juce::jmax (blockSize, 1));
    }
    instance->addListener (this);

    auto& params = instance->getParameters();
    {
        const juce::ScopedLock swap (swapLock);
        const juce::ScopedLock sl (hostedLock);
        hosted = std::move (instance);
    }
    for (int i = 0; i < numSlots; ++i)
    {
        auto* p = i < params.size() ? params[i] : nullptr;
        slots[(size_t) i]->cached = p != nullptr ? p->getValue() : 0.0f;
        slots[(size_t) i]->target = p;
    }
    {
        const juce::ScopedLock hl (historyLock);
        history.clear();
        for (int i = 0; i < params.size(); ++i)
            history.setKnown (i, params[i]->getValue());
    }

    setLatencySamples (hosted->getLatencySamples());
    updateHostDisplay (juce::AudioProcessorListener::ChangeDetails().withParameterInfoChanged (true).withLatencyChanged (true));
    sendMeta();
    sendSync();
    sendChangeMessage();
}

void LimitlessUndoProcessor::unloadPlugin()
{
    JUCE_ASSERT_MESSAGE_THREAD
    if (hosted == nullptr)
        return;
    if (onHostedChanging)
        onHostedChanging();

    for (auto* s : slots)
    {
        if (s->inGesture)
        {
            s->endChangeGesture();
            s->inGesture = false;
        }
        s->target = nullptr;
    }
    while (slotCallers.load() > 0)          // anyone still reading a parameter
        std::this_thread::yield();

    hosted->removeListener (this);
    std::unique_ptr<juce::AudioPluginInstance> old;
    {
        const juce::ScopedLock swap (swapLock);
        const juce::ScopedLock sl (hostedLock);   // waits for the audio thread to finish its block
        old = std::move (hosted);
    }
    old->releaseResources();
    old.reset();

    {
        const juce::ScopedLock hl (historyLock);
        history.clear();
    }
    updateHostDisplay (juce::AudioProcessorListener::ChangeDetails().withParameterInfoChanged (true));
    sendMeta();
    sendSync();
    sendChangeMessage();
}

//==============================================================================
// Changes, from whichever thread they happen on

void LimitlessUndoProcessor::push (int index, float value, Kind kind)
{
    const juce::SpinLock::ScopedLockType sl (pushLock);
    int start1, size1, start2, size2;
    fifo.prepareToWrite (1, start1, size1, start2, size2);
    if (size1 > 0)
        events[(size_t) start1] = { index, value, kind, now() };
    else if (size2 > 0)
        events[(size_t) start2] = { index, value, kind, now() };
    fifo.finishedWrite (size1 + size2);
}

void LimitlessUndoProcessor::slotSetByHost (int index, float value)
{
    auto& slot = *slots[(size_t) index];
    Slot::Use u (slot);
    if (u.p == nullptr || std::abs (u.p->getValue() - value) < 1.0e-6f)
        return;
    u.p->setValue (value);
    push (index, value, Kind::host);
}

void LimitlessUndoProcessor::audioProcessorParameterChanged (juce::AudioProcessor*, int index, float value)
{
    // People change knobs on the message thread. A plugin moving its own knobs while
    // it plays (an LFO, its own automation) is never something to undo.
    push (index, value, juce::MessageManager::existsAndIsCurrentThread() ? Kind::value : Kind::host);
    if (sendToHost && index < numSlots)
    {
        auto& slot = *slots[(size_t) index];
        if (std::abs (slot.cached.load() - value) > 1.0e-6f)
        {
            slot.cached = value;
            slot.sendValueChangedMessageToListeners (value);   // tells the DAW, without echoing back
        }
    }
}

void LimitlessUndoProcessor::audioProcessorParameterChangeGestureBegin (juce::AudioProcessor*, int index)
{
    push (index, 0.0f, Kind::gestureBegin);
    if (sendToHost && index < numSlots && juce::MessageManager::existsAndIsCurrentThread())
    {
        auto& slot = *slots[(size_t) index];
        if (! slot.inGesture)
        {
            slot.inGesture = true;
            slot.beginChangeGesture();
        }
    }
}

void LimitlessUndoProcessor::audioProcessorParameterChangeGestureEnd (juce::AudioProcessor*, int index)
{
    push (index, 0.0f, Kind::gestureEnd);
    if (index < numSlots && juce::MessageManager::existsAndIsCurrentThread())
    {
        auto& slot = *slots[(size_t) index];
        if (slot.inGesture)
        {
            slot.inGesture = false;
            slot.endChangeGesture();
        }
    }
}

void LimitlessUndoProcessor::audioProcessorChanged (juce::AudioProcessor* p, const juce::AudioProcessorListener::ChangeDetails& details)
{
    if (details.latencyChanged)
        setLatencySamples (p->getLatencySamples());
    if (details.parameterInfoChanged)
        updateHostDisplay (juce::AudioProcessorListener::ChangeDetails().withParameterInfoChanged (true));
}

void LimitlessUndoProcessor::timerCallback()
{
    limitless::Step* made = nullptr;
    {
        const juce::ScopedLock hl (historyLock);
        int start1, size1, start2, size2;
        fifo.prepareToRead (fifo.getNumReady(), start1, size1, start2, size2);
        auto feed = [this] (const Event& e)
        {
            switch (e.kind)
            {
                case Kind::value:        history.valueChanged (e.index, e.value, e.time); break;
                case Kind::gestureBegin: history.gestureBegin (e.index, e.time); break;
                case Kind::gestureEnd:   history.gestureEnd (e.index, e.time); break;
                case Kind::host:         history.hostChanged (e.index, e.value, e.time); break;
            }
        };
        for (int i = 0; i < size1; ++i) feed (events[(size_t) (start1 + i)]);
        for (int i = 0; i < size2; ++i) feed (events[(size_t) (start2 + i)]);
        fifo.finishedRead (size1 + size2);
        made = history.tick (now());
        if (made != nullptr)
            sendStep (*made);
    }
    if (made != nullptr)
        sendChangeMessage();
}

//==============================================================================
// Undo and redo

juce::String LimitlessUndoProcessor::valueText (int index, float value) const
{
    if (hosted == nullptr || index >= hosted->getParameters().size())
        return {};
    auto* p = hosted->getParameters()[index];
    auto text = p->getText (value, 32).trim();
    auto unit = p->getLabel().trim();
    if (unit.isNotEmpty() && ! text.endsWithIgnoreCase (unit))
        text << " " << unit;
    return text;
}

void LimitlessUndoProcessor::label (limitless::Step& s)
{
    if (s.changes.size() == 1)
    {
        auto i = s.changes[0].index;
        auto name = hosted != nullptr && i < hosted->getParameters().size()
                        ? hosted->getParameters()[i]->getName (64)
                        : "Setting " + juce::String (i + 1);
        s.label = name.toStdString();
        s.before = valueText (i, s.changes[0].before).toStdString();
        s.after = valueText (i, s.changes[0].after).toStdString();
    }
    else
    {
        s.label = (juce::String ((int) s.changes.size()) + " settings").toStdString();
    }
}

void LimitlessUndoProcessor::sendStep (limitless::Step& s)
{
    label (s);
    auto v = stepVar (s);
    v.getDynamicObject()->setProperty ("op", "step");
    link.send (v);
}

void LimitlessUndoProcessor::applyStep (const limitless::Step& step, bool toBefore)
{
    if (hosted == nullptr)
        return;
    auto& params = hosted->getParameters();
    for (auto& c : step.changes)
        if (c.index < params.size())
            params[c.index]->setValueNotifyingHost (toBefore ? c.before : c.after);
}

bool LimitlessUndoProcessor::undo()
{
    JUCE_ASSERT_MESSAGE_THREAD
    std::optional<limitless::Step> step;
    {
        const juce::ScopedLock hl (historyLock);
        if (auto* fresh = history.flush (now()))
            sendStep (*fresh);          // so Limitless Keys knows it before it's undone
        step = history.undo (now());
    }
    if (! step)
        return false;
    applyStep (*step, true);
    auto v = juce::var (new juce::DynamicObject());
    v.getDynamicObject()->setProperty ("op", "undone");
    v.getDynamicObject()->setProperty ("id", (juce::int64) step->id);
    link.send (v);
    sendChangeMessage();
    return true;
}

bool LimitlessUndoProcessor::redo()
{
    JUCE_ASSERT_MESSAGE_THREAD
    std::optional<limitless::Step> step;
    {
        const juce::ScopedLock hl (historyLock);
        step = history.redo (now());
    }
    if (! step)
        return false;
    applyStep (*step, false);
    auto v = juce::var (new juce::DynamicObject());
    v.getDynamicObject()->setProperty ("op", "redone");
    v.getDynamicObject()->setProperty ("id", (juce::int64) step->id);
    link.send (v);
    sendChangeMessage();
    return true;
}

void LimitlessUndoProcessor::compare (bool hearBefore)
{
    if (hearBefore)
    {
        if (undo())
        {
            const juce::ScopedLock hl (historyLock);
            if (auto* s = history.nextRedo())
                comparing = s->id;
        }
        return;
    }
    if (! comparing)
        return;
    bool same;
    {
        const juce::ScopedLock hl (historyLock);
        same = history.nextRedo() != nullptr && history.nextRedo()->id == *comparing;
    }
    comparing.reset();
    if (same)
        redo();
    sendChangeMessage();
}

int LimitlessUndoProcessor::undoCount() const
{
    const juce::ScopedLock hl (historyLock);
    return (int) history.undoSteps().size();
}

int LimitlessUndoProcessor::redoCount() const
{
    const juce::ScopedLock hl (historyLock);
    return (int) history.redoSteps().size();
}

juce::String LimitlessUndoProcessor::describeNext (bool forUndo) const
{
    const juce::ScopedLock hl (historyLock);
    auto* s = forUndo ? history.nextUndo() : history.nextRedo();
    if (s == nullptr)
        return {};
    juce::String text (s->label);
    auto value = forUndo ? s->before : s->after;
    if (! value.empty())
        text << (forUndo ? " back to " : " to ") << juce::String (value);
    return text;
}

//==============================================================================
// Saved with the session

void LimitlessUndoProcessor::getStateInformation (juce::MemoryBlock& dest)
{
    juce::XmlElement xml ("LimitlessUndo");
    xml.setAttribute ("version", 1);
    xml.setAttribute ("instance", instanceId);
    xml.setAttribute ("sendToHost", sendToHost);
    {
        // Not the audio lock: saving mustn't wait for, or be skipped because of, playback.
        const juce::ScopedLock sl (swapLock);
        if (hosted != nullptr)
        {
            xml.addChildElement (hosted->getPluginDescription().createXml().release());
            juce::MemoryBlock state;
            hosted->getStateInformation (state);
            xml.createNewChildElement ("STATE")->addTextElement (state.toBase64Encoding());
        }
    }
    {
        const juce::ScopedLock hl (historyLock);
        xml.createNewChildElement ("HISTORY")->addTextElement (juce::String (history.serialise()));
    }
    copyXmlToBinary (xml, dest);
}

void LimitlessUndoProcessor::setStateInformation (const void* data, int size)
{
    auto xml = getXmlFromBinary (data, size);
    if (xml == nullptr || ! xml->hasTagName ("LimitlessUndo"))
        return;

    auto restore = [this, xml = std::shared_ptr<juce::XmlElement> (std::move (xml))]
    {
        instanceId = xml->getStringAttribute ("instance", instanceId);
        sendToHost = xml->getBoolAttribute ("sendToHost", true);
        auto historyText = xml->getChildElementAllSubText ("HISTORY", {});

        juce::PluginDescription desc;
        auto* plugin = xml->getChildByName ("PLUGIN");
        if (plugin != nullptr && desc.loadFromXml (*plugin))
        {
            auto state = std::make_shared<juce::MemoryBlock>();
            state->fromBase64Encoding (xml->getChildElementAllSubText ("STATE", {}));
            loadPlugin (desc, nullptr, state, historyText);
        }
        else
        {
            unloadPlugin();
            sendMeta();
        }
    };

    // Plugins can only be opened on the message thread.
    if (juce::MessageManager::existsAndIsCurrentThread())
        restore();
    else
    {
        auto stillAlive = alive;
        juce::MessageManager::callAsync ([stillAlive, restore] { if (stillAlive->load()) restore(); });
    }
}

void LimitlessUndoProcessor::updateTrackProperties (const TrackProperties& props)
{
    trackName = props.name.value_or (juce::String());
    sendMeta();
}

//==============================================================================
// Talking to Limitless Keys

juce::var LimitlessUndoProcessor::stepVar (const limitless::Step& s) const
{
    auto v = juce::var (new juce::DynamicObject());
    auto* o = v.getDynamicObject();
    o->setProperty ("id", (juce::int64) s.id);
    o->setProperty ("label", juce::String (s.label));
    o->setProperty ("before", juce::String (s.before));
    o->setProperty ("after", juce::String (s.after));
    o->setProperty ("age", juce::jmax (0.0, now() - s.time));
    return v;
}

void LimitlessUndoProcessor::sendMeta()
{
    auto id = juce::var (new juce::DynamicObject());
    auto* o = id.getDynamicObject();
    o->setProperty ("instance", instanceId);
    o->setProperty ("host", juce::String (juce::PluginHostType().getHostDescription()));
    o->setProperty ("pid", processId());
    o->setProperty ("plugin", hostedName());
    o->setProperty ("track", trackName);
    o->setProperty ("version", JucePlugin_VersionString);
    link.setIdentity (id);

    auto meta = juce::var (new juce::DynamicObject());
    meta.getDynamicObject()->setProperty ("op", "meta");
    meta.getDynamicObject()->setProperty ("plugin", hostedName());
    meta.getDynamicObject()->setProperty ("track", trackName);
    link.send (meta);
}

void LimitlessUndoProcessor::sendSync()
{
    juce::Array<juce::var> undos, redos;
    {
        const juce::ScopedLock hl (historyLock);
        for (auto& s : history.undoSteps()) undos.add (stepVar (s));
        for (auto& s : history.redoSteps()) redos.add (stepVar (s));
    }
    auto v = juce::var (new juce::DynamicObject());
    v.getDynamicObject()->setProperty ("op", "sync");
    v.getDynamicObject()->setProperty ("undo", undos);
    v.getDynamicObject()->setProperty ("redo", redos);
    link.send (v);
}

void LimitlessUndoProcessor::linkConnected()
{
    sendMeta();
    sendSync();
    sendChangeMessage();
}

void LimitlessUndoProcessor::linkMessage (const juce::var& msg)
{
    auto op = msg.getProperty ("op", {}).toString();
    auto id = (uint64_t) (juce::int64) msg.getProperty ("id", 0);

    auto next = [this] (bool forUndo) -> uint64_t
    {
        const juce::ScopedLock hl (historyLock);
        auto* s = forUndo ? history.nextUndo() : history.nextRedo();
        return s != nullptr ? s->id : 0;
    };

    bool waiting;
    {
        const juce::ScopedLock hl (historyLock);
        waiting = history.hasPending();
    }

    if (op == "undo")
    {
        if (id != 0 && (next (true) == id || waiting))
        {
            undo();
            if (waiting)
                sendSync();   // a change still settling was newer than anything Keys knew of
        }
        else
            sendSync();       // Limitless Keys had an old picture of this plugin
    }
    else if (op == "redo")
    {
        if (id != 0 && next (false) == id)
            redo();
        else
            sendSync();
    }
}

//==============================================================================

juce::AudioProcessor* JUCE_CALLTYPE createPluginFilter()
{
    return new LimitlessUndoProcessor();
}
