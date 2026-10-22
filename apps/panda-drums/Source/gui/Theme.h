#pragma once

#include <juce_gui_basics/juce_gui_basics.h>

// Colours, fonts and the look of every control.
namespace pd::theme
{
namespace colour
{
    const juce::Colour pink       { 0xfff3b6d6 };   // the stage, like the sticker
    const juce::Colour pinkDeep   { 0xffe594c2 };
    const juce::Colour pinkLight  { 0xfffbd9ea };
    const juce::Colour ink        { 0xff151016 };   // outlines
    const juce::Colour cream      { 0xfffbf2dc };   // panda face
    const juce::Colour creamShade { 0xffe9dcbc };
    const juce::Colour purple     { 0xff5e2a9e };   // t-shirt
    const juce::Colour purpleHi   { 0xff8248c8 };
    const juce::Colour heart      { 0xffe2322b };
    const juce::Colour heartDark  { 0xffb3221d };
    const juce::Colour blush      { 0xfff59cc8 };
    // The GUI asset pack's palette (see UiKit.h).
    const juce::Colour plum       { 0xff1c0d23 };   // behind the panels
    const juce::Colour plumLight  { 0xff3a1f45 };
    const juce::Colour plumLine   { 0xff73417b };
    const juce::Colour hot        { 0xffff439d };   // accent
    const juce::Colour mint       { 0xff2aab9c };   // in key, OK
    const juce::Colour gold       { 0xfff5c04a };
    const juce::Colour bad        { 0xffff5a4e };
    const juce::Colour text       { 0xfff6e8f4 };
    const juce::Colour textDim    { 0xffb99dc0 };
    const juce::Colour bronze     { 0xffe7b54c };
    const juce::Colour bronzeDark { 0xffa8721c };
    const juce::Colour chrome     { 0xffdfe3ea };

    // Velocity zones from soft (cool) to hard (hot).
    juce::Colour zone (int zone, int zones);
}

juce::Font display (float height);      // Anton: big condensed, like CRUSH
juce::Font title (float height);        // Lilita One: chunky cartoon
juce::Font body (float height);         // Varela Round: everything small

void drawCard (juce::Graphics&, juce::Rectangle<float>, juce::Colour fill, float radius = 14.0f, bool shadow = true);
void drawPill (juce::Graphics&, juce::Rectangle<float>, juce::Colour fill, juce::Colour outline = juce::Colours::transparentBlack);
void drawTextOutlined (juce::Graphics&, const juce::String&, juce::Rectangle<float>, const juce::Font&, juce::Colour fill,
                       juce::Colour outline, float outlineThickness, juce::Justification = juce::Justification::centred);

// How a control is drawn from the pack: the piece for its off and on states, and an accent
// (pink, teal, yellow or purple) for toggles, sliders and meters.
void look (juce::Component&, const juce::String& piece, const juce::String& pieceOn = {});
void accent (juce::Component&, const juce::String& accentName);

// Tooltips on the pack's tooltip panel.
class Tooltips : public juce::TooltipWindow
{
public:
    explicit Tooltips (juce::Component* parent) : juce::TooltipWindow (parent, 600) { setOpaque (false); }
};

class LookAndFeel : public juce::LookAndFeel_V4
{
public:
    LookAndFeel();

    void drawRotarySlider (juce::Graphics&, int x, int y, int w, int h, float pos, float start, float end, juce::Slider&) override;
    void drawLinearSlider (juce::Graphics&, int x, int y, int w, int h, float pos, float min, float max,
                           juce::Slider::SliderStyle, juce::Slider&) override;
    void drawButtonBackground (juce::Graphics&, juce::Button&, const juce::Colour&, bool over, bool down) override;
    void drawButtonText (juce::Graphics&, juce::TextButton&, bool over, bool down) override;
    void drawToggleButton (juce::Graphics&, juce::ToggleButton&, bool over, bool down) override;
    void drawComboBox (juce::Graphics&, int w, int h, bool down, int bx, int by, int bw, int bh, juce::ComboBox&) override;
    juce::Font getComboBoxFont (juce::ComboBox&) override;
    juce::Font getPopupMenuFont() override;
    juce::Font getTextButtonFont (juce::TextButton&, int buttonHeight) override;
    juce::Font getLabelFont (juce::Label&) override;
    void drawPopupMenuBackground (juce::Graphics&, int w, int h) override;
    void drawPopupMenuItem (juce::Graphics&, const juce::Rectangle<int>& area, bool isSeparator, bool isActive, bool isHighlighted,
                            bool isTicked, bool hasSubMenu, const juce::String& text, const juce::String& shortcut,
                            const juce::Drawable* icon, const juce::Colour* textColour) override;
    void drawPopupMenuSectionHeader (juce::Graphics&, const juce::Rectangle<int>& area, const juce::String& name) override;
    void getIdealPopupMenuItemSize (const juce::String& text, bool isSeparator, int standardHeight, int& w, int& h) override;
    int getPopupMenuBorderSize() override;
    void positionComboBoxText (juce::ComboBox&, juce::Label&) override;
    juce::Rectangle<int> getTooltipBounds (const juce::String&, juce::Point<int> screenPos, juce::Rectangle<int> parentArea) override;
    void drawTooltip (juce::Graphics&, const juce::String& text, int w, int h) override;
    void drawCallOutBoxBackground (juce::CallOutBox&, juce::Graphics&, const juce::Path&, juce::Image&) override;
    int getCallOutBoxBorderSize (const juce::CallOutBox&) override;
    void drawScrollbar (juce::Graphics&, juce::ScrollBar&, int x, int y, int w, int h, bool vertical, int thumbStart, int thumbSize,
                        bool over, bool down) override;
    void drawBubble (juce::Graphics&, juce::BubbleComponent&, const juce::Point<float>& tip, const juce::Rectangle<float>& body) override;
    juce::Font getSliderPopupFont (juce::Slider&) override;
    juce::Slider::SliderLayout getSliderLayout (juce::Slider&) override;
};
} // namespace pd::theme
