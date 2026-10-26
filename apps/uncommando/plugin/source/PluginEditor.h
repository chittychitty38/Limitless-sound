// The Uncommando window: a bar with Undo, Redo and "hold to hear before",
// and the window of the plugin inside underneath it.

#pragma once

#include "PluginBrowser.h"
#include "PluginProcessor.h"

class UncommandoEditor : public juce::AudioProcessorEditor,
                            private juce::ChangeListener,
                            private juce::ComponentListener,
                            private juce::Timer
{
public:
    explicit UncommandoEditor (UncommandoProcessor&);
    ~UncommandoEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;
    bool keyPressed (const juce::KeyPress&) override;

private:
    // Plays the sound before the last change while it's held down.
    struct HoldButton : juce::TextButton
    {
        using TextButton::TextButton;
        std::function<void (bool)> onHold;
        void mouseDown (const juce::MouseEvent& e) override { TextButton::mouseDown (e); if (onHold) onHold (true); }
        void mouseUp (const juce::MouseEvent& e) override { TextButton::mouseUp (e); if (onHold) onHold (false); }
    };

    void changeListenerCallback (juce::ChangeBroadcaster*) override;
    void componentMovedOrResized (juce::Component&, bool wasMoved, bool wasResized) override;
    void timerCallback() override;

    void showHosted();
    void showBrowser();
    void refresh();
    void fit();

    UncommandoProcessor& proc;
    static constexpr int barHeight = 92;
    const juce::AudioPluginInstance* shownFor = nullptr;   // compared, never used

    juce::Label title, status;
    juce::TextButton pluginButton, undoButton { "Undo" }, redoButton { "Redo" };
    HoldButton compareButton { "Hold: before" };
    juce::ToggleButton sendToHost { "DAW sees knob moves" };

    std::unique_ptr<juce::AudioProcessorEditor> inner;
    std::unique_ptr<PluginBrowser> browser;
    juce::Label empty;

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (UncommandoEditor)
};
