# BLACK BOX

The first four sectors teach the controls through alternating pulses, armor, noise and a shield threshold. The three sectors below the recorder vault test rhythm. A rotating shell exposes a cutter opening, a harp gives the pilot a silent beat, and an iris changes its pulse cycle at half hull. A matching visual cue, an instrument readout and a localized tip announce each opening.

## Combat and presentation

`Dive` owns the encounter. `Character` enforces hull bounds, `Hero` owns an inventory of cells, and the two rigs implement the same ability interface. A successful action returns ordered events with actual damage and repairs. Input timing cannot change their outcome. The terminal animates a separate combat reading from those events. Sound effects, recoil and damage readouts share an impact phase.

The renderer paints the station, rigs, creatures and attacks onto a procedural raster. Color cells, fine pixels and ASCII shading all sample that raster. Instruments use plain characters in every mode. The HUD allocates space before the arena, then the scene scales to the terminal. Each sector has its own four-bar loop, plus the pressure layer and positioned one-shot effects.

## Continuity

`Logbook` stores preferences separately from the campaign. The campaign contains an active turn, its sector entrance and the highest clearance. A sector transition commits the cell reward together with the pending service choice. Claiming the choice records the updated inventory before control returns. A defeat restores the entrance as the next playable checkpoint. Victory retains the completed map and closes the active dive.

Saves use a temporary file in the destination directory, a flush and an atomic replacement. Restoring validates counts, sector bounds, flags and rig-specific resources before rebuilding game objects. An unavailable save location or unreadable file produces a localized warning.
