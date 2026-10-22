#include "KitPage.h"
#include "Theme.h"

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

void drawArrow (juce::Graphics& g, juce::Rectangle<float> r, float angle, bool hot)
{
    if (r.isEmpty())
        return;
    if (hot)
    {
        g.setColour (colour::hot.withAlpha (0.35f));
        g.fillEllipse (r.withSizeKeepingCentre (20.0f, 20.0f));
    }
    juce::Path tri;
    tri.addTriangle (-4.5f, -5.5f, -4.5f, 5.5f, 5.5f, 0.0f);
    tri.applyTransform (juce::AffineTransform::rotation (angle).translated (r.getCentreX(), r.getCentreY()));
    g.setColour (hot ? juce::Colours::white : colour::hot);
    g.fillPath (tri);
}
} // namespace

//==============================================================================
// Every drum in a row: which one it is, arrows to swap it, arrows to tune it.
class KitPage::DrumStrip : public juce::Component, public juce::SettableTooltipClient
{
public:
    DrumStrip (PandaDrumsProcessor& p, KitPage& k) : proc (p), page (k) {}

    void refresh()
    {
        auto kit = proc.getKit();
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
            cells.push_back (c);
        }
        layoutCells();
        repaint();
    }

    void resized() override { layoutCells(); }

    void paint (juce::Graphics& g) override
    {
        g.fillAll (colour::plum);
        g.setColour (colour::plumLine);
        g.fillRect (0, 0, getWidth(), 2);
        for (auto& c : cells)
        {
            auto sel = c.piece == selected, hov = c.piece == hoverCell;
            theme::drawCard (g, c.r, sel ? colour::plumLight.brighter (0.15f) : (hov ? colour::plumLight : colour::plumLight.darker (0.25f)), 10.0f, false);
            if (sel)
            {
                g.setColour (colour::hot);
                g.drawRoundedRectangle (c.r.reduced (0.5f), 10.0f, 2.0f);
            }
            auto r = c.r.reduced (4.0f, 4.0f);
            g.setColour (sel ? colour::hot : colour::textDim);
            g.setFont (theme::title (12.5f));
            g.drawText (c.name, r.removeFromTop (16.0f), juce::Justification::centred, true);

            auto vr = c.variantRow;
            drawArrow (g, c.prev, juce::MathConstants<float>::pi, hov && hoverButton == 1);
            drawArrow (g, c.next, 0.0f, hov && hoverButton == 2);
            g.setColour (colour::text);
            g.setFont (theme::body (12.5f));
            g.drawFittedText (c.loading ? juce::String ("loading...") : c.variant,
                              vr.withTrimmedLeft (c.prev.isEmpty() ? 2.0f : 18.0f).withTrimmedRight (c.next.isEmpty() ? 2.0f : 18.0f).toNearestInt(),
                              juce::Justification::centred, 1, 0.75f);

            auto pr = c.pitchRow;
            if (c.tunable)
            {
                drawArrow (g, c.down, juce::MathConstants<float>::halfPi, hov && hoverButton == 3);
                drawArrow (g, c.up, -juce::MathConstants<float>::halfPi, hov && hoverButton == 4);
                auto pill = pr.withTrimmedLeft (20.0f).withTrimmedRight (20.0f).reduced (2.0f, 1.0f);
                auto ok = c.keyOn && c.inKey;
                theme::drawPill (g, pill, ok ? colour::mint.withAlpha (0.22f) : colour::ink.withAlpha (0.45f));
                g.setColour (ok ? colour::mint : (c.keyOn ? colour::gold : colour::cream));
                g.setFont (theme::title (14.0f));
                g.drawText (c.pitch + (ok ? utf8 (" \xe2\x9c\x93") : juce::String()), pill, juce::Justification::centred);
            }
            else
            {
                g.setColour (colour::textDim);
                g.setFont (theme::body (11.5f));
                g.drawText (juce::String (c.sounds) + (c.sounds == 1 ? " sound" : " sounds"), pr, juce::Justification::centred);
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
        juce::String name, variant, pitch;
        bool tunable = false, inKey = false, keyOn = false, loading = false;
        juce::Rectangle<float> r, variantRow, pitchRow, prev, next, down, up;
    };

    void layoutCells()
    {
        if (cells.empty())
            return;
        auto area = getLocalBounds().toFloat().reduced (8.0f, 8.0f).withTrimmedTop (2.0f);
        auto w = area.getWidth() / (float) cells.size();
        for (size_t i = 0; i < cells.size(); ++i)
        {
            auto& c = cells[i];
            c.r = juce::Rectangle<float> (area.getX() + w * (float) i, area.getY(), w, area.getHeight()).reduced (3.0f, 0.0f);
            auto inner = c.r.reduced (4.0f, 4.0f).withTrimmedTop (16.0f);
            c.variantRow = inner.removeFromTop (inner.getHeight() * 0.5f);
            c.pitchRow = inner;
            c.prev = c.variants > 1 ? c.variantRow.withWidth (18.0f) : juce::Rectangle<float>();
            c.next = c.variants > 1 ? c.variantRow.withLeft (c.variantRow.getRight() - 18.0f) : juce::Rectangle<float>();
            c.down = c.tunable ? c.pitchRow.withWidth (20.0f) : juce::Rectangle<float>();
            c.up = c.tunable ? c.pitchRow.withLeft (c.pitchRow.getRight() - 20.0f) : juce::Rectangle<float>();
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
        bad.setColour (juce::TextButton::buttonOnColourId, colour::bad);
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
        auto r = getLocalBounds().reduced (12, 10);
        auto row = r.removeFromBottom (26);
        bad.setBounds (row.removeFromLeft (150));
        row.removeFromLeft (8);
        replay.setBounds (row.removeFromLeft (90));
    }

    void paint (juce::Graphics& g) override
    {
        auto r = getLocalBounds().toFloat();
        theme::drawCard (g, r, colour::plum.withAlpha (0.93f));
        auto in = r.reduced (12.0f, 8.0f);
        if (! has)
        {
            g.setColour (colour::hot);
            g.setFont (theme::title (16.0f));
            g.drawText ("LAST HIT", in.removeFromTop (20.0f), juce::Justification::centredLeft);
            g.setColour (colour::textDim);
            g.setFont (theme::body (13.0f));
            g.drawFittedText ("Play something. Every hit shows its round robin, velocity and zone here, so you can catch a weird sample and mark it.",
                              in.removeFromTop (54.0f).toNearestInt(), juce::Justification::topLeft, 3);
            return;
        }
        auto top = in.removeFromTop (20.0f);
        g.setColour (colour::hot);
        g.setFont (theme::title (17.0f));
        g.drawText (piece.toUpperCase(), top, juce::Justification::centredLeft);
        g.setColour (colour::textDim);
        g.setFont (theme::body (12.5f));
        g.drawText (variant + utf8 ("  \xc2\xb7  ") + artic, top.withTrimmedLeft (juce::GlyphArrangement::getStringWidth (theme::title (17.0f), piece.toUpperCase()) + 10.0f),
                    juce::Justification::centredLeft, true);

        auto big = in.removeFromTop (34.0f);
        auto zc = colour::zone (e.zone, e.zoneCount);
        auto part = [&] (const juce::String& label, const juce::String& value, juce::Colour col, float w)
        {
            auto cell = big.removeFromLeft (w);
            g.setColour (colour::textDim);
            g.setFont (theme::title (11.0f));
            g.drawText (label, cell.removeFromTop (11.0f), juce::Justification::centredLeft);
            g.setColour (col);
            g.setFont (theme::display (23.0f));
            g.drawText (value, cell, juce::Justification::centredLeft);
        };
        part ("ROUND ROBIN", juce::String (e.round + 1) + " OF " + juce::String (e.roundCount), colour::cream, 108.0f);
        part ("VELOCITY", juce::String (e.velocityIn) + (e.velocityUsed != e.velocityIn ? juce::String (" > ") + juce::String (e.velocityUsed) : juce::String()), colour::gold, 88.0f);
        part ("ZONE", juce::String (e.zone + 1) + " OF " + juce::String (e.zoneCount), zc, 90.0f);

        g.setColour (colour::textDim);
        g.setFont (theme::body (11.5f));
        g.drawText (sample + (lane.isNotEmpty() ? "   (" + lane + ")" : juce::String()), in.removeFromTop (16.0f), juce::Justification::centredLeft, true);
    }

private:
    PandaDrumsProcessor& proc;
    HitEvent e;
    bool has = false;
    juce::String piece, variant, artic, sample, lane;
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
        auto r = getLocalBounds().reduced (12, 8);
        r.removeFromTop (22);
        auto buttons = r.removeFromRight (128);
        sweep.setBounds (buttons.removeFromTop (buttons.getHeight() / 2).reduced (0, 3));
        rounds.setBounds (buttons.reduced (0, 3));
        r.removeFromRight (6);
        auto w = r.getWidth() / 3;
        for (auto* s : { &vol, &decay, &tune })
            s->setBounds (r.removeFromLeft (w).withTrimmedBottom (14).reduced (2));
    }

    void paint (juce::Graphics& g) override
    {
        theme::drawCard (g, getLocalBounds().toFloat(), colour::plum.withAlpha (0.93f));
        auto r = getLocalBounds().toFloat().reduced (12.0f, 8.0f);
        g.setColour (colour::hot);
        g.setFont (theme::title (16.0f));
        g.drawText (piece >= 0 ? name.toUpperCase() : juce::String ("PICK A DRUM"), r.removeFromTop (20.0f), juce::Justification::centredLeft);
        g.setColour (colour::textDim);
        g.setFont (theme::title (11.0f));
        for (auto* s : { &vol, &decay, &tune })
        {
            auto b = s->getBounds().toFloat();
            g.drawText (s == &vol ? "VOLUME" : s == &decay ? "DECAY" : "TUNE", b.withY (b.getBottom() + 1.0f).withHeight (13.0f).expanded (8.0f, 0.0f),
                        juce::Justification::centred);
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
        showtime.setTooltip ("Delays the sound by 75 ms (your DAW compensates on playback) so the panda winds up and lands every hit dead on time. Turn off when playing live.");
        comic.setTooltip ("BOOM! CRASH! on the big hits");
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
        auto r = getLocalBounds().reduced (10, 6);
        for (auto* b : { &popups, &showtime, &comic })
            b->setBounds (r.removeFromTop (24));
    }

    void paint (juce::Graphics& g) override
    {
        theme::drawCard (g, getLocalBounds().toFloat(), colour::plum.withAlpha (0.82f), 12.0f);
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
    auto r = getLocalBounds();
    strip->setBounds (r.removeFromBottom (84));
    stage.setBounds (r);
    card->setBounds (r.getX() + 12, r.getBottom() - 116, 340, 106);
    panel->setBounds (r.getRight() - 12 - 330, r.getBottom() - 116, 330, 106);
    toggles->setBounds (r.getRight() - 12 - 170, r.getY() + 120, 170, 86);
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
        card->show (e);
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
