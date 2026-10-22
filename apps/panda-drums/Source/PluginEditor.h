#pragma once

#include "PluginProcessor.h"
#include "gui/KitPage.h"
#include "gui/LabPage.h"
#include "gui/MappingPage.h"
#include "gui/MixerPage.h"
#include "gui/Theme.h"
#include "gui/TopBar.h"

// Everything is laid out on a 1280 x 860 canvas and scaled to the window, so it looks the
// same at any size.
class PandaDrumsEditor : public juce::AudioProcessorEditor,
                         private juce::ChangeListener,
                         private juce::Timer
{
public:
    static constexpr int designW = 1280, designH = 860, barH = 64;

    explicit PandaDrumsEditor (PandaDrumsProcessor&);
    ~PandaDrumsEditor() override;

    void paint (juce::Graphics&) override;
    void resized() override;

    void showPage (int);
    int getPage() const { return page; }
    KitPage& getKitPage() { return *kitPage; }
    LabPage& getLabPage() { return *labPage; }
    TopBar& getTopBar() { return *topBar; }

    // Moves hits from the engine to the screen. The render tool passes its own clock and
    // tells it exactly when each hit is heard.
    void pumpEvents (double now, std::function<double (const pd::HitEvent&)> strikeTime = {});
    void setStageLive (bool live) { kitPage->stage.setLive (live); if (! live) stopTimer(); }
    void refreshAll();

private:
    void changeListenerCallback (juce::ChangeBroadcaster*) override;
    void timerCallback() override;

    PandaDrumsProcessor& proc;
    pd::theme::LookAndFeel lookAndFeel;
    juce::Component content;
    std::unique_ptr<TopBar> topBar;
    std::unique_ptr<KitPage> kitPage;
    std::unique_ptr<MixerPage> mixerPage;
    std::unique_ptr<LabPage> labPage;
    std::unique_ptr<MappingPage> mappingPage;
    pd::theme::Tooltips tooltips { this };
    int page = 0;
    juce::uint32 lastGeneration = 0;
};
