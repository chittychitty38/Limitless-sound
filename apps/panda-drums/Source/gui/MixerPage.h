#pragma once

#include "../PluginProcessor.h"

// One channel strip per mic the kit was recorded with. Overheads, rooms and far rooms (any
// channel, in fact) open up to show a fader for every drum inside them.
class MixerPage : public juce::Component, private juce::Timer
{
public:
    explicit MixerPage (PandaDrumsProcessor&);
    ~MixerPage() override;

    void resized() override;
    void paint (juce::Graphics&) override;
    void refresh();

private:
    class Strip;
    class MasterStrip;
    class InsidePanel;

    void timerCallback() override;
    void openInside (int mic);

    PandaDrumsProcessor& proc;
    juce::OwnedArray<Strip> strips;
    std::unique_ptr<MasterStrip> master;
    std::unique_ptr<InsidePanel> inside;
    juce::Viewport viewport;
    juce::Component holder;
    int numMics = 0;
};
