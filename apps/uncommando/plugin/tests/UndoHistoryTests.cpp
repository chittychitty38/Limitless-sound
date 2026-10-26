// Tests for the Uncommando plugin's undo history. Plain C++, no framework: run the binary,
// it prints each failure and returns non-zero if any.

#include "../core/UndoHistory.h"

#include <cmath>
#include <cstdio>
#include <functional>
#include <string>
#include <vector>

using limitless::UndoHistory;

static int failures = 0;

#define CHECK(cond)                                                              \
    do {                                                                         \
        if (! (cond)) {                                                          \
            std::printf ("  FAILED %s:%d  %s\n", __FILE__, __LINE__, #cond);    \
            ++failures;                                                          \
        }                                                                        \
    } while (0)

static bool near (float a, float b) { return std::abs (a - b) < 1.0e-6f; }

static UndoHistory knobs (int count = 4)
{
    UndoHistory h;
    for (int i = 0; i < count; ++i)
        h.setKnown (i, 0.5f);
    return h;
}

static void dragIsOneStep()
{
    auto h = knobs();
    h.gestureBegin (1, 0.0);
    for (int i = 1; i <= 20; ++i)
        h.valueChanged (1, 0.5f + i * 0.01f, i * 0.01);
    CHECK (h.tick (0.3) == nullptr);           // still dragging
    h.gestureEnd (1, 0.31);
    auto* s = h.tick (0.32);
    CHECK (s != nullptr);
    CHECK (s->changes.size() == 1);
    CHECK (near (s->changes[0].before, 0.5f) && near (s->changes[0].after, 0.7f));
    CHECK (h.tick (0.4) == nullptr);           // nothing more
}

static void gestureWithoutChangeIsNoStep()
{
    auto h = knobs();
    h.gestureBegin (2, 0.0);
    h.gestureEnd (2, 0.1);
    CHECK (h.tick (0.2) == nullptr);
    CHECK (! h.canUndo());
}

static void changesWithoutGestureAreGrouped()
{
    auto h = knobs();
    h.valueChanged (0, 0.1f, 0.00);   // a preset load: many knobs at once
    h.valueChanged (1, 0.2f, 0.01);
    h.valueChanged (2, 0.3f, 0.02);
    CHECK (h.tick (0.10) == nullptr);           // wait in case more come
    auto* s = h.tick (0.40);
    CHECK (s != nullptr && s->changes.size() == 3);
}

static void undoAndRedoRestoreValues()
{
    auto h = knobs();
    h.gestureBegin (0, 0);
    h.valueChanged (0, 0.9f, 0.1);
    h.gestureEnd (0, 0.2);
    h.tick (0.2);
    h.gestureBegin (3, 1);
    h.valueChanged (3, 0.1f, 1.1);
    h.gestureEnd (3, 1.2);
    h.tick (1.2);

    auto u = h.undo (2.0);
    CHECK (u && u->changes[0].index == 3 && near (u->changes[0].before, 0.5f));
    // The plugin now sets knob 3 back: that echo is not a new change.
    h.valueChanged (3, 0.5f, 2.01);
    CHECK (h.tick (3.0) == nullptr);
    CHECK (h.canRedo());

    auto u2 = h.undo (3.1);
    CHECK (u2 && u2->changes[0].index == 0);
    CHECK (! h.canUndo());
    CHECK (! h.undo (3.2));

    auto r = h.redo (3.3);
    CHECK (r && r->changes[0].index == 0 && near (r->changes[0].after, 0.9f));
    h.valueChanged (0, 0.9f, 3.31);
    CHECK (h.tick (4.0) == nullptr);
    CHECK (h.nextRedo() && h.nextRedo()->changes[0].index == 3);
}

static void newChangeEndsRedo()
{
    auto h = knobs();
    h.valueChanged (0, 0.9f, 0.0);
    h.tick (1.0);
    h.undo (1.1);
    h.valueChanged (0, 0.5f, 1.11);    // echo
    h.valueChanged (1, 0.8f, 2.0);     // a new change
    h.tick (3.0);
    CHECK (! h.canRedo());
    CHECK (h.canUndo());
}

static void automationIsNeverAStep()
{
    auto h = knobs();
    for (int i = 0; i < 50; ++i)
    {
        double t = i * 0.01;
        float v = 0.5f + 0.4f * std::sin ((float) i);
        h.hostChanged (2, v, t);         // the DAW sets it
        h.valueChanged (2, v, t + 0.001); // and the plugin reports it back
    }
    CHECK (h.tick (2.0) == nullptr);
    CHECK (! h.canUndo());
    CHECK (h.known (2).has_value());

    // But the person grabbing that knob while automation plays is a change.
    h.gestureBegin (2, 2.1);
    h.valueChanged (2, 0.05f, 2.15);
    h.gestureEnd (2, 2.2);
    auto* s = h.tick (2.2);
    CHECK (s && near (s->changes[0].after, 0.05f));
}

static void undoFlushesAChangeStillWaiting()
{
    auto h = knobs();
    h.valueChanged (1, 0.75f, 0.0);
    auto u = h.undo (0.05);              // pressed ⌥⌘Z straight away
    CHECK (u && u->changes[0].index == 1 && near (u->changes[0].before, 0.5f));
}

static void historyHasALimit()
{
    UndoHistory h (10);
    h.setKnown (0, 0.0f);
    for (int i = 1; i <= 25; ++i)
    {
        h.valueChanged (0, i / 100.0f, i);
        h.tick (i + 0.5);
    }
    CHECK (h.undoSteps().size() == 10);
    CHECK (h.undoSteps().front().id == 16);
}

static void savesAndRestores()
{
    auto h = knobs();
    h.valueChanged (0, 0.25f, 0);
    auto* s = h.tick (1);
    s->label = "Band 2\tGain \\ \"x\"";
    s->before = "-3.1 dB";
    s->after = "+2.4 dB";
    h.gestureBegin (1, 2);
    h.valueChanged (1, 0.125f, 2.1);
    h.valueChanged (2, 0.875f, 2.1);
    h.gestureEnd (1, 2.2);
    h.tick (2.2);
    h.undo (3);

    auto text = h.serialise();
    UndoHistory back;
    CHECK (back.deserialise (text));
    CHECK (back.undoSteps().size() == 1 && back.redoSteps().size() == 1);
    CHECK (back.undoSteps()[0].label == "Band 2\tGain \\ \"x\"");
    CHECK (back.undoSteps()[0].after == "+2.4 dB");
    CHECK (back.redoSteps()[0].changes.size() == 2);
    CHECK (near (back.redoSteps()[0].changes[1].after, 0.875f));

    // New steps never reuse an id, so the Uncommando app can't mix them up.
    back.setKnown (3, 0.5f);
    back.valueChanged (3, 0.6f, 10);
    auto* n = back.tick (11);
    CHECK (n && n->id > h.redoSteps()[0].id);

    // A damaged history is refused and leaves the current one as it was.
    auto size = back.undoSteps().size();
    CHECK (! back.deserialise ("nonsense"));
    CHECK (! back.deserialise ("LUH1 5\nU 1 2 x\ty\tz\n0 0 1\n"));   // a change line missing
    CHECK (back.undoSteps().size() == size);
}

static void findsStepsById()
{
    auto h = knobs();
    h.valueChanged (0, 0.1f, 0);
    auto id = h.tick (1)->id;
    CHECK (h.find (id) != nullptr);
    h.undo (2);
    CHECK (h.find (id) != nullptr);
    CHECK (h.find (999) == nullptr);
}

int main()
{
    std::vector<std::pair<const char*, std::function<void()>>> tests {
        { "a drag is one step", dragIsOneStep },
        { "a gesture without a change is no step", gestureWithoutChangeIsNoStep },
        { "changes without a gesture are grouped", changesWithoutGestureAreGrouped },
        { "undo and redo restore values", undoAndRedoRestoreValues },
        { "a new change ends redo", newChangeEndsRedo },
        { "automation is never a step", automationIsNeverAStep },
        { "undo flushes a change still waiting", undoFlushesAChangeStillWaiting },
        { "history has a limit", historyHasALimit },
        { "saves and restores", savesAndRestores },
        { "finds steps by id", findsStepsById },
    };
    for (auto& [name, fn] : tests)
    {
        int before = failures;
        fn();
        std::printf ("%s %s\n", failures == before ? "ok  " : "FAIL", name);
    }
    std::printf ("%d failure(s)\n", failures);
    return failures == 0 ? 0 : 1;
}
