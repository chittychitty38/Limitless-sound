// Limitless Undo: the undo history for one hosted plugin.
//
// Plain C++17 with no JUCE, so it can be tested on its own. Every call is made on
// the message thread; the plugin collects changes from other threads first.
//
// A knob drag, wrapped in the plugin's begin/end gesture, becomes one step. Changes
// without a gesture (some plugins never send one, and preset loads change many
// settings at once) are grouped until nothing has changed for a moment. Changes the
// DAW makes (automation playing back) are never steps, and nor are the changes made
// by undo and redo themselves.

#pragma once

#include <cstdint>
#include <deque>
#include <map>
#include <optional>
#include <set>
#include <string>
#include <vector>

namespace limitless
{

struct ParamChange
{
    int index = 0;
    float before = 0.0f;
    float after = 0.0f;
};

struct Step
{
    uint64_t id = 0;
    std::vector<ParamChange> changes;
    std::string label, before, after;   // words for people, filled in by the plugin
    double time = 0.0;                  // seconds, on the clock the caller uses
};

class UndoHistory
{
public:
    static constexpr double groupSeconds = 0.35;   // changes without a gesture this close together are one step
    static constexpr double hostSeconds = 0.25;    // after the DAW sets a value, ignore that knob's echoes
    static constexpr float epsilon = 1.0e-5f;

    explicit UndoHistory (size_t limit = 500) : maxSteps (limit) {}

    // What the plugin says a parameter is now, without it being a change (after loading).
    void setKnown (int index, float value);
    std::optional<float> known (int index) const;

    // From the hosted plugin's own editor.
    void gestureBegin (int index, double now);
    void gestureEnd (int index, double now);
    void valueChanged (int index, float value, double now);

    // From the DAW: automation, or the DAW's own controls. Never undoable here.
    void hostChanged (int index, float value, double now);

    // Call regularly. Returns the step it just made, if any, for labelling and reporting.
    Step* tick (double now);

    // Make a step from any changes still waiting, e.g. before an undo.
    Step* flush (double now);

    bool canUndo() const { return ! undoStack.empty(); }
    bool canRedo() const { return ! redoStack.empty(); }
    const Step* nextUndo() const { return undoStack.empty() ? nullptr : &undoStack.back(); }
    const Step* nextRedo() const { return redoStack.empty() ? nullptr : &redoStack.back(); }
    const std::deque<Step>& undoSteps() const { return undoStack; }
    const std::deque<Step>& redoSteps() const { return redoStack; }
    Step* find (uint64_t id);

    // Undo or redo the next step. The caller sets the values in the returned step
    // ("before" for undo, "after" for redo); the echoes of those sets are ignored.
    std::optional<Step> undo (double now);
    std::optional<Step> redo (double now);

    // The plugin is about to set this value itself: its echo isn't a change.
    void expect (int index, float value, double now);

    bool isGestureOpen() const { return ! openGestures.empty(); }
    bool hasPending() const { return ! pending.empty(); }

    void clear();

    // Saved with the DAW session, so plugin undo survives closing and reopening it.
    std::string serialise() const;
    bool deserialise (const std::string& text);

private:
    struct Pending
    {
        float before = 0.0f, latest = 0.0f;
        double lastChange = 0.0;
    };

    struct Expected
    {
        float value = 0.0f;
        double until = 0.0;
    };

    Step* commit (double now);
    void trim();

    size_t maxSteps;
    uint64_t nextId = 1;
    std::map<int, float> knownValues;
    std::map<int, Pending> pending;
    std::set<int> openGestures;
    std::map<int, double> hostUntil;
    std::map<int, Expected> expected;
    bool gestureFinished = false;
    std::deque<Step> undoStack, redoStack;
};

} // namespace limitless
