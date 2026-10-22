#pragma once

#include <juce_gui_basics/juce_gui_basics.h>
#include <map>

// The interface pieces of the Panda Drums GUI asset pack (Resources/ui, prepared by
// art/ui_prep.py): panels, buttons, the knob, toggles, instrument tiles, readouts and icons. Every
// control in the plugin is drawn from these.
//
// Pieces are stretched the way their shape allows: a panel keeps its rounded corners and stretches
// in between, a button keeps its corners and its lettering, a tile keeps its label and arrows.
// Each stretched piece is rendered once at the screen's pixel size and kept, so the slices meet
// without seams and nothing is resampled twice. Use from the message thread only.
namespace pd::ui
{
class Kit
{
public:
    static const Kit& get();

    bool has (const juce::String& name) const;
    juce::Point<float> size (const juce::String& name) const;          // at 1x
    juce::Rectangle<float> box (const juce::String& name, const char* part) const;  // "text", "prev", "next", "dot", "thumb"
    juce::Point<float> point (const juce::String& name, const char* part) const;    // "pivot"
    float corner (const juce::String& name) const;

    struct Slice { juce::Rectangle<int> src; juce::Rectangle<float> dst; };

    // The piece cut into slices (source rectangles at 1x) laid out on dest; drawn at the pixel size
    // of dest on the screen and cached under key.
    void drawSlices (juce::Graphics&, const juce::String& name, juce::Rectangle<float> dest, const std::vector<Slice>&,
                     float alpha = 1.0f, const juce::String& key = {}) const;
    // The same, brightened (light > 0) or darkened (light < 0).
    void drawSlicesLit (juce::Graphics&, const juce::String& name, juce::Rectangle<float> dest, const std::vector<Slice>&,
                        float alpha, float light, const juce::String& key = {}) const;

    // The whole piece as an image of exactly w x h pixels, properly filtered.
    juce::Image scaled (const juce::String& name, int w, int h) const;

    // The piece at w x h pixels, its shape blurred by radius pixels and padded by radius on every
    // side: draw it filled with a colour for a glow.
    juce::Image glow (const juce::String& name, int w, int h, int radius) const;

private:
    Kit();
    const juce::Image& image (const juce::String& name, bool hiRes) const;
    juce::Image render (const juce::String& name, int w, int h, const std::vector<Slice>&, float density) const;
    juce::var entry (const juce::String& name) const;

    juce::var json;
    std::map<juce::String, std::pair<const char*, int>> files;
    mutable std::map<juce::String, juce::Image> images, rendered;
};

// The pack's lettering (DejaVu Sans Bold), for labels on the blank pieces.
juce::Font font (float height);

namespace colour
{
    const juce::Colour panel     { 0xff271330 };
    const juce::Colour panelHi   { 0xff3a1f45 };
    const juce::Colour border    { 0xff73417b };
    const juce::Colour ring      { 0xff7e538e };
    const juce::Colour pink      { 0xffff439d };
    const juce::Colour teal      { 0xff2aab9c };
    const juce::Colour yellow    { 0xfff5c04a };
    const juce::Colour purple    { 0xff823abe };
    const juce::Colour thumb     { 0xffebfffb };
    const juce::Colour text      { 0xfff6e8f4 };
    const juce::Colour textDim   { 0xffb99dc0 };
}

enum class Accent { pink, teal, yellow, purple };
juce::Colour colourOf (Accent);

// A panel stretched to r, its corners kept.
void panel (juce::Graphics&, const juce::String& name, juce::Rectangle<float> r, float alpha = 1.0f);

// A button stretched to r: scaled to its height, the corners and any lettering kept, the plain
// part in between stretched. light > 0 brightens (hover), < 0 darkens (pressed).
void button (juce::Graphics&, const juce::String& name, juce::Rectangle<float> r, float light = 0.0f, float alpha = 1.0f);

// An instrument tile: scaled to the height of r, its label and arrows kept.
void tile (juce::Graphics&, const juce::String& name, juce::Rectangle<float> r, float light = 0.0f);

// A readout pill stretched to r. Vertical ones (name ending "_v") stretch along their height.
void readout (juce::Graphics&, const juce::String& name, juce::Rectangle<float> r, float alpha = 1.0f);

// The pack's knob in r, its needle at proportion (0..1 sweeps -135 to +135 degrees).
void knob (juce::Graphics&, juce::Rectangle<float> r, float proportion, float alpha = 1.0f, float light = 0.0f);

// A toggle; on goes from 0 (off) to 1 (on), crossfading the pack's off and on pieces.
void toggle (juce::Graphics&, Accent, juce::Rectangle<float> r, float on, float light = 0.0f);

// An icon fitted in r, turned by angle (radians).
void icon (juce::Graphics&, const juce::String& name, juce::Rectangle<float> r, float angle = 0.0f, float alpha = 1.0f);

// Glow around a piece drawn at r (the piece's own shape, blurred, in colour).
void glow (juce::Graphics&, const juce::String& name, juce::Rectangle<float> r, juce::Colour, float radius = 10.0f);

// Text in the pack's lettering, shrunk to fit.
void label (juce::Graphics&, const juce::String&, juce::Rectangle<float>, juce::Colour, float height,
            juce::Justification = juce::Justification::centred);

// Which tile the pack has for a drum (by its name), or tile_blank.
juce::String tileFor (const juce::String& pieceName);

// Keeps repainting a component for the next few seconds (a slide, a flash, a glow fading out).
void animate (juce::Component&, double seconds = 0.25);

// The clock the controls animate by: the wall clock, unless a renderer sets the time of the
// frame it is drawing (seconds; negative goes back to the wall clock).
double now();
void setTime (double seconds);
} // namespace pd::ui
