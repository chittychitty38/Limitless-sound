#pragma once

#include "../PluginProcessor.h"

// Which note plays which drum: built-in maps (General MIDI, Toontrack style, Roland e-kits),
// saving and loading your own, MIDI learn, and the chromatic keys.
class MappingPage : public juce::Component, private juce::Timer
{
public:
    explicit MappingPage (PandaDrumsProcessor&);
    ~MappingPage() override;

    void resized() override;
    void paint (juce::Graphics&) override;
    void refresh();

private:
    class Rows;
    class Keys;

    void timerCallback() override;
    void learn (int row);
    void clearRow (int row);
    void pushChromatic();

    PandaDrumsProcessor& proc;
    std::unique_ptr<Rows> rows;
    std::unique_ptr<Keys> keys;
    juce::Viewport viewport;
    juce::ComboBox preset;
    juce::TextButton save { "Save map..." }, load { "Load map..." }, reset { "Default" };
    juce::ToggleButton chromaticOn { "Chromatic drum on the keys" }, snap { "Snap to the song's key" };
    juce::ComboBox chromaticPiece, low, high;
    juce::Label pieceL, lowL, highL;
    std::unique_ptr<juce::FileChooser> chooser;
    juce::Rectangle<int> chromaticArea;
    int learning = -1;
};
