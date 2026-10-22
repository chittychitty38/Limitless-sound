#pragma once

#include "PandaStage.h"

// The main page: the panda on stage, a strip with every drum's swap and tune arrows, the
// card telling you exactly which sample just played, and tools for testing one drum.
class KitPage : public juce::Component, private juce::Timer
{
public:
    explicit KitPage (PandaDrumsProcessor&);
    ~KitPage() override;

    void resized() override;
    void paint (juce::Graphics&) override;
    void refresh();                                   // kit, variant, tuning or key changed
    void onHit (const pd::HitEvent&);

    PandaStage stage;

private:
    class DrumStrip;
    class LastHitCard;
    class DrumPanel;
    class StageToggles;

    void timerCallback() override;
    void select (int piece);
    void velocitySweep();
    void cycleRounds();

    PandaDrumsProcessor& proc;
    std::unique_ptr<DrumStrip> strip;
    std::unique_ptr<LastHitCard> card;
    std::unique_ptr<DrumPanel> panel;
    std::unique_ptr<StageToggles> toggles;

    struct Queued { double at; int piece, artic, velocity, hit; };
    std::vector<Queued> queue;
};
