#include "TopBar.h"
#include "PandaArt.h"
#include "Theme.h"

using namespace pd;
namespace colour = pd::theme::colour;

//==============================================================================
// Pick the song's key; every tunable drum follows it.
class TopBar::KeyPanel : public juce::Component
{
public:
    explicit KeyPanel (PandaDrumsProcessor& p) : proc (p)
    {
        proc.addChangeListener (&repainter);
        for (int n = 0; n < 12; ++n)
        {
            auto* b = roots.add (new juce::TextButton (midiNoteName (n, false)));
            b->setClickingTogglesState (false);
            b->onClick = [this, n] { auto k = proc.getKey(); k.root = n; if (k.isOff()) k.scale = 1; proc.setKey (k); sync(); };
            addAndMakeVisible (b);
        }
        for (size_t s = 0; s < scales().size(); ++s)
        {
            auto* b = scaleButtons.add (new juce::TextButton (s == 0 ? juce::String ("Off - no key") : juce::String (scales()[s].name)));
            b->onClick = [this, s] { auto k = proc.getKey(); k.scale = (int) s; proc.setKey (k); sync(); };
            addAndMakeVisible (b);
        }
        tuneNow.onClick = [this] { proc.tuneKitToKey(); proc.sendChangeMessage(); sync(); };
        tuneNow.setTooltip ("Retune the kick, snare and toms to the nearest notes of this key, keeping their order");
        autoTune.setToggleState (proc.autoTuneToKey, juce::dontSendNotification);
        autoTune.onClick = [this] { proc.autoTuneToKey = autoTune.getToggleState(); };
        addAndMakeVisible (tuneNow);
        addAndMakeVisible (autoTune);
        setSize (560, 430);
        sync();
    }

    void sync()
    {
        auto k = proc.getKey();
        for (int n = 0; n < 12; ++n)
            roots[n]->setToggleState (! k.isOff() && k.root == n, juce::dontSendNotification);
        for (int s = 0; s < scaleButtons.size(); ++s)
            scaleButtons[s]->setToggleState (k.scale == s, juce::dontSendNotification);
        tuneNow.setEnabled (! k.isOff());
        repaint();
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (14);
        r.removeFromTop (34);
        auto rootRow = r.removeFromTop (76);
        auto w = rootRow.getWidth() / 6;
        for (int n = 0; n < 12; ++n)
            roots[n]->setBounds (juce::Rectangle<int> (rootRow.getX() + (n % 6) * w, rootRow.getY() + (n / 6) * 38, w, 38).reduced (3));
        r.removeFromTop (8);
        auto scaleArea = r.removeFromTop (6 * 32);
        auto left = scaleArea.removeFromLeft (scaleArea.getWidth() / 2);
        for (int s = 0; s < scaleButtons.size(); ++s)
            scaleButtons[s]->setBounds (juce::Rectangle<int> ((s < 6 ? left : scaleArea).getX(), (s < 6 ? left : scaleArea).getY() + (s % 6) * 32,
                                                              left.getWidth(), 32).reduced (3));
        r.removeFromTop (10);
        auto bottom = r.removeFromTop (34);
        tuneNow.setBounds (bottom.removeFromLeft (190).reduced (2));
        bottom.removeFromLeft (10);
        autoTune.setBounds (bottom);
        notesArea = r;
    }

    void paint (juce::Graphics& g) override
    {
        g.fillAll (colour::plum);
        auto r = getLocalBounds().reduced (14);
        g.setColour (colour::mint);
        g.setFont (theme::display (24.0f));
        g.drawText ("SONG KEY:  " + proc.getKey().name().toUpperCase(), r.removeFromTop (30), juce::Justification::centredLeft);

        auto kit = proc.getKit();
        if (kit == nullptr)
            return;
        juce::String line;
        for (size_t p = 0; p < kit->pieces.size(); ++p)
            if (isTunable (kit->pieces[p].type))
                line << kit->pieces[p].name << " " << pitchName (proc.getPitch ((int) p)).upToFirstOccurrenceOf (" ", false, false)
                     << (proc.pitchInKey ((int) p) && ! proc.getKey().isOff() ? utf8 (" \xe2\x9c\x93") : juce::String()) << "    ";
        g.setColour (colour::textDim);
        g.setFont (theme::body (12.5f));
        g.drawFittedText (line, notesArea.reduced (2), juce::Justification::centredLeft, 2);
    }

    ~KeyPanel() override
    {
        proc.removeChangeListener (&repainter);
        setLookAndFeel (nullptr);
    }

private:
    struct Repainter : juce::ChangeListener
    {
        KeyPanel& owner;
        explicit Repainter (KeyPanel& k) : owner (k) {}
        void changeListenerCallback (juce::ChangeBroadcaster*) override { owner.repaint(); }
    };
    Repainter repainter { *this };
    PandaDrumsProcessor& proc;
    juce::OwnedArray<juce::TextButton> roots, scaleButtons;
    juce::TextButton tuneNow { "Tune kit to key" };
    juce::ToggleButton autoTune { "Retune when the key changes" };
    juce::Rectangle<int> notesArea;
};

//==============================================================================
TopBar::TopBar (PandaDrumsProcessor& p) : proc (p)
{
    int i = 0;
    for (auto* name : { "KIT", "MIXER", "LAB", "MAPPING" })
    {
        auto* b = tabs.add (new juce::TextButton (name));
        b->setRadioGroupId (77);
        b->setClickingTogglesState (true);
        b->onClick = [this, i] { setPage (i); if (onPage) onPage (i); };
        addAndMakeVisible (b);
        ++i;
    }
    tabs[0]->setToggleState (true, juce::dontSendNotification);
    tabs[2]->setTooltip ("Velocity & round robin lab: every sample in its lane");

    keyButton.setColour (juce::TextButton::buttonColourId, colour::mint.darker (0.55f));
    keyButton.setTooltip ("The song's key: every tunable drum snaps into it");
    keyButton.onClick = [this] { showKeyPanel(); };
    kitButton.setTooltip ("Load your kit folder, or go back to the factory kit");
    kitButton.onClick = [this] { showKitMenu(); };
    addAndMakeVisible (keyButton);
    addAndMakeVisible (kitButton);

    master.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
    master.setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
    master.setPopupDisplayEnabled (true, true, nullptr);
    master.setColour (juce::Slider::rotarySliderFillColourId, colour::gold);
    master.setDoubleClickReturnValue (true, 0.0);
    master.setTooltip ("Master volume");
    addAndMakeVisible (master);
    masterA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "master", master);
    refresh();
    startTimerHz (30);
}

TopBar::~TopBar() = default;

void TopBar::setPage (int i)
{
    page = i;
    for (int t = 0; t < tabs.size(); ++t)
        tabs[t]->setToggleState (t == i, juce::dontSendNotification);
}

void TopBar::refresh()
{
    keyButton.setButtonText ("KEY  " + proc.getKey().name().toUpperCase() + utf8 ("  \xe2\x96\xbe"));
    auto kit = proc.getKit();
    auto name = kit != nullptr ? kit->name : juce::String ("No kit");
    if (proc.isLoading())
        name = "Loading...";
    kitButton.setButtonText (name + utf8 ("  \xe2\x96\xbe"));
    repaint();
}

void TopBar::resized()
{
    auto r = getLocalBounds().reduced (10, 10);
    r.removeFromLeft (300);
    auto right = r.removeFromRight (520);
    meterArea = right.removeFromRight (16).reduced (0, 4).toFloat();
    right.removeFromRight (4);
    master.setBounds (right.removeFromRight (44));
    right.removeFromRight (10);
    kitButton.setBounds (right.removeFromRight (210));
    right.removeFromRight (8);
    keyButton.setBounds (right.removeFromRight (220));
    auto w = std::min (110, r.getWidth() / tabs.size());
    auto x = r.getX() + (r.getWidth() - w * tabs.size()) / 2;
    for (int t = 0; t < tabs.size(); ++t)
        tabs[t]->setBounds (juce::Rectangle<int> (x + t * w, r.getY(), w, r.getHeight()).reduced (3, 0));
}

void TopBar::paint (juce::Graphics& g)
{
    auto r = getLocalBounds().toFloat();
    g.setGradientFill (juce::ColourGradient (colour::plumLight, 0.0f, 0.0f, colour::plum, 0.0f, r.getBottom(), false));
    g.fillRect (r);
    g.setColour (colour::hot);
    g.fillRect (r.removeFromBottom (3.0f));

    auto logo = juce::Rectangle<float> (12.0f, 4.0f, 58.0f, 58.0f);
    g.setColour (colour::pink);
    g.fillEllipse (logo.reduced (2.0f));
    g.setColour (colour::ink);
    g.drawEllipse (logo.reduced (2.0f), 2.5f);
    {
        juce::Graphics::ScopedSaveState s (g);
        juce::Path clip;
        clip.addEllipse (logo.reduced (3.0f));
        g.reduceClipRegion (clip);
        art::drawPandaBadge (g, logo.reduced (1.0f).translated (0.0f, 4.0f));
    }
    theme::drawTextOutlined (g, "PANDA DRUMS", { 78.0f, 6.0f, 200.0f, 36.0f }, theme::display (32.0f), colour::cream, colour::ink, 5.0f,
                             juce::Justification::centredLeft);
    g.setColour (colour::hot);
    g.setFont (theme::title (14.0f));
    g.drawText (utf8 ("vol. one  \xc2\xb7  in key with any song"), juce::Rectangle<float> (80.0f, 40.0f, 230.0f, 18.0f), juce::Justification::centredLeft);

    auto half = meterArea.getWidth() * 0.5f - 1.0f;
    for (int s = 0; s < 2; ++s)
    {
        auto m = juce::Rectangle<float> (meterArea.getX() + (half + 2.0f) * (float) s, meterArea.getY(), half, meterArea.getHeight());
        g.setColour (colour::ink);
        g.fillRoundedRectangle (m, 2.0f);
        auto lvl = s == 0 ? levelL : levelR;
        auto frac = juce::jlimit (0.0f, 1.0f, (juce::Decibels::gainToDecibels (lvl, -60.0f) + 60.0f) / 66.0f);
        g.setGradientFill (juce::ColourGradient (colour::mint, m.getX(), m.getBottom(), colour::bad, m.getX(), m.getY(), false));
        g.fillRoundedRectangle (m.withTop (m.getBottom() - m.getHeight() * frac), 2.0f);
    }
}

void TopBar::timerCallback()
{
    levelL = std::max (proc.takeMasterPeak (0), levelL * 0.85f);
    levelR = std::max (proc.takeMasterPeak (1), levelR * 0.85f);
    repaint (meterArea.getSmallestIntegerContainer().expanded (2));
}

void TopBar::showKeyPanel()
{
    auto panel = std::make_unique<KeyPanel> (proc);
    panel->setLookAndFeel (&getLookAndFeel());
    juce::CallOutBox::launchAsynchronously (std::move (panel), keyButton.getScreenBounds(), nullptr);
}

void TopBar::showKitMenu()
{
    juce::PopupMenu m;
    m.addSectionHeader ("KIT");
    m.addItem (1, "Factory kit (built in)", true, proc.getKit() != nullptr && proc.getKit()->isFactory);
    m.addItem (2, "Load my kit folder...");
    m.addItem (3, "Reload the kit folder", proc.getKitFolder().isDirectory());
    m.addItem (4, "Show the kit folder", proc.getKitFolder().isDirectory());
    m.addSeparator();
    m.addItem (5, "Write panda-kit.json (check the mics and sizes)...", proc.getKit() != nullptr && ! proc.getKit()->isFactory);
    auto message = proc.getLoadMessage();
    if (message.isNotEmpty())
    {
        m.addSeparator();
        m.addItem (99, message, false);
    }
    m.showMenuAsync (juce::PopupMenu::Options().withTargetComponent (&kitButton), [this] (int r)
    {
        if (r == 1)
            proc.loadFactoryKit();
        else if (r == 2)
        {
            chooser = std::make_unique<juce::FileChooser> ("Choose your kit folder (one folder per drum inside)",
                                                           proc.getKitFolder().isDirectory() ? proc.getKitFolder() : juce::File::getSpecialLocation (juce::File::userMusicDirectory));
            chooser->launchAsync (juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectDirectories, [this] (const juce::FileChooser& fc)
            {
                auto f = fc.getResult();
                if (f.isDirectory())
                    proc.loadKitFolder (f);
            });
        }
        else if (r == 3)
            proc.reloadKit();
        else if (r == 4)
            proc.getKitFolder().revealToUser();
        else if (r == 5)
        {
            auto kit = proc.getKit();
            auto target = proc.getKitFolder().getChildFile ("panda-kit.json");
            if (kit != nullptr && KitLoader::writeManifestTemplate (*kit, target))
                target.revealToUser();
        }
        refresh();
    });
}
