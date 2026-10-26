#include "AppLink.h"

AppLink::AppLink() : juce::Thread ("Uncommando link") {}

AppLink::~AppLink()
{
    stop();
}

void AppLink::start()
{
    *alive = true;
    startThread (juce::Thread::Priority::background);
}

void AppLink::stop()
{
    *alive = false;
    signalThreadShouldExit();
    {
        const juce::ScopedLock sl (socketLock);
        if (socket != nullptr)
            socket->close();
    }
    stopThread (3000);
}

juce::File AppLink::infoFile()
{
    auto home = juce::SystemStats::getEnvironmentVariable ("LIMITLESS_SOUND_HOME", {});
    if (home.isNotEmpty())
        return juce::File (home).getChildFile ("uncommando-link.json");

    auto base = juce::File::getSpecialLocation (juce::File::userApplicationDataDirectory);
   #if JUCE_MAC
    base = base.getChildFile ("Application Support");
   #endif
    return base.getChildFile ("Limitless Sound").getChildFile ("uncommando-link.json");
}

void AppLink::setIdentity (const juce::var& newIdentity)
{
    const juce::ScopedLock sl (identityLock);
    identity = newIdentity;
}

void AppLink::post (std::function<void()> fn)
{
    auto stillAlive = alive;
    juce::MessageManager::callAsync ([stillAlive, fn = std::move (fn)]
    {
        if (stillAlive->load())
            fn();
    });
}

bool AppLink::writeLine (const juce::String& line)
{
    const juce::ScopedLock sl (socketLock);
    if (socket == nullptr || ! socket->isConnected())
        return false;
    auto utf8 = (line + "\n").toStdString();
    return socket->write (utf8.data(), (int) utf8.size()) == (int) utf8.size();
}

bool AppLink::send (const juce::var& message)
{
    if (! connected.load())
        return false;
    return writeLine (juce::JSON::toString (message, true));
}

void AppLink::run()
{
    while (! threadShouldExit())
    {
        auto info = juce::JSON::parse (infoFile());
        auto port = (int) info.getProperty ("port", 0);
        auto token = info.getProperty ("token", {}).toString();

        if (port > 0 && token.isNotEmpty())
            session (port, token);

        // The Uncommando app isn't running, or it quit: look again in a moment.
        for (int i = 0; i < 20 && ! threadShouldExit(); ++i)
            juce::Thread::sleep (100);
    }
}

void AppLink::session (int port, const juce::String& token)
{
    auto s = std::make_unique<juce::StreamingSocket>();
    if (! s->connect ("127.0.0.1", port, 1000))
        return;

    {
        const juce::ScopedLock sl (socketLock);
        socket = std::move (s);
    }

    juce::var hello;
    {
        const juce::ScopedLock sl (identityLock);
        hello = juce::JSON::parse (juce::JSON::toString (identity, true));   // a copy
    }
    if (auto* obj = hello.getDynamicObject())
    {
        obj->setProperty ("op", "hello");
        obj->setProperty ("token", token);
    }
    writeLine (juce::JSON::toString (hello, true));

    juce::MemoryBlock pending;
    char buffer[4096];

    while (! threadShouldExit())
    {
        juce::StreamingSocket* sock;
        {
            const juce::ScopedLock sl (socketLock);
            sock = socket.get();
        }
        auto ready = sock->waitUntilReady (true, 250);
        if (ready < 0)
            break;
        if (ready == 0)
            continue;

        auto got = sock->read (buffer, (int) sizeof (buffer), false);
        if (got <= 0)
            break;
        pending.append (buffer, (size_t) got);

        for (;;)
        {
            auto* data = static_cast<const char*> (pending.getData());
            auto size = pending.getSize();
            auto* nl = static_cast<const char*> (std::memchr (data, '\n', size));
            if (nl == nullptr)
                break;

            auto line = juce::String::fromUTF8 (data, (int) (nl - data));
            pending.removeSection (0, (size_t) (nl - data) + 1);

            auto msg = juce::JSON::parse (line);
            auto op = msg.getProperty ("op", {}).toString();
            if (op == "welcome")
            {
                connected = true;
                post ([this] { if (onConnected) onConnected(); });
            }
            else if (op == "error")
            {
                break;
            }
            else if (connected.load())
            {
                post ([this, msg] { if (onMessage) onMessage (msg); });
            }
        }

        if (pending.getSize() > (1 << 20))
            break;   // a line that never ends: something is wrong, start again
    }

    connected = false;
    const juce::ScopedLock sl (socketLock);
    if (socket != nullptr)
        socket->close();
    socket.reset();
}
