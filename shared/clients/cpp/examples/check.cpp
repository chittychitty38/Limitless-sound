// A Color-like product over the real hub, in C++. Used by shared/hub/tests/test_clients.py,
// and a product to try the Limitless Access Standard test kit on:
//
//   python3 standard/conformance/las_check.py --tool color --try on,off --level adaptive
//   LIMITLESS_SOUND_HOME=<the folder it prints> ./check --stay 30
//
// Build: c++ -std=c++17 -pthread -o check check.cpp   (Windows: add -lws2_32, or use CMake)
#include "../limitless_link.hpp"

#include <chrono>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <mutex>
#include <string>
#include <thread>

namespace json = limitless::json;

static void print(const std::string& line) {
    static std::mutex lock;
    std::lock_guard<std::mutex> hold(lock);
    std::printf("%s\n", line.c_str());
    std::fflush(stdout);
}

int main(int argc, char** argv) {
    double stay = 3.0;  // seconds to stay after joining: --stay 30 for the test kit
    for (int i = 1; i + 1 < argc; ++i)
        if (std::strcmp(argv[i], "--stay") == 0) stay = std::atof(argv[i + 1]);

    limitless::Link link("color", "Limitless Color", "test",
                         {{"on", "Screen colors on"}, {"off", "Screen colors off"}});
    link.state("ready", true);  // before connecting: the hub still hears it

    // Honor the shared settings this product supports, and say so (Adaptive, level 2).
    link.onPrefs([&link](const json::Value& prefs) {
        link.state("prefs.applied", json::Object{{"textScale", prefs["textScale"].asNumber(1.0)},
                                                 {"highContrast", prefs["highContrast"].asBool(false)},
                                                 {"reduceMotion", prefs["reduceMotion"].asBool(false)}});
    });
    link.onInvoke([&link](const std::string& action, const json::Value&, const std::string&) -> limitless::Result {
        if (action != "on" && action != "off") return {false, "Limitless Color has no action called " + action + "."};
        link.state("filter", action == "on");
        return {true, "cpp did " + action};
    });
    link.onEvent([](const std::string& name, const json::Value&, const std::string&) { print("EVENT " + name); });
    link.onConnected([](bool on) { print(on ? "CONNECTED true" : "CONNECTED false"); });
    link.start();

    const auto joinBy = std::chrono::steady_clock::now() + std::chrono::seconds(20);  // cold CI starts
    while (!link.connected() && std::chrono::steady_clock::now() < joinBy)
        std::this_thread::sleep_for(std::chrono::milliseconds(20));

    // Ask another product in the suite to do something, and hear its answer.
    link.invoke("zoom.in", json::Object(), [](const limitless::Result& r) {
        print(std::string("RESULT ") + (r.ok ? "ok " : "refused ") + r.message);
    });
    std::this_thread::sleep_for(std::chrono::milliseconds(static_cast<long long>(stay * 1000)));
    link.stop();
    return 0;
}
