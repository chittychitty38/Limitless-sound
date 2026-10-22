// limitless::Link against a small fake hub, to pin down what the real hub can't easily
// provoke: no hub at all, over-long lines, a handler that throws, a dropped connection,
// "replaced", a dispatcher, and stop() from inside a handler.
// Build and run: c++ -std=c++17 -Wall -Wextra -pthread -o link_test link_test.cpp && ./link_test [folder]
// (Windows: add -lws2_32.) Also run by shared/hub/tests/test_clients.py.
#undef NDEBUG
#include "../limitless_link.hpp"

#include <atomic>
#include <cassert>
#include <chrono>
#include <cstdio>
#include <fstream>
#include <functional>
#include <mutex>
#include <stdexcept>
#include <string>
#include <thread>
#include <vector>

#ifndef _WIN32
#include <sys/stat.h>
#endif

namespace json = limitless::json;
using limitless::Result;
using limitless::detail::kNoSocket;
using limitless::detail::Socket;
using Clock = std::chrono::steady_clock;
using std::chrono::milliseconds;

static std::string root;

static json::Value P(const std::string& text) {
    const auto v = json::parse(text);
    assert(v.has_value());
    return *v;
}

static void makeDir(const std::string& path) {
#ifdef _WIN32
    ::CreateDirectoryA(path.c_str(), nullptr);
#else
    ::mkdir(path.c_str(), 0700);
#endif
}

static std::string useHome(const std::string& name) {
    const std::string home = root + "/" + name;
    makeDir(home);
#ifdef _WIN32
    ::SetEnvironmentVariableA("LIMITLESS_SOUND_HOME", home.c_str());
#else
    ::setenv("LIMITLESS_SOUND_HOME", home.c_str(), 1);
#endif
    return home;
}

static void writeFile(const std::string& path, const std::string& text) {
    std::ofstream(path, std::ios::binary) << text;
}

template <typename Cond>
static bool waitUntil(Cond cond, int ms = 5000) {
    const auto end = Clock::now() + milliseconds(ms);
    while (Clock::now() < end) {
        if (cond()) return true;
        std::this_thread::sleep_for(milliseconds(5));
    }
    return cond();
}

// Listens on 127.0.0.1 and writes link.json, like the real hub; the test plays its part.
class FakeHub {
public:
    explicit FakeHub(const std::string& home) {
        listener_ = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
        assert(listener_ != kNoSocket);
        sockaddr_in addr;
        std::memset(&addr, 0, sizeof addr);
        addr.sin_family = AF_INET;
        addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
        assert(::bind(listener_, reinterpret_cast<sockaddr*>(&addr), sizeof addr) == 0);
        assert(::listen(listener_, 4) == 0);
        socklen_t len = sizeof addr;
        assert(::getsockname(listener_, reinterpret_cast<sockaddr*>(&addr), &len) == 0);
        const unsigned short port = ntohs(addr.sin_port);
        writeFile(home + "/link.json", json::Value(json::Object{{"protocol", 1}, {"port", port}, {"http", 0},
                                                                {"token", token}, {"pid", 1}, {"version", "test"}}).dump());
    }
    ~FakeHub() {
        drop();
        limitless::detail::closeSocket(listener_);
    }

    const std::string token = "the-token";

    // The next connection from the client, if one comes within `ms`.
    bool accept(int ms = 5000) {
        drop();
        if (limitless::detail::waitFor(listener_, false, ms) != 1) return false;
        conn_ = ::accept(listener_, nullptr, nullptr);
#ifdef SO_NOSIGPIPE
        int one = 1;
        ::setsockopt(conn_, SOL_SOCKET, SO_NOSIGPIPE, &one, sizeof one);
#endif
        return conn_ != kNoSocket;
    }

    // The next message from the client, or null when none came within `ms`.
    json::Value read(int ms = 5000) {
        const auto end = Clock::now() + milliseconds(ms);
        for (;;) {
            const auto nl = buf_.find('\n');
            if (nl != std::string::npos) {
                const std::string line = buf_.substr(0, nl);
                buf_.erase(0, nl + 1);
                return P(line);
            }
            const auto left = std::chrono::duration_cast<milliseconds>(end - Clock::now()).count();
            if (left <= 0 || conn_ == kNoSocket || closed_) return json::Value();
            if (limitless::detail::waitFor(conn_, false, static_cast<int>(left)) != 1) continue;
            const long got = limitless::detail::receiveSome(conn_, chunk_.data(), chunk_.size());
            if (got <= 0) {
                closed_ = true;
                return json::Value();
            }
            buf_.append(chunk_.data(), static_cast<std::size_t>(got));
        }
    }

    // True once the client has closed its end.
    bool hungUp(int ms = 3000) {
        const auto end = Clock::now() + milliseconds(ms);
        while (!closed_ && Clock::now() < end) read(50);
        return closed_;
    }

    void send(const json::Value& msg) { sendRaw(msg.dump() + "\n"); }
    void sendRaw(const std::string& text) { assert(limitless::detail::sendAll(conn_, text.data(), text.size())); }

    void drop() {
        if (conn_ != kNoSocket) {
            limitless::detail::shutdownSocket(conn_);
            limitless::detail::closeSocket(conn_);
        }
        conn_ = kNoSocket;
        closed_ = false;
        buf_.clear();
    }

    void welcome(const std::string& prefs = "{}") {
        send(P(R"({"op":"welcome","protocol":1,"prefs":)" + prefs + R"(,"actions":[],"states":{},"tools":["amp"]})"));
    }

private:
    Socket listener_ = kNoSocket;
    Socket conn_ = kNoSocket;
    bool closed_ = false;
    std::string buf_;
    std::vector<char> chunk_ = std::vector<char>(65536);
};

// What the handlers saw, from whichever thread they ran on.
struct Seen {
    std::mutex mu;
    std::vector<bool> connected;
    std::vector<json::Value> prefs;
    std::vector<std::string> events;
    std::vector<Result> answers;

    template <typename T>
    void add(std::vector<T>& list, T v) {
        std::lock_guard<std::mutex> lock(mu);
        list.push_back(std::move(v));
    }
    template <typename T>
    std::size_t size(const std::vector<T>& list) {
        std::lock_guard<std::mutex> lock(mu);
        return list.size();
    }
    template <typename T>
    T at(const std::vector<T>& list, std::size_t i) {
        std::lock_guard<std::mutex> lock(mu);
        return list.at(i);
    }
};

static void lineReader() {
    limitless::detail::LineReader reader(16);
    std::vector<std::string> lines;
    const auto add = [&](const std::string& line) { lines.push_back(line); };
    reader.feed("ab", 2, add);
    reader.feed("c\nde\r\n\n", 7, add);
    assert((lines == std::vector<std::string>{"abc", "de", ""}));
    lines.clear();
    const std::string tooLong = std::string(40, 'x') + "\nok\n";
    reader.feed(tooLong.data(), tooLong.size(), add);
    assert((lines == std::vector<std::string>{"ok"}));
    lines.clear();
    for (int i = 0; i < 10; ++i) reader.feed("xxxxx", 5, add);  // too long, across many reads
    reader.feed("\nfine\n", 6, add);
    assert((lines == std::vector<std::string>{"fine"}));
    lines.clear();
    const std::string atLimit = std::string(15, 'y') + "\n";  // 16 bytes with its newline: kept
    const std::string overLimit = std::string(16, 'z') + "\n";
    reader.feed(atLimit.data(), atLimit.size(), add);
    reader.feed(overLimit.data(), overLimit.size(), add);
    assert((lines == std::vector<std::string>{std::string(15, 'y')}));
    std::printf("line reader: ok\n");
}

static void noHub() {
    useHome("nohub");  // an empty folder: no link.json
    {
        limitless::Link link("amp", "Amp", "1", {{"tuner", "Tuner"}});
        link.setRetryInterval(milliseconds(50));
        int answers = 0;
        Result last;
        link.start();
        std::this_thread::sleep_for(milliseconds(300));
        assert(!link.connected());
        assert(!link.did("tuner") && !link.state("on", true) && !link.say("Tuner on"));
        assert(!link.setActions({{"tuner", "Tuner"}}));
        assert(!link.invoke("zoom.in", json::Object(), [&](const Result& r) {
            last = r;
            ++answers;
        }));
        assert(answers == 1 && !last.ok && !last.message.empty());  // answered at once
        assert(link.prefs().isObject() && link.prefs().size() == 0);
        const auto t0 = Clock::now();
        link.stop();
        assert(Clock::now() - t0 < milliseconds(1000));
        link.start();  // starting again after stop() is fine
    }  // the destructor stops it at once

    // A link.json left behind by a hub that crashed: the port refuses, and still nothing happens.
    const Socket probe = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    sockaddr_in addr;
    std::memset(&addr, 0, sizeof addr);
    addr.sin_family = AF_INET;
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    assert(::bind(probe, reinterpret_cast<sockaddr*>(&addr), sizeof addr) == 0);
    socklen_t len = sizeof addr;
    ::getsockname(probe, reinterpret_cast<sockaddr*>(&addr), &len);
    limitless::detail::closeSocket(probe);
    const std::string home = useHome("stale");
    writeFile(home + "/link.json", R"({"protocol":1,"port":)" + std::to_string(ntohs(addr.sin_port)) + R"(,"token":"t"})");
    const auto t0 = Clock::now();
    {
        limitless::Link link("amp", "Amp");
        link.setRetryInterval(milliseconds(50));
        link.start();
        std::this_thread::sleep_for(milliseconds(300));
        assert(!link.connected() && !link.say("x"));
    }
    assert(Clock::now() - t0 < milliseconds(2500));

    writeFile(home + "/link.json", "not json at all");  // a broken file: the same
    {
        limitless::Link link("amp", "Amp");
        link.start();
        std::this_thread::sleep_for(milliseconds(100));
        assert(!link.connected());
    }
    limitless::Link idle("amp", "Amp");  // a Link that never starts is fine too
    assert(!idle.did("x") && !idle.connected());
    std::printf("no hub: ok\n");
}

static void session() {
    FakeHub hub(useHome("hub"));
    Seen seen;
    limitless::Link link("amp", "My Amp", "1.2.0",
                         {{"nextPreset", "Next preset", "", {"next sound"}}, {"record", "Record", "daw.record"}});
    link.setRetryInterval(milliseconds(100));
    link.onConnected([&](bool on) { seen.add(seen.connected, on); });
    link.onPrefs([&](const json::Value& prefs) { seen.add(seen.prefs, prefs); });
    link.onEvent([&](const std::string& name, const json::Value&, const std::string& source) {
        seen.add(seen.events, name + " from " + source);
    });
    link.onInvoke([&](const std::string& action, const json::Value& args, const std::string& source) -> Result {
        if (action == "boom") throw std::runtime_error("The boom pedal is unplugged.");
        if (action == "mystery") throw 42;
        if (action == "nextPreset") {
            link.did("nextPreset", "", args["step"]);
            return {true, "Preset 2 for " + source};
        }
        return {false, "No such thing."};
    });
    assert(!link.state("ready", true));  // not connected yet, but remembered
    link.start();

    // hello, with everything the hub needs
    assert(hub.accept());
    const json::Value hello = hub.read();
    assert(hello["op"].asString() == "hello" && hello["protocol"].asInt() == 1 && hello["token"].asString() == hub.token);
    assert(hello["tool"].asString() == "amp" && hello["name"].asString() == "My Amp" && hello["version"].asString() == "1.2.0");
    assert(hello["actions"].size() == 2);
    assert(hello["actions"][0] == P(R"({"id":"nextPreset","label":"Next preset","phrases":["next sound"]})"));
    assert(hello["actions"][1] == P(R"({"id":"record","label":"Record","intent":"daw.record"})"));
    assert(hello["subscribe"] == P(R"(["*"])"));
    std::this_thread::sleep_for(milliseconds(100));
    assert(!link.connected() && !link.did("nextPreset"));  // nothing but hello until welcome

    hub.welcome(R"({"oneVoice":true,"textScale":1.25})");
    assert(hub.read() == P(R"({"op":"state","key":"ready","value":true,"depth":0})"));  // set before connecting
    assert(waitUntil([&] { return link.connected() && seen.size(seen.connected) == 1 && seen.size(seen.prefs) == 1; }));
    assert(seen.at(seen.connected, 0) && seen.at(seen.prefs, 0)["textScale"].asNumber() == 1.25);
    assert(link.prefs()["textScale"].asNumber() == 1.25);

    // Telling the suite
    assert(link.say("Tuner on"));
    assert(hub.read() == P(R"({"op":"say","text":"Tuner on"})"));
    assert(link.did("nextPreset", "", 3));
    assert(hub.read() == P(R"({"op":"did","action":"nextPreset","depth":0,"value":3})"));
    assert(link.did("record", "daw.record"));
    assert(hub.read() == P(R"({"op":"did","action":"record","depth":0,"intent":"daw.record"})"));
    assert(link.state("tuner", json::Object{{"on", true}}));
    assert(hub.read() == P(R"({"op":"state","key":"tuner","value":{"on":true},"depth":0})"));
    assert(link.setActions({{"nextPreset", "Next preset"}}));
    assert(hub.read() == P(R"({"op":"actions","actions":[{"id":"nextPreset","label":"Next preset"}]})"));

    // The hub asks: the answer carries its id, and what the handler does carries its depth.
    hub.send(P(R"({"op":"invoke","id":7,"action":"nextPreset","args":{"step":1},"source":"voice","depth":2})"));
    assert(hub.read() == P(R"({"op":"did","action":"nextPreset","depth":2,"value":1})"));
    assert(hub.read() == P(R"({"op":"result","id":7,"ok":true,"message":"Preset 2 for voice"})"));
    // A handler that throws: a refusal that says why, and the product carries on.
    hub.send(P(R"({"op":"invoke","id":8,"action":"boom","args":{},"source":"gaze","depth":0})"));
    assert(hub.read() == P(R"({"op":"result","id":8,"ok":false,"message":"The boom pedal is unplugged."})"));
    hub.send(P(R"({"op":"invoke","id":9,"action":"mystery","source":"gaze"})"));
    assert(hub.read() == P(R"({"op":"result","id":9,"ok":false,"message":"My Amp couldn't do that."})"));
    assert(link.did("nextPreset") && hub.read()["depth"].asInt(-1) == 0);  // depth is back to 0

    // We ask: exactly one answer, the hub's.
    std::atomic<int> answers{0};
    const auto onAnswer = [&](const Result& r) {
        seen.add(seen.answers, r);
        ++answers;
    };
    assert(link.invoke("zoom.in", json::Object{{"step", 2}}, onAnswer));
    const json::Value ask = hub.read();
    assert(ask["op"].asString() == "invoke" && ask["action"].asString() == "zoom.in" && ask["id"].isNumber());
    assert(ask["args"] == P(R"({"step":2})") && ask["depth"].asInt(-1) == 0);
    hub.send(json::Object{{"op", "result"}, {"id", ask["id"]}, {"ok", true}, {"message", "Zoomed in"}});
    assert(waitUntil([&] { return answers == 1; }));
    assert(seen.at(seen.answers, 0).ok && seen.at(seen.answers, 0).message == "Zoomed in");
    assert(link.invoke("hub.status") && hub.read()["args"] == json::Value(json::Object()));  // no callback: fine
    hub.send(P(R"({"op":"result","id":12345,"ok":true,"message":"nobody asked"})"));  // ignored

    // A line longer than 64 KB is skipped whole; the connection and the next line are fine.
    hub.sendRaw(std::string(70000, 'x') + "\n");
    hub.sendRaw("this is not json\n[1,2]\n");
    hub.send(P(R"({"op":"event","name":"zoom.in","value":null,"source":"zoom"})"));
    assert(waitUntil([&] { return seen.size(seen.events) == 1; }));
    assert(seen.at(seen.events, 0) == "zoom.in from zoom");
    // And it never sends a line the hub would hang up on: 64 KB with the newline is the most.
    const std::size_t room = limitless::kMaxLine - std::string(R"({"op":"say","text":""})" "\n").size();
    assert(!link.say(std::string(room + 1, 'a')));
    assert(link.connected() && link.say(std::string(room, 'a')));
    assert(hub.read()["text"].asString().size() == room);

    // The shared settings change: with the one voice off, the product speaks for itself.
    hub.send(P(R"({"op":"prefs","prefs":{"oneVoice":false,"textScale":1.5}})"));
    assert(waitUntil([&] { return seen.size(seen.prefs) == 2; }));
    assert(seen.at(seen.prefs, 1)["textScale"].asNumber() == 1.5 && !link.say("Tuner on"));

    assert(link.state("ready", false) && hub.read()["value"] == json::Value(false));
    assert(link.state("mode", "live") && hub.read()["key"].asString() == "mode");

    // The hub goes away: a question still waiting gets its one answer, and the link says it's down.
    assert(link.invoke("zoom.out", json::Object(), onAnswer));
    assert(hub.read()["action"].asString() == "zoom.out");
    hub.drop();
    for (int i = 0; i < 50; ++i) link.did("nextPreset");  // writing to a closed connection never kills the process
    assert(waitUntil([&] { return answers == 2 && seen.size(seen.connected) == 2; }));
    assert(!seen.at(seen.answers, 1).ok && seen.at(seen.answers, 1).message.find("connection") != std::string::npos);
    assert(!seen.at(seen.connected, 1) && !link.connected());

    // It comes back by itself: hello again, then the latest value of every state it holds.
    assert(hub.accept());
    assert(hub.read()["op"].asString() == "hello");
    hub.welcome();
    assert(hub.read() == P(R"({"op":"state","key":"ready","value":false,"depth":0})"));
    assert(hub.read() == P(R"({"op":"state","key":"tuner","value":{"on":true},"depth":0})"));
    assert(hub.read() == P(R"({"op":"state","key":"mode","value":"live","depth":0})"));
    assert(waitUntil([&] { return link.connected() && seen.size(seen.connected) == 3; }));
    assert(link.say("back") && hub.read()["text"].asString() == "back");  // oneVoice is on unless it says off

    // A newer copy of the product connected: this one steps aside for good.
    hub.send(P(R"({"op":"error","code":"replaced","message":"Another copy of this app connected; closing this one."})"));
    assert(waitUntil([&] { return !link.connected() && seen.size(seen.connected) == 4; }));
    assert(!hub.accept(800));  // no reconnect, though it would otherwise try every 100 ms
    link.start();
    assert(!hub.accept(500));  // not even when started again
    std::printf("session: ok\n");
}

static void refusedBeforeWelcome() {
    FakeHub hub(useHome("refused"));
    limitless::Link link("amp", "Amp");
    link.setRetryInterval(milliseconds(100));
    link.start();
    assert(hub.accept() && hub.read()["op"].asString() == "hello");
    hub.send(P(R"({"op":"error","message":"Wrong token. Read link.json again."})"));
    assert(hub.hungUp());     // it closes...
    assert(hub.accept(3000));  // ...and tries again a little later
    assert(hub.read()["op"].asString() == "hello");
    hub.welcome();
    assert(waitUntil([&] { return link.connected(); }));
    hub.send(P(R"({"op":"error","message":"Unknown op 'x'."})"));  // after welcome: just a note
    hub.send(P(R"({"op":"pong"})"));
    std::this_thread::sleep_for(milliseconds(200));
    assert(link.connected() && link.did("still") && hub.read()["action"].asString() == "still");
    std::printf("refused before welcome: ok\n");
}

static void dispatcher() {
    FakeHub hub(useHome("dispatch"));
    std::mutex queueMu;
    std::vector<std::function<void()>> queue;
    const auto drain = [&] {
        std::vector<std::function<void()>> jobs;
        {
            std::lock_guard<std::mutex> lock(queueMu);
            jobs.swap(queue);
        }
        for (auto& job : jobs) job();
        return jobs.size();
    };
    std::atomic<int> ups{0};
    std::atomic<int> handled{0};
    std::thread::id handlerThread;
    {
        limitless::Link link("amp", "Amp", "1", {{"tuner", "Tuner"}});
        link.setRetryInterval(milliseconds(100));
        link.setDispatch([&](std::function<void()> job) {
            std::lock_guard<std::mutex> lock(queueMu);
            queue.push_back(std::move(job));
        });
        link.onConnected([&](bool on) { ups += on ? 1 : 0; });
        link.onInvoke([&](const std::string&, const json::Value&, const std::string&) -> Result {
            handlerThread = std::this_thread::get_id();
            ++handled;
            return {true, "Tuner on"};
        });
        link.start();
        assert(hub.accept() && hub.read()["op"].asString() == "hello");
        hub.welcome();
        assert(waitUntil([&] { return link.connected(); }));
        std::this_thread::sleep_for(milliseconds(100));
        assert(ups == 0);  // handlers wait for the dispatcher...
        drain();
        assert(ups == 1);  // ...and run where it runs them
        hub.send(P(R"({"op":"invoke","id":1,"action":"tuner","args":{},"source":"voice","depth":0})"));
        assert(hub.read(300).isNull());  // no answer until the job runs
        assert(waitUntil([&] { return drain() > 0; }));
        assert(handlerThread == std::this_thread::get_id());
        assert(hub.read() == P(R"({"op":"result","id":1,"ok":true,"message":"Tuner on"})"));

        hub.send(P(R"({"op":"invoke","id":2,"action":"tuner","args":{},"source":"voice","depth":0})"));
        assert(waitUntil([&] {
            std::lock_guard<std::mutex> lock(queueMu);
            return !queue.empty();
        }));
        const auto t0 = Clock::now();
        link.stop();
        assert(Clock::now() - t0 < milliseconds(1000));
        assert(hub.hungUp());

        link.start();  // it can start again, and the job queued before stop() still never runs
        assert(hub.accept() && hub.read()["op"].asString() == "hello");
        hub.welcome();
        assert(waitUntil([&] {
            std::lock_guard<std::mutex> lock(queueMu);
            return queue.size() >= 4;  // the stale invoke, then onConnected, onPrefs, onActions
        }));
        drain();
        assert(handled == 1 && ups == 2);
        assert(hub.read(300).isNull());  // and no answer went out for it

        hub.send(P(R"({"op":"event","name":"zoom.in","value":1,"source":"zoom"})"));
        assert(waitUntil([&] {
            std::lock_guard<std::mutex> lock(queueMu);
            return !queue.empty();
        }));
    }  // the Link is gone while a job waits
    drain();  // it does nothing, safely
    assert(handled == 1 && ups == 2);
    std::printf("dispatcher: ok\n");
}

static void stopFromHandler() {
    FakeHub hub(useHome("inside"));
    std::atomic<bool> stoppedInside{false};
    limitless::Link link("amp", "Amp", "1", {{"quit", "Quit"}});
    link.onInvoke([&](const std::string&, const json::Value&, const std::string&) -> Result {
        link.stop();  // from the link's own thread: no deadlock
        stoppedInside = true;
        return true;
    });
    link.start();
    assert(hub.accept() && hub.read()["op"].asString() == "hello");
    hub.welcome();
    assert(waitUntil([&] { return link.connected(); }));
    hub.send(P(R"({"op":"invoke","id":1,"action":"quit","args":{},"source":"voice","depth":0})"));
    assert(waitUntil([&] { return stoppedInside.load(); }));
    assert(hub.hungUp());
    std::printf("stop from a handler: ok\n");
}  // and the destructor, on this thread, finishes it

int main(int argc, char** argv) {
#ifdef _WIN32
    WSADATA data;
    ::WSAStartup(MAKEWORD(2, 2), &data);
    char temp[MAX_PATH];
    ::GetTempPathA(MAX_PATH, temp);
    root = argc > 1 ? argv[1] : std::string(temp) + "limitless-link-test-" + std::to_string(::GetCurrentProcessId());
#else
    char temp[] = "/tmp/limitless-link-test-XXXXXX";
    root = argc > 1 ? argv[1] : (::mkdtemp(temp) != nullptr ? temp : "/tmp");
#endif
    makeDir(root);
    lineReader();
    noHub();
    session();
    refusedBeforeWelcome();
    dispatcher();
    stopFromHandler();
    std::printf("link_test: all passed\n");
    return 0;
}
