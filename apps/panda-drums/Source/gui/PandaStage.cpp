#include "PandaStage.h"
#include "Theme.h"
#include "UiKit.h"

using namespace pd;
namespace colour = pd::theme::colour;

namespace
{
constexpr float floorY = 690.0f;
constexpr double liveStroke = 0.035;    // how long a stick takes to land a hit played live (s)
constexpr float strokeDwell = 0.016f;   // how long a stick sits on the head (a frame: the eye needs to see it land)
constexpr float whipPower = 2.4f;       // a stroke's fall: height (1 - u^p), slow at the top, fastest as it lands
// How fast a stick comes off the head (heights a second): a loud one bounces back hard.
float reboundSpeed (float vel) { return 0.6f + 3.0f * (0.12f + 0.98f * std::pow (juce::jlimit (0.0f, 1.0f, vel / 127.0f), 1.8f)); }
// The art's sticks are longer than the drawn ones were; the rig's says how long its is.
float stickLength()
{
    auto& skin = pd::Skin::get();
    return skin.isLoaded() ? pd::Skin::number (skin.at ("panda/stick/length"), 132.0f) : 108.0f;
}

// How high a stroke starts for a velocity: a ghost note is a tap an inch off the head; a rock
// backbeat or crash starts with the stick up past vertical, the whole arm in it.
float strokeHeightFor (float vel)
{
    return 0.12f + 0.98f * std::pow (juce::jlimit (0.0f, 1.0f, vel / 127.0f), 1.8f);
}


float easeOutCubic (float t) { t = juce::jlimit (0.0f, 1.0f, t); return 1.0f - std::pow (1.0f - t, 3.0f); }
float easeInOut (float t)    { t = juce::jlimit (0.0f, 1.0f, t); return t * t * (3.0f - 2.0f * t); }

juce::Point<float> rotate (juce::Point<float> v, float a)
{
    return { v.x * std::cos (a) - v.y * std::sin (a), v.x * std::sin (a) + v.y * std::cos (a) };
}

juce::Point<float> normalised (juce::Point<float> v)
{
    auto l = v.getDistanceFromOrigin();
    return l > 1.0e-4f ? v / l : juce::Point<float> (0.0f, 1.0f);
}

float defaultSize (PieceType t, bool floor, int index)
{
    switch (t)
    {
        case PieceType::Kick:   return 22.0f;
        case PieceType::Snare:  return 14.0f;
        case PieceType::Tom:    return floor ? (index == 0 ? 16.0f : 14.0f) : 10.0f + 2.0f * (float) index;
        case PieceType::HiHat:  return 14.0f;
        case PieceType::Crash:  return 18.0f;
        case PieceType::Ride:   return 21.0f;
        case PieceType::China:  return 18.0f;
        case PieceType::Splash: return 10.0f;
        case PieceType::Perc:   return 8.0f;
    }
    return 12.0f;
}

const char* comicFor (PieceType t, const juce::String& artic, float vel)
{
    switch (t)
    {
        case PieceType::Kick:   return vel >= 120 ? "BOOM!" : nullptr;
        case PieceType::Snare:  return vel >= 122 ? (artic == "rim" ? "CRACK!" : "SMACK!") : nullptr;
        case PieceType::Crash:  return vel >= 116 ? "CRASH!" : nullptr;
        case PieceType::China:  return vel >= 112 ? "TSSH!" : nullptr;
        case PieceType::Splash: return vel >= 120 ? "SPLASH!" : nullptr;
        case PieceType::Tom:    return vel >= 125 ? "THUD!" : nullptr;
        case PieceType::HiHat:
        case PieceType::Ride:
        case PieceType::Perc:   return nullptr;
    }
    return nullptr;
}
} // namespace

PandaStage::PandaStage (PandaDrumsProcessor& p) : proc (p)
{
    setOpaque (true);
    hands[0].side = 0;
    hands[1].side = 1;
    if (auto& skin = Skin::get(); skin.isLoaded())
    {
        // The panda sits where it was rendered; the arms leave the sleeves where they were.
        headBase = Skin::point (skin.at ("panda/head/anchor"));
        rig = skin.at ("panda/mode").toString() == "rig";
        pandaScale = Skin::number (skin.at ("panda/scale"), 1.0f);
        centreX = Skin::number (skin.at ("stage/centre_x"), 640.0f);
        pose.radius = Skin::number (skin.at ("panda/head/radius"), pose.radius);
        if (auto* sh = skin.at ("panda/shoulders").getArray(); sh != nullptr && sh->size() == 2)
            pose.shoulderOffset = (Skin::point ((*sh)[1]) - headBase) / pose.radius;
    }
    pose.head = pose.torso = headBase;
    refreshKit();
    setLive (true);
}

void PandaStage::setLive (bool shouldRunOwnClock)
{
    live = shouldRunOwnClock;
    lastAnyHit = live ? nowSeconds() : 0.0;
    if (live)
    {
        now = lastAdvance = nowSeconds();
        clockSet = false;
        // In step with the display: every refresh (60 or 120 times a second), and the frames
        // evenly spaced however late the message thread gets to them.
        vblank = juce::VBlankAttachment (this, [this] (double t) { frame (t); });
    }
    else
        vblank = {};
}

void PandaStage::frame (double displayTime)
{
    // The display's clock, kept on the engine's (the one hits are timed on): evenly spaced frames,
    // each at the moment it's shown.
    auto wall = nowSeconds();
    auto offset = wall - displayTime;
    if (! clockSet || std::abs (offset - clockOffset) > 0.05)
        clockOffset = offset;
    else
        clockOffset += (offset - clockOffset) * 0.02;
    clockSet = true;
    auto t = std::max (now, displayTime + clockOffset);

    if (onFrame)
        onFrame (t);
    auto tr = proc.getTransport();
    setTransport (tr.bpm, tr.ppq, tr.playing);
    if (--labelCountdown <= 0)
    {
        updateLabels();
        labelCountdown = 6;
    }
    advanceTo (t);
    repaintChanged();
}

//==============================================================================
void PandaStage::refreshKit()
{
    everything = true;
    auto kit = proc.getKit();
    if (kit == nullptr)
        return;
    if (views.size() != kit->pieces.size())
    {
        views.clear();
        views.resize (kit->pieces.size());
    }
    layoutPieces();
    updateLabels();
}

void PandaStage::layoutPieces()
{
    auto kit = proc.getKit();
    std::vector<int> toms;
    for (size_t p = 0; p < kit->pieces.size(); ++p)
        if (kit->pieces[p].type == PieceType::Tom)
            toms.push_back ((int) p);
    auto tomCount = (int) toms.size();
    int floors = tomCount >= 5 ? 2 : tomCount >= 3 ? 1 : 0;
    for (auto t : toms)
        if (kit->pieces[(size_t) t].name.containsIgnoreCase ("floor"))
            floors = std::max (floors, 1);
    floors = std::min (floors, tomCount);
    auto racks = tomCount - floors;

    static const std::vector<std::vector<P>> rackSlots {
        {}, { { 640, 400 } }, { { 712, 410 }, { 565, 415 } }, { { 738, 410 }, { 640, 395 }, { 542, 410 } },
        { { 762, 412 }, { 682, 396 }, { 598, 396 }, { 518, 412 } } };
    static const std::vector<P> floorSlots { { 430, 540 }, { 322, 578 } };
    static const std::vector<P> crashSlots { { 950, 215 }, { 345, 215 }, { 1112, 300 }, { 170, 340 } };
    static const std::vector<P> rideSlots { { 300, 405 }, { 1105, 345 } };
    static const std::vector<P> chinaSlots { { 205, 255 }, { 1098, 160 } };
    static const std::vector<P> splashSlots { { 820, 150 }, { 470, 150 } };
    static const std::vector<P> percSlots { { 1095, 560 }, { 190, 565 } };
    static const std::vector<P> snareSlots { { 800, 505 }, { 1060, 575 } };

    // With the 3D art the slots come from the render, so the drums sit where they were rendered
    // and come out at the size the camera saw them at (radius in px per inch at that spot).
    auto& skin = Skin::get();
    auto skinSlot = [&skin] (const juce::String& kind, int i, P& pos, float& ppi)
    {
        auto list = skin.at ("slots/" + kind);
        if (auto* a = list.getArray(); a != nullptr && ! a->isEmpty())
        {
            auto slotVar = (*a)[std::min (i, a->size() - 1)];
            pos = Skin::point (slotVar.getProperty ("at", {}));
            ppi = Skin::number (slotVar.getProperty ("ppi", {}), ppi);
            if (i >= a->size())
                pos.y += (float) (i - a->size() + 1) * -8.0f;
        }
    };
    auto rendered = [&skin] (const juce::String& kind) { return Skin::point (skin.at ("kit/" + kind + "/anchor")); };
    auto mirrored = [this] (P renderedAt, P pos) { return (renderedAt.x - centreX) * (pos.x - centreX) < 0.0f; };
    auto squashOf = [&skin] (const juce::String& kind, const char* key, float fallback)
    {
        auto e = Skin::ellipse (skin.at ("kit/" + kind + "/" + key));
        return e.getWidth() > 0.0f ? e.getHeight() / e.getWidth() : fallback;
    };

    std::map<PieceType, int> seen;
    int tomIndex = 0;
    for (size_t p = 0; p < kit->pieces.size(); ++p)
    {
        auto& piece = kit->pieces[p];
        auto& v = views[p];
        v.piece = (int) p;
        v.type = piece.type;
        auto variant = proc.getSelectedVariant ((int) p);
        auto& var = piece.variants[(size_t) juce::jlimit (0, (int) piece.variants.size() - 1, variant)];
        v.variants = (int) piece.variants.size();
        v.wrap = art::wrapForVariant (var.name, piece.type);
        auto index = seen[piece.type]++;
        auto slot = [] (const std::vector<P>& s, int i) { return s[(size_t) std::min (i, (int) s.size() - 1)]; };

        float size = var.sizeInches;
        v.isFloor = false;
        v.eitherHand = false;
        switch (piece.type)
        {
            case PieceType::Kick:
            {
                if (size <= 0) size = defaultSize (piece.type, false, 0);
                v.pos = { 640.0f, 575.0f + (float) index * -6.0f };
                float ppi = 5.0f;
                if (skin.isLoaded())
                    skinSlot ("kick", index, v.pos, ppi);
                v.radius = size * ppi;
                break;
            }
            case PieceType::Snare:
            {
                if (size <= 0) size = defaultSize (piece.type, false, 0);
                v.pos = slot (snareSlots, index);
                float ppi = 4.0f;
                v.squash = 0.36f;
                auto depth = var.depthInches > 0 ? var.depthInches : 5.5f;
                v.shell = depth * 3.6f;
                if (skin.isLoaded())
                {
                    skinSlot ("snare", index, v.pos, ppi);
                    v.squash = squashOf ("snare", "head", 0.36f);
                    v.flip = mirrored (rendered ("snare"), v.pos);
                    auto shell0 = Skin::number (skin.at ("kit/snare/shell"), 40.0f) / Skin::number (skin.at ("kit/snare/radius"), 60.0f);
                    v.stretch = juce::jlimit (0.75f, 1.5f, 0.6f + 0.4f * depth / Skin::number (skin.at ("kit/snare/depth"), 5.5f));
                    v.shell = shell0 * size * ppi * v.stretch;
                }
                v.radius = size * ppi;
                v.slot = index;
                v.hand = rig ? (v.pos.x >= centreX ? 1 : 0) : 1;
                v.eitherHand = true;
                break;
            }
            case PieceType::Tom:
            {
                auto i = tomIndex++;
                v.isFloor = i >= (int) racks;
                if (size <= 0) size = defaultSize (piece.type, v.isFloor, v.isFloor ? i - (int) racks : i);
                if (v.isFloor)
                    v.pos = slot (floorSlots, i - (int) racks);
                else
                    v.pos = slot (rackSlots[(size_t) std::min (racks, 4)], i);
                float ppi = 4.0f;
                auto depth = var.depthInches > 0 ? var.depthInches : size * (v.isFloor ? 0.95f : 0.75f);
                v.shell = depth * (v.isFloor ? 3.0f : 3.2f);
                v.squash = 0.36f;
                if (skin.isLoaded())
                {
                    v.slot = v.isFloor ? i - (int) racks : i;
                    skinSlot (v.isFloor ? juce::String ("floor") : "rack" + juce::String (juce::jlimit (1, 4, (int) racks)), v.slot, v.pos, ppi);
                    auto kind = skinKind (v);
                    v.squash = squashOf (kind, "head", 0.36f);
                    v.flip = mirrored (rendered (kind), v.pos);
                    // Deeper or shallower than the rendered drum: stretch the shell a little.
                    auto ratio0 = Skin::number (skin.at ("kit/" + kind + "/depth"), 8.0f) / Skin::number (skin.at ("kit/" + kind + "/size"), 10.0f);
                    v.stretch = juce::jlimit (0.75f, 1.4f, 0.55f + 0.45f * (depth / size) / ratio0);
                    v.shell = Skin::number (skin.at ("kit/" + kind + "/shell"), 40.0f) / Skin::number (skin.at ("kit/" + kind + "/radius"), 48.0f)
                              * size * ppi * v.stretch;
                }
                v.radius = size * ppi;
                v.hand = v.pos.x >= centreX ? 1 : 0;
                v.eitherHand = true;
                break;
            }
            case PieceType::HiHat:
            {
                if (size <= 0) size = defaultSize (piece.type, false, 0);
                v.pos = { 945.0f, 440.0f };
                float ppi = 4.4f;
                v.squash = 0.19f;
                if (skin.isLoaded())
                {
                    skinSlot ("hihat", index, v.pos, ppi);
                    v.squash = squashOf ("hihat", "ellipse", 0.19f);
                }
                v.radius = size * ppi;
                v.hand = 1;
                break;
            }
            case PieceType::Crash:
            case PieceType::Ride:
            case PieceType::China:
            case PieceType::Splash:
            {
                if (size <= 0) size = defaultSize (piece.type, false, 0);
                auto kind = piece.type == PieceType::Crash ? "crash" : piece.type == PieceType::Ride ? "ride"
                          : piece.type == PieceType::China ? "china" : "splash";
                auto& slots = piece.type == PieceType::Crash ? crashSlots : piece.type == PieceType::Ride ? rideSlots
                            : piece.type == PieceType::China ? chinaSlots : splashSlots;
                v.pos = slot (slots, index);
                float ppi = 4.4f;
                v.squash = 0.19f;
                v.slot = index;
                if (skin.isLoaded())
                {
                    skinSlot (kind, index, v.pos, ppi);
                    v.squash = squashOf (skinKind (v), "ellipse", 0.19f);
                    v.flip = mirrored (rendered (skinKind (v)), v.pos);
                }
                v.radius = size * ppi;
                v.hand = v.pos.x >= centreX ? 1 : 0;
                break;
            }
            case PieceType::Perc:
            {
                if (size <= 0) size = defaultSize (piece.type, false, 0);
                v.pos = slot (percSlots, index);
                float ppi = 4.0f;
                v.squash = 0.36f;
                if (skin.isLoaded())
                {
                    skinSlot ("perc", index, v.pos, ppi);
                    v.squash = squashOf ("snare", "head", 0.36f);
                    v.flip = mirrored (rendered ("snare"), v.pos);
                }
                v.radius = size * ppi;
                v.shell = size * 2.4f;
                v.hand = v.pos.x >= centreX ? 1 : 0;
                break;
            }
        }

        // A piece in the same place, the same size and the same picture as one before it shares
        // that one's drum (the art has one where the kit has two): only the first is drawn.
        v.sharesWith = -1;
        if (skin.isLoaded())
            for (size_t q = 0; q < p; ++q)
                if (auto& o = views[q]; o.sharesWith < 0 && skinKind (o) == skinKind (v)
                    && o.pos.getDistanceFrom (v.pos) < 1.0f && std::abs (o.radius - v.radius) < 1.0f)
                {
                    v.sharesWith = (int) q;
                    break;
                }

        // Where a click counts as hitting it.
        if (piece.type == PieceType::Kick)
            v.hitArea = juce::Rectangle<float> (v.radius * 2.0f, v.radius * 2.0f).withCentre (v.pos);
        else if (isCymbal (piece.type))
            v.hitArea = juce::Rectangle<float> (v.radius * 2.0f, std::max (v.radius * 0.7f, v.radius * v.squash * 2.6f)).withCentre (v.pos);
        else
            v.hitArea = { v.pos.x - v.radius, v.pos.y - v.radius * v.squash, v.radius * 2.0f, v.shell + v.radius * v.squash * 2.0f };

        if (v.gap.x <= 0.0f && piece.type == PieceType::HiHat)
            v.gap.x = v.gap.target = rig ? 1.5f : 3.0f;     // the picture's hi-hat is shut
    }

    // Hands start over the snare and the hi-hat.
    for (auto& h : hands)
        if (h.piece < 0 || h.piece >= (int) views.size())
        {
            h.piece = -1;
            for (auto& v : views)
                if ((h.side == 0 && v.type == PieceType::Snare) || (h.side == 1 && v.type == PieceType::HiHat))
                    h.piece = v.piece;
            if (h.piece < 0)
                for (auto& v : views)
                    if (v.type != PieceType::Kick && v.hand == h.side)
                        h.piece = v.piece;
            if (h.piece >= 0)
                h.base = h.from = strikePoint (views[(size_t) h.piece], h.side) - stickDir (views[(size_t) h.piece], h.side) * (stickLength() * 0.92f);
        }
}

void PandaStage::updateLabels()
{
    auto kit = proc.getKit();
    if (kit == nullptr || views.size() != kit->pieces.size())
        return;
    auto key = proc.getKey();
    auto font = ui::font (11.5f);
    for (auto& v : views)
    {
        auto& piece = kit->pieces[(size_t) v.piece];
        auto variant = proc.getSelectedVariant (v.piece);
        v.variantName = piece.variants[(size_t) juce::jlimit (0, (int) piece.variants.size() - 1, variant)].name;
        v.tunable = isTunable (v.type);
        v.keyOn = ! key.isOff();
        v.inKey = proc.pitchInKey (v.piece);
        v.pitchText = v.tunable ? pitchName (proc.getPitch (v.piece)) : juce::String();

        // Tag under the drum: [<] name [>]   [v] note [^]
        auto nameW = juce::GlyphArrangement::getStringWidth (font, v.variantName) + 10.0f;
        auto arrows = v.variants > 1 ? 40.0f : 0.0f;
        auto pitchW = v.tunable ? 26.0f + 70.0f + 4.0f : 0.0f;
        auto w = nameW + arrows + pitchW + 16.0f;
        P anchor;
        if (v.type == PieceType::Kick)          anchor = { v.pos.x, v.pos.y + v.radius + 2.0f };
        else if (v.type == PieceType::HiHat)    anchor = { v.pos.x + 20.0f, v.pos.y + 36.0f };
        else if (isCymbal (v.type))             anchor = { v.pos.x, v.pos.y + v.radius * v.squash + 14.0f };
        else                                    anchor = { v.pos.x, v.pos.y + v.shell + v.radius * v.squash + 16.0f };
        anchor.y = std::min (anchor.y, designH - 26.0f);
        v.tag = juce::Rectangle<float> (w, 26.0f).withCentre (anchor);
        if (v.tag.getRight() > designW - 4.0f) v.tag.setX (designW - 4.0f - w);
        if (v.tag.getX() < 4.0f) v.tag.setX (4.0f);

        auto r = v.tag.reduced (6.0f, 2.0f);
        v.prevBtn = v.variants > 1 ? r.removeFromLeft (20.0f) : juce::Rectangle<float>();
        if (v.tunable)
        {
            v.upBtn = r.removeFromRight (20.0f);
            r.removeFromRight (70.0f);
            v.downBtn = r.removeFromRight (20.0f);
            r.removeFromRight (4.0f);
        }
        else
            v.upBtn = v.downBtn = {};
        v.nextBtn = v.variants > 1 ? r.removeFromRight (20.0f) : juce::Rectangle<float>();
    }
}

PandaStage::PieceView* PandaStage::viewFor (int piece)
{
    return juce::isPositiveAndBelow (piece, (int) views.size()) ? &views[(size_t) piece] : nullptr;
}

//==============================================================================
PandaStage::P PandaStage::strikePoint (const PieceView& v, int hand) const
{
    auto side = hand == 0 ? -1.0f : 1.0f;
    if (v.type == PieceType::HiHat)
        return v.pos.translated (side * v.radius * 0.15f - v.radius * 0.35f, -v.gap.x * 0.5f - 2.0f);
    if (isCymbal (v.type))
        // Crashes are hit on the edge nearest the panda; the ride on its bow; the bell in the middle.
        return v.pos.translated ((v.pos.x < centreX ? 1.0f : -1.0f) * v.radius * (v.type == PieceType::Ride ? 0.45f : 0.72f), 0.0f);
    return v.pos.translated (side * v.radius * 0.18f, v.radius * 0.04f);
}

PandaStage::P PandaStage::stickDir (const PieceView& v, int hand) const
{
    auto shoulder = pose.shoulder (hand == 0);
    auto towards = normalised (strikePoint (v, hand) - shoulder);
    auto down = isCymbal (v.type) ? 0.25f : 0.5f;
    return normalised (towards * (1.0f - down) + P (0.0f, down));
}

float PandaStage::liftAt (const Hand& h, double t) const
{
    auto rest = 0.55f + 0.06f * std::sin ((float) t * 2.1f + (float) h.side * 1.7f);
    auto post = rest;
    if (h.last.piece >= 0)
    {
        auto d = (float) (t - h.last.time);
        if (d >= 0.0f)
        {
            auto vel = h.last.vel / 127.0f;
            post = rest * (1.0f - std::exp (-d / 0.06f));
            if (d < 0.16f)
                post += vel * 0.45f * std::sin (d / 0.16f * juce::MathConstants<float>::pi) * std::exp (-d / 0.09f);
        }
    }

    // Wind-up before a hit that was announced early enough.
    if (h.next.piece >= 0)
    {
        auto window = (float) std::min (0.12, h.next.time - h.next.scheduled);
        auto before = (float) (h.next.time - t);
        if (window >= 0.03f && before >= 0.0f && before <= window)
        {
            auto u = before / window;                      // 1 at the start of the swing, 0 on impact
            auto top = rest + 0.3f + 0.3f * (h.next.vel / 127.0f);
            if (u > 0.45f)
                return post + (top - post) * easeOutCubic ((1.0f - u) / 0.55f);
            auto k = u / 0.45f;
            return top * k * k;
        }
    }
    return post;
}

void PandaStage::handPose (const Hand& h, double t, P& paw, P& tip) const
{
    if (t < cheerUntil)
    {
        auto side = h.side == 0 ? -1.0f : 1.0f;
        auto wave = std::sin ((float) t * 14.0f + (float) h.side * 1.6f);
        auto in = easeOutCubic ((float) (1.6 - (cheerUntil - t)) / 0.18f);
        paw = pose.shoulder (h.side == 0) + P (side * (62.0f + 10.0f * wave), -150.0f * in + 60.0f * (1.0f - in));
        tip = paw + rotate (P (side * 0.25f, -1.0f), side * 0.25f * wave) * stickLength();
        return;
    }
    if (h.piece < 0 || h.piece >= (int) views.size())
    {
        paw = pose.shoulder (h.side == 0).translated (h.side == 0 ? -20.0f : 20.0f, 90.0f);
        tip = paw + P (h.side == 0 ? -60.0f : 60.0f, -80.0f);
        return;
    }
    auto& v = views[(size_t) h.piece];
    auto dir = stickDir (v, h.side);
    auto target = strikePoint (v, h.side) - dir * (stickLength() * 0.92f);
    auto base = target;
    if (t < h.moveEnd && h.moveEnd > h.moveStart)
        base = h.from + (target - h.from) * easeOutCubic ((float) ((t - h.moveStart) / (h.moveEnd - h.moveStart)));
    auto lift = liftAt (h, t);
    auto up = dir.x >= 0.0f ? -1.0f : 1.0f;
    paw = base + P (0.0f, -lift * 30.0f) - dir * (lift * 6.0f);
    auto stickAngle = up * lift;
    if (t - h.twirlAt < 0.7)
        stickAngle += juce::MathConstants<float>::twoPi * easeInOut ((float) ((t - h.twirlAt) / 0.7)) * up;
    tip = paw + rotate (dir, stickAngle) * stickLength();
}

int PandaStage::chooseHand (const PieceView& v, double time)
{
    auto pref = v.hand;
    if (v.type == PieceType::Snare)
    {
        // Open-handed: the hand keeping time on the hi-hat or ride leaves the snare to the other one.
        auto recentOn = [&] (int h, PieceType type)
        {
            auto& H = hands[(size_t) h];
            auto check = [&] (const Strike& s) { return s.piece >= 0 && views[(size_t) s.piece].type == type && std::abs (time - s.time) < 0.6; };
            return check (H.last) || check (H.next);
        };
        // (with nothing to go by, the right: his left hand is the hi-hat's, so it's never crossed)
        pref = recentOn (1, PieceType::HiHat) ? 0 : recentOn (0, PieceType::Ride) ? 1 : 0;
    }
    auto busy = [&] (int h)
    {
        auto& H = hands[(size_t) h];
        if (H.next.piece >= 0 && H.next.piece != v.piece && std::abs (H.next.time - time) < 0.06) return true;
        if (H.last.piece >= 0 && H.last.piece != v.piece && std::abs (time - H.last.time) < 0.05) return true;
        for (auto& s : pending)
            if (s.hand == h && s.piece != v.piece && std::abs (s.time - time) < 0.06) return true;
        return false;
    };
    auto other = 1 - pref;
    if (busy (pref) && ! busy (other))
        return other;
    // Fast repeats on a drum: alternate sticking.
    if (v.eitherHand && hands[(size_t) pref].last.piece == v.piece && time - hands[(size_t) pref].last.time < 0.13 && ! busy (other))
        return other;
    if (rig && ! isCymbal (v.type) && v.type != PieceType::Kick)
    {
        // Singles around the drums (a fill): each note to the hand that didn't play the last one,
        // if it can reach (no left hand on the floor tom).
        auto latest = [&] (int h)
        {
            auto& H = hands[(size_t) h];
            auto t = H.last.piece >= 0 ? H.last.time : -10.0;
            if (H.next.piece >= 0 && H.next.time < time)
                t = std::max (t, H.next.time);
            for (auto& s : pending)
                if (s.hand == h && s.time < time)
                    t = std::max (t, s.time);
            return t;
        };
        auto reaches = [&] (int h)
        {
            P shoulder;
            if (auto* arr = Skin::get().at ("panda/shoulders").getArray(); arr != nullptr && arr->size() > h)
                shoulder = Skin::point ((*arr)[h]);
            return std::abs (v.pos.x - shoulder.x) < 250.0f;
        };
        // (not a hand keeping time on the hi-hat or ride: in a groove it stays there)
        auto keepingTime = [&] (int h)
        {
            auto& H = hands[(size_t) h];
            auto check = [&] (const Strike& s)
            {
                return s.piece >= 0 && (views[(size_t) s.piece].type == PieceType::HiHat || views[(size_t) s.piece].type == PieceType::Ride)
                    && std::abs (time - s.time) < 0.3;
            };
            if (check (H.last) || check (H.next))
                return true;
            for (auto& s : pending)
                if (s.hand == h && check (s))
                    return true;
            return false;
        };
        auto lastHand = latest (0) > latest (1) ? 0 : 1;
        if (time - std::max (latest (0), latest (1)) < 0.2 && ! busy (1 - lastHand) && reaches (1 - lastHand) && ! keepingTime (1 - lastHand))
            return 1 - lastHand;
    }
    return pref;
}

void PandaStage::hit (const HitEvent& e, double strikeTime)
{
    auto* v = viewFor (e.piece);
    if (v == nullptr)
        return;
    if ((e.flags & HitEvent::choke) != 0)
    {
        v->wobble.v *= 0.1f;
        v->wobble.x *= 0.3f;
        v->flashAmt = 0.0f;
        return;
    }
    strikeTime = std::max (strikeTime, now);
    v->last = e;
    v->lastAt = strikeTime;
    lastAnyHit = strikeTime;

    Strike s;
    s.piece = e.piece;
    s.artic = e.artic;
    s.vel = (float) e.velocityIn;
    s.time = strikeTime;
    s.scheduled = now;
    if (v->type == PieceType::Kick)
        s.hand = -1;
    else if (auto snap = proc.getSnapshot(); v->type == PieceType::HiHat && snap != nullptr
                                              && juce::isPositiveAndBelow ((int) e.piece, (int) snap->pieces.size()))
    {
        auto& rt = snap->pieces[(size_t) e.piece];
        auto pedal = rt.data != nullptr && juce::isPositiveAndBelow ((int) e.artic, (int) rt.data->artics.size())
                     && rt.data->artics[(size_t) e.artic].id == "pedal";
        s.hand = pedal ? -2 : chooseHand (*v, strikeTime);
    }
    else
        s.hand = chooseHand (*v, strikeTime);

    // Played live (no warning): the stick still makes a real stroke, a fast one, landing a couple
    // of frames after the sound, inside the time the eye and ear take as one.
    if (rig && s.hand >= 0 && strikeTime - now < liveStroke)
        s.time = now + liveStroke;

    // Two hands, and both already have something else to hit right then: this one goes unplayed
    // by a stick (it still rings and lights up).
    if (rig && s.hand >= 0)
        for (auto& p : pending)
            if (p.hand == s.hand && p.piece != s.piece && std::abs (p.time - s.time) < 0.03)
            {
                s.hand = -3;
                break;
            }

    if (s.hand >= 0)
    {
        auto& h = hands[(size_t) s.hand];
        h.twirlAt = -10.0;      // no showing off when there's work to do
        P paw, tip;
        handPose (h, now, paw, tip);
        strikeTime = s.time;
        auto early = strikeTime - now >= 0.03;
        // The rigged hand plays what it already has first; it heads for this one when that lands.
        auto queued = rig && h.next.piece >= 0 && h.next.time < strikeTime - 1.0e-6;
        if (rig && ! queued)
        {
            // From where the stick is, at the speed it's going: the stroke carries on from it.
            h.nextFromT = now;
            h.nextFromH = strokeAt (h, now);
            h.nextFromV = (h.nextFromH - strokeAt (h, now - 1.0 / 480.0)) * 480.0f;
        }
        auto atHome = rig ? homeWeight (h, now) : 0.0f;
        if (! queued && (h.piece != s.piece || atHome > 0.001f))
        {
            h.from = paw + P (0.0f, liftAt (h, now) * 30.0f);
            if (rig)
            {
                auto arm = armPose (h, now);
                h.from = arm.strikePivot;
                h.fromHeading = arm.heading;
                h.fromPitch = arm.pitch;
                h.fromLift = arm.liftScale;
            }
            h.piece = s.piece;
            h.moveStart = now;
            h.moveEnd = early ? std::min (strikeTime, std::max (now + 0.04, strikeTime - 0.02)) : now;
            if (atHome > 0.001f)
            {
                // Out of the picture's pose: it fades on the way to the stroke.
                h.homeFrom = atHome;
                h.homeFadeStart = now;
                h.homeFadeEnd = h.moveEnd;
                h.home = 0.0f;
            }
        }
        if (! early)
        {
            h.smearUntil = now + 0.045;
            h.smearPaw = paw;
            h.smearTip = tip;
        }
        if (h.next.piece < 0 || strikeTime < h.next.time)
            h.next = s;
    }
    pending.push_back (s);
}

void PandaStage::land (Hand& h, const Strike& s)
{
    if (h.last.piece >= 0 && s.time - h.last.time > 0.04 && s.time - h.last.time < 1.2)
        h.ioi = h.ioi * 0.7f + (float) (s.time - h.last.time) * 0.3f;
    h.last = s;
    h.ready = h.ready * 0.6f + strokeHeightFor (s.vel) * 0.4f;
    if (h.next.piece >= 0 && std::abs (h.next.time - s.time) < 1.0e-6)
        h.next = {};
    // The next pending strike for this hand, if any: it starts from the head, where this one left the stick.
    for (auto& p : pending)
        if (p.hand == h.side && p.time > s.time + 1.0e-6 && (h.next.piece < 0 || p.time < h.next.time))
        {
            h.next = p;
            h.nextFromT = s.time + strokeDwell;
            h.nextFromH = 0.0f;
            h.nextFromV = reboundSpeed (s.vel);
        }
    // The rigged hand sets off for its next drum now that this stroke is in.
    if (rig && h.next.piece >= 0 && h.next.piece != h.piece)
    {
        auto arm = armPose (h, s.time);
        h.from = arm.strikePivot;
        h.fromHeading = arm.heading;
        h.fromPitch = arm.pitch;
        h.fromLift = arm.liftScale;
        h.piece = h.next.piece;
        h.moveStart = s.time;
        h.moveEnd = std::max (s.time + 0.04, h.next.time - 0.02);
    }
}

void PandaStage::spawnSparkles (const PieceView& v, float vel)
{
    auto count = 2 + (int) (vel * 5.0f);
    for (int i = 0; i < count && particles.size() < 160; ++i)
    {
        Particle p;
        auto a = rng.nextFloat() * juce::MathConstants<float>::twoPi;
        p.pos = v.pos + P (std::cos (a) * v.radius, std::sin (a) * v.radius * v.squash);
        p.vel = P (std::cos (a) * 40.0f, -60.0f - 80.0f * rng.nextFloat());
        p.life = 0.35f + 0.3f * rng.nextFloat();
        p.size = 5.0f + 7.0f * rng.nextFloat() * vel;
        p.kind = 0;
        p.colour = rng.nextBool() ? juce::Colours::white : colour::gold;
        particles.push_back (p);
    }
}

void PandaStage::spawnHearts (float count)
{
    for (int i = 0; i < (int) count && particles.size() < 160; ++i)
    {
        Particle p;
        p.pos = pose.head + P ((rng.nextFloat() - 0.5f) * 220.0f, -60.0f - rng.nextFloat() * 60.0f);
        p.vel = P ((rng.nextFloat() - 0.5f) * 50.0f, -70.0f - 50.0f * rng.nextFloat());
        p.life = 0.9f + 0.5f * rng.nextFloat();
        p.size = 14.0f + 12.0f * rng.nextFloat();
        p.kind = 1;
        p.spin = (rng.nextFloat() - 0.5f) * 0.8f;
        p.colour = rng.nextBool() ? colour::heart : colour::hot;
        p.variant = rng.nextInt (3);
        particles.push_back (p);
    }
}

void PandaStage::advanceTo (double t)
{
    auto dt = (float) juce::jlimit (0.0, 0.05, t - now);
    now = t;

    // Strikes whose moment has come.
    std::stable_sort (pending.begin(), pending.end(), [] (auto& a, auto& b) { return a.time < b.time; });
    while (! pending.empty() && pending.front().time <= now)
    {
        auto s = pending.front();
        pending.erase (pending.begin());
        auto* v = viewFor (s.piece);
        if (v == nullptr)
            continue;
        auto vel = s.vel / 127.0f;
        v->flashAt = now;
        v->flashAmt = vel;
        v->rippleAt = now;
        v->rippleAmt = vel;
        v->pulse.v += 9.0f * vel;
        if (auto* shared = viewFor (v->sharesWith))
        {
            shared->flashAt = now;
            shared->flashAmt = std::max (shared->flashAmt * 0.5f, vel);
            shared->rippleAt = now;
            shared->rippleAmt = vel;
            shared->pulse.v += 9.0f * vel;
            if (isCymbal (v->type))
                shared->wobble.v += vel * 5.5f * (v->pos.x < centreX ? -1.0f : 1.0f);
        }

        juce::String articId;
        if (auto snap = proc.getSnapshot(); snap != nullptr && juce::isPositiveAndBelow (s.piece, (int) snap->pieces.size()))
            if (auto& rt = snap->pieces[(size_t) s.piece]; rt.data != nullptr && juce::isPositiveAndBelow (s.artic, (int) rt.data->artics.size()))
                articId = rt.data->artics[(size_t) s.artic].id;

        // His head leans toward what he hits and dips into it.
        headLean.v += juce::jlimit (-1.0f, 1.0f, (v->pos.x - centreX) / 420.0f) * (0.7f + 0.9f * vel);
        headDip.v += (v->type == PieceType::Kick ? 40.0f : 85.0f) * vel;

        switch (v->type)
        {
            case PieceType::Kick:
                bounce.v += 110.0f * vel;
                if (! rig)
                    shake.v += 30.0f * vel * vel;     // (the picture's room doesn't shake)
                nod.v += 2.5f * vel;
                break;
            case PieceType::Snare:
                nod.v += 3.0f * vel;
                break;
            case PieceType::HiHat:
                if (articId == "open")       { v->gap.target = 14.0f; v->press.target = 0.0f; }
                else if (articId == "half")  { v->gap.target = 7.0f;  v->press.target = 0.5f; }
                else                         { v->gap.target = 1.5f;  v->press.target = 1.0f; v->gap.x = std::min (v->gap.x, 4.0f); }
                v->wobble.v += vel * (articId == "open" ? 3.5f : 1.2f);
                break;
            case PieceType::Crash:
            case PieceType::Ride:
            case PieceType::China:
            case PieceType::Splash:
                v->wobble.v += vel * (v->type == PieceType::Ride ? 2.2f : 5.5f) * (v->pos.x < centreX ? -1.0f : 1.0f);
                spawnSparkles (*v, vel);
                if (vel > 0.85f && v->type != PieceType::Ride)
                {
                    happyUntil = now + 0.45;
                    spawnHearts (2.0f + 3.0f * vel);
                }
                break;
            case PieceType::Tom:
            case PieceType::Perc:
                nod.v += 1.5f * vel;
                break;
        }

        // Faces for the moment: surprised by the first hit after a rest, a rock-out scowl on a
        // solid china, concentration through a tom fill.
        if (now - lastLanded > 5.0)
        {
            mood = "surprised";
            moodUntil = now + 0.35;
        }
        else if (v->type == PieceType::China && vel > 0.6f && vel <= 0.85f)
        {
            // (Harder than that he laughs and throws hearts instead.)
            mood = "angry";
            moodUntil = now + 0.4;
        }
        else if (v->type == PieceType::Tom)
        {
            recentToms = now - recentTomsAt < 0.35 ? recentToms + 1 : 1;
            recentTomsAt = now;
            if (recentToms >= 3)
            {
                mood = "focused";
                moodUntil = now + 0.45;
            }
        }
        lastLanded = now;

        auto weight = v->type == PieceType::Crash || v->type == PieceType::China ? 0.55f
                    : v->type == PieceType::Snare ? 0.32f : v->type == PieceType::Kick ? 0.28f : 0.16f;
        energy += vel * weight;
        earL.v += (rng.nextFloat() - 0.3f) * vel * 5.0f;
        earR.v -= (rng.nextFloat() - 0.3f) * vel * 5.0f;
        lookX.target = juce::jlimit (-1.0f, 1.0f, (v->pos.x - centreX) / 380.0f);
        lookY.target = juce::jlimit (-0.6f, 1.0f, (v->pos.y - 205.0f) / 260.0f);

        if (s.hand >= 0)
        {
            static const bool logRig = juce::SystemStats::getEnvironmentVariable ("PD_RIG_LOG", {}).isNotEmpty();
            if (logRig && rig)
            {
                auto arm = armPose (hands[(size_t) s.hand], s.time);
                auto aim = rigStrikePoint (*v, s.hand);
                std::fprintf (stderr, "hit %.3f piece %d type %d hand %d vel %3.0f  contact %6.1f %6.1f  aim %6.1f %6.1f  off %5.1f  H %.2f  known %.0f ms\n",
                              s.time, s.piece, (int) v->type, s.hand, (double) s.vel, (double) arm.contact.x, (double) arm.contact.y,
                              (double) aim.x, (double) aim.y, (double) arm.contact.getDistanceFrom (aim), (double) arm.height,
                              (s.time - s.scheduled) * 1000.0);
            }
            land (hands[(size_t) s.hand], s);
        }
        if (s.hand >= -1 && Skin::get().isLoaded())
            strikeFx (*v, s.hand, vel);

        // Comic words for the big moments; with the panda playing a whole kit, not every kick, and
        // never over his hands: beside the kick, outside a cymbal, off to the snare's side.
        if (proc.comicFx && now - lastBurst > (rig ? 1.6 : 0.6) && (! rig || v->type != PieceType::Kick || s.vel >= 126.0f))
            if (auto* text = comicFor (v->type, articId, s.vel))
            {
                Burst b;
                b.text = text;
                b.pos = v->type == PieceType::Kick ? v->pos.translated (0.0f, -v->radius - 40.0f) : v->pos.translated (0.0f, -70.0f);
                if (rig)
                {
                    auto out = v->pos.x < centreX ? -1.0f : 1.0f;
                    b.pos = v->type == PieceType::Kick  ? v->pos.translated (-v->radius * 0.95f, v->radius * 0.35f)
                          : isCymbal (v->type)          ? v->pos.translated (out * v->radius * 0.55f, -v->radius * v->squash - 46.0f)
                                                        : v->pos.translated (-v->radius * 1.25f, v->radius * 0.6f + 30.0f);
                }
                b.pos.x = juce::jlimit (150.0f, designW - 150.0f, b.pos.x);
                b.pos.y = juce::jlimit (80.0f, designH - 120.0f, b.pos.y);
                b.at = now;
                b.rot = (rng.nextFloat() - 0.5f) * 0.3f;
                b.colour = v->type == PieceType::Kick ? colour::gold : v->type == PieceType::Snare ? colour::hot : colour::mint;
                bursts.push_back (b);
                lastBurst = now;
            }
    }

    // Back to sitting when the hands have nothing to do; old effects go.
    if (now > poseHold && poseName != "idle")
    {
        lastPoseName = poseName;
        poseName = "idle";
        poseAt = now;
    }
    fx.erase (std::remove_if (fx.begin(), fx.end(), [this] (auto& f) { return now - f.at > f.life; }), fx.end());

    // Springs.
    for (auto& v : views)
    {
        v.pulse.step (dt, 30.0f, 0.35f);
        auto zeta = v.type == PieceType::Crash || v.type == PieceType::Splash || v.type == PieceType::China ? 0.08f
                  : v.type == PieceType::Ride ? 0.14f : 0.3f;
        v.wobble.step (dt, juce::MathConstants<float>::twoPi * 3.2f, zeta);
        // With his hands elsewhere (on the ride, round the toms) his left foot keeps time on the
        // hi-hat pedal, with his head: the top cymbal lifts a little through the beat and chicks
        // shut on it.
        if (rig && v.type == PieceType::HiHat && tPlaying && now - v.lastAt > 0.8)
        {
            auto beats = tBpm > 130.0 ? tPpq * 0.5 : tPpq;
            auto frac = (float) (beats - std::floor (beats));
            auto up = frac < 0.7f ? std::sin (frac / 0.7f * juce::MathConstants<float>::halfPi)
                                  : std::cos ((frac - 0.7f) / 0.3f * juce::MathConstants<float>::halfPi);
            v.gap.target = 1.5f + 4.0f * up * up;
            v.press.target = 1.0f - 0.4f * up;
        }
        v.gap.step (dt, 70.0f, 0.85f);
        v.press.step (dt, 45.0f, 0.8f);
        if (v.type == PieceType::HiHat && v.press.target > 0.9f && now - v.lastAt > 0.25)
            v.press.target = 0.85f;
    }
    bounce.step (dt, 16.0f, 0.32f);
    nod.step (dt, 13.0f, 0.4f);
    headLean.step (dt, 8.5f, 0.42f);
    headDip.step (dt, 15.0f, 0.45f);
    if (rig)
    {
        // A hand with nothing to play for a while goes back to the picture's pose.
        for (auto& h : hands)
        {
            auto idle = h.piece < 0 || (h.next.piece < 0 && now - h.last.time > 1.4 && now - h.moveEnd > 1.4);
            h.home = idle ? std::min (1.0f, h.home + dt / 0.45f) : h.home;
        }
        auto lean = 0.0f;
        for (auto& h : hands)
            if (h.piece >= 0)
            {
                auto arm = armPose (h, now);
                auto d = arm.pivot - arm.shoulder;
                auto len = d.getDistanceFromOrigin();
                if (len > 95.0f)
                    lean += d.x / len * (len - 95.0f) * 0.55f;
            }
        bodyLean.target = juce::jlimit (-45.0f, 45.0f, lean);
        bodyLean.step (dt, 7.0f, 0.85f);
    }
    earL.step (dt, 22.0f, 0.15f);
    earR.step (dt, 22.0f, 0.15f);
    shake.step (dt, 55.0f, 0.25f);
    if (now - lastAnyHit > 1.2)
    {
        lookX.target = 0.15f * std::sin ((float) now * 0.7f);
        lookY.target = 0.1f * std::sin ((float) now * 0.5f);
    }
    lookX.step (dt, 12.0f, 0.9f);
    lookY.step (dt, 12.0f, 0.9f);
    energy *= std::exp (-dt / 0.35f);

    // Stick twirls when nothing is happening.
    if (now - lastAnyHit > 4.0 && ! tPlaying)
        for (auto& h : hands)
            if (now - h.twirlAt > 6.5 + h.side * 3.3)
                h.twirlAt = now;

    // Face and body.
    // A rocker's head-bang: down hard into the beat (the last quarter of it), lowest on the beat,
    // then up slower; a smooth curve, still at the top and the bottom. Fast songs bang on every
    // other beat (the way a drummer's head goes at 165).
    float beat = 0.0f;
    if (tPlaying)
    {
        auto beats = tBpm > 130.0 ? tPpq * 0.5 : tPpq;
        auto frac = (float) (beats - std::floor (beats));
        auto warped = frac < 0.75f ? frac / 0.75f * 0.5f : 0.5f + (frac - 0.75f) / 0.25f * 0.5f;
        beat = 0.5f * (1.0f + std::cos (juce::MathConstants<float>::twoPi * warped));
    }
    pose.torso = headBase;
    // How much he's into it: all the way while he's playing, a gentle nod while the song goes on
    // without him (an intro), eased so it never jumps.
    grooving += ((now - lastAnyHit < 1.5 ? 1.0f : 0.25f) - grooving) * (1.0f - std::exp (-dt / 0.6f));
    pose.head = headBase.translated (0.0f, beat * (rig ? 11.0f * grooving : 5.0f) + nod.x * (rig ? 4.0f : 3.0f));
    pose.bodyBounce = bounce.x * 0.08f;
    pose.tilt = 0.03f * std::sin ((float) now * 1.3f) * (tPlaying ? 0.4f : 1.0f) + nod.x * 0.012f + beat * 0.025f * grooving;
    pose.squash = 1.0f - juce::jlimit (-0.05f, 0.06f, bounce.x * 0.0035f);
    pose.mouthOpen = 0.3f + 0.62f * std::min (1.0f, energy);
    pose.mouthRound = juce::jlimit (0.0f, 1.0f, (energy - 0.85f) / 0.5f);
    pose.happy = now < happyUntil ? 1.0f : 0.0f;
    pose.blushGlow = std::min (1.0f, energy);
    pose.breath = std::sin ((float) now * juce::MathConstants<float>::twoPi / 3.4f);
    pose.earL = earL.x * 0.08f;
    pose.earR = earR.x * 0.08f;
    pose.look = { lookX.x, lookY.x };
    if (now >= nextBlink)
    {
        blinkAt = now;
        nextBlink = now + 2.2 + rng.nextFloat() * 3.6;
    }
    auto bt = (float) (now - blinkAt) / 0.14f;
    pose.blink = bt < 1.0f ? 1.0f - std::abs (bt * 2.0f - 1.0f) : 0.0f;

    // The song stopped after a good run: both sticks up, once the last hits have landed.
    if (tPlaying && ! wasPlaying)
        playingSince = now;
    auto stopped = ! tPlaying && wasPlaying;
    if (stopped && pending.empty() && now - playingSince > 4.0 && now - lastAnyHit < 1.5)
    {
        cheerUntil = now + 1.6;
        spawnHearts (5.0f);
    }
    if (! stopped || pending.empty())
        wasPlaying = tPlaying;

    // Marking a hit bad makes him sad for a moment; taking the mark off cheers him up.
    if (auto bad = proc.countBad(); bad != lastBadCount)
    {
        if (lastBadCount >= 0)
        {
            mood = bad > lastBadCount ? "sad" : "happy";
            moodUntil = now + 1.2;
        }
        lastBadCount = bad;
    }

    // Idle: a wink or a tongue now and then.
    if (now - lastAnyHit > 5.0 && now >= nextIdleMood && now >= cheerUntil)
    {
        static const char* idle[] = { "wink", "laugh", "smile", "happy" };
        mood = idle[rng.nextInt (4)];
        moodUntil = now + 1.3;
        nextIdleMood = now + 5.0 + rng.nextFloat() * 4.0;
    }

    // Change face, but not so often it flickers (a blink always goes through).
    auto wanted = pickFace();
    if (wanted != face && (now - faceAt > 0.16 || wanted == "blink" || face == "blink"))
    {
        lastFace = face;
        face = wanted;
        faceAt = now;
    }

    for (auto& p : particles)
    {
        p.age += dt;
        p.pos += p.vel * dt;
        p.vel.y += (p.kind == 0 ? 160.0f : -10.0f) * dt;
    }
    particles.erase (std::remove_if (particles.begin(), particles.end(), [] (auto& p) { return p.age >= p.life; }), particles.end());
    bursts.erase (std::remove_if (bursts.begin(), bursts.end(), [this] (auto& b) { return now - b.at > 0.7; }), bursts.end());

    // The arms for this frame (and the last frame's, for the motion blur between them).
    ++frameNo;
    if (rig && Skin::get().isLoaded())
    {
        auto first = ! haveLastArms[0];
        lastArms = shownArms;
        for (size_t i = 0; i < 2; ++i)
        {
            auto& h = hands[i];
            auto a = armPose (h, now);
            // The elbow: out and down when the arm is short, straight when it reaches; it trails
            // the hand a little (the forearm leads, the upper arm follows), springing after it.
            auto span = a.wrist.getDistanceFrom (a.shoulder);
            auto along = (a.wrist - a.shoulder) / std::max (1.0f, span);
            auto across = P (-along.y, along.x);
            if (across.x * (h.side == 0 ? -1.0f : 1.0f) < 0.0f)
                across = -across;
            auto bend = juce::jlimit (0.0f, 30.0f * a.scale, (210.0f * a.scale - span) * 0.2f);
            auto target = (a.shoulder + a.wrist) * 0.5f + (across + P (0.0f, 0.4f)) * (2.0f * bend);
            h.elbowX.target = target.x;
            h.elbowY.target = target.y;
            if (first || a.atRest)
            {
                h.elbowX.x = target.x; h.elbowX.v = 0.0f;
                h.elbowY.x = target.y; h.elbowY.v = 0.0f;
            }
            h.elbowX.step (dt, 26.0f, 0.75f);
            h.elbowY.step (dt, 26.0f, 0.75f);
            a.elbow = { h.elbowX.x, h.elbowY.x };
            // Keep it on the right side of the line from shoulder to wrist (a lag can't fold it).
            auto off = a.elbow - (a.shoulder + a.wrist) * 0.5f;
            if (off.x * across.x + off.y * across.y < 0.0f)
                a.elbow -= across * (off.x * across.x + off.y * across.y);
            // The shoulder rises with the arm when it swings up big (the upper arm lifting).
            h.shoulderLift.target = a.atRest ? 0.0f : juce::jlimit (0.0f, 6.0f, (a.shoulder.y - a.pivot.y - 20.0f) * 0.06f);
            h.shoulderLift.step (dt, 18.0f, 0.8f);
            a.sleeveLift = h.shoulderLift.x * a.scale;
            a.shoulder.y -= a.sleeveLift;
            shownArms[i] = a;
        }
        if (first)
            lastArms = shownArms;
        haveLastArms = { true, true };
    }
}

//==============================================================================
juce::AffineTransform PandaStage::designTransform() const
{
    auto s = std::min ((float) getWidth() / designW, (float) getHeight() / designH);
    auto ox = ((float) getWidth() - designW * s) * 0.5f;
    auto oy = ((float) getHeight() - designH * s) * 0.5f;
    return juce::AffineTransform::scale (s).translated (ox, oy);
}

PandaStage::P PandaStage::toDesign (P screen) const
{
    return screen.transformedBy (designTransform().inverted());
}

void PandaStage::resized()
{
    everything = true;
    background = {};
}

void PandaStage::paint (juce::Graphics& g)
{
    g.fillAll (colour::plum);
    auto t = designTransform();

    auto scale = std::max (1.0f, (float) g.getInternalContext().getPhysicalPixelScaleFactor());
    auto w = juce::roundToInt ((float) getWidth() * scale), h = juce::roundToInt ((float) getHeight() * scale);
    if (background.isNull() || background.getWidth() != w || background.getHeight() != h)
    {
        background = juce::Image (juce::Image::RGB, std::max (1, w), std::max (1, h), true);
        juce::Graphics bg (background);
        bg.fillAll (colour::plum);
        bg.addTransform (t.scaled (scale));
        if (auto& skin = Skin::get(); skin.isLoaded())
        {
            bg.setImageResamplingQuality (juce::Graphics::highResamplingQuality);
            skin.draw (bg, skin.sprite ("stage"));
            // The kit as it stands in the room (its stands, the drums at rest, bigger than the
            // picture's): it never moves, so it's drawn with the room.
            if (auto* still = skin.at ("stage/kit").getArray())
                for (auto& layer : *still)
                    skin.draw (bg, skin.sprite (layer.toString()));
        }
        else
            art::drawStage (bg, { 0.0f, 0.0f, designW, designH });
    }
    g.drawImage (background, getLocalBounds().toFloat());

    juce::Graphics::ScopedSaveState save (g);
    auto stageT = juce::AffineTransform::translation (0.0f, juce::jlimit (-4.0f, 4.0f, shake.x * 0.1f)).followedBy (t);
    g.addTransform (stageT);
    stageToDevice = stageT.scaled (scale);
    deviceToStage = stageToDevice.inverted();
    if (frameNo % 60 == 0)
        for (auto it = layerCache.begin(); it != layerCache.end();)
            it = frameNo - it->second.used > 120 ? layerCache.erase (it) : std::next (it);
    g.reduceClipRegion (juce::Rectangle<int> (0, 0, (int) designW, (int) designH));

    if (Skin::get().isLoaded())
        paintSkin (g);
    else
        paintVector (g);

    drawParticles (g);
    for (auto& b : bursts)
    {
        auto age = (float) (now - b.at);
        auto pop = age < 0.12f ? 1.2f * easeOutCubic (age / 0.12f) : 1.2f - 0.2f * easeOutCubic ((age - 0.12f) / 0.15f);
        auto alpha = age < 0.45f ? 1.0f : 1.0f - (age - 0.45f) / 0.25f;
        art::drawComicBurst (g, b.text, b.pos, pop * 0.85f, juce::jlimit (0.0f, 1.0f, alpha), b.rot, b.colour);
    }

    if (showTags)
        drawTags (g);
    if (proc.showHitInfo)
        drawChips (g);
}

art::DrumState PandaStage::drumState (const PieceView& v) const
{
    art::DrumState s;
    auto ft = (float) (now - v.flashAt);
    s.flash = ft >= 0.0f ? v.flashAmt * std::exp (-ft / 0.09f) : 0.0f;
    auto rt = (float) (now - v.rippleAt) / 0.32f;
    s.ripple = rt >= 0.0f && rt < 1.0f ? rt : -1.0f;
    s.rippleStrength = v.rippleAmt;
    s.pulse = juce::jlimit (-0.5f, 1.2f, v.pulse.x * 0.12f);
    return s;
}

void PandaStage::drawSelection (juce::Graphics& g)
{
    if (auto* sv = juce::isPositiveAndBelow (selected, (int) views.size()) ? &views[(size_t) selected] : nullptr)
    {
        auto glow = 0.45f + 0.25f * std::sin ((float) now * 5.0f);
        g.setColour (colour::hot.withAlpha (glow));
        if (sv->type == PieceType::Kick)
            g.drawEllipse (sv->pos.x - sv->radius - 6.0f, sv->pos.y - sv->radius - 6.0f, sv->radius * 2.0f + 12.0f, sv->radius * 2.0f + 12.0f, 4.0f);
        else
            g.drawEllipse (sv->pos.x - sv->radius - 6.0f, sv->pos.y - sv->radius * sv->squash - 6.0f, sv->radius * 2.0f + 12.0f, sv->radius * sv->squash * 2.0f + 12.0f, 3.5f);
    }
}

void PandaStage::paintVector (juce::Graphics& g)
{
    auto state = [this] (const PieceView& v) { return drumState (v); };

    art::drawPandaShadow (g, pose);
    art::drawPandaBody (g, pose);
    art::drawPandaHead (g, pose);

    // Cymbals (stands behind the drums), then drums from the back forward.
    for (auto& v : views)
        if (isCymbal (v.type) && v.type != PieceType::HiHat)
        {
            // Splashes hang off a boom so their stand doesn't run through the drums.
            auto pole = v.type == PieceType::Splash ? v.pos.x + (v.pos.x >= 640.0f ? 135.0f : -135.0f) : -1.0f;
            art::drawCymbal (g, v.pos, v.radius, v.wobble.x * 0.05f + (v.pos.x < 640.0f ? -0.06f : 0.06f),
                             1.0f + 0.25f * std::sin (v.wobble.x * 0.4f), v.type, state (v), floorY, true, pole);
        }

    auto kick = std::find_if (views.begin(), views.end(), [] (auto& v) { return v.type == PieceType::Kick; });
    std::vector<const PieceView*> drums;
    for (auto& v : views)
        if (! isCymbal (v.type) && v.type != PieceType::Kick)
            drums.push_back (&v);
    std::sort (drums.begin(), drums.end(), [] (auto* a, auto* b) { return a->pos.y < b->pos.y; });

    // Rack toms sit on the kick; mounts first.
    if (kick != views.end())
        for (auto* d : drums)
            if (d->type == PieceType::Tom && ! d->isFloor)
            {
                auto bottom = d->pos.translated (0.0f, d->shell + d->radius * d->squash);
                g.setColour (colour::ink);
                g.drawLine (bottom.x, bottom.y - 6.0f, kick->pos.x + (d->pos.x - kick->pos.x) * 0.3f, kick->pos.y - kick->radius * 0.8f, 9.0f);
                g.setColour (colour::chrome);
                g.drawLine (bottom.x, bottom.y - 6.0f, kick->pos.x + (d->pos.x - kick->pos.x) * 0.3f, kick->pos.y - kick->radius * 0.8f, 5.5f);
            }

    for (auto* d : drums)
        if (d->type == PieceType::Tom && ! d->isFloor)
            art::drawDrum (g, d->pos, d->radius, d->shell, d->wrap, d->type, state (*d), floorY);
    if (kick != views.end())
    {
        art::drawKick (g, kick->pos, kick->radius, kick->wrap, state (*kick), floorY, "PANDA");
        auto kt = (float) (now - kick->rippleAt) / 0.4f;
        if (kt >= 0.0f && kt < 1.0f)
        {
            auto rr = kick->radius * (1.05f + 0.5f * kt);
            g.setColour (juce::Colours::white.withAlpha ((1.0f - kt) * 0.45f * kick->rippleAmt));
            g.drawEllipse (kick->pos.x - rr, kick->pos.y - rr, rr * 2.0f, rr * 2.0f, 4.0f * (1.0f - kt) + 1.0f);
        }
    }
    for (auto* d : drums)
        if (! (d->type == PieceType::Tom && ! d->isFloor))
            art::drawDrum (g, d->pos, d->radius, d->shell, d->wrap, d->type, state (*d), floorY);
    for (auto& v : views)
        if (v.type == PieceType::HiHat)
            art::drawHiHat (g, v.pos, v.radius, v.gap.x, v.wobble.x * 0.04f - 0.04f, state (v), floorY, juce::jlimit (0.0f, 1.0f, v.press.x));

    drawSelection (g);

    // Arms, sticks and paws.
    for (auto& hand : hands)
    {
        P paw, tip;
        handPose (hand, now, paw, tip);
        auto shoulder = pose.shoulder (hand.side == 0);
        if (now < hand.smearUntil)
        {
            auto a = (float) ((hand.smearUntil - now) / 0.045) * 0.4f;
            juce::Path streak;
            streak.startNewSubPath (hand.smearTip);
            streak.lineTo (tip);
            streak.lineTo (paw);
            streak.lineTo (hand.smearPaw);
            streak.closeSubPath();
            g.setColour (juce::Colours::white.withAlpha (a * 0.6f));
            g.fillPath (streak);
            art::drawArm (g, shoulder, hand.smearPaw, hand.smearTip - hand.smearPaw, 24.0f, a);
            art::drawStick (g, hand.smearPaw - normalised (hand.smearTip - hand.smearPaw) * 14.0f, hand.smearTip, 7.0f, a);
        }
        art::drawArm (g, shoulder, paw, tip - paw, 25.0f);
        art::drawStick (g, paw - normalised (tip - paw) * 16.0f, tip, 7.5f);
        art::drawPaw (g, paw, 16.0f);
    }

}

//==============================================================================
juce::AffineTransform PandaStage::pieceTransform (const PieceView& v, P anchor, float renderedRadius, float extraScale) const
{
    // From where the layer was rendered to where this piece is, at this piece's size.
    auto s = v.radius / std::max (1.0f, renderedRadius) * extraScale;
    auto t = juce::AffineTransform::translation (-anchor.x, -anchor.y);
    if (v.flip)
        t = t.scaled (-1.0f, 1.0f);
    return t.scaled (s, s * v.stretch).translated (v.pos.x, v.pos.y);
}

void PandaStage::drawContactShadow (juce::Graphics& g, juce::Rectangle<float> footprint, float alpha)
{
    if (footprint.isEmpty())
        return;
    juce::ColourGradient grad (juce::Colour (0xff2a0a24).withAlpha (alpha), footprint.getCentre(),
                               juce::Colour (0xff2a0a24).withAlpha (0.0f), footprint.getCentre().translated (footprint.getWidth() * 0.5f, 0.0f), true);
    g.setGradientFill (grad);
    g.saveState();
    g.addTransform (juce::AffineTransform::scale (1.0f, footprint.getHeight() / footprint.getWidth(), footprint.getCentreX(), footprint.getCentreY()));
    g.fillEllipse (footprint.withSizeKeepingCentre (footprint.getWidth(), footprint.getWidth()));
    g.restoreState();
}

juce::String PandaStage::pickFace() const
{
    if (now < cheerUntil)                          return "excited";
    if (now < moodUntil && mood.isNotEmpty())      return mood;
    if (pose.blink > 0.4f)                         return "blink";
    if (pose.happy > 0.5f)                         return "laugh";
    if (energy > 1.1f)                             return "excited";
    if (energy > 0.6f)                             return "happy";
    if (energy > 0.15f)                            return "focused";
    return tPlaying ? "smile" : "neutral";
}

juce::String PandaStage::skinKind (const PieceView& v) const
{
    // Pieces on the left use their own picture where the art has one ("tom_alt", "crash_alt").
    auto& skin = Skin::get();
    auto alt = [this, &skin, &v] (const juce::String& k)
    {
        return v.pos.x < centreX && skin.at ("kit/" + k + "_alt").isObject() ? k + "_alt" : k;
    };
    switch (v.type)
    {
        case PieceType::Kick:   return "kick";
        case PieceType::Snare:  return "snare";
        case PieceType::Tom:    return v.isFloor ? juce::String ("floor") : alt ("tom");
        case PieceType::HiHat:  return "hihat";
        case PieceType::Crash:  return alt ("crash");
        case PieceType::Ride:   return "ride";
        case PieceType::China:  return "china";
        case PieceType::Splash: return "splash";
        case PieceType::Perc:   return "snare";
    }
    return "tom";
}

juce::String PandaStage::poseFor (const PieceView& v) const
{
    auto left = v.pos.x < centreX;
    switch (v.type)
    {
        case PieceType::Kick:   return "kick";
        case PieceType::Snare:
        case PieceType::Perc:   return "snare";
        case PieceType::HiHat:
        case PieceType::Ride:   return "hi_hat";
        case PieceType::Tom:    return v.isFloor ? "fill" : (left ? "tom_left" : "tom_right");
        case PieceType::Crash:
        case PieceType::China:
        case PieceType::Splash: return left ? "crash_left" : "crash_right";
    }
    return "idle";
}

void PandaStage::strikeFx (const PieceView& v, int hand, float vel)
{
    // The pose for the drum, held a moment; a kick on its own gets its own, otherwise the hands lead.
    juce::String next = poseFor (v);
    if (recentToms >= 3 && v.type == PieceType::Tom)
        next = "fill";
    if (hand < 0 && now < poseHold && poseName != "kick")
        next = poseName;
    if (next != poseName)
    {
        lastPoseName = poseName;
        poseName = next;
        poseAt = now;
    }
    poseHold = now + (hand < 0 ? 0.2 : 0.36);      // long enough that a groove doesn't flicker back to sitting

    if (hand < 0)
        return;
    // A streak where the stick came down, and a spark on hard hits.
    auto at = rig ? rigStrikePoint (v, hand) : strikePoint (v, hand);
    if (rig && vel < 0.55f)
        return;     // a tap is just a tap
    Fx streak;
    streak.sprite = "blur_" + juce::String (1 + rng.nextInt (3));
    streak.pos = at.translated ((hand == 0 ? -1.0f : 1.0f) * 30.0f, -34.0f);
    streak.at = now;
    streak.life = 0.14f;
    streak.rot = (hand == 0 ? 0.35f : -0.35f) + (rng.nextFloat() - 0.5f) * 0.3f;
    streak.scale = 0.7f + 0.4f * vel;
    streak.flip = hand == 0;
    fx.push_back (streak);
    if (vel > 0.7f)
    {
        Fx spark;
        spark.sprite = "hit_spark";
        spark.pos = at;
        spark.at = now;
        spark.life = 0.18f;
        spark.rot = rng.nextFloat() * 6.28f;
        spark.scale = 0.5f + 0.6f * vel;
        fx.push_back (spark);
    }
}

void PandaStage::paintSkin (juce::Graphics& g)
{
    auto& skin = Skin::get();
    g.setImageResamplingQuality (juce::Graphics::highResamplingQuality);
    auto pt = [&skin] (const juce::String& path) { return Skin::point (skin.at (path)); };
    auto num = [&skin] (const juce::String& path, float fallback) { return Skin::number (skin.at (path), fallback); };
    auto wrapName = [] (art::Wrap w) -> juce::String
    {
        switch (w)
        {
            case art::Wrap::PurpleSparkle: return "purple";
            case art::Wrap::Brass:         return "brass";
            case art::Wrap::Maple:         return "maple";
            case art::Wrap::Chrome:        return "chrome";
            case art::Wrap::Walnut:        return "walnut";
            case art::Wrap::Black:         return "black";
        }
        return "purple";
    };
    auto layerFor = [this, &skin, &wrapName] (const PieceView& v)
    {
        auto kind = skinKind (v);
        auto wrap = v.type == PieceType::Perc ? juce::String ("chrome") : wrapName (v.wrap);
        auto name = skin.at ("kit/" + kind + "/wraps/" + wrap).toString();
        if (name.isEmpty())
            name = skin.at ("kit/" + kind + "/wraps/purple").toString();
        return skin.sprite (name);
    };
    auto slotKind = [] (const PieceView& v) -> juce::String
    {
        return v.type == PieceType::Crash ? "crash" : v.type == PieceType::Ride ? "ride" : v.type == PieceType::China ? "china" : "splash";
    };

    // PD_PLAIN=1 (the render tool's check against the picture): no lights or specks over the room.
    static const bool plain = juce::SystemStats::getEnvironmentVariable ("PD_PLAIN", {}).isNotEmpty();

    // ---- the heart lights glow, twinkle, and flare with the kick
    if (auto* bulbs = skin.at ("stage/bulbs").getArray(); bulbs != nullptr && ! plain)
    {
        float kickFlash = 0.0f;
        for (auto& v : views)
            if (v.type == PieceType::Kick)
                kickFlash = std::max (kickFlash, drumState (v).flash);
        for (int i = 0; i < bulbs->size(); ++i)
        {
            auto b = (*bulbs)[i];
            auto p = Skin::point (b.getProperty ("at", {}));
            auto* c = b.getProperty ("colour", {}).getArray();
            if (c == nullptr || c->size() < 3)
                continue;
            auto col = juce::Colour::fromFloatRGBA ((float) (double) (*c)[0], (float) (double) (*c)[1], (float) (double) (*c)[2], 1.0f);
            auto twinkle = 0.75f + 0.25f * std::sin ((float) now * 2.3f + (float) i * 1.7f);
            auto a = juce::jlimit (0.0f, 1.0f, 0.3f * twinkle + 0.35f * kickFlash);
            auto rr = 26.0f + 12.0f * kickFlash;
            juce::ColourGradient grad (col.withAlpha (a), p, col.withAlpha (0.0f), p.translated (rr, 0.0f), true);
            g.setGradientFill (grad);
            g.fillEllipse (juce::Rectangle<float> (rr * 2.0f, rr * 2.0f).withCentre (p));
        }
    }

    // ---- the spotlights' beams sway over the room and flare with the cymbals; the rug's ring
    // lights up with the kick; specks of light drift up through the beams.
    if (! plain)
    {
        float crashFlash = 0.0f, kickGlow = 0.0f;
        for (auto& v : views)
        {
            auto f = drumState (v).flash;
            if (v.type == PieceType::Crash || v.type == PieceType::China || v.type == PieceType::Splash)
                crashFlash = std::max (crashFlash, f);
            if (v.type == PieceType::Kick)
                kickGlow = std::max (kickGlow, f);
        }
        if (auto* beams = skin.at ("stage/beams").getArray())
            for (int i = 0; i < beams->size(); ++i)
            {
                auto b = (*beams)[i];
                auto pivot = Skin::point (b.getProperty ("pivot", {}));
                auto sway = 0.05f * std::sin ((float) now * (0.29f + 0.06f * (float) i) + (float) i * 2.1f);
                auto a = 0.36f + 0.07f * std::sin ((float) now * 0.8f + (float) i * 1.3f) + 0.45f * crashFlash + 0.15f * kickGlow;
                skin.draw (g, skin.sprite (b.getProperty ("file", {}).toString()), juce::AffineTransform::rotation (sway, pivot.x, pivot.y),
                           juce::jlimit (0.0f, 0.95f, a));
            }
        auto rug = Skin::ellipse (skin.at ("stage/rug"));
        if (! rug.isEmpty() && kickGlow > 0.01f)
        {
            juce::Path ring;
            ring.addEllipse (rug);
            for (auto [width, alpha] : { std::pair { 30.0f, 0.12f }, std::pair { 16.0f, 0.22f }, std::pair { 6.0f, 0.5f } })
            {
                g.setColour (juce::Colour (0xffff7ac0).withAlpha (alpha * kickGlow));
                g.strokePath (ring, juce::PathStrokeType (width));
            }
        }
        auto motes = skin.sprite (skin.at ("panda/fx/glow_particles").toString());
        if (motes.isValid() && ! rig)
            for (int i = 0; i < 7; ++i)
            {
                auto cycle = 14.0f + 3.0f * (float) (i % 3);
                auto phase = std::fmod ((float) now / cycle + (float) i * 0.37f, 1.0f);
                auto x = 240.0f + 130.0f * (float) i + 24.0f * std::sin ((float) now * 0.4f + (float) i);
                auto y = 560.0f - 460.0f * phase;
                auto size = 0.3f + 0.12f * (float) ((i * 5) % 3);
                auto a = 0.45f * std::sin (juce::MathConstants<float>::pi * phase) * (0.7f + 0.3f * std::sin ((float) now * 3.0f + (float) i));
                auto c = motes.bounds.getCentre();
                skin.draw (g, motes, juce::AffineTransform::translation (-c.x, -c.y).scaled (size).rotated ((float) i).translated (x, y), a);
            }
    }

    auto drawPosePanda = [&]
    {
        // ---- the panda: his body in the pose for what he's playing, his head on it moving on its
        // own (nodding to the beat, leaning toward each hit, dipping into it), his face over that.
        auto head0 = pt ("panda/head/anchor");
        P seat (head0.x, head0.y + pose.radius * 2.1f);
        auto popIn = 1.0f + 0.03f * std::exp (-(float) (now - poseAt) / 0.06f);   // each new pose lands with a little punch
        auto nodBy = pose.head - pose.torso;
        auto breathe = 1.0f + 0.006f * pose.breath;
        auto shown = now < cheerUntil ? juce::String ("cheer") : poseName;
        auto poseKey = [&skin] (const juce::String& name, const juce::String& key)
        {
            auto v = skin.at ("panda/poses/" + name + "/" + key);
            return v.isVoid() ? skin.at ("panda/poses/idle/" + key) : v;
        };
        auto split = poseKey (shown, "head_file").toString().isNotEmpty();
        auto panT = juce::AffineTransform::translation (-seat.x, -seat.y)
                        .scaled ((1.0f + (1.0f - pose.squash) * 0.6f) * popIn, pose.squash * popIn * breathe)
                        .rotated (pose.tilt * (split ? 0.25f : 0.6f))
                        .translated (seat.x + nodBy.x * (split ? 0.3f : 1.0f), seat.y + pose.bodyBounce + nodBy.y * (split ? 0.3f : 1.0f));
        auto headT = panT;
        if (split)
        {
            auto neck = Skin::point (poseKey (shown, "neck"));
            headT = juce::AffineTransform::rotation (pose.tilt * 1.2f + juce::jlimit (-0.14f, 0.14f, headLean.x * 0.09f), neck.x, neck.y)
                        .translated (nodBy.x * 0.7f, nodBy.y * 0.7f + juce::jlimit (-4.0f, 9.0f, headDip.x * 0.09f))
                        .followedBy (panT);
            skin.draw (g, skin.sprite (poseKey (shown, "body_file").toString()), panT);
            skin.draw (g, skin.sprite (poseKey (shown, "head_file").toString()), headT);
        }
        else
            skin.draw (g, skin.sprite (poseKey (shown, "file").toString()), panT);
        if (! (bool) skin.at ("panda/poses/" + shown + "/own_face"))
        {
            auto* f = skin.at ("panda/poses/" + shown + "/face").getArray();
            auto faceT = f != nullptr && f->size() == 3
                           ? juce::AffineTransform::scale ((float) (double) (*f)[0]).translated ((float) (double) (*f)[1], (float) (double) (*f)[2])
                           : juce::AffineTransform();
            auto faceLayer = [&skin] (const juce::String& name)
            {
                auto file = skin.at ("panda/faces/" + name + "/file").toString();
                return skin.sprite (file.isNotEmpty() ? file : skin.at ("panda/faces/neutral/file").toString());
            };
            // Faces cut from one to the next like a cartoon's: a blend would show two pairs of eyes.
            skin.draw (g, faceLayer (face), faceT.followedBy (headT));
        }

    };

    auto drawCymbals = [&] (int which)      // 0: all, 1: behind the panda, 2: in front of his arms
    {
        // ---- cymbals: stands, then the discs swinging on them
        for (auto& v : views)
            if (isCymbal (v.type) && v.type != PieceType::HiHat && v.sharesWith < 0
                && (which == 0 || (which == 2) == (bool) skin.at ("kit/" + skinKind (v) + "/front")))
            {
                auto kind = skinKind (v);
                auto st = drumState (v);
                auto stands = skin.at ("kit/stands/" + slotKind (v));
                juce::var stand;
                if (auto* a = stands.getArray(); a != nullptr && v.slot < a->size())
                    stand = (*a)[v.slot];
                auto standLayer = skin.sprite (stand.getProperty ("file", {}).toString());
                if (standLayer.isValid())
                {
                    if (! rig)
                        drawContactShadow (g, juce::Rectangle<float> (80.0f, 14.0f).withCentre ({ standLayer.bounds.getCentreX(), standLayer.bounds.getBottom() - 6.0f }));
                    drawLayer (g, standLayer, juce::AffineTransform::translation (v.pos - Skin::point (stand.getProperty ("top", {}))));
                }
                // Settled (a swing under a fifteenth of a degree, a hairline at the rim), it sits
                // exactly at rest.
                auto wob = std::abs (v.wobble.x * 0.05f) < 0.0012f ? 0.0f : v.wobble.x;
                auto angle = wob * 0.05f;
                auto squash = 1.0f + 0.25f * std::sin (wob * 0.4f);
                auto anchor = pt ("kit/" + kind + "/anchor");
                auto t = juce::AffineTransform::translation (-anchor.x, -anchor.y);
                if (v.flip)
                    t = t.scaled (-1.0f, 1.0f);
                auto sc = v.radius / num ("kit/" + kind + "/radius", v.radius);
                t = t.rotated (angle).scaled (sc, sc * squash).translated (v.pos.x, v.pos.y);
                drawLayer (g, skin.sprite (skin.at ("kit/" + kind + "/file").toString()), t);
                if (st.flash > 0.02f)
                {
                    // A flash of light across the bronze.
                    auto e = juce::Rectangle<float> (v.radius * 2.0f, v.radius * v.squash * 2.0f * squash).withCentre (v.pos);
                    juce::ColourGradient grad (juce::Colours::white.withAlpha (0.7f * st.flash), e.getCentre(),
                                               juce::Colour (0xffffd27a).withAlpha (0.0f), e.getCentre().translated (e.getWidth() * 0.5f, 0.0f), true);
                    g.setGradientFill (grad);
                    g.saveState();
                    g.addTransform (juce::AffineTransform::rotation (angle, v.pos.x, v.pos.y));
                    g.fillEllipse (e);
                    g.restoreState();
                }
            }

    };

    auto drawDrums = [&]
    {
        // ---- drums from the back forward
        auto kick = std::find_if (views.begin(), views.end(), [] (auto& v) { return v.type == PieceType::Kick; });
        std::vector<const PieceView*> drums;
        for (auto& v : views)
            if (! isCymbal (v.type) && v.type != PieceType::Kick && v.sharesWith < 0)
                drums.push_back (&v);
        std::sort (drums.begin(), drums.end(), [] (auto* a, auto* b) { return a->pos.y < b->pos.y; });

        auto drawDrumLayer = [&] (const PieceView& v)
        {
            auto kind = skinKind (v);
            auto st = drumState (v);
            auto layer = layerFor (v);
            // A hit knocks the drum down a hair and it springs back (with the art, not swelling).
            auto t = rig ? pieceTransform (v, pt ("kit/" + kind + "/anchor"), num ("kit/" + kind + "/radius", v.radius),
                                           v.type == PieceType::Perc ? 0.9f : 1.0f)
                               .translated (0.0f, std::abs (st.pulse) < 0.02f ? 0.0f : 6.0f * st.pulse)
                         : pieceTransform (v, pt ("kit/" + kind + "/anchor"), num ("kit/" + kind + "/radius", v.radius),
                                           (v.type == PieceType::Perc ? 0.9f : 1.0f) * (1.0f + 0.035f * st.pulse));
            auto still = pieceTransform (v, pt ("kit/" + kind + "/anchor"), num ("kit/" + kind + "/radius", v.radius),
                                         v.type == PieceType::Perc ? 0.9f : 1.0f);
            if (auto standName = skin.at ("kit/" + kind + "/stand_file").toString(); standName.isNotEmpty())
            {
                auto standLayer = skin.sprite (standName);
                auto foot = standLayer.bounds.transformedBy (still);
                drawContactShadow (g, juce::Rectangle<float> (foot.getWidth() * 0.9f, 14.0f).withCentre ({ foot.getCentreX(), foot.getBottom() - 4.0f }));
                drawLayer (g, standLayer, still);
            }
            else if (v.isFloor && ! rig)
            {
                auto foot = layer.bounds.transformedBy (t);
                drawContactShadow (g, juce::Rectangle<float> (foot.getWidth() * 0.85f, 16.0f).withCentre ({ foot.getCentreX(), foot.getBottom() - 6.0f }));
            }
            drawLayer (g, layer, t);
            // The head lights up and a ring runs out across it.
            auto head = Skin::ellipse (skin.at ("kit/" + kind + "/head")).transformedBy (t);
            if (st.flash > 0.02f)
            {
                g.setColour (juce::Colours::white.withAlpha (0.5f * st.flash));
                g.fillEllipse (head);
            }
            if (st.ripple >= 0.0f)
            {
                auto ring = head.withSizeKeepingCentre (head.getWidth() * (0.2f + 0.8f * st.ripple), head.getHeight() * (0.2f + 0.8f * st.ripple));
                g.setColour (juce::Colours::white.withAlpha ((1.0f - st.ripple) * 0.65f * st.rippleStrength));
                g.drawEllipse (ring, 2.5f * (1.0f - st.ripple) + 0.8f);
            }
        };

        // The rig's picture has the kick in front of every drum (the rack tom sits on it): the
        // drums go first, back to front, then the kick.
        for (auto* d : drums)
            if (rig || (d->type == PieceType::Tom && ! d->isFloor))
                drawDrumLayer (*d);
        if (kick != views.end())
        {
            auto st = drumState (*kick);
            auto layer = layerFor (*kick);
            auto t = rig ? pieceTransform (*kick, pt ("kit/kick/anchor"), num ("kit/kick/radius", kick->radius))
                               .translated (0.0f, std::abs (st.pulse) < 0.02f ? 0.0f : 5.0f * st.pulse)
                         : pieceTransform (*kick, pt ("kit/kick/anchor"), num ("kit/kick/radius", kick->radius), 1.0f + 0.02f * st.pulse);
            auto foot = layer.bounds.transformedBy (t);
            if (! rig)
                drawContactShadow (g, juce::Rectangle<float> (foot.getWidth() * 0.9f, 22.0f).withCentre ({ foot.getCentreX(), foot.getBottom() - 8.0f }), 0.32f);
            drawLayer (g, layer, t);
            if (auto pedal = skin.sprite (skin.at ("kit/kick/pedal_file").toString()); pedal.isValid())
                drawLayer (g, pedal, pieceTransform (*kick, pt ("kit/kick/anchor"), num ("kit/kick/radius", kick->radius)));
            auto head = Skin::ellipse (skin.at ("kit/kick/head")).transformedBy (t);
            if (st.flash > 0.02f)
            {
                g.setColour (juce::Colours::white.withAlpha (0.3f * st.flash));
                g.fillEllipse (head);
            }
            auto kt = (float) (now - kick->rippleAt) / 0.4f;
            if (! rig && kt >= 0.0f && kt < 1.0f)
            {
                auto rr = kick->radius * (1.05f + 0.5f * kt);
                g.setColour (juce::Colours::white.withAlpha ((1.0f - kt) * 0.45f * kick->rippleAmt));
                g.drawEllipse (kick->pos.x - rr, kick->pos.y - rr, rr * 2.0f, rr * 2.0f, 4.0f * (1.0f - kt) + 1.0f);
            }
        }
        for (auto* d : drums)
            if (! rig && ! (d->type == PieceType::Tom && ! d->isFloor) && d->type != PieceType::HiHat)
                drawDrumLayer (*d);

    };

    auto drawHiHat = [&]
    {
        // ---- hi-hat: stand, bottom cymbal, top cymbal lifted by the pedal
        for (auto& v : views)
            if (v.type == PieceType::HiHat)
            {
                auto anchor = pt ("kit/hihat/anchor");
                auto move = juce::AffineTransform::translation (v.pos - anchor);
                auto standLayer = skin.sprite (skin.at ("kit/hihat/stand_file").toString());
                if (standLayer.isValid())
                {
                    drawContactShadow (g, juce::Rectangle<float> (90.0f, 14.0f).withCentre (P (standLayer.bounds.getCentreX(), standLayer.bounds.getBottom() - 6.0f).transformedBy (move)));
                    drawLayer (g, standLayer, move);
                }
                auto sc = v.radius / num ("kit/hihat/radius", v.radius);
                auto angle = std::abs (v.wobble.x * 0.04f) < 0.0012f ? 0.0f : v.wobble.x * 0.04f;
                auto cym = [&] (const char* file, const char* where, float lift)
                {
                    auto c = pt (juce::String ("kit/hihat/") + where);
                    auto t = juce::AffineTransform::translation (-c.x, -c.y).rotated (angle).scaled (sc).translated (c.x, c.y - lift).followedBy (move);
                    drawLayer (g, skin.sprite (skin.at (juce::String ("kit/hihat/") + file).toString()), t);
                };
                cym ("bottom_file", "bottom", 0.0f);
                cym ("top_file", "top", juce::jlimit (0.0f, 18.0f, (v.gap.x - 1.5f) * 0.9f));
                auto st = drumState (v);
                if (st.flash > 0.02f)
                {
                    auto c = pt ("kit/hihat/top").transformedBy (move);
                    auto e = juce::Rectangle<float> (v.radius * 2.0f, v.radius * v.squash * 2.0f).withCentre (c);
                    juce::ColourGradient grad (juce::Colours::white.withAlpha (0.6f * st.flash), e.getCentre(),
                                               juce::Colour (0xffffd27a).withAlpha (0.0f), e.getCentre().translated (e.getWidth() * 0.5f, 0.0f), true);
                    g.setGradientFill (grad);
                    g.fillEllipse (e);
                }
            }

    };

    if (rig)
    {
        // The picture's order: the cymbals and hi-hat behind him, his body and head, the drums
        // in front of him, his arms over them, and the china hanging in front of it all.
        drawCymbals (1);
        drawHiHat();
        paintRig (g, false);
        drawDrums();
        paintRig (g, true);
        drawCymbals (2);
    }
    else
    {
        drawPosePanda();
        drawCymbals (0);
        drawDrums();
        drawHiHat();
    }

    drawSelection (g);

    // ---- stick streaks and sparks
    for (auto& f : fx)
    {
        auto age = (float) (now - f.at);
        if (age < 0.0f || age > f.life)
            continue;
        auto sprite = skin.sprite (skin.at ("panda/fx/" + f.sprite).toString());
        if (! sprite.isValid())
            continue;
        auto k = age / f.life;
        auto grow = f.sprite == "hit_spark" ? 0.6f + 0.6f * k : 1.0f;
        auto c = sprite.bounds.getCentre();
        auto t = juce::AffineTransform::translation (-c.x, -c.y);
        if (f.flip)
            t = t.scaled (-1.0f, 1.0f);
        t = t.rotated (f.rot).scaled (f.scale * grow).translated (f.pos.x, f.pos.y);
        skin.draw (g, sprite, t, 1.0f - k * k);
    }
}

void PandaStage::drawParticles (juce::Graphics& g)
{
    for (auto& p : particles)
    {
        auto a = 1.0f - p.age / p.life;
        if (p.kind == 0)
            art::drawSparkle (g, p.pos, p.size * (0.6f + 0.4f * a), a, p.colour);
        else if (auto& skin = Skin::get(); skin.isLoaded())
        {
            static const char* hearts[] = { "heart_red", "heart_pink", "heart_yellow" };
            auto sprite = skin.sprite (skin.at (juce::String ("panda/fx/") + hearts[(size_t) p.variant % 3]).toString());
            auto c = sprite.bounds.getCentre();
            skin.draw (g, sprite, juce::AffineTransform::translation (-c.x, -c.y).rotated (p.spin * p.age)
                                      .scaled (p.size / std::max (1.0f, sprite.bounds.getHeight()))
                                      .translated (p.pos.x, p.pos.y), a);
        }
        else
        {
            juce::Graphics::ScopedSaveState s (g);
            g.addTransform (juce::AffineTransform::rotation (p.spin * p.age, p.pos.x, p.pos.y));
            art::drawHeart (g, juce::Rectangle<float> (p.size, p.size * 0.9f).withCentre (p.pos), p.colour.withAlpha (a), colour::ink.withAlpha (a), 2.0f);
        }
    }
}

void PandaStage::drawTags (juce::Graphics& g)
{
    // The drum's swap and tune controls, on the pack's selector with its arrows and a readout.
    for (auto& v : views)
    {
        auto isSel = v.piece == selected, isHover = v.piece == hoverPiece;
        if (v.tag.isEmpty() || ! (isSel || isHover))
            continue;
        if (isSel)
            ui::glow (g, "button_instrument_selector", v.tag, colour::hot.withAlpha (0.7f), 7.0f);
        ui::button (g, "button_instrument_selector", v.tag, isHover && hoverButton == "tag" ? 0.07f : 0.0f);

        auto arrow = [&] (juce::Rectangle<float> r, float angle, const juce::String& id)
        {
            if (r.isEmpty())
                return;
            if (isHover && hoverButton == id)
            {
                g.setColour (juce::Colours::white.withAlpha (0.18f));
                g.fillEllipse (r.withSizeKeepingCentre (19.0f, 19.0f));
            }
            ui::icon (g, "icon_chevron_left", r.withSizeKeepingCentre (13.0f, 13.0f), angle);
        };
        arrow (v.prevBtn, 0.0f, "prev");
        arrow (v.nextBtn, juce::MathConstants<float>::pi, "next");
        arrow (v.downBtn, -juce::MathConstants<float>::halfPi, "down");
        arrow (v.upBtn, juce::MathConstants<float>::halfPi, "up");

        auto nameArea = v.tag.reduced (6.0f, 0.0f);
        if (! v.prevBtn.isEmpty()) nameArea.setLeft (v.prevBtn.getRight());
        nameArea.setRight (! v.nextBtn.isEmpty() ? v.nextBtn.getX() : (! v.downBtn.isEmpty() ? v.downBtn.getX() - 4.0f : nameArea.getRight()));
        ui::label (g, v.variantName, nameArea, ui::colour::text, 11.5f);

        if (v.tunable)
        {
            auto pr = juce::Rectangle<float> (v.downBtn.getRight(), v.tag.getY() + 4.0f, v.upBtn.getX() - v.downBtn.getRight(), v.tag.getHeight() - 8.0f);
            auto ok = v.keyOn && v.inKey;
            auto piece = ok ? "readout_zone" : (v.keyOn ? "readout_midi" : "readout_velocity");
            ui::readout (g, piece, pr);
            auto text = pr.withTrimmedLeft (pr.getHeight() * 0.85f).withTrimmedRight (pr.getHeight() * 0.3f);
            if (ok)
                ui::icon (g, "icon_heart_teal", text.removeFromRight (pr.getHeight()).reduced (pr.getHeight() * 0.18f));
            ui::label (g, v.pitchText.upToFirstOccurrenceOf (" ", false, false), text, ok ? ui::colour::text : (v.keyOn ? ui::colour::yellow : ui::colour::text), 12.0f);
        }
    }
}

PandaStage::P PandaStage::chipAnchor (const PieceView& v) const
{
    // Out of the sticks' way: with the rigged panda the sticks come down from above, so a drum's
    // chip sits on its shell and the hi-hat's under it.
    return v.type == PieceType::Kick                 ? P (v.pos.x - v.radius - 70.0f, 712.0f)
         : rig && v.type == PieceType::HiHat         ? v.pos.translated (0.0f, v.radius * v.squash + 40.0f)
         : isCymbal (v.type)                         ? v.pos.translated (0.0f, -v.radius * v.squash - 26.0f)
         : rig                                       ? v.pos.translated (0.0f, v.radius * v.squash + v.shell * 0.45f)
                                                     : v.pos.translated (0.0f, -v.radius * v.squash - 22.0f);
}

void PandaStage::drawChips (juce::Graphics& g)
{
    // What just played: round robin, velocity and zone on the pack's readout, in the zone's colour.
    for (auto& v : views)
    {
        auto age = (float) (now - v.lastAt);
        if (age < 0.0f || age > 1.5f || v.last.zone < 0)
            continue;
        auto alpha = age < 0.9f ? 1.0f : 1.0f - (age - 0.9f) / 0.6f;
        auto pop = 1.0f + 0.22f * std::exp (-age / 0.05f);
        auto anchor = chipAnchor (v);
        auto& e = v.last;
        juce::String rr = "RR " + juce::String (e.round + 1) + "/" + juce::String (e.roundCount);
        juce::String vel = "VEL " + juce::String (e.velocityIn);
        juce::String zone = "ZONE " + juce::String (e.zone + 1) + "/" + juce::String (e.zoneCount);
        if ((e.flags & HitEvent::chromatic) != 0)
            zone = pitchName (proc.getNaturalMidi (v.piece) + e.semis).upToFirstOccurrenceOf (" ", false, false);

        juce::Graphics::ScopedSaveState s (g);
        g.addTransform (juce::AffineTransform::scale (pop, pop, anchor.x, anchor.y));
        auto box = juce::Rectangle<float> (206.0f, 28.0f).withCentre (anchor);
        box.setX (juce::jlimit (4.0f, designW - 210.0f, box.getX()));
        box.setY (std::max (4.0f, box.getY()));
        auto t = e.zoneCount > 1 ? (float) e.zone / (float) (e.zoneCount - 1) : 1.0f;
        auto piece = t < 0.34f ? "readout_zone" : (t < 0.67f ? "readout_midi" : "readout_hit");
        auto zc = colour::zone (e.zone, e.zoneCount);
        g.setColour (juce::Colours::black.withAlpha (0.25f * alpha));
        g.fillRoundedRectangle (box.translated (0.0f, 3.0f).reduced (2.0f, 1.0f), 13.0f);
        ui::readout (g, piece, box, alpha);
        auto r = box.withTrimmedLeft (box.getHeight() * 0.95f).withTrimmedRight (11.0f);
        ui::label (g, rr, r.removeFromLeft (54.0f), colour::text.withAlpha (alpha), 12.5f, juce::Justification::centredLeft);
        ui::label (g, vel, r.removeFromLeft (62.0f), colour::gold.withAlpha (alpha), 12.5f, juce::Justification::centredLeft);
        ui::label (g, zone, r, zc.withAlpha (alpha), 12.5f, juce::Justification::centredRight);
    }
}

//==============================================================================
void PandaStage::mouseMove (const juce::MouseEvent& e)
{
    auto d = toDesign (e.position);
    auto oldPiece = hoverPiece;
    auto oldButton = hoverButton;
    hoverPiece = -1;
    hoverButton = {};
    for (auto& v : views)
    {
        if ((v.piece == selected || v.piece == hoverPiece) && v.tag.contains (d))
        {
            hoverPiece = v.piece;
            hoverButton = v.prevBtn.contains (d) ? "prev" : v.nextBtn.contains (d) ? "next"
                        : v.downBtn.contains (d) ? "down" : v.upBtn.contains (d) ? "up" : "tag";
            break;
        }
    }
    if (hoverPiece < 0)
        for (auto it = views.rbegin(); it != views.rend(); ++it)
            if (it->hitArea.contains (d))
            {
                hoverPiece = it->piece;
                hoverButton = "drum";
                break;
            }
    setMouseCursor (hoverPiece >= 0 ? juce::MouseCursor::PointingHandCursor : juce::MouseCursor::NormalCursor);
    if (hoverButton == "prev" || hoverButton == "next")      setTooltip ("Swap to the previous / next drum");
    else if (hoverButton == "up" || hoverButton == "down")   setTooltip ("Tune up / down to the next note in the key");
    else if (hoverButton == "drum")                          setTooltip ("Click to play (centre = loud). Right-click for every articulation.");
    else                                                     setTooltip ({});
    if (oldPiece != hoverPiece || oldButton != hoverButton)
        repaint();
}

void PandaStage::mouseExit (const juce::MouseEvent&)
{
    hoverPiece = -1;
    hoverButton = {};
    repaint();
}

void PandaStage::mouseDown (const juce::MouseEvent& e)
{
    mouseMove (e);
    if (hoverPiece < 0)
        return;
    auto piece = hoverPiece;
    if (hoverButton == "prev" || hoverButton == "next")
    {
        proc.stepVariant (piece, hoverButton == "next" ? 1 : -1);
        refreshKit();
    }
    else if (hoverButton == "up" || hoverButton == "down")
    {
        proc.stepPitch (piece, hoverButton == "up" ? 1 : -1);
        updateLabels();
        proc.play (piece, 0, 100);
    }
    else if (e.mods.isPopupMenu())
    {
        auto snap = proc.getSnapshot();
        if (snap == nullptr || ! juce::isPositiveAndBelow (piece, (int) snap->pieces.size()) || snap->pieces[(size_t) piece].data == nullptr)
            return;
        juce::PopupMenu m;
        auto& artics = snap->pieces[(size_t) piece].data->artics;
        for (size_t a = 0; a < artics.size(); ++a)
            m.addItem ((int) a + 1, "Play " + artics[a].name);
        m.showMenuAsync (juce::PopupMenu::Options().withTargetComponent (this).withMousePosition(), [this, piece] (int r)
        {
            if (r > 0)
                proc.play (piece, r - 1, 110);
        });
    }
    else
    {
        auto& v = views[(size_t) piece];
        auto d = toDesign (e.position);
        int vel = 110;
        if (v.type != PieceType::Kick && ! isCymbal (v.type))
        {
            auto dx = (d.x - v.pos.x) / v.radius, dy = (d.y - v.pos.y) / (v.radius * v.squash);
            vel = juce::jlimit (25, 127, (int) (127.0f - 85.0f * std::min (1.0f, std::sqrt (dx * dx + dy * dy))));
        }
        if (e.mods.isShiftDown()) vel = 127;
        if (e.mods.isAltDown())   vel = 35;
        proc.play (piece, 0, vel);
    }
    selected = piece;
    if (onSelect)
        onSelect (piece);
    repaint();
}

//==============================================================================
// The rigged panda: the picture's torso and head, moving on their own, and two arms that play
// the way a drummer does. A stroke is the stick turning about the fulcrum in his fist: up off the
// head on the rebound, held at the height the next stroke needs, then dropped (faster and faster)
// onto the head on time; the wrist does a tap, the forearm joins in for the loud ones. The stick
// turns in 3D (it points at us when it's on a drum), so on screen it shortens and swings.
namespace
{
constexpr float camTilt = 0.26f;      // the camera looks down on him a little (~15 degrees)
constexpr float degrees = juce::MathConstants<float>::pi / 180.0f;
constexpr float topPitch = 75.0f * degrees;    // the stick at the top of a full stroke (and in the picture)

// A stick's direction (heading across the floor: 0 toward us, + to screen right; pitch above the
// floor) as it shows on screen, per unit of its length.
juce::Point<float> onScreen (float heading, float pitch)
{
    auto X = std::cos (pitch) * std::sin (heading), Y = std::sin (pitch), Z = std::cos (pitch) * std::cos (heading);
    return { X, -Y * std::cos (camTilt) + Z * std::sin (camTilt) };
}

float smooth (float u) { u = juce::jlimit (0.0f, 1.0f, u); return u * u * (3.0f - 2.0f * u); }

// From rest to rest with no kick at either end: how a hand moves (Flash and Hogan's minimum jerk).
float minimumJerk (float u) { u = juce::jlimit (0.0f, 1.0f, u); return u * u * u * (10.0f - 15.0f * u + 6.0f * u * u); }
}

juce::AffineTransform PandaStage::torsoTransform() const
{
    auto seat = Skin::point (Skin::get().at ("panda/seat"));
    auto nodBy = pose.head - pose.torso;
    // His chest rises and falls with his breath and drops with the kick; he turns into a lean.
    // (A turn smaller than a sixth of a degree is left out, so his body is copied, not redrawn.)
    auto turn = pose.tilt * 0.25f + bodyLean.x * 0.0022f;
    turn = turn > 0.0f ? std::max (0.0f, turn - 0.003f) : std::min (0.0f, turn + 0.003f);
    return juce::AffineTransform::translation (-seat.x, -seat.y)
        .scaled (pandaScale)
        .rotated (turn)
        .translated (seat.x + bodyLean.x + nodBy.x * 0.3f,
                     seat.y + pose.bodyBounce + nodBy.y * 0.3f + std::abs (bodyLean.x) * 0.12f - 1.1f * pose.breath
                         + 3.0f * (1.0f - pose.squash));
}

juce::AffineTransform PandaStage::headTransform() const
{
    auto neck = Skin::point (Skin::get().at ("panda/neck"));
    auto nodBy = pose.head - pose.torso;
    return juce::AffineTransform::rotation (pose.tilt * 1.2f + juce::jlimit (-0.14f, 0.14f, headLean.x * 0.09f), neck.x, neck.y)
        .translated (nodBy.x * 0.7f, nodBy.y * 0.7f + juce::jlimit (-4.0f, 18.0f, headDip.x * 0.12f))
        .followedBy (torsoTransform());
}

std::array<juce::Point<float>, 4> PandaStage::bodyPoints() const
{
    auto neck = Skin::point (Skin::get().at ("panda/neck"));
    auto seat = Skin::point (Skin::get().at ("panda/seat"));
    auto H = headTransform(), T = torsoTransform();
    return { (neck + P (0.0f, -150.0f)).transformedBy (H), (neck + P (110.0f, -70.0f)).transformedBy (H),
             (seat + P (-120.0f, -110.0f)).transformedBy (T), (seat + P (120.0f, -110.0f)).transformedBy (T) };
}

juce::Rectangle<float> PandaStage::pieceBounds (const PieceView& v) const
{
    auto& skin = Skin::get();
    auto kind = skinKind (v);
    auto anchor = Skin::point (skin.at ("kit/" + kind + "/anchor"));
    juce::Rectangle<float> r;
    auto add = [&] (const juce::String& file, const juce::AffineTransform& t)
    {
        if (auto sp = skin.sprite (file); sp.isValid())
            r = r.isEmpty() ? sp.bounds.transformedBy (t) : r.getUnion (sp.bounds.transformedBy (t));
    };
    if (v.type == PieceType::HiHat)
    {
        auto move = juce::AffineTransform::translation (v.pos - anchor);
        add (skin.at ("kit/hihat/top_file").toString(), move);
        add (skin.at ("kit/hihat/bottom_file").toString(), move);
        r = r.withTop (r.getY() - 24.0f).expanded (6.0f, 4.0f);
    }
    else if (isCymbal (v.type))
    {
        auto sc = v.radius / Skin::number (skin.at ("kit/" + kind + "/radius"), v.radius);
        auto t = juce::AffineTransform::translation (-anchor.x, -anchor.y);
        add (skin.at ("kit/" + kind + "/file").toString(), t.scaled (sc).translated (v.pos.x, v.pos.y));
        add (skin.at ("kit/" + kind + "/file").toString(), t.scaled (-sc, sc).translated (v.pos.x, v.pos.y));
        r = r.expanded (10.0f, r.getHeight() * 0.3f + 10.0f);      // its swing and squash
    }
    else
    {
        auto t = pieceTransform (v, anchor, Skin::number (skin.at ("kit/" + kind + "/radius"), v.radius));
        add (skin.at ("kit/" + kind + "/wraps/purple").toString(), t);
        r = r.expanded (6.0f, 10.0f);                            // its thump
    }
    return r.expanded (4.0f);
}

bool PandaStage::pieceMoving (const PieceView& v) const
{
    auto st = drumState (v);
    auto kt = (float) (now - v.rippleAt) / 0.4f;
    return std::abs (v.wobble.x) > 1.0e-4f || std::abs (v.wobble.v) > 1.0e-3f
        || std::abs (v.pulse.x) > 1.0e-3f || std::abs (v.pulse.v) > 1.0e-2f
        || std::abs (v.gap.x - v.gap.target) > 1.0e-3f || std::abs (v.gap.v) > 1.0e-2f
        || st.flash > 0.004f || st.ripple >= 0.0f || (! rig && kt >= 0.0f && kt < 1.0f);
}

juce::Rectangle<float> PandaStage::pandaBounds() const
{
    auto& skin = Skin::get();
    juce::Rectangle<float> r;
    auto add = [&] (juce::Rectangle<float> b) { r = r.isEmpty() ? b : r.getUnion (b); };
    auto T = torsoTransform(), H = headTransform();
    for (auto* key : { "panda/torso", "panda/sleeves" })
    {
        auto v = skin.at (key);
        if (auto* a = v.getArray())
            for (auto& item : *a)
                add (skin.sprite (item.toString()).bounds.transformedBy (T));
        else
            add (skin.sprite (v.toString()).bounds.transformedBy (T));
    }
    if (auto* rest = skin.at ("panda/rest").getArray())
        for (auto& item : *rest)
            add (skin.sprite (item.toString()).bounds.transformedBy (T));
    add (skin.sprite (skin.at ("panda/head_file").toString()).bounds.transformedBy (H));
    add (skin.sprite (skin.at ("panda/faces/" + face + "/file").toString()).bounds.transformedBy (H));
    auto reach = Skin::number (skin.at ("panda/fur/radius"), 32.0f) * pandaScale * 1.2f + 60.0f * pandaScale;
    // (a point at a time: a rectangle's union skips empty ones, and a point is one)
    auto include = [] (juce::Rectangle<float> box, P p)
    {
        return juce::Rectangle<float>::leftTopRightBottom (std::min (box.getX(), p.x), std::min (box.getY(), p.y),
                                                          std::max (box.getRight(), p.x), std::max (box.getBottom(), p.y));
    };
    for (size_t i = 0; i < 2; ++i)
    {
        auto& a = shownArms[i];
        auto arm = juce::Rectangle<float> (a.shoulder, a.shoulder);
        for (auto p : { a.wrist, a.pivot, a.tip, a.butt, a.contact, a.elbow })
            arm = include (arm, p);
        // The stick's blur sweeps round from where it was last frame: an arc that can bulge
        // past both ends.
        if (haveLastArms[i])
        {
            auto& was = lastArms[i];
            auto turn = std::remainder (a.angle - was.angle, juce::MathConstants<float>::twoPi);
            for (int k = 0; k <= 8; ++k)
            {
                auto u = (float) k / 8.0f;
                auto pivot = was.pivot + (a.pivot - was.pivot) * u;
                auto angle = was.angle + turn * u;
                auto len = std::max (was.tip.getDistanceFrom (was.pivot), a.tip.getDistanceFrom (a.pivot));
                auto tip = pivot + P (std::cos (angle), std::sin (angle)) * len;
                arm = include (include (arm, tip), pivot);
            }
        }
        add (arm.expanded (reach));
    }
    return r.expanded (6.0f);
}

juce::RectangleList<int> PandaStage::changedArea()
{
    juce::RectangleList<float> now_;
    auto everythingNow = everything || ! rig || ! Skin::get().isLoaded() || std::abs (shake.x) > 0.01f;
    everything = false;
    if (! everythingNow)
    {
        auto& skin = Skin::get();
        now_.add (pandaBounds());
        for (auto& v : views)
        {
            v.stillFrames = pieceMoving (v) ? 0 : std::min (99, v.stillFrames + 1);
            if (v.sharesWith < 0 && v.stillFrames <= 3)
                now_.add (pieceBounds (v));
        }
        for (auto& v : views)
        {
            // Hit pop-ups (drawn each frame as they pop, hold and fade) and the selection's glow.
            auto age = (float) (now - v.lastAt);
            if (proc.showHitInfo && age >= -0.05f && age <= 1.6f)
            {
                // (where drawChips puts it, popping up to 1.22x about its anchor)
                auto anchor = chipAnchor (v);
                auto box = juce::Rectangle<float> (206.0f, 28.0f).withCentre (anchor);
                box.setX (juce::jlimit (4.0f, designW - 210.0f, box.getX()));
                box.setY (std::max (4.0f, box.getY()));
                now_.add (box.getUnion (box.transformedBy (juce::AffineTransform::scale (1.25f, 1.25f, anchor.x, anchor.y))).expanded (6.0f));
            }
            if (v.piece == selected || v.piece == hoverPiece)
            {
                now_.add (pieceBounds (v).expanded (14.0f));
                now_.add (v.tag.expanded (12.0f));
            }
        }
        if (auto* bulbs = skin.at ("stage/bulbs").getArray())
            for (auto& b : *bulbs)
                now_.add (juce::Rectangle<float> (84.0f, 84.0f).withCentre (Skin::point (b.getProperty ("at", {}))));
        for (auto& p : particles)
            now_.add (juce::Rectangle<float> (p.size * 3.2f + 12.0f, p.size * 3.2f + 12.0f).withCentre (p.pos));
        for (auto& f : fx)
            if (auto sp = skin.sprite (skin.at ("panda/fx/" + f.sprite).toString()); sp.isValid())
            {
                // (turned any way and growing up to 1.2x: its half diagonal, and some)
                auto radius = std::hypot (sp.bounds.getWidth(), sp.bounds.getHeight()) * 0.5f * std::abs (f.scale) * 1.25f + 8.0f;
                now_.add (juce::Rectangle<float> (radius * 2.0f, radius * 2.0f).withCentre (f.pos));
            }
        for (auto& b : bursts)
            now_.add (juce::Rectangle<float> (380.0f, 260.0f).withCentre (b.pos));
    }
    else
        now_.add ({ 0.0f, 0.0f, designW, designH });

    auto both = now_;
    both.add (lastChanged);
    lastChanged = now_;
    auto t = designTransform();
    juce::RectangleList<int> out;
    for (auto& r : both)
        out.add (r.transformedBy (t).getSmallestIntegerContainer().expanded (2));
    out.consolidate();
    return out;
}

void PandaStage::repaintChanged()
{
    for (auto& r : changedArea())
        repaint (r);
}

void PandaStage::drawLayer (juce::Graphics& g, const Skin::Sprite& sprite, const juce::AffineTransform& t, float alpha)
{
    auto& skin = Skin::get();
    if (! sprite.isValid() || alpha <= 0.0f)
        return;
    auto d = t.followedBy (stageToDevice);
    auto sx = d.mat00, sy = d.mat11;
    static const bool off = juce::SystemStats::getEnvironmentVariable ("PD_NO_LAYER_CACHE", {}).isNotEmpty();
    if (off || std::abs (d.mat01) > 1.0e-5f * std::abs (sx) || std::abs (d.mat10) > 1.0e-5f * std::abs (sy)
        || std::abs (sx) < 0.05f || std::abs (sy) < 0.05f)
    {
        // Turning: drawn from the art each frame. Bilinear is as good as anything while it moves
        // (and on a Mac, CoreGraphics' best filter costs several times as much).
        g.setImageResamplingQuality (juce::Graphics::mediumResamplingQuality);
        skin.draw (g, sprite, t, alpha);
        g.setImageResamplingQuality (juce::Graphics::highResamplingQuality);
        return;
    }
    auto key = sprite.name + "|" + juce::String (juce::roundToInt (sx * 4096.0f)) + "|" + juce::String (juce::roundToInt (sy * 4096.0f));
    auto found = layerCache.find (key);
    if (found == layerCache.end())
    {
        // Only a layer shown the same way two frames running is worth drawing into the cache.
        auto& asked = layerAsked[key];
        if (asked.last != frameNo)
        {
            asked.before = asked.last;
            asked.last = frameNo;
        }
        if (asked.before != frameNo - 1)
        {
            skin.draw (g, sprite, t, alpha);
            return;
        }
        auto b = sprite.bounds;
        auto xa = sx * b.getX(), xb = sx * b.getRight(), ya = sy * b.getY(), yb = sy * b.getBottom();
        auto x0 = std::floor (std::min (xa, xb)), y0 = std::floor (std::min (ya, yb));
        auto w = (int) std::ceil (std::max (xa, xb) - x0) + 1, h = (int) std::ceil (std::max (ya, yb) - y0) + 1;
        if (w * h > 6000000)
        {
            skin.draw (g, sprite, t, alpha);
            return;
        }
        CachedLayer layer;
        layer.image = juce::Image (juce::Image::ARGB, std::max (1, w), std::max (1, h), true);
        layer.x0 = x0;
        layer.y0 = y0;
        {
            juce::Graphics cg (layer.image);
            cg.setImageResamplingQuality (juce::Graphics::highResamplingQuality);
            skin.draw (cg, sprite, juce::AffineTransform::scale (sx, sy).translated (-x0, -y0));
        }
        found = layerCache.emplace (key, std::move (layer)).first;
        if (layerAsked.size() > 4096)
            layerAsked.clear();
    }
    auto& layer = found->second;
    layer.used = frameNo;
    // Onto whole screen pixels: copied as it is, no resampling.
    auto ix = std::round (layer.x0 + d.getTranslationX()), iy = std::round (layer.y0 + d.getTranslationY());
    g.setOpacity (juce::jlimit (0.0f, 1.0f, alpha));
    g.drawImageTransformed (layer.image, juce::AffineTransform::translation (ix, iy).followedBy (deviceToStage));
    g.setOpacity (1.0f);
}

PandaStage::P PandaStage::rigStrikePoint (const PieceView& v, int hand) const
{
    auto toward = v.pos.x < centreX ? 1.0f : -1.0f;        // toward his middle
    auto across = v.radius * v.squash;
    if (v.type == PieceType::HiHat)
    {
        // The top cymbal's near edge, wherever the pedal holds it.
        auto& skin = Skin::get();
        auto top = Skin::point (skin.at ("kit/hihat/top")) + (v.pos - Skin::point (skin.at ("kit/hihat/anchor")));
        return top.translated (toward * v.radius * 0.5f, -juce::jlimit (0.0f, 18.0f, (v.gap.x - 1.5f) * 0.9f) + across * 0.2f);
    }
    if (v.type == PieceType::Ride)
        return v.pos.translated (toward * v.radius * 0.45f, across * 0.2f);
    if (isCymbal (v.type))
        return v.pos.translated (toward * v.radius * 0.78f, across * 0.3f);
    if (v.type == PieceType::Kick)
        return v.pos;
    // A drum: just in front of the middle of the head, a little toward the hand playing it.
    return v.pos.translated ((hand == 0 ? -1.0f : 1.0f) * v.radius * 0.12f, across * 0.25f);
}

float PandaStage::strokeAt (const Hand& h, double t) const
{
    // A stick's height (0 on the head ... 1 straight up) moves like a drummer's: every stroke is
    // one smooth curve from wherever the stick is, at the speed it's going (cubic Hermite pieces,
    // so it never changes speed in a jump), and only the head stops it.
    // Between strokes it waits at the height this hand has been playing at (a hand playing
    // backbeats stays up, a hand playing quiet notes stays low), bobbing a little with the groove.
    auto hover = juce::jlimit (0.16f, 0.85f, h.ready) + 0.015f * std::sin ((float) t * 5.3f + (float) h.side * 2.0f);
    constexpr float maxRise = 5.5f;      // a wrist lifts the stick no faster than this (heights a second)
    auto hermite = [] (float u, float span, float h0, float v0, float h1, float v1)
    {
        auto u2 = u * u, u3 = u2 * u;
        return (2.0f * u3 - 3.0f * u2 + 1.0f) * h0 + (u3 - 2.0f * u2 + u) * span * v0
             + (3.0f * u2 - 2.0f * u3) * h1 + (u3 - u2) * span * v1;
    };
    // Off the head: it sits there a frame (the eye needs to see it land), leaves at the speed it
    // bounces at, and eases up to where the hand waits, in about 40% of the time between its strokes.
    auto after = [&] (const Strike& s, double at)
    {
        auto d = (float) (at - s.time) - strokeDwell;
        if (d <= 0.0f)
            return 0.0f;
        auto span = juce::jlimit (0.09f, 0.28f, 0.4f * h.ioi);
        auto v0 = std::min (reboundSpeed (s.vel), 2.5f * hover / span);
        return d < span ? std::max (0.0f, hermite (d / span, span, 0.0f, v0, hover, 0.0f)) : hover;
    };
    if (h.next.piece >= 0 && t < h.next.time)
    {
        // The next stroke: from where the stick was when it was known, up to the height this stroke
        // needs if there's room (an accent's upstroke), then down onto the head like a whip, slow
        // at the top and fastest as it lands.
        auto target = strokeHeightFor (h.next.vel);
        auto t0 = std::min (h.nextFromT, t);
        auto h0 = h.nextFromH, v0 = h.nextFromV;
        auto window = (float) std::max (1.0e-3, h.next.time - t0);
        auto fall = 0.035f + 0.075f * std::max (target, h0);       // a full stroke falls in ~110 ms
        auto x = (float) (t - t0);
        if (window <= fall * 1.1f)
        {
            // No time for a whole stroke: one curve from the stick as it is onto the head, as high
            // as there's time for on the way.
            auto top = std::max (h0, std::min (target, h0 + maxRise * window * 0.25f));
            auto vIn = whipPower * std::max (top, 0.08f) / std::max (0.03f, window);
            return std::max (0.0f, hermite (x / window, window, h0, v0, 0.0f, -vIn));
        }
        // Room to spare: up to the height (the rebound carrying into it), wait there if there's
        // time, then the stroke.
        auto drop = window - fall;
        auto peak = std::max (target, 0.12f);
        auto rise = std::min (drop, 0.1f + 0.08f * peak + 0.25f * std::abs (peak - h0));
        if (peak > h0)
            peak = std::min (peak, h0 + maxRise / 1.875f * rise);
        if (x < rise)
            return std::max (0.0f, hermite (x / rise, rise, h0, v0, peak, 0.0f));
        if (x < drop)
            return peak;
        auto u = (x - drop) / fall;
        return peak * (1.0f - std::pow (u, whipPower));
    }
    if (h.next.piece >= 0)
        return after (h.next, t);
    if (h.last.piece >= 0 && t >= h.last.time)
        return after (h.last, t);
    return hover;
}

float PandaStage::homeWeight (const Hand& h, double t) const
{
    // How much the hand is in the picture's pose: settling into it after a while with nothing to
    // play, and on the way out of it to the first stroke after a rest.
    auto w = smooth (h.home);
    if (t < h.homeFadeEnd && h.homeFadeEnd > h.homeFadeStart)
        w = std::max (w, h.homeFrom * (1.0f - easeInOut ((float) ((t - h.homeFadeStart) / (h.homeFadeEnd - h.homeFadeStart)))));
    return juce::jlimit (0.0f, 1.0f, w);
}

PandaStage::Arm PandaStage::armPose (const Hand& h, double t) const
{
    auto& skin = Skin::get();
    auto T = torsoTransform();
    auto inward = h.side == 0 ? 1.0f : -1.0f;              // toward his middle on screen
    Arm a;
    auto contact = 0.98f;
    if (auto* arr = skin.at ("panda/shoulders").getArray(); arr != nullptr && arr->size() > h.side)
        a.shoulder = Skin::point ((*arr)[h.side]).transformedBy (T);

    auto ps = pandaScale;
    auto L3 = Skin::number (skin.at ("panda/stick/real"), 150.0f) * ps;   // the stick's real length, fulcrum to tip
    // The hand rises with the stroke: the wrist for a tap, the forearm and shoulder for the loud
    // ones, the elbow swinging out as it goes. On a cymbal it's mostly the wrist.
    auto onCymbalNow = juce::isPositiveAndBelow (h.piece, (int) views.size()) && isCymbal (views[(size_t) h.piece].type);
    auto liftScale = onCymbalNow ? 0.55f : 1.0f;
    if (t < h.moveEnd && h.moveEnd > h.moveStart)       // (changing over on the way from the last thing played)
        liftScale = h.fromLift + (liftScale - h.fromLift) * easeInOut ((float) ((t - h.moveStart) / (h.moveEnd - h.moveStart)));
    auto liftOf = [ps, liftScale] (float H) { return ps * liftScale * (9.0f * H + 30.0f * H * H); };
    auto lift = liftOf;
    auto outward = h.side == 0 ? -1.0f : 1.0f;
    auto headEllipse = skin.at ("panda/head/ellipse");
    auto headRadii = headEllipse.size() == 4 ? P ((float) (double) headEllipse[2], (float) (double) headEllipse[3]) * ps : P (150.0f, 115.0f);
    auto fistRadius = 36.0f * ps;
    // Going up, the forearm turns the stick out (the sticks open into a V), away from his face.
    constexpr float rise = 22.0f * degrees;

    // At rest he holds his sticks exactly as in the picture: the right one up, the left one level.
    auto home = skin.at ("panda/home")[h.side];
    auto homePivot = Skin::point (home.getProperty ("pivot", {})).transformedBy (T);
    auto homeHeading = (float) (double) home.getProperty ("heading", 0.9);
    auto homePitch = (float) (double) home.getProperty ("pitch", 1.3);

    // Where the fist is, and how the stick points, with it on the head of what it's playing.
    auto hitPivot = homePivot;
    auto hd = homeHeading, hp = homePitch;
    if (juce::isPositiveAndBelow (h.piece, (int) views.size()))
    {
        auto& v = views[(size_t) h.piece];
        auto S = rigStrikePoint (v, h.side);
        float reach = 110.0f, hitPitch = -7.0f;     // a drum: the tip, the stick nearly flat to the head
        if (v.type == PieceType::HiHat)     { reach = 45.0f; hitPitch = 3.0f; contact = 0.88f; }    // across the top, from the side
        else if (v.type == PieceType::Ride) { reach = 70.0f; hitPitch = -2.0f; contact = 0.93f; }   // the tip on the bow
        else if (isCymbal (v.type))         { reach = 70.0f; hitPitch = v.type == PieceType::China ? 2.0f : 8.0f; contact = 0.72f; }   // the stick's shoulder on the edge
        // Which way the stick comes in across the floor: from the shoulder toward the piece. A
        // drum's stick comes in at no more than 50 degrees across (the hand stays over the drum's
        // near side); cymbals can be played from further round; never straight at us.
        auto most = (isCymbal (v.type) ? 72.0f : 50.0f) * degrees;
        P restShoulder;
        if (auto* arr = skin.at ("panda/shoulders").getArray(); arr != nullptr && arr->size() > h.side)
            restShoulder = Skin::point ((*arr)[h.side]);
        auto rawFrom = [&] (P shoulder)
        {
            return juce::jlimit (-most, most, std::atan2 (S.x - shoulder.x, reach) + inward * (isCymbal (v.type) ? 0.0f : 10.0f * degrees));
        };
        // Never straight at us: at least 12 degrees round, to the side it comes in from when he
        // sits still (decided once for the piece, so it can't flip over as he sways), a soft limit.
        auto restRaw = rawFrom (restShoulder);
        auto side = std::abs (restRaw) < 1.0e-4f ? inward : (restRaw > 0.0f ? 1.0f : -1.0f);
        auto headingFrom = [&] (P shoulder)
        {
            constexpr float least = 12.0f * degrees, soft = 3.0f * degrees;
            auto z = (rawFrom (shoulder) * side - least) / soft;
            return side * (least + soft * (z > 20.0f ? z : std::log1p (std::exp (z))));
        };
        hd = headingFrom (a.shoulder);
        hp = hitPitch * degrees;
        // His fist never goes up in front of his face. Where it meets the head, the fist must be
        // below his chin (with room for his head dipping into the hit): the stick comes in from
        // further round (a left stick on the snare angles in from the hi-hat side, under his
        // face) or, for a piece out to his side, points more at us (the hand stays out by the
        // piece, the way a drummer's does over the hi-hat). It's the nearest heading that clears,
        // planned once for the piece from him sitting still, so it never flickers as he moves.
        {
            auto plan = S;
            if (v.type == PieceType::HiHat)
                plan.y += juce::jlimit (0.0f, 18.0f, (v.gap.x - 1.5f) * 0.9f);       // (the hi-hat shut)
            auto planLift = ps * (onCymbalNow ? 0.55f : 1.0f) * 39.0f;        // (a full stroke's lift)
            auto restHead = headEllipse.size() == 4 ? P ((float) (double) headEllipse[0], (float) (double) headEllipse[1]) : P (centreX, 180.0f);
            auto clearOf = [&] (P fist, float room)        // how far below his chin a fist is (< 0: on his face)
            {
                auto dx = (fist.x - restHead.x) / (headRadii.x + fistRadius);
                if (std::abs (dx) >= 1.0f)
                    return 1000.0f;
                return fist.y - (restHead.y + (headRadii.y + fistRadius) * std::sqrt (1.0f - dx * dx) + room);
            };
            auto fistAt = [&] (float heading) { return plan - onScreen (heading, hp) * (contact * L3); };
            // At the top of a full stroke (if it could rise that far) and on the head.
            auto clears = [&] (float heading)
            {
                return clearOf (fistAt (heading), 14.0f * ps) >= 0.0f
                    && (isCymbal (v.type) ? clearOf (fistAt (heading) - P (outward * 0.5f * planLift, planLift), 0.0f) >= 0.0f : true);
            };
            auto natural = headingFrom (restShoulder);
            if (! clears (natural))
            {
                auto best = natural;
                for (int step = 1; step <= 140; ++step)
                {
                    auto d = (float) step * 0.5f * degrees;
                    auto wider = juce::jlimit (-80.0f * degrees, 80.0f * degrees, natural + d);
                    auto narrower = juce::jlimit (-80.0f * degrees, 80.0f * degrees, natural - d);
                    // (the stick never points at his body: a fist out past the piece, on its own side)
                    auto ok = [&] (float hh) { return std::abs (hh) >= 12.0f * degrees && clears (hh); };
                    if (ok (wider)) { best = wider; break; }
                    if (ok (narrower)) { best = narrower; break; }
                }
                hd += best - natural;
            }
        }
        hitPivot = S - onScreen (hd, hp) * (contact * L3);
        // On the way from the last thing played: an arc, the stick turning as it goes.
        if (t < h.moveEnd && h.moveEnd > h.moveStart)
        {
            // A minimum-jerk reach (how a hand really moves from one place to another): it
            // eases out and in with no kick in its acceleration at either end.
            auto u = minimumJerk ((float) ((t - h.moveStart) / (h.moveEnd - h.moveStart)));
            auto arc = std::min (34.0f, h.from.getDistanceFrom (hitPivot) * 0.22f) * std::sin (u * juce::MathConstants<float>::pi);
            hitPivot = h.from + (hitPivot - h.from) * u - P (0.0f, arc);
            hd = h.fromHeading + (hd - h.fromHeading) * u;
            hp = h.fromPitch + (hp - h.fromPitch) * u;
        }
    }
    a.strikePivot = hitPivot;
    a.heading = hd;
    a.pitch = hp;

    // The stroke. The hand leads the stick a little on the way down (the wrist snaps it after).
    auto H = strokeAt (h, t), handH = strokeAt (h, t + 0.018);
    a.height = H;
    auto pitchNow = hp + (topPitch - hp) * std::min (H, 1.15f);
    auto headingNow = juce::jlimit (-80.0f * degrees, 80.0f * degrees, hd - inward * rise * std::min (H, 1.0f));
    auto up = lift (std::min (handH, 1.15f));
    auto pivotNow = hitPivot - P (outward * 0.5f * up, up);
    // Going up, the fist stops under his chin (wherever his head is now): the stick goes on up
    // from the wrist, past his face, but the hand doesn't. A soft stop (a smooth max), never a kink,
    // and never lower than where it meets the head.
    if (up > 0.0f)
    {
        auto c = (headEllipse.size() == 4 ? P ((float) (double) headEllipse[0], (float) (double) headEllipse[1]) : P (centreX, 180.0f))
                     .transformedBy (headTransform());
        auto dx = (pivotNow.x - c.x) / (headRadii.x + fistRadius);
        if (std::abs (dx) < 1.0f)
        {
            auto chin = c.y + (headRadii.y + fistRadius) * std::sqrt (1.0f - dx * dx);
            constexpr float soft = 6.0f;
            auto z = (pivotNow.y - chin) / soft;
            auto pushed = chin + soft * (z > 20.0f ? z : std::log1p (std::exp (z)));
            pivotNow.y = std::min (hitPivot.y, pushed);
        }
    }

    // Into and out of the picture's pose.
    auto w = homeWeight (h, t);
    pivotNow += (homePivot - pivotNow) * w;
    headingNow += (homeHeading - headingNow) * w;
    pitchNow += (homePitch - pitchNow) * w;

    // Arms up after a good run, sticks waving.
    if (t < cheerUntil)
    {
        auto wave = std::sin ((float) t * 13.0f + (float) h.side * 1.6f);
        auto k = easeOutCubic ((float) (1.6 - (cheerUntil - t)) / 0.2f) * std::min (1.0f, (float) (cheerUntil - t) / 0.2f);
        auto raised = a.shoulder + P (-inward * (72.0f + 10.0f * wave), -125.0f) * ps;
        pivotNow += (raised - pivotNow) * k;
        headingNow += (-inward * (25.0f + 12.0f * wave) * degrees - headingNow) * k;
        pitchNow += (80.0f * degrees - pitchNow) * k;
    }
    a.pivot = pivotNow;

    auto dir = onScreen (headingNow, pitchNow);
    a.angle = std::atan2 (dir.y, dir.x);
    auto twirling = t - h.twirlAt < 0.7;
    if (twirling)
        a.angle += juce::MathConstants<float>::twoPi * easeInOut ((float) ((t - h.twirlAt) / 0.7)) * inward;
    auto shown = dir.getDistanceFromOrigin();
    auto unit = P (std::cos (a.angle), std::sin (a.angle));
    a.tip = a.pivot + unit * (L3 * shown);
    a.butt = a.pivot - unit * (Skin::number (skin.at ("panda/stick/butt"), 46.0f) * L3 / Skin::number (skin.at ("panda/stick/length"), 138.0f) * shown);
    a.scale = ps;
    a.liftScale = liftScale;
    a.contact = a.pivot + (a.tip - a.pivot) * contact;
    a.atRest = w > 0.999f && t >= cheerUntil && ! twirling;

    // The fist turns with the stick's heading (the forearm turning it), not all the way.
    auto fist = skin.at ("panda/fists")[h.side];
    a.fistTurn = juce::jlimit (-0.7f, 0.7f, 0.35f * (headingNow - homeHeading));
    auto wristOff = Skin::point (fist.getProperty ("wrist", {})) - Skin::point (fist.getProperty ("pivot", {}));
    a.wrist = a.pivot + rotate (wristOff * ps, a.fistTurn);
    return a;
}

void PandaStage::drawArm (juce::Graphics& g, const Arm& a, int side)
{
    auto& skin = Skin::get();
    auto fist = skin.at ("panda/fists")[side];
    auto picPivot = Skin::point (fist.getProperty ("pivot", {}));
    auto stick = skin.sprite (skin.at ("panda/stick/file").toString());
    auto pivotY = Skin::number (skin.at ("panda/stick/pivot_y"), 142.0f);
    auto picLen = Skin::number (skin.at ("panda/stick/length"), 138.0f);
    auto stickT = juce::AffineTransform::translation (-stick.bounds.getWidth() * 0.5f, -pivotY)
                      .scaled (a.scale, a.tip.getDistanceFrom (a.pivot) / picLen)
                      .rotated (a.angle + juce::MathConstants<float>::halfPi)
                      .translated (a.pivot.x, a.pivot.y);
    auto stickPart = [&] (bool tipEnd)
    {
        if (! stick.isValid())
            return;
        juce::Path clip;
        clip.addRectangle (tipEnd ? stick.bounds.withBottom (pivotY) : stick.bounds.withTop (pivotY));
        juce::Graphics::ScopedSaveState state (g);
        g.reduceClipRegion (clip, stickT);
        skin.draw (g, stick, stickT);
    };

    // His arm: a string of balls of his own fur from inside the sleeve to the wrist, along a gentle
    // curve. A long reach straightens it; a short one bends it, the elbow out and down (the rest
    // of the bend goes back, away from us, where it doesn't show).
    if (auto fur = skin.sprite (skin.at ("panda/fur/file").toString()); fur.isValid())
    {
        auto r = Skin::number (skin.at ("panda/fur/radius"), 32.0f) * a.scale;
        auto span = a.wrist.getDistanceFrom (a.shoulder);
        auto along = (a.wrist - a.shoulder) / std::max (1.0f, span);
        auto across = P (-along.y, along.x);
        if (across.x * (side == 0 ? -1.0f : 1.0f) < 0.0f)
            across = -across;
        auto control = a.elbow;
        auto n = std::max (2, (int) std::ceil (std::max (span, a.elbow.getDistanceFrom (a.shoulder) + a.elbow.getDistanceFrom (a.wrist)) / (r * 0.5f)));
        auto c = fur.bounds.getCentre();
        for (int i = 0; i <= n; ++i)
        {
            auto u = (float) i / (float) n;
            auto p = a.shoulder * ((1.0f - u) * (1.0f - u)) + control * (2.0f * u * (1.0f - u)) + a.wrist * (u * u);
            // (the taper in four steps, so each size is drawn once and copied)
            auto taper = 1.0f - 0.08f * std::round (u * 4.0f) / 4.0f;
            drawLayer (g, fur, juce::AffineTransform::translation (-c.x, -c.y).scaled (a.scale * taper).translated (p.x, p.y));
        }
    }
    if (auto* sleeves = skin.at ("panda/sleeves").getArray(); sleeves != nullptr && sleeves->size() > side)
        drawLayer (g, skin.sprite ((*sleeves)[side].toString()), torsoTransform().translated (0.0f, -a.sleeveLift));

    // The stick lies across the front of the fist, as in the picture; on the right its butt shows
    // below the fist, on the left it's inside it.
    auto buttFront = (bool) fist.getProperty ("butt_front", false);
    if (! buttFront)
        stickPart (false);
    drawLayer (g, skin.sprite (fist.getProperty ("file", {}).toString()),
               juce::AffineTransform::translation (-picPivot.x, -picPivot.y).scaled (a.scale).rotated (a.fistTurn).translated (a.pivot.x, a.pivot.y));
    stickPart (true);
    if (buttFront)
        stickPart (false);
}

void PandaStage::drawStickBlur (juce::Graphics& g, const Hand& h, const Arm& a)
{
    // A fast stick blurs, the way a camera's shutter sees a drummer's downstroke: between where it
    // was a frame ago and where it is now, fainter toward the old end.
    auto& skin = Skin::get();
    auto stick = skin.sprite (skin.at ("panda/stick/file").toString());
    auto side = (size_t) h.side;
    if (! stick.isValid() || ! haveLastArms[side] || lastArms[side].atRest)
        return;
    auto& was = lastArms[side];
    auto moved = was.tip.getDistanceFrom (a.tip);
    if (moved < 7.0f)
        return;
    auto pivotY = Skin::number (skin.at ("panda/stick/pivot_y"), 142.0f);
    auto picLen = Skin::number (skin.at ("panda/stick/length"), 138.0f);
    auto steps = juce::jlimit (2, 6, (int) (moved / 14.0f));
    auto turn = std::remainder (a.angle - was.angle, juce::MathConstants<float>::twoPi);
    for (int k = 0; k < steps; ++k)
    {
        auto u = (float) k / (float) steps;                 // 0: last frame ... toward now
        auto pivot = was.pivot + (a.pivot - was.pivot) * u;
        auto angle = was.angle + turn * u;
        auto len = was.tip.getDistanceFrom (was.pivot) + (a.tip.getDistanceFrom (a.pivot) - was.tip.getDistanceFrom (was.pivot)) * u;
        auto alpha = juce::jlimit (0.0f, 0.3f, (moved - 7.0f) / 80.0f) * (0.35f + 0.65f * u);
        skin.draw (g, stick, juce::AffineTransform::translation (-stick.bounds.getWidth() * 0.5f, -pivotY)
                                 .scaled (a.scale, len / picLen)
                                 .rotated (angle + juce::MathConstants<float>::halfPi)
                                 .translated (pivot.x, pivot.y),
                   alpha);
    }
}

void PandaStage::paintRig (juce::Graphics& g, bool arms)
{
    auto& skin = Skin::get();
    // An arm reaching up (for a crash, or cheering) goes behind his big head; the rest are drawn
    // after the drums, in front of everything of his.
    auto high = [] (const Arm& a) { return ! a.atRest && a.shoulder.y - a.pivot.y > 95.0f * a.scale; };
    auto drawSide = [&] (int side)
    {
        // At rest, the picture's own arm; otherwise the rig's.
        if (auto& a = shownArms[(size_t) side]; a.atRest)
            drawLayer (g, skin.sprite (skin.at ("panda/rest")[side].toString()), torsoTransform());
        else
        {
            drawStickBlur (g, hands[(size_t) side], a);
            drawArm (g, a, side);
        }
    };
    if (! arms)
    {
        drawLayer (g, skin.sprite (skin.at ("panda/torso").toString()), torsoTransform());
        for (int side = 0; side < 2; ++side)
            if (high (shownArms[(size_t) side]))
                drawSide (side);
        auto headT = headTransform();
        drawLayer (g, skin.sprite (skin.at ("panda/head_file").toString()), headT);
        // The picture's own face is his big grin; the others are drawn over it.
        if (! (bool) skin.at ("panda/faces/" + face + "/own"))
            if (auto file = skin.at ("panda/faces/" + face + "/file").toString(); file.isNotEmpty())
                drawLayer (g, skin.sprite (file), headT);
        return;
    }
    auto& pose2 = shownArms;
    // The arm further back (higher up, reaching for a cymbal) goes first.
    auto first = pose2[0].pivot.y <= pose2[1].pivot.y ? 0 : 1;
    for (auto side : { first, 1 - first })
        if (! high (pose2[(size_t) side]))
            drawSide (side);

    static const bool debugRig = juce::SystemStats::getEnvironmentVariable ("PD_RIG_DEBUG", {}).isNotEmpty();
    if (debugRig)
    {
        auto dot = [&g] (P p, juce::Colour c, float r = 4.0f) { g.setColour (c); g.fillEllipse (juce::Rectangle<float> (r * 2.0f, r * 2.0f).withCentre (p)); };
        for (auto& v : views)
            if (v.type != PieceType::Kick)
                for (int side = 0; side < 2; ++side)
                    dot (rigStrikePoint (v, side), side == 0 ? juce::Colours::cyan : juce::Colours::yellow, 3.0f);
        for (auto& a : pose2)
        {
            dot (a.shoulder, juce::Colours::red, 5.0f);
            dot (a.wrist, juce::Colours::orange);
            dot (a.pivot, juce::Colours::lime);
            dot (a.tip, juce::Colours::magenta);
        }
    }
}
