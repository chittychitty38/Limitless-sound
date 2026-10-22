# Limitless Link for C++

Connect an instrument, plug-in, amp modeler, DAW extension or hardware bridge to the
Limitless Sound hub, so any input a disabled musician can use (eyes, voice, one hand, a
single switch) can drive your product. It is how a product meets the
[Limitless Access Standard](../../../standard/README.md).

One header, [`limitless_link.hpp`](limitless_link.hpp): C++17, the standard library and the
operating system's sockets, nothing else. It reads on its own thread, reconnects by itself,
and does nothing at all when the hub isn't running, so your product behaves exactly as it
always did on a computer without Limitless Sound.

## Add it

Copy `limitless_link.hpp` into your project, then:

- **Threads:** link your platform's threads (`-pthread`, or `Threads::Threads` in CMake).
- **Windows:** link `ws2_32` (with MSVC the header does it for you), and include the header
  before `<windows.h>` unless you define `WIN32_LEAN_AND_MEAN`.

```cmake
find_package(Threads REQUIRED)
target_include_directories(MyProduct PRIVATE third_party/limitless)  # the folder holding the header
target_link_libraries(MyProduct PRIVATE Threads::Threads $<$<PLATFORM_ID:Windows>:ws2_32>)
```

[`examples/`](examples) is a complete product with a minimal `CMakeLists.txt`.

## Use it

```cpp
#include "limitless_link.hpp"

limitless::Link link("myamp", "My Amp", "1.2.0", {{"nextPreset", "Next preset"}, {"tuner", "Tuner"}});
link.onInvoke([&](const std::string& action, const limitless::json::Value& /*args*/,
                  const std::string& /*source: "voice", "gaze", ...*/) -> limitless::Result {
    if (action == "nextPreset") { amp.nextPreset(); return {true, amp.presetName()}; }
    if (action == "tuner") { amp.toggleTuner(); return {true, "Tuner"}; }
    return {false, "My Amp can't do that yet."};   // a refusal always says why
});
link.start();
link.did("nextPreset");                           // after the musician did it by hand, too
link.state("tuner", true);                        // remembered, and told again after a reconnect
```

| Call | What it does |
|---|---|
| `Link(tool, name, version, actions)` | `tool` is a short lowercase id that never changes. Each action has an `id`, a plain-language `label` (what a screen reader says) and, for transport-style actions, a shared `intent` such as `daw.record`. |
| `start()`, `stop()` | Start the link's thread (returns at once); disconnect and stop. The destructor stops it too. No handler runs after `stop()` returns. |
| `onInvoke(fn)` | Do one of your actions: `(action, args, source) -> Result`. Answer within 3 seconds. An exception becomes a refusal carrying its `what()`. |
| `onEvent(fn)` | Hear what happens in the suite: `(name, value, source)`, e.g. `daw.record`. |
| `onPrefs(fn)` | The musician's shared settings, on joining and on every change. |
| `onConnected(fn)`, `onActions(fn)` | Joined or lost the hub; the suite's action list changed. |
| `setDispatch(fn)` | Where handlers run. Without it, on the link's thread. |
| `did(action, intent = "", value = null)` | "I just did this", from any input. |
| `state(key, value)` | A state changed. Sent before connecting, it reaches the hub on connecting. |
| `say(text)` | Speak through the suite's one voice. `false` means speak for yourself as before (no hub, or the musician turned the one voice off). |
| `invoke(action, args = {}, onResult)` | Ask the suite: `"zoom.in"`, `"daw.record"`, `"hub.say"` with `{"text": ...}`. `onResult` gets exactly one answer. |
| `setActions(list)` | Replace your action list (another amp model loaded, say). |
| `connected()`, `prefs()` | Whether the hub is there; the latest shared settings. |
| `limitless::json::Value`, `json::parse(text)`, `value.dump()` | The small JSON type inside the header, for args, values and prefs. Lookups never throw: `prefs["textScale"].asNumber(1.0)`. |

Every call is safe from any thread, but not from a real-time audio callback: sending can wait
on a socket. Messages over 64 KB are never sent (the hub would hang up), lines over 64 KB
from the hub are skipped, and text that isn't valid UTF-8 is repaired so the hub can read it.

## Level 2: honor the shared settings

Apply the settings you support, then report what you applied as the state `prefs.applied`.
That is how the hub's settings page, and the test kit, know a setting reached you.

```cpp
link.onPrefs([&](const limitless::json::Value& prefs) {
    const double scale = prefs["textScale"].asNumber(1.0);
    const bool contrast = prefs["highContrast"].asBool(false);
    const bool calm = prefs["reduceMotion"].asBool(false);
    ui.apply(scale, contrast, calm);
    link.state("prefs.applied", limitless::json::Object{
        {"textScale", scale}, {"highContrast", contrast}, {"reduceMotion", calm}});
});
```

## In a JUCE plug-in

A DAW loads every instance of a plug-in into one process, and the hub keeps one connection
per tool id: a newer connection replaces the older one, which then steps aside for good. So
share one `Link` for the whole plug-in with `juce::SharedResourcePointer`, and send handlers
to the message thread:

```cpp
struct AmpLink {
    limitless::Link link{"myamp", "My Amp", JucePlugin_VersionString,
                         {{"nextPreset", "Next preset"}, {"prevPreset", "Previous preset"}, {"tuner", "Tuner"}}};
    AmpLink() {
        link.setDispatch([](std::function<void()> job) { juce::MessageManager::callAsync(std::move(job)); });
        link.start();
    }
};

class MyAmpProcessor : public juce::AudioProcessor {
    juce::SharedResourcePointer<AmpLink> amp;   // one link however many instances
public:
    MyAmpProcessor() {
        amp->link.onInvoke([this](const std::string& action, const limitless::json::Value&,
                                  const std::string&) -> limitless::Result {
            if (action == "nextPreset") {       // runs on the message thread
                setCurrentProgram((getCurrentProgram() + 1) % getNumPrograms());
                return {true, getProgramName(getCurrentProgram()).toStdString()};
            }
            return {false, "My Amp can't do that yet."};
        });
    }
    ~MyAmpProcessor() override { amp->link.onInvoke(nullptr); }
    // ...
};
```

- With several instances open, route actions to the one the musician touched last.
- Report presets changed by hand with `did("nextPreset")` from the message thread, never
  from `processBlock`.
- Keep the `Link` in an object like this, not in a global: on Windows a global is destroyed
  while the plug-in's DLL unloads, when waiting for a thread can hang the host.

## Not like the app clients

- It never starts the hub app itself: a plug-in inside a DAW shouldn't launch programs. The
  musician can have Limitless Sound start when they sign in (**My apps** on the hub's page).
- `invoke`'s callback always gets exactly one answer: the hub's, or a refusal when the suite
  isn't there or the connection drops.

## Test it

```sh
c++ -std=c++17 -Wall -Wextra -Werror -pthread -o json_test tests/json_test.cpp && ./json_test
c++ -std=c++17 -Wall -Wextra -Werror -pthread -o link_test tests/link_test.cpp && ./link_test
cd ../../hub && python -m pytest -q tests/test_clients.py   # against the real hub
```

Then check your own product with the
[Limitless Access Standard test kit](../../../standard/conformance/):

```sh
python3 standard/conformance/las_check.py --tool myamp --try-all --level adaptive
# start your product with the LIMITLESS_SOUND_HOME it prints
```
