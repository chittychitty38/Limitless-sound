#include "PluginEditor.h"

static const juce::Colour background (0xff111111), bar (0xff1c1c1c), yellow (0xffffcc00);

LimitlessUndoEditor::LimitlessUndoEditor (LimitlessUndoProcessor& p)
    : AudioProcessorEditor (p), proc (p)
{
    // "Limitless Undo" in plain text also lets Limitless Keys see that this window
    // reports its own changes.
    title.setText ("Limitless Undo", juce::dontSendNotification);
    title.setFont (juce::FontOptions (18.0f, juce::Font::bold));
    title.setColour (juce::Label::textColourId, yellow);
    addAndMakeVisible (title);

    pluginButton.setTooltip ("Choose the plugin inside");
    pluginButton.onClick = [this] { showBrowser(); };
    addAndMakeVisible (pluginButton);

    undoButton.setTitle ("Undo plugin change");
    undoButton.setTooltip ("Undo the last change to this plugin. With Limitless Keys: Option Command Z, in any plugin.");
    undoButton.onClick = [this] { proc.undo(); };
    redoButton.setTitle ("Redo plugin change");
    redoButton.onClick = [this] { proc.redo(); };
    compareButton.setTitle ("Hold to hear before the last change");
    compareButton.setTooltip ("Hold to hear the sound before your last change; let go to hear it after.");
    compareButton.onHold = [this] (bool down) { proc.compare (down); };
    for (auto* b : { &undoButton, &redoButton, (juce::TextButton*) &compareButton })
    {
        b->setColour (juce::TextButton::buttonColourId, juce::Colour (0xff2a2a2a));
        addAndMakeVisible (*b);
    }

    sendToHost.setToggleState (proc.sendToHost, juce::dontSendNotification);
    sendToHost.setTooltip ("On: the DAW records these knob moves as automation and may put them in its own "
                           "undo. Off: they stay out of the DAW's undo, so Command Z never undoes them.");
    sendToHost.onClick = [this] { proc.sendToHost = sendToHost.getToggleState(); };
    addAndMakeVisible (sendToHost);

    status.setFont (juce::FontOptions (14.0f));
    status.setColour (juce::Label::textColourId, juce::Colours::lightgrey);
    status.setJustificationType (juce::Justification::centredRight);
    addAndMakeVisible (status);

    empty.setText ("Choose a plugin to put inside Limitless Undo. Every change you make to it can then be "
                   "undone on its own: Option Command Z with Limitless Keys, or the Undo button above.",
                   juce::dontSendNotification);
    empty.setFont (juce::FontOptions (18.0f));
    empty.setJustificationType (juce::Justification::centred);
    empty.setColour (juce::Label::textColourId, juce::Colours::white);
    addChildComponent (empty);

    proc.onHostedChanging = [this] { if (inner != nullptr) { inner->removeComponentListener (this); inner.reset(); } };
    proc.addChangeListener (this);

    setResizable (false, false);
    setSize (760, barHeight + 420);
    showHosted();
    refresh();
    startTimerHz (4);
}

LimitlessUndoEditor::~LimitlessUndoEditor()
{
    proc.onHostedChanging = nullptr;
    proc.removeChangeListener (this);
    if (inner != nullptr)
        inner->removeComponentListener (this);
    inner.reset();
}

void LimitlessUndoEditor::showHosted()
{
    browser.reset();
    shownFor = proc.getHosted();
    if (inner != nullptr)
    {
        inner->removeComponentListener (this);
        inner.reset();
    }
    if (auto* h = proc.getHosted())
    {
        juce::AudioProcessorEditor* ed = h->hasEditor() ? h->createEditorIfNeeded() : nullptr;
        if (ed == nullptr)
            ed = new juce::GenericAudioProcessorEditor (*h);
        inner.reset (ed);
        addAndMakeVisible (*inner);
        inner->addComponentListener (this);
        empty.setVisible (false);
    }
    else
        empty.setVisible (true);
    fit();
}

void LimitlessUndoEditor::showBrowser()
{
    if (inner != nullptr)
        inner->setVisible (false);
    empty.setVisible (false);
    browser = std::make_unique<PluginBrowser> (proc.formatManager, LimitlessUndoProcessor::isInstrument);
    browser->onCancel = [this]
    {
        juce::MessageManager::callAsync ([safe = juce::Component::SafePointer<LimitlessUndoEditor> (this)]
        {
            if (safe != nullptr)
            {
                safe->browser.reset();
                if (safe->inner != nullptr)
                    safe->inner->setVisible (true);
                else
                    safe->empty.setVisible (true);
                safe->fit();
            }
        });
    };
    browser->onChoose = [this] (const juce::PluginDescription& desc)
    {
        status.setText ("Opening " + desc.name + "…", juce::dontSendNotification);
        auto safe = juce::Component::SafePointer<LimitlessUndoEditor> (this);
        juce::MessageManager::callAsync ([safe, desc]
        {
            if (safe == nullptr)
                return;
            safe->browser.reset();
            safe->proc.loadPlugin (desc, [safe] (juce::String error)
            {
                if (safe == nullptr)
                    return;
                if (error.isNotEmpty())
                    safe->status.setText (error, juce::dontSendNotification);
                safe->showHosted();
                safe->refresh();
            });
        });
    };
    addAndMakeVisible (*browser);
    setSize (juce::jmax (getWidth(), 760), barHeight + 520);
    resized();
}

void LimitlessUndoEditor::fit()
{
    if (browser != nullptr)
        return;
    if (inner != nullptr)
        setSize (juce::jmax (inner->getWidth(), 760), barHeight + inner->getHeight());
    else
        setSize (760, barHeight + 420);
    resized();
}

void LimitlessUndoEditor::componentMovedOrResized (juce::Component& c, bool, bool wasResized)
{
    if (wasResized && &c == inner.get())
        fit();
}

void LimitlessUndoEditor::changeListenerCallback (juce::ChangeBroadcaster*)
{
    // The plugin inside changed (or was loaded from the session): show its window.
    auto* h = proc.getHosted();
    if (browser == nullptr && (h != shownFor || (inner == nullptr) != (h == nullptr)))
        showHosted();
    refresh();
}

void LimitlessUndoEditor::timerCallback()
{
    refresh();
}

void LimitlessUndoEditor::refresh()
{
    auto name = proc.hostedName();
    pluginButton.setButtonText (name.isNotEmpty() ? name + "  ▾" : "Choose a plugin…");
    pluginButton.setTitle (name.isNotEmpty() ? "Plugin inside: " + name + ". Press to change it." : "Choose a plugin");

    auto undos = proc.undoCount(), redos = proc.redoCount();
    undoButton.setEnabled (undos > 0);
    redoButton.setEnabled (redos > 0);
    compareButton.setEnabled (undos > 0 || proc.isComparing());
    undoButton.setTooltip (undos > 0 ? "Undo " + proc.describeNext (true) : "Nothing to undo yet");
    redoButton.setTooltip (redos > 0 ? "Redo " + proc.describeNext (false) : "Nothing to redo");

    if (! status.getText().startsWith ("Opening") || name.isNotEmpty())
    {
        juce::String text;
        text << undos << (undos == 1 ? " change" : " changes");
        text << (proc.isLinked() ? "  ·  Limitless Keys: ⌥⌘Z ready" : "  ·  Limitless Keys not running");
        status.setText (text, juce::dontSendNotification);
    }
}

bool LimitlessUndoEditor::keyPressed (const juce::KeyPress& key)
{
    // While this window has the keyboard: ⌥⌘Z undo, ⌥⇧⌘Z redo, as everywhere else.
    auto mods = key.getModifiers();
    if (key.getKeyCode() == 'Z' || key.getKeyCode() == 'z')
        if (mods.isCommandDown() && mods.isAltDown())
        {
            mods.isShiftDown() ? proc.redo() : proc.undo();
            return true;
        }
    return false;
}

void LimitlessUndoEditor::paint (juce::Graphics& g)
{
    g.fillAll (background);
    g.setColour (bar);
    g.fillRect (0, 0, getWidth(), barHeight);
}

void LimitlessUndoEditor::resized()
{
    auto r = getLocalBounds();
    auto top = r.removeFromTop (barHeight).reduced (10, 8);
    auto first = top.removeFromTop (36);
    top.removeFromTop (4);
    auto second = top;

    title.setBounds (first.removeFromLeft (140));
    pluginButton.setBounds (first.removeFromLeft (240));
    status.setBounds (first);

    undoButton.setBounds (second.removeFromLeft (100));
    second.removeFromLeft (6);
    redoButton.setBounds (second.removeFromLeft (100));
    second.removeFromLeft (6);
    compareButton.setBounds (second.removeFromLeft (140));
    second.removeFromLeft (12);
    sendToHost.setBounds (second.removeFromLeft (240));

    if (browser != nullptr)
        browser->setBounds (r);
    if (inner != nullptr)
        inner->setTopLeftPosition (0, barHeight);
    empty.setBounds (r.reduced (40));
}
