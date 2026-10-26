# Limitless Undo: a plugin that holds another plugin and remembers every change you
# make to it, so it can be undone on its own with ⌥⌘Z through Limitless Keys.
#
#   cmake -B build -DCMAKE_BUILD_TYPE=Release          # downloads JUCE
#   cmake -B build -DJUCE_DIR=/path/to/JUCE             # or use a copy you have
#   cmake --build build --config Release
#   ctest --test-dir build                               # the undo history tests
#
# Options: -DLIMITLESS_UNDO_AAX=ON adds the Pro Tools (AAX) plugin,
#          -DLIMITLESS_UNDO_TESTS_ONLY=ON builds only the tests, without JUCE.

cmake_minimum_required(VERSION 3.22)
project(LimitlessUndo VERSION 0.1.0 LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
if(APPLE)
    set(CMAKE_OSX_DEPLOYMENT_TARGET "11.0" CACHE STRING "Oldest macOS to run on")
endif()

option(LIMITLESS_UNDO_AAX "Build the AAX plugin for Pro Tools" OFF)
option(LIMITLESS_UNDO_TESTS_ONLY "Build only the undo history tests" OFF)

# The undo history, with no JUCE in it, and its tests ---------------------------------

add_library(undo_core STATIC core/UndoHistory.cpp)
target_include_directories(undo_core PUBLIC core)
set_target_properties(undo_core PROPERTIES POSITION_INDEPENDENT_CODE ON)

add_executable(undo_core_tests tests/UndoHistoryTests.cpp)
target_link_libraries(undo_core_tests PRIVATE undo_core)
enable_testing()
add_test(NAME undo_core COMMAND undo_core_tests)

if(LIMITLESS_UNDO_TESTS_ONLY)
    return()
endif()

# JUCE ---------------------------------------------------------------------------------

if(JUCE_DIR)
    add_subdirectory(${JUCE_DIR} juce EXCLUDE_FROM_ALL)
else()
    include(FetchContent)
    FetchContent_Declare(JUCE
        GIT_REPOSITORY https://github.com/juce-framework/JUCE.git
        GIT_TAG 8.0.12
        GIT_SHALLOW TRUE)
    FetchContent_MakeAvailable(JUCE)
endif()

set(LIMITLESS_FORMATS VST3 Standalone)
if(APPLE)
    list(APPEND LIMITLESS_FORMATS AU)
endif()
if(LIMITLESS_UNDO_AAX)
    list(APPEND LIMITLESS_FORMATS AAX)
endif()

function(limitless_undo_plugin target product code bundle synth)
    juce_add_plugin(${target}
        COMPANY_NAME "Limitless Sound"
        COMPANY_WEBSITE "https://github.com/chittychitty38/limitless-sound"
        BUNDLE_ID ${bundle}
        PLUGIN_MANUFACTURER_CODE Lmls
        PLUGIN_CODE ${code}
        PRODUCT_NAME "${product}"
        DESCRIPTION "Holds a plugin and remembers every change to it, for plugin-only undo"
        VERSION ${PROJECT_VERSION}
        FORMATS ${LIMITLESS_FORMATS}
        IS_SYNTH ${synth}
        NEEDS_MIDI_INPUT ${synth}
        NEEDS_MIDI_OUTPUT FALSE
        IS_MIDI_EFFECT FALSE
        EDITOR_WANTS_KEYBOARD_FOCUS TRUE
        COPY_PLUGIN_AFTER_BUILD FALSE)

    target_sources(${target} PRIVATE
        source/PluginProcessor.cpp
        source/PluginEditor.cpp
        source/PluginBrowser.cpp
        source/KeysLink.cpp)

    target_compile_definitions(${target} PUBLIC
        LIMITLESS_UNDO_INSTRUMENT=$<BOOL:${synth}>
        JUCE_PLUGINHOST_VST3=1
        JUCE_PLUGINHOST_AU=$<BOOL:${APPLE}>
        JUCE_WEB_BROWSER=0
        JUCE_USE_CURL=0
        JUCE_VST3_CAN_REPLACE_VST2=0
        JUCE_REPORT_APP_USAGE=0)

    target_link_libraries(${target}
        PRIVATE
            undo_core
            juce::juce_audio_utils
            juce::juce_audio_processors
        PUBLIC
            juce::juce_recommended_config_flags
            juce::juce_recommended_lto_flags
            juce::juce_recommended_warning_flags)
endfunction()

# An audio effect, for effects, and an instrument, for instruments.
limitless_undo_plugin(LimitlessUndo "Limitless Undo" Lund org.limitlesssound.undo FALSE)
limitless_undo_plugin(LimitlessUndoInstrument "Limitless Undo Instrument" Luni org.limitlesssound.undo.instrument TRUE)

# The plugin with a stand-in plugin inside it, and the link to Limitless Keys.
juce_add_console_app(undo_plugin_tests PRODUCT_NAME "undo_plugin_tests")
target_sources(undo_plugin_tests PRIVATE
    tests/PluginTests.cpp
    source/PluginProcessor.cpp
    source/PluginEditor.cpp
    source/PluginBrowser.cpp
    source/KeysLink.cpp)
target_compile_definitions(undo_plugin_tests PRIVATE
    JucePlugin_Name="Limitless Undo"
    JucePlugin_VersionString="${PROJECT_VERSION}"
    LIMITLESS_UNDO_INSTRUMENT=0
    JUCE_PLUGINHOST_VST3=1
    JUCE_PLUGINHOST_AU=$<BOOL:${APPLE}>
    JUCE_WEB_BROWSER=0
    JUCE_USE_CURL=0
    JUCE_MODAL_LOOPS_PERMITTED=1)
target_link_libraries(undo_plugin_tests PRIVATE
    undo_core
    juce::juce_audio_utils
    juce::juce_audio_processors
    juce::juce_recommended_config_flags
    juce::juce_recommended_warning_flags)
add_test(NAME undo_plugin COMMAND undo_plugin_tests)
