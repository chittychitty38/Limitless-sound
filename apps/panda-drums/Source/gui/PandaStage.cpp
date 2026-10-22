#include "PandaStage.h"
#include "Theme.h"

using namespace pd;
namespace colour = pd::theme::colour;

namespace
{
constexpr float floorY = 690.0f;
// The 3D sticks are longer than the drawn ones were.
float stickLength() { return pd::Skin::get().isLoaded() ? 132.0f : 108.0f; }

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
        startTimerHz (60);
    }
    else
        stopTimer();
}

void PandaStage::timerCallback()
{
    auto t = proc.getTransport();
    setTransport (t.bpm, t.ppq, t.playing);
    if (--labelCountdown <= 0)
    {
        updateLabels();
        labelCountdown = 6;
    }
    advanceTo (nowSeconds());
    repaint();
}

//==============================================================================
void PandaStage::refreshKit()
{
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
    auto mirrored = [] (P renderedAt, P pos) { return (renderedAt.x - 640.0f) * (pos.x - 640.0f) < 0.0f; };
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
                v.hand = 1;
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
                    juce::String kind = v.isFloor ? "floor" : "tom";
                    v.slot = v.isFloor ? i - (int) racks : i;
                    skinSlot (v.isFloor ? juce::String ("floor") : "rack" + juce::String (juce::jlimit (1, 4, (int) racks)), v.slot, v.pos, ppi);
                    v.squash = squashOf (kind, "head", 0.36f);
                    v.flip = mirrored (rendered (kind), v.pos);
                    // Deeper or shallower than the rendered drum: stretch the shell a little.
                    auto ratio0 = Skin::number (skin.at ("kit/" + kind + "/depth"), 8.0f) / Skin::number (skin.at ("kit/" + kind + "/size"), 10.0f);
                    v.stretch = juce::jlimit (0.75f, 1.4f, 0.55f + 0.45f * (depth / size) / ratio0);
                    v.shell = Skin::number (skin.at ("kit/" + kind + "/shell"), 40.0f) / Skin::number (skin.at ("kit/" + kind + "/radius"), 48.0f)
                              * size * ppi * v.stretch;
                }
                v.radius = size * ppi;
                v.hand = v.pos.x >= 640.0f ? 1 : 0;
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
                    v.squash = squashOf (kind, "ellipse", 0.19f);
                    v.flip = mirrored (rendered (kind), v.pos);
                }
                v.radius = size * ppi;
                v.hand = v.pos.x >= 640.0f ? 1 : 0;
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
                v.hand = v.pos.x >= 640.0f ? 1 : 0;
                break;
            }
        }

        // Where a click counts as hitting it.
        if (piece.type == PieceType::Kick)
            v.hitArea = juce::Rectangle<float> (v.radius * 2.0f, v.radius * 2.0f).withCentre (v.pos);
        else if (isCymbal (piece.type))
            v.hitArea = juce::Rectangle<float> (v.radius * 2.0f, std::max (v.radius * 0.7f, v.radius * v.squash * 2.6f)).withCentre (v.pos);
        else
            v.hitArea = { v.pos.x - v.radius, v.pos.y - v.radius * v.squash, v.radius * 2.0f, v.shell + v.radius * v.squash * 2.0f };

        if (v.gap.x <= 0.0f && piece.type == PieceType::HiHat)
            v.gap.x = v.gap.target = 3.0f;
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
    auto font = theme::body (13.0f);
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
        auto pitchW = v.tunable ? 26.0f + 62.0f + 4.0f : 0.0f;
        auto w = nameW + arrows + pitchW + 12.0f;
        P anchor;
        if (v.type == PieceType::Kick)          anchor = { v.pos.x, v.pos.y + v.radius + 2.0f };
        else if (v.type == PieceType::HiHat)    anchor = { v.pos.x + 20.0f, v.pos.y + 36.0f };
        else if (isCymbal (v.type))             anchor = { v.pos.x, v.pos.y + v.radius * v.squash + 14.0f };
        else                                    anchor = { v.pos.x, v.pos.y + v.shell + v.radius * v.squash + 16.0f };
        anchor.y = std::min (anchor.y, designH - 26.0f);
        v.tag = juce::Rectangle<float> (w, 22.0f).withCentre (anchor);
        if (v.tag.getRight() > designW - 4.0f) v.tag.setX (designW - 4.0f - w);
        if (v.tag.getX() < 4.0f) v.tag.setX (4.0f);

        auto r = v.tag.reduced (4.0f, 2.0f);
        v.prevBtn = v.variants > 1 ? r.removeFromLeft (20.0f) : juce::Rectangle<float>();
        if (v.tunable)
        {
            v.upBtn = r.removeFromRight (20.0f);
            r.removeFromRight (62.0f);
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
        return v.pos.translated ((v.pos.x < 640.0f ? 1.0f : -1.0f) * v.radius * (v.type == PieceType::Ride ? 0.45f : 0.72f), 0.0f);
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
        pref = recentOn (1, PieceType::HiHat) ? 0 : recentOn (0, PieceType::Ride) ? 1 : 1;
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

    if (s.hand >= 0)
    {
        auto& h = hands[(size_t) s.hand];
        h.twirlAt = -10.0;      // no showing off when there's work to do
        P paw, tip;
        handPose (h, now, paw, tip);
        auto early = strikeTime - now >= 0.03;
        if (h.piece != s.piece)
        {
            h.from = paw + P (0.0f, liftAt (h, now) * 30.0f);
            h.piece = s.piece;
            h.moveStart = now;
            h.moveEnd = early ? std::max (now + 0.04, strikeTime - 0.02) : now;
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
    h.last = s;
    if (h.next.piece >= 0 && std::abs (h.next.time - s.time) < 1.0e-6)
        h.next = {};
    // The next pending strike for this hand, if any.
    for (auto& p : pending)
        if (p.hand == h.side && p.time > s.time + 1.0e-6 && (h.next.piece < 0 || p.time < h.next.time))
            h.next = p;
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

        juce::String articId;
        if (auto snap = proc.getSnapshot(); snap != nullptr && juce::isPositiveAndBelow (s.piece, (int) snap->pieces.size()))
            if (auto& rt = snap->pieces[(size_t) s.piece]; rt.data != nullptr && juce::isPositiveAndBelow (s.artic, (int) rt.data->artics.size()))
                articId = rt.data->artics[(size_t) s.artic].id;

        switch (v->type)
        {
            case PieceType::Kick:
                bounce.v += 110.0f * vel;
                shake.v += 30.0f * vel * vel;
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
                v->wobble.v += vel * (v->type == PieceType::Ride ? 2.2f : 5.5f) * (v->pos.x < 640.0f ? -1.0f : 1.0f);
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
        lookX.target = juce::jlimit (-1.0f, 1.0f, (v->pos.x - 640.0f) / 380.0f);
        lookY.target = juce::jlimit (-0.6f, 1.0f, (v->pos.y - 205.0f) / 260.0f);

        if (s.hand >= 0)
            land (hands[(size_t) s.hand], s);

        if (proc.comicFx && now - lastBurst > 0.6)
            if (auto* text = comicFor (v->type, articId, s.vel))
            {
                Burst b;
                b.text = text;
                b.pos = v->type == PieceType::Kick ? v->pos.translated (0.0f, -v->radius - 40.0f) : v->pos.translated (0.0f, -70.0f);
                b.pos.x = juce::jlimit (150.0f, designW - 150.0f, b.pos.x);
                b.pos.y = juce::jlimit (80.0f, designH - 120.0f, b.pos.y);
                b.at = now;
                b.rot = (rng.nextFloat() - 0.5f) * 0.3f;
                b.colour = v->type == PieceType::Kick ? colour::gold : v->type == PieceType::Snare ? colour::hot : colour::mint;
                bursts.push_back (b);
                lastBurst = now;
            }
    }

    // Springs.
    for (auto& v : views)
    {
        v.pulse.step (dt, 30.0f, 0.35f);
        auto zeta = v.type == PieceType::Crash || v.type == PieceType::Splash || v.type == PieceType::China ? 0.08f
                  : v.type == PieceType::Ride ? 0.14f : 0.3f;
        v.wobble.step (dt, juce::MathConstants<float>::twoPi * 3.2f, zeta);
        v.gap.step (dt, 70.0f, 0.85f);
        v.press.step (dt, 45.0f, 0.8f);
        if (v.type == PieceType::HiHat && v.press.target > 0.9f && now - v.lastAt > 0.25)
            v.press.target = 0.85f;
    }
    bounce.step (dt, 16.0f, 0.32f);
    nod.step (dt, 13.0f, 0.4f);
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
    float beat = 0.0f;
    if (tPlaying)
    {
        auto frac = (float) (tPpq - std::floor (tPpq));
        beat = std::exp (-frac * 5.0f);
    }
    pose.torso = headBase;
    pose.head = headBase.translated (0.0f, beat * 5.0f + nod.x * 3.0f);
    pose.bodyBounce = bounce.x * 0.08f;
    pose.tilt = 0.03f * std::sin ((float) now * 1.3f) * (tPlaying ? 0.4f : 1.0f) + nod.x * 0.012f + beat * 0.025f;
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

    // The song stopped after a good run: both sticks up.
    if (tPlaying && ! wasPlaying)
        playingSince = now;
    if (! tPlaying && wasPlaying && now - playingSince > 4.0 && now - lastAnyHit < 1.5)
    {
        cheerUntil = now + 1.6;
        spawnHearts (5.0f);
    }
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
        static const char* idle[] = { "wink", "tongue_out", "smile", "happy" };
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
        }
        else
            art::drawStage (bg, { 0.0f, 0.0f, designW, designH });
    }
    g.drawImage (background, getLocalBounds().toFloat());

    juce::Graphics::ScopedSaveState save (g);
    g.addTransform (juce::AffineTransform::translation (0.0f, juce::jlimit (-4.0f, 4.0f, shake.x * 0.1f)).followedBy (t));
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
    if (energy > 0.6f)                             return "open_mouth";
    if (energy > 0.2f)                             return "happy";
    return tPlaying ? "smile" : "neutral";
}

PandaStage::P PandaStage::elbowFor (P shoulder, P paw)
{
    // Same elbow as the drawn arm: it bends down and out, and past full reach it stretches.
    const float reach = 255.0f;
    auto d = paw - shoulder;
    auto len = std::max (1.0f, d.getDistanceFromOrigin());
    P perp (-d.y / len, d.x / len);
    if (perp.y < 0.0f) perp = -perp;
    perp.x += (paw.x < shoulder.x ? -1.0f : 1.0f) * 0.35f;
    perp = normalised (perp);
    auto bend = std::sqrt (std::max (0.0f, reach * reach * 0.25f - len * len * 0.25f)) + 10.0f;
    return shoulder + d * 0.5f + perp * bend;
}

void PandaStage::drawSkinArm (juce::Graphics& g, P shoulder, P paw, P tip, float alpha)
{
    auto& skin = Skin::get();
    auto s = pose.radius / Skin::number (skin.at ("panda/head/radius"), pose.radius);

    auto elbow = elbowFor (shoulder, paw);

    auto arm = skin.sprite ("arm");
    auto a = Skin::point (skin.at ("panda/arm/a")), b = Skin::point (skin.at ("panda/arm/b"));
    const float across = 0.86f * s;
    auto dir = normalised (tip - paw);
    // Two halves with round furry ends: they overlap into a soft elbow.
    skin.drawAlong (g, arm, a, b, shoulder, elbow, across, alpha);
    skin.drawAlong (g, arm, a, b, elbow, paw - dir * 6.0f, across, alpha);

    // Stick, then the paw round it (thumb on top whichever way the stick points).
    auto butt = Skin::point (skin.at ("panda/stick/butt")), stickTip = Skin::point (skin.at ("panda/stick/tip"));
    auto back = (stickTip - butt).getDistanceFromOrigin() * 0.12f * s;
    skin.drawAlong (g, skin.sprite ("stick"), butt, stickTip, paw - dir * back, tip, s, alpha);
    auto pawSprite = skin.sprite ("paw");
    auto pc = Skin::point (skin.at ("panda/paw/centre"));
    auto t = juce::AffineTransform::translation (-pc.x, -pc.y);
    if (dir.x < 0.0f)
        t = t.scaled (1.0f, -1.0f);
    t = t.scaled (s).rotated (std::atan2 (dir.y, dir.x)).translated (paw.x, paw.y);
    skin.draw (g, pawSprite, t, alpha);
}

void PandaStage::paintSkin (juce::Graphics& g)
{
    auto& skin = Skin::get();
    g.setImageResamplingQuality (juce::Graphics::highResamplingQuality);
    auto pt = [&skin] (const juce::String& path) { return Skin::point (skin.at (path)); };
    auto num = [&skin] (const juce::String& path, float fallback) { return Skin::number (skin.at (path), fallback); };
    auto kindOf = [] (const PieceView& v) -> juce::String
    {
        switch (v.type)
        {
            case PieceType::Kick:   return "kick";
            case PieceType::Snare:  return "snare";
            case PieceType::Tom:    return v.isFloor ? "floor" : "tom";
            case PieceType::HiHat:  return "hihat";
            case PieceType::Crash:  return "crash";
            case PieceType::Ride:   return "ride";
            case PieceType::China:  return "china";
            case PieceType::Splash: return "splash";
            case PieceType::Perc:   return "snare";
        }
        return "tom";
    };
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
    auto layerFor = [&skin, &kindOf, &wrapName] (const PieceView& v)
    {
        auto kind = kindOf (v);
        auto wrap = v.type == PieceType::Perc ? juce::String ("chrome") : wrapName (v.wrap);
        auto name = skin.at ("kit/" + kind + "/wraps/" + wrap).toString();
        if (name.isEmpty())
            name = skin.at ("kit/" + kind + "/wraps/purple").toString();
        return skin.sprite (name);
    };

    // ---- the heart lights glow, twinkle, and flare with the kick
    if (auto* bulbs = skin.at ("stage/bulbs").getArray())
    {
        float kickFlash = 0.0f;
        for (auto& v : views)
            if (v.type == PieceType::Kick)
                kickFlash = std::max (kickFlash, drumState (v).flash);
        for (int i = 0; i < bulbs->size(); ++i)
        {
            auto b = (*bulbs)[i];
            auto p = Skin::point (b.getProperty ("at", {})).translated (0.0f, 4.0f);
            auto* c = b.getProperty ("colour", {}).getArray();
            if (c == nullptr || c->size() < 3)
                continue;
            auto col = juce::Colour::fromFloatRGBA ((float) (double) (*c)[0], (float) (double) (*c)[1], (float) (double) (*c)[2], 1.0f);
            auto twinkle = 0.75f + 0.25f * std::sin ((float) now * 2.3f + (float) i * 1.7f);
            auto a = juce::jlimit (0.0f, 1.0f, 0.32f * twinkle + 0.35f * kickFlash);
            auto rr = 24.0f + 10.0f * kickFlash;
            juce::ColourGradient grad (col.withAlpha (a), p, col.withAlpha (0.0f), p.translated (rr, 0.0f), true);
            g.setGradientFill (grad);
            g.fillEllipse (juce::Rectangle<float> (rr * 2.0f, rr * 2.0f).withCentre (p));
        }
    }

    // ---- the panda's body and head, behind the kit
    auto head0 = pt ("panda/head/anchor");
    auto r0 = num ("panda/head/radius", pose.radius);
    auto s = pose.radius / r0;
    auto body = skin.sprite (skin.at ("panda/body").toString());
    auto bodyBottom = body.bounds.getBottom();
    auto bodyT = juce::AffineTransform::scale (s, s * (1.0f + 0.012f * pose.breath), head0.x, bodyBottom)
                     .translated (pose.torso.x - head0.x, pose.torso.y - head0.y + pose.bodyBounce);
    skin.draw (g, body, bodyT);

    P neck (head0.x, head0.y + r0 * 0.85f);
    auto headT = juce::AffineTransform::scale (s, s * pose.squash, neck.x, neck.y)
                     .rotated (pose.tilt, neck.x, neck.y)
                     .translated (pose.head.x - head0.x, pose.head.y - head0.y + pose.bodyBounce * 0.6f);
    if (auto* ears = skin.at ("panda/ears").getArray(); ears != nullptr && ears->size() == 2)
        for (int i = 0; i < 2; ++i)
        {
            auto pivot = Skin::point ((*ears)[i].getProperty ("pivot", {}));
            auto angle = (i == 0 ? -pose.earL : pose.earR) * 1.4f;
            skin.draw (g, skin.sprite ((*ears)[i].getProperty ("file", {}).toString()),
                       juce::AffineTransform::rotation (angle, pivot.x, pivot.y).followedBy (headT));
        }
    auto fade = juce::jlimit (0.0f, 1.0f, (float) (now - faceAt) / 0.06f);
    auto headLayer = [&skin] (const juce::String& f)
    {
        auto name = skin.at ("panda/heads/" + f).toString();
        return skin.sprite (name.isNotEmpty() ? name : skin.at ("panda/heads/neutral").toString());
    };
    if (fade < 1.0f)
        skin.draw (g, headLayer (lastFace), headT);
    skin.draw (g, headLayer (face), headT, fade < 1.0f ? fade : 1.0f);
    // Cheeks glow when he's going for it.
    if (pose.blushGlow > 0.05f)
        if (auto* cheeks = skin.at ("panda/cheeks").getArray(); cheeks != nullptr)
            for (auto& c : *cheeks)
            {
                auto p = Skin::point (c).transformedBy (headT);
                auto rr = pose.radius * 0.2f;
                juce::ColourGradient grad (juce::Colour (0xffff5c8a).withAlpha (0.4f * pose.blushGlow), p,
                                           juce::Colour (0xffff5c8a).withAlpha (0.0f), p.translated (rr, 0.0f), true);
                g.setGradientFill (grad);
                g.fillEllipse (juce::Rectangle<float> (rr * 2.0f, rr * 1.4f).withCentre (p));
            }

    // ---- cymbals: stands, then the discs swinging on them
    for (auto& v : views)
        if (isCymbal (v.type) && v.type != PieceType::HiHat)
        {
            auto kind = kindOf (v);
            auto st = drumState (v);
            auto stands = skin.at ("kit/stands/" + kind);
            juce::var stand;
            if (auto* a = stands.getArray(); a != nullptr && v.slot < a->size())
                stand = (*a)[v.slot];
            auto standLayer = skin.sprite (stand.getProperty ("file", {}).toString());
            if (standLayer.isValid())
            {
                drawContactShadow (g, juce::Rectangle<float> (70.0f, 14.0f).withCentre ({ standLayer.bounds.getCentreX() - 6.0f, standLayer.bounds.getBottom() - 6.0f }));
                skin.draw (g, standLayer, juce::AffineTransform::translation (v.pos - Skin::point (stand.getProperty ("top", {}))));
            }
            else
            {
                g.setColour (colour::chrome);
                g.drawLine (v.pos.x, v.pos.y, v.pos.x, floorY - 30.0f, 4.0f);
            }
            auto angle = v.wobble.x * 0.05f;
            auto squash = 1.0f + 0.25f * std::sin (v.wobble.x * 0.4f);
            auto anchor = pt ("kit/" + kind + "/anchor");
            auto t = juce::AffineTransform::translation (-anchor.x, -anchor.y);
            if (v.flip)
                t = t.scaled (-1.0f, 1.0f);
            auto sc = v.radius / num ("kit/" + kind + "/radius", v.radius);
            t = t.rotated (angle).scaled (sc, sc * squash).translated (v.pos.x, v.pos.y);
            skin.draw (g, skin.sprite (skin.at ("kit/" + kind + "/file").toString()), t);
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

    // ---- drums from the back forward; rack toms sit on the kick
    auto kick = std::find_if (views.begin(), views.end(), [] (auto& v) { return v.type == PieceType::Kick; });
    std::vector<const PieceView*> drums;
    for (auto& v : views)
        if (! isCymbal (v.type) && v.type != PieceType::Kick)
            drums.push_back (&v);
    std::sort (drums.begin(), drums.end(), [] (auto* a, auto* b) { return a->pos.y < b->pos.y; });

    auto drawDrumLayer = [&] (const PieceView& v)
    {
        auto kind = kindOf (v);
        auto st = drumState (v);
        auto layer = layerFor (v);
        auto t = pieceTransform (v, pt ("kit/" + kind + "/anchor"), num ("kit/" + kind + "/radius", v.radius),
                                 (v.type == PieceType::Perc ? 0.9f : 1.0f) * (1.0f + 0.035f * st.pulse));
        if (v.isFloor || v.type == PieceType::Snare || v.type == PieceType::Perc)
        {
            auto foot = layer.bounds.transformedBy (t);
            drawContactShadow (g, juce::Rectangle<float> (foot.getWidth() * 0.8f, 16.0f).withCentre ({ foot.getCentreX(), foot.getBottom() - 6.0f }));
        }
        skin.draw (g, layer, t);
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

    if (kick != views.end())
        for (auto* d : drums)
            if (d->type == PieceType::Tom && ! d->isFloor)
            {
                auto bottom = d->pos.translated (0.0f, d->shell * 0.9f);
                P to (kick->pos.x + (d->pos.x - kick->pos.x) * 0.3f, kick->pos.y - kick->radius * 0.85f);
                g.setColour (colour::ink.withAlpha (0.8f));
                g.drawLine (bottom.x, bottom.y, to.x, to.y, 8.0f);
                g.setColour (juce::Colour (0xffd9d6e6));
                g.drawLine (bottom.x, bottom.y, to.x, to.y, 4.5f);
                g.setColour (juce::Colours::white.withAlpha (0.8f));
                g.drawLine (bottom.x - 1.0f, bottom.y, to.x - 1.0f, to.y, 1.4f);
            }
    for (auto* d : drums)
        if (d->type == PieceType::Tom && ! d->isFloor)
            drawDrumLayer (*d);
    if (kick != views.end())
    {
        auto st = drumState (*kick);
        auto layer = layerFor (*kick);
        auto t = pieceTransform (*kick, pt ("kit/kick/anchor"), num ("kit/kick/radius", kick->radius), 1.0f + 0.02f * st.pulse);
        auto foot = layer.bounds.transformedBy (t);
        drawContactShadow (g, juce::Rectangle<float> (foot.getWidth() * 0.9f, 22.0f).withCentre ({ foot.getCentreX(), foot.getBottom() - 8.0f }), 0.32f);
        skin.draw (g, layer, t);
        auto head = Skin::ellipse (skin.at ("kit/kick/head")).transformedBy (t);
        if (st.flash > 0.02f)
        {
            g.setColour (juce::Colours::white.withAlpha (0.3f * st.flash));
            g.fillEllipse (head);
        }
        auto kt = (float) (now - kick->rippleAt) / 0.4f;
        if (kt >= 0.0f && kt < 1.0f)
        {
            auto rr = kick->radius * (1.05f + 0.5f * kt);
            g.setColour (juce::Colours::white.withAlpha ((1.0f - kt) * 0.45f * kick->rippleAmt));
            g.drawEllipse (kick->pos.x - rr, kick->pos.y - rr, rr * 2.0f, rr * 2.0f, 4.0f * (1.0f - kt) + 1.0f);
        }
    }
    for (auto* d : drums)
        if (! (d->type == PieceType::Tom && ! d->isFloor) && d->type != PieceType::HiHat)
            drawDrumLayer (*d);

    // ---- hi-hat: stand, bottom cymbal, top cymbal lifted by the pedal
    for (auto& v : views)
        if (v.type == PieceType::HiHat)
        {
            auto anchor = pt ("kit/hihat/anchor");
            auto move = juce::AffineTransform::translation (v.pos - anchor);
            auto standLayer = skin.sprite (skin.at ("kit/hihat/stand_file").toString());
            drawContactShadow (g, juce::Rectangle<float> (80.0f, 14.0f).withCentre (P (standLayer.bounds.getCentreX(), standLayer.bounds.getBottom() - 8.0f).transformedBy (move)));
            skin.draw (g, standLayer, move);
            auto sc = v.radius / num ("kit/hihat/radius", v.radius);
            auto angle = v.wobble.x * 0.04f;
            auto cym = [&] (const char* file, const char* where, float lift)
            {
                auto c = pt (juce::String ("kit/hihat/") + where);
                auto t = juce::AffineTransform::translation (-c.x, -c.y).rotated (angle).scaled (sc).translated (c.x, c.y - lift).followedBy (move);
                skin.draw (g, skin.sprite (skin.at (juce::String ("kit/hihat/") + file).toString()), t);
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

    drawSelection (g);

    // ---- arms over the kit, then the sleeves over the tops of the arms
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
            drawSkinArm (g, shoulder, hand.smearPaw, hand.smearTip, a);
        }
        drawSkinArm (g, shoulder, paw, tip, 1.0f);
    }
    if (auto* sleeves = skin.at ("panda/sleeves").getArray(); sleeves != nullptr && sleeves->size() == 2)
        for (int i = 0; i < 2; ++i)
        {
            auto pivot = Skin::point ((*sleeves)[i].getProperty ("pivot", {}));
            auto end = Skin::point ((*sleeves)[i].getProperty ("end", {}));
            auto shoulder = pose.shoulder (i == 0);
            // The sleeve hangs from the shoulder and turns with the upper arm.
            P paw, tip;
            handPose (hands[(size_t) i], now, paw, tip);
            auto upper = elbowFor (shoulder, paw) - shoulder;
            auto rest = end - pivot;
            auto turn = rest.getDistanceFromOrigin() > 0.0f ? std::atan2 (upper.y, upper.x) - std::atan2 (rest.y, rest.x) : 0.0f;
            auto t = juce::AffineTransform::rotation (turn, pivot.x, pivot.y)
                         .scaled (s, s, pivot.x, pivot.y)
                         .translated (shoulder - pivot);
            skin.draw (g, skin.sprite ((*sleeves)[i].getProperty ("file", {}).toString()), t);
        }
}

void PandaStage::drawParticles (juce::Graphics& g)
{
    for (auto& p : particles)
    {
        auto a = 1.0f - p.age / p.life;
        if (p.kind == 0)
            art::drawSparkle (g, p.pos, p.size * (0.6f + 0.4f * a), a, p.colour);
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
    auto font = theme::body (13.0f);
    for (auto& v : views)
    {
        auto isSel = v.piece == selected, isHover = v.piece == hoverPiece;
        if (v.tag.isEmpty() || ! (isSel || isHover))
            continue;
        theme::drawPill (g, v.tag, colour::plum.withAlpha (isSel || isHover ? 0.95f : 0.78f), isSel ? colour::hot : juce::Colours::transparentBlack);

        auto arrow = [&] (juce::Rectangle<float> r, float angle, const juce::String& id)
        {
            if (r.isEmpty())
                return;
            auto hot = isHover && hoverButton == id;
            if (hot)
            {
                g.setColour (colour::hot.withAlpha (0.35f));
                g.fillEllipse (r.withSizeKeepingCentre (18.0f, 18.0f));
            }
            juce::Path tri;
            tri.addTriangle (-4.5f, -5.0f, -4.5f, 5.0f, 5.0f, 0.0f);
            tri.applyTransform (juce::AffineTransform::rotation (angle).translated (r.getCentreX(), r.getCentreY()));
            g.setColour (hot ? juce::Colours::white : colour::hot);
            g.fillPath (tri);
        };
        arrow (v.prevBtn, juce::MathConstants<float>::pi, "prev");
        arrow (v.nextBtn, 0.0f, "next");
        arrow (v.downBtn, juce::MathConstants<float>::halfPi, "down");
        arrow (v.upBtn, -juce::MathConstants<float>::halfPi, "up");

        auto nameArea = v.tag.reduced (4.0f, 0.0f);
        if (! v.prevBtn.isEmpty()) nameArea.setLeft (v.prevBtn.getRight());
        nameArea.setRight (! v.nextBtn.isEmpty() ? v.nextBtn.getX() : (! v.downBtn.isEmpty() ? v.downBtn.getX() - 4.0f : nameArea.getRight()));
        g.setColour (colour::text);
        g.setFont (font);
        g.drawText (v.variantName, nameArea, juce::Justification::centred, true);

        if (v.tunable)
        {
            auto pr = juce::Rectangle<float> (v.downBtn.getRight(), v.tag.getY() + 3.0f, v.upBtn.getX() - v.downBtn.getRight(), v.tag.getHeight() - 6.0f);
            auto ok = v.keyOn && v.inKey;
            theme::drawPill (g, pr, (ok ? colour::mint : colour::plumLight).withAlpha (ok ? 0.25f : 0.9f));
            g.setColour (ok ? colour::mint : (v.keyOn ? colour::gold : colour::cream));
            g.setFont (theme::title (14.0f));
            g.drawText (v.pitchText.upToFirstOccurrenceOf (" ", false, false), pr, juce::Justification::centred);
        }
    }
}

void PandaStage::drawChips (juce::Graphics& g)
{
    for (auto& v : views)
    {
        auto age = (float) (now - v.lastAt);
        if (age < 0.0f || age > 1.5f || v.last.zone < 0)
            continue;
        auto alpha = age < 0.9f ? 1.0f : 1.0f - (age - 0.9f) / 0.6f;
        auto pop = 1.0f + 0.22f * std::exp (-age / 0.05f);
        P anchor = v.type == PieceType::Kick ? P (v.pos.x - v.radius - 70.0f, 712.0f)
                 : isCymbal (v.type)         ? v.pos.translated (0.0f, -v.radius * v.squash - 26.0f)
                                             : v.pos.translated (0.0f, -v.radius * v.squash - 22.0f);
        auto& e = v.last;
        juce::String rr = "RR " + juce::String (e.round + 1) + "/" + juce::String (e.roundCount);
        juce::String vel = "VEL " + juce::String (e.velocityIn);
        juce::String zone = "ZONE " + juce::String (e.zone + 1) + "/" + juce::String (e.zoneCount);
        if ((e.flags & HitEvent::chromatic) != 0)
            zone = pitchName (proc.getNaturalMidi (v.piece) + e.semis).upToFirstOccurrenceOf (" ", false, false);

        juce::Graphics::ScopedSaveState s (g);
        g.addTransform (juce::AffineTransform::scale (pop, pop, anchor.x, anchor.y));
        auto box = juce::Rectangle<float> (196.0f, 26.0f).withCentre (anchor);
        box.setX (juce::jlimit (4.0f, designW - 200.0f, box.getX()));
        box.setY (std::max (4.0f, box.getY()));
        auto zc = colour::zone (e.zone, e.zoneCount);
        theme::drawPill (g, box.translated (0.0f, 2.0f), juce::Colours::black.withAlpha (0.25f * alpha));
        theme::drawPill (g, box, colour::plum.withAlpha (0.94f * alpha), zc.withAlpha (alpha));
        g.setColour (zc.withAlpha (alpha));
        g.fillEllipse (box.getX() + 8.0f, box.getCentreY() - 5.0f, 10.0f, 10.0f);
        auto r = box.withTrimmedLeft (22.0f).withTrimmedRight (8.0f);
        g.setFont (theme::title (14.5f));
        g.setColour (colour::text.withAlpha (alpha));
        g.drawText (rr, r.removeFromLeft (52.0f), juce::Justification::centredLeft);
        g.setColour (colour::gold.withAlpha (alpha));
        g.drawText (vel, r.removeFromLeft (58.0f), juce::Justification::centredLeft);
        g.setColour (zc.withAlpha (alpha));
        g.drawText (zone, r, juce::Justification::centredRight);
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
