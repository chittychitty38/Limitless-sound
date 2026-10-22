#include "MixerPage.h"
#include "Theme.h"

using namespace pd;
namespace colour = pd::theme::colour;

namespace
{
juce::Colour groupColour (MicGroup g)
{
    switch (g)
    {
        case MicGroup::Close:     return colour::hot;
        case MicGroup::Overhead:  return colour::gold;
        case MicGroup::RoomClose: return colour::mint;
        case MicGroup::RoomFar:   return juce::Colour (0xffa98bff);
        case MicGroup::Other:     return colour::cream;
    }
    return colour::cream;
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

void drawMeter (juce::Graphics& g, juce::Rectangle<float> r, float level)
{
    g.setColour (colour::ink.withAlpha (0.8f));
    g.fillRoundedRectangle (r, 2.0f);
    auto db = juce::Decibels::gainToDecibels (level, -60.0f);
    auto frac = juce::jlimit (0.0f, 1.0f, (db + 60.0f) / 66.0f);
    auto fill = r.withTop (r.getBottom() - r.getHeight() * frac);
    g.setGradientFill (juce::ColourGradient (colour::mint, r.getX(), r.getBottom(), colour::bad, r.getX(), r.getY(), false));
    g.fillRoundedRectangle (fill, 2.0f);
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
        pandaKnob.setColour (juce::Slider::rotarySliderFillColourId, colour::hot);
        pandaKnob.setTooltip ("Panda FX: punch and grit for this channel");
        panKnob.setColour (juce::Slider::rotarySliderFillColourId, colour::mint);
        mute.setClickingTogglesState (true);
        solo.setClickingTogglesState (true);
        mute.setColour (juce::TextButton::buttonOnColourId, colour::bad);
        solo.setColour (juce::TextButton::buttonOnColourId, colour::gold);
        solo.setColour (juce::TextButton::textColourOnId, colour::ink);
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

    void setMic (const MicDef& def) { name = def.name; group = def.group; repaint(); }

    void resized() override
    {
        auto r = getLocalBounds().reduced (6, 6);
        r.removeFromTop (54);
        auto knobs = r.removeFromTop (60);
        pandaKnob.setBounds (knobs.removeFromLeft (knobs.getWidth() / 2).withTrimmedBottom (14).reduced (1));
        panKnob.setBounds (knobs.withTrimmedBottom (14).reduced (4));
        auto ms = r.removeFromTop (26);
        mute.setBounds (ms.removeFromLeft (ms.getWidth() / 2).reduced (2, 1));
        solo.setBounds (ms.reduced (2, 1));
        open.setBounds (r.removeFromBottom (28).reduced (0, 2));
        r.removeFromBottom (18);
        meterArea = r.removeFromRight (10).reduced (0, 10).toFloat();
        fader.setBounds (r);
    }

    void paint (juce::Graphics& g) override
    {
        auto r = getLocalBounds().toFloat().reduced (3.0f, 2.0f);
        theme::drawCard (g, r, colour::plumLight.darker (0.2f), 12.0f, false);
        auto gc = groupColour (group);
        g.setColour (gc);
        g.fillRoundedRectangle (r.withHeight (6.0f).reduced (8.0f, 0.0f).translated (0.0f, 4.0f), 3.0f);
        auto t = r.reduced (6.0f, 0.0f).withTrimmedTop (12.0f);
        g.setColour (gc);
        g.setFont (theme::title (10.5f));
        g.drawText (groupLabel (group), t.removeFromTop (12.0f), juce::Justification::centred);
        g.setColour (colour::text);
        g.setFont (theme::title (14.0f));
        g.drawFittedText (name, t.removeFromTop (32.0f).toNearestInt(), juce::Justification::centred, 2, 0.8f);

        g.setColour (colour::textDim);
        g.setFont (theme::title (10.0f));
        auto pk = pandaKnob.getBounds().toFloat();
        g.drawText ("PANDA", pk.withY (pk.getBottom()).withHeight (12.0f).expanded (8.0f, 0.0f), juce::Justification::centred);
        auto pn = panKnob.getBounds().toFloat();
        g.drawText ("PAN", pn.withY (pn.getBottom() + 3.0f).withHeight (12.0f).expanded (8.0f, 0.0f), juce::Justification::centred);

        drawMeter (g, meterArea, level);
        auto fb = fader.getBounds().toFloat();
        auto v = fader.getValue();
        g.setColour (colour::text);
        g.setFont (theme::body (12.0f));
        g.drawText (v <= -59.9 ? juce::String ("-inf") : juce::String (v, 1) + " dB", fb.withY (fb.getBottom() + 1.0f).withHeight (16.0f).expanded (10.0f, 0.0f),
                    juce::Justification::centred);
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
        fader.setColour (juce::Slider::trackColourId, colour::gold);
        fader.onValueChange = [this] { repaint(); };
        bus.setColour (juce::Slider::rotarySliderFillColourId, colour::gold);
        bus.setTooltip ("Panda FX on the whole kit");
        addAndMakeVisible (fader);
        addAndMakeVisible (bus);
        faderA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "master", fader);
        busA = std::make_unique<juce::AudioProcessorValueTreeState::SliderAttachment> (proc.params, "masterPanda", bus);
    }

    void resized() override
    {
        auto r = getLocalBounds().reduced (8, 6);
        r.removeFromTop (54);
        bus.setBounds (r.removeFromTop (60).withTrimmedBottom (14).withSizeKeepingCentre (52, 46));
        r.removeFromTop (26);
        r.removeFromBottom (46);
        meters = r.removeFromRight (22).reduced (0, 10).toFloat();
        fader.setBounds (r);
    }

    void paint (juce::Graphics& g) override
    {
        auto r = getLocalBounds().toFloat().reduced (3.0f, 2.0f);
        theme::drawCard (g, r, colour::plumLight, 12.0f, false);
        g.setColour (colour::gold);
        g.fillRoundedRectangle (r.withHeight (6.0f).reduced (8.0f, 0.0f).translated (0.0f, 4.0f), 3.0f);
        g.setFont (theme::title (10.5f));
        g.drawText ("OUTPUT", r.withTrimmedTop (12.0f).withHeight (12.0f), juce::Justification::centred);
        g.setColour (colour::text);
        g.setFont (theme::display (22.0f));
        g.drawText ("MASTER", r.withTrimmedTop (24.0f).withHeight (30.0f), juce::Justification::centred);
        g.setColour (colour::textDim);
        g.setFont (theme::title (10.0f));
        auto bb = bus.getBounds().toFloat();
        g.drawText ("PANDA BUS", bb.withY (bb.getBottom()).withHeight (12.0f).expanded (20.0f, 0.0f), juce::Justification::centred);
        drawMeter (g, meters.withWidth (9.0f), levelL);
        drawMeter (g, meters.withTrimmedLeft (12.0f), levelR);
        auto fb = fader.getBounds().toFloat();
        auto v = fader.getValue();
        g.setColour (colour::text);
        g.setFont (theme::body (12.0f));
        g.drawText (v <= -59.9 ? juce::String ("-inf") : juce::String (v, 1) + " dB", fb.withY (fb.getBottom() + 1.0f).withHeight (16.0f).expanded (10.0f, 0.0f),
                    juce::Justification::centred);
        g.setFont (theme::body (11.0f));
        g.setColour (colour::textDim);
        g.drawFittedText (juce::String (proc.getActiveVoices()) + " voices", getLocalBounds().removeFromBottom (24), juce::Justification::centred, 1);
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
            s->setColour (juce::Slider::trackColourId, colour::gold);
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
        theme::drawCard (g, r, colour::plum, 16.0f);
        auto in = r.reduced (14.0f, 10.0f);
        g.setColour (colour::gold);
        g.setFont (theme::display (28.0f));
        g.drawText (micName.toUpperCase() + "  - WHAT'S INSIDE", in.removeFromTop (36.0f), juce::Justification::centredLeft);
        g.setColour (colour::textDim);
        g.setFont (theme::body (13.0f));
        g.drawText ("How loud each drum is in this mic. Turn one down here without touching the rest of it. Double-click a fader to reset.",
                    in.removeFromTop (22.0f), juce::Justification::centredLeft);
        if (faders.isEmpty())
        {
            g.drawText ("Nothing in the loaded drums reaches this mic.", in, juce::Justification::centred);
            return;
        }
        for (int i = 0; i < faders.size(); ++i)
        {
            auto b = faders[i]->getBounds().toFloat();
            g.setColour (colour::text);
            g.setFont (theme::title (13.0f));
            g.drawFittedText (names[i], b.withY (b.getBottom() + 4.0f).withHeight (18.0f).expanded (30.0f, 0.0f).toNearestInt(), juce::Justification::centred, 1);
            g.setColour (colour::gold);
            g.setFont (theme::body (11.5f));
            auto v = faders[i]->getValue();
            g.drawText (v <= -59.9 ? juce::String ("-inf") : juce::String (v, 1) + " dB", b.withY (b.getBottom() + 20.0f).withHeight (16.0f).expanded (30.0f, 0.0f),
                        juce::Justification::centred);
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
    auto r = getLocalBounds().reduced (16, 10).removeFromTop (36);
    g.setColour (colour::text);
    g.setFont (theme::display (26.0f));
    g.drawText ("MIXER", r, juce::Justification::centredLeft);
    g.setColour (colour::textDim);
    g.setFont (theme::body (13.0f));
    g.drawText ("One channel per mic. Hit OPEN on the overheads or rooms to set every drum inside them.", r.withTrimmedLeft (110),
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
