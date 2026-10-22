#pragma once

#include "../PluginProcessor.h"

// The velocity and round robin lab: every recorded hit of a drum laid out in its velocity
// lane, so each one can be auditioned, compared and taken out if it's weird.
class LabPage : public juce::Component
{
public:
    explicit LabPage (PandaDrumsProcessor&);
    ~LabPage() override;

    void resized() override;
    void paint (juce::Graphics&) override;
    void refresh();
    void onHit (const pd::HitEvent&);

private:
    class DrumList;
    class Lanes;
    class Grid;

    void select (int piece, int artic);
    void pushZoneSettings();
    void exportText (const juce::String& title, const juce::String& fileName, const juce::String& text);

    PandaDrumsProcessor& proc;
    std::unique_ptr<DrumList> list;
    std::unique_ptr<Lanes> lanes;
    std::unique_ptr<Grid> grid;
    int piece = 0, artic = 0;

    juce::ComboBox source, zones, ranges, rrMode;
    juce::Slider levelMatch, build, curve, humanize;
    juce::Label sourceL, zonesL, rangesL, rrL, levelL, buildL, curveL, humanizeL;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> buildA, curveA, humanizeA;
    std::unique_ptr<juce::AudioProcessorValueTreeState::ComboBoxAttachment> rrA;
    juce::TextButton report { "Save report..." }, badList { "Save bad list..." }, clear { "Clear marks" };
    std::unique_ptr<juce::FileChooser> chooser;
};
