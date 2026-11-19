# BLACK BOX — Hydrophone edition

A rescue pilot descends into Pelagic Station after hearing their own callsign on a twelve-year-old recorder. A lantern drone guards the flood lock; a piston crab occupies the pump cathedral; a spindle eel nests in the tape archive. The Listener guards the master tape at 1,200 m.

**Rigs.** Both start with 28 hull and two cells. Rivet can anchor twice per encounter to absorb an incoming pulse. Echo spends a cell to reflect the contact's announced pulse. A cell can also repair up to 12 hull. Recovered cells and remaining hull carry forward; every cleared non-final sector awards one cell.

**Hydrophone.** Each cutter hit (5 damage) adds one noise mark. At two marks the pilot can match the contact's three-note signature to discharge a 4-point resonance hit and cancel its response. The signature is audible and visible. There is no timer. Against a contact with 4 hull this ends the fight; against one with 5 hull a cutter is the better finisher. A surviving contact responding to a third cutter hit deals 3 bonus damage and resets noise. Both rig abilities clear noise.

**Turns.** The pilot acts first. Scan, listening, editing a phrase, invalid input and unavailable actions are free. A successful action spends the turn. A destroyed contact has no response. Leaving ends the expedition; zero hull loses it; recovering the final tape wins it.

**Relationships.** Character enforces hull bounds. Hero adds an independently owned Inventory of Cell objects. Rivet and Echo implement the same ability method. Dive resolves commands; an accepted turn produces events. The terminal animates and scores those events after resolution, so music latency, frame rate and keyboard speed cannot affect damage.
