#pragma once

#include <juce_gui_basics/juce_gui_basics.h>
#include <map>

// The 3D art. Every part of the panda and the kit was rendered in Blender (art/panda3d.py) on
// its own transparent layer, at 1x and 2x the 1280 x 736 stage, and manifest.json says where
// each layer sat on the stage when it was rendered and where its joints and anchors are. The
// stage animates the layers by moving them from where they were rendered.
namespace pd
{
class Skin
{
public:
    static const Skin& get();

    bool isLoaded() const { return loaded; }

    struct Sprite
    {
        juce::String name;
        juce::Rectangle<float> bounds;    // where it sat on the stage when it was rendered
        bool isValid() const { return name.isNotEmpty(); }
    };

    Sprite sprite (const juce::String& name) const;
    bool imagesLoad (const Sprite&) const;                  // both the 1x and the 2x image decode

    // Draws a layer where it was rendered, then moved by t (stage units).
    void draw (juce::Graphics&, const Sprite&, const juce::AffineTransform& t = {}, float alpha = 1.0f) const;

    // Draws a layer so that its points a and b land on from and to (a straight part of a limb:
    // turned to the new direction, stretched along it, `across` scales its thickness).
    void drawAlong (juce::Graphics&, const Sprite&, juce::Point<float> a, juce::Point<float> b,
                    juce::Point<float> from, juce::Point<float> to, float across, float alpha = 1.0f) const;

    const juce::var& manifest() const { return json; }
    juce::var at (const juce::String& path) const;          // "kit/tom/anchor"

    static juce::Point<float> point (const juce::var&);     // [x, y]
    static juce::Rectangle<float> ellipse (const juce::var&); // [cx, cy, rx, ry]
    static float number (const juce::var&, float fallback = 0.0f);

private:
    Skin();
    const juce::Image& image (const juce::String& name, bool hiRes) const;

    bool loaded = false;
    juce::var json;
    std::map<juce::String, Sprite> sprites;
    std::map<juce::String, std::pair<const char*, int>> files;
    mutable std::map<juce::String, juce::Image> cache;
};
} // namespace pd
