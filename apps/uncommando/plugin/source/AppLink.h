// The line from an Uncommando plugin to the Uncommando app, so ⌥⌘Z can reach it.
//
// The Uncommando app writes uncommando-link.json (port and token) to the Limitless Sound
// folder. This connects to it in the background, keeps trying every couple of
// seconds while it isn't running, and does nothing at all without it: the plugin's
// own Undo and Redo buttons always work. Protocol: uncommando/undo_link.py.

#pragma once

#include <juce_core/juce_core.h>
#include <juce_events/juce_events.h>

#include <atomic>
#include <functional>
#include <memory>

class AppLink : private juce::Thread
{
public:
    AppLink();
    ~AppLink() override;

    void start();
    void stop();

    // Who this plugin is: plugin, track, host... sent in the hello. Any thread.
    void setIdentity (const juce::var& identity);

    // Sends one message. Any thread. False when the app isn't connected.
    bool send (const juce::var& message);

    bool isConnected() const { return connected.load(); }

    std::function<void()> onConnected;                    // on the message thread
    std::function<void (const juce::var&)> onMessage;      // on the message thread

    static juce::File infoFile();

private:
    void run() override;
    void session (int port, const juce::String& token);
    bool writeLine (const juce::String& line);
    void post (std::function<void()> fn);

    std::unique_ptr<juce::StreamingSocket> socket;
    juce::CriticalSection socketLock, identityLock;
    juce::var identity;
    std::atomic<bool> connected { false };
    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>> (true);

    JUCE_DECLARE_NON_COPYABLE (AppLink)
};
