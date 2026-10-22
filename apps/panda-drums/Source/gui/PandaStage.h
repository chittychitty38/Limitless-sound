#pragma once

#include "../PluginProcessor.h"
#include "PandaArt.h"
#include "Skin.h"

// The stage: the panda behind the kit, playing every hit the engine plays.
//
// Hits arrive with the time they will be heard. With Showtime on they arrive ~150 ms early,
// so a hand can wind up and land exactly on the sound; otherwise the stick snaps down the
// moment the hit is heard, with a smear frame so it still reads as a swing.
class PandaStage : public juce::Component,
                   public juce::SettableTooltipClient
{
public:
    static constexpr float designW = 1280.0f, designH = 736.0f;

    explicit PandaStage (PandaDrumsProcessor&);

    void paint (juce::Graphics&) override;
    void resized() override;
    void mouseMove (const juce::MouseEvent&) override;
    void mouseExit (const juce::MouseEvent&) override;
    void mouseDown (const juce::MouseEvent&) override;

    // A hit from the engine; strikeTime in seconds on the same clock as advanceTo().
    void hit (const pd::HitEvent&, double strikeTime);
    void advanceTo (double now);
    void setLive (bool shouldRunOwnClock);        // false: the render tool drives advanceTo()
    std::function<void (double)> onFrame;         // each frame, just before he moves: hand him the hits that came in
    void setTransport (double bpm, double ppq, bool playing) { tBpm = bpm; tPpq = ppq; tPlaying = playing; }
    void refreshKit();                            // kit, variants or tuning changed

    // How far out to one side a piece is (stage units from his middle): of hits heard together the
    // one furthest out takes the hand on its side first, so the rest go to the other hand and his
    // arms never cross.
    float sideReach (int piece) const;

    int getSelectedPiece() const { return selected; }
    void setSelectedPiece (int p) { selected = p; repaint(); }
    std::function<void (int)> onSelect;
    bool showTags = true;          // tag under the hovered / selected drum

    static double nowSeconds() { return juce::Time::getMillisecondCounterHiRes() * 0.001; }

    // What has to be redrawn for this frame: everything that moves now or moved last frame (in
    // this component's coordinates). With the rigged panda that's him, what he's playing, the
    // lights and the effects; the rest of the stage is left as it is on screen.
    juce::RectangleList<int> changedArea();
    void repaintChanged();

    // Where his hands are this frame (each fist's fulcrum, then each stick's tip), for checking
    // that they move smoothly.
    std::array<juce::Point<float>, 4> handPoints() const
    {
        return { shownArms[0].pivot, shownArms[1].pivot, shownArms[0].tip, shownArms[1].tip };
    }
    // And where his head (crown, cheek) and shoulders are.
    std::array<juce::Point<float>, 4> bodyPoints() const;

private:
    using P = juce::Point<float>;

    struct Spring
    {
        float x = 0.0f, v = 0.0f, target = 0.0f;
        void step (float dt, float omega, float zeta)
        {
            // Small sub-steps keep stiff springs stable at any frame rate.
            auto n = std::max (1, (int) std::ceil (dt / 0.002f));
            auto h = dt / (float) n;
            for (int i = 0; i < n; ++i)
            {
                auto a = -omega * omega * (x - target) - 2.0f * zeta * omega * v;
                v += a * h;
                x += v * h;
            }
        }
    };

    struct PieceView
    {
        int piece = -1;
        pd::PieceType type = pd::PieceType::Perc;
        P pos;                     // drums: top centre; kick and cymbals: centre
        float radius = 40.0f, shell = 30.0f;
        pd::art::Wrap wrap = pd::art::Wrap::PurpleSparkle;
        int hand = 0;              // preferred: 0 = screen left, 1 = screen right
        bool eitherHand = false;
        bool isFloor = false;
        juce::String variantName, pitchText;
        bool tunable = false, inKey = false, keyOn = false;
        int variants = 1;
        int slot = 0;              // which of the slots for its kind it sits in
        float squash = 0.36f;      // drum head / cymbal: height of its ellipse over its width
        bool flip = false;         // the 3D layer is drawn mirrored (rendered on the other side)
        float stretch = 1.0f;      // deeper or shallower shell than the rendered one
        int sharesWith = -1;       // drawn by another piece: the picture has one drum for both
        int stillFrames = 99;      // frames since it last moved (it's redrawn for a couple more as it settles)

        // Animation.
        double flashAt = -10.0, rippleAt = -10.0;
        float flashAmt = 0.0f, rippleAmt = 0.0f;
        Spring pulse, wobble, gap, press;

        // Hit popup.
        pd::HitEvent last;
        double lastAt = -10.0;

        juce::Rectangle<float> hitArea, tag, prevBtn, nextBtn, downBtn, upBtn;
    };

    struct Strike
    {
        int piece = -1, artic = 0;
        int hand = -1;             // 0 / 1 = a hand, -1 = kick foot, -2 = hi-hat foot
        float vel = 0.0f;
        double time = -10.0;       // when it is heard
        double scheduled = -10.0;  // when we learned about it (wind-up room = time - scheduled)
    };

    struct Hand
    {
        int side = 0;
        int piece = -1;             // where it is heading / playing
        P base, from;               // paw hover position, and where the last move began
        double moveStart = -10.0, moveEnd = -10.0;
        Strike last, next;          // last landed, next pending
        double smearUntil = -10.0;
        P smearPaw, smearTip;
        double twirlAt = -10.0;
        // The rigged arm: where the last move began (the fist at the stroke, the stick's heading
        // and pitch there), the stroke height it has been playing at, and its rhythm.
        float fromHeading = 0.0f, fromPitch = 0.0f, fromLift = 1.0f;
        float ready = 0.45f;        // the stroke height it has been playing at
        double nextFromT = -10.0;   // when the next stroke was known, and how high the stick was then
        float nextFromH = 0.0f;
        float nextFromV = 0.0f;     // and how fast it was going (heights a second, + up)
        float ioi = 0.4f;           // the time between its strokes lately
        Spring elbowX, elbowY;      // the elbow trailing the hand (overlapping action)
        Spring shoulderLift;        // the shoulder rising with a big stroke
        float home = 1.0f;          // 1: resting in the picture's pose
        float homeFrom = 0.0f;      // leaving it: how far in it the hand was, and over when
        double homeFadeStart = -10.0, homeFadeEnd = -10.0;
    };

    // The rigged panda's arm at a moment. The stick turns in 3D about the fulcrum in his fist:
    // heading is its direction across the floor (0 toward us, + to screen right), pitch its angle
    // above the floor; on screen it shows foreshortened.
    struct Arm
    {
        P shoulder, wrist, pivot;   // the fist is drawn about the pivot (the stick's fulcrum)
        P tip, butt;                // the stick's two ends, on screen
        P contact;                  // the part of the stick that meets what it plays (the tip, or a crash's shoulder)
        float angle = 0.0f;         // the stick's direction on screen (radians)
        float fistTurn = 0.0f;      // how far the fist is turned from the picture's
        P strikePivot;              // where the fist is when the stick is on the head
        float heading = 0.0f, pitch = 0.0f;   // the stick's heading and pitch on the head
        float height = 0.0f;        // the stroke: 0 on the head ... 1 all the way up
        bool atRest = false;        // exactly in the picture's pose
        float scale = 1.0f;         // the panda's size against the picture's
        P elbow;                    // where the arm bends (it trails the hand a little)
        float sleeveLift = 0.0f;    // how far the shoulder rises with the arm
        float liftScale = 1.0f;     // how much the arm (not just the wrist) goes into its strokes
    };

    struct Particle { P pos, vel; float life = 0.0f, age = 0.0f, size = 0.0f; int kind = 0; juce::Colour colour; float spin = 0.0f; int variant = 0; };
    struct Fx { juce::String sprite; P pos; double at = -10.0; float life = 0.15f, rot = 0.0f, scale = 1.0f; bool flip = false; };
    struct Burst { juce::String text; P pos; double at = -10.0; float rot = 0.0f; juce::Colour colour; };

    void frame (double displayTime);              // once per refresh of the display
    juce::VBlankAttachment vblank;
    double clockOffset = 0.0;
    bool clockSet = false;
    void layoutPieces();
    void updateLabels();
    PieceView* viewFor (int piece);
    int chooseHand (const PieceView&, double time);
    P strikePoint (const PieceView&, int hand) const;
    P stickDir (const PieceView&, int hand) const;
    void handPose (const Hand&, double now, P& paw, P& tip) const;
    float liftAt (const Hand&, double now) const;
    void land (Hand&, const Strike&);
    void spawnSparkles (const PieceView&, float vel);
    void spawnHearts (float count);
    P toDesign (P screen) const;
    juce::AffineTransform designTransform() const;
    void paintVector (juce::Graphics&);
    void drawSelection (juce::Graphics&);
    void paintSkin (juce::Graphics&);
    Arm armPose (const Hand&, double t) const;
    float strokeAt (const Hand&, double t) const;
    float homeWeight (const Hand&, double t) const;
    P rigStrikePoint (const PieceView&, int hand) const;
    juce::AffineTransform torsoTransform() const;
    juce::AffineTransform headTransform() const;
    void paintRig (juce::Graphics&, bool arms);
    void drawArm (juce::Graphics&, const Arm&, int side);
    void drawStickBlur (juce::Graphics&, const Hand&, const Arm&);

    // A layer drawn at the screen's own resolution: a sprite that's only moved (or scaled the way
    // it was last frame) is drawn once into a cached image at exactly the size it shows at, then
    // copied pixel for pixel; one that turns or changes size is drawn from the art.
    void drawLayer (juce::Graphics&, const pd::Skin::Sprite&, const juce::AffineTransform&, float alpha = 1.0f);
    struct CachedLayer { juce::Image image; float x0 = 0.0f, y0 = 0.0f; juce::int64 used = 0; };
    std::map<juce::String, CachedLayer> layerCache;
    struct Asked { juce::int64 last = 0, before = 0; };
    std::map<juce::String, Asked> layerAsked;            // the frames each layer at each size was last asked for
    juce::int64 frameNo = 2;
    juce::AffineTransform stageToDevice, deviceToStage; // this frame's stage units to the screen's pixels
    juce::Rectangle<float> pieceBounds (const PieceView&) const;
    bool pieceMoving (const PieceView&) const;
    juce::Rectangle<float> pandaBounds() const;
    P chipAnchor (const PieceView&) const;
    juce::RectangleList<float> lastChanged;
    bool everything = true;          // the next frame redraws the whole stage
    juce::String skinKind (const PieceView&) const;        // which picture of the art a piece uses
    juce::String poseFor (const PieceView&) const;         // the panda's pose for hitting it
    void strikeFx (const PieceView&, int hand, float vel);
    void drawContactShadow (juce::Graphics&, juce::Rectangle<float> footprint, float alpha = 0.26f);
    pd::art::DrumState drumState (const PieceView&) const;
    juce::AffineTransform pieceTransform (const PieceView&, P anchor, float renderedRadius, float extraScale = 1.0f) const;
    juce::String pickFace() const;
    void drawTags (juce::Graphics&);
    void drawChips (juce::Graphics&);
    void drawParticles (juce::Graphics&);

    PandaDrumsProcessor& proc;
    std::vector<PieceView> views;
    std::array<Hand, 2> hands;
    std::vector<Particle> particles;
    std::vector<Burst> bursts;
    std::vector<Strike> pending;                  // strikes waiting for their time
    pd::art::PandaPose pose;
    juce::Image background;

    // The 3D panda's face: which rendered head shows, and the one it is fading from.
    juce::String face { "neutral" }, lastFace { "neutral" };
    double faceAt = -10.0;
    juce::String mood;             // a face held for a moment (a wink when idle, a scowl on a china)
    double moodUntil = -10.0, nextIdleMood = 6.0, cheerUntil = -10.0, playingSince = -10.0;
    bool wasPlaying = false;
    double lastLanded = -10.0;
    juce::String poseName { "idle" }, lastPoseName { "idle" };   // the art's pose for what he's playing
    double poseAt = -10.0, poseHold = -10.0;
    std::vector<Fx> fx;
    int lastBadCount = -1;
    P headBase { 640.0f, 205.0f };
    int recentToms = 0;
    double recentTomsAt = -10.0;

    double now = 0.0, lastAdvance = 0.0;
    double lastAnyHit = -10.0, lastBurst = -10.0, nextBlink = 2.0, blinkAt = -10.0, happyUntil = -10.0;
    float energy = 0.0f;
    Spring bounce, nod, earL, earR, lookX, lookY, shake;
    Spring headLean, headDip;       // the head on its own: leaning toward a hit (radians), dipping with it (stage units)
    Spring bodyLean;                // the rigged panda leaning toward a far reach (stage units)
    float grooving = 0.25f;         // how much he's into the song: 1 playing, less while it goes on without him
    float hostPlaying = 0.0f;       // the host playing, eased (his head-bang comes and goes with it)
    std::array<Arm, 2> shownArms;   // the arms as this frame draws them
    std::array<Arm, 2> lastArms;    // and as the frame before showed them (the motion blur runs between)
    std::array<bool, 2> haveLastArms { false, false };
    bool rig = false;               // the art is the rigged hero panda
    float centreX = 640.0f;         // the panda's middle: pieces left of it are his right hand's
    float pandaScale = 1.0f;        // the rigged panda against the picture: smaller behind a bigger kit
    double tBpm = 120.0, tPpq = 0.0;
    bool tPlaying = false;
    bool live = true;
    int selected = -1;
    int hoverPiece = -1;
    juce::String hoverButton;
    juce::Random rng { 1234 };
    int labelCountdown = 0;
};
