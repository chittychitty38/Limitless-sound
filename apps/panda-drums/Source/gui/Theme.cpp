#include "Theme.h"
#include "PandaBinaryData.h"
#include "UiKit.h"

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
void look (juce::Component& c, const juce::String& piece, const juce::String& pieceOn)
{
    c.getProperties().set ("piece", piece);
    c.getProperties().set ("pieceOn", pieceOn.isNotEmpty() ? pieceOn : piece);
    c.repaint();
}

void accent (juce::Component& c, const juce::String& name)
{
    c.getProperties().set ("accent", name);
    c.repaint();
}

namespace
{
juce::String pieceFor (juce::Component& c, bool on)
{
    auto v = c.getProperties().getWithDefault (on ? "pieceOn" : "piece", {}).toString();
    if (v.isNotEmpty())
        return v;
    return on ? "button_primary_action" : "button_secondary_action";
}

ui::Accent accentOf (juce::Component& c, ui::Accent fallback)
{
    auto a = c.getProperties().getWithDefault ("accent", {}).toString();
    return a == "teal" ? ui::Accent::teal : a == "yellow" ? ui::Accent::yellow : a == "purple" ? ui::Accent::purple
         : a == "pink" ? ui::Accent::pink : fallback;
}

// The readout pill in an accent's colour (the track of a slider or a meter).
juce::String readoutFor (ui::Accent a)
{
    return a == ui::Accent::teal ? "readout_zone" : a == ui::Accent::yellow ? "readout_midi" : "readout_hit";
}

// How far a toggle has slid (0 off, 1 on), animated over 160 ms after it changes.
float slide (juce::Button& b)
{
    auto& p = b.getProperties();
    auto on = b.getToggleState();
    auto t = ui::now();
    if (! p.contains ("slideState"))
    {
        p.set ("slideState", on);
        p.set ("slideAt", 0.0);
    }
    else if ((bool) p["slideState"] != on)
    {
        p.set ("slideState", on);
        p.set ("slideAt", t);
        ui::animate (b, 0.2);
    }
    auto k = (float) juce::jlimit (0.0, 1.0, (t - (double) p["slideAt"]) / 0.16);
    return on ? k : 1.0f - k;
}
} // namespace

LookAndFeel::LookAndFeel()
{
    using namespace colour;
    setColour (juce::ResizableWindow::backgroundColourId, plum);
    setColour (juce::Label::textColourId, text);
    setColour (juce::TextButton::buttonColourId, plumLight);
    setColour (juce::TextButton::buttonOnColourId, hot);
    setColour (juce::TextButton::textColourOffId, text);
    setColour (juce::TextButton::textColourOnId, text);
    setColour (juce::ComboBox::backgroundColourId, plumLight);
    setColour (juce::ComboBox::textColourId, text);
    setColour (juce::ComboBox::arrowColourId, hot);
    setColour (juce::ComboBox::outlineColourId, plumLine);
    // Not quite opaque, so the menu's window lets the panel's rounded corners through.
    setColour (juce::PopupMenu::backgroundColourId, ui::colour::panel.withAlpha (0.97f));
    setColour (juce::PopupMenu::textColourId, text);
    setColour (juce::PopupMenu::highlightedBackgroundColourId, hot);
    setColour (juce::PopupMenu::highlightedTextColourId, text);
    setColour (juce::PopupMenu::headerTextColourId, gold);
    setColour (juce::Slider::textBoxTextColourId, text);
    setColour (juce::Slider::textBoxOutlineColourId, juce::Colours::transparentBlack);
    setColour (juce::Slider::textBoxBackgroundColourId, juce::Colours::transparentBlack);
    setColour (juce::BubbleComponent::backgroundColourId, ui::colour::panel);
    setColour (juce::BubbleComponent::outlineColourId, ui::colour::border);
    setColour (juce::TooltipWindow::backgroundColourId, ui::colour::panel);
    setColour (juce::TooltipWindow::textColourId, text);
    setColour (juce::TextEditor::backgroundColourId, plumLight);
    setColour (juce::TextEditor::textColourId, text);
    setColour (juce::TextEditor::outlineColourId, plumLine);
    setColour (juce::ListBox::backgroundColourId, plum);
    setColour (juce::ScrollBar::thumbColourId, plumLine);
}

void LookAndFeel::drawRotarySlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float, float, juce::Slider& s)
{
    auto over = s.isMouseOverOrDragging() && s.isEnabled();
    ui::knob (g, juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h), pos, s.isEnabled() ? 1.0f : 0.45f, over ? 0.07f : 0.0f);
}

void LookAndFeel::drawLinearSlider (juce::Graphics& g, int x, int y, int w, int h, float pos, float, float,
                                    juce::Slider::SliderStyle style, juce::Slider& s)
{
    auto r = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h);
    auto a = accentOf (s, ui::Accent::pink);
    auto c = ui::colourOf (a);
    auto alpha = s.isEnabled() ? 1.0f : 0.45f;
    auto over = s.isMouseOverOrDragging() && s.isEnabled();
    auto& kit = ui::Kit::get();
    auto thumbSize = kit.size ("toggle_thumb");
    auto vertical = style == juce::Slider::LinearVertical;
    auto across = vertical ? std::min (16.0f, r.getWidth()) : std::min (16.0f, r.getHeight());

    // The track is the pack's readout pill; the part below (or left of) the value fills with the accent.
    auto track = vertical ? r.withSizeKeepingCentre (across, r.getHeight()) : r.withSizeKeepingCentre (r.getWidth(), across);
    ui::readout (g, readoutFor (a) + (vertical ? "_v" : ""), track, alpha);
    auto inner = track.reduced (across * 0.24f);
    auto fill = vertical ? inner.withTop (juce::jlimit (inner.getY(), inner.getBottom(), pos)) : inner.withRight (juce::jlimit (inner.getX(), inner.getRight(), pos));
    // Faders fill from the bottom; a control centred on zero (like a pan) fills out from the centre.
    auto origin = juce::approximatelyEqual (s.getMinimum(), -s.getMaximum()) ? (float) s.valueToProportionOfLength (0.0) : 0.0f;
    if (origin > 0.0f)
    {
        auto o = vertical ? inner.getBottom() - inner.getHeight() * origin : inner.getX() + inner.getWidth() * origin;
        fill = vertical ? juce::Rectangle<float>::leftTopRightBottom (inner.getX(), std::min (o, pos), inner.getRight(), std::max (o, pos))
                        : juce::Rectangle<float>::leftTopRightBottom (std::min (o, pos), inner.getY(), std::max (o, pos), inner.getBottom());
    }
    g.setColour (c.withAlpha (0.9f * alpha));
    g.fillRoundedRectangle (fill, std::min (fill.getWidth(), fill.getHeight()) * 0.5f);

    // The thumb is the toggle's thumb.
    auto d = vertical ? std::min (r.getWidth(), 26.0f) : std::min (r.getHeight() + 4.0f, 22.0f);
    auto thumb = juce::Rectangle<float> (d, d * thumbSize.y / std::max (1.0f, thumbSize.x))
                     .withCentre (vertical ? juce::Point<float> (r.getCentreX(), pos) : juce::Point<float> (pos, r.getCentreY()));
    g.setColour (juce::Colours::black.withAlpha (0.35f * alpha));
    g.fillEllipse (thumb.translated (0.0f, 2.0f).reduced (1.0f));
    ui::icon (g, "toggle_thumb", thumb, 0.0f, alpha);
    if (over)
    {
        g.setColour (c.withAlpha (0.8f));
        g.drawEllipse (thumb.expanded (1.5f), 2.0f);
    }
}

void LookAndFeel::drawButtonBackground (juce::Graphics& g, juce::Button& b, const juce::Colour&, bool over, bool down)
{
    auto piece = pieceFor (b, b.getToggleState());
    auto r = b.getLocalBounds().toFloat();
    if (down)
        r = r.reduced (r.getWidth() * 0.012f, r.getHeight() * 0.03f).translated (0.0f, 1.0f);
    ui::button (g, piece, r, down ? -0.12f : (over ? 0.08f : 0.0f), b.isEnabled() ? 1.0f : 0.45f);
}

void LookAndFeel::drawButtonText (juce::Graphics& g, juce::TextButton& b, bool, bool down)
{
    // Pieces with their own lettering need none.
    auto piece = pieceFor (b, b.getToggleState());
    if (! ui::Kit::get().box (piece, "text").isEmpty())
        return;
    auto r = b.getLocalBounds().toFloat().reduced (8.0f, 0.0f).translated (0.0f, down ? 1.0f : 0.0f);
    ui::label (g, b.getButtonText(), r, colour::text.withMultipliedAlpha (b.isEnabled() ? 1.0f : 0.5f),
               getTextButtonFont (b, b.getHeight()).getHeight());
}

void LookAndFeel::drawToggleButton (juce::Graphics& g, juce::ToggleButton& b, bool over, bool)
{
    auto r = b.getLocalBounds().toFloat();
    auto sw = juce::Rectangle<float> (r.getX() + 1.0f, r.getCentreY() - 11.0f, 40.0f, 22.0f);
    ui::toggle (g, accentOf (b, ui::Accent::teal), sw, slide (b), over ? 0.08f : 0.0f);
    ui::label (g, b.getButtonText(), r.withLeft (sw.getRight() + 8.0f), colour::text.withMultipliedAlpha (b.isEnabled() ? 1.0f : 0.5f),
               12.5f, juce::Justification::centredLeft);
}

void LookAndFeel::drawComboBox (juce::Graphics& g, int w, int h, bool, int, int, int, int, juce::ComboBox& box)
{
    auto r = juce::Rectangle<float> (0.0f, 0.0f, (float) w, (float) h);
    auto over = box.isMouseOver (true) && box.isEnabled();
    ui::button (g, "button_instrument_selector", r, over ? 0.08f : 0.0f, box.isEnabled() ? 1.0f : 0.45f);
    ui::icon (g, "icon_dropdown", r.removeFromRight ((float) h).reduced ((float) h * 0.32f), 0.0f, box.isEnabled() ? 1.0f : 0.4f);
}

void LookAndFeel::positionComboBoxText (juce::ComboBox& box, juce::Label& l)
{
    l.setBounds (10, 1, box.getWidth() - box.getHeight() - 10, box.getHeight() - 2);
    l.setFont (getComboBoxFont (box));
}

juce::Font LookAndFeel::getComboBoxFont (juce::ComboBox&) { return ui::font (12.5f); }
juce::Font LookAndFeel::getPopupMenuFont() { return ui::font (13.0f); }
juce::Font LookAndFeel::getTextButtonFont (juce::TextButton&, int h) { return ui::font (juce::jlimit (11.0f, 15.0f, (float) h * 0.25f)); }
juce::Font LookAndFeel::getLabelFont (juce::Label& l) { return body ((float) std::min (15, std::max (11, l.getHeight() - 6))); }

void LookAndFeel::drawPopupMenuBackground (juce::Graphics& g, int w, int h)
{
    g.fillAll (juce::Colours::transparentBlack);
    ui::panel (g, "panel_popup_panel", { 0.0f, 0.0f, (float) w, (float) h });
}

int LookAndFeel::getPopupMenuBorderSize() { return 9; }

void LookAndFeel::getIdealPopupMenuItemSize (const juce::String& text, bool isSeparator, int, int& w, int& h)
{
    if (isSeparator)
    {
        w = 50;
        h = 10;
        return;
    }
    h = 30;
    w = juce::roundToInt (juce::GlyphArrangement::getStringWidth (getPopupMenuFont(), text)) + h + 34;
}

void LookAndFeel::drawPopupMenuItem (juce::Graphics& g, const juce::Rectangle<int>& area, bool isSeparator, bool isActive, bool isHighlighted,
                                     bool isTicked, bool hasSubMenu, const juce::String& text, const juce::String&,
                                     const juce::Drawable*, const juce::Colour* textColour)
{
    auto r = area.toFloat();
    if (isSeparator)
    {
        g.setColour (ui::colour::border.withAlpha (0.7f));
        g.fillRect (r.withSizeKeepingCentre (r.getWidth() - 20.0f, 1.5f));
        return;
    }
    if (isHighlighted && isActive)
        ui::button (g, "button_primary_action", r.reduced (2.0f, 1.0f));
    auto tick = r.removeFromLeft (r.getHeight()).reduced (r.getHeight() * 0.24f);
    if (isTicked)
        ui::icon (g, "icon_heart_teal", tick);
    if (hasSubMenu)
        ui::icon (g, "icon_chevron_right", r.removeFromRight (r.getHeight()).reduced (r.getHeight() * 0.3f));
    auto c = textColour != nullptr ? *textColour : colour::text;
    ui::label (g, text, r.withTrimmedRight (8.0f), c.withMultipliedAlpha (isActive ? 1.0f : 0.5f), 13.0f, juce::Justification::centredLeft);
}

void LookAndFeel::drawPopupMenuSectionHeader (juce::Graphics& g, const juce::Rectangle<int>& area, const juce::String& name)
{
    ui::label (g, name, area.toFloat().reduced (12.0f, 0.0f), colour::gold, 11.5f, juce::Justification::bottomLeft);
}

juce::Rectangle<int> LookAndFeel::getTooltipBounds (const juce::String& text, juce::Point<int> pos, juce::Rectangle<int> parent)
{
    juce::AttributedString s;
    s.append (text, ui::font (12.5f), colour::text);
    s.setWordWrap (juce::AttributedString::byWord);
    juce::TextLayout tl;
    tl.createLayoutWithBalancedLineLengths (s, 300.0f);
    auto w = (int) (tl.getWidth() + 30.0f), h = (int) (tl.getHeight() + 22.0f);
    return juce::Rectangle<int> (pos.x > parent.getCentreX() ? pos.x - (w + 12) : pos.x + 24,
                                 pos.y > parent.getCentreY() ? pos.y - (h + 6) : pos.y + 6, w, h).constrainedWithin (parent);
}

void LookAndFeel::drawTooltip (juce::Graphics& g, const juce::String& text, int w, int h)
{
    auto r = juce::Rectangle<float> (0.0f, 0.0f, (float) w, (float) h);
    ui::panel (g, "panel_tooltip", r);
    juce::AttributedString s;
    s.append (text, ui::font (12.5f), colour::text);
    s.setWordWrap (juce::AttributedString::byWord);
    s.setJustification (juce::Justification::centredLeft);
    juce::TextLayout tl;
    tl.createLayoutWithBalancedLineLengths (s, 300.0f);
    tl.draw (g, r.reduced (15.0f, 11.0f));
}

void LookAndFeel::drawCallOutBoxBackground (juce::CallOutBox& box, juce::Graphics& g, const juce::Path&, juce::Image&)
{
    if (auto* content = box.getChildComponent (0))
    {
        auto r = content->getBounds().toFloat().expanded (14.0f);
        g.setColour (juce::Colours::black.withAlpha (0.35f));
        g.fillRoundedRectangle (r.translated (0.0f, 6.0f).reduced (4.0f), 18.0f);
        ui::panel (g, "panel_modal_dialog", r);
    }
}

int LookAndFeel::getCallOutBoxBorderSize (const juce::CallOutBox&) { return 22; }

void LookAndFeel::drawScrollbar (juce::Graphics& g, juce::ScrollBar&, int x, int y, int w, int h, bool vertical, int thumbStart, int thumbSize,
                                 bool over, bool down)
{
    auto r = juce::Rectangle<float> ((float) x, (float) y, (float) w, (float) h);
    auto t = vertical ? juce::Rectangle<float> (r.getX(), (float) thumbStart, r.getWidth(), (float) thumbSize)
                      : juce::Rectangle<float> ((float) thumbStart, r.getY(), (float) thumbSize, r.getHeight());
    auto c = (over || down) ? ui::colour::ring.brighter (0.2f) : ui::colour::border;
    g.setColour (c);
    g.fillRoundedRectangle (t.reduced (vertical ? 2.0f : 1.0f, vertical ? 1.0f : 2.0f), 4.0f);
}

void LookAndFeel::drawBubble (juce::Graphics& g, juce::BubbleComponent&, const juce::Point<float>&, const juce::Rectangle<float>& body)
{
    // A knob's or fader's value, on the pack's tooltip panel.
    ui::panel (g, "panel_tooltip", body.expanded (4.0f, 2.0f));
}

juce::Font LookAndFeel::getSliderPopupFont (juce::Slider&) { return ui::font (12.5f); }

juce::Slider::SliderLayout LookAndFeel::getSliderLayout (juce::Slider& s)
{
    return LookAndFeel_V4::getSliderLayout (s);
}
} // namespace pd::theme
