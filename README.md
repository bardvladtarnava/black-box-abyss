# BLACK BOX
### Hydrophone edition

Pelagic Station has been dark for twelve years. Six minutes ago its recorder called you by name. Take a salvage rig through four flooded compartments and find the original tape.

## Play

Extract the entire archive. On Windows, double-click **PLAY-WINDOWS.cmd** with Python 3.8+ installed. From an open terminal in this directory, run:

```sh
python play.py
```

On macOS or Linux, use `python3 play.py` if that is your Python command. Pick **1** for Rivet or **2** for Echo. **D** plays an autonomous expedition. In a real terminal, keys respond immediately. Use the arrow keys or Tab to select a button and Enter to confirm. Each button shows its shortcut and a contextual explanation. A × marks a temporarily unavailable action. Windows Terminal, Terminal.app and UTF-8 Linux terminals can render the half-block pixel art. Around 100 columns and 30 rows gives both combatants and their instruments room. The interface adapts to resizing.

The game starts in Bulgarian. Press **K** in the menu or during a dive and choose **1** for Bulgarian, **2** for Russian, or **3** for English. The switch leaves the current fight intact. You can also start with a specific language using `python play.py --lang en` or `--lang ru`.

Press **P** to open the station map. Use arrows, Tab or **1–4** to inspect a sector. **✓** marks cleared sectors, **◆** marks your current sector and **○** marks locked depths. Cleared sectors let you reread their recovered tapes. The progress meter counts cleared sectors from **0/4** through **4/4**. Opening the map takes no combat turn.

| Key | Action |
| --- | --- |
| A | Thrust with the cutter. Deal 5 damage before armor and add one noise mark. |
| S | Activate the rig's special ability. Clear noise and avoid the incoming pulse. |
| B | Breach for 7 damage and strip armor for the rest of the sector. One charge per sector. |
| G | Brace to clear noise and reduce the incoming strike by 4. |
| R | Consume one cell to repair up to 12 hull. A surviving contact can respond. |
| F | At two noise marks, listen to the three-note call and answer using 1, 2 and 3. |
| I | Inspect the upcoming pulse cycle and the contact's acoustic signature. |
| M | Mute or restore both music and effects. |
| P | Inspect the station map. |
| K | Change the interface language. |
| Q | End the expedition. |

Inside the hydrophone, **1 / 2 / 3** are low / middle / high. **L** repeats the call, **Backspace** edits an incomplete phrase, and **X** returns to combat. The call is also printed. Take as long as you like. A wrong phrase has no cost.

## Encounters and turn rules

Both rigs start with 28 hull and two cells. Rivet carries two anchors per compartment. An anchor absorbs the incoming strike; bracing on a strong pulse makes more sense than bracing on a weak one. Echo trades one cell for a decoy that redirects the displayed incoming pulse. Every decoy uses a cell that could otherwise repair the rig.

| Depth | Contact | Hull | Repeating base pulses | Signature |
| --- | --- | ---: | --- | --- |
| 180 m · Flood lock | Lantern drone | 11 | 2, 4 | 1–3–2 |
| 460 m · Pump cathedral | Piston crab | 16 | 5, 1, 2 | 2–1–1 |
| 790 m · Tape archive | Spindle eel | 19 | 1, 3, 6 | 3–1–2 |
| 1,200 m · Recorder vault | The Listener | 25 | 2, 6, 3 | 1–2–3 |

The crab closes its shell on its strongest pulse, shaving 3 damage off the cutter. The eel hits for 2 extra at two noise marks. The Listener activates armor at half hull, reducing cutter damage by 2. Breach and the acoustic abilities bypass armor. The HUD previews the cutter’s actual damage and the incoming pulse.

The pilot acts first. With two noise marks, a matching phrase deals 4 damage, clears noise and silences the contact for that turn. Another cutter strike deals up to 5. If the target survives that third strike it gets a 3-point sonar bonus, and the meter resets. For example, an unarmored contact with 5 hull can be finished immediately with the cutter. Against one with 6 hull, resonance leaves it at 2 and avoids its reply. Repair retains noise. Scan, listening, mute, invalid input and unavailable commands leave combat state unchanged.

A finishing hit prevents retaliation. Each cleared non-final compartment awards a cell and opens a service bay. Choose an extra cell or up to 8 hull before continuing. The next contact refreshes anchors, Breach and noise. Current hull and inventory carry over. Zero hull loses the dive. Recovering the final reel wins it. Combat rules also run with redirected input or plain line input.

## Sound and display

Four original looping arrangements share a 100 BPM pulse. The mixer crossfades at sector boundaries. Two noise marks or low hull bring up a heartbeat. A cutter hitting a target has a rightward stereo accent; an incoming strike lands on the pilot's side. Each three-note call uses the same pitches on the score and the playable hydrophone.

The game uses only Python's standard library. It reads bundled WAV samples and streams stereo PCM to Windows WaveOut, macOS AudioQueue, or a Linux SDL2 / PulseAudio / aplay output when available. Actual speaker latency depends on the OS and audio device. The HUD shows **off-line** if output is unavailable. Listening, matching pitches and all combat remain accessible visually.

```sh
python play.py --demo
python play.py --mute
python play.py --still
python play.py --plain
python -m unittest -v
```

Set `NO_COLOR=1` for monochrome rendering. The pixel scenes are drawn in Python; lighting, joint movement, pressure rings and debris are generated for each frame. To regenerate the bundled score from its Python source, run `python tools/compose.py`.

## Object design

| Principle | Example from the implementation |
| --- | --- |
| Encapsulation | `self.contact.damage(5)` clamps incoming damage and returns the amount actually taken. Hull and its maximum are read-only properties. |
| Inheritance | `class Echo(Hero)` and `class Rivet(Hero)` reuse Character's bounds and Hero's inventory. |
| Polymorphism | `self.pilot.ability(self.contact, incoming)` dispatches through the Hero interface. |
| Composition | Each Hero constructs `self.pack = Inventory()`, which owns a distinct collection of Cell instances. |

`dive.py` resolves input-free combat. A successful turn returns the ordered events, including the exact damage or repair. `play.py` schedules each event's sound and visual beats. `console.py` handles terminal input, display and temporary hull readings. `ocean.py` draws the artwork. `audio.py` mixes the score and owns the output device.

## Verification

Run the suite from the project directory. The following results were observed during release verification.

| Setup | Expected | Actual |
| --- | --- | --- |
| Apply 99 damage and healing to a 10-hull character; then try negative amounts | Bounds 0 and 10; both negative changes rejected | Passed |
| Scan, mistype a key, repair a full rig, exhaust both anchors | No extra turn or state change | Passed |
| Repair with a cell, spend the last cell, construct another rig | Cell removed once, empty ability rejected, new pack independent | Passed |
| Attack a 40-hull contact three times | Third counter gains 3; pilot has 17 hull, noise returns to zero | Passed |
| Enter a wrong phrase or try the receiver without sufficient noise | No resource or turn consumed | Passed |
| Match a signature on a surviving or finishing hit | One resonance event; no counter; one reward on a sector clear | Passed |
| Complete the recorded routes using strikes, repairs, rig abilities and matching | Both pilots recover the master tape | Rivet ended with 15 hull and Echo with 21 |
| Inspect the crab, eel and Listener and claim salvage twice | Armor responds to Breach, noise amplifies the eel, the Listener shields at half hull, one service reward per clearance | Passed |
| Deplete hull or quit, then issue more commands | End state stays final | Passed |
| Mix an impact and a counter, change depth, engage danger, mute and resume | Cues favour opposite speakers; score changes; mute emits zero samples and preserves the playhead | Passed |
| Inspect event cue times and replay HUD damage | Sound trigger lands in its scheduled visual frame; display cannot change game state | Passed |
| Resize a live terminal, tune correctly after a wrong phrase, run a full animated demo | Immediate keys, intact display and all four encounters | Passed in a Linux pseudo-terminal with simulated audio output |

The Linux SDL output path was exercised with a virtual device. Windows and macOS audio paths were implemented but were not tested on physical hardware. The stereo preview is rendered from the same game frames, cue schedule and mixer.

## Design revision and history

The original prototype showed a static character between commands and moved the whole text sprite when it struck. The revised design separates resolved turns from their presentation. A hit can now have anticipation, impact, recoil and a positioned sound while input timing has no effect on the turn outcome. The hydrophone uses an untimed three-note reply so the musical mechanic remains playable on a muted computer.

The archive includes `history.bundle` with the project's Git history. To open it as a working repository from the extracted folder:

```sh
git clone -b main history.bundle black-box
```
