#include "PluginEditor.h"

using namespace pd;

PandaDrumsEditor::PandaDrumsEditor (PandaDrumsProcessor& p) : AudioProcessorEditor (p), proc (p)
{
    // Read the remembered size first: setting up the resize limits below already resizes the editor.
    auto savedWidth = (int) proc.uiState.getProperty ("width", designW * 88 / 100);
    setLookAndFeel (&lookAndFeel);

    topBar = std::make_unique<TopBar> (p);
    kitPage = std::make_unique<KitPage> (p);
    mixerPage = std::make_unique<MixerPage> (p);
    labPage = std::make_unique<LabPage> (p);
    mappingPage = std::make_unique<MappingPage> (p);

    content.setSize (designW, designH);
    content.addAndMakeVisible (*topBar);
    for (auto* c : std::initializer_list<juce::Component*> { kitPage.get(), mixerPage.get(), labPage.get(), mappingPage.get() })
        content.addChildComponent (c);
    topBar->setBounds (0, 0, designW, barH);
    for (auto* c : std::initializer_list<juce::Component*> { kitPage.get(), mixerPage.get(), labPage.get(), mappingPage.get() })
        c->setBounds (0, barH, designW, designH - barH);
    addAndMakeVisible (content);
    topBar->onPage = [this] (int i) { showPage (i); };

    proc.addChangeListener (this);
    showPage ((int) proc.uiState.getProperty ("page", 0));

    setResizable (true, true);
    getConstrainer()->setFixedAspectRatio ((double) designW / (double) designH);
    setResizeLimits (designW * 55 / 100, designH * 55 / 100, designW * 3 / 2, designH * 3 / 2);
    auto w = juce::jlimit (designW * 55 / 100, designW * 3 / 2, savedWidth);
    setSize (w, w * designH / designW);
    startTimerHz (60);
}

PandaDrumsEditor::~PandaDrumsEditor()
{
    proc.removeChangeListener (this);
    setLookAndFeel (nullptr);
}

void PandaDrumsEditor::paint (juce::Graphics& g)
{
    g.fillAll (theme::colour::plum);
}

void PandaDrumsEditor::resized()
{
    auto s = (float) getWidth() / (float) designW;
    content.setTransform (juce::AffineTransform::scale (s));
    proc.uiState.setProperty ("width", getWidth(), nullptr);
}

void PandaDrumsEditor::showPage (int i)
{
    page = juce::jlimit (0, 3, i);
    kitPage->setVisible (page == 0);
    mixerPage->setVisible (page == 1);
    labPage->setVisible (page == 2);
    mappingPage->setVisible (page == 3);
    topBar->setPage (page);
    proc.uiState.setProperty ("page", page, nullptr);
    if (page == 1) mixerPage->refresh();
    if (page == 2) labPage->refresh();
    if (page == 3) mappingPage->refresh();
}

void PandaDrumsEditor::refreshAll()
{
    topBar->refresh();
    kitPage->refresh();
    mixerPage->refresh();
    labPage->refresh();
    mappingPage->refresh();
}

void PandaDrumsEditor::changeListenerCallback (juce::ChangeBroadcaster*)
{
    refreshAll();
}

void PandaDrumsEditor::pumpEvents (double now, std::function<double (const HitEvent&)> strikeTime)
{
    auto sr = std::max (1.0, proc.getSampleRate());
    auto latency = proc.getShowtimeLatency() + proc.getBlockSize();
    auto blockWall = proc.getClockWallMs() * 0.001;
    auto blockClock = proc.getClock();
    HitEvent e;
    while (proc.hitEvents.pop (e))
    {
        // When will this hit be heard? The engine's clock, mapped onto the wall clock.
        auto strike = strikeTime ? strikeTime (e) : blockWall + (double) (e.time - blockClock + latency) / sr;
        if (strike < now - 0.5)
            continue;   // played while the window was closed: don't replay it now
        kitPage->stage.hit (e, std::max (now, strike));
        kitPage->onHit (e);
        labPage->onHit (e);
    }
}

void PandaDrumsEditor::timerCallback()
{
    pumpEvents (PandaStage::nowSeconds());
    if (auto snap = proc.getSnapshot(); snap != nullptr && snap->generation != lastGeneration)
    {
        lastGeneration = snap->generation;
        kitPage->refresh();
        topBar->refresh();
    }
}
