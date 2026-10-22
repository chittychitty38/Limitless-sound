// Limitless Link for C++: connect an instrument, plug-in, amp modeler, DAW extension or
// hardware bridge to the Limitless Sound hub, so that any input a disabled musician can use
// (eyes, voice, one hand, a single switch) can drive your product. This is the open protocol
// behind the Limitless Access Standard (standard/README.md). The protocol: shared/PROTOCOL.md.
//
// One header, C++17, nothing to install: only the standard library and the operating
// system's sockets. On Windows link ws2_32 (MSVC does that for you through a pragma), and
// include this header before <windows.h> unless WIN32_LEAN_AND_MEAN is defined.
//
// What it does for you:
//   - finds the hub through link.json in the suite folder and connects to 127.0.0.1;
//   - says hello with your actions, and tries again every couple of seconds while the hub
//     isn't running. With no hub nothing else happens: your product works exactly as before;
//   - reads on its own thread and answers the hub through your handlers. An exception thrown
//     by a handler becomes a refusal that says why, never a crash;
//   - remembers your states and tells the hub again after every reconnect;
//   - steps aside for good when a newer copy of your product connects.
//
// A plug-in with two actions that honors the musician's shared settings (Adaptive, level 2):
//
//   limitless::Link link("myamp", "My Amp", "1.2.0", {{"nextPreset", "Next preset"}, {"tuner", "Tuner"}});
//   link.onInvoke([&](const std::string& action, const limitless::json::Value&, const std::string&)
//                     -> limitless::Result {
//       if (action == "nextPreset") { amp.nextPreset(); return {true, amp.presetName()}; }
//       if (action == "tuner") { amp.toggleTuner(); return {true, "Tuner"}; }
//       return {false, "My Amp can't do that yet."};      // a refusal always says why
//   });
//   link.onPrefs([&](const limitless::json::Value& prefs) {  // on joining, and on every change
//       ui.apply(prefs["textScale"].asNumber(1.0), prefs["highContrast"].asBool(), prefs["reduceMotion"].asBool());
//       link.state("prefs.applied", limitless::json::Object{{"textScale", ui.textScale()},
//                  {"highContrast", ui.highContrast()}, {"reduceMotion", ui.reduceMotion()}});
//   });
//   link.start();                                          // returns at once, hub or no hub
//   link.did("nextPreset");                                // after the musician did it by hand, too
//   if (!link.say("Tuner on")) speakForMyself("Tuner on");
//
// Handlers run on the link's own thread, or wherever setDispatch() sends them (for example
// juce::MessageManager::callAsync). Keep them short. Every method is safe to call from any
// thread, but never from a real-time audio callback: sending can wait on a socket.

#pragma once

#include <atomic>
#include <chrono>
#include <cmath>
#include <condition_variable>
#include <cstddef>
#include <cstdlib>
#include <cstring>
#include <exception>
#include <functional>
#include <iomanip>
#include <locale>
#include <map>
#include <memory>
#include <mutex>
#include <optional>
#include <sstream>
#include <string>
#include <string_view>
#include <thread>
#include <type_traits>
#include <utility>
#include <vector>

#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#include <windows.h>
#ifdef _MSC_VER
#pragma comment(lib, "ws2_32.lib")
#endif
#else
#include <arpa/inet.h>
#include <cerrno>
#include <fcntl.h>
#include <fstream>
#include <netinet/in.h>
#include <netinet/tcp.h>
#include <poll.h>
#include <pwd.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>
#endif

namespace limitless {

inline constexpr int kProtocol = 1;
// The longest message line either side may send, newline included (PROTOCOL.md).
inline constexpr std::size_t kMaxLine = 64 * 1024;

// ===================================================================================== JSON
// A small JSON value: enough for the protocol, and for the values you send with it.

namespace json {

enum class Type { Null, Boolean, Number, String, Array, Object };

class Value;
using Array = std::vector<Value>;
using Object = std::vector<std::pair<std::string, Value>>;  // keeps the order you build it in

class Value {
public:
    Value() = default;                                   // null
    Value(std::nullptr_t) noexcept {}                    // null
    Value(bool b) noexcept : type_(Type::Boolean), bool_(b) {}
    template <typename T, typename std::enable_if<std::is_arithmetic<T>::value &&
                                                  !std::is_same<T, bool>::value, int>::type = 0>
    Value(T n) noexcept : type_(Type::Number), number_(static_cast<double>(n)) {}
    Value(const char* s) : type_(s != nullptr ? Type::String : Type::Null), string_(s != nullptr ? s : "") {}
    Value(std::string s) noexcept : type_(Type::String), string_(std::move(s)) {}
    Value(Array a) noexcept : type_(Type::Array), array_(std::move(a)) {}
    Value(Object o) noexcept : type_(Type::Object), object_(std::move(o)) {}

    Type type() const noexcept { return type_; }
    bool isNull() const noexcept { return type_ == Type::Null; }
    bool isBool() const noexcept { return type_ == Type::Boolean; }
    bool isNumber() const noexcept { return type_ == Type::Number; }
    bool isString() const noexcept { return type_ == Type::String; }
    bool isArray() const noexcept { return type_ == Type::Array; }
    bool isObject() const noexcept { return type_ == Type::Object; }

    // The value, or `fallback` when it is some other type.
    bool asBool(bool fallback = false) const noexcept { return type_ == Type::Boolean ? bool_ : fallback; }
    double asNumber(double fallback = 0.0) const noexcept { return type_ == Type::Number ? number_ : fallback; }
    long long asInt(long long fallback = 0) const noexcept {
        if (type_ != Type::Number || !std::isfinite(number_) || std::fabs(number_) > 9007199254740992.0)
            return fallback;
        return static_cast<long long>(number_);
    }
    std::string asString(const std::string& fallback = std::string()) const {
        return type_ == Type::String ? string_ : fallback;
    }
    const Array& asArray() const noexcept { return array_; }     // empty unless an array
    const Object& asObject() const noexcept { return object_; }  // empty unless an object
    std::size_t size() const noexcept {
        return type_ == Type::Array ? array_.size() : type_ == Type::Object ? object_.size() : 0;
    }

    // Look inside. A missing key or index gives null, so lookups chain safely:
    // msg["prefs"]["textScale"].asNumber(1.0).
    const Value* find(const std::string& key) const noexcept {
        if (type_ != Type::Object) return nullptr;
        for (const auto& kv : object_)
            if (kv.first == key) return &kv.second;
        return nullptr;
    }
    bool has(const std::string& key) const noexcept { return find(key) != nullptr; }
    const Value& operator[](const std::string& key) const noexcept {
        const Value* v = find(key);
        return v != nullptr ? *v : null();
    }
    const Value& operator[](std::size_t index) const noexcept {
        return type_ == Type::Array && index < array_.size() ? array_[index] : null();
    }

    // Build. set() makes a null value an object (and replaces a key that is already there);
    // push() makes a null value an array. Both return *this, so calls chain.
    Value& set(const std::string& key, Value v) {
        if (type_ != Type::Object) *this = Value(Object());
        for (auto& kv : object_) {
            if (kv.first == key) {
                kv.second = std::move(v);
                return *this;
            }
        }
        object_.emplace_back(key, std::move(v));
        return *this;
    }
    Value& push(Value v) {
        if (type_ != Type::Array) *this = Value(Array());
        array_.push_back(std::move(v));
        return *this;
    }

    // Compact JSON text. Strings that aren't valid UTF-8 are repaired with U+FFFD, and
    // numbers that JSON can't hold (NaN, infinity) become null, so the text is always valid.
    std::string dump() const {
        std::string out;
        write(out);
        return out;
    }

    friend bool operator==(const Value& a, const Value& b) noexcept;
    friend bool operator!=(const Value& a, const Value& b) noexcept { return !(a == b); }

private:
    Type type_ = Type::Null;
    bool bool_ = false;
    double number_ = 0.0;
    std::string string_;
    Array array_;
    Object object_;

    static const Value& null() noexcept {
        static const Value none;
        return none;
    }
    void write(std::string& out) const;
};

namespace detail {

// Locale-independent text to number (a host app may have set a locale with a decimal comma).
inline bool textToNumber(std::string_view text, double& out) {
    std::size_t i = text.size() > 0 && text[0] == '-' ? 1 : 0;
    if (text.size() > i && text.size() - i <= 15 &&
        text.find_first_not_of("0123456789", i) == std::string_view::npos) {
        long long n = 0;  // plain integers (ids, ports, sizes): exact and quick
        for (; i < text.size(); ++i) n = n * 10 + (text[i] - '0');
        out = static_cast<double>(text[0] == '-' ? -n : n);
        return true;
    }
    std::istringstream in{std::string(text)};
    in.imbue(std::locale::classic());
    in >> out;
    return !in.fail();
}

inline void writeNumber(std::string& out, double d) {
    if (!std::isfinite(d)) {
        out += "null";
        return;
    }
    if (d == std::floor(d) && std::fabs(d) < 1e15) {
        out += std::to_string(static_cast<long long>(d));
        return;
    }
    for (int precision = 15; precision <= 17; precision += 2) {  // shortest that reads back the same
        std::ostringstream os;
        os.imbue(std::locale::classic());
        os << std::setprecision(precision) << d;
        const std::string text = os.str();
        double back = 0.0;
        if (precision == 17 || (textToNumber(text, back) && back == d)) {
            out += text;
            return;
        }
    }
}

// Length of the well-formed UTF-8 sequence that starts at s[i] (a byte >= 0x80), or 0.
inline std::size_t utf8Length(const std::string& s, std::size_t i) noexcept {
    const std::size_t n = s.size();
    const auto at = [&](std::size_t k) { return static_cast<unsigned char>(s[k]); };
    const auto cont = [&](std::size_t k) { return k < n && (at(k) & 0xC0) == 0x80; };
    const unsigned char c = at(i);
    if (c >= 0xC2 && c <= 0xDF) return cont(i + 1) ? 2 : 0;
    if (c >= 0xE0 && c <= 0xEF) {
        if (i + 2 >= n) return 0;
        const unsigned char c1 = at(i + 1);
        if ((c == 0xE0 && c1 < 0xA0) || (c == 0xED && c1 > 0x9F)) return 0;  // overlong, surrogate
        return cont(i + 1) && cont(i + 2) ? 3 : 0;
    }
    if (c >= 0xF0 && c <= 0xF4) {
        if (i + 3 >= n) return 0;
        const unsigned char c1 = at(i + 1);
        if ((c == 0xF0 && c1 < 0x90) || (c == 0xF4 && c1 > 0x8F)) return 0;  // overlong, > U+10FFFF
        return cont(i + 1) && cont(i + 2) && cont(i + 3) ? 4 : 0;
    }
    return 0;
}

inline void writeString(std::string& out, const std::string& s) {
    static const char hex[] = "0123456789abcdef";
    out += '"';
    std::size_t i = 0;
    while (i < s.size()) {
        const unsigned char c = static_cast<unsigned char>(s[i]);
        if (c >= 0x80) {
            const std::size_t len = utf8Length(s, i);
            if (len == 0) {
                out += "\xEF\xBF\xBD";  // not UTF-8: U+FFFD keeps the message readable
                ++i;
            } else {
                out.append(s, i, len);
                i += len;
            }
            continue;
        }
        switch (c) {
            case '"': out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\n': out += "\\n"; break;
            case '\r': out += "\\r"; break;
            case '\t': out += "\\t"; break;
            case '\b': out += "\\b"; break;
            case '\f': out += "\\f"; break;
            default:
                if (c < 0x20 || c == 0x7F) {
                    out += "\\u00";
                    out += hex[c >> 4];
                    out += hex[c & 0x0F];
                } else {
                    out += static_cast<char>(c);
                }
        }
        ++i;
    }
    out += '"';
}

inline void appendUtf8(std::string& out, unsigned cp) {
    if (cp < 0x80) {
        out += static_cast<char>(cp);
    } else if (cp < 0x800) {
        out += static_cast<char>(0xC0 | (cp >> 6));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else if (cp < 0x10000) {
        out += static_cast<char>(0xE0 | (cp >> 12));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    } else {
        out += static_cast<char>(0xF0 | (cp >> 18));
        out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F));
        out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F));
        out += static_cast<char>(0x80 | (cp & 0x3F));
    }
}

class Parser {
public:
    explicit Parser(std::string_view text) noexcept : s_(text) {}

    bool parse(Value& out) {
        space();
        if (!value(out, 0)) return false;
        space();
        return pos_ == s_.size() || fail("Unexpected text after the value");
    }
    std::string error;

private:
    static constexpr int kMaxDepth = 200;
    std::string_view s_;
    std::size_t pos_ = 0;

    bool fail(const char* why) {
        if (error.empty()) error = std::string(why) + " at byte " + std::to_string(pos_) + ".";
        return false;
    }
    bool more() const noexcept { return pos_ < s_.size(); }
    char peek() const noexcept { return s_[pos_]; }
    static bool digit(char c) noexcept { return c >= '0' && c <= '9'; }
    void space() noexcept {
        while (more() && (peek() == ' ' || peek() == '\t' || peek() == '\n' || peek() == '\r')) ++pos_;
    }
    bool word(std::string_view w) {
        if (s_.substr(pos_, w.size()) != w) return false;
        pos_ += w.size();
        return true;
    }

    bool value(Value& out, int depth) {
        if (depth > kMaxDepth) return fail("Nested too deeply");
        if (!more()) return fail("Unexpected end");
        switch (peek()) {
            case 'n':
                if (!word("null")) return fail("Expected null");
                out = Value();
                return true;
            case 't':
                if (!word("true")) return fail("Expected true");
                out = Value(true);
                return true;
            case 'f':
                if (!word("false")) return fail("Expected false");
                out = Value(false);
                return true;
            case '"': {
                std::string text;
                if (!readString(text)) return false;
                out = Value(std::move(text));
                return true;
            }
            case '[': return readArray(out, depth);
            case '{': return readObject(out, depth);
            default: return readNumber(out);
        }
    }

    bool readNumber(Value& out) {
        const std::size_t start = pos_;
        if (more() && peek() == '-') ++pos_;
        if (!more() || !digit(peek())) return fail("Unexpected character");
        if (peek() == '0') {
            ++pos_;  // no leading zeros: "01" stops after the 0 and fails as extra text
        } else {
            while (more() && digit(peek())) ++pos_;
        }
        if (more() && peek() == '.') {
            ++pos_;
            if (!more() || !digit(peek())) return fail("Expected a digit");
            while (more() && digit(peek())) ++pos_;
        }
        if (more() && (peek() == 'e' || peek() == 'E')) {
            ++pos_;
            if (more() && (peek() == '+' || peek() == '-')) ++pos_;
            if (!more() || !digit(peek())) return fail("Expected a digit");
            while (more() && digit(peek())) ++pos_;
        }
        double d = 0.0;
        textToNumber(s_.substr(start, pos_ - start), d);  // out of range: the stream's nearest value
        out = Value(d);
        return true;
    }

    bool hex4(unsigned& cp) {
        if (s_.size() - pos_ < 4) return false;
        cp = 0;
        for (int k = 0; k < 4; ++k) {
            const char h = s_[pos_++];
            cp <<= 4;
            if (h >= '0' && h <= '9') cp |= static_cast<unsigned>(h - '0');
            else if (h >= 'a' && h <= 'f') cp |= static_cast<unsigned>(h - 'a' + 10);
            else if (h >= 'A' && h <= 'F') cp |= static_cast<unsigned>(h - 'A' + 10);
            else return false;
        }
        return true;
    }

    bool readString(std::string& out) {
        ++pos_;  // the opening quote
        for (;;) {
            if (!more()) return fail("Unterminated string");
            const char c = s_[pos_++];
            if (c == '"') return true;
            if (static_cast<unsigned char>(c) < 0x20) return fail("Control character in a string");
            if (c != '\\') {
                out += c;
                continue;
            }
            if (!more()) return fail("Unterminated string");
            switch (s_[pos_++]) {
                case '"': out += '"'; break;
                case '\\': out += '\\'; break;
                case '/': out += '/'; break;
                case 'b': out += '\b'; break;
                case 'f': out += '\f'; break;
                case 'n': out += '\n'; break;
                case 'r': out += '\r'; break;
                case 't': out += '\t'; break;
                case 'u': {
                    unsigned cp = 0;
                    if (!hex4(cp)) return fail("Bad \\u escape");
                    if (cp >= 0xD800 && cp <= 0xDBFF) {
                        // A high surrogate joins the low one after it into one character past U+FFFF.
                        const std::size_t save = pos_;
                        unsigned low = 0;
                        bool paired = false;
                        if (s_.substr(pos_, 2) == "\\u") {
                            pos_ += 2;
                            paired = hex4(low) && low >= 0xDC00 && low <= 0xDFFF;
                        }
                        if (paired) {
                            cp = 0x10000 + ((cp - 0xD800) << 10) + (low - 0xDC00);
                        } else {
                            pos_ = save;  // a lone high surrogate: read whatever follows on its own
                            cp = 0xFFFD;
                        }
                    } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                        cp = 0xFFFD;  // a low surrogate alone
                    }
                    appendUtf8(out, cp);
                    break;
                }
                default: return fail("Bad escape");
            }
        }
    }

    bool readArray(Value& out, int depth) {
        ++pos_;
        Array items;
        space();
        if (more() && peek() == ']') {
            ++pos_;
            out = Value(std::move(items));
            return true;
        }
        for (;;) {
            space();
            Value item;
            if (!value(item, depth + 1)) return false;
            items.push_back(std::move(item));
            space();
            if (!more()) return fail("Unterminated array");
            if (peek() == ']') break;
            if (peek() != ',') return fail("Expected , or ]");
            ++pos_;
        }
        ++pos_;
        out = Value(std::move(items));
        return true;
    }

    bool readObject(Value& out, int depth) {
        ++pos_;
        Value obj{Object()};
        space();
        if (more() && peek() == '}') {
            ++pos_;
            out = std::move(obj);
            return true;
        }
        for (;;) {
            space();
            if (!more() || peek() != '"') return fail("Expected a key");
            std::string key;
            if (!readString(key)) return false;
            space();
            if (!more() || peek() != ':') return fail("Expected :");
            ++pos_;
            space();
            Value item;
            if (!value(item, depth + 1)) return false;
            obj.set(key, std::move(item));  // a repeated key: the last one wins, as in Python
            space();
            if (!more()) return fail("Unterminated object");
            if (peek() == '}') break;
            if (peek() != ',') return fail("Expected , or }");
            ++pos_;
        }
        ++pos_;
        out = std::move(obj);
        return true;
    }
};

}  // namespace detail

inline void Value::write(std::string& out) const {
    switch (type_) {
        case Type::Null: out += "null"; break;
        case Type::Boolean: out += bool_ ? "true" : "false"; break;
        case Type::Number: detail::writeNumber(out, number_); break;
        case Type::String: detail::writeString(out, string_); break;
        case Type::Array: {
            out += '[';
            for (std::size_t i = 0; i < array_.size(); ++i) {
                if (i > 0) out += ',';
                array_[i].write(out);
            }
            out += ']';
            break;
        }
        case Type::Object: {
            out += '{';
            for (std::size_t i = 0; i < object_.size(); ++i) {
                if (i > 0) out += ',';
                detail::writeString(out, object_[i].first);
                out += ':';
                object_[i].second.write(out);
            }
            out += '}';
            break;
        }
    }
}

inline bool operator==(const Value& a, const Value& b) noexcept {
    if (a.type_ != b.type_) return false;
    switch (a.type_) {
        case Type::Null: return true;
        case Type::Boolean: return a.bool_ == b.bool_;
        case Type::Number: return a.number_ == b.number_;
        case Type::String: return a.string_ == b.string_;
        case Type::Array: return a.array_ == b.array_;
        case Type::Object: {  // the same keys and values, in any order
            if (a.object_.size() != b.object_.size()) return false;
            for (const auto& kv : a.object_) {
                const Value* other = b.find(kv.first);
                if (other == nullptr || !(*other == kv.second)) return false;
            }
            return true;
        }
    }
    return false;
}

// Read JSON text. Nothing when it isn't valid JSON (and `error`, if given, says why).
inline std::optional<Value> parse(std::string_view text, std::string* error = nullptr) {
    detail::Parser parser(text);
    Value v;
    if (parser.parse(v)) return v;
    if (error != nullptr) *error = parser.error;
    return std::nullopt;
}

}  // namespace json

// ==================================================================================== Link

// What a handler answers. `return {true, "Next preset"};`, `return true;`,
// `return "Tuner on";` (done, with a message) or `return {false, "The tuner is busy."};`.
struct Result {
    bool ok = true;
    std::string message;  // what a person hears; a refusal always says why

    Result(bool succeeded = true, std::string text = std::string()) : ok(succeeded), message(std::move(text)) {}
    Result(const char* text) : ok(true), message(text != nullptr ? text : "") {}
    Result(std::string text) : ok(true), message(std::move(text)) {}
};

// Something a musician can reach for. Across the suite it is called "<tool>.<id>".
struct Action {
    std::string id;                    // short: letters and digits, e.g. "nextPreset"
    std::string label;                 // what a person sees and hears, 60 characters at most
    std::string intent;                // optional shared intent, e.g. "daw.record"
    std::vector<std::string> phrases;  // optional extra ways to say it, for Limitless Voice
    json::Value args;                  // optional argument names and types, e.g. {"name": "text"}

    Action(std::string actionId, std::string actionLabel, std::string sharedIntent = std::string(),
           std::vector<std::string> sayings = std::vector<std::string>())
        : id(std::move(actionId)), label(std::move(actionLabel)), intent(std::move(sharedIntent)),
          phrases(std::move(sayings)) {}

    json::Value toJson() const {
        json::Value v = json::Object{{"id", id}, {"label", label.empty() ? id : label}};
        if (!intent.empty()) v.set("intent", intent);
        if (!phrases.empty()) {
            json::Array list;
            for (const auto& p : phrases) list.push_back(p);
            v.set("phrases", std::move(list));
        }
        if (args.isObject() && args.size() > 0) v.set("args", args);
        return v;
    }
};

using InvokeHandler = std::function<Result(const std::string& action, const json::Value& args, const std::string& source)>;
using EventHandler = std::function<void(const std::string& name, const json::Value& value, const std::string& source)>;
using PrefsHandler = std::function<void(const json::Value& prefs)>;
using ActionsHandler = std::function<void(const json::Value& suiteActions)>;
using ConnectedHandler = std::function<void(bool connected)>;
using ResultHandler = std::function<void(const Result& result)>;
using Dispatcher = std::function<void(std::function<void()> job)>;

namespace detail {

#ifdef _WIN32
using Socket = SOCKET;
inline constexpr Socket kNoSocket = INVALID_SOCKET;
inline void closeSocket(Socket s) noexcept { ::closesocket(s); }
inline void shutdownSocket(Socket s) noexcept { ::shutdown(s, SD_BOTH); }
#else
using Socket = int;
inline constexpr Socket kNoSocket = -1;
inline void closeSocket(Socket s) noexcept { ::close(s); }
inline void shutdownSocket(Socket s) noexcept { ::shutdown(s, SHUT_RDWR); }
#endif

// 1 when the socket is ready, 0 on timeout, -1 on error.
inline int waitFor(Socket s, bool forWriting, int ms) noexcept {
#ifdef _WIN32
    fd_set ready, failed;
    FD_ZERO(&ready);
    FD_ZERO(&failed);
    FD_SET(s, &ready);
    FD_SET(s, &failed);  // Windows reports a failed connect here
    timeval tv;
    tv.tv_sec = ms / 1000;
    tv.tv_usec = (ms % 1000) * 1000;
    const int r = ::select(0, forWriting ? nullptr : &ready, forWriting ? &ready : nullptr,
                           forWriting ? &failed : nullptr, &tv);
    if (r == SOCKET_ERROR) return -1;
    if (r == 0) return 0;
    return forWriting && FD_ISSET(s, &failed) ? -1 : 1;
#else
    pollfd p;  // poll, not select: a busy host can have descriptors past FD_SETSIZE
    p.fd = s;
    p.events = static_cast<short>(forWriting ? POLLOUT : POLLIN);
    p.revents = 0;
    const int r = ::poll(&p, 1, ms);
    if (r < 0) return errno == EINTR ? 0 : -1;
    return r == 0 ? 0 : 1;
#endif
}

// Connect to 127.0.0.1:port within two seconds, or give up. Never blocks past `stopping`.
inline Socket connectLocal(unsigned short port, const std::atomic<bool>& stopping) {
#ifdef _WIN32
    Socket s = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
    if (s == kNoSocket) return kNoSocket;
    ::SetHandleInformation(reinterpret_cast<HANDLE>(s), HANDLE_FLAG_INHERIT, 0);
    u_long nonBlocking = 1;
    ::ioctlsocket(s, static_cast<long>(FIONBIO), &nonBlocking);
#else
    Socket s = ::socket(AF_INET, SOCK_STREAM, 0);
    if (s < 0) return kNoSocket;
    ::fcntl(s, F_SETFD, FD_CLOEXEC);  // never leak into programs the host starts
    const int flags = ::fcntl(s, F_GETFL, 0);
    ::fcntl(s, F_SETFL, flags | O_NONBLOCK);
#ifdef SO_NOSIGPIPE
    int noSigpipe = 1;  // Apple: a closed hub must not kill the host with SIGPIPE
    ::setsockopt(s, SOL_SOCKET, SO_NOSIGPIPE, &noSigpipe, sizeof noSigpipe);
#endif
#endif
    sockaddr_in addr;
    std::memset(&addr, 0, sizeof addr);
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    addr.sin_addr.s_addr = htonl(INADDR_LOOPBACK);
    if (::connect(s, reinterpret_cast<const sockaddr*>(&addr), sizeof addr) != 0) {
#ifdef _WIN32
        const bool pending = ::WSAGetLastError() == WSAEWOULDBLOCK;
#else
        const bool pending = errno == EINPROGRESS || errno == EINTR;
#endif
        int ready = pending ? 0 : -1;
        for (int waited = 0; ready == 0 && waited < 2000 && !stopping.load(); waited += 100)
            ready = waitFor(s, true, 100);
        int err = 0;
        socklen_t len = sizeof err;
        if (ready != 1 || ::getsockopt(s, SOL_SOCKET, SO_ERROR, reinterpret_cast<char*>(&err), &len) != 0 || err != 0) {
            closeSocket(s);
            return kNoSocket;
        }
    }
#ifdef _WIN32
    nonBlocking = 0;
    ::ioctlsocket(s, static_cast<long>(FIONBIO), &nonBlocking);
    DWORD sendTimeoutMs = 3000;
    ::setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, reinterpret_cast<const char*>(&sendTimeoutMs), sizeof sendTimeoutMs);
#else
    ::fcntl(s, F_SETFL, flags);
    timeval sendTimeout;
    sendTimeout.tv_sec = 3;
    sendTimeout.tv_usec = 0;
    ::setsockopt(s, SOL_SOCKET, SO_SNDTIMEO, &sendTimeout, sizeof sendTimeout);
#endif
    int noDelay = 1;
    ::setsockopt(s, IPPROTO_TCP, TCP_NODELAY, reinterpret_cast<const char*>(&noDelay), sizeof noDelay);
    return s;
}

inline bool sendAll(Socket s, const char* data, std::size_t size) noexcept {
    while (size > 0) {
#ifdef _WIN32
        const int sent = ::send(s, data, static_cast<int>(size), 0);
        if (sent <= 0) return false;  // SOCKET_ERROR, or the send timeout
#else
#ifdef MSG_NOSIGNAL
        const ssize_t sent = ::send(s, data, size, MSG_NOSIGNAL);
#else
        const ssize_t sent = ::send(s, data, size, 0);
#endif
        if (sent < 0 && errno == EINTR) continue;
        if (sent <= 0) return false;
#endif
        data += sent;
        size -= static_cast<std::size_t>(sent);
    }
    return true;
}

// Bytes read, 0 when the other side closed, negative on error.
inline long receiveSome(Socket s, char* buf, std::size_t size) noexcept {
#ifdef _WIN32
    return ::recv(s, buf, static_cast<int>(size), 0);
#else
    for (;;) {
        const ssize_t got = ::recv(s, buf, size, 0);
        if (got < 0 && errno == EINTR) continue;
        return static_cast<long>(got);
    }
#endif
}

#ifdef _WIN32
inline std::wstring environment(const wchar_t* name) {
    const DWORD size = ::GetEnvironmentVariableW(name, nullptr, 0);
    if (size == 0) return std::wstring();
    std::wstring value(size, L'\0');
    const DWORD got = ::GetEnvironmentVariableW(name, &value[0], size);
    value.resize(got < size ? got : 0);
    return value;
}

inline std::wstring wideConfigDir() {
    const std::wstring override = environment(L"LIMITLESS_SOUND_HOME");
    if (!override.empty()) return override;
    std::wstring appData = environment(L"APPDATA");
    if (appData.empty()) appData = environment(L"USERPROFILE") + L"\\AppData\\Roaming";
    return appData + L"\\Limitless Sound";
}

inline std::string toUtf8(const std::wstring& w) {
    if (w.empty()) return std::string();
    const int n = ::WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), nullptr, 0, nullptr, nullptr);
    if (n <= 0) return std::string();
    std::string s(static_cast<std::size_t>(n), '\0');
    ::WideCharToMultiByte(CP_UTF8, 0, w.data(), static_cast<int>(w.size()), &s[0], n, nullptr, nullptr);
    return s;
}

inline bool readLinkText(std::string& out) {
    const std::wstring path = wideConfigDir() + L"\\link.json";
    HANDLE file = ::CreateFileW(path.c_str(), GENERIC_READ, FILE_SHARE_READ | FILE_SHARE_WRITE | FILE_SHARE_DELETE,
                                nullptr, OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, nullptr);
    if (file == INVALID_HANDLE_VALUE) return false;
    char buf[4096];
    DWORD got = 0;
    while (out.size() < kMaxLine && ::ReadFile(file, buf, sizeof buf, &got, nullptr) && got > 0) out.append(buf, got);
    ::CloseHandle(file);
    return !out.empty();
}
#else
inline std::string homeDir() {
    const char* home = std::getenv("HOME");
    if (home != nullptr && *home != '\0') return home;
    std::vector<char> buf(16384);
    passwd pw;
    passwd* found = nullptr;
    if (::getpwuid_r(::getuid(), &pw, buf.data(), buf.size(), &found) == 0 && found != nullptr && found->pw_dir != nullptr)
        return found->pw_dir;
    return std::string();
}
#endif

}  // namespace detail

// The suite's shared folder, where the hub writes link.json (UTF-8).
inline std::string configDir() {
#ifdef _WIN32
    return detail::toUtf8(detail::wideConfigDir());
#else
    const char* override = std::getenv("LIMITLESS_SOUND_HOME");
    if (override != nullptr && *override != '\0') return override;
#ifdef __APPLE__
    return detail::homeDir() + "/Library/Application Support/Limitless Sound";
#else
    const char* xdg = std::getenv("XDG_CONFIG_HOME");
    return (xdg != nullptr && *xdg != '\0' ? std::string(xdg) : detail::homeDir() + "/.config") + "/Limitless Sound";
#endif
#endif
}

namespace detail {

#ifndef _WIN32
inline bool readLinkText(std::string& out) {
    std::ifstream file(configDir() + "/link.json", std::ios::binary);
    if (!file) return false;
    char buf[4096];
    while (out.size() < kMaxLine && file.read(buf, sizeof buf).gcount() > 0) out.append(buf, static_cast<std::size_t>(file.gcount()));
    return !out.empty();
}
#endif

// Splits what arrives into lines, and skips any line longer than kMaxLine whole.
class LineReader {
public:
    explicit LineReader(std::size_t maxLine = kMaxLine) noexcept : max_(maxLine) {}

    template <typename OnLine>
    void feed(const char* data, std::size_t size, OnLine&& onLine) {
        std::size_t i = 0;
        while (i < size) {
            const void* hit = std::memchr(data + i, '\n', size - i);
            const std::size_t end = hit != nullptr ? static_cast<std::size_t>(static_cast<const char*>(hit) - data) : size;
            if (!skipping_) {
                if (buf_.size() + (end - i) + 1 > max_) {  // + 1: the newline, now or still to come
                    skipping_ = true;
                    std::string().swap(buf_);
                } else {
                    buf_.append(data + i, end - i);
                }
            }
            if (hit == nullptr) break;
            if (!skipping_) {
                std::string line;
                line.swap(buf_);
                if (!line.empty() && line.back() == '\r') line.pop_back();
                onLine(line);
            }
            skipping_ = false;
            i = end + 1;
        }
    }

private:
    std::size_t max_;
    std::string buf_;
    bool skipping_ = false;
};

// Which link's request this thread is answering, and how many sidechain steps led to it.
inline std::pair<const void*, long long>& depthSlot() noexcept {
    static thread_local std::pair<const void*, long long> slot{nullptr, 0};
    return slot;
}

inline json::Value stateMessage(const std::string& key, const json::Value& value, long long depth) {
    return json::Object{{"op", "state"}, {"key", key}, {"value", value}, {"depth", depth}};
}

// Everything the link thread shares with the Link and with jobs handed to a dispatcher.
// Jobs keep it alive, so a job that runs after the Link is gone does nothing, safely.
class Core : public std::enable_shared_from_this<Core> {
public:
    Core(std::string toolId, std::string displayName, std::string ver, std::vector<Action> acts)
        : tool(std::move(toolId)), name(std::move(displayName)), version(std::move(ver)), actions(std::move(acts)) {
#ifdef _WIN32
        WSADATA data;
        winsockReady = ::WSAStartup(MAKEWORD(2, 2), &data) == 0;
#endif
    }
    ~Core() {
#ifdef _WIN32
        if (winsockReady) ::WSACleanup();
#endif
    }
    Core(const Core&) = delete;
    Core& operator=(const Core&) = delete;

    const std::string tool, name, version;

    mutable std::mutex mu;  // guards everything from here to `waiting`
    std::vector<Action> actions;
    std::vector<std::string> subscribe{"*"};
    std::chrono::milliseconds retry{2000};
    InvokeHandler onInvoke;
    EventHandler onEvent;
    PrefsHandler onPrefs;
    ActionsHandler onActions;
    ConnectedHandler onConnected;
    Dispatcher dispatch;
    json::Value prefs{json::Object()};
    std::map<long long, ResultHandler> waiting;

    std::mutex statesMu;  // taken before sockMu, never after
    json::Value states{json::Object()};  // the last value of each state, told again on reconnect

    std::mutex sockMu;
    Socket sock = kNoSocket;

    std::mutex wakeMu;
    std::condition_variable wake;
    std::atomic<bool> connected{false};
    std::atomic<bool> stopping{false};  // the thread should finish
    std::atomic<bool> closed{false};    // stop() was called: no more handlers
    std::atomic<bool> replaced{false};  // a newer copy took over: never come back by ourselves
    std::atomic<unsigned> generation{0};  // one per stop(): jobs from before it never run
    std::atomic<long long> nextId{1};
#ifdef _WIN32
    bool winsockReady = false;
#endif

    template <typename Handler>
    Handler get(const Handler& h) const {
        std::lock_guard<std::mutex> lock(mu);
        return h;
    }

    long long depth() const noexcept {
        const auto& slot = depthSlot();
        return slot.first == this ? slot.second : 0;
    }

    // One line to the hub. Before `welcome` only hello may go.
    bool send(const json::Value& msg, bool beforeWelcome = false) {
        if (!beforeWelcome && !connected.load()) return false;
        std::string line = msg.dump();
        line += '\n';
        if (line.size() > kMaxLine) return false;  // the hub would hang up on it
        std::lock_guard<std::mutex> lock(sockMu);
        if (sock == kNoSocket) return false;
        if (sendAll(sock, line.data(), line.size())) return true;
        shutdownSocket(sock);  // the reader notices, closes it and tries again later
        connected = false;
        return false;
    }

    // Run a handler: on this thread, or through the dispatcher. Never after stop().
    void post(std::function<void()> job) {
        if (closed.load()) return;
        Dispatcher d = get(dispatch);
        std::shared_ptr<Core> self = shared_from_this();
        const unsigned gen = generation.load();
        std::function<void()> guarded = [self, job, gen]() {
            if (self->closed.load() || self->generation.load() != gen) return;
            try {
                job();
            } catch (...) {  // a mistake in a handler never takes the product down
            }
        };
        if (!d) {
            guarded();
            return;
        }
        try {
            d(std::move(guarded));
        } catch (...) {
        }
    }

    void closeDown() {
        closed = true;
        ++generation;
        {
            std::lock_guard<std::mutex> lock(wakeMu);
            stopping = true;
        }
        wake.notify_all();
        {
            std::lock_guard<std::mutex> lock(sockMu);
            if (sock != kNoSocket) shutdownSocket(sock);
        }
        connected = false;
    }

    void run() {
        try {
            while (!stopping.load()) {
                std::string text;
                if (readLinkText(text)) {
                    const std::optional<json::Value> info = json::parse(text);
                    if (info && info->isObject()) {
                        const double port = (*info)["port"].asNumber(0);
                        const std::string token = (*info)["token"].asString();
                        if (port >= 1 && port <= 65535 && !token.empty())
                            session(static_cast<unsigned short>(port), token);
                    }
                }
                const std::chrono::milliseconds pause = get(retry);
                std::unique_lock<std::mutex> lock(wakeMu);
                wake.wait_for(lock, pause, [this] { return stopping.load(); });
            }
        } catch (...) {  // out of memory or threads: the product carries on without the suite
        }
    }

    json::Value hello(const std::string& token) const {
        std::lock_guard<std::mutex> lock(mu);
        json::Array list;
        for (const auto& a : actions) list.push_back(a.toJson());
        json::Array patterns;
        for (const auto& p : subscribe) patterns.push_back(p);
        return json::Object{{"op", "hello"}, {"protocol", kProtocol}, {"token", token}, {"tool", tool},
                            {"name", name}, {"version", version}, {"actions", std::move(list)},
                            {"subscribe", std::move(patterns)}};
    }

    void session(unsigned short port, const std::string& token) {
        const Socket s = connectLocal(port, stopping);
        if (s == kNoSocket) return;
        {
            std::lock_guard<std::mutex> lock(sockMu);
            if (stopping.load()) {
                closeSocket(s);
                return;
            }
            sock = s;
        }
        bool welcomed = false;
        try {
            send(hello(token), true);
            LineReader reader;
            std::vector<char> buf(65536);
            bool going = true;
            while (going && !stopping.load()) {
                const int ready = waitFor(s, false, 200);
                if (ready < 0) break;
                if (ready == 0) continue;
                const long got = receiveSome(s, buf.data(), buf.size());
                if (got <= 0) break;
                reader.feed(buf.data(), static_cast<std::size_t>(got), [&](const std::string& line) {
                    if (!going) return;
                    const std::optional<json::Value> msg = json::parse(line);
                    if (msg && msg->isObject()) going = handle(*msg, welcomed);
                });
            }
        } catch (...) {
        }
        {
            std::lock_guard<std::mutex> lock(sockMu);
            sock = kNoSocket;
        }
        shutdownSocket(s);
        closeSocket(s);
        connected = false;
        finishWaiting("Lost the connection to Limitless Sound.");
        if (welcomed) post([this] { if (auto h = get(onConnected)) h(false); });
    }

    // One message from the hub. False ends the connection.
    bool handle(const json::Value& msg, bool& welcomed) {
        const std::string op = msg["op"].asString();
        if (op == "welcome" || op == "prefs") {
            const json::Value p = msg["prefs"].isObject() ? msg["prefs"] : json::Value(json::Object());
            {
                std::lock_guard<std::mutex> lock(mu);
                prefs = p;
            }
            if (op == "welcome") {
                {
                    std::lock_guard<std::mutex> lock(statesMu);
                    connected = true;
                    for (const auto& kv : states.asObject()) send(stateMessage(kv.first, kv.second, 0));
                }
                welcomed = true;
                post([this] { if (auto h = get(onConnected)) h(true); });
            }
            post([this, p] { if (auto h = get(onPrefs)) h(p); });
            if (op == "welcome") {
                const json::Value acts = msg["actions"];
                post([this, acts] { if (auto h = get(onActions)) h(acts); });
            }
        } else if (op == "invoke") {
            const json::Value request = msg;
            post([this, request] { answer(request); });
        } else if (op == "event") {
            const std::string evName = msg["name"].asString();
            const std::string evSource = msg["source"].asString();
            const json::Value evValue = msg["value"];
            post([this, evName, evValue, evSource] { if (auto h = get(onEvent)) h(evName, evValue, evSource); });
        } else if (op == "actions") {
            const json::Value acts = msg["actions"];
            post([this, acts] { if (auto h = get(onActions)) h(acts); });
        } else if (op == "result") {
            ResultHandler cb;
            {
                std::lock_guard<std::mutex> lock(mu);
                const auto it = waiting.find(msg["id"].asInt(-1));
                if (it != waiting.end()) {
                    cb = std::move(it->second);
                    waiting.erase(it);
                }
            }
            if (cb) {
                const Result r(msg["ok"].asBool(false), msg["message"].asString());
                post([cb, r] { cb(r); });
            }
        } else if (op == "error") {
            if (msg["code"].asString() == "replaced") {
                // A newer copy of this product took over: step aside for good instead of fighting it.
                replaced = true;
                stopping = true;
                return false;
            }
            if (!welcomed) return false;  // refused (wrong token, bad tool id): try again later
        }
        return true;
    }

    // Do one of this product's actions for the hub, and answer within its 3 seconds.
    void answer(const json::Value& request) {
        Result result(false, name + " takes no actions.");
        if (InvokeHandler h = get(onInvoke)) {
            static const json::Value noArgs{json::Object()};
            auto& slot = depthSlot();
            const auto saved = slot;
            slot = {this, request["depth"].asInt(0)};  // a did() or state() from the handler carries it
            try {
                const json::Value& args = request["args"];
                result = h(request["action"].asString(), args.isObject() ? args : noArgs, request["source"].asString());
            } catch (const std::exception& e) {
                const char* why = e.what();
                result = Result(false, why != nullptr && *why != '\0' ? std::string(why) : name + " couldn't do that.");
            } catch (...) {
                result = Result(false, name + " couldn't do that.");
            }
            slot = saved;
        }
        send(json::Object{{"op", "result"}, {"id", request["id"]}, {"ok", result.ok}, {"message", result.message}});
    }

    void finishWaiting(const std::string& why) {
        std::map<long long, ResultHandler> left;
        {
            std::lock_guard<std::mutex> lock(mu);
            left.swap(waiting);
        }
        for (auto& kv : left) {
            ResultHandler cb = std::move(kv.second);
            post([cb, why] { cb(Result(false, why)); });
        }
    }
};

}  // namespace detail

class Link {
public:
    // `tool` is a short lowercase id that stays the same in every version ("myamp").
    Link(std::string tool, std::string name, std::string version = std::string(),
         std::vector<Action> actions = std::vector<Action>())
        : core_(std::make_shared<detail::Core>(std::move(tool), std::move(name), std::move(version), std::move(actions))) {}

    // Stops and waits for the link's thread (at most a fraction of a second).
    ~Link() {
        stop();
        std::lock_guard<std::mutex> lock(threadMu_);
        if (thread_.joinable()) thread_.detach();  // only when a handler destroyed its own Link
    }
    Link(const Link&) = delete;
    Link& operator=(const Link&) = delete;

    // ------------------------------------------------------------------------- handlers
    // Set them any time, usually before start().

    // Do one of your actions: (action id, args, who asked) -> Result. Answer within 3 seconds.
    void onInvoke(InvokeHandler h) { set(core_->onInvoke, std::move(h)); }
    // Something happened in the suite: ("zoom.in", value, "zoom"). Never your own events.
    void onEvent(EventHandler h) { set(core_->onEvent, std::move(h)); }
    // The musician's shared settings, on joining and on every change. Apply what you support,
    // then report it: state("prefs.applied", {"textScale": 1.5, ...}).
    void onPrefs(PrefsHandler h) { set(core_->onPrefs, std::move(h)); }
    // The suite's whole action list changed (an app opened or closed).
    void onActions(ActionsHandler h) { set(core_->onActions, std::move(h)); }
    // Joined (true) or lost (false) the hub.
    void onConnected(ConnectedHandler h) { set(core_->onConnected, std::move(h)); }
    // Where handlers run, e.g. [](auto job) { juce::MessageManager::callAsync(std::move(job)); }.
    void setDispatch(Dispatcher d) { set(core_->dispatch, std::move(d)); }
    // Which events to hear, as patterns ("daw.*"). Default: everything. Applies on (re)connect.
    void setSubscribe(std::vector<std::string> patterns) { set(core_->subscribe, std::move(patterns)); }
    // How long to wait between tries while the hub isn't there. Default: 2 seconds.
    void setRetryInterval(std::chrono::milliseconds interval) { set(core_->retry, interval); }

    // ------------------------------------------------------------------------- lifecycle

    // Start the link's thread. Returns at once. Does nothing once a newer copy took over.
    void start() {
        std::lock_guard<std::mutex> lock(threadMu_);
        if (core_->replaced.load()) return;
        if (thread_.joinable()) {
            if (!core_->stopping.load() || thread_.get_id() == std::this_thread::get_id()) return;
            thread_.join();  // stopped earlier from one of its own handlers
        }
        core_->closed = false;
        core_->stopping = false;
        std::shared_ptr<detail::Core> core = core_;
        try {
            thread_ = std::thread([core] { core->run(); });
        } catch (...) {  // no thread to be had: carry on without the suite
        }
    }

    // Disconnect and stop trying. No handler runs after this returns. start() again to resume.
    void stop() {
        std::thread finished;
        {
            std::lock_guard<std::mutex> lock(threadMu_);
            core_->closeDown();
            if (thread_.joinable() && thread_.get_id() != std::this_thread::get_id()) finished = std::move(thread_);
        }
        if (finished.joinable()) finished.join();
    }

    bool connected() const noexcept { return core_->connected.load(); }
    // The latest shared settings (an empty object until the hub sends them).
    json::Value prefs() const { return core_->get(core_->prefs); }
    const std::string& tool() const noexcept { return core_->tool; }

    // ------------------------------------------------------------------------- telling the suite
    // Each returns true when the message went to the hub, false when there is no hub.

    // "I just did this", whatever input caused it: a click, a MIDI note, the hub.
    bool did(const std::string& action, const std::string& intent = std::string(), const json::Value& value = json::Value()) {
        json::Value m = json::Object{{"op", "did"}, {"action", action}, {"depth", core_->depth()}};
        if (!intent.empty()) m.set("intent", intent);
        if (!value.isNull()) m.set("value", value);
        return core_->send(m);
    }

    // A state changed ("tuner", true). Remembered, so the hub hears it again after reconnecting,
    // and hears it on connecting when you set it before then.
    bool state(const std::string& key, const json::Value& value) {
        std::lock_guard<std::mutex> lock(core_->statesMu);
        core_->states.set(key, value);
        return core_->connected.load() && core_->send(detail::stateMessage(key, value, core_->depth()));
    }

    // Speak through the suite's one voice. False means speak for yourself, as you always did:
    // no hub, or the musician turned the one voice off.
    bool say(const std::string& text) {
        if (!core_->connected.load()) return false;
        const bool oneVoice = core_->get(core_->prefs)["oneVoice"].asBool(true);
        return oneVoice && core_->send(json::Object{{"op", "say"}, {"text", text}});
    }

    // Ask the suite to do something: "zoom.in", "daw.record", "hub.say" with {"text": ...}.
    // `onResult` gets exactly one answer: the hub's, or a refusal saying the suite isn't there.
    bool invoke(const std::string& action, const json::Value& args = json::Value(json::Object()),
                ResultHandler onResult = nullptr) {
        const long long id = core_->nextId++;
        if (onResult) {
            std::lock_guard<std::mutex> lock(core_->mu);
            core_->waiting[id] = onResult;
        }
        const json::Value m = json::Object{{"op", "invoke"}, {"id", id}, {"action", action},
                                           {"args", args.isObject() ? args : json::Value(json::Object())},
                                           {"depth", core_->depth()}};
        if (core_->send(m)) return true;
        if (onResult) {
            bool mine = false;
            {
                std::lock_guard<std::mutex> lock(core_->mu);
                mine = core_->waiting.erase(id) > 0;
            }
            if (mine) core_->post([onResult] { onResult(Result(false, "Limitless Sound isn't running.")); });
        }
        return false;
    }

    // Replace this product's action list (for example when a different model is loaded).
    bool setActions(std::vector<Action> actions) {
        json::Array list;
        {
            std::lock_guard<std::mutex> lock(core_->mu);
            core_->actions = std::move(actions);
            for (const auto& a : core_->actions) list.push_back(a.toJson());
        }
        return core_->send(json::Object{{"op", "actions"}, {"actions", std::move(list)}});
    }

private:
    std::shared_ptr<detail::Core> core_;
    std::mutex threadMu_;
    std::thread thread_;

    template <typename T>
    void set(T& field, T value) {
        std::lock_guard<std::mutex> lock(core_->mu);
        field = std::move(value);
    }
};

}  // namespace limitless
