#pragma once

#include <juce_audio_basics/juce_audio_basics.h>
#include <juce_core/juce_core.h>
#include <atomic>
#include <map>
#include <memory>
#include <mutex>
#include <vector>

// The data model of a drum kit.
//
//   Kit
//    ├─ mics      the microphones the kit was recorded with (one mixer channel each)
//    └─ pieces    kick, snare, toms, hi-hat, cymbals...
//         └─ variants   the actual drums you can swap between (22" kick, 24" kick...)
//              └─ articulations   center, rimshot, sidestick, open, pedal...
//                   └─ hits       every recorded strike, one audio buffer per mic
//
// Velocity zones and round robins are not stored in the kit: they are worked out from the
// hits by the engine (see Analysis.h) so the same recordings can be zoned by their file
// names or by how loud they actually are, and re-zoned without reloading anything.
namespace pd
{
enum class PieceType { Kick, Snare, Tom, HiHat, Crash, Ride, China, Splash, Perc };
enum class MicGroup  { Close, Overhead, RoomClose, RoomFar, Other };

const char* pieceTypeName (PieceType);
PieceType pieceTypeFromName (const juce::String&, PieceType fallback);
const char* micGroupName (MicGroup);
MicGroup micGroupFromName (const juce::String&);

inline bool isTunable (PieceType t) { return t == PieceType::Kick || t == PieceType::Snare || t == PieceType::Tom || t == PieceType::Perc; }
inline bool isCymbal  (PieceType t) { return t == PieceType::HiHat || t == PieceType::Crash || t == PieceType::Ride || t == PieceType::China || t == PieceType::Splash; }

struct MicDef
{
    juce::String id, name;
    MicGroup group = MicGroup::Close;
};

using SampleBuffer = std::shared_ptr<const juce::AudioBuffer<float>>;

struct Hit
{
    std::vector<SampleBuffer> mics;      // indexed like Kit::mics; null = this mic has nothing for the hit
    double sampleRate = 44100.0;
    int fileLayer = -1;                  // velocity layer number from the file name, 1 = softest; -1 = none
    int fileRR = -1;                     // round robin number from the file name; -1 = none
    float peakDb = -120.0f;              // measured on the piece's reference mic
    float rmsDb = -120.0f;               // first 50 ms
    int length = 0;                      // longest mic buffer, in samples
    juce::String name;                   // shown in the hit popup and the Lab
};

struct Articulation
{
    juce::String id, name;               // "rim", "Rimshot"
    std::vector<Hit> hits;
    bool isOpen = false;                 // rings until something closes it (open hi-hat)
    bool closes = false;                 // chokes the piece's open articulations (closed hat, pedal)
    bool chokesAll = false;              // grabs the cymbal: silences every voice of the piece
};

struct VariantData
{
    std::vector<Articulation> artics;
    float detectedHz = 0.0f;             // fundamental found by pitch detection, 0 = none
    size_t bytes = 0;
};

struct Variant
{
    juce::String name;                   // "22\" Vintage"
    float sizeInches = 0.0f;             // drawn size; 0 = the piece type's usual size
    float depthInches = 0.0f;
    float naturalHz = 0.0f;              // declared pitch; 0 = use detectedHz
    juce::File folder;                   // user kits
    bool folderIsPiece = false;          // the piece folder holds the samples directly
    int factoryId = -1;                  // factory kit
};

struct Piece
{
    juce::String id, name;               // "tom1", "Tom 1"
    PieceType type = PieceType::Perc;
    std::vector<Variant> variants;
    int referenceMic = -1;               // the close mic used for levels and pitch
    float pan = 0.0f;                    // -1 left ... +1 right, where it sits in mono overheads and rooms
};

class Kit
{
public:
    juce::String name;
    bool isFactory = false;
    juce::File root;
    std::vector<MicDef> mics;
    std::vector<Piece> pieces;

    int findPiece (const juce::String& id) const;
    int findMic (const juce::String& id) const;

    // Loaded audio for a variant, or null while it hasn't been loaded. Loading is done by
    // KitLoader / FactoryKit; the kit only keeps what was loaded so switching back is instant.
    std::shared_ptr<const VariantData> getLoaded (int piece, int variant) const;
    void setLoaded (int piece, int variant, std::shared_ptr<const VariantData>);
    size_t loadedBytes() const;

private:
    mutable std::mutex cacheLock;
    std::map<std::pair<int, int>, std::shared_ptr<const VariantData>> cache;
};

// A stable name for one hit, used to remember which samples were marked bad:
// "snare/14x6.5 Brass/center/7"
juce::String hitKey (const Kit&, int piece, int variant, int artic, int hit);

// Text with non-ASCII characters in it (JUCE reads plain char* as ASCII).
inline juce::String utf8 (const char* text) { return juce::String (juce::CharPointer_UTF8 (text)); }

// Note names and frequencies.
float hzToMidi (float hz);
float midiToHz (float midi);
juce::String midiNoteName (int note, bool withOctave = true);   // 36 -> "C1" (C3 = 60, Logic / Ableton style)
juce::String pitchName (float midi);                             // 50.2 -> "D2 +20c"
} // namespace pd
