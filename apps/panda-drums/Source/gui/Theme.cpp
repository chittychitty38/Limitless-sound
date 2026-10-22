#include "Theme.h"
#include "PandaBinaryData.h"

namespace pd::theme
{
juce::Colour colour::zone (int z, int zones)
{
    // Soft hits teal, through gold, to hot pink at full force.
    if (zones <= 1)
        return hot;
    auto t = juce::jlimit (0.0f, 1.0f, (float) z / (float) (zones - 1));
    return t < 0.5f ? mint.interpolatedWith (gold, t * 2.0f) : gold.interpolatedWith (hot, (t - 0.5f) * 2.0f);
}

namespace
{
juce::Typeface::Ptr load (const char* data, int size)
{
    return juce::Typeface::createSystemTypefaceFor (data, (size_t) size);
}
} // namespace

juce::Font display (float h)
{
    static auto tf = load (PandaBinaryData::AntonRegular_ttf, PandaBinaryData::AntonRegular_ttfSize);
    return juce::Font (juce::FontOptions (tf).withHeight (h));
}

juce::Font title (float h)
{
    static auto tf = load (PandaBinaryData::LilitaOneRegular_ttf, PandaBinaryData::LilitaOneRegular_ttfSize);
    return juce::Font (juce::FontOptions (tf).withHeight (h));
}

juce::Font body (float h)
{
    static auto tf = load (PandaBinaryData::VarelaRoundRegular_ttf, PandaBinaryData::VarelaRoundRegular_ttfSize);
    return juce::Font (juce::FontOptions (tf).withHeight (h));
}

void drawCard (juce::Graphics& g, juce::Rectangle<float> r, juce::Colour fill, float radius, bool shadow)
{
    if (shadow)
    {
        g.setColour (juce::Colours::black.withAlpha (0.22f));
        g.fillRoundedRectangle (r.translated (0.0f, 4.0f), radius);
    }
    g.setColour (fill);
    g.fillRoundedRectangle (r, radius);
    g.setGradientFill (juce::ColourGradient (juce::Colours::white.withAlpha (0.07f), r.getX(), r.getY(),
                                             juce::Colours::transparentWhite, r.getX(), r.getY() + 30.0f, false));
    g.fillRoundedRectangle (r, radius);
    g.setColour (juce::Colours::white.withAlpha (0.08f));
    g.drawRoundedRectangle (r.reduced (0.5f), radius, 1.0f);
}

void drawPill (juce::Graphics& g, juce::Rectangle<float> r, juce::Colour fill, juce::Colour outline)
{
    auto radius = r.getHeight() * 0.5f;
    g.setColour (fill);
    g.fillRoundedRectangle (r, radius);
    if (! outline.isTransparent())
    {
        g.setColour (outline);
        g.drawRoundedRectangle (r.reduced (0.75f), radius, 1.5f);
    }
}

void drawTextOutlined (juce::Graphics& g, const juce::String& text, juce::Rectangle<float> r, const juce::Font& font,
                       juce::Colour fill, juce::Colour outline, float thickness, juce::Justification just)
{
    juce::GlyphArrangement ga;
    ga.addFittedText (font, text, r.getX(), r.getY(), r.getWidth(), r.getHeight(), just, 1, 0.9f);
    juce::Path p;
    ga.createPath (p);
    g.setColour (outline);
    g.strokePath (p, juce::PathStrokeType (thickness, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
    g.setColour (fill);
    g.fillPath (p);
}

//==============================================================================
LookAndFeel::LookAndFeel()
{
    using namespace colour;
    setColour (juce::ResizableWindow::backgroundColourId, plum);
    setColour (juce::Label::textColourId, text);
    setColour (juce::TextButton::buttonColourId, plumLight);
    setColour (juce::TextButton::buttonOnColourId, hot);
    setColour (juce::TextButton::textColourOffId, text);
    setColour (juce::TextButton::textColourOnId, juce::Colours::white);
    setColour (juce::ComboBox::backgroundColourId, plumLight);
    setColour (juce::ComboBox::textColourId, text);
    setColour (juce::ComboBox::arrowColourId, hot);
    setColour (juce::ComboBox::outlineColourId, plumLine);
    setColour (juce::PopupMenu::backgroundColourId, plum);
    setColour (juce::PopupMenu::textColourId, text);
    setColour (juce::PopupMenu::highlightedBackgroundColourId, hot);
    setColour (juce::PopupMenu::highlightedTextColourId, juce::Colours::white);
    setColour (juce::PopupMenu::headerTextColourId, gold);
    setColour (juce::Slider::textBoxTextColourId, text);
    setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    setColour (juce::Slider::textBoxBackgroundColourId, juce::Colours::transparentBlack);
    setColour (juce::TooltipWindow::backgroundColourId, plum);
    setColour (juce::TooltipWindow::textColourId, text);
    setColour (juce::TextEditor::backgroundColourId, plumLight);
    setColour (juce::TextEditor::textColourId, text);
    setColour (juce::TextEditor::outlineColourId, plumLine);
    setColour (juce::ListBox::backgroundColourId, plum);
    setColour (juce::ScrollBar::thumbColourId, plumLine);
}

void LookAndFeel::drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float start, float end, juce::Slider& s)
{
    using namespace colour;
    auto r = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h).reduced (3.0f);
    auto size = std::min (r.getWidth(), r.getHeight());
    r = r.withSizeKeepingCentre (size, size);
    auto c = r.getCentre();
    auto radius = size * 0.5f;
    auto angle = start + pos * (end - start);
    auto accent = s.findColour (juce::Slider::rotarySliderFillColourId);
    if (accent == juce::Colours::transparentBlack || accent == juce::LookAndFeel_V4::getCurrentColourScheme().getUIColour (juce::LookAndFeel_V4::ColourScheme::highlightedFill))
        accent = hot;

    // Track and value arc.
    juce::Path track, value;
    track.addCentredArc (c.x, c.y, radius - 2.0f, radius - 2.0f, 0.0f, start, end, true);
    g.setColour (ink.withAlpha (0.6f));
    g.strokePath (track, juce::PathStrokeType (4.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));
    auto centreAngle = s.getMinimum() < 0.0 && s.getMaximum() > 0.0 ? start + (end - start) * (float) s.valueToProportionOfLength (0.0) : start;
    value.addCentredArc (c.x, c.y, radius - 2.0f, radius - 2.0f, 0.0f, std::min (centreAngle, angle), std::max (centreAngle, angle), true);
    g.setColour (accent);
    g.strokePath (value, juce::PathStrokeType (4.0f, juce::PathStrokeType::curved, juce::PathStrokeType::rounded));

    // The cap: a chunky button with a cream pointer.
    auto cap = r.reduced (size * 0.17f);
    g.setColour (juce::Colours::black.withAlpha (0.3f));
    g.fillEllipse (cap.translated (0.0f, 2.0f));
    g.setGradientFill (juce::ColourGradient (plumLight.brighter (0.25f), cap.getX(), cap.getY(), plum, cap.getX(), cap.getBottom(), false));
    g.fillEllipse (cap);
    g.setColour (ink);
    g.drawEllipse (cap, 1.5f);
    auto pr = cap.getWidth() * 0.5f;
    juce::Point<float> tip (c.x + std::sin (angle) * (pr - 4.0f), c.y - std::cos (angle) * (pr - 4.0f));
    juce::Point<float> base (c.x + std::sin (angle) * pr * 0.25f, c.y - std::cos (angle) * pr * 0.25f);
    g.setColour (cream);
    g.drawLine ({ base, tip }, 3.0f);
}

void LookAndFeel::drawLinearSlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float, float,
                                    juce::Slider::SliderStyle style, juce::Slider& s)
{
    using namespace colour;
    auto r = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h);
    auto accent = s.findColour (juce::Slider::trackColourId);
    if (accent.isTransparent() || accent == juce::LookAndFeel_V4::getCurrentColourScheme().getUIColour (juce::LookAndFeel_V4::ColourScheme::highlightedFill))
        accent = hot;

    if (style == juce::Slider::LinearVertical)
    {
        auto track = juce::Rectangle<float> (r.getCentreX() - 3.0f, r.getY(), 6.0f, r.getHeight());
        g.setColour (ink.withAlpha (0.7f));
        g.fillRoundedRectangle (track, 3.0f);
        auto filled = track.withTop (pos);
        g.setColour (accent.withAlpha (0.85f));
        g.fillRoundedRectangle (filled, 3.0f);

        // Fader cap with a paw print.
        auto cap = juce::Rectangle<float> (r.getCentreX() - 15.0f, pos - 11.0f, 30.0f, 22.0f);
        g.setColour (juce::Colours::black.withAlpha (0.35f));
        g.fillRoundedRectangle (cap.translated (0.0f, 2.0f), 6.0f);
        g.setGradientFill (juce::ColourGradient (cream, cap.getX(), cap.getY(), creamShade, cap.getX(), cap.getBottom(), false));
        g.fillRoundedRectangle (cap, 6.0f);
        g.setColour (ink);
        g.drawRoundedRectangle (cap, 6.0f, 1.5f);
        auto pc = cap.getCentre();
        g.fillEllipse (pc.x - 4.0f, pc.y - 1.5f, 8.0f, 6.0f);
        for (int i = 0; i < 3; ++i)
            g.fillEllipse (pc.x - 6.0f + (float) i * 4.5f - 1.2f, pc.y - 6.0f, 3.2f, 3.2f);
        return;
    }

    auto track = juce::Rectangle<float> (r.getX(), r.getCentreY() - 3.0f, r.getWidth(), 6.0f);
    g.setColour (ink.withAlpha (0.7f));
    g.fillRoundedRectangle (track, 3.0f);
    g.setColour (accent);
    g.fillRoundedRectangle (track.withRight (pos), 3.0f);
    auto thumb = juce::Rectangle<float> (16.0f, 16.0f).withCentre ({ pos, r.getCentreY() });
    g.setColour (cream);
    g.fillEllipse (thumb);
    g.setColour (ink);
    g.drawEllipse (thumb, 1.5f);
}

void LookAndFeel::drawButtonBackground (juce::Graphics& g, juce::Button& b, const juce::Colour& bg, bool over, bool down)
{
    using namespace colour;
    auto r = b.getLocalBounds().toFloat().reduced (1.0f);
    auto on = b.getToggleState();
    auto base = on ? b.findColour (juce::TextButton::buttonOnColourId) : bg;
    if (over) base = base.brighter (0.12f);
    if (down) base = base.darker (0.15f);
    auto radius = std::min (r.getHeight() * 0.5f, 12.0f);
    g.setColour (juce::Colours::black.withAlpha (0.25f));
    g.fillRoundedRectangle (r.translated (0.0f, down ? 0.5f : 2.0f), radius);
    g.setColour (base);
    g.fillRoundedRectangle (r.translated (0.0f, down ? 1.0f : 0.0f), radius);
    g.setColour (juce::Colours::white.withAlpha (on ? 0.25f : 0.08f));
    g.drawRoundedRectangle (r.reduced (0.5f).translated (0.0f, down ? 1.0f : 0.0f), radius, 1.0f);
}

void LookAndFeel::drawButtonText (juce::Graphics& g, juce::TextButton& b, bool, bool down)
{
    auto font = getTextButtonFont (b, b.getHeight());
    g.setFont (font);
    g.setColour (b.findColour (b.getToggleState() ? juce::TextButton::textColourOnId : juce::TextButton::textColourOffId)
                  .withMultipliedAlpha (b.isEnabled() ? 1.0f : 0.5f));
    g.drawFittedText (b.getButtonText(), b.getLocalBounds().reduced (6, 0).translated (0, down ? 1 : 0), juce::Justification::centred, 1, 0.8f);
}

void LookAndFeel::drawToggleButton (juce::Graphics& g, juce::ToggleButton& b, bool over, bool)
{
    using namespace colour;
    auto r = b.getLocalBounds().toFloat();
    auto sw = juce::Rectangle<float> (r.getX() + 2.0f, r.getCentreY() - 9.0f, 34.0f, 18.0f);
    auto on = b.getToggleState();
    drawPill (g, sw, on ? mint.darker (0.15f) : ink.withAlpha (0.55f), over ? text.withAlpha (0.4f) : juce::Colours::transparentBlack);
    auto knob = juce::Rectangle<float> (14.0f, 14.0f).withCentre ({ on ? sw.getRight() - 9.0f : sw.getX() + 9.0f, sw.getCentreY() });
    g.setColour (cream);
    g.fillEllipse (knob);
    g.setColour (text.withMultipliedAlpha (b.isEnabled() ? 1.0f : 0.5f));
    g.setFont (body (13.5f));
    g.drawFittedText (b.getButtonText(), r.withLeft (sw.getRight() + 6.0f).toNearestInt(), juce::Justification::centredLeft, 2);
}

void LookAndFeel::drawComboBox (juce::Graphics& g, int w, int h, bool, int, int, int, int, juce::ComboBox& box)
{
    using namespace colour;
    auto r = juce::Rectangle<float> (0.0f, 0.0f, (float) w, (float) h).reduced (1.0f);
    auto radius = std::min (r.getHeight() * 0.5f, 10.0f);
    g.setColour (box.findColour (juce::ComboBox::backgroundColourId));
    g.fillRoundedRectangle (r, radius);
    g.setColour (box.findColour (juce::ComboBox::outlineColourId));
    g.drawRoundedRectangle (r, radius, 1.0f);
    juce::Path arrow;
    auto ax = r.getRight() - 16.0f, ay = r.getCentreY();
    arrow.addTriangle (ax - 5.0f, ay - 2.5f, ax + 5.0f, ay - 2.5f, ax, ay + 3.5f);
    g.setColour (box.findColour (juce::ComboBox::arrowColourId));
    g.fillPath (arrow);
}

juce::Font LookAndFeel::getComboBoxFont (juce::ComboBox&) { return body (14.0f); }
juce::Font LookAndFeel::getPopupMenuFont() { return body (15.0f); }
juce::Font LookAndFeel::getTextButtonFont (juce::TextButton&, int h) { return title (std::min (17.0f, (float) h * 0.55f)); }
juce::Font LookAndFeel::getLabelFont (juce::Label& l) { return body ((float) std::min (15, std::max (11, l.getHeight() - 6))); }

void LookAndFeel::drawPopupMenuBackground (juce::Graphics& g, int w, int h)
{
    g.fillAll (colour::plum);
    g.setColour (colour::plumLine);
    g.drawRect (0, 0, w, h, 1);
}

juce::Slider::SliderLayout LookAndFeel::getSliderLayout (juce::Slider& s)
{
    return LookAndFeel_V4::getSliderLayout (s);
}
} // namespace pd::theme
