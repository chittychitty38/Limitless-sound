#include "KitPage.h"
#include "Theme.h"
#include "UiKit.h"

using namespace pd;
namespace colour = pd::theme::colour;

namespace
{
juce::String articName (const EngineSnapshot& s, int piece, int artic)
{
    if (! juce::isPositiveAndBelow (piece, (int) s.pieces.size()) || s.pieces[(size_t) piece].data == nullptr)
        return {};
    auto& a = s.pieces[(size_t) piece].data->artics;
    return juce::isPositiveAndBelow (artic, (int) a.size()) ? a[(size_t) artic].name : juce::String();
}

// A label and its value on one of the pack's readouts, after its dot.
void drawReadout (juce::Graphics& g, const juce::String& piece, juce::Rectangle<float> r, const juce::String& name,
                  const juce::String& value, juce::Colour valueColour, float pop = 0.0f)
{
    auto box = r.withSizeKeepingCentre (r.getWidth() * (1.0f + 0.06f * pop), r.getHeight() * (1.0f + 0.12f * pop));
    ui::readout (g, piece, box);
    auto& kit = ui::Kit::get();
    auto k = box.getHeight() / std::max (1.0f, kit.size (piece).y);
    auto in = box.withTrimmedLeft ((kit.box (piece, "dot").getRight() + 5.0f) * k).withTrimmedRight (box.getHeight() * 0.42f);
    auto labelW = juce::GlyphArrangement::getStringWidth (ui::font (9.5f), name) + 5.0f;
    ui::label (g, name, in.removeFromLeft (labelW), ui::colour::textDim, 9.5f, juce::Justification::centredLeft);
    ui::label (g, value, in, valueColour, 13.0f, juce::Justification::centredRight);
}
} // namespace

//==============================================================================
// Every drum on its tile from the pack: its name, arrows to swap it, arrows to tune it. A tile
// lights up when its drum is hit.
class KitPage::DrumStrip : public juce::Component, public juce::SettableTooltipClient
{
public:
    DrumStrip (PandaDrumsProcessor& p, KitPage& k) : proc (p), page (k) {}

    void refresh()
    {
        auto kit = proc.getKit();
        std::vector<double> flashes;
        for (auto& c : cells)
            flashes.push_back (c.flashAt);
        cells.clear();
        if (kit == nullptr)
            return;
        auto key = proc.getKey();
        for (size_t i = 0; i < kit->pieces.size(); ++i)
        {
            auto& piece = kit->pieces[i];
            Cell c;
            c.piece = (int) i;
            c.name = piece.name.toUpperCase();
            c.tile = ui::tileFor (piece.name);
            auto v = proc.getSelectedVariant ((int) i);
            c.variant = piece.variants[(size_t) juce::jlimit (0, (int) piece.variants.size() - 1, v)].name;
            c.variants = (int) piece.variants.size();
            c.tunable = isTunable (piece.type);
            c.keyOn = ! key.isOff();
            c.inKey = proc.pitchInKey ((int) i);
            c.pitch = c.tunable ? pitchName (proc.getPitch ((int) i)) : juce::String();
            if (auto d = kit->getLoaded ((int) i, v))
                c.sounds = (int) d->artics.size();
            else
                c.loading = true;
            c.flashAt = i < flashes.size() ? flashes[i] : 0.0;
            cells.push_back (c);
        }
        layoutCells();
        repaint();
    }

    void flash (int piece, float velocity)
    {
        if (! juce::isPositiveAndBelow (piece, (int) cells.size()))
            return;
        cells[(size_t) piece].flashAt = ui::now();
        cells[(size_t) piece].flashVel = velocity;
        ui::animate (*this, 0.5);
    }

    void resized() override { layoutCells(); }

    void paint (juce::Graphics& g) override
    {
        g.fillAll (colour::plum);
        ui::panel (g, "panel_bottom_instrument_strip", getLocalBounds().toFloat().reduced (4.0f, 3.0f));
        auto t = ui::now();
        for (auto& c : cells)
        {
            auto sel = c.piece == selected, hov = c.piece == hoverCell;
            auto f = (float) juce::jlimit (0.0, 1.0, 1.0 - (t - c.flashAt) / 0.4);
            f *= f * (0.45f + 0.55f * c.flashVel);
            auto r = c.r.translated (0.0f, -3.0f * f);
            if (sel || f > 0.0f)
                ui::glow (g, c.tile, r, colour::hot.withAlpha (juce::jlimit (0.0f, 1.0f, (sel ? 0.55f : 0.0f) + 0.9f * f)), 9.0f);
            ui::tile (g, c.tile, r, (sel ? 0.07f : 0.0f) + (hov ? 0.05f : 0.0f) + 0.2f * f);
            auto k = r.getHeight() / ui::Kit::get().size (c.tile).y;
            if (c.tile == "tile_blank")
                ui::label (g, c.name, { r.getX() + 10.0f * k, r.getY() + 7.0f * k, r.getWidth() - 20.0f * k, 16.0f * k },
                           ui::colour::text, 11.0f * k, juce::Justification::centredLeft);

            // The drum: between the tile's arrows.
            auto vr = c.variantRow.translated (0.0f, -3.0f * f);
            ui::label (g, c.loading ? juce::String ("loading...") : c.variant, vr, ui::colour::text.withAlpha (0.92f), 10.5f * k);
            if (hov && hoverButton == 1) hotSpot (g, c.prev.translated (0.0f, -3.0f * f));
            if (hov && hoverButton == 2) hotSpot (g, c.next.translated (0.0f, -3.0f * f));

            // Its note: a readout in teal when it's in the song's key.
            auto pr = c.pitchRow.translated (0.0f, -3.0f * f);
            if (c.tunable)
            {
                auto ok = c.keyOn && c.inKey;
                auto pill = pr.reduced (17.0f * k, 0.0f);
                ui::readout (g, ok ? "readout_zone" : (c.keyOn ? "readout_midi" : "readout_velocity"), pill);
                auto tr = pill.withTrimmedLeft (pill.getHeight() * 0.9f);
                if (ok)
                    ui::icon (g, "icon_heart_teal", tr.removeFromRight (pill.getHeight()).reduced (pill.getHeight() * 0.22f));
                ui::label (g, c.pitch, tr, ok ? ui::colour::text : (c.keyOn ? ui::colour::yellow : ui::colour::text), 11.5f * k);
                ui::icon (g, "icon_chevron_left", c.down.translated (0.0f, -3.0f * f).reduced (c.down.getWidth() * 0.18f), -juce::MathConstants<float>::halfPi,
                          hov && hoverButton == 3 ? 1.0f : 0.8f);
                ui::icon (g, "icon_chevron_left", c.up.translated (0.0f, -3.0f * f).reduced (c.up.getWidth() * 0.18f), juce::MathConstants<float>::halfPi,
                          hov && hoverButton == 4 ? 1.0f : 0.8f);
                if (hov && hoverButton == 3) hotSpot (g, c.down.translated (0.0f, -3.0f * f));
                if (hov && hoverButton == 4) hotSpot (g, c.up.translated (0.0f, -3.0f * f));
            }
            else
            {
                ui::label (g, juce::String (c.sounds) + (c.sounds == 1 ? " sound" : " sounds"), pr, ui::colour::textDim, 10.0f * k);
            }
        }
    }

    void mouseMove (const juce::MouseEvent& e) override
    {
        auto oldCell = hoverCell, oldButton = hoverButton;
        hoverCell = -1;
        hoverButton = 0;
        for (auto& c : cells)
            if (c.r.contains (e.position))
            {
                hoverCell = c.piece;
                hoverButton = c.prev.contains (e.position) ? 1 : c.next.contains (e.position) ? 2
                            : c.down.contains (e.position) ? 3 : c.up.contains (e.position) ? 4 : 0;
            }
        setTooltip (hoverButton == 1 || hoverButton == 2 ? "Swap to the previous / next drum (instant, while playing)"
                  : hoverButton == 3 || hoverButton == 4 ? "Tune down / up to the next note of the song's key"
                  : hoverCell >= 0 ? "Click to select and play" : "");
        setMouseCursor (hoverCell >= 0 ? juce::MouseCursor::PointingHandCursor : juce::MouseCursor::NormalCursor);
        if (oldCell != hoverCell || oldButton != hoverButton)
            repaint();
    }

    void mouseExit (const juce::MouseEvent&) override { hoverCell = -1; hoverButton = 0; repaint(); }

    void mouseDown (const juce::MouseEvent& e) override
    {
        mouseMove (e);
        if (hoverCell < 0)
            return;
        auto p = hoverCell;
        switch (hoverButton)
        {
            case 1: proc.stepVariant (p, -1); break;
            case 2: proc.stepVariant (p, 1); break;
            case 3: proc.stepPitch (p, -1); proc.play (p, 0, 100); break;
            case 4: proc.stepPitch (p, 1); proc.play (p, 0, 100); break;
            default: proc.play (p, 0, 105); break;
        }
        page.select (p);
        page.refresh();
    }

    int selected = -1;

private:
    struct Cell
    {
        int piece = -1, variants = 1, sounds = 0;
        juce::String name, tile, variant, pitch;
        bool tunable = false, inKey = false, keyOn = false, loading = false;
        double flashAt = 0.0;
        float flashVel = 1.0f;
        juce::Rectangle<float> r, variantRow, pitchRow, prev, next, down, up;
    };

    static void hotSpot (juce::Graphics& g, juce::Rectangle<float> r)
    {
        g.setColour (juce::Colours::white.withAlpha (0.16f));
        g.fillEllipse (r.withSizeKeepingCentre (std::min (r.getWidth(), r.getHeight()) + 4.0f, std::min (r.getWidth(), r.getHeight()) + 4.0f));
    }

    void layoutCells()
    {
        if (cells.empty())
            return;
        auto& kit = ui::Kit::get();
        auto area = getLocalBounds().toFloat().reduced (14.0f, 9.0f);
        auto w = area.getWidth() / (float) cells.size();
        for (size_t i = 0; i < cells.size(); ++i)
        {
            auto& c = cells[i];
            c.r = juce::Rectangle<float> (area.getX() + w * (float) i, area.getY(), w, area.getHeight()).reduced (2.5f, 0.0f);
            auto size = kit.size (c.tile);
            auto k = c.r.getHeight() / std::max (1.0f, size.y);
            // The tile's own arrows, at its ends.
            auto prev = kit.box (c.tile, "prev"), next = kit.box (c.tile, "next");
            auto arrowY = c.r.getY() + prev.getCentreY() * k;
            auto hit = 22.0f * k;
            c.prev = juce::Rectangle<float> (hit, hit).withCentre ({ c.r.getX() + prev.getCentreX() * k, arrowY });
            c.next = juce::Rectangle<float> (hit, hit).withCentre ({ c.r.getRight() - (size.x - next.getCentreX()) * k, arrowY });
            c.variantRow = juce::Rectangle<float>::leftTopRightBottom (c.prev.getRight() - 2.0f, arrowY - 8.0f * k, c.next.getX() + 2.0f, arrowY + 8.0f * k);
            if (c.variants <= 1)
                c.prev = c.next = {};
            c.pitchRow = juce::Rectangle<float>::leftTopRightBottom (c.r.getX() + 6.0f * k, c.r.getY() + 57.0f * k, c.r.getRight() - 6.0f * k, c.r.getY() + 76.0f * k);
            c.down = c.tunable ? c.pitchRow.withWidth (18.0f * k) : juce::Rectangle<float>();
            c.up = c.tunable ? c.pitchRow.withLeft (c.pitchRow.getRight() - 18.0f * k) : juce::Rectangle<float>();
        }
    }

    PandaDrumsProcessor& proc;
    KitPage& page;
    std::vector<Cell> cells;
    int hoverCell = -1, hoverButton = 0;
};

//==============================================================================
// Exactly which sample just played, and the buttons to deal with a bad one.
class KitPage::LastHitCard : public juce::Component
{
public:
    explicit LastHitCard (PandaDrumsProcessor& p) : proc (p)
    {
        addAndMakeVisible (bad);
        addAndMakeVisible (replay);
        theme::look (bad, "button_mark_bad", "button_primary_action");
        theme::look (replay, "button_replay");
        bad.setClickingTogglesState (false);
        bad.setTooltip ("Take this exact sample out of rotation (it's remembered with the song)");
        replay.setTooltip ("Play this exact sample again");
        bad.onClick = [this]
        {
            if (! has) return;
            auto now = proc.isBad (e.piece, e.artic, e.hit);
            proc.setBad (e.piece, e.artic, e.hit, ! now);
            update();
        };
        replay.onClick = [this] { if (has) proc.play (e.piece, e.artic, e.velocityIn, e.hit); };
        update();
    }

    void show (const HitEvent& ev)
    {
        e = ev;
        has = true;
        shownAt = ui::now();
        ui::animate (*this, 0.3);
        update();
    }

    void update()
    {
        auto snap = proc.getSnapshot();
        auto kit = proc.getKit();
        bad.setEnabled (has);
        replay.setEnabled (has);
        if (! has || snap == nullptr || kit == nullptr || ! juce::isPositiveAndBelow ((int) e.piece, (int) snap->pieces.size()))
        {
            repaint();
            return;
        }
        auto& rt = snap->pieces[(size_t) e.piece];
        piece = kit->pieces[(size_t) e.piece].name;
        variant = kit->pieces[(size_t) e.piece].variants[(size_t) rt.variant].name;
        artic = articName (*snap, e.piece, e.artic);
        sample = {};
        lane = {};
        if (rt.data != nullptr && juce::isPositiveAndBelow ((int) e.artic, (int) rt.data->artics.size()))
        {
            auto& a = rt.data->artics[(size_t) e.artic];
            if (juce::isPositiveAndBelow ((int) e.hit, (int) a.hits.size()))
                sample = a.hits[(size_t) e.hit].name;
            auto& lay = rt.layouts[(size_t) e.artic];
            if (juce::isPositiveAndBelow ((int) e.zone, (int) lay.zones.size()))
                lane = "lane " + juce::String (lay.zones[(size_t) e.zone].lo) + "-" + juce::String (lay.zones[(size_t) e.zone].hi);
        }
        auto isBad = proc.isBad (e.piece, e.artic, e.hit);
        bad.setButtonText (isBad ? "Marked bad - undo" : "Mark bad");
        bad.setToggleState (isBad, juce::dontSendNotification);
        repaint();
    }

    void resized() override
    {
        // On the pack's hit info panel: the two buttons along the bottom.
        auto row = getLocalBounds().reduced (14, 12).removeFromBottom (32);
        bad.setBounds (row.removeFromLeft (124));
        row.removeFromLeft (6);
        replay.setBounds (row.removeFromLeft (106));
    }

    void paint (juce::Graphics& g) override
    {
        auto r = getLocalBounds().toFloat();
        ui::panel (g, "panel_hit_info_panel", r);
        auto in = r.reduced (14.0f, 11.0f);
        if (! has)
        {
            ui::label (g, "LAST HIT", in.removeFromTop (18.0f), ui::colour::pink, 13.5f, juce::Justification::centredLeft);
            g.setColour (ui::colour::textDim);
            g.setFont (ui::font (11.0f));
            g.drawFittedText ("Play something. Every hit shows its round robin, velocity and zone here, so you can catch a weird sample and mark it.",
                              in.removeFromTop (50.0f).toNearestInt(), juce::Justification::topLeft, 3);
            return;
        }
        auto top = in.removeFromTop (18.0f);
        auto title = piece.toUpperCase();
        auto tw = juce::GlyphArrangement::getStringWidth (ui::font (13.5f), title) + 8.0f;
        ui::label (g, title, top.removeFromLeft (tw), ui::colour::pink, 13.5f, juce::Justification::centredLeft);
        ui::label (g, variant + utf8 ("  \xc2\xb7  ") + artic, top, ui::colour::textDim, 10.5f, juce::Justification::centredLeft);

        // Round robin, velocity and zone on the pack's readouts; they pop when a hit lands.
        in.removeFromTop (5.0f);
        auto row = in.removeFromTop (24.0f);
        auto pop = (float) juce::jlimit (0.0, 1.0, 1.0 - (ui::now() - shownAt) / 0.22);
        auto w = (row.getWidth() - 8.0f) / 3.0f;
        drawReadout (g, "readout_hit", row.removeFromLeft (w), "RR", juce::String (e.round + 1) + "/" + juce::String (e.roundCount), ui::colour::text, pop);
        row.removeFromLeft (4.0f);
        drawReadout (g, "readout_midi", row.removeFromLeft (w), "VEL",
                     juce::String (e.velocityIn) + (e.velocityUsed != e.velocityIn ? utf8 ("\xe2\x86\x92") + juce::String (e.velocityUsed) : juce::String()),
                     ui::colour::yellow, pop);
        row.removeFromLeft (4.0f);
        drawReadout (g, "readout_zone", row, "ZONE", juce::String (e.zone + 1) + "/" + juce::String (e.zoneCount), colour::zone (e.zone, e.zoneCount), pop);

        in.removeFromTop (4.0f);
        ui::label (g, sample + (lane.isNotEmpty() ? "   (" + lane + ")" : juce::String()), in.removeFromTop (15.0f), ui::colour::textDim, 9.5f,
                   juce::Justification::centredLeft);
    }

private:
    PandaDrumsProcessor& proc;
    HitEvent e;
    bool has = false;
    juce::String piece, variant, artic, sample, lane;
    double shownAt = 0.0;
    juce::TextButton bad { "Mark bad" }, replay { "Replay" };
};

//==============================================================================
// Volume, decay and fine tune for the selected drum, plus quick tests.
class KitPage::DrumPanel : public juce::Component
{
public:
    DrumPanel (PandaDrumsProcessor& p, KitPage& k) : proc (p), page (k)
    {
        for (auto* s : { &vol, &decay, &tune })
        {
            s->setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
            s->setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
            s->setPopupDisplayEnabled (true, true, this);
            addAndMakeVisible (*s);
        }
        addAndMakeVisible (sweep);
        addAndMakeVisible (rounds);
        theme::look (sweep, "button_velocity_sweep");
        theme::look (rounds, "button_every_rr");
        sweep.setTooltip ("Plays the drum from the softest to the hardest velocity: hear every zone build up");
        rounds.setTooltip ("Plays every round robin of one zone in turn, to find the odd one out");
        sweep.onClick = [this] { page.velocitySweep(); };
        rounds.onClick = [this] { page.cycleRounds(); };
        setPiece (-1);
    }

    void setPiece (int p)
    {
        piece = p;
        volA.reset(); decayA.reset(); tuneA.reset();
        auto ok = juce::isPositiveAndBelow (p, maxPieces);
        for (auto* c : std::initializer_list<juce::Component*> { &vol, &decay, &tune, &sweep, &rounds })
            c->setEnabled (ok);
        if (ok)
        {
            volA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, PandaDrumsProcessor::pieceParam (p, "Vol"), vol);
            decayA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, PandaDrumsProcessor::pieceParam (p, "Decay"), decay);
            tuneA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, PandaDrumsProcessor::pieceParam (p, "Tune"), tune);
            auto kit = proc.getKit();
            name = kit != nullptr && p < (int) kit->pieces.size() ? kit->pieces[(size_t) p].name : juce::String();
            tune.setEnabled (kit != nullptr && p < (int) kit->pieces.size() && isTunable (kit->pieces[(size_t) p].type));
        }
        repaint();
    }

    void resized() override
    {
        // On the pack's drum edit panel: three knobs and the two test buttons.
        auto r = getLocalBounds().reduced (14, 12);
        r.removeFromTop (20);
        auto buttons = r.removeFromRight (112);
        sweep.setBounds (buttons.removeFromTop (buttons.getHeight() / 2).withSizeKeepingCentre (112, 34));
        rounds.setBounds (buttons.withSizeKeepingCentre (112, 34));
        r.removeFromRight (4);
        auto w = r.getWidth() / 3;
        for (auto* s : { &vol, &decay, &tune })
            s->setBounds (r.removeFromLeft (w).withTrimmedBottom (14).reduced (1));
    }

    void paint (juce::Graphics& g) override
    {
        ui::panel (g, "panel_drum_edit_panel", getLocalBounds().toFloat());
        auto r = getLocalBounds().toFloat().reduced (14.0f, 11.0f);
        ui::label (g, piece >= 0 ? name.toUpperCase() : juce::String ("PICK A DRUM"), r.removeFromTop (18.0f), ui::colour::pink, 13.5f,
                   juce::Justification::centredLeft);
        for (auto* s : { &vol, &decay, &tune })
        {
            auto b = s->getBounds().toFloat();
            ui::label (g, s == &vol ? "VOLUME" : s == &decay ? "DECAY" : "TUNE", b.withY (b.getBottom() + 1.0f).withHeight (13.0f).expanded (8.0f, 0.0f),
                       ui::colour::textDim.withAlpha (s->isEnabled() ? 1.0f : 0.5f), 9.5f);
        }
    }

    int piece = -1;

private:
    PandaDrumsProcessor& proc;
    KitPage& page;
    juce::String name;
    juce::Slider vol, decay, tune;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> volA, decayA, tuneA;
    juce::TextButton sweep { "Velocity sweep" }, rounds { "Every RR" };
};

//==============================================================================
class KitPage::StageToggles : public juce::Component
{
public:
    explicit StageToggles (PandaDrumsProcessor& p) : proc (p)
    {
        popups.setToggleState (proc.showHitInfo, juce::dontSendNotification);
        showtime.setToggleState (proc.getShowtime(), juce::dontSendNotification);
        comic.setToggleState (proc.comicFx, juce::dontSendNotification);
        popups.setTooltip ("A little pop-up on each drum with its round robin, velocity and zone");
        showtime.setTooltip ("Delays the sound by 150 ms (your DAW compensates on playback) so the panda sees every hit coming: he moves to the drum, winds up and lands it dead on time. Turn off when playing live.");
        comic.setTooltip ("BOOM! CRASH! on the big hits");
        theme::accent (popups, "pink");
        theme::accent (showtime, "teal");
        theme::accent (comic, "yellow");
        popups.onClick = [this] { proc.setShowHitInfo (popups.getToggleState()); };
        showtime.onClick = [this] { proc.setShowtime (showtime.getToggleState()); };
        comic.onClick = [this] { proc.setComicFx (comic.getToggleState()); };
        for (auto* b : { &popups, &showtime, &comic })
            addAndMakeVisible (*b);
    }

    void sync()
    {
        popups.setToggleState (proc.showHitInfo, juce::dontSendNotification);
        showtime.setToggleState (proc.getShowtime(), juce::dontSendNotification);
        comic.setToggleState (proc.comicFx, juce::dontSendNotification);
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (14, 10);
        for (auto* b : { &popups, &showtime, &comic })
            b->setBounds (r.removeFromTop (r.getHeight() / (b == &popups ? 3 : b == &showtime ? 2 : 1)));
    }

    void paint (juce::Graphics& g) override
    {
        ui::panel (g, "panel_popup_panel", getLocalBounds().toFloat(), 0.94f);
    }

private:
    PandaDrumsProcessor& proc;
    juce::ToggleButton popups { "Hit pop-ups" }, showtime { "Showtime sync" }, comic { "Comic FX" };
};

//==============================================================================
KitPage::KitPage (PandaDrumsProcessor& p) : stage (p), proc (p)
{
    strip = std::make_unique<DrumStrip> (p, *this);
    card = std::make_unique<LastHitCard> (p);
    panel = std::make_unique<DrumPanel> (p, *this);
    toggles = std::make_unique<StageToggles> (p);
    addAndMakeVisible (stage);
    addAndMakeVisible (*strip);
    addAndMakeVisible (*card);
    addAndMakeVisible (*panel);
    addAndMakeVisible (*toggles);
    stage.onSelect = [this] (int piece) { select (piece); };
    refresh();
    startTimerHz (30);
}

KitPage::~KitPage() = default;

void KitPage::resized()
{
    // The pack's panels at their own size, over the stage.
    auto r = getLocalBounds();
    strip->setBounds (r.removeFromBottom (102));
    stage.setBounds (r);
    card->setBounds (r.getX() + 12, r.getBottom() - 126 - 10, 320, 126);
    panel->setBounds (r.getRight() - 12 - 315, r.getBottom() - 125 - 10, 315, 125);
    toggles->setBounds (r.getRight() - 12 - 196, r.getY() + 110, 196, 104);
}

void KitPage::paint (juce::Graphics& g)
{
    g.fillAll (colour::plum);
}

void KitPage::refresh()
{
    stage.refreshKit();
    strip->refresh();
    card->update();
    toggles->sync();
    if (panel->piece >= 0)
        panel->setPiece (panel->piece);
}

void KitPage::onHit (const HitEvent& e)
{
    if ((e.flags & HitEvent::choke) == 0 && e.zone >= 0)
    {
        card->show (e);
        strip->flash (e.piece, (float) e.velocityIn / 127.0f);
    }
}

void KitPage::select (int piece)
{
    strip->selected = piece;
    stage.setSelectedPiece (piece);
    panel->setPiece (piece);
    strip->repaint();
}

void KitPage::velocitySweep()
{
    auto p = panel->piece;
    if (p < 0)
        return;
    auto t = juce::Time::getMillisecondCounterHiRes() * 0.001;
    queue.clear();
    int i = 0;
    for (int v = 8; v <= 127; v += 9, ++i)
        queue.push_back ({ t + 0.2 * i, p, 0, std::min (v, 127), -1 });
    queue.push_back ({ t + 0.2 * i, p, 0, 127, -1 });
}

void KitPage::cycleRounds()
{
    auto p = panel->piece;
    auto snap = proc.getSnapshot();
    if (snap == nullptr || ! juce::isPositiveAndBelow (p, (int) snap->pieces.size()) || snap->pieces[(size_t) p].layouts.empty())
        return;
    auto& lay = snap->pieces[(size_t) p].layouts.front();
    auto zone = zoneForVelocity (lay, 100);
    if (zone < 0)
        return;
    auto t = juce::Time::getMillisecondCounterHiRes() * 0.001;
    queue.clear();
    int i = 0;
    for (auto h : lay.zones[(size_t) zone].hits)
        queue.push_back ({ t + 0.32 * i++, p, 0, 100, h });
}

void KitPage::timerCallback()
{
    auto t = juce::Time::getMillisecondCounterHiRes() * 0.001;
    while (! queue.empty() && queue.front().at <= t)
    {
        auto q = queue.front();
        queue.erase (queue.begin());
        proc.play (q.piece, q.artic, q.velocity, q.hit);
    }
}
