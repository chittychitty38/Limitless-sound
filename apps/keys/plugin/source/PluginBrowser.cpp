#include "PluginBrowser.h"

#include <thread>

static bool isOurs (const juce::String& nameOrId)
{
    return nameOrId.containsIgnoreCase ("Limitless Undo") || nameOrId.contains ("Lmls");
}

std::vector<PluginChoice> PluginBrowser::findPlugins (juce::AudioPluginFormatManager& formats, bool instruments)
{
    std::vector<PluginChoice> found;
    for (auto* format : formats.getFormats())
    {
        auto name = format->getName();
        auto ids = format->searchPathsForPlugins (format->getDefaultLocationsToSearch(), true, true);
        for (auto& id : ids)
        {
            if (isOurs (id))
                continue;
            if (name == "AudioUnit")
            {
                // The type is in the id: aumu instruments, aufx and aumf effects.
                bool synth = id.contains ("aumu");
                bool effect = id.contains ("aufx") || id.contains ("aumf");
                if (instruments ? ! synth : ! effect)
                    continue;
            }
            auto pluginName = format->getNameOfPluginFromIdentifier (id);
            if (pluginName.isEmpty())
                pluginName = juce::File (id).getFileNameWithoutExtension();
            if (isOurs (pluginName))
                continue;
            found.push_back ({ pluginName, name == "AudioUnit" ? "AU" : name, id });
        }
    }
    std::sort (found.begin(), found.end(), [] (const PluginChoice& a, const PluginChoice& b)
    {
        auto c = a.name.compareIgnoreCase (b.name);
        return c != 0 ? c < 0 : a.format < b.format;
    });
    return found;
}

bool PluginBrowser::describe (juce::AudioPluginFormatManager& formats, const PluginChoice& choice, bool instruments,
                              juce::PluginDescription& result)
{
    for (auto* format : formats.getFormats())
    {
        auto formatName = format->getName();
        if ((choice.format == "AU" ? juce::String ("AudioUnit") : choice.format) != formatName)
            continue;

        if (formatName == "AudioUnit")
        {
            // An Audio Unit can be opened from its id alone, without loading it twice.
            result.pluginFormatName = formatName;
            result.fileOrIdentifier = choice.identifier;
            result.name = result.descriptiveName = choice.name;
            result.isInstrument = choice.identifier.contains ("aumu");
            return true;
        }

        juce::OwnedArray<juce::PluginDescription> types;
        format->findAllTypesForFile (types, choice.identifier);
        for (auto* t : types)
            if (t->isInstrument == instruments)
            {
                result = *t;
                return true;
            }
        if (! types.isEmpty())
        {
            result = *types.getFirst();
            return true;
        }
    }
    return false;
}

PluginBrowser::PluginBrowser (juce::AudioPluginFormatManager& f, bool forInstruments)
    : formats (f), instruments (forInstruments)
{
    title.setText (instruments ? "Choose an instrument to put inside" : "Choose a plugin to put inside",
                   juce::dontSendNotification);
    title.setFont (juce::FontOptions (24.0f, juce::Font::bold));
    addAndMakeVisible (title);

    status.setText ("Looking for plugins…", juce::dontSendNotification);
    status.setFont (juce::FontOptions (16.0f));
    addAndMakeVisible (status);

    search.setTextToShowWhenEmpty ("Search", juce::Colours::grey);
    search.setFont (juce::FontOptions (20.0f));
    search.setTitle ("Search plugins");
    search.onTextChange = [this] { filter(); };
    search.onReturnKey = [this] { choose (list.getSelectedRow() >= 0 ? list.getSelectedRow() : 0); };
    addAndMakeVisible (search);

    list.setModel (this);
    list.setRowHeight (34);
    list.setTitle ("Plugins");
    addAndMakeVisible (list);

    openButton.onClick = [this] { choose (list.getSelectedRow()); };
    cancelButton.onClick = [this] { if (onCancel) onCancel(); };
    addAndMakeVisible (openButton);
    addAndMakeVisible (cancelButton);

    // Reading every plugin's name can take a moment: do it off the message thread.
    // Its own format manager, so it never outlives the one it borrowed.
    auto stillAlive = alive;
    std::thread ([this, stillAlive, forInstruments]
    {
        juce::AudioPluginFormatManager local;
        juce::addDefaultFormatsToManager (local);
        auto found = findPlugins (local, forInstruments);
        juce::MessageManager::callAsync ([this, stillAlive, found = std::move (found)]() mutable
        {
            if (! stillAlive->load())
                return;
            all = std::move (found);
            status.setText (juce::String ((int) all.size()) + " plugins. Double-click one, or type and press Return.",
                            juce::dontSendNotification);
            filter();
        });
    }).detach();
}

PluginBrowser::~PluginBrowser()
{
    *alive = false;
}

void PluginBrowser::visibilityChanged()
{
    if (isShowing())
        search.grabKeyboardFocus();
}

void PluginBrowser::filter()
{
    auto words = juce::StringArray::fromTokens (search.getText(), true);
    shown.clear();
    for (auto& c : all)
    {
        bool ok = true;
        for (auto& w : words)
            ok = ok && (c.name.containsIgnoreCase (w) || c.format.containsIgnoreCase (w));
        if (ok)
            shown.push_back (c);
    }
    list.updateContent();
    list.selectRow (0);
    list.repaint();
}

void PluginBrowser::choose (int row)
{
    if (row < 0 || row >= (int) shown.size())
        return;
    juce::PluginDescription desc;
    if (describe (formats, shown[(size_t) row], instruments, desc))
    {
        if (onChoose)
            onChoose (desc);
    }
    else
        status.setText ("That one couldn't be read. Try another.", juce::dontSendNotification);
}

int PluginBrowser::getNumRows()
{
    return (int) shown.size();
}

juce::String PluginBrowser::getNameForRow (int row)
{
    if (row < 0 || row >= (int) shown.size())
        return {};
    return shown[(size_t) row].name + ", " + shown[(size_t) row].format;
}

void PluginBrowser::paintListBoxItem (int row, juce::Graphics& g, int width, int height, bool selected)
{
    if (row < 0 || row >= (int) shown.size())
        return;
    auto& c = shown[(size_t) row];
    g.fillAll (selected ? juce::Colour (0xff4fc3f7) : juce::Colour (row % 2 ? 0xff1d1d1d : 0xff181818));
    g.setColour (selected ? juce::Colours::black : juce::Colours::white);
    g.setFont (juce::FontOptions (18.0f));
    g.drawText (c.name, 12, 0, width - 90, height, juce::Justification::centredLeft, true);
    g.setColour (selected ? juce::Colours::black : juce::Colours::grey);
    g.setFont (juce::FontOptions (14.0f));
    g.drawText (c.format, width - 80, 0, 70, height, juce::Justification::centredRight, true);
}

void PluginBrowser::listBoxItemDoubleClicked (int row, const juce::MouseEvent&)
{
    choose (row);
}

void PluginBrowser::returnKeyPressed (int row)
{
    choose (row);
}

void PluginBrowser::paint (juce::Graphics& g)
{
    g.fillAll (juce::Colour (0xff111111));
}

void PluginBrowser::resized()
{
    auto r = getLocalBounds().reduced (16);
    title.setBounds (r.removeFromTop (34));
    status.setBounds (r.removeFromTop (24));
    r.removeFromTop (6);
    search.setBounds (r.removeFromTop (40));
    r.removeFromTop (8);
    auto buttons = r.removeFromBottom (44);
    cancelButton.setBounds (buttons.removeFromLeft (140));
    openButton.setBounds (buttons.removeFromRight (140));
    r.removeFromBottom (8);
    list.setBounds (r);
}
