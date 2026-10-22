#include "TopBar.h"
#include "PandaArt.h"
#include "Theme.h"
#include "UiKit.h"

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
        theme::look (tuneNow, "button_key_selector_blank");
        theme::accent (autoTune, "teal");
        tuneNow.onClick = [this] { proc.tuneKitToKey(); proc.sendChangeMessage(); sync(); };
        tuneNow.setTooltip ("Retune the kick, snare and toms to the nearest notes of this key, keeping their order");
        autoTune.setToggleState (proc.autoTuneToKey, juce::dontSendNotification);
        autoTune.onClick = [this] { proc.setAutoTuneToKey (autoTune.getToggleState()); };
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
        auto r = getLocalBounds().reduced (14);
        auto head = r.removeFromTop (30).toFloat();
        ui::label (g, "SONG KEY", head.removeFromLeft (100.0f), ui::colour::textDim, 13.0f, juce::Justification::centredLeft);
        ui::label (g, proc.getKey().name().toUpperCase(), head, ui::colour::teal.brighter (0.35f), 20.0f, juce::Justification::centredLeft);

        auto kit = proc.getKit();
        if (kit == nullptr)
            return;
        juce::String line;
        for (size_t p = 0; p < kit->pieces.size(); ++p)
            if (isTunable (kit->pieces[p].type))
                line << kit->pieces[p].name << " " << pitchName (proc.getPitch ((int) p)).upToFirstOccurrenceOf (" ", false, false)
                     << (proc.pitchInKey ((int) p) && ! proc.getKey().isOff() ? utf8 (" \xe2\x9c\x93") : juce::String()) << "    ";
        g.setColour (colour::textDim);
        g.setFont (ui::font (11.5f));
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
        theme::look (*b, "button_tab_inactive", "button_tab_" + juce::String (name).toLowerCase() + "_active");
        b->setRadioGroupId (77);
        b->setClickingTogglesState (true);
        b->onClick = [this, i] { setPage (i); if (onPage) onPage (i); };
        addAndMakeVisible (b);
        ++i;
    }
    tabs[0]->setToggleState (true, juce::dontSendNotification);
    tabs[2]->setTooltip ("Velocity & round robin lab: every sample in its lane");

    keyButton.setTooltip ("The song's key: every tunable drum snaps into it");
    keyButton.onClick = [this] { showKeyPanel(); };
    kitButton.setTooltip ("Load your kit folder, or go back to the factory kit");
    kitButton.onClick = [this] { showKitMenu(); };
    addAndMakeVisible (keyButton);
    addAndMakeVisible (kitButton);

    master.setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
    master.setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
    master.setPopupDisplayEnabled (true, true, nullptr);
    master.setDoubleClickReturnValue (true, 0.0);
    master.setTooltip ("Master volume");
    addAndMakeVisible (master);
    masterA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "master", master);
    refresh();
    startTimerHz (30);
}

TopBar::~TopBar()
{
    if (auto* box = keyBox.getComponent())
        delete box;
}

void TopBar::setPage (int i)
{
    page = i;
    for (int t = 0; t < tabs.size(); ++t)
        tabs[t]->setToggleState (t == i, juce::dontSendNotification);
}

void TopBar::refresh()
{
    // The pack's selectors have the factory kit and D minor lettered on them; any other kit or
    // key goes on the blank ones in the same lettering.
    auto key = proc.getKey();
    auto keyName = key.isOff() ? juce::String ("OFF") : key.name().toUpperCase();
    keyButton.setButtonText ("KEY " + keyName);
    theme::look (keyButton, keyName == "D MINOR" ? "button_key_selector" : "button_key_selector_blank");
    auto kit = proc.getKit();
    auto name = kit != nullptr ? kit->name : juce::String ("No kit");
    if (proc.isLoading())
        name = "Loading...";
    kitButton.setButtonText (name);
    theme::look (kitButton, kit != nullptr && kit->isFactory && name == "Panda Factory Kit" && ! proc.isLoading()
                                ? "button_kit_selector" : "button_kit_selector_blank");
    if (auto* panel = dynamic_cast<KeyPanel*> (keyPanel.getComponent()))
        panel->sync();
    repaint();
}

void TopBar::resized()
{
    // The pack's nav bar holds tabs and selectors at their own height.
    auto r = getLocalBounds().reduced (4, 3).reduced (0, 7);
    auto x = 292;
    for (int t = 0; t < tabs.size(); ++t)
        tabs[t]->setBounds (x + t * 126, r.getY(), 120, r.getHeight());
    x += 4 * 126 + 6;
    keyButton.setBounds (x, r.getY(), 190, r.getHeight());
    kitButton.setBounds (keyButton.getRight() + 8, r.getY(), 190, r.getHeight());
    master.setBounds (kitButton.getRight() + 6, r.getY(), 44, r.getHeight());
    meterArea = juce::Rectangle<float> ((float) master.getRight() + 6.0f, (float) r.getY() + 1.0f, 18.0f, (float) r.getHeight() - 2.0f);
}

void TopBar::paintOverChildren (juce::Graphics& g)
{
    for (auto* b : { &keyButton, &kitButton })
    {
        auto r = b->getBounds().toFloat();
        auto down = b->isDown();
        ui::icon (g, "icon_dropdown", r.removeFromRight (r.getHeight()).reduced (r.getHeight() * 0.33f).translated (-4.0f, down ? 1.0f : 0.0f));
    }
}

void TopBar::paint (juce::Graphics& g)
{
    auto r = getLocalBounds().toFloat();
    g.fillAll (colour::plum);
    ui::panel (g, "panel_top_navigation_bar", r.reduced (4.0f, 3.0f));

    auto logo = juce::Rectangle<float> (14.0f, 6.0f, 52.0f, 52.0f);
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
    theme::drawTextOutlined (g, "PANDA DRUMS", { 76.0f, 8.0f, 200.0f, 32.0f }, theme::display (29.0f), colour::cream, colour::ink, 5.0f,
                             juce::Justification::centredLeft);
    ui::label (g, utf8 ("vol. one  \xc2\xb7  in key with any song"), { 78.0f, 39.0f, 205.0f, 16.0f }, colour::hot, 10.5f,
               juce::Justification::centredLeft);
    drawMeters (g);
}

void TopBar::drawMeters (juce::Graphics& g)
{
    // Left and right in the pack's teal readout, stood on end.
    auto half = meterArea.getWidth() * 0.5f - 1.0f;
    for (int s = 0; s < 2; ++s)
    {
        auto m = juce::Rectangle<float> (meterArea.getX() + (half + 2.0f) * (float) s, meterArea.getY(), half, meterArea.getHeight());
        ui::readout (g, "readout_zone_v", m);
        auto lvl = s == 0 ? levelL : levelR;
        auto frac = juce::jlimit (0.0f, 1.0f, (juce::Decibels::gainToDecibels (lvl, -60.0f) + 60.0f) / 66.0f);
        auto in = m.reduced (2.5f, 3.0f);
        g.setGradientFill (juce::ColourGradient (ui::colour::teal, in.getX(), in.getBottom(), ui::colour::pink, in.getX(), in.getY(), false));
        g.fillRoundedRectangle (in.withTop (in.getBottom() - in.getHeight() * frac), in.getWidth() * 0.5f);
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
    closeKeyPanel();
    auto panel = std::make_unique<KeyPanel> (proc);
    panel->setLookAndFeel (&getLookAndFeel());
    keyPanel = panel.get();
    // Inside the window (scaled with it, and it never ends up behind the host's window).
    auto* parent = getParentComponent();
    auto area = parent != nullptr ? keyButton.getBounds() + getPosition() : keyButton.getScreenBounds();
    keyBox = &juce::CallOutBox::launchAsynchronously (std::move (panel), area, parent);
}

void TopBar::closeKeyPanel()
{
    if (auto* box = keyBox.getComponent())
    {
        box->exitModalState (0);
        box->setVisible (false);
    }
    keyBox = nullptr;
    keyPanel = nullptr;
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
