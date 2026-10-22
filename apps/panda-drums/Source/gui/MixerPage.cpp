#include "MixerPage.h"
#include "Theme.h"
#include "UiKit.h"

using namespace pd;
namespace colour = pd::theme::colour;

namespace
{
juce::Colour groupColour (MicGroup g)
{
    switch (g)
    {
        case MicGroup::Close:     return ui::colour::pink;
        case MicGroup::Overhead:  return ui::colour::yellow;
        case MicGroup::RoomClose: return ui::colour::teal;
        case MicGroup::RoomFar:   return ui::colour::purple.brighter (0.4f);
        case MicGroup::Other:     return ui::colour::text;
    }
    return ui::colour::text;
}

const char* groupAccent (MicGroup g)
{
    switch (g)
    {
        case MicGroup::Overhead:  return "yellow";
        case MicGroup::RoomClose: return "teal";
        case MicGroup::RoomFar:   return "purple";
        case MicGroup::Close:
        case MicGroup::Other:     break;
    }
    return "pink";
}

const char* groupLabel (MicGroup g)
{
    switch (g)
    {
        case MicGroup::Close:     return "CLOSE";
        case MicGroup::Overhead:  return "OVERHEAD";
        case MicGroup::RoomClose: return "ROOM";
        case MicGroup::RoomFar:   return "FAR ROOM";
        case MicGroup::Other:     return "OTHER";
    }
    return "";
}

// A level meter in the pack's teal readout, stood on end.
void drawMeter (juce::Graphics& g, juce::Rectangle<float> r, float level)
{
    ui::readout (g, "readout_zone_v", r);
    auto db = juce::Decibels::gainToDecibels (level, -60.0f);
    auto frac = juce::jlimit (0.0f, 1.0f, (db + 60.0f) / 66.0f);
    auto in = r.reduced (r.getWidth() * 0.26f, r.getWidth() * 0.3f);
    if (frac <= 0.0f)
        return;
    g.setGradientFill (juce::ColourGradient (ui::colour::teal, in.getX(), in.getBottom(), ui::colour::pink, in.getX(), in.getY(), false));
    g.fillRoundedRectangle (in.withTop (in.getBottom() - in.getHeight() * frac), in.getWidth() * 0.5f);
}

juce::String dbText (double v)
{
    return v <= -59.9 ? juce::String ("-inf") : juce::String (v, 1) + " dB";
}

struct Knob : juce::Slider
{
    Knob()
    {
        setSliderStyle (juce::Slider::RotaryHorizontalVerticalDrag);
        setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
        setPopupDisplayEnabled (true, true, nullptr);
    }
};
} // namespace

//==============================================================================
class MixerPage::Strip : public juce::Component
{
public:
    Strip (PandaDrumsProcessor& p, MixerPage& m, int index) : mic (index), proc (p), page (m)
    {
        fader.setSliderStyle (juce::Slider::LinearVertical);
        fader.setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
        fader.setDoubleClickReturnValue (true, 0.0);
        fader.onValueChange = [this] { repaint(); };
        pandaKnob.setTooltip ("Panda FX: punch and grit for this channel");
        mute.setClickingTogglesState (true);
        solo.setClickingTogglesState (true);
        theme::look (mute, "button_secondary_action", "button_primary_action");
        theme::look (solo, "button_secondary_action", "button_key_selector_blank");
        open.setTooltip ("Open this mic: a fader for every drum inside it");
        open.onClick = [this] { page.openInside (mic); };
        for (auto* c : std::initializer_list<juce::Component*> { &fader, &pandaKnob, &panKnob, &mute, &solo, &open })
            addAndMakeVisible (*c);

        auto& ps = proc.params;
        faderA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (ps, PandaDrumsProcessor::chParam (mic, "Vol"), fader);
        pandaA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (ps, PandaDrumsProcessor::chParam (mic, "Panda"), pandaKnob);
        panA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (ps, PandaDrumsProcessor::chParam (mic, "Pan"), panKnob);
        muteA = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (ps, PandaDrumsProcessor::chParam (mic, "Mute"), mute);
        soloA = std::make_unique<juce::AudioProcessorValueTreeState::ButtonAttachment> (ps, PandaDrumsProcessor::chParam (mic, "Solo"), solo);
    }

    void setMic (const MicDef& def) { name = def.name; group = def.group; theme::accent (fader, groupAccent (group)); repaint(); }

    void resized() override
    {
        auto r = getLocalBounds().reduced (9, 10);
        r.removeFromTop (50);
        auto knobs = r.removeFromTop (62);
        pandaKnob.setBounds (knobs.removeFromLeft (knobs.getWidth() / 2).withTrimmedBottom (14).reduced (1));
        panKnob.setBounds (knobs.withTrimmedBottom (14).reduced (1));
        auto ms = r.removeFromTop (28);
        mute.setBounds (ms.removeFromLeft (ms.getWidth() / 2).reduced (1, 1));
        solo.setBounds (ms.reduced (1, 1));
        open.setBounds (r.removeFromBottom (30).reduced (0, 1));
        r.removeFromBottom (18);
        r.removeFromTop (6);
        meterArea = r.removeFromRight (9).reduced (0, 6).toFloat();
        fader.setBounds (r);
    }

    void paint (juce::Graphics& g) override
    {
        // The pack's mixer channel, its mic's group in the group's colour.
        auto r = getLocalBounds().toFloat().reduced (3.0f, 2.0f);
        ui::panel (g, "panel_mixer_channel", r);
        auto gc = groupColour (group);
        auto t = r.reduced (8.0f, 0.0f).withTrimmedTop (11.0f);
        ui::label (g, groupLabel (group), t.removeFromTop (12.0f), gc, 9.5f);
        g.setColour (ui::colour::text);
        g.setFont (ui::font (12.0f));
        g.drawFittedText (name, t.removeFromTop (30.0f).toNearestInt(), juce::Justification::centred, 2, 0.8f);

        auto pk = pandaKnob.getBounds().toFloat();
        ui::label (g, "PANDA", pk.withY (pk.getBottom()).withHeight (12.0f).expanded (8.0f, 0.0f), ui::colour::textDim, 8.5f);
        auto pn = panKnob.getBounds().toFloat();
        ui::label (g, "PAN", pn.withY (pn.getBottom()).withHeight (12.0f).expanded (8.0f, 0.0f), ui::colour::textDim, 8.5f);

        drawMeter (g, meterArea, level);
        auto fb = fader.getBounds().toFloat();
        ui::label (g, dbText (fader.getValue()), fb.withY (fb.getBottom() + 1.0f).withHeight (16.0f).expanded (10.0f, 0.0f), ui::colour::text, 10.5f);
    }

    void tick()
    {
        auto peak = proc.takeChannelPeak (mic);
        level = std::max (peak, level * 0.86f);
        repaint (meterArea.getSmallestIntegerContainer().expanded (2));
    }

    int mic;

private:
    PandaDrumsProcessor& proc;
    MixerPage& page;
    juce::String name;
    MicGroup group = MicGroup::Close;
    juce::Slider fader;
    Knob pandaKnob, panKnob;
    juce::TextButton mute { "M" }, solo { "S" }, open { "OPEN" };
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> faderA, pandaA, panA;
    std::unique_ptr<juce::AudioProcessorValueTreeState::ButtonAttachment> muteA, soloA;
    juce::Rectangle<float> meterArea;
    float level = 0.0f;
};

//==============================================================================
class MixerPage::MasterStrip : public juce::Component
{
public:
    explicit MasterStrip (PandaDrumsProcessor& p) : proc (p)
    {
        fader.setSliderStyle (juce::Slider::LinearVertical);
        fader.setTextBoxStyle (juce::Slider::NoTextBox, false, 0, 0);
        fader.setDoubleClickReturnValue (true, 0.0);
        theme::accent (fader, "yellow");
        fader.onValueChange = [this] { repaint(); };
        bus.setTooltip ("Panda FX on the whole kit");
        addAndMakeVisible (fader);
        addAndMakeVisible (bus);
        faderA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "master", fader);
        busA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "masterPanda", bus);
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (10, 10);
        r.removeFromTop (50);
        bus.setBounds (r.removeFromTop (62).withTrimmedBottom (14).withSizeKeepingCentre (54, 48));
        r.removeFromTop (34);
        r.removeFromBottom (46);
        meters = r.removeFromRight (20).reduced (0, 6).toFloat();
        fader.setBounds (r);
    }

    void paint (juce::Graphics& g) override
    {
        auto r = getLocalBounds().toFloat().reduced (3.0f, 2.0f);
        ui::panel (g, "panel_mixer_channel", r);
        auto t = r.reduced (8.0f, 0.0f).withTrimmedTop (11.0f);
        ui::label (g, "OUTPUT", t.removeFromTop (12.0f), ui::colour::yellow, 9.5f);
        ui::label (g, "MASTER", t.removeFromTop (28.0f), ui::colour::text, 17.0f);
        auto bb = bus.getBounds().toFloat();
        ui::label (g, "PANDA BUS", bb.withY (bb.getBottom()).withHeight (12.0f).expanded (20.0f, 0.0f), ui::colour::textDim, 8.5f);
        drawMeter (g, meters.withWidth (9.0f), levelL);
        drawMeter (g, meters.withTrimmedLeft (11.0f), levelR);
        auto fb = fader.getBounds().toFloat();
        ui::label (g, dbText (fader.getValue()), fb.withY (fb.getBottom() + 1.0f).withHeight (16.0f).expanded (10.0f, 0.0f), ui::colour::text, 10.5f);
        ui::label (g, juce::String (proc.getActiveVoices()) + " voices", getLocalBounds().toFloat().removeFromBottom (30.0f), ui::colour::textDim, 9.5f);
    }

    void tick()
    {
        levelL = std::max (proc.takeMasterPeak (0), levelL * 0.86f);
        levelR = std::max (proc.takeMasterPeak (1), levelR * 0.86f);
        repaint();
    }

private:
    PandaDrumsProcessor& proc;
    juce::Slider fader;
    Knob bus;
    std::unique_ptr<juce::AudioProcessorValueTreeState::SliderAttachment> faderA, busA;
    juce::Rectangle<float> meters;
    float levelL = 0.0f, levelR = 0.0f;
};

//==============================================================================
// What's inside one mic: a fader for every drum that reaches it.
class MixerPage::InsidePanel : public juce::Component
{
public:
    explicit InsidePanel (PandaDrumsProcessor& p) : proc (p)
    {
        addAndMakeVisible (close);
        addAndMakeVisible (reset);
        close.onClick = [this] { setVisible (false); };
        reset.onClick = [this]
        {
            for (auto* s : faders)
                s->setValue (0.0);
        };
    }

    void show (int m)
    {
        mic = m;
        faders.clear();
        names.clear();
        auto kit = proc.getKit();
        auto snap = proc.getSnapshot();
        if (kit == nullptr || snap == nullptr || ! juce::isPositiveAndBelow (m, (int) kit->mics.size()))
            return;
        micName = kit->mics[(size_t) m].name;
        for (size_t p = 0; p < snap->pieces.size() && p < (size_t) maxPieces; ++p)
        {
            auto& rt = snap->pieces[p];
            bool reaches = false;
            if (rt.data != nullptr)
                for (auto& a : rt.data->artics)
                    for (auto& h : a.hits)
                        if ((size_t) m < h.mics.size() && h.mics[(size_t) m] != nullptr) { reaches = true; break; }
            if (! reaches)
                continue;
            auto* s = faders.add (new juce::Slider (juce::Slider::LinearVertical, juce::Slider::NoTextBox));
            s->setRange (-60.0, 12.0, 0.1);
            s->setSkewFactorFromMidPoint (-12.0);
            s->setDoubleClickReturnValue (true, 0.0);
            s->setPopupDisplayEnabled (true, true, this);
            s->setTextValueSuffix (" dB");
            theme::accent (*s, "yellow");
            s->setValue (proc.getBleedDb ((int) p, m), juce::dontSendNotification);
            auto piece = (int) p;
            s->onValueChange = [this, s, piece] { proc.setBleedDb (piece, mic, (float) s->getValue()); repaint(); };
            addAndMakeVisible (s);
            names.add (kit->pieces[p].name);
        }
        resized();
        setVisible (true);
        toFront (true);
        repaint();
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (18, 14);
        auto top = r.removeFromTop (34);
        close.setBounds (top.removeFromRight (90).reduced (0, 3));
        top.removeFromRight (8);
        reset.setBounds (top.removeFromRight (110).reduced (0, 3));
        r.removeFromTop (30);
        r.removeFromBottom (40);
        if (faders.isEmpty())
            return;
        auto w = std::min (90, r.getWidth() / faders.size());
        auto x = r.getX() + (r.getWidth() - w * faders.size()) / 2;
        for (int i = 0; i < faders.size(); ++i)
            faders[i]->setBounds (x + i * w + w / 2 - 18, r.getY(), 36, r.getHeight());
    }

    void paint (juce::Graphics& g) override
    {
        g.fillAll (colour::ink.withAlpha (0.55f));
        auto r = getLocalBounds().toFloat().reduced (6.0f);
        ui::panel (g, "panel_modal_dialog", r);
        auto in = r.reduced (18.0f, 14.0f);
        ui::label (g, micName.toUpperCase() + utf8 ("  \xc2\xb7  WHAT'S INSIDE"), in.removeFromTop (34.0f), ui::colour::yellow, 18.0f,
                   juce::Justification::centredLeft);
        ui::label (g, "How loud each drum is in this mic. Turn one down here without touching the rest of it. Double-click a fader to reset.",
                   in.removeFromTop (22.0f), ui::colour::textDim, 11.5f, juce::Justification::centredLeft);
        if (faders.isEmpty())
        {
            ui::label (g, "Nothing in the loaded drums reaches this mic.", in, ui::colour::textDim, 12.0f);
            return;
        }
        for (int i = 0; i < faders.size(); ++i)
        {
            auto b = faders[i]->getBounds().toFloat();
            ui::label (g, names[i], b.withY (b.getBottom() + 4.0f).withHeight (18.0f).expanded (30.0f, 0.0f), ui::colour::text, 11.5f);
            ui::label (g, dbText (faders[i]->getValue()), b.withY (b.getBottom() + 20.0f).withHeight (16.0f).expanded (30.0f, 0.0f),
                       ui::colour::yellow, 10.5f);
        }
    }

private:
    PandaDrumsProcessor& proc;
    int mic = -1;
    juce::String micName;
    juce::OwnedArray<juce::Slider> faders;
    juce::StringArray names;
    juce::TextButton close { "Close" }, reset { "Reset all" };
};

//==============================================================================
MixerPage::MixerPage (PandaDrumsProcessor& p) : proc (p)
{
    for (int m = 0; m < maxMics; ++m)
        holder.addChildComponent (strips.add (new Strip (p, *this, m)));
    master = std::make_unique<MasterStrip> (p);
    inside = std::make_unique<InsidePanel> (p);
    viewport.setViewedComponent (&holder, false);
    viewport.setScrollBarsShown (false, true);
    addAndMakeVisible (viewport);
    addAndMakeVisible (*master);
    addChildComponent (*inside);
    refresh();
    startTimerHz (30);
}

MixerPage::~MixerPage() = default;

void MixerPage::refresh()
{
    auto kit = proc.getKit();
    numMics = kit != nullptr ? std::min ((int) kit->mics.size(), maxMics) : 0;
    for (int m = 0; m < maxMics; ++m)
    {
        strips[m]->setVisible (m < numMics);
        if (m < numMics)
            strips[m]->setMic (kit->mics[(size_t) m]);
    }
    resized();
}

void MixerPage::resized()
{
    auto r = getLocalBounds().reduced (12);
    r.removeFromTop (40);
    master->setBounds (r.removeFromRight (128));
    r.removeFromRight (10);
    viewport.setBounds (r);
    auto w = numMics > 0 ? std::max (84, std::min (110, r.getWidth() / numMics)) : 84;
    holder.setSize (w * numMics, r.getHeight() - (w * numMics > r.getWidth() ? 10 : 0));
    for (int m = 0; m < numMics; ++m)
        strips[m]->setBounds (m * w, 0, w, holder.getHeight());
    inside->setBounds (getLocalBounds().reduced (60, 40));
}

void MixerPage::paint (juce::Graphics& g)
{
    g.fillAll (colour::plum);
    auto r = getLocalBounds().reduced (16, 10).removeFromTop (36).toFloat();
    ui::label (g, "MIXER", r.removeFromLeft (110.0f), ui::colour::pink, 18.0f, juce::Justification::centredLeft);
    ui::label (g, "One channel per mic. Hit OPEN on the overheads or rooms to set every drum inside them.", r, ui::colour::textDim, 11.5f,
               juce::Justification::centredLeft);
}

void MixerPage::timerCallback()
{
    if (! isShowing())
        return;
    for (int m = 0; m < numMics; ++m)
        strips[m]->tick();
    master->tick();
}

void MixerPage::openInside (int mic)
{
    inside->show (mic);
}
