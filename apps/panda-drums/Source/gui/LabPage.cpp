#include "LabPage.h"
#include "Theme.h"
#include "UiKit.h"

using namespace pd;
namespace colour = pd::theme::colour;

namespace
{
struct LabTarget { int piece, artic; juce::String label; };

std::vector<LabTarget> targets (const EngineSnapshot& s, const Kit& kit)
{
    std::vector<LabTarget> out;
    for (size_t p = 0; p < s.pieces.size(); ++p)
        if (s.pieces[p].data != nullptr)
            for (size_t a = 0; a < s.pieces[p].data->artics.size(); ++a)
                if (! s.pieces[p].data->artics[a].hits.empty())
                    out.push_back ({ (int) p, (int) a, kit.pieces[p].name.toUpperCase() + utf8 ("  \xc2\xb7  ") + s.pieces[p].data->artics[a].name });
    return out;
}

// The pack's readout in a zone's colour: teal for the soft zones, yellow in the middle, pink for the hard ones.
const char* zoneReadout (int zone, int zones)
{
    auto t = zones > 1 ? (float) zone / (float) (zones - 1) : 1.0f;
    return t < 0.34f ? "readout_zone" : (t < 0.67f ? "readout_midi" : "readout_hit");
}
} // namespace

//==============================================================================
class LabPage::DrumList : public juce::Component
{
public:
    explicit DrumList (LabPage& l) : lab (l) {}

    void setItems (std::vector<LabTarget> t) { items = std::move (t); repaint(); }

    void paint (juce::Graphics& g) override
    {
        ui::panel (g, "panel_lab_panel", getLocalBounds().toFloat());
        auto r = getLocalBounds().reduced (10, 10);
        ui::label (g, utf8 ("DRUM  \xc2\xb7  SOUND"), r.removeFromTop (22).toFloat().withTrimmedLeft (4.0f), ui::colour::textDim, 10.5f,
                   juce::Justification::centredLeft);
        rowH = std::min (32, items.empty() ? 32 : r.getHeight() / (int) items.size());
        top = r.getY();
        for (size_t i = 0; i < items.size(); ++i)
        {
            auto row = juce::Rectangle<int> (r.getX(), top + (int) i * rowH, r.getWidth(), rowH).reduced (0, 1).toFloat();
            auto sel = items[i].piece == lab.piece && items[i].artic == lab.artic;
            if (sel)
                ui::button (g, "button_primary_action", row);
            else if ((int) i == hover)
                ui::button (g, "button_secondary_action", row, 0.06f);
            ui::label (g, items[i].label, row.reduced (10.0f, 0.0f), ui::colour::text, std::min (12.0f, (float) rowH * 0.4f),
                       juce::Justification::centredLeft);
        }
    }

    int rowAt (juce::Point<int> p) const
    {
        auto i = (p.y - top) / std::max (1, rowH);
        return p.y >= top && i < (int) items.size() ? i : -1;
    }

    void mouseMove (const juce::MouseEvent& e) override { hover = rowAt (e.getPosition()); repaint(); }
    void mouseExit (const juce::MouseEvent&) override { hover = -1; repaint(); }
    void mouseDown (const juce::MouseEvent& e) override
    {
        if (auto i = rowAt (e.getPosition()); i >= 0)
            lab.select (items[(size_t) i].piece, items[(size_t) i].artic);
    }

private:
    LabPage& lab;
    std::vector<LabTarget> items;
    int rowH = 30, top = 0, hover = -1;
};

//==============================================================================
// 1..127 split into the velocity lanes of the selected sound.
class LabPage::Lanes : public juce::Component
{
public:
    explicit Lanes (LabPage& l) : lab (l) {}

    void setLayout (const ArticLayout* l) { layout = l != nullptr ? *l : ArticLayout(); repaint(); }
    void showVelocity (int in, int used) { lastIn = in; lastUsed = used; repaint(); }

    void paint (juce::Graphics& g) override
    {
        auto r = getLocalBounds().toFloat();
        ui::panel (g, "panel_lab_panel", r);
        auto bar = r.reduced (16.0f, 0.0f).withTrimmedTop (26.0f).withTrimmedBottom (20.0f);
        ui::label (g, "VELOCITY LANES", r.reduced (16.0f, 7.0f).removeFromTop (16.0f), ui::colour::textDim, 10.5f, juce::Justification::centredLeft);
        auto x = [&] (float v) { return bar.getX() + (v - 1.0f) / 126.0f * bar.getWidth(); };
        auto n = (int) layout.zones.size();
        for (int z = 0; z < n; ++z)
        {
            // Each lane on the pack's readout in its zone's colour.
            auto& zone = layout.zones[(size_t) z];
            auto seg = juce::Rectangle<float> (x ((float) zone.lo - 0.5f), bar.getY(), x ((float) zone.hi + 0.5f) - x ((float) zone.lo - 0.5f), bar.getHeight()).reduced (1.5f, 0.0f);
            auto zc = colour::zone (z, n);
            auto playing = lastIn > 0 && lastUsed >= zone.lo && lastUsed <= zone.hi;
            if (playing)
                ui::glow (g, zoneReadout (z, n), seg, zc.withAlpha (0.8f), 8.0f);
            ui::readout (g, zoneReadout (z, n), seg);
            g.setColour (zc.withAlpha (playing ? 0.32f : 0.16f));
            g.fillRoundedRectangle (seg.reduced (3.0f), seg.getHeight() * 0.4f);
            auto text = seg.withTrimmedLeft (std::min (seg.getWidth() * 0.3f, seg.getHeight() * 0.7f));
            if (seg.getWidth() > 44.0f)
            {
                ui::label (g, "ZONE " + juce::String (z + 1), text.withTrimmedBottom (text.getHeight() * 0.45f).withTrimmedTop (3.0f), ui::colour::text, 11.5f);
                ui::label (g, juce::String (zone.lo) + "-" + juce::String (zone.hi) + utf8 ("  \xc2\xb7  ") + juce::String ((int) zone.hits.size()) + " RR",
                           text.withTrimmedTop (text.getHeight() * 0.5f).withTrimmedBottom (3.0f), zc.brighter (0.3f), 9.5f);
            }
        }
        for (int v : { 1, 32, 64, 96, 127 })
            ui::label (g, juce::String (v), juce::Rectangle<float> (40.0f, 14.0f).withCentre ({ x ((float) v), bar.getBottom() + 10.0f }), ui::colour::textDim, 9.5f);
        if (lastIn > 0)
        {
            // Where the last hit landed: the pack's pointer over a line through the lanes.
            auto px = x ((float) lastUsed);
            g.setColour (ui::colour::text);
            g.fillRoundedRectangle (px - 1.0f, bar.getY(), 2.0f, bar.getHeight(), 1.0f);
            ui::icon (g, "icon_dropdown", juce::Rectangle<float> (18.0f, 18.0f).withCentre ({ px, bar.getY() - 4.0f }));
        }
    }

private:
    LabPage& lab;
    ArticLayout layout;
    int lastIn = 0, lastUsed = 0;
};

//==============================================================================
// Rows are zones (loudest at the top), columns are round robins.
class LabPage::Grid : public juce::Component, public juce::SettableTooltipClient, private juce::Timer
{
public:
    Grid (PandaDrumsProcessor& p, LabPage& l) : proc (p), lab (l) {}

    void refresh()
    {
        snap = proc.getSnapshot();
        repaint();
    }

    void flash (int hit)
    {
        flashHit = hit;
        flashAt = ui::now();
        startTimerHz (30);
    }

    void paint (juce::Graphics& g) override
    {
        ui::panel (g, "panel_lab_panel", getLocalBounds().toFloat());
        cells.clear();
        auto* a = artic();
        auto* lay = layout();
        if (a == nullptr || lay == nullptr)
        {
            ui::label (g, "Pick a drum on the left.", getLocalBounds().toFloat(), ui::colour::textDim, 13.0f);
            return;
        }
        auto r = getLocalBounds().toFloat().reduced (14.0f, 12.0f);
        auto head = r.removeFromTop (24.0f);
        ui::label (g, utf8 ("ROUND ROBINS   (click: play it  \xc2\xb7  right-click or Cmd-click: mark bad)"), head, ui::colour::textDim, 10.5f,
                   juce::Justification::centredLeft);

        auto zones = (int) lay->zones.size();
        int cols = 1;
        for (auto& z : lay->zones) cols = std::max (cols, (int) z.hits.size());
        auto rowH = std::min (64.0f, r.getHeight() / (float) std::max (1, zones));
        auto labelW = 132.0f;
        auto colW = std::min (156.0f, (r.getWidth() - labelW) / (float) cols);
        auto& disabled = snap->pieces[(size_t) lab.piece].disabled[(size_t) lab.artic];
        auto flashAmt = (float) std::max (0.0, 1.0 - (ui::now() - flashAt) / 0.6);

        for (int z = zones - 1, row = 0; z >= 0; --z, ++row)
        {
            auto& zone = lay->zones[(size_t) z];
            auto zc = colour::zone (z, zones);
            auto y = r.getY() + rowH * (float) row;

            // The zone on its readout.
            auto label = juce::Rectangle<float> (r.getX(), y, labelW - 8.0f, rowH).reduced (0.0f, 4.0f);
            ui::readout (g, zoneReadout (z, zones), label);
            g.setColour (zc.withAlpha (0.18f));
            g.fillRoundedRectangle (label.reduced (3.0f), label.getHeight() * 0.4f);
            auto lt = label.withTrimmedLeft (label.getHeight() * 0.62f).withTrimmedRight (6.0f);
            ui::label (g, "ZONE " + juce::String (z + 1), lt.withTrimmedBottom (lt.getHeight() * 0.45f).withTrimmedTop (2.0f), ui::colour::text,
                       std::min (14.0f, rowH * 0.25f));
            ui::label (g, "vel " + juce::String (zone.lo) + "-" + juce::String (zone.hi) + "  " + juce::String (zone.refDb, 1) + " dB",
                       lt.withTrimmedTop (lt.getHeight() * 0.52f).withTrimmedBottom (2.0f), zc.brighter (0.3f), std::min (10.0f, rowH * 0.18f));

            for (size_t k = 0; k < zone.hits.size(); ++k)
            {
                // Each round robin on a pack panel; it glows in the zone's colour when it plays.
                auto h = zone.hits[k];
                auto cell = juce::Rectangle<float> (r.getX() + labelW + colW * (float) k, y, colW, rowH).reduced (3.0f);
                cells.push_back ({ cell, h, zone.hi });
                auto isBad = juce::isPositiveAndBelow (h, (int) disabled.size()) && disabled[(size_t) h] != 0;
                auto hov = h == hover;
                auto& hit = a->hits[(size_t) h];
                auto flashing = h == flashHit && flashAmt > 0.0f;
                if (flashing)
                    ui::glow (g, "panel_popup_panel", cell, zc.withAlpha (flashAmt), 9.0f);
                ui::panel (g, "panel_popup_panel", cell, isBad ? 0.6f : 1.0f);
                if (hov || flashing)
                {
                    g.setColour ((flashing ? zc : juce::Colours::white).withAlpha (flashing ? flashAmt * 0.3f : 0.05f));
                    g.fillRoundedRectangle (cell.reduced (3.0f), 9.0f);
                }

                auto in = cell.reduced (12.0f, 6.0f);
                auto top = in.withHeight (in.getHeight() * 0.5f);
                if (isBad)
                    ui::icon (g, "icon_heart_red", top.removeFromRight (top.getHeight() + 10.0f).withTrimmedRight (10.0f));
                ui::label (g, "RR " + juce::String ((int) k + 1), top, isBad ? ui::colour::textDim : ui::colour::text, std::min (13.0f, rowH * 0.24f),
                           juce::Justification::centredLeft);
                auto matchDb = juce::Decibels::gainToDecibels (lay->hitGain[(size_t) h]);
                ui::label (g, isBad ? juce::String ("BAD - skipped") : juce::String (hit.rmsDb, 1) + " dB" + (std::abs (matchDb) > 0.05f ? " (" + juce::String (matchDb, 1) + ")" : juce::String()),
                           in.withTrimmedTop (in.getHeight() * 0.5f).withTrimmedRight (10.0f), isBad ? colour::bad : ui::colour::textDim,
                           std::min (10.0f, rowH * 0.18f), juce::Justification::centredLeft);

                // How far this one sits from the zone's level: the odd one out sticks out.
                auto dev = juce::jlimit (-6.0f, 6.0f, hit.rmsDb - zone.refDb);
                auto bar = juce::Rectangle<float> (in.getRight() - 5.0f, in.getY(), 5.0f, in.getHeight());
                g.setColour (ui::colour::panel);
                g.fillRoundedRectangle (bar, 2.0f);
                auto mid = bar.getCentreY();
                auto len = dev / 6.0f * bar.getHeight() * 0.5f;
                g.setColour (std::abs (dev) > 3.0f ? ui::colour::pink : ui::colour::teal);
                g.fillRect (bar.getX(), std::min (mid, mid - len), bar.getWidth(), std::max (1.5f, std::abs (len)));
            }
        }
    }

    void mouseMove (const juce::MouseEvent& e) override
    {
        auto old = hover;
        hover = -1;
        for (auto& c : cells)
            if (c.r.contains (e.position))
                hover = c.hit;
        auto* a = artic();
        setTooltip (hover >= 0 && a != nullptr ? a->hits[(size_t) hover].name : juce::String());
        setMouseCursor (hover >= 0 ? juce::MouseCursor::PointingHandCursor : juce::MouseCursor::NormalCursor);
        if (old != hover)
            repaint();
    }

    void mouseExit (const juce::MouseEvent&) override { hover = -1; repaint(); }

    void mouseDown (const juce::MouseEvent& e) override
    {
        for (auto& c : cells)
            if (c.r.contains (e.position))
            {
                if (e.mods.isPopupMenu() || e.mods.isCommandDown())
                    proc.setBad (lab.piece, lab.artic, c.hit, ! proc.isBad (lab.piece, lab.artic, c.hit));
                else
                    proc.play (lab.piece, lab.artic, c.vel, c.hit);
                return;
            }
    }

private:
    const Articulation* artic() const
    {
        if (snap == nullptr || ! juce::isPositiveAndBelow (lab.piece, (int) snap->pieces.size()))
            return nullptr;
        auto& rt = snap->pieces[(size_t) lab.piece];
        if (rt.data == nullptr || ! juce::isPositiveAndBelow (lab.artic, (int) rt.data->artics.size()))
            return nullptr;
        return &rt.data->artics[(size_t) lab.artic];
    }

    const ArticLayout* layout() const
    {
        if (artic() == nullptr)
            return nullptr;
        return &snap->pieces[(size_t) lab.piece].layouts[(size_t) lab.artic];
    }

    void timerCallback() override
    {
        repaint();
        if (ui::now() - flashAt > 0.7)
            stopTimer();
    }

    struct Cell { juce::Rectangle<float> r; int hit; int vel; };
    PandaDrumsProcessor& proc;
    LabPage& lab;
    std::shared_ptr<const EngineSnapshot> snap;
    std::vector<Cell> cells;
    int hover = -1, flashHit = -1;
    double flashAt = 0.0;
};

//==============================================================================
LabPage::LabPage (PandaDrumsProcessor& p) : proc (p)
{
    list = std::make_unique<DrumList> (*this);
    lanes = std::make_unique<Lanes> (*this);
    grid = std::make_unique<Grid> (p, *this);
    addAndMakeVisible (*list);
    addAndMakeVisible (*lanes);
    addAndMakeVisible (*grid);

    auto label = [this] (juce::Label& l, const juce::String& text, juce::Component& target)
    {
        l.setText (text, juce::dontSendNotification);
        l.setFont (ui::font (10.5f));
        l.setColour (juce::Label::textColourId, ui::colour::textDim);
        l.attachToComponent (&target, false);
        addAndMakeVisible (target);
    };

    source.addItem ("File names", 1);
    source.addItem ("Loudness", 2);
    source.setTooltip ("Which zone a sample lives in: the layer number in its file name, or how loud it really is");
    zones.addItem ("Auto", 1);
    for (int i = 1; i <= 16; ++i)
        zones.addItem (juce::String (i), i + 1);
    zones.setTooltip ("How many zones to sort the hits into (when zoning by loudness)");
    ranges.addItem ("Even", 1);
    ranges.addItem ("By loudness", 2);
    ranges.setTooltip ("Even: 1-127 split into equal lanes. By loudness: louder zones get placed by how loud they are");
    for (auto* c : { &source, &zones, &ranges })
        c->onChange = [this] { pushZoneSettings(); };
    label (sourceL, "ZONES FROM", source);
    label (zonesL, "HOW MANY", zones);
    label (rangesL, "LANES", ranges);

    rrMode.addItemList (proc.params.getParameter ("rrMode")->getAllValueStrings(), 1);
    rrA = std::make_unique<juce::AudioProcessorValueTreeState::ComboBoxAttachment> (proc.params, "rrMode", rrMode);
    label (rrL, "ROUND ROBIN", rrMode);

    for (auto* s : { &levelMatch, &build, &curve, &humanize })
    {
        s->setSliderStyle (juce::Slider::LinearHorizontal);
        s->setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
        s->setPopupDisplayEnabled (true, true, this);
    }
    theme::accent (levelMatch, "teal");
    theme::accent (build, "pink");
    theme::accent (curve, "yellow");
    theme::accent (humanize, "purple");
    levelMatch.setRange (0.0, 100.0, 1.0);
    levelMatch.setTextValueSuffix (" %");
    levelMatch.setTooltip ("Stabilize: pulls every round robin of a zone to the same level, so none jumps out");
    levelMatch.onValueChange = [this] { pushZoneSettings(); };
    build.setTooltip ("Velocity build: how much softer the bottom of each lane plays, so velocity is one smooth build");
    curve.setTooltip ("Velocity curve: left = you have to dig in, right = soft playing comes out louder");
    humanize.setTooltip ("Random velocity variation on every hit");
    buildA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "dynamics", build);
    curveA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "velCurve", curve);
    humanizeA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "humanize", humanize);
    label (levelL, "STABILIZE", levelMatch);
    label (buildL, "VELOCITY BUILD", build);
    label (curveL, "CURVE", curve);
    label (humanizeL, "HUMANIZE", humanize);

    report.onClick = [this] { exportText ("Save the sample report", "Panda Drums sample report.txt", proc.buildReport()); };
    badList.onClick = [this] { exportText ("Save the list of bad samples", "Panda Drums bad samples.txt", proc.buildBadList()); };
    clear.onClick = [this] { proc.clearBad(); };
    report.setTooltip ("Every hit with its zone, round robin, level and whether it's marked bad - for checking or sending on");
    badList.setTooltip ("Just the samples you marked bad");
    for (auto* b : { &report, &badList, &clear })
        addAndMakeVisible (*b);
    refresh();
}

LabPage::~LabPage() = default;

void LabPage::resized()
{
    auto r = getLocalBounds().reduced (14);
    r.removeFromTop (40);
    auto bottom = r.removeFromBottom (36);
    report.setBounds (bottom.removeFromLeft (150).reduced (0, 3));
    bottom.removeFromLeft (8);
    badList.setBounds (bottom.removeFromLeft (150).reduced (0, 3));
    bottom.removeFromLeft (8);
    clear.setBounds (bottom.removeFromLeft (120).reduced (0, 3));
    r.removeFromBottom (8);

    list->setBounds (r.removeFromLeft (250));
    r.removeFromLeft (12);
    auto controls = r.removeFromTop (60).withTrimmedTop (20);
    auto w = controls.getWidth() / 8;
    for (auto* c : std::initializer_list<juce::Component*> { &source, &zones, &ranges, &rrMode, &levelMatch, &build, &curve, &humanize })
        c->setBounds (controls.removeFromLeft (w).reduced (5, 1));
    r.removeFromTop (8);
    lanes->setBounds (r.removeFromTop (86));
    r.removeFromTop (8);
    grid->setBounds (r);
}

void LabPage::paint (juce::Graphics& g)
{
    g.fillAll (colour::plum);
    auto r = getLocalBounds().reduced (16, 10).removeFromTop (36).toFloat();
    ui::label (g, "VELOCITY & ROUND ROBIN LAB", r.removeFromLeft (330.0f), ui::colour::pink, 18.0f, juce::Justification::centredLeft);
    auto bad = proc.countBad();
    ui::label (g, bad == 0 ? juce::String ("Every recorded hit in its lane. Play them, compare them, take out the weird ones.")
                           : juce::String (bad) + (bad == 1 ? " sample marked bad and skipped." : " samples marked bad and skipped."),
               r, bad == 0 ? ui::colour::textDim : colour::bad, 11.5f, juce::Justification::centredLeft);
}

void LabPage::refresh()
{
    auto z = proc.getZoneSettings();
    source.setSelectedId (z.source == ZoneSettings::Source::FileNames ? 1 : 2, juce::dontSendNotification);
    zones.setSelectedId (z.zoneCount <= 0 ? 1 : z.zoneCount + 1, juce::dontSendNotification);
    zones.setEnabled (z.source == ZoneSettings::Source::Loudness);
    ranges.setSelectedId (z.ranges == ZoneSettings::Ranges::Even ? 1 : 2, juce::dontSendNotification);
    levelMatch.setValue (z.levelMatch * 100.0, juce::dontSendNotification);

    auto snap = proc.getSnapshot();
    auto kit = proc.getKit();
    if (snap != nullptr && kit != nullptr)
    {
        auto t = targets (*snap, *kit);
        auto found = std::any_of (t.begin(), t.end(), [this] (auto& x) { return x.piece == piece && x.artic == artic; });
        if (! found && ! t.empty())
        {
            piece = t.front().piece;
            artic = t.front().artic;
        }
        list->setItems (t);
        const ArticLayout* lay = nullptr;
        if (juce::isPositiveAndBelow (piece, (int) snap->pieces.size()) && juce::isPositiveAndBelow (artic, (int) snap->pieces[(size_t) piece].layouts.size()))
            lay = &snap->pieces[(size_t) piece].layouts[(size_t) artic];
        lanes->setLayout (lay);
    }
    grid->refresh();
    repaint();
}

void LabPage::onHit (const HitEvent& e)
{
    if (e.piece != piece || e.artic != artic || e.zone < 0)
        return;
    lanes->showVelocity (e.velocityIn, e.velocityUsed);
    grid->flash (e.hit);
}

void LabPage::select (int p, int a)
{
    piece = p;
    artic = a;
    refresh();
}

void LabPage::pushZoneSettings()
{
    ZoneSettings z;
    z.source = source.getSelectedId() == 2 ? ZoneSettings::Source::Loudness : ZoneSettings::Source::FileNames;
    z.zoneCount = std::max (0, zones.getSelectedId() - 1);
    z.ranges = ranges.getSelectedId() == 2 ? ZoneSettings::Ranges::Loudness : ZoneSettings::Ranges::Even;
    z.levelMatch = (float) levelMatch.getValue() / 100.0f;
    proc.setZoneSettings (z);
}

void LabPage::exportText (const juce::String& title, const juce::String& fileName, const juce::String& text)
{
    chooser = std::make_unique<juce::FileChooser> (title, juce::File::getSpecialLocation (juce::File::userDesktopDirectory).getChildFile (fileName), "*.txt");
    chooser->launchAsync (juce::FileBrowserComponent::saveMode | juce::FileBrowserComponent::canSelectFiles | juce::FileBrowserComponent::warnAboutOverwriting,
                          [text] (const juce::FileChooser& fc)
                          {
                              auto f = fc.getResult();
                              if (f != juce::File())
                                  f.replaceWithText (text);
                          });
}
