cmake_minimum_required(VERSION 3.22)

project(PandaDrums VERSION 0.5.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "Oldest macOS the plugin runs on")

option(PD_BUILD_PLUGIN "Build the AU / VST3 / Standalone plugin" ON)
option(PD_BUILD_TOOLS  "Build the unit tests and the offline render tool" ON)

# JUCE comes from GitHub at a pinned release unless FETCHCONTENT_SOURCE_DIR_JUCE points at a local copy.
include(FetchContent)
FetchContent_Declare(JUCE
    GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
    GIT_TAG        8.0.16-security
    GIT_SHALLOW    ON)
FetchContent_MakeAvailable(JUCE)

juce_add_binary_data(PandaDrumsData
    HEADER_NAME PandaBinaryData.h
    NAMESPACE   PandaBinaryData
    SOURCES
        Resources/fonts/Anton-Regular.ttf
        Resources/fonts/LilitaOne-Regular.ttf
        Resources/fonts/VarelaRound-Regular.ttf
        Resources/fonts/DejaVuSans-Bold.ttf)

# The 3D-rendered panda, kit and room (art/panda3d.py renders them; see art/README.md).
file(GLOB PD_ART_FILES CONFIGURE_DEPENDS Resources/art/*.png Resources/art/*.jpg Resources/art/*.json)
juce_add_binary_data(PandaArtData
    HEADER_NAME PandaArtData.h
    NAMESPACE   PandaArtData
    SOURCES     ${PD_ART_FILES})

# The GUI asset pack's panels, buttons, knob, toggles, tiles, readouts and icons (art/ui_prep.py).
file(GLOB PD_UI_FILES CONFIGURE_DEPENDS Resources/ui/*.png Resources/ui/*.json)
juce_add_binary_data(PandaUiData
    HEADER_NAME PandaUiData.h
    NAMESPACE   PandaUiData
    SOURCES     ${PD_UI_FILES})

set(PD_ENGINE_SOURCES
    Source/engine/KitTypes.cpp
    Source/engine/Analysis.cpp
    Source/engine/KitLoader.cpp
    Source/engine/FactoryKit.cpp
    Source/engine/Tuning.cpp
    Source/engine/Mapping.cpp
    Source/engine/Sampler.cpp
    Source/engine/Mixer.cpp
    Source/PluginProcessor.cpp)

set(PD_GUI_SOURCES
    Source/gui/Theme.cpp
    Source/gui/PandaArt.cpp
    Source/gui/Skin.cpp
    Source/gui/UiKit.cpp
    Source/gui/PandaStage.cpp
    Source/gui/KitPage.cpp
    Source/gui/MixerPage.cpp
    Source/gui/LabPage.cpp
    Source/gui/MappingPage.cpp
    Source/gui/TopBar.cpp
    Source/PluginEditor.cpp)

set(PD_DEFINITIONS
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_VST3_CAN_REPLACE_VST2=0
    JUCE_USE_FLAC=1
    JUCE_USE_OGGVORBIS=1
    PANDA_VERSION_STRING="${PROJECT_VERSION}")

set(PD_MODULES
    juce::juce_audio_utils
    juce::juce_audio_formats
    juce::juce_dsp)

if (PD_BUILD_PLUGIN)
    set(PD_ICON_ARGS)
    if (EXISTS "${CMAKE_CURRENT_SOURCE_DIR}/Resources/icon.png")
        set(PD_ICON_ARGS ICON_BIG Resources/icon.png ICON_SMALL Resources/icon.png)
    endif()

    juce_add_plugin(PandaDrums
        COMPANY_NAME                "The Panda Studios"
        COMPANY_WEBSITE             "https://github.com/chittychitty38/Limitless-sound"
        BUNDLE_ID                   com.thepandastudios.pandadrums
        PLUGIN_MANUFACTURER_CODE    Pnds
        PLUGIN_CODE                 PDrm
        FORMATS                     AU VST3 Standalone
        PRODUCT_NAME                "Panda Drums"
        DESCRIPTION                 "Chromatic, in-key drums played by a panda"
        IS_SYNTH                    TRUE
        NEEDS_MIDI_INPUT            TRUE
        NEEDS_MIDI_OUTPUT           FALSE
        IS_MIDI_EFFECT              FALSE
        EDITOR_WANTS_KEYBOARD_FOCUS FALSE
        COPY_PLUGIN_AFTER_BUILD     FALSE
        VST3_CATEGORIES             Instrument Drum
        AU_MAIN_TYPE                kAudioUnitType_MusicDevice
        ${PD_ICON_ARGS})

    target_sources(PandaDrums PRIVATE ${PD_ENGINE_SOURCES} ${PD_GUI_SOURCES} Source/PluginEntry.cpp)
    target_include_directories(PandaDrums PRIVATE Source)
    target_compile_definitions(PandaDrums PUBLIC ${PD_DEFINITIONS})
    target_link_libraries(PandaDrums
        PRIVATE PandaDrumsData PandaArtData PandaUiData ${PD_MODULES}
        PUBLIC juce::juce_recommended_config_flags juce::juce_recommended_lto_flags juce::juce_recommended_warning_flags)
endif()

if (PD_BUILD_TOOLS)
    # Unit tests: the engine, mapping, tuning and the editor, headless.
    juce_add_console_app(PandaDrumsTests PRODUCT_NAME "PandaDrumsTests")
    target_sources(PandaDrumsTests PRIVATE ${PD_ENGINE_SOURCES} ${PD_GUI_SOURCES} tests/Tests.cpp)
    target_include_directories(PandaDrumsTests PRIVATE Source)
    target_compile_definitions(PandaDrumsTests PRIVATE ${PD_DEFINITIONS} JUCE_MODAL_LOOPS_PERMITTED=1)
    target_link_libraries(PandaDrumsTests PRIVATE PandaDrumsData PandaArtData PandaUiData ${PD_MODULES}
        juce::juce_recommended_config_flags juce::juce_recommended_warning_flags)

    # Offline renderer: screenshots of every page and a demo video of the panda playing a groove.
    juce_add_console_app(PandaDrumsRender PRODUCT_NAME "PandaDrumsRender")
    target_sources(PandaDrumsRender PRIVATE ${PD_ENGINE_SOURCES} ${PD_GUI_SOURCES} tools/Render.cpp)
    target_include_directories(PandaDrumsRender PRIVATE Source)
    target_compile_definitions(PandaDrumsRender PRIVATE ${PD_DEFINITIONS} JUCE_MODAL_LOOPS_PERMITTED=1)
    target_link_libraries(PandaDrumsRender PRIVATE PandaDrumsData PandaArtData PandaUiData ${PD_MODULES}
        juce::juce_recommended_config_flags juce::juce_recommended_warning_flags)
endif()
