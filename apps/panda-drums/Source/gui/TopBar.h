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
    void refresh();
    void setPage (int);
    std::function<void (int)> onPage;

private:
    class KeyPanel;
    void timerCallback() override;
    void showKeyPanel();
    void showKitMenu();

    PandaDrumsProcessor& proc;
    juce::OwnedArray<juce::TextButton> tabs;
    juce::TextButton keyButton, kitButton;
    juce::Slider master;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> masterA;
    std::unique_ptr<juce::FileChooser> chooser;
    juce::Rectangle<float> meterArea;
    float levelL = 0.0f, levelR = 0.0f;
    int page = 0;
};
