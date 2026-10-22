// The JSON value, parser and serializer inside limitless_link.hpp.
// Build and run: c++ -std=c++17 -Wall -Wextra -pthread -o json_test json_test.cpp && ./json_test
// (Windows: add -lws2_32.) Also run by shared/hub/tests/test_clients.py.
#undef NDEBUG
#include "../limitless_link.hpp"

#include <cassert>
#include <clocale>
#include <cmath>
#include <cstdio>
#include <limits>
#include <locale>
#include <string>

namespace json = limitless::json;

static json::Value P(const std::string& text) {
    std::string why;
    const auto v = json::parse(text, &why);
    if (!v) std::fprintf(stderr, "did not parse: %s (%s)\n", text.c_str(), why.c_str());
    assert(v.has_value());
    return *v;
}

static bool bad(const std::string& text) {
    std::string why;
    const bool refused = !json::parse(text, &why).has_value();
    assert(!refused || !why.empty());  // a refusal says why
    return refused;
}

static void scalars() {
    assert(P("null").isNull());
    assert(P("true").isBool() && P("true").asBool());
    assert(P("false").isBool() && !P("false").asBool(true));
    assert(P("0").asNumber() == 0.0);
    assert(P("-12").asNumber() == -12.0);
    assert(P("1.5").asNumber() == 1.5);
    assert(P("-0.25e2").asNumber() == -25.0);
    assert(P("1E3").asNumber() == 1000.0);
    assert(P("2.5e-3").asNumber() == 0.0025);
    assert(P("1e+2").asNumber() == 100.0);
    assert(P(" 47900 ").asInt() == 47900);
    assert(P("9007199254740993").asNumber() == 9007199254740992.0);  // past 2^53, as JSON readers do
    assert(P("12.9").asInt() == 12);
    assert(P("1e300").asInt(-1) == -1);  // too big for an integer: the fallback
}

static void strings() {
    assert(P(R"("a\"b\\c\/d")").asString() == "a\"b\\c/d");
    assert(P(R"("\b\f\n\r\t")").asString() == "\b\f\n\r\t");
    assert(P(R"("\u0041\u00e9\u20AC")").asString() == "A\xC3\xA9\xE2\x82\xAC");          // A, e-acute, euro
    assert(P(R"("\uD83C\uDFB8")").asString() == "\xF0\x9F\x8E\xB8");                       // a guitar, U+1F3B8
    assert(P(R"("\ud83c\udfb8!")").asString() == "\xF0\x9F\x8E\xB8!");
    assert(P(R"("\uD800x")").asString() == "\xEF\xBF\xBDx");                               // lone high surrogate
    assert(P(R"("\uDC00")").asString() == "\xEF\xBF\xBD");                                 // lone low surrogate
    assert(P(R"("\uD800\u0041")").asString() == "\xEF\xBF\xBD" "A");                       // high, then not a low
    assert(P(R"("\uD800\uD800\uDC00")").asString() == "\xEF\xBF\xBD\xF0\x90\x80\x80");      // high, then a pair
    assert(P(R"("\u0000")").asString() == std::string(1, '\0'));
    assert(P("\"caf\xC3\xA9\"").asString() == "caf\xC3\xA9");                              // raw UTF-8 passes through
    assert(P(R"("")").asString().empty() && P(R"("")").isString());
}

static void containers() {
    const json::Value v = P(R"({"op":"welcome","prefs":{"textScale":1.5,"highContrast":true},)"
                            R"("tools":["zoom","color"],"empty":{},"none":[]})");
    assert(v.isObject() && v.size() == 5);
    assert(v["op"].asString() == "welcome");
    assert(v["prefs"]["textScale"].asNumber() == 1.5);
    assert(v["prefs"]["highContrast"].asBool());
    assert(v["tools"].isArray() && v["tools"].size() == 2 && v["tools"][1].asString() == "color");
    assert(v["missing"].isNull() && v["missing"]["deeper"][3].isNull());  // lookups chain safely
    assert(v["tools"][5].isNull() && v["op"]["x"].isNull() && v["op"][0].isNull());
    assert(v["empty"].isObject() && v["empty"].size() == 0);
    assert(v["none"].isArray() && v["none"].size() == 0);
    assert(v.has("op") && !v.has("nope") && v.find("nope") == nullptr);
    assert(v.asObject()[0].first == "op" && v.asObject()[2].first == "tools");  // order kept
    assert(v["tools"].asArray().size() == 2 && v["op"].asArray().empty());

    const json::Value dup = P(R"({"a":1,"a":2})");  // the last one wins, as in Python
    assert(dup.size() == 1 && dup["a"].asNumber() == 2.0);

    assert(P(" \t\r\n{ \"a\" : [ 1 , 2 ] } \n")["a"][1].asNumber() == 2.0);

    std::string deep;
    for (int i = 0; i < 150; ++i) deep += '[';
    for (int i = 0; i < 150; ++i) deep += ']';
    assert(json::parse(deep).has_value());
    std::string tooDeep;
    for (int i = 0; i < 5000; ++i) tooDeep += "[{\"a\":";  // refused, not a stack overflow
    assert(bad(tooDeep));
}

static void errors() {
    const char* cases[] = {
        "", " ", "nul", "tru", "fals", "nulls", "[1,]", "{\"a\":1,}", "[1 2]", "{a:1}", "{\"a\" 1}",
        "{\"a\":}", "{,}", "[,1]", "\"abc", "\"a\nb\"", "\"a\tb\"", "\"\\x\"", "\"\\u12\"", "\"\\u12G4\"",
        "01", "-01", "-", "1.", ".5", "1e", "1e+", "+1", "[1]x", "NaN", "Infinity", "{\"a\":1} {",
        "'a'", "[", "{", "[\"a\"", "{\"a\":1", "\"\\", "0x10", "1.2.3", "--1",
    };
    for (const char* text : cases) {
        if (!bad(text)) std::fprintf(stderr, "should not parse: %s\n", text);
        assert(bad(text));
    }
    std::string why;
    assert(!json::parse("[1,]", &why) && why.find("byte") != std::string::npos);
}

static void serializing() {
    assert(json::Value().dump() == "null" && json::Value(nullptr).dump() == "null");
    assert(json::Value(true).dump() == "true" && json::Value(false).dump() == "false");
    assert(json::Value(42).dump() == "42" && json::Value(-7).dump() == "-7");
    assert(json::Value(47900u).dump() == "47900" && json::Value(123456789012LL).dump() == "123456789012");
    assert(json::Value(1.0).dump() == "1" && json::Value(-0.0).dump() == "0");
    assert(json::Value(1.5).dump() == "1.5" && json::Value(0.1).dump() == "0.1");
    assert(json::Value(1e20).dump() == "1e+20");
    for (double d : {1.0 / 3.0, 2.0 / 3.0, 1e-7, 123456.789, 1e300, -2.5e-300, 0.30000000000000004,
                     static_cast<double>(3.14f)}) {
        assert(P(json::Value(d).dump()).asNumber() == d);  // every number reads back exactly
    }
    assert(json::Value(std::nan("")).dump() == "null");
    assert(json::Value(std::numeric_limits<double>::infinity()).dump() == "null");

    assert(json::Value("a\"b\\c\n\t\x01\x7f/").dump() == R"("a\"b\\c\n\t\u0001\u007f/")");
    assert(json::Value(std::string(1, '\0')).dump() == R"("\u0000")");
    assert(json::Value("caf\xC3\xA9 \xF0\x9F\x8E\xB8").dump() == "\"caf\xC3\xA9 \xF0\x9F\x8E\xB8\"");
    // Not UTF-8 (a Latin-1 preset name, say): repaired, so the hub can still read the message.
    assert(json::Value("Caf\xE9").dump() == "\"Caf\xEF\xBF\xBD\"");
    assert(json::Value("bad\xFF" "byte").dump() == "\"bad\xEF\xBF\xBD" "byte\"");
    assert(json::Value("\xC0\xAF").dump() == "\"\xEF\xBF\xBD\xEF\xBF\xBD\"");                       // overlong
    assert(json::Value("\xED\xA0\x80").dump() == "\"\xEF\xBF\xBD\xEF\xBF\xBD\xEF\xBF\xBD\"");       // surrogate
    assert(json::Value("\xE2\x82").dump() == "\"\xEF\xBF\xBD\xEF\xBF\xBD\"");                       // cut short
    assert(json::Value("\xF4\x90\x80\x80").dump().find("\xEF\xBF\xBD") != std::string::npos);      // past U+10FFFF

    const json::Value msg = json::Object{{"op", "did"}, {"action", "tuner"}, {"depth", 0}};
    assert(msg.dump() == R"({"op":"did","action":"tuner","depth":0})");
    const json::Value list = json::Array{1, "two", nullptr, true, json::Array(), json::Object()};
    assert(list.dump() == R"([1,"two",null,true,[],{}])");
    assert(json::Value(json::Object{{"k", json::Object{{"x", 1.5}}}}).dump() == R"({"k":{"x":1.5}})");
}

static void roundTrip() {
    const std::string text = R"({"a":[1,2.5,-3e-7,true,false,null,"\u00e9\ud83c\udfb8\n\"q\""],"b":{"c":{}},"d":""})";
    const json::Value v = P(text);
    assert(P(v.dump()) == v);
    assert(P(v.dump()).dump() == v.dump());
    const std::string big(60000, 'x');  // a long string survives whole
    assert(P(json::Value(big).dump()).asString() == big);
}

static void building() {
    json::Value o;
    o.set("x", 1).set("y", "z").set("x", 2);
    assert(o.dump() == R"({"x":2,"y":"z"})");
    json::Value a;
    a.push(1).push("b");
    assert(a.dump() == R"([1,"b"])");
    json::Value s = "text";
    s.set("now", "an object");  // set() on something else starts a fresh object
    assert(s.dump() == R"({"now":"an object"})");

    assert(P(R"({"a":1,"b":[true]})") == P(R"({"b":[true],"a":1.0})"));  // keys in any order
    assert(P(R"({"a":1})") != P(R"({"a":2})"));
    assert(P(R"({"a":1})") != P(R"({"a":1,"b":2})"));
    assert(P("[1,2]") != P("[2,1]") && P("1") != P("\"1\"") && P("null") == json::Value());

    assert(json::Value("s").asNumber(7.0) == 7.0);
    assert(json::Value(1).asString("f") == "f");
    assert(json::Value(2.0).asBool(true));
    assert(json::Value(static_cast<const char*>(nullptr)).isNull());
    assert(json::Value('A').asNumber() == 65.0);
}

static void localeIndependent() {
    // A host may switch the C or C++ locale to one with a decimal comma: JSON must not change.
    const char* names[] = {"de_DE.UTF-8", "de_DE.utf8", "de_DE", "fr_FR.UTF-8", "German_Germany.1252"};
    bool switched = false;
    for (const char* name : names) {
        if (std::setlocale(LC_ALL, name) != nullptr) {
            switched = true;
            try {
                std::locale::global(std::locale(name));
            } catch (...) {
            }
            break;
        }
    }
    assert(json::Value(1.5).dump() == "1.5" && json::Value(0.25).dump() == "0.25");
    assert(P("2.75").asNumber() == 2.75 && P("-1.5e3").asNumber() == -1500.0);
    std::setlocale(LC_ALL, "C");
    std::locale::global(std::locale::classic());
    std::printf("json_test: decimal-comma locale %s\n", switched ? "checked" : "not installed here, skipped");
}

int main() {
    scalars();
    strings();
    containers();
    errors();
    serializing();
    roundTrip();
    building();
    localeIndependent();
    std::printf("json_test: all passed\n");
    return 0;
}
