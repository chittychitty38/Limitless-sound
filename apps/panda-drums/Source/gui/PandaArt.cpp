#include "PandaArt.h"
#include "Skin.h"
#include "Theme.h"

namespace pd::art
{
using P = juce::Point<float>;
namespace c = theme::colour;

namespace
{
constexpr float pi = juce::MathConstants<float>::pi;

const juce::PathStrokeType roundStroke (float w)
{
    return juce::PathStrokeType (w, juce::PathStrokeType::curved, juce::PathStrokeType::rounded);
}

// Appends an arc of an axis-aligned ellipse, maths angles (0 = right, pi/2 = down on screen).
void arcTo (juce::Path& p, P centre, float rx, float ry, float from, float to, int steps = 28)
{
    for (int i = 0; i <= steps; ++i)
    {
        auto t = from + (to - from) * (float) i / (float) steps;
        p.lineTo (centre.x + rx * std::cos (t), centre.y + ry * std::sin (t));
    }
}

juce::Path ellipseAt (P centre, float rx, float ry)
{
    juce::Path p;
    p.addEllipse (centre.x - rx, centre.y - ry, rx * 2.0f, ry * 2.0f);
    return p;
}

struct WrapColours { juce::Colour base, light, dark; };

WrapColours wrapColours (Wrap w)
{
    switch (w)
    {
        case Wrap::PurpleSparkle: return { juce::Colour (0xff5b2a9b), juce::Colour (0xffa066e8), juce::Colour (0xff260c45) };
        case Wrap::Brass:         return { juce::Colour (0xffd4a23a), juce::Colour (0xfff8e09a), juce::Colour (0xff7d5410) };
        case Wrap::Maple:         return { juce::Colour (0xffc78545), juce::Colour (0xfff0c792), juce::Colour (0xff6e3f18) };
        case Wrap::Chrome:        return { juce::Colour (0xffbfc5d0), juce::Colour (0xffffffff), juce::Colour (0xff6d7482) };
        case Wrap::Walnut:        return { juce::Colour (0xff6b3f22), juce::Colour (0xffa8744a), juce::Colour (0xff2e1708) };
        case Wrap::Black:         return { juce::Colour (0xff1f1b23), juce::Colour (0xff57505e), juce::Colour (0xff050406) };
    }
    return { c::purple, c::purpleHi, c::ink };
}

juce::ColourGradient shellGradient (const WrapColours& w, float x0, float x1, float y)
{
    juce::ColourGradient grad (w.dark, x0, y, w.dark, x1, y, false);
    grad.addColour (0.12, w.base);
    grad.addColour (0.28, w.light);
    grad.addColour (0.42, w.base);
    grad.addColour (0.8, w.base.darker (0.25f));
    return grad;
}

void chromeLine (juce::Graphics& g, P a, P b, float width)
{
    g.setColour (c::ink);
    g.drawLine ({ a, b }, width + 2.6f);
    g.setColour (c::chrome);
    g.drawLine ({ a, b }, width);
    g.setColour (juce::Colours::white.withAlpha (0.7f));
    g.drawLine ({ a.translated (-width * 0.2f, 0.0f), b.translated (-width * 0.2f, 0.0f) }, width * 0.3f);
}

void floorShadow (juce::Graphics& g, P centre, float rx, float alpha = 0.18f)
{
    g.setGradientFill (juce::ColourGradient (juce::Colour (0xff6a2150).withAlpha (alpha), centre.x, centre.y,
                                             juce::Colour (0xff6a2150).withAlpha (0.0f), centre.x + rx, centre.y, true));
    g.fillEllipse (centre.x - rx, centre.y - rx * 0.16f, rx * 2.0f, rx * 0.32f);
}

float hash01 (int i)
{
    auto x = (juce::uint32) i * 2654435761u;
    x ^= x >> 13; x *= 0x5bd1e995u; x ^= x >> 15;
    return (float) (x & 0xffffu) / 65535.0f;
}
} // namespace

//==============================================================================
P PandaPose::shoulder (bool left) const
{
    auto side = left ? -1.0f : 1.0f;
    return { torso.x + side * shoulderOffset.x * radius, torso.y + shoulderOffset.y * radius + bodyBounce };
}

void drawPandaShadow (juce::Graphics& g, const PandaPose& pose)
{
    floorShadow (g, { pose.head.x, 690.0f }, pose.radius * 2.6f, 0.22f);
}

void drawPandaBody (juce::Graphics& g, const PandaPose& pose)
{
    auto R = pose.radius;
    auto B = pose.torso.translated (0.0f, pose.bodyBounce);
    auto widen = 1.0f + 0.012f * pose.breath;
    auto x = [&] (float u) { return B.x + u * R * widen; };
    auto y = [&] (float v) { return B.y + v * R; };

    // Belly and body (cream), mostly behind the kick.
    juce::Path body;
    body.startNewSubPath (x (-0.42f), y (0.78f));
    body.cubicTo (x (-0.78f), y (0.95f), x (-1.02f), y (1.25f), x (-1.06f), y (1.85f));
    body.cubicTo (x (-1.12f), y (2.55f), x (-0.75f), y (3.1f), x (0.0f), y (3.12f));
    body.cubicTo (x (0.75f), y (3.1f), x (1.12f), y (2.55f), x (1.06f), y (1.85f));
    body.cubicTo (x (1.02f), y (1.25f), x (0.78f), y (0.95f), x (0.42f), y (0.78f));
    body.closeSubPath();
    g.setGradientFill (juce::ColourGradient (c::cream, x (-0.4f), y (1.2f), c::creamShade, x (0.8f), y (2.8f), false));
    g.fillPath (body);
    g.setColour (c::ink);
    g.strokePath (body, roundStroke (R * 0.045f));

    // T-shirt.
    juce::Path shirt;
    shirt.startNewSubPath (x (-0.44f), y (0.8f));
    shirt.cubicTo (x (-0.8f), y (0.96f), x (-1.03f), y (1.25f), x (-1.07f), y (1.85f));
    shirt.lineTo (x (-1.08f), y (2.2f));
    // Wavy hem.
    for (int i = 0; i <= 8; ++i)
    {
        auto u = -1.08f + 2.16f * (float) i / 8.0f;
        auto wave = (i % 2 == 0) ? 2.26f : 2.31f;
        shirt.lineTo (x (u), y (wave + 0.06f * (1.0f - std::abs (u))));
    }
    shirt.lineTo (x (1.07f), y (1.85f));
    shirt.cubicTo (x (1.03f), y (1.25f), x (0.8f), y (0.96f), x (0.44f), y (0.8f));
    shirt.quadraticTo (x (0.0f), y (0.98f), x (-0.44f), y (0.8f));
    shirt.closeSubPath();
    g.setGradientFill (juce::ColourGradient (c::purpleHi, x (-0.6f), y (0.9f), c::purple.darker (0.25f), x (0.9f), y (2.3f), false));
    g.fillPath (shirt);
    // Folds.
    g.setColour (c::purple.darker (0.45f).withAlpha (0.55f));
    juce::Path folds;
    folds.startNewSubPath (x (-0.62f), y (1.95f)); folds.quadraticTo (x (-0.45f), y (2.05f), x (-0.3f), y (2.18f));
    folds.startNewSubPath (x (0.55f), y (1.9f));  folds.quadraticTo (x (0.42f), y (2.05f), x (0.38f), y (2.2f));
    g.strokePath (folds, roundStroke (R * 0.025f));
    g.setColour (c::ink);
    g.strokePath (shirt, roundStroke (R * 0.045f));

    // Collar.
    juce::Path collar;
    collar.startNewSubPath (x (-0.4f), y (0.86f));
    collar.quadraticTo (x (0.0f), y (1.08f), x (0.4f), y (0.86f));
    g.setColour (c::purple.darker (0.5f));
    g.strokePath (collar, roundStroke (R * 0.07f));

    // A little heart on the chest.
    drawHeart (g, { x (-0.58f), y (1.36f), R * 0.3f, R * 0.27f }, c::heart, c::ink, R * 0.025f);

    // Sleeves.
    for (auto side : { -1.0f, 1.0f })
    {
        juce::Path sleeve;
        auto cx = x (side * 0.93f), cy = y (1.28f);
        sleeve.addEllipse (-R * 0.3f, -R * 0.24f, R * 0.6f, R * 0.48f);
        sleeve.applyTransform (juce::AffineTransform::rotation (side * 0.55f).translated (cx, cy));
        g.setGradientFill (juce::ColourGradient (c::purpleHi, cx - R * 0.2f, cy - R * 0.2f, c::purple.darker (0.2f), cx + R * 0.2f, cy + R * 0.3f, false));
        g.fillPath (sleeve);
        g.setColour (c::ink);
        g.strokePath (sleeve, roundStroke (R * 0.04f));
    }
}

void drawPandaHead (juce::Graphics& g, const PandaPose& pose)
{
    auto R = pose.radius;
    auto H = pose.head.translated (0.0f, pose.bodyBounce * 0.6f);

    juce::Graphics::ScopedSaveState save (g);
    g.addTransform (juce::AffineTransform::scale (1.0f, pose.squash, H.x, H.y + 0.9f * R)
                        .followedBy (juce::AffineTransform::rotation (pose.tilt, H.x, H.y + 0.9f * R)));

    auto at = [&] (float u, float v) { return P (H.x + u * R, H.y + v * R); };

    // Ears, behind the head.
    for (auto side : { -1.0f, 1.0f })
    {
        juce::Graphics::ScopedSaveState s (g);
        auto base = at (side * 0.55f, -0.52f);
        g.addTransform (juce::AffineTransform::rotation (side * (side < 0 ? pose.earL : pose.earR), base.x, base.y));
        auto e = at (side * 0.76f, -0.72f);
        g.setColour (c::ink);
        g.fillEllipse (e.x - R * 0.35f, e.y - R * 0.35f, R * 0.7f, R * 0.7f);
        g.setColour (juce::Colour (0xff3d3439));
        auto inner = at (side * 0.71f, -0.66f);
        g.fillEllipse (inner.x - R * 0.17f, inner.y - R * 0.17f, R * 0.34f, R * 0.34f);
        g.setColour (juce::Colours::white.withAlpha (0.12f));
        g.fillEllipse (e.x - R * 0.2f, e.y - R * 0.27f, R * 0.18f, R * 0.12f);
    }

    // Head.
    auto head = ellipseAt (H, R * 1.04f, R * 0.93f);
    juce::ColourGradient face (juce::Colour (0xfffffbf0), H.x - R * 0.35f, H.y - R * 0.45f, c::creamShade, H.x + R * 0.6f, H.y + R * 0.9f, true);
    face.addColour (0.55, c::cream);
    g.setGradientFill (face);
    g.fillPath (head);

    // Blush.
    for (auto side : { -1.0f, 1.0f })
    {
        auto ch = at (side * 0.68f, 0.34f);
        auto glow = 0.75f + 0.25f * pose.blushGlow;
        g.setGradientFill (juce::ColourGradient (c::blush.withAlpha (glow), ch.x, ch.y, c::blush.withAlpha (0.0f), ch.x + R * 0.2f, ch.y, true));
        g.fillEllipse (ch.x - R * 0.2f, ch.y - R * 0.12f, R * 0.4f, R * 0.24f);
        g.setColour (c::blush.withAlpha (glow));
        g.fillEllipse (ch.x - R * 0.14f, ch.y - R * 0.085f, R * 0.28f, R * 0.17f);
    }

    g.setColour (c::ink);
    g.strokePath (head, roundStroke (R * 0.05f));

    // Eye patches and eyes.
    for (auto side : { -1.0f, 1.0f })
    {
        auto pc = at (side * 0.4f, 0.01f);
        juce::Path patch;
        patch.addEllipse (-R * 0.25f, -R * 0.2f, R * 0.5f, R * 0.4f);
        patch.applyTransform (juce::AffineTransform::rotation (side * 0.45f).translated (pc.x, pc.y));
        g.setColour (c::ink);
        g.fillPath (patch);

        auto ec = pc.translated (-side * R * 0.03f, -R * 0.02f);
        if (pose.happy > 0.5f)
        {
            juce::Path happy;
            happy.startNewSubPath (ec.x - R * 0.12f, ec.y + R * 0.05f);
            happy.quadraticTo (ec.x, ec.y - R * 0.12f, ec.x + R * 0.12f, ec.y + R * 0.05f);
            g.setColour (c::cream);
            g.strokePath (happy, roundStroke (R * 0.06f));
        }
        else if (pose.blink > 0.82f)
        {
            juce::Path shut;
            shut.startNewSubPath (ec.x - R * 0.12f, ec.y);
            shut.quadraticTo (ec.x, ec.y + R * 0.08f, ec.x + R * 0.12f, ec.y);
            g.setColour (c::cream);
            g.strokePath (shut, roundStroke (R * 0.045f));
        }
        else
        {
            auto open = 1.0f - pose.blink;
            auto er = R * 0.16f;
            g.setColour (juce::Colours::white);
            g.fillEllipse (ec.x - er, ec.y - er * open, er * 2.0f, er * 2.0f * open);
            juce::Graphics::ScopedSaveState s (g);
            g.reduceClipRegion (ellipseAt (ec, er, er * open));
            auto pp = ec + P (pose.look.x * R * 0.05f, pose.look.y * R * 0.045f);
            auto pr = R * 0.105f;
            g.setColour (c::ink);
            g.fillEllipse (pp.x - pr, pp.y - pr, pr * 2.0f, pr * 2.0f);
            g.setColour (juce::Colours::white);
            g.fillEllipse (pp.x - R * 0.077f, pp.y - R * 0.082f, R * 0.084f, R * 0.084f);
            g.fillEllipse (pp.x + R * 0.02f, pp.y + R * 0.02f, R * 0.036f, R * 0.036f);
        }
    }

    // Glasses.
    for (auto side : { -1.0f, 1.0f })
    {
        auto lc = at (side * 0.4f, 0.0f);
        auto lens = juce::Rectangle<float> (R * 0.72f, R * 0.56f).withCentre (lc);
        juce::Path frame;
        frame.addRoundedRectangle (lens, R * 0.2f);
        {
            juce::Graphics::ScopedSaveState s (g);
            g.reduceClipRegion (frame);
            juce::Path glare;
            glare.startNewSubPath (lens.getX() + R * 0.08f, lens.getBottom());
            glare.lineTo (lens.getX() + R * 0.3f, lens.getY());
            glare.lineTo (lens.getX() + R * 0.42f, lens.getY());
            glare.lineTo (lens.getX() + R * 0.2f, lens.getBottom());
            glare.closeSubPath();
            g.setColour (juce::Colours::white.withAlpha (0.16f));
            g.fillPath (glare);
        }
        g.setColour (c::ink);
        g.strokePath (frame, roundStroke (R * 0.075f));
        // Temple arm to the side of the head.
        juce::Path arm;
        arm.startNewSubPath (lc.x + side * R * 0.36f, lc.y - R * 0.12f);
        arm.lineTo (H.x + side * R * 1.0f, H.y - R * 0.16f);
        g.strokePath (arm, roundStroke (R * 0.06f));
    }
    juce::Path bridge;
    bridge.startNewSubPath (at (-0.06f, -0.1f));
    bridge.quadraticTo (at (0.0f, -0.17f), at (0.06f, -0.1f));
    g.strokePath (bridge, roundStroke (R * 0.07f));

    // Eyebrows, raised when excited.
    auto lift = 0.06f * pose.mouthOpen;
    for (auto side : { -1.0f, 1.0f })
    {
        juce::Path brow;
        brow.startNewSubPath (at (side * 0.25f, -0.4f - lift));
        brow.quadraticTo (at (side * 0.38f, -0.49f - lift), at (side * 0.53f, -0.42f - lift));
        g.strokePath (brow, roundStroke (R * 0.055f));
    }

    // Nose.
    auto n = at (0.0f, 0.2f);
    juce::Path nose;
    nose.startNewSubPath (n.x - R * 0.1f, n.y - R * 0.045f);
    nose.quadraticTo (n.x, n.y - R * 0.085f, n.x + R * 0.1f, n.y - R * 0.045f);
    nose.quadraticTo (n.x + R * 0.1f, n.y + R * 0.01f, n.x, n.y + R * 0.075f);
    nose.quadraticTo (n.x - R * 0.1f, n.y + R * 0.01f, n.x - R * 0.1f, n.y - R * 0.045f);
    nose.closeSubPath();
    g.setColour (c::ink);
    g.fillPath (nose);
    g.setColour (juce::Colours::white.withAlpha (0.45f));
    g.fillEllipse (n.x - R * 0.06f, n.y - R * 0.055f, R * 0.06f, R * 0.03f);

    // Mouth: a grin that opens up, or a round "O" on the big hits.
    auto round = juce::jlimit (0.0f, 1.0f, pose.mouthRound);
    auto open = juce::jlimit (0.0f, 1.0f, pose.mouthOpen);
    auto w = R * juce::jmap (round, 0.42f, 0.26f);
    auto h = R * (0.07f + 0.26f * open + 0.06f * round);
    auto top = H.y + R * 0.33f;
    juce::Path mouth;
    mouth.startNewSubPath (H.x - w * 0.5f, top);
    mouth.quadraticTo (H.x, top + juce::jmap (round, R * 0.06f, -h * 0.55f), H.x + w * 0.5f, top);
    mouth.cubicTo (H.x + w * 0.5f, top + h * 1.25f, H.x - w * 0.5f, top + h * 1.25f, H.x - w * 0.5f, top);
    mouth.closeSubPath();
    g.setColour (juce::Colour (0xff7a1414));
    g.fillPath (mouth);
    {
        juce::Graphics::ScopedSaveState s (g);
        g.reduceClipRegion (mouth);
        g.setColour (c::heart);
        g.fillEllipse (H.x - w * 0.32f, top + h * 0.45f, w * 0.64f, h * 0.9f);
        g.setColour (juce::Colours::white.withAlpha (0.25f));
        g.fillEllipse (H.x - w * 0.12f, top + h * 0.55f, w * 0.16f, h * 0.18f);
    }
    g.setColour (c::ink);
    g.strokePath (mouth, roundStroke (R * 0.04f));
    // Philtrum and dimples.
    g.drawLine ({ n.x, n.y + R * 0.07f, n.x, top + juce::jmap (round, R * 0.04f, -h * 0.25f) }, R * 0.035f);
    for (auto side : { -1.0f, 1.0f })
    {
        juce::Path d;
        auto e = P (H.x + side * w * 0.5f, top);
        d.startNewSubPath (e.translated (-side * R * 0.02f, -R * 0.04f));
        d.quadraticTo (e.translated (side * R * 0.05f, -R * 0.02f), e.translated (side * R * 0.03f, R * 0.04f));
        g.strokePath (d, roundStroke (R * 0.03f));
    }
}

//==============================================================================
void drawArm (juce::Graphics& g, P shoulder, P paw, P stickDir, float thickness, float alpha)
{
    // A two-part arm with a soft elbow that bends outwards and down; past full reach it
    // stretches like a rubber hose instead.
    const float reach = 255.0f;
    auto d = paw - shoulder;
    auto len = std::max (1.0f, d.getDistanceFromOrigin());
    auto mid = shoulder + d * 0.5f;
    P perp (-d.y / len, d.x / len);
    auto out = paw.x < shoulder.x ? -1.0f : 1.0f;
    if (perp.y < 0.0f) perp = -perp;                       // elbows hang down...
    perp.x += out * 0.35f;                                 // ...and out to the side
    perp = perp / std::max (0.001f, perp.getDistanceFromOrigin());
    auto bend = std::sqrt (std::max (0.0f, reach * reach * 0.25f - len * len * 0.25f)) + 10.0f;
    auto elbow = mid + perp * bend;
    auto sd = stickDir.getDistanceFromOrigin() > 0.0f ? stickDir / stickDir.getDistanceFromOrigin() : P (0.0f, 1.0f);
    auto wrist = paw - sd * std::min (34.0f, len * 0.3f);

    juce::Path arm;
    arm.startNewSubPath (shoulder);
    arm.quadraticTo (elbow, (elbow + wrist) * 0.5f);
    arm.quadraticTo (wrist, paw);
    g.setColour (c::ink.withAlpha (alpha));
    g.strokePath (arm, roundStroke (thickness));
    juce::Path sheen;
    auto o = P (-thickness * 0.2f, -thickness * 0.22f);
    sheen.startNewSubPath (shoulder + o);
    sheen.quadraticTo (elbow + o, (elbow + wrist) * 0.5f + o);
    sheen.quadraticTo (wrist + o, paw + o * 0.7f);
    g.setColour (juce::Colour (0xff4a3f4e).withAlpha (0.5f * alpha));
    g.strokePath (sheen, roundStroke (thickness * 0.2f));
}

void drawStick (juce::Graphics& g, P butt, P tip, float t, float alpha)
{
    auto d = tip - butt;
    auto len = d.getDistanceFromOrigin();
    if (len < 1.0f)
        return;
    auto u = d / len;
    P n (-u.y, u.x);
    juce::Path s;
    s.startNewSubPath (butt + n * (t * 0.5f));
    s.lineTo (tip + n * (t * 0.3f));
    s.lineTo (tip - n * (t * 0.3f));
    s.lineTo (butt - n * (t * 0.5f));
    s.closeSubPath();
    g.setGradientFill (juce::ColourGradient (juce::Colour (0xfff6dca8).withAlpha (alpha), butt.x + n.x * t, butt.y + n.y * t,
                                             juce::Colour (0xffcf9550).withAlpha (alpha), butt.x - n.x * t, butt.y - n.y * t, false));
    g.fillPath (s);
    g.setColour (c::ink.withAlpha (alpha));
    g.strokePath (s, roundStroke (1.6f));
    g.setColour (juce::Colour (0xffe8c38a).withAlpha (alpha));
    g.fillEllipse (tip.x - t * 0.42f, tip.y - t * 0.42f, t * 0.84f, t * 0.84f);
    g.setColour (c::ink.withAlpha (alpha));
    g.drawEllipse (tip.x - t * 0.42f, tip.y - t * 0.42f, t * 0.84f, t * 0.84f, 1.4f);
}

void drawPaw (juce::Graphics& g, P centre, float r, float alpha)
{
    g.setGradientFill (juce::ColourGradient (juce::Colour (0xff3a3138).withAlpha (alpha), centre.x - r * 0.4f, centre.y - r * 0.5f,
                                             c::ink.withAlpha (alpha), centre.x + r * 0.5f, centre.y + r * 0.6f, false));
    g.fillEllipse (centre.x - r, centre.y - r, r * 2.0f, r * 2.0f);
    g.setColour (juce::Colours::white.withAlpha (0.18f * alpha));
    g.fillEllipse (centre.x - r * 0.55f, centre.y - r * 0.65f, r * 0.55f, r * 0.35f);
}

//==============================================================================
Wrap wrapForVariant (const juce::String& name, PieceType type)
{
    auto n = name.toLowerCase();
    if (n.contains ("brass") || n.contains ("bronze"))                       return Wrap::Brass;
    if (n.contains ("maple") || n.contains ("birch"))                        return Wrap::Maple;
    if (n.contains ("piccolo") || n.contains ("steel") || n.contains ("chrome") || n.contains ("alu")) return Wrap::Chrome;
    if (n.contains ("wood") || n.contains ("walnut") || n.contains ("vintage")) return type == PieceType::Snare ? Wrap::Walnut : Wrap::PurpleSparkle;
    if (n.contains ("black"))                                                return Wrap::Black;
    return type == PieceType::Snare ? Wrap::Chrome : Wrap::PurpleSparkle;
}

void drawDrum (juce::Graphics& g, P T, float r, float shellH, Wrap wrap, PieceType type, const DrumState& st, float floorY)
{
    r *= 1.0f + 0.035f * st.pulse;
    auto eh = r * 0.36f;
    auto wc = wrapColours (wrap);
    auto bottom = T.y + shellH;
    auto isFloor = type == PieceType::Tom && floorY - bottom < 140.0f;

    if (isFloor || type == PieceType::Snare)
    {
        floorShadow (g, { T.x, floorY }, r * 1.25f);
        auto legTop = T.y + shellH * (type == PieceType::Snare ? 1.0f : 0.55f);
        for (auto side : { -1.0f, 1.0f })
            chromeLine (g, { T.x + side * r * (type == PieceType::Snare ? 0.45f : 0.9f), legTop },
                           { T.x + side * r * (type == PieceType::Snare ? 0.85f : 1.05f), floorY }, 4.0f);
        if (type == PieceType::Snare)
            chromeLine (g, { T.x, bottom + eh }, { T.x, floorY - 6.0f }, 4.5f);
    }

    // Shell.
    juce::Path shell;
    shell.startNewSubPath (T.x - r, T.y);
    shell.lineTo (T.x - r, bottom);
    arcTo (shell, { T.x, bottom }, r, eh, pi, 0.0f);
    shell.lineTo (T.x + r, T.y);
    shell.closeSubPath();
    g.setGradientFill (shellGradient (wc, T.x - r, T.x + r, T.y));
    g.fillPath (shell);

    if (wrap == Wrap::PurpleSparkle)
    {
        juce::Graphics::ScopedSaveState s (g);
        g.reduceClipRegion (shell);
        auto seed = (int) (T.x * 7.0f + T.y * 13.0f);
        for (int i = 0; i < (int) (r * shellH / 60.0f); ++i)
        {
            auto px = T.x - r + hash01 (seed + i * 3) * 2.0f * r;
            auto py = T.y + hash01 (seed + i * 3 + 1) * (shellH + eh);
            auto sz = 0.8f + 1.6f * hash01 (seed + i * 3 + 2);
            g.setColour (juce::Colours::white.withAlpha (0.2f + 0.45f * hash01 (seed + i * 7)));
            g.fillEllipse (px, py, sz, sz);
        }
    }
    else if (wrap == Wrap::Maple || wrap == Wrap::Walnut)
    {
        juce::Graphics::ScopedSaveState s (g);
        g.reduceClipRegion (shell);
        g.setColour (wc.dark.withAlpha (0.25f));
        for (int i = 0; i < 9; ++i)
        {
            auto yy = T.y + (shellH + eh) * (float) i / 9.0f + 3.0f;
            g.drawLine (T.x - r, yy, T.x + r, yy + 2.0f, 0.8f);
        }
    }

    // Lugs and tension rods across the front.
    for (float a : { 0.12f, 0.32f, 0.5f, 0.68f, 0.88f })
    {
        auto theta = pi * a;
        auto lx = T.x + r * std::cos (theta);
        auto depth = std::sin (theta);
        auto lugH = std::max (8.0f, shellH * 0.32f);
        auto lug = juce::Rectangle<float> (r * 0.085f, lugH).withCentre ({ lx, T.y + eh * depth * 0.5f + shellH * 0.5f });
        g.setColour (c::ink);
        g.fillRoundedRectangle (lug.expanded (1.2f), 3.0f);
        g.setGradientFill (juce::ColourGradient (juce::Colours::white, lug.getX(), lug.getY(), c::chrome.darker (0.3f), lug.getRight(), lug.getY(), false));
        g.fillRoundedRectangle (lug, 3.0f);
        g.setColour (c::chrome.darker (0.4f));
        g.drawLine (lx, T.y + eh * depth, lx, lug.getY(), 1.3f);
        g.drawLine (lx, lug.getBottom(), lx, bottom + eh * depth, 1.3f);
    }
    if (type == PieceType::Snare)
    {
        auto strainer = juce::Rectangle<float> (r * 0.16f, shellH * 0.45f).withCentre ({ T.x + r * 0.62f, T.y + shellH * 0.55f + eh * 0.6f });
        g.setColour (c::ink);
        g.fillRoundedRectangle (strainer.expanded (1.2f), 2.0f);
        g.setColour (c::chrome);
        g.fillRoundedRectangle (strainer, 2.0f);
    }

    // Bottom hoop.
    juce::Path hoopBottom;
    hoopBottom.startNewSubPath (T.x - r, bottom);
    arcTo (hoopBottom, { T.x, bottom }, r, eh, pi, 0.0f);
    g.setColour (c::ink);
    g.strokePath (hoopBottom, roundStroke (r * 0.075f + 2.4f));
    g.setColour (c::chrome);
    g.strokePath (hoopBottom, roundStroke (r * 0.075f));

    g.setColour (c::ink);
    g.strokePath (shell, roundStroke (2.4f));

    // Head.
    auto head = ellipseAt (T, r * 0.96f, eh * 0.96f);
    juce::ColourGradient hg (juce::Colours::white, T.x - r * 0.25f, T.y - eh * 0.4f, juce::Colour (0xffe7dfcd), T.x + r, T.y + eh, true);
    g.setGradientFill (hg);
    g.fillPath (head);
    if (st.flash > 0.001f)
    {
        g.setColour (juce::Colours::white.withAlpha (juce::jlimit (0.0f, 1.0f, st.flash) * 0.85f));
        g.fillPath (head);
        g.setColour (c::hot.withAlpha (st.flash * 0.35f));
        g.strokePath (ellipseAt (T, r * 1.05f, eh * 1.08f), juce::PathStrokeType (5.0f));
    }
    if (st.ripple >= 0.0f && st.ripple < 1.0f)
    {
        auto rr = 0.15f + 0.85f * st.ripple;
        g.setColour (c::hot.withAlpha ((1.0f - st.ripple) * 0.75f * st.rippleStrength));
        g.strokePath (ellipseAt (T, r * 0.92f * rr, eh * 0.92f * rr), juce::PathStrokeType (2.5f));
    }

    // Top hoop.
    auto hoop = ellipseAt (T, r, eh);
    g.setColour (c::ink);
    g.strokePath (hoop, juce::PathStrokeType (r * 0.07f + 2.6f));
    g.setGradientFill (juce::ColourGradient (juce::Colours::white, T.x - r, T.y, c::chrome.darker (0.25f), T.x + r, T.y, false));
    g.strokePath (hoop, juce::PathStrokeType (r * 0.07f));
}

void drawHeart (juce::Graphics& g, juce::Rectangle<float> r, juce::Colour fill, juce::Colour outline, float ow)
{
    auto p = heartPath (r);
    g.setColour (fill);
    g.fillPath (p);
    g.setColour (outline);
    g.strokePath (p, roundStroke (ow));
}

juce::Path heartPath (juce::Rectangle<float> r)
{
    juce::Path p;
    for (int i = 0; i <= 120; ++i)
    {
        auto t = 2.0f * pi * (float) i / 120.0f;
        auto x = 16.0f * std::pow (std::sin (t), 3.0f);
        auto y = -(13.0f * std::cos (t) - 5.0f * std::cos (2.0f * t) - 2.0f * std::cos (3.0f * t) - std::cos (4.0f * t));
        auto px = r.getCentreX() + x / 34.0f * r.getWidth();
        auto py = r.getY() + (y + 12.5f) / 30.0f * r.getHeight();
        if (i == 0) p.startNewSubPath (px, py);
        else        p.lineTo (px, py);
    }
    p.closeSubPath();
    return p;
}

void drawHeartLogo (juce::Graphics& g, juce::Rectangle<float> r, const juce::String& text)
{
    auto p = heartPath (r);
    g.setColour (juce::Colours::black.withAlpha (0.18f));
    g.fillPath (p, juce::AffineTransform::translation (0.0f, r.getHeight() * 0.04f));
    g.setGradientFill (juce::ColourGradient (c::heart.brighter (0.15f), r.getX(), r.getY(), c::heartDark, r.getRight(), r.getBottom(), false));
    g.fillPath (p);
    g.setColour (juce::Colours::white.withAlpha (0.28f));
    g.fillEllipse (r.getX() + r.getWidth() * 0.14f, r.getY() + r.getHeight() * 0.1f, r.getWidth() * 0.18f, r.getHeight() * 0.12f);
    g.setColour (c::ink);
    g.strokePath (p, roundStroke (std::max (2.0f, r.getWidth() * 0.035f)));
    auto tr = juce::Rectangle<float> (r.getWidth() * 0.78f, r.getHeight() * 0.36f).withCentre ({ r.getCentreX(), r.getY() + r.getHeight() * 0.44f });
    g.setColour (c::cream);
    g.setFont (theme::display (tr.getHeight()));
    g.drawFittedText (text, tr.toNearestInt(), juce::Justification::centred, 1, 0.6f);
}

void drawKick (juce::Graphics& g, P C, float r, Wrap wrap, const DrumState& st, float floorY, const juce::String& logo)
{
    floorShadow (g, { C.x, floorY }, r * 1.2f, 0.25f);
    for (auto side : { -1.0f, 1.0f })
        chromeLine (g, { C.x + side * r * 0.72f, C.y + r * 0.5f }, { C.x + side * r * 1.12f, floorY + 2.0f }, 4.5f);

    juce::Graphics::ScopedSaveState save (g);
    auto s = 1.0f + 0.045f * st.pulse;
    g.addTransform (juce::AffineTransform::scale (s, s, C.x, C.y));
    auto wc = wrapColours (wrap);

    // Shell edge, hoop, head.
    g.setGradientFill (shellGradient (wc, C.x - r, C.x + r, C.y));
    g.fillEllipse (C.x - r, C.y - r, r * 2.0f, r * 2.0f);
    auto hoopR = r * 0.94f;
    g.setGradientFill (juce::ColourGradient (juce::Colours::white, C.x - r, C.y - r, c::chrome.darker (0.35f), C.x + r, C.y + r, false));
    g.fillEllipse (C.x - hoopR, C.y - hoopR, hoopR * 2.0f, hoopR * 2.0f);
    auto headR = r * 0.86f;
    juce::ColourGradient hg (juce::Colour (0xfffffaea), C.x - r * 0.3f, C.y - r * 0.35f, juce::Colour (0xffeadbb8), C.x + r, C.y + r, true);
    g.setGradientFill (hg);
    g.fillEllipse (C.x - headR, C.y - headR, headR * 2.0f, headR * 2.0f);
    g.setColour (c::ink);
    g.drawEllipse (C.x - headR, C.y - headR, headR * 2.0f, headR * 2.0f, 2.0f);

    // Claws round the hoop.
    for (int i = 0; i < 10; ++i)
    {
        auto a = 2.0f * pi * ((float) i + 0.5f) / 10.0f;
        auto p = P (C.x + std::cos (a) * r * 0.9f, C.y + std::sin (a) * r * 0.9f);
        juce::Path claw;
        claw.addRoundedRectangle (-4.0f, -r * 0.07f, 8.0f, r * 0.14f, 2.5f);
        claw.applyTransform (juce::AffineTransform::rotation (a + pi * 0.5f).translated (p.x, p.y));
        g.setColour (c::ink);
        g.strokePath (claw, juce::PathStrokeType (2.0f));
        g.setColour (c::chrome);
        g.fillPath (claw);
    }

    // Logo, with a bounce.
    auto lb = 1.0f + 0.06f * st.pulse;
    auto heartBox = juce::Rectangle<float> (r * 1.12f * lb, r * 0.98f * lb).withCentre ({ C.x, C.y - r * 0.04f });
    drawHeartLogo (g, heartBox, logo);
    g.setColour (c::ink.withAlpha (0.75f));
    g.setFont (theme::title (r * 0.14f));
    g.drawText ("DRUMS  vol. one", juce::Rectangle<float> (r * 1.2f, r * 0.16f).withCentre ({ C.x, C.y + r * 0.62f }), juce::Justification::centred);

    // Port hole.
    auto port = P (C.x + r * 0.5f, C.y + r * 0.42f);
    g.setColour (c::chrome);
    g.fillEllipse (port.x - r * 0.1f, port.y - r * 0.1f, r * 0.2f, r * 0.2f);
    g.setColour (c::ink);
    g.fillEllipse (port.x - r * 0.08f, port.y - r * 0.08f, r * 0.16f, r * 0.16f);

    if (st.flash > 0.001f)
    {
        g.setColour (juce::Colours::white.withAlpha (st.flash * 0.35f));
        g.fillEllipse (C.x - headR, C.y - headR, headR * 2.0f, headR * 2.0f);
    }
    if (st.ripple >= 0.0f && st.ripple < 1.0f)
    {
        auto rr = headR * (0.3f + 0.7f * st.ripple);
        g.setColour (c::hot.withAlpha ((1.0f - st.ripple) * 0.6f * st.rippleStrength));
        g.drawEllipse (C.x - rr, C.y - rr, rr * 2.0f, rr * 2.0f, 3.0f);
    }
    g.setColour (c::ink);
    g.drawEllipse (C.x - r, C.y - r, r * 2.0f, r * 2.0f, 3.0f);
}

namespace
{
void drawDisc (juce::Graphics& g, P C, float r, float angle, float squash, PieceType type, const DrumState& st, bool bellDown)
{
    juce::Graphics::ScopedSaveState save (g);
    g.addTransform (juce::AffineTransform::rotation (angle, C.x, C.y));
    auto ry = r * 0.19f * squash;
    auto china = type == PieceType::China;
    auto light = china ? juce::Colour (0xfff0b15a) : c::bronze.brighter (0.35f);
    auto mid = china ? juce::Colour (0xffc77a2a) : c::bronze;
    auto dark = china ? juce::Colour (0xff7a3d10) : c::bronzeDark;

    // Thickness.
    g.setColour (c::ink);
    g.fillEllipse (C.x - r - 1.5f, C.y - ry + 1.5f, r * 2.0f + 3.0f, ry * 2.0f + 3.0f);
    g.setColour (dark);
    g.fillEllipse (C.x - r, C.y - ry + 2.5f, r * 2.0f, ry * 2.0f);

    juce::ColourGradient grad (light, C.x - r * 0.6f, C.y - ry, dark, C.x + r * 0.8f, C.y + ry, false);
    grad.addColour (0.45, mid);
    g.setGradientFill (grad);
    g.fillEllipse (C.x - r, C.y - ry, r * 2.0f, ry * 2.0f);

    // Lathe rings.
    for (int k = 1; k <= 7; ++k)
    {
        auto f = (float) k / 8.0f;
        g.setColour (dark.withAlpha (0.18f));
        g.drawEllipse (C.x - r * f, C.y - ry * f, r * 2.0f * f, ry * 2.0f * f, 0.9f);
    }
    if (china)
    {
        g.setColour (dark.withAlpha (0.55f));
        g.drawEllipse (C.x - r * 0.86f, C.y - ry * 0.86f, r * 1.72f, ry * 1.72f, r * 0.05f);
    }

    // Shine.
    juce::Path shine;
    shine.startNewSubPath (C.x - r * 0.75f, C.y - ry * 0.25f);
    arcTo (shine, C, r * 0.72f, ry * 0.72f, pi * 1.08f, pi * 1.42f, 10);
    g.setColour (juce::Colours::white.withAlpha (0.45f));
    g.strokePath (shine, roundStroke (std::max (1.5f, ry * 0.18f)));

    // Bell.
    auto br = r * (type == PieceType::Ride ? 0.26f : 0.18f);
    auto bellY = C.y + (bellDown ? ry * 0.15f : -ry * 0.2f);
    juce::Path bell;
    bell.addEllipse (C.x - br, bellY - br * 0.42f, br * 2.0f, br * 0.84f);
    g.setGradientFill (juce::ColourGradient (light.brighter (0.2f), C.x - br, bellY - br * 0.4f, dark, C.x + br, bellY + br * 0.4f, false));
    g.fillPath (bell);
    g.setColour (dark.darker (0.3f));
    g.strokePath (bell, juce::PathStrokeType (1.2f));

    if (st.flash > 0.001f)
    {
        g.setColour (juce::Colour (0xfffff3c4).withAlpha (st.flash * 0.6f));
        g.fillEllipse (C.x - r, C.y - ry, r * 2.0f, ry * 2.0f);
    }
    g.setColour (c::ink);
    g.drawEllipse (C.x - r, C.y - ry, r * 2.0f, ry * 2.0f, 1.8f);
}

void stand (juce::Graphics& g, P top, float floorY, float spread = 34.0f, float poleX = -1.0f)
{
    // Straight stand, or a boom stand when the pole stands somewhere else.
    auto px = poleX < 0.0f ? top.x : poleX;
    floorShadow (g, { px, floorY }, spread * 1.6f, 0.16f);
    auto foot = floorY - 34.0f;
    auto joint = poleX < 0.0f ? top : P (px, top.y + 70.0f);
    if (poleX >= 0.0f)
        chromeLine (g, joint, top, 3.4f);
    chromeLine (g, joint, { px, foot }, 4.0f);
    chromeLine (g, { px, foot }, { px - spread, floorY }, 3.2f);
    chromeLine (g, { px, foot }, { px + spread, floorY }, 3.2f);
    chromeLine (g, { px, foot }, { px + 4.0f, floorY + 4.0f }, 3.2f);
}
} // namespace

void drawCymbal (juce::Graphics& g, P C, float r, float angle, float squash, PieceType type, const DrumState& st, float floorY, bool withStand, float poleX)
{
    if (withStand)
        stand (g, C, floorY, 34.0f, poleX);
    drawDisc (g, C, r, angle, squash, type, st, false);
}

void drawHiHat (juce::Graphics& g, P C, float r, float gap, float angle, const DrumState& st, float floorY, float press)
{
    stand (g, C, floorY - 14.0f, 30.0f);

    // Pedal with a panda foot on it.
    auto pivot = P (C.x - 22.0f, floorY - 4.0f);
    juce::Path pedal;
    pedal.addRoundedRectangle (0.0f, -5.0f, 58.0f, 10.0f, 4.0f);
    auto tiltAngle = -0.32f * (1.0f - press);
    pedal.applyTransform (juce::AffineTransform::rotation (tiltAngle).translated (pivot.x, pivot.y));
    g.setColour (c::ink);
    g.strokePath (pedal, juce::PathStrokeType (2.6f));
    g.setColour (c::chrome.darker (0.15f));
    g.fillPath (pedal);
    juce::Path foot;
    foot.addEllipse (8.0f, -30.0f, 56.0f, 30.0f);
    foot.applyTransform (juce::AffineTransform::rotation (tiltAngle).translated (pivot.x, pivot.y));
    g.setColour (c::ink);
    g.fillPath (foot);
    g.setColour (juce::Colours::white.withAlpha (0.15f));
    g.fillPath (foot, juce::AffineTransform::scale (0.4f, 0.3f, foot.getBounds().getCentreX() - 8.0f, foot.getBounds().getCentreY() - 6.0f));

    drawDisc (g, C.translated (0.0f, gap * 0.5f), r, angle * 0.3f, 1.0f, PieceType::HiHat, {}, true);
    // Clutch rod.
    chromeLine (g, C.translated (0.0f, -gap * 0.5f - 16.0f), C.translated (0.0f, gap * 0.5f), 2.5f);
    drawDisc (g, C.translated (0.0f, -gap * 0.5f), r, angle, 1.0f, PieceType::HiHat, st, false);
    auto clutch = juce::Rectangle<float> (14.0f, 9.0f).withCentre (C.translated (0.0f, -gap * 0.5f - 8.0f));
    g.setColour (c::ink);
    g.fillRoundedRectangle (clutch.expanded (1.2f), 2.0f);
    g.setColour (c::chrome);
    g.fillRoundedRectangle (clutch, 2.0f);
}

//==============================================================================
void drawSparkle (juce::Graphics& g, P c0, float s, float alpha, juce::Colour col)
{
    juce::Path p;
    p.startNewSubPath (c0.x, c0.y - s);
    p.quadraticTo (c0.x + s * 0.12f, c0.y - s * 0.12f, c0.x + s, c0.y);
    p.quadraticTo (c0.x + s * 0.12f, c0.y + s * 0.12f, c0.x, c0.y + s);
    p.quadraticTo (c0.x - s * 0.12f, c0.y + s * 0.12f, c0.x - s, c0.y);
    p.quadraticTo (c0.x - s * 0.12f, c0.y - s * 0.12f, c0.x, c0.y - s);
    p.closeSubPath();
    g.setColour (col.withAlpha (alpha));
    g.fillPath (p);
}

void drawComicBurst (juce::Graphics& g, const juce::String& text, P centre, float scale, float alpha, float rotation, juce::Colour fill)
{
    if (alpha <= 0.01f || scale <= 0.01f)
        return;
    juce::Graphics::ScopedSaveState save (g);
    g.addTransform (juce::AffineTransform::rotation (rotation).scaled (scale).translated (centre.x, centre.y));
    juce::Path burst;
    const int spikes = 14;
    for (int i = 0; i < spikes * 2; ++i)
    {
        auto a = pi * (float) i / (float) spikes;
        auto rad = (i % 2 == 0) ? 74.0f + 10.0f * hash01 (i) : 50.0f;
        auto p = P (std::cos (a) * rad * 1.35f, std::sin (a) * rad * 0.85f);
        if (i == 0) burst.startNewSubPath (p);
        else        burst.lineTo (p);
    }
    burst.closeSubPath();
    g.setColour (c::ink.withAlpha (alpha));
    g.fillPath (burst, juce::AffineTransform::translation (4.0f, 5.0f));
    g.setColour (fill.withAlpha (alpha));
    g.fillPath (burst);
    g.setColour (c::ink.withAlpha (alpha));
    g.strokePath (burst, roundStroke (4.0f));
    theme::drawTextOutlined (g, text, { -95.0f, -34.0f, 190.0f, 68.0f }, theme::display (58.0f),
                             juce::Colours::white.withAlpha (alpha), c::ink.withAlpha (alpha), 7.0f);
}

void drawStage (juce::Graphics& g, juce::Rectangle<float> a)
{
    // Pink wall with a soft spotlight.
    g.setGradientFill (juce::ColourGradient (juce::Colour (0xfff8c6e0), a.getCentreX(), a.getY(), c::pinkDeep, a.getCentreX(), a.getBottom(), false));
    g.fillRect (a);
    g.setGradientFill (juce::ColourGradient (juce::Colours::white.withAlpha (0.38f), 640.0f, 300.0f,
                                             juce::Colours::white.withAlpha (0.0f), 640.0f + 620.0f, 300.0f, true));
    g.fillRect (a);

    // Halftone dots fading in towards the edges.
    for (float y = 10.0f; y < 640.0f; y += 22.0f)
        for (float x = 10.0f + std::fmod (y, 44.0f) * 0.5f; x < 1280.0f; x += 22.0f)
        {
            auto d = P (x, y).getDistanceFrom ({ 640.0f, 330.0f }) / 720.0f;
            auto t = juce::jlimit (0.0f, 1.0f, (d - 0.55f) / 0.45f);
            if (t <= 0.0f) continue;
            g.setColour (c::hot.withAlpha (0.13f * t));
            auto rr = 1.5f + 2.5f * t;
            g.fillEllipse (x - rr, y - rr, rr * 2.0f, rr * 2.0f);
        }

    // Light beams.
    for (auto bx : { 330.0f, 950.0f })
    {
        juce::Path beam;
        beam.startNewSubPath (bx - 30.0f, -10.0f);
        beam.lineTo (bx + 30.0f, -10.0f);
        beam.lineTo (bx + (bx < 640.0f ? 330.0f : -30.0f) + 140.0f, 700.0f);
        beam.lineTo (bx + (bx < 640.0f ? 30.0f : -330.0f) - 140.0f, 700.0f);
        beam.closeSubPath();
        g.setGradientFill (juce::ColourGradient (juce::Colours::white.withAlpha (0.16f), bx, 0.0f, juce::Colours::white.withAlpha (0.0f), bx, 640.0f, false));
        g.fillPath (beam);
    }

    // String of heart lights.
    juce::Path wire;
    wire.startNewSubPath (-10.0f, 30.0f);
    wire.quadraticTo (640.0f, 120.0f, 1290.0f, 30.0f);
    g.setColour (c::ink.withAlpha (0.55f));
    g.strokePath (wire, juce::PathStrokeType (2.0f));
    const juce::Colour bulbs[] = { c::heart, c::gold, c::mint, c::hot };
    for (int i = 0; i < 17; ++i)
    {
        auto t = ((float) i + 0.5f) / 17.0f;
        auto x = -10.0f + 1300.0f * t;
        auto y = (1.0f - t) * (1.0f - t) * 30.0f + 2.0f * (1.0f - t) * t * 120.0f + t * t * 30.0f;
        auto col = bulbs[i % 4];
        g.setGradientFill (juce::ColourGradient (col.withAlpha (0.55f), x, y + 12.0f, col.withAlpha (0.0f), x + 34.0f, y + 12.0f, true));
        g.fillEllipse (x - 34.0f, y - 22.0f, 68.0f, 68.0f);
        drawHeart (g, { x - 11.0f, y + 2.0f, 22.0f, 20.0f }, col, c::ink, 2.0f);
    }

    // Bamboo at both sides.
    auto bamboo = [&g] (float x, float top, float w, float tint)
    {
        auto green = juce::Colour (0xff59b85a).withMultipliedBrightness (tint);
        for (float y = top; y < 700.0f; y += 78.0f)
        {
            auto seg = juce::Rectangle<float> (x - w * 0.5f, y, w, 74.0f);
            g.setGradientFill (juce::ColourGradient (green.brighter (0.35f), seg.getX(), y, green.darker (0.35f), seg.getRight(), y, false));
            g.fillRoundedRectangle (seg, w * 0.3f);
            g.setColour (c::ink.withAlpha (0.85f));
            g.drawRoundedRectangle (seg, w * 0.3f, 2.0f);
            g.setColour (green.darker (0.5f));
            g.fillRoundedRectangle (seg.withHeight (6.0f).translated (-2.0f, 72.0f).withWidth (w + 4.0f), 3.0f);
        }
        for (int i = 0; i < 4; ++i)
        {
            auto ly = top + 60.0f + (float) i * 130.0f;
            auto dir = (i % 2 == 0) ? 1.0f : -1.0f;
            juce::Path leaf;
            leaf.startNewSubPath (0.0f, 0.0f);
            leaf.quadraticTo (34.0f, -16.0f, 78.0f, 0.0f);
            leaf.quadraticTo (34.0f, 14.0f, 0.0f, 0.0f);
            leaf.closeSubPath();
            leaf.applyTransform (juce::AffineTransform::rotation (dir > 0 ? -0.35f : pi + 0.35f).translated (x + dir * w * 0.4f, ly));
            g.setColour (juce::Colour (0xff4fae4c).withMultipliedBrightness (tint));
            g.fillPath (leaf);
            g.setColour (c::ink.withAlpha (0.85f));
            g.strokePath (leaf, juce::PathStrokeType (1.8f));
        }
    };
    bamboo (38.0f, 140.0f, 26.0f, 0.85f);
    bamboo (92.0f, 230.0f, 22.0f, 1.0f);
    bamboo (1242.0f, 160.0f, 26.0f, 0.85f);
    bamboo (1190.0f, 250.0f, 22.0f, 1.0f);

    // Floor and a rug with a border.
    g.setGradientFill (juce::ColourGradient (juce::Colour (0xffd77ab0), 640.0f, 640.0f, juce::Colour (0xffb9518f), 640.0f, 736.0f, false));
    g.fillRect (0.0f, 655.0f, 1280.0f, 90.0f);
    auto rug = juce::Rectangle<float> (130.0f, 640.0f, 1020.0f, 112.0f);
    g.setColour (juce::Colour (0xff9c3f78));
    g.fillEllipse (rug.translated (0.0f, 5.0f));
    g.setColour (juce::Colour (0xffc4579a));
    g.fillEllipse (rug);
    g.setColour (c::cream.withAlpha (0.8f));
    g.drawEllipse (rug.reduced (18.0f, 10.0f), 3.0f);
    g.setColour (c::gold.withAlpha (0.7f));
    g.drawEllipse (rug.reduced (30.0f, 17.0f), 2.0f);
}

void drawPandaBadge (juce::Graphics& g, juce::Rectangle<float> r)
{
    // The art's happy head when there is one, fitted to the badge.
    if (auto& skin = Skin::get(); skin.isLoaded())
    {
        auto head = skin.sprite (skin.at ("panda/badge").toString());
        if (head.isValid())
        {
            auto all = head.bounds;
            auto size = std::min (r.getWidth(), r.getHeight()) * 0.9f;
            auto scale = size / std::max (all.getWidth(), all.getHeight());
            auto t = juce::AffineTransform::translation (-all.getCentreX(), -all.getCentreY()).scaled (scale)
                         .translated (r.getCentreX(), r.getCentreY());
            juce::Graphics::ScopedSaveState save (g);
            g.setImageResamplingQuality (juce::Graphics::highResamplingQuality);
            skin.draw (g, head, t);
            return;
        }
    }
    PandaPose pose;
    auto size = std::min (r.getWidth(), r.getHeight());
    pose.radius = size * 0.36f;
    pose.head = r.getCentre().translated (0.0f, size * 0.07f);
    pose.mouthOpen = 0.45f;
    drawPandaHead (g, pose);
}
} // namespace pd::art
