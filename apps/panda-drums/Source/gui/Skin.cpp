#include "Skin.h"
#include "PandaArtData.h"

namespace pd
{
const Skin& Skin::get()
{
    static const Skin skin;
    return skin;
}

Skin::Skin()
{
    for (int i = 0; i < PandaArtData::namedResourceListSize; ++i)
    {
        auto* name = PandaArtData::namedResourceList[i];
        int size = 0;
        if (auto* data = PandaArtData::getNamedResource (name, size))
            files[PandaArtData::getNamedResourceOriginalFilename (name)] = { data, size };
    }
    auto m = files.find ("manifest.json");
    if (m == files.end())
        return;
    json = juce::JSON::parse (juce::String::fromUTF8 (m->second.first, m->second.second));
    if (auto* layers = json.getProperty ("files", {}).getDynamicObject())
        for (auto& p : layers->getProperties())
        {
            Sprite s;
            s.name = p.value.getProperty ("file", {}).toString();
            s.bounds = { number (p.value.getProperty ("x", 0)), number (p.value.getProperty ("y", 0)),
                         number (p.value.getProperty ("w", 0)), number (p.value.getProperty ("h", 0)) };
            if (s.name.isNotEmpty())
                sprites[p.name.toString()] = s;
        }
    loaded = ! sprites.empty();
}

Skin::Sprite Skin::sprite (const juce::String& name) const
{
    auto it = sprites.find (name);
    return it != sprites.end() ? it->second : Sprite();
}

bool Skin::imagesLoad (const Sprite& s) const
{
    return s.isValid() && image (s.name, false).isValid() && image (s.name, true).isValid();
}

const juce::Image& Skin::image (const juce::String& name, bool hiRes) const
{
    auto key = name + (hiRes ? "@2x" : "");
    auto it = cache.find (key);
    if (it != cache.end())
        return it->second;
    juce::Image img;
    for (auto* ext : { ".png", ".jpg" })
        if (auto f = files.find (key + ext); f != files.end())
            img = juce::ImageFileFormat::loadFrom (f->second.first, (size_t) f->second.second);
    return cache[key] = img;
}

void Skin::draw (juce::Graphics& g, const Sprite& s, const juce::AffineTransform& t, float alpha) const
{
    if (! s.isValid() || alpha <= 0.0f)
        return;
    // The 2x layer once the layer covers more physical pixels than the 1x one has.
    auto pixels = g.getInternalContext().getPhysicalPixelScaleFactor() * std::sqrt (std::abs (t.getDeterminant()));
    auto& img = image (s.name, pixels > 1.15f);
    auto& use = img.isValid() ? img : image (s.name, pixels <= 1.15f);
    if (! use.isValid())
        return;
    auto place = juce::AffineTransform::scale (s.bounds.getWidth() / (float) use.getWidth(), s.bounds.getHeight() / (float) use.getHeight())
                     .translated (s.bounds.getX(), s.bounds.getY())
                     .followedBy (t);
    g.setOpacity (juce::jlimit (0.0f, 1.0f, alpha));
    g.drawImageTransformed (use, place);
    g.setOpacity (1.0f);
}

void Skin::drawAlong (juce::Graphics& g, const Sprite& s, juce::Point<float> a, juce::Point<float> b,
                      juce::Point<float> from, juce::Point<float> to, float across, float alpha) const
{
    auto d0 = b - a, d1 = to - from;
    auto l0 = d0.getDistanceFromOrigin(), l1 = d1.getDistanceFromOrigin();
    if (l0 < 1.0e-3f || l1 < 1.0e-3f)
        return;
    auto t = juce::AffineTransform::translation (-a.x, -a.y)
                 .rotated (-std::atan2 (d0.y, d0.x))
                 .scaled (l1 / l0, across)
                 .rotated (std::atan2 (d1.y, d1.x))
                 .translated (from.x, from.y);
    draw (g, s, t, alpha);
}

juce::var Skin::at (const juce::String& path) const
{
    auto v = json;
    for (auto& key : juce::StringArray::fromTokens (path, "/", {}))
        v = v.getProperty (key, {});
    return v;
}

juce::Point<float> Skin::point (const juce::var& v)
{
    if (auto* a = v.getArray(); a != nullptr && a->size() >= 2)
        return { number ((*a)[0]), number ((*a)[1]) };
    return {};
}

juce::Rectangle<float> Skin::ellipse (const juce::var& v)
{
    if (auto* a = v.getArray(); a != nullptr && a->size() >= 4)
    {
        auto rx = number ((*a)[2]), ry = number ((*a)[3]);
        return { number ((*a)[0]) - rx, number ((*a)[1]) - ry, rx * 2.0f, ry * 2.0f };
    }
    return {};
}

float Skin::number (const juce::var& v, float fallback)
{
    return v.isDouble() || v.isInt() || v.isInt64() ? (float) (double) v : fallback;
}
} // namespace pd
