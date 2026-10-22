#pragma once

#include "KitTypes.h"

// The kit that comes inside the plugin, so it plays (and the panda drums) before any samples
// are loaded. Every hit is synthesized: several kick, snare, tom and cymbal sizes, five
// velocity layers with three round robins each, on close mics, overheads, a room and a far room.
namespace pd
{
class FactoryKit
{
public:
    static constexpr int layers = 5;
    static constexpr int rounds = 3;
    static constexpr double renderRate = 32000.0;

    static std::shared_ptr<Kit> create();

    // Synthesizes one variant. Takes a few tens of milliseconds; safe on a background thread.
    static std::shared_ptr<const VariantData> render (const Kit&, int piece, int variant);

    // Default variant of each piece (the arrows start here).
    static int defaultVariant (const Kit&, int piece);
};
} // namespace pd
