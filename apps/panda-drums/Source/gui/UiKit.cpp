#include "UiKit.h"
#include "PandaBinaryData.h"
#include "PandaUiData.h"

namespace pd::ui
{
namespace
{
float num (const juce::var& v, float fallback = 0.0f)
{
    return v.isDouble() || v.isInt() || v.isInt64() ? (float) (double) v : fallback;
}

// Halves an image by averaging each 2 x 2 block (premultiplied, so edges stay clean).
juce::Image halve (const juce::Image& in)
{
    auto w = in.getWidth() / 2, h = in.getHeight() / 2;
    juce::Image out (juce::Image::ARGB, std::max (1, w), std::max (1, h), true);
    juce::Image::BitmapData s (in, juce::Image::BitmapData::readOnly);
    juce::Image::BitmapData d (out, juce::Image::BitmapData::writeOnly);
    for (int y = 0; y < h; ++y)
        for (int x = 0; x < w; ++x)
        {
            juce::uint32 sum[4] = {};
            for (int dy = 0; dy < 2; ++dy)
                for (int dx = 0; dx < 2; ++dx)
                {
                    auto* p = reinterpret_cast<const juce::PixelARGB*> (s.getPixelPointer (x * 2 + dx, y * 2 + dy));
                    sum[0] += p->getAlpha(); sum[1] += p->getRed(); sum[2] += p->getGreen(); sum[3] += p->getBlue();
                }
            auto* q = reinterpret_cast<juce::PixelARGB*> (d.getPixelPointer (x, y));
            q->setARGB ((juce::uint8) ((sum[0] + 2) / 4), (juce::uint8) ((sum[1] + 2) / 4), (juce::uint8) ((sum[2] + 2) / 4), (juce::uint8) ((sum[3] + 2) / 4));
        }
    return out;
}

float physicalScale (juce::Graphics& g)
{
    return std::max (0.05f, g.getInternalContext().getPhysicalPixelScaleFactor());
}

void drawLit (juce::Graphics& g, const juce::Image& img, juce::Rectangle<float> dest, float alpha, float light)
{
    if (! img.isValid() || alpha <= 0.0f)
        return;
    g.setOpacity (juce::jlimit (0.0f, 1.0f, alpha));
    g.drawImage (img, dest);
    if (std::abs (light) > 0.001f)
    {
        g.setColour ((light > 0.0f ? juce::Colours::white : juce::Colours::black).withAlpha (std::min (1.0f, std::abs (light)) * alpha));
        g.drawImage (img, dest, juce::RectanglePlacement::stretchToFit, true);
    }
    g.setOpacity (1.0f);
}
} // namespace

//==============================================================================
const Kit& Kit::get()
{
    static const Kit kit;
    return kit;
}

Kit::Kit()
{
    for (int i = 0; i < PandaUiData::namedResourceListSize; ++i)
    {
        auto* name = PandaUiData::namedResourceList[i];
        int size = 0;
        if (auto* data = PandaUiData::getNamedResource (name, size))
            files[PandaUiData::getNamedResourceOriginalFilename (name)] = { data, size };
    }
    if (auto m = files.find ("ui.json"); m != files.end())
        json = juce::JSON::parse (juce::String::fromUTF8 (m->second.first, m->second.second));
}

juce::var Kit::entry (const juce::String& name) const { return json.getProperty (name, {}); }

bool Kit::has (const juce::String& name) const { return entry (name).isObject() && files.count (name + ".png") > 0; }

juce::Point<float> Kit::size (const juce::String& name) const
{
    auto e = entry (name);
    return { num (e.getProperty ("w", 0)), num (e.getProperty ("h", 0)) };
}

juce::Rectangle<float> Kit::box (const juce::String& name, const char* part) const
{
    if (auto* a = entry (name).getProperty (part, {}).getArray(); a != nullptr && a->size() == 4)
        return juce::Rectangle<float>::leftTopRightBottom (num ((*a)[0]), num ((*a)[1]), num ((*a)[2]), num ((*a)[3]));
    return {};
}

juce::Point<float> Kit::point (const juce::String& name, const char* part) const
{
    if (auto* a = entry (name).getProperty (part, {}).getArray(); a != nullptr && a->size() == 2)
        return { num ((*a)[0]), num ((*a)[1]) };
    return size (name) * 0.5f;
}

float Kit::corner (const juce::String& name) const { return num (entry (name).getProperty ("corner", 0), 0.0f); }

const juce::Image& Kit::image (const juce::String& name, bool hiRes) const
{
    auto key = name + (hiRes ? "@2x" : "");
    if (auto it = images.find (key); it != images.end())
        return it->second;
    juce::Image img;
    if (auto f = files.find (key + ".png"); f != files.end())
        img = juce::ImageFileFormat::loadFrom (f->second.first, (size_t) f->second.second);
    return images[key] = img;
}

juce::Image Kit::render (const juce::String& name, int w, int h, const std::vector<Slice>& slices, float density) const
{
    // The 2x piece once a source pixel covers more than a screen pixel; drawn larger still and
    // halved down when it shrinks a lot, so thin lines don't break up.
    auto* src = &image (name, density > 1.15f);
    if (! src->isValid())
        src = &image (name, density <= 1.15f);
    if (! src->isValid() || w <= 0 || h <= 0)
        return {};
    auto pieceW = size (name).x;
    auto srcScale = pieceW > 0.0f ? (float) src->getWidth() / pieceW : 1.0f;
    auto r = density / srcScale;
    int m = r < 0.375f ? 4 : (r < 0.75f ? 2 : 1);

    juce::Image out (juce::Image::ARGB, w * m, h * m, true);
    {
        juce::Graphics g (out);
        g.setImageResamplingQuality (juce::Graphics::highResamplingQuality);
        for (auto& s : slices)
        {
            auto d = s.dst * (float) m;
            auto x0 = juce::roundToInt (d.getX()), x1 = juce::roundToInt (d.getRight());
            auto y0 = juce::roundToInt (d.getY()), y1 = juce::roundToInt (d.getBottom());
            if (x1 <= x0 || y1 <= y0 || s.src.isEmpty())
                continue;
            auto sr = (s.src.toFloat() * srcScale).toNearestInt().getIntersection (src->getBounds());
            if (! sr.isEmpty())
                g.drawImage (*src, x0, y0, x1 - x0, y1 - y0, sr.getX(), sr.getY(), sr.getWidth(), sr.getHeight());
        }
    }
    for (; m > 1; m /= 2)
        out = halve (out);
    return out;
}

void Kit::drawSlices (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> dest, const std::vector<Slice>& slices,
                      float alpha, const juce::String& key) const
{
    drawSlicesLit (g, name, dest, slices, alpha, 0.0f, key);
}

void Kit::drawSlicesLit (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> dest, const std::vector<Slice>& slices,
                         float alpha, float light, const juce::String& key) const
{
    if (dest.isEmpty() || slices.empty() || alpha <= 0.0f)
        return;
    auto phys = physicalScale (g);
    auto w = std::max (1, juce::roundToInt (dest.getWidth() * phys));
    auto h = std::max (1, juce::roundToInt (dest.getHeight() * phys));
    // The same pixels can be the same piece at a different window size, its corners scaled differently.
    auto id = name + "|" + key + "|" + juce::String (w) + "x" + juce::String (h) + "|" + juce::String (dest.getWidth(), 1) + "x" + juce::String (dest.getHeight(), 1);
    auto it = rendered.find (id);
    if (it == rendered.end())
    {
        if (rendered.size() > 700)
            rendered.clear();
        auto sx = (float) w / dest.getWidth(), sy = (float) h / dest.getHeight();
        std::vector<Slice> px;
        px.reserve (slices.size());
        for (auto& s : slices)
            px.push_back ({ s.src, { s.dst.getX() * sx, s.dst.getY() * sy, s.dst.getWidth() * sx, s.dst.getHeight() * sy } });
        auto& f = slices.front();
        auto density = std::max (px.front().dst.getWidth() / (float) std::max (1, f.src.getWidth()),
                                 px.front().dst.getHeight() / (float) std::max (1, f.src.getHeight()));
        it = rendered.emplace (id, render (name, w, h, px, density)).first;
    }
    drawLit (g, it->second, dest, alpha, light);
}

juce::Image Kit::scaled (const juce::String& name, int w, int h) const
{
    auto id = name + "|whole|" + juce::String (w) + "x" + juce::String (h);
    if (auto it = rendered.find (id); it != rendered.end())
        return it->second;
    if (rendered.size() > 700)
        rendered.clear();
    auto s = size (name);
    std::vector<Slice> one { { { 0, 0, (int) s.x, (int) s.y }, { 0.0f, 0.0f, (float) w, (float) h } } };
    return rendered[id] = render (name, w, h, one, std::max ((float) w / std::max (1.0f, s.x), (float) h / std::max (1.0f, s.y)));
}

juce::Image Kit::glow (const juce::String& name, int w, int h, int radius) const
{
    auto id = name + "|glow" + juce::String (radius) + "|" + juce::String (w) + "x" + juce::String (h);
    if (auto it = rendered.find (id); it != rendered.end())
        return it->second;
    auto piece = scaled (name, w, h);
    juce::Image padded (juce::Image::ARGB, w + radius * 2, h + radius * 2, true), out (juce::Image::ARGB, w + radius * 2, h + radius * 2, true);
    if (piece.isValid())
    {
        juce::Graphics (padded).drawImageAt (piece, radius, radius);
        juce::Graphics g (out);
        juce::DropShadow (juce::Colours::white, radius, {}).drawForImage (g, padded);
    }
    return rendered[id] = out;
}

//==============================================================================
juce::Font font (float height)
{
    static auto tf = juce::Typeface::createSystemTypefaceFor (PandaBinaryData::DejaVuSansBold_ttf, (size_t) PandaBinaryData::DejaVuSansBold_ttfSize);
    return juce::Font (juce::FontOptions (tf).withHeight (height));
}

juce::Colour colourOf (Accent a)
{
    switch (a)
    {
        case Accent::teal:   return colour::teal;
        case Accent::yellow: return colour::yellow;
        case Accent::purple: return colour::purple;
        case Accent::pink:   break;
    }
    return colour::pink;
}

void panel (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> r, float alpha)
{
    auto& kit = Kit::get();
    auto s = kit.size (name);
    auto c = kit.corner (name);
    if (s.x <= 0.0f || r.isEmpty())
        return;
    auto k = std::min ({ 1.0f, r.getWidth() / (2.0f * c), r.getHeight() / (2.0f * c) });
    int sx[] = { 0, (int) c, (int) (s.x - c), (int) s.x }, sy[] = { 0, (int) c, (int) (s.y - c), (int) s.y };
    float dx[] = { 0.0f, c * k, r.getWidth() - c * k, r.getWidth() }, dy[] = { 0.0f, c * k, r.getHeight() - c * k, r.getHeight() };
    std::vector<Kit::Slice> slices;
    for (int row = 0; row < 3; ++row)
        for (int col = 0; col < 3; ++col)
            slices.push_back ({ { sx[col], sy[row], sx[col + 1] - sx[col], sy[row + 1] - sy[row] },
                                { dx[col], dy[row], dx[col + 1] - dx[col], dy[row + 1] - dy[row] } });
    kit.drawSlices (g, name, r, slices, alpha, "panel");
}

namespace
{
// A row of slices across the piece: [0, a) kept, [a, b) stretched, [b, c) kept, [c, d) stretched,
// [d, W) kept, all scaled to the height of r. The kept middle part stays centred on the piece's own
// centre; when it doesn't fit, it's squeezed.
void drawRow (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> r, float a, float b, float c, float d,
              float light, float alpha, const char* kind)
{
    auto& kit = Kit::get();
    auto s = kit.size (name);
    if (s.y <= 0.0f || r.isEmpty())
        return;
    auto k = r.getHeight() / s.y;
    auto W = r.getWidth();
    auto left = a * k, right = (s.x - d) * k, mid = (c - b) * k;
    auto room = W - left - right;
    if (room < 0.0f)
    {
        // Narrower than its ends: squeeze the whole piece.
        kit.drawSlicesLit (g, name, r, { { { 0, 0, (int) s.x, (int) s.y }, { 0.0f, 0.0f, W, r.getHeight() } } }, alpha, light, kind);
        return;
    }
    mid = std::min (mid, room);
    auto centre = W * 0.5f + ((b + c) * 0.5f - s.x * 0.5f) * k;
    auto m0 = juce::jlimit (left, W - right - mid, centre - mid * 0.5f);
    auto H = r.getHeight();
    auto ia = (int) a, ib = (int) b, ic = (int) c, id = (int) d, iw = (int) s.x, ih = (int) s.y;
    std::vector<Kit::Slice> slices {
        { { 0, 0, ia, ih }, { 0.0f, 0.0f, left, H } },
        { { ia, 0, std::max (1, ib - ia), ih }, { left, 0.0f, m0 - left, H } },
        { { ib, 0, ic - ib, ih }, { m0, 0.0f, mid, H } },
        { { ic, 0, std::max (1, id - ic), ih }, { m0 + mid, 0.0f, W - right - m0 - mid, H } },
        { { id, 0, iw - id, ih }, { W - right, 0.0f, right, H } },
    };
    kit.drawSlicesLit (g, name, r, slices, alpha, light, kind);
}
} // namespace

void button (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> r, float light, float alpha)
{
    auto& kit = Kit::get();
    auto s = kit.size (name);
    auto c = std::ceil (kit.corner (name));
    auto t = kit.box (name, "text");
    float b = s.x * 0.5f, e = s.x * 0.5f;
    if (! t.isEmpty())
    {
        b = std::max (c + 1.0f, std::floor (t.getX()) - 3.0f);
        e = std::min (s.x - c - 1.0f, std::ceil (t.getRight()) + 3.0f);
    }
    drawRow (g, name, r, c, b, e, s.x - c, light, alpha, "button");
}

void tile (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> r, float light)
{
    auto& kit = Kit::get();
    auto s = kit.size (name);
    auto t = kit.box (name, "text"), prev = kit.box (name, "prev"), next = kit.box (name, "next");
    auto a = std::ceil (std::max ({ t.getRight(), prev.getRight(), 24.0f }) + 4.0f);
    auto d = std::floor (std::min (next.isEmpty() ? s.x - 20.0f : next.getX(), s.x - 14.0f) - 4.0f);
    auto m = std::floor ((a + d) * 0.5f);
    drawRow (g, name, r, a, m, m, d, light, 1.0f, "tile");
}

void readout (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> r, float alpha)
{
    auto& kit = Kit::get();
    auto vertical = name.endsWith ("_v");
    auto flat = vertical ? name.dropLastCharacters (2) : name;
    auto s = kit.size (flat);
    auto c = std::ceil (kit.corner (flat));
    auto dot = kit.box (flat, "dot");
    auto a = std::ceil (std::max (c, dot.getRight() + 3.0f));
    if (! vertical)
    {
        drawRow (g, name, r, a, s.x - c, s.x - c, s.x - c, 0.0f, alpha, "readout");
        return;
    }
    // Stood on end: the dot is at the bottom.
    auto k = r.getWidth() / s.y;
    auto H = r.getHeight(), W = r.getWidth();
    auto top = c * k, bottom = a * k;
    if (H < top + bottom)
    {
        kit.drawSlices (g, name, r, { { { 0, 0, (int) s.y, (int) s.x }, { 0.0f, 0.0f, W, H } } }, alpha, "readoutv");
        return;
    }
    auto ic = (int) c, ia = (int) a, ih = (int) s.x, iw = (int) s.y;
    kit.drawSlices (g, name, r, {
        { { 0, 0, iw, ic }, { 0.0f, 0.0f, W, top } },
        { { 0, ic, iw, std::max (1, ih - ia - ic) }, { 0.0f, top, W, H - top - bottom } },
        { { 0, ih - ia, iw, ia }, { 0.0f, H - bottom, W, bottom } },
    }, alpha, "readoutv");
}

void knob (juce::Graphics& g, juce::Rectangle<float> r, float proportion, float alpha, float light)
{
    auto& kit = Kit::get();
    auto side = std::min (r.getWidth(), r.getHeight());
    auto sq = r.withSizeKeepingCentre (side, side);
    auto phys = physicalScale (g);
    auto n = std::max (8, juce::roundToInt (side * phys));
    auto px = side / (float) n;
    drawLit (g, kit.scaled ("knob_face", n, n), sq, alpha, light);

    auto s = kit.size ("knob_face");
    auto pivot = kit.point ("knob_face", "pivot") * ((float) n / std::max (1.0f, s.x));
    auto angle = juce::degreesToRadians (-135.0f + 270.0f * juce::jlimit (0.0f, 1.0f, proportion));
    auto needle = kit.scaled ("knob_needle", n, n);
    if (needle.isValid())
    {
        g.setOpacity (alpha);
        g.drawImageTransformed (needle, juce::AffineTransform::rotation (angle, pivot.x, pivot.y).scaled (px).translated (sq.getX(), sq.getY()));
        g.setOpacity (1.0f);
    }
    drawLit (g, kit.scaled ("knob_dot", n, n), sq, alpha, 0.0f);
}

void toggle (juce::Graphics& g, Accent accent, juce::Rectangle<float> r, float on, float light)
{
    auto& kit = Kit::get();
    juce::String colourName = accent == Accent::teal ? "teal" : accent == Accent::yellow ? "yellow" : accent == Accent::purple ? "purple" : "pink";
    auto offName = "toggle_" + colourName + "_off", onName = "toggle_" + colourName + "_on";
    auto s = kit.size (offName);
    if (s.y <= 0.0f)
        return;
    auto k = std::min (r.getHeight() / s.y, r.getWidth() / s.x);
    auto box = juce::Rectangle<float> (s.x * k, s.y * k).withPosition (r.getX(), r.getCentreY() - s.y * k * 0.5f);
    on = juce::jlimit (0.0f, 1.0f, on);
    auto eased = on * on * (3.0f - 2.0f * on);
    auto phys = physicalScale (g);
    auto w = std::max (4, juce::roundToInt (box.getWidth() * phys)), h = std::max (4, juce::roundToInt (box.getHeight() * phys));
    if (eased < 1.0f)
        drawLit (g, kit.scaled (offName + "_track", w, h), box, 1.0f, light);
    if (eased > 0.0f)
        drawLit (g, kit.scaled (onName + "_track", w, h), box, eased, light);
    auto t0 = kit.box (offName, "thumb"), t1 = kit.box (onName, "thumb");
    auto t = t0.isEmpty() ? t1 : (t1.isEmpty() ? t0 : t0 + (t1.getPosition() - t0.getPosition()) * eased);
    auto ts = kit.size ("toggle_thumb");
    auto thumb = juce::Rectangle<float> (ts.x * k, ts.y * k).withCentre (box.getPosition() + t.getCentre() * k);
    drawLit (g, kit.scaled ("toggle_thumb", std::max (2, juce::roundToInt (thumb.getWidth() * phys)), std::max (2, juce::roundToInt (thumb.getHeight() * phys))),
             thumb, 1.0f, 0.0f);
}

void icon (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> r, float angle, float alpha)
{
    auto& kit = Kit::get();
    auto s = kit.size (name);
    if (s.x <= 0.0f || r.isEmpty())
        return;
    auto k = std::min (r.getWidth() / s.x, r.getHeight() / s.y);
    auto box = juce::Rectangle<float> (s.x * k, s.y * k).withCentre (r.getCentre());
    auto phys = physicalScale (g);
    auto img = kit.scaled (name, std::max (2, juce::roundToInt (box.getWidth() * phys)), std::max (2, juce::roundToInt (box.getHeight() * phys)));
    if (! img.isValid())
        return;
    g.setOpacity (juce::jlimit (0.0f, 1.0f, alpha));
    auto px = box.getWidth() / (float) img.getWidth();
    g.drawImageTransformed (img, juce::AffineTransform::scale (px).translated (box.getX(), box.getY())
                                     .rotated (angle, box.getCentreX(), box.getCentreY()));
    g.setOpacity (1.0f);
}

void glow (juce::Graphics& g, const juce::String& name, juce::Rectangle<float> r, juce::Colour c, float radius)
{
    auto phys = physicalScale (g);
    auto w = std::max (2, juce::roundToInt (r.getWidth() * phys)), h = std::max (2, juce::roundToInt (r.getHeight() * phys));
    auto rad = std::max (1, juce::roundToInt (radius * phys));
    auto img = Kit::get().glow (name, w, h, rad);
    if (! img.isValid())
        return;
    g.setColour (c);
    g.drawImage (img, r.expanded ((float) rad / phys), juce::RectanglePlacement::stretchToFit, true);
}

void label (juce::Graphics& g, const juce::String& text, juce::Rectangle<float> r, juce::Colour c, float height, juce::Justification j)
{
    g.setColour (c);
    g.setFont (font (height));
    g.drawFittedText (text, r.toNearestInt(), j, 1, 0.75f);
}

juce::String tileFor (const juce::String& pieceName)
{
    auto n = pieceName.toLowerCase().removeCharacters (" -_");
    static const std::pair<const char*, const char*> names[] = {
        { "kick", "tile_kick" }, { "snare", "tile_snare" }, { "tom1", "tile_tom1" }, { "tom2", "tile_tom2" },
        { "floortom", "tile_floor_tom" }, { "hihat", "tile_hi_hat" }, { "crash1", "tile_crash1" }, { "crash", "tile_crash1" },
        { "crash2", "tile_crash2" }, { "ride", "tile_ride" }, { "china", "tile_china" }, { "splash", "tile_splash" },
    };
    for (auto& p : names)
        if (n == p.first && Kit::get().has (p.second))
            return p.second;
    return "tile_blank";
}

//==============================================================================
namespace
{
class Animator : private juce::Timer
{
public:
    static Animator& get()
    {
        static Animator a;
        return a;
    }

    void add (juce::Component& c, double until)
    {
        for (auto& e : items)
            if (e.first.getComponent() == &c)
            {
                e.second = std::max (e.second, until);
                return;
            }
        items.emplace_back (&c, until);
        if (! isTimerRunning())
            startTimerHz (60);
    }

private:
    void timerCallback() override
    {
        auto t = now();
        for (auto& e : items)
            if (auto* c = e.first.getComponent())
                c->repaint();
        items.erase (std::remove_if (items.begin(), items.end(), [t] (auto& e) { return e.first == nullptr || e.second < t; }), items.end());
        if (items.empty())
            stopTimer();
    }

    std::vector<std::pair<juce::Component::SafePointer<juce::Component>, double>> items;
};
} // namespace

namespace
{
double fixedTime = -1.0;
}

double now() { return fixedTime >= 0.0 ? fixedTime : juce::Time::getMillisecondCounterHiRes() * 0.001; }

void setTime (double seconds) { fixedTime = seconds; }

void animate (juce::Component& c, double seconds)
{
    Animator::get().add (c, now() + seconds);
}
} // namespace pd::ui
