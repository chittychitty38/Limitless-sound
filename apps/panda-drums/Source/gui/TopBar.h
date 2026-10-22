#pragma once

#include "../PluginProcessor.h"

// Logo, the pages, the song's key, the kit menu and the master level.
class TopBar : public juce::Component, private juce::Timer
{
public:
    explicit TopBar (PandaDrumsProcessor&);
    ~TopBar() override;

    void resized() override;
    void paint (juce::Graphics&) override;
    void paintOverChildren (juce::Graphics&) override;
    void refresh();
    void setPage (int);
    std::function<void (int)> onPage;

    // The song's key panel, on the pack's dialog under the key button, inside the window.
    void showKeyPanel();
    void closeKeyPanel();

private:
    class KeyPanel;
    void timerCallback() override;
    void drawMeters (juce::Graphics&);
    void showKitMenu();

    PandaDrumsProcessor& proc;
    juce::OwnedArray<juce::TextButton> tabs;
    juce::TextButton keyButton, kitButton;
    juce::Slider master;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> masterA;
    std::unique_ptr<juce::FileChooser> chooser;
    // The open key panel and the call-out it sits in. Ours, not the modal manager's, so the window
    // can close with it open: both go before the bar does.
    std::unique_ptr<KeyPanel> keyPanel;
    std::unique_ptr<juce::CallOutBox> keyBox;
    int keyPanelCount = 0;
    juce::Rectangle<float> meterArea;
    float levelL = 0.0f, levelR = 0.0f;
    int page = 0;
};
