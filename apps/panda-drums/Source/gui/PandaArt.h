#pragma once

#include <juce_gui_basics/juce_gui_basics.h>
#include "../engine/KitTypes.h"

// The drawings: the panda, the drums, the cymbals and the stage. All vector, all in stage
// units (the stage is 1280 x 736 and scales to the window), drawn fresh every frame from the
// state the animation hands in.
namespace pd::art
{
struct PandaPose
{
    juce::Point<float> head { 640.0f, 205.0f };
    float radius = 118.0f;
    float tilt = 0.0f;            // radians, around the neck
    float squash = 1.0f;          // vertical scale of the head
    float blink = 0.0f;           // 0 open ... 1 shut
    float happy = 0.0f;           // 0..1: eyes become ^ ^
    float mouthOpen = 0.35f;      // 0 shut ... 1 wide
    float mouthRound = 0.0f;      // 0 grin ... 1 "O"
    juce::Point<float> look;      // -1..1 where the pupils point
    float earL = 0.0f, earR = 0.0f;
    float blushGlow = 0.0f;       // 0..1
    float bodyBounce = 0.0f;      // stage units down
    float breath = 0.0f;          // -1..1

    juce::Point<float> shoulder (bool left) const;    // where an arm leaves the sleeve
};

void drawPandaBody (juce::Graphics&, const PandaPose&);
void drawPandaHead (juce::Graphics&, const PandaPose&);
void drawPandaShadow (juce::Graphics&, const PandaPose&);

// Rubber-hose arm from the sleeve to the paw; the forearm lines up with the stick.
void drawArm (juce::Graphics&, juce::Point<float> shoulder, juce::Point<float> paw, juce::Point<float> stickDir,
              float thickness, float alpha = 1.0f);
void drawStick (juce::Graphics&, juce::Point<float> butt, juce::Point<float> tip, float thickness, float alpha = 1.0f);
void drawPaw (juce::Graphics&, juce::Point<float> centre, float radius, float alpha = 1.0f);

enum class Wrap { PurpleSparkle, Brass, Maple, Chrome, Walnut, Black };
Wrap wrapForVariant (const juce::String& variantName, PieceType);

struct DrumState
{
    float flash = 0.0f;           // 0..1 head lights up
    float ripple = -1.0f;         // 0..1 ring travelling out, <0 none
    float rippleStrength = 0.0f;
    float pulse = 0.0f;           // 0..1 swells the drum
};

void drawDrum (juce::Graphics&, juce::Point<float> topCentre, float radius, float shellHeight, Wrap,
               PieceType, const DrumState&, float floorY);
void drawKick (juce::Graphics&, juce::Point<float> centre, float radius, Wrap, const DrumState&, float floorY,
               const juce::String& logoText);
void drawCymbal (juce::Graphics&, juce::Point<float> centre, float radius, float angle, float squash,
                 PieceType, const DrumState&, float floorY, bool stand, float poleX = -1.0f);
void drawHiHat (juce::Graphics&, juce::Point<float> centre, float radius, float gap, float angle,
                const DrumState&, float floorY, float footPress);

void drawHeart (juce::Graphics&, juce::Rectangle<float>, juce::Colour fill, juce::Colour outline, float outlineWidth);
juce::Path heartPath (juce::Rectangle<float>);
void drawHeartLogo (juce::Graphics&, juce::Rectangle<float>, const juce::String& text);

void drawStage (juce::Graphics&, juce::Rectangle<float> area);
void drawComicBurst (juce::Graphics&, const juce::String& text, juce::Point<float> centre, float scale, float alpha,
                     float rotation, juce::Colour fill);
void drawSparkle (juce::Graphics&, juce::Point<float> c, float size, float alpha, juce::Colour);

// The panda's face on its own, for the logo and the app icon.
void drawPandaBadge (juce::Graphics&, juce::Rectangle<float>);
} // namespace pd::art
