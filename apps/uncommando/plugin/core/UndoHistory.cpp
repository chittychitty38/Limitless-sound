#include "UndoHistory.h"

#include <algorithm>
#include <cmath>
#include <cstdio>
#include <cstdlib>
#include <sstream>

namespace limitless
{

void UndoHistory::setKnown (int index, float value)
{
    knownValues[index] = value;
}

std::optional<float> UndoHistory::known (int index) const
{
    auto it = knownValues.find (index);
    if (it == knownValues.end())
        return std::nullopt;
    return it->second;
}

void UndoHistory::gestureBegin (int index, double now)
{
    openGestures.insert (index);
    if (pending.count (index) == 0)
        if (auto k = known (index))
            pending[index] = { *k, *k, now };
}

void UndoHistory::gestureEnd (int index, double now)
{
    openGestures.erase (index);
    if (auto it = pending.find (index); it != pending.end())
        it->second.lastChange = now;
    gestureFinished = true;
}

void UndoHistory::valueChanged (int index, float value, double now)
{
    // The echo of a value this plugin set itself, for undo or redo.
    if (auto it = expected.find (index); it != expected.end())
    {
        if (now <= it->second.until && std::abs (it->second.value - value) <= epsilon)
        {
            knownValues[index] = value;
            return;
        }
        expected.erase (it);
    }

    // Automation moves knobs too. Without a gesture, a change right after the DAW
    // set this knob is the DAW's, not the person's.
    if (openGestures.count (index) == 0)
        if (auto it = hostUntil.find (index); it != hostUntil.end() && now <= it->second)
        {
            knownValues[index] = value;
            return;
        }

    auto k = known (index);
    if (k && std::abs (*k - value) <= epsilon && pending.count (index) == 0)
        return;

    auto it = pending.find (index);
    if (it == pending.end())
        pending[index] = { k.value_or (value), value, now };
    else
    {
        it->second.latest = value;
        it->second.lastChange = now;
    }
    knownValues[index] = value;
}

void UndoHistory::hostChanged (int index, float value, double now)
{
    knownValues[index] = value;
    hostUntil[index] = now + hostSeconds;
    // A change the person was still making is overtaken by the DAW.
    if (openGestures.count (index) == 0)
        if (auto it = pending.find (index); it != pending.end())
            it->second.latest = value;
}

void UndoHistory::expect (int index, float value, double now)
{
    expected[index] = { value, now + 0.5 };
    knownValues[index] = value;
}

Step* UndoHistory::tick (double now)
{
    if (pending.empty() || ! openGestures.empty())
        return nullptr;

    double last = 0.0;
    for (auto& [index, p] : pending)
        last = std::max (last, p.lastChange);

    if (gestureFinished || now - last >= groupSeconds)
        return commit (now);
    return nullptr;
}

Step* UndoHistory::flush (double now)
{
    if (pending.empty())
        return nullptr;
    openGestures.clear();
    return commit (now);
}

Step* UndoHistory::commit (double now)
{
    Step step;
    for (auto& [index, p] : pending)
        if (std::abs (p.before - p.latest) > epsilon)
            step.changes.push_back ({ index, p.before, p.latest });

    pending.clear();
    gestureFinished = false;

    if (step.changes.empty())
        return nullptr;

    step.id = nextId++;
    step.time = now;
    undoStack.push_back (std::move (step));
    redoStack.clear();   // a new change ends redo, as in any undo
    trim();
    return &undoStack.back();
}

void UndoHistory::trim()
{
    while (undoStack.size() > maxSteps)
        undoStack.pop_front();
}

Step* UndoHistory::find (uint64_t id)
{
    for (auto* stack : { &undoStack, &redoStack })
        for (auto& s : *stack)
            if (s.id == id)
                return &s;
    return nullptr;
}

std::optional<Step> UndoHistory::undo (double now)
{
    flush (now);
    if (undoStack.empty())
        return std::nullopt;

    Step step = undoStack.back();
    undoStack.pop_back();
    for (auto& c : step.changes)
        expect (c.index, c.before, now);
    redoStack.push_back (step);
    return step;
}

std::optional<Step> UndoHistory::redo (double now)
{
    flush (now);
    if (redoStack.empty())
        return std::nullopt;

    Step step = redoStack.back();
    redoStack.pop_back();
    for (auto& c : step.changes)
        expect (c.index, c.after, now);
    undoStack.push_back (step);
    return step;
}

void UndoHistory::clear()
{
    pending.clear();
    openGestures.clear();
    hostUntil.clear();
    expected.clear();
    undoStack.clear();
    redoStack.clear();
    gestureFinished = false;
}

// Saving ---------------------------------------------------------------------------
//
//   LUH1 <next id>
//   U|R <id> <number of changes> <label>\t<before>\t<after>
//   <index> <before> <after>          (one line per change)

static std::string escape (const std::string& s)
{
    std::string out;
    for (char c : s)
    {
        if (c == '\\') out += "\\\\";
        else if (c == '\t') out += "\\t";
        else if (c == '\n') out += "\\n";
        else if (c == '\r') out += "\\r";
        else out += c;
    }
    return out;
}

static std::string unescape (const std::string& s)
{
    std::string out;
    for (size_t i = 0; i < s.size(); ++i)
    {
        if (s[i] == '\\' && i + 1 < s.size())
        {
            char n = s[++i];
            out += n == 't' ? '\t' : n == 'n' ? '\n' : n == 'r' ? '\r' : n;
        }
        else
            out += s[i];
    }
    return out;
}

static std::string number (float v)
{
    char buf[32];
    std::snprintf (buf, sizeof (buf), "%.9g", (double) v);
    return buf;
}

std::string UndoHistory::serialise() const
{
    std::ostringstream out;
    out << "LUH1 " << nextId << "\n";
    auto write = [&out] (char kind, const Step& s)
    {
        out << kind << ' ' << s.id << ' ' << s.changes.size() << ' '
            << escape (s.label) << '\t' << escape (s.before) << '\t' << escape (s.after) << "\n";
        for (auto& c : s.changes)
            out << c.index << ' ' << number (c.before) << ' ' << number (c.after) << "\n";
    };
    for (auto& s : undoStack) write ('U', s);
    for (auto& s : redoStack) write ('R', s);
    return out.str();
}

bool UndoHistory::deserialise (const std::string& text)
{
    std::istringstream in (text);
    std::string line;
    if (! std::getline (in, line) || line.rfind ("LUH1 ", 0) != 0)
        return false;

    std::deque<Step> undos, redos;
    uint64_t next = std::strtoull (line.c_str() + 5, nullptr, 10);

    while (std::getline (in, line))
    {
        if (line.empty())
            continue;
        if (line.size() < 2 || (line[0] != 'U' && line[0] != 'R') || line[1] != ' ')
            return false;

        Step s;
        std::istringstream head (line.substr (2));
        size_t count = 0;
        if (! (head >> s.id >> count) || count > 100000)
            return false;
        head.get();   // the space before the words
        std::string words;
        std::getline (head, words);
        auto t1 = words.find ('\t');
        auto t2 = t1 == std::string::npos ? t1 : words.find ('\t', t1 + 1);
        if (t2 == std::string::npos)
            return false;
        s.label = unescape (words.substr (0, t1));
        s.before = unescape (words.substr (t1 + 1, t2 - t1 - 1));
        s.after = unescape (words.substr (t2 + 1));

        for (size_t i = 0; i < count; ++i)
        {
            std::string changeLine;
            if (! std::getline (in, changeLine))
                return false;
            std::istringstream cl (changeLine);
            ParamChange c;
            if (! (cl >> c.index >> c.before >> c.after))
                return false;
            s.changes.push_back (c);
        }
        next = std::max (next, s.id + 1);
        (line[0] == 'U' ? undos : redos).push_back (std::move (s));
    }

    clear();
    undoStack = std::move (undos);
    redoStack = std::move (redos);
    nextId = std::max<uint64_t> (next, 1);
    trim();
    return true;
}

} // namespace limitless
