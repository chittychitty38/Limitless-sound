#include "MappingPage.h"
#include "Theme.h"

using namespace pd;
namespace colour = pd::theme::colour;

namespace
{
juce::Colour pieceColour (int piece)
{
    static const juce::Colour cols[] = { colour::hot, colour::gold, colour::mint, juce::Colour (0xffa98bff), juce::Colour (0xffff8a5b),
                                         juce::Colour (0xff6fc3ff), colour::blush, juce::Colour (0xffc6f06b) };
    return cols[(size_t) (std::max (0, piece) % 8)];
}

juce::String noteLabel (int n) { return midiNoteName (n) + " (" + juce::String (n) + ")"; }
} // namespace

//==============================================================================
class MappingPage::Rows : public juce::Component
{
public:
    Rows (PandaDrumsProcessor& p, MappingPage& m) : proc (p), page (m) {}

    void refresh()
    {
        targets.clear();
        auto kit = proc.getKit();
        auto snap = proc.getSnapshot();
        if (kit == nullptr || snap == nullptr)
            return;
        std::vector<std::shared_ptr<const VariantData>> data;
        for (auto& rt : snap->pieces)
            data.push_back (rt.data);
        targets = playableTargets (*kit, data);
        resolved = snap->notes;
        for (auto* b : learnButtons) removeChildComponent (b);
        for (auto* b : clearButtons) removeChildComponent (b);
        learnButtons.clear();
        clearButtons.clear();
        for (size_t i = 0; i < targets.size(); ++i)
        {
            auto* l = learnButtons.add (new juce::TextButton ("Learn"));
            l->setClickingTogglesState (false);
            l->setTooltip ("Then hit a pad or key: that note plays this drum");
            l->onClick = [this, i] { page.learn ((int) i); };
            auto* c = clearButtons.add (new juce::TextButton ("Clear"));
            c->onClick = [this, i] { page.clearRow ((int) i); };
            addAndMakeVisible (l);
            addAndMakeVisible (c);
        }
        setSize (getWidth(), (int) targets.size() * rowH + 4);
        resized();
        repaint();
    }

    void setLearning (int row)
    {
        for (int i = 0; i < learnButtons.size(); ++i)
        {
            learnButtons[i]->setToggleState (i == row, juce::dontSendNotification);
            learnButtons[i]->setButtonText (i == row ? "Play a note..." : "Learn");
        }
    }

    void resized() override
    {
        for (int i = 0; i < learnButtons.size(); ++i)
        {
            auto row = juce::Rectangle<int> (0, i * rowH, getWidth(), rowH).reduced (6, 4);
            clearButtons[i]->setBounds (row.removeFromRight (70));
            row.removeFromRight (6);
            learnButtons[i]->setBounds (row.removeFromRight (120));
        }
    }

    void paint (juce::Graphics& g) override
    {
        for (size_t i = 0; i < targets.size(); ++i)
        {
            auto row = juce::Rectangle<int> (0, (int) i * rowH, getWidth(), rowH).reduced (2, 2).toFloat();
            g.setColour (i % 2 == 0 ? colour::plumLight.darker (0.25f) : colour::plumLight.darker (0.4f));
            g.fillRoundedRectangle (row, 8.0f);
            auto& t = targets[i];
            g.setColour (pieceColour (t.piece));
            g.fillRoundedRectangle (row.withWidth (6.0f).reduced (0.0f, 4.0f).translated (6.0f, 0.0f), 3.0f);
            g.setColour (colour::text);
            g.setFont (theme::title (15.0f));
            g.drawText (t.label, row.withTrimmedLeft (20.0f).withWidth (230.0f), juce::Justification::centredLeft, true);

            auto x = row.getX() + 260.0f;
            for (int n = 0; n < 128; ++n)
                if (resolved[(size_t) n].piece == t.piece && resolved[(size_t) n].artic == t.artic)
                {
                    auto text = noteLabel (n);
                    auto w = juce::GlyphArrangement::getStringWidth (theme::body (13.0f), text) + 18.0f;
                    auto chip = juce::Rectangle<float> (x, row.getCentreY() - 11.0f, w, 22.0f);
                    if (chip.getRight() > row.getRight() - 210.0f)
                        break;
                    theme::drawPill (g, chip, pieceColour (t.piece).withAlpha (0.22f), pieceColour (t.piece));
                    g.setColour (colour::text);
                    g.setFont (theme::body (13.0f));
                    g.drawText (text, chip, juce::Justification::centred);
                    x += w + 6.0f;
                }
        }
    }

    std::vector<ArticRef> targets;
    std::array<ResolvedNote, 128> resolved {};
    static constexpr int rowH = 38;

private:
    PandaDrumsProcessor& proc;
    MappingPage& page;
    juce::OwnedArray<juce::TextButton> learnButtons, clearButtons;
};

//==============================================================================
// A keyboard with every mapped note coloured by drum and the chromatic zone shaded.
class MappingPage::Keys : public juce::Component, public juce::SettableTooltipClient
{
public:
    explicit Keys (PandaDrumsProcessor& p) : proc (p) {}

    void paint (juce::Graphics& g) override
    {
        theme::drawCard (g, getLocalBounds().toFloat(), colour::plumLight.darker (0.3f), 12.0f, false);
        auto snap = proc.getSnapshot();
        auto kit = proc.getKit();
        if (snap == nullptr || kit == nullptr)
            return;
        auto area = getLocalBounds().toFloat().reduced (10.0f, 8.0f);
        keyArea = area;
        int whites = 0;
        for (int n = lowNote; n <= highNote; ++n) whites += isBlack (n) ? 0 : 1;
        auto ww = area.getWidth() / (float) whites;

        auto drawKey = [&] (int n, juce::Rectangle<float> r, bool black)
        {
            auto t = snap->notes[(size_t) n];
            auto chrom = snap->chromaticOn && n >= snap->chromaticLow && n <= snap->chromaticHigh;
            auto base = black ? colour::ink : colour::cream;
            if (chrom) base = black ? colour::mint.darker (0.6f) : colour::mint.brighter (0.4f);
            if (t.piece >= 0 && ! chrom) base = pieceColour (t.piece).withMultipliedBrightness (black ? 0.8f : 1.0f);
            if (n == pressed) base = base.brighter (0.5f);
            g.setColour (base);
            g.fillRoundedRectangle (r, 3.0f);
            g.setColour (colour::ink);
            g.drawRoundedRectangle (r, 3.0f, 1.0f);
            if (n % 12 == 0 && ! black)
            {
                g.setColour (colour::ink.withAlpha (0.6f));
                g.setFont (theme::body (10.0f));
                g.drawText (midiNoteName (n), r.removeFromBottom (14.0f), juce::Justification::centred);
            }
        };

        int w = 0;
        keyRects.clear();
        for (int n = lowNote; n <= highNote; ++n)
            if (! isBlack (n))
            {
                auto r = juce::Rectangle<float> (area.getX() + ww * (float) w++, area.getY(), ww, area.getHeight()).reduced (0.5f, 0.0f);
                drawKey (n, r, false);
                keyRects.push_back ({ n, r });
            }
        w = 0;
        for (int n = lowNote; n <= highNote; ++n)
        {
            if (! isBlack (n)) { ++w; continue; }
            auto r = juce::Rectangle<float> (area.getX() + ww * (float) w - ww * 0.32f, area.getY(), ww * 0.64f, area.getHeight() * 0.6f);
            drawKey (n, r, true);
            keyRects.insert (keyRects.begin(), { n, r });
        }
    }

    int noteAt (juce::Point<float> p) const
    {
        for (auto& k : keyRects)
            if (k.second.contains (p))
                return k.first;
        return -1;
    }

    void mouseMove (const juce::MouseEvent& e) override
    {
        auto n = noteAt (e.position);
        auto snap = proc.getSnapshot();
        auto kit = proc.getKit();
        juce::String tip;
        if (n >= 0 && snap != nullptr && kit != nullptr)
        {
            tip = noteLabel (n);
            if (snap->chromaticOn && n >= snap->chromaticLow && n <= snap->chromaticHigh && snap->chromaticPiece >= 0)
                tip << ": " << kit->pieces[(size_t) snap->chromaticPiece].name << ", chromatic";
            else if (auto t = snap->notes[(size_t) n]; t.piece >= 0)
                tip << ": " << kit->pieces[(size_t) t.piece].name;
        }
        setTooltip (tip);
    }

    void mouseDown (const juce::MouseEvent& e) override
    {
        pressed = noteAt (e.position);
        if (pressed >= 0)
            proc.playNote (pressed, 105);
        repaint();
    }

    void mouseUp (const juce::MouseEvent&) override { pressed = -1; repaint(); }

private:
    static bool isBlack (int n) { auto pc = n % 12; return pc == 1 || pc == 3 || pc == 6 || pc == 8 || pc == 10; }
    PandaDrumsProcessor& proc;
    const int lowNote = 21, highNote = 108;
    juce::Rectangle<float> keyArea;
    std::vector<std::pair<int, juce::Rectangle<float>>> keyRects;
    int pressed = -1;
};

//==============================================================================
MappingPage::MappingPage (PandaDrumsProcessor& p) : proc (p)
{
    rows = std::make_unique<Rows> (p, *this);
    keys = std::make_unique<Keys> (p);
    viewport.setViewedComponent (rows.get(), false);
    viewport.setScrollBarsShown (true, false);
    addAndMakeVisible (viewport);
    addAndMakeVisible (*keys);

    for (size_t i = 0; i < presetMaps().size(); ++i)
        preset.addItem (presetMaps()[i].name, (int) i + 1);
    preset.setTextWhenNothingSelected ("Custom map");
    preset.onChange = [this]
    {
        auto i = preset.getSelectedId() - 1;
        if (juce::isPositiveAndBelow (i, (int) presetMaps().size()))
            proc.setMap (presetMaps()[(size_t) i]);
    };
    save.onClick = [this]
    {
        chooser = std::make_unique<juce::FileChooser> ("Save this map", juce::File::getSpecialLocation (juce::File::userDocumentsDirectory).getChildFile ("My Panda map.json"), "*.json");
        chooser->launchAsync (juce::FileBrowserComponent::saveMode | juce::FileBrowserComponent::canSelectFiles | juce::FileBrowserComponent::warnAboutOverwriting,
                              [this] (const juce::FileChooser& fc)
                              {
                                  auto f = fc.getResult();
                                  if (f == juce::File()) return;
                                  auto m = proc.getMap();
                                  m.name = f.getFileNameWithoutExtension();
                                  f.replaceWithText (juce::JSON::toString (m.toVar()));
                              });
    };
    load.onClick = [this]
    {
        chooser = std::make_unique<juce::FileChooser> ("Load a map", juce::File::getSpecialLocation (juce::File::userDocumentsDirectory), "*.json");
        chooser->launchAsync (juce::FileBrowserComponent::openMode | juce::FileBrowserComponent::canSelectFiles, [this] (const juce::FileChooser& fc)
        {
            auto f = fc.getResult();
            if (! f.existsAsFile()) return;
            auto v = juce::JSON::parse (f.loadFileAsString());
            if (v.isObject())
                proc.setMap (MidiMap::fromVar (v));
        });
    };
    reset.onClick = [this] { proc.setMap (presetMaps().front()); };
    save.setTooltip ("Save this map to a file, to use in other songs or share");
    load.setTooltip ("Import a map (.json) - your own or one made for another drum plugin");
    for (auto* c : std::initializer_list<juce::Component*> { &preset, &save, &load, &reset })
        addAndMakeVisible (*c);

    // Chromatic keys.
    for (int n = 0; n < 128; ++n)
    {
        low.addItem (noteLabel (n), n + 1);
        high.addItem (noteLabel (n), n + 1);
    }
    auto label = [this] (juce::Label& l, const juce::String& text, juce::Component& target)
    {
        l.setText (text, juce::dontSendNotification);
        l.setFont (theme::title (12.0f));
        l.setColour (juce::Label::textColourId, colour::textDim);
        l.attachToComponent (&target, false);
        addAndMakeVisible (target);
    };
    label (pieceL, "DRUM", chromaticPiece);
    label (lowL, "FROM", low);
    label (highL, "TO", high);
    addAndMakeVisible (chromaticOn);
    addAndMakeVisible (snap);
    for (auto* c : { &chromaticPiece, &low, &high })
        c->onChange = [this] { pushChromatic(); };
    chromaticOn.onClick = [this] { pushChromatic(); };
    snap.onClick = [this] { pushChromatic(); };
    refresh();
}

MappingPage::~MappingPage()
{
    proc.learnArmed.store (false);
}

void MappingPage::refresh()
{
    rows->refresh();
    rows->setLearning (learning);
    auto m = proc.getMap();
    int id = 0;
    for (size_t i = 0; i < presetMaps().size(); ++i)
        if (presetMaps()[i].name == m.name && presetMaps()[i].entries.size() == m.entries.size())
            id = (int) i + 1;
    preset.setSelectedId (id, juce::dontSendNotification);

    auto c = proc.getChromatic();
    auto kit = proc.getKit();
    chromaticPiece.clear (juce::dontSendNotification);
    if (kit != nullptr)
        for (size_t p = 0; p < kit->pieces.size(); ++p)
            if (isTunable (kit->pieces[p].type))
                chromaticPiece.addItem (kit->pieces[p].name, (int) p + 1);
    if (kit != nullptr)
        chromaticPiece.setSelectedId (kit->findPiece (c.pieceId) + 1, juce::dontSendNotification);
    low.setSelectedId (c.low + 1, juce::dontSendNotification);
    high.setSelectedId (c.high + 1, juce::dontSendNotification);
    chromaticOn.setToggleState (c.on, juce::dontSendNotification);
    snap.setToggleState (c.snap, juce::dontSendNotification);
    keys->repaint();
    repaint();
}

void MappingPage::pushChromatic()
{
    auto kit = proc.getKit();
    PandaDrumsProcessor::Chromatic c;
    c.on = chromaticOn.getToggleState();
    c.snap = snap.getToggleState();
    auto p = chromaticPiece.getSelectedId() - 1;
    c.pieceId = kit != nullptr && juce::isPositiveAndBelow (p, (int) kit->pieces.size()) ? kit->pieces[(size_t) p].id : proc.getChromatic().pieceId;
    c.low = low.getSelectedId() - 1;
    c.high = std::max (c.low, high.getSelectedId() - 1);
    proc.setChromatic (c);
}

void MappingPage::learn (int row)
{
    learning = learning == row ? -1 : row;
    proc.learnedNote.store (-1);
    proc.learnArmed.store (learning >= 0);
    rows->setLearning (learning);
    if (learning >= 0) startTimerHz (20);
    else               stopTimer();
}

void MappingPage::clearRow (int row)
{
    if (! juce::isPositiveAndBelow (row, (int) rows->targets.size()))
        return;
    auto& t = rows->targets[(size_t) row];
    auto m = proc.getMap();
    auto resolved = proc.getResolvedNotes();
    for (int n = 0; n < 128; ++n)
        if (resolved[(size_t) n].piece == t.piece && resolved[(size_t) n].artic == t.artic)
            m.set (n, {});
    m.name = "Custom";
    proc.setMap (m);
}

void MappingPage::timerCallback()
{
    auto note = proc.learnedNote.exchange (-1);
    if (note < 0 || ! juce::isPositiveAndBelow (learning, (int) rows->targets.size()))
        return;
    auto m = proc.getMap();
    m.set (note, rows->targets[(size_t) learning].target);
    m.name = "Custom";
    learning = -1;
    stopTimer();
    proc.setMap (m);
}

void MappingPage::resized()
{
    auto r = getLocalBounds().reduced (14);
    r.removeFromTop (40);
    keys->setBounds (r.removeFromBottom (92));
    r.removeFromBottom (10);
    auto side = r.removeFromRight (320);
    r.removeFromRight (12);
    auto bar = r.removeFromTop (34);
    preset.setBounds (bar.removeFromLeft (290).reduced (0, 2));
    bar.removeFromLeft (8);
    save.setBounds (bar.removeFromLeft (120).reduced (0, 2));
    bar.removeFromLeft (6);
    load.setBounds (bar.removeFromLeft (120).reduced (0, 2));
    bar.removeFromLeft (6);
    reset.setBounds (bar.removeFromLeft (90).reduced (0, 2));
    r.removeFromTop (8);
    viewport.setBounds (r);
    rows->setSize (r.getWidth() - 10, rows->getHeight());

    auto s = side.reduced (16, 12);
    s.removeFromTop (34);
    chromaticOn.setBounds (s.removeFromTop (28));
    s.removeFromTop (24);
    chromaticPiece.setBounds (s.removeFromTop (30));
    s.removeFromTop (24);
    auto lh = s.removeFromTop (30);
    low.setBounds (lh.removeFromLeft (lh.getWidth() / 2 - 4));
    lh.removeFromLeft (8);
    high.setBounds (lh);
    s.removeFromTop (10);
    snap.setBounds (s.removeFromTop (28));
    chromaticArea = side;
}

void MappingPage::paint (juce::Graphics& g)
{
    g.fillAll (colour::plum);
    auto r = getLocalBounds().reduced (16, 10).removeFromTop (36);
    g.setColour (colour::text);
    g.setFont (theme::display (26.0f));
    g.drawText ("MAPPING", r, juce::Justification::centredLeft);
    g.setColour (colour::textDim);
    g.setFont (theme::body (13.0f));
    g.drawText ("Pick a map, learn notes from your pads, or save and load your own. Notes are C3 = 60.", r.withTrimmedLeft (140), juce::Justification::centredLeft);

    theme::drawCard (g, chromaticArea.toFloat(), colour::plumLight.darker (0.3f), 12.0f, false);
    auto c = chromaticArea.toFloat().reduced (16.0f, 10.0f);
    g.setColour (colour::mint);
    g.setFont (theme::display (22.0f));
    g.drawText ("CHROMATIC DRUM", c.removeFromTop (28.0f), juce::Justification::centredLeft);
    auto text = c.withTrimmedTop (snap.getBottom() - chromaticArea.getY() - 2.0f);
    g.setColour (colour::textDim);
    g.setFont (theme::body (12.5f));
    g.drawFittedText ("Play a tunable drum on the keys like an instrument: every key is a note. With snap on, out-of-key notes "
                      "land on the nearest note of the song's key, so a tom melody or an 808-style kick line is always in key.",
                      text.reduced (0.0f, 4.0f).toNearestInt(), juce::Justification::topLeft, 8);
}
