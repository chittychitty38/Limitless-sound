// Choosing the plugin to put inside Uncommando: every AU and VST3 on this
// computer, by name, with a search box. Nothing is scanned or opened until you
// pick one, so a broken plugin elsewhere can't crash the DAW.

#pragma once

#include <juce_audio_processors/juce_audio_processors.h>
#include <juce_gui_basics/juce_gui_basics.h>

struct PluginChoice
{
    juce::String name, format, identifier;
};

class PluginBrowser : public juce::Component,
                      private juce::ListBoxModel
{
public:
    PluginBrowser (juce::AudioPluginFormatManager&, bool instruments);
    ~PluginBrowser() override;

    std::function<void (const juce::PluginDescription&)> onChoose;
    std::function<void()> onCancel;

    void resized() override;
    void paint (juce::Graphics&) override;
    void visibilityChanged() override;

    static std::vector<PluginChoice> findPlugins (juce::AudioPluginFormatManager&, bool instruments);
    static bool describe (juce::AudioPluginFormatManager&, const PluginChoice&, bool instruments,
                          juce::PluginDescription& result);

private:
    int getNumRows() override;
    void paintListBoxItem (int row, juce::Graphics&, int width, int height, bool selected) override;
    void listBoxItemDoubleClicked (int row, const juce::MouseEvent&) override;
    void returnKeyPressed (int row) override;
    juce::String getNameForRow (int row) override;

    void filter();
    void choose (int row);

    juce::AudioPluginFormatManager& formats;
    const bool instruments;
    std::vector<PluginChoice> all, shown;
    juce::Label title, status;
    juce::TextEditor search;
    juce::ListBox list;
    juce::TextButton openButton { "Open" }, cancelButton { "Cancel" };
    std::shared_ptr<std::atomic<bool>> alive = std::make_shared<std::atomic<bool>> (true);

    JUCE_DECLARE_NON_COPYABLE_WITH_LEAK_DETECTOR (PluginBrowser)
};
