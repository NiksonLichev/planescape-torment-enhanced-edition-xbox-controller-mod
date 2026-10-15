# PST:EE Xbox Controller Mod 0.1.31 - preview

Xbox/XInput support for the verified Windows x64 PST:EE 3.2.2.0 executable.

## Current features

- LS character/group movement, L3 WALK/RUN and R3 select all.
- Filtered small steering corrections; continuous RUN and preserved WALK
  actions during turns. Releasing the stick stops movement immediately.
- RS world camera, RT+RS zoom and working PC mouse edge scrolling.
- D-pad Up opens Attack and Down opens Select Special Ability in neutral world
  gameplay; menus, radial, dialogue and targeting retain directional navigation.
- Direct white Talk (A), Open (A), Use (A) and Inspect prompts; nearby target cycling.
- Compact opaque two-page radial, centered action name and thin yellow icon frames.
- Mage Book, Priest Book and casting Spells, alongside Inventory, Journal, Map,
  Character, Attack, Talk, Items, Abilities, Rest, Stop, Formation, loot and quick save.
- Menu/slot/list navigation; first carried-item focus and parent focus restoration.
- Inventory Y stack splitting: D-pad quantity, A confirm, B cancel.
- A skips active movies; D-pad selects confirmation buttons, with Quit starting on No.
- Real mouse click returns to PC mode; a controller button/trigger reactivates Xbox.
- No top PC/controller status text. Back/View opens Options; Start pauses.

## Changes in 0.1.31

- Optional existing-save import after interactive installation; decline to keep
  a fresh profile. Command-line installs can request -ImportSaves explicitly.
- Import-Saves.cmd can copy saves later without reinstalling the mod.
- Originals and existing target slots are preserved. Conflicting names get a
  free slot number; identical copies are skipped on repeat imports.
- Complete local slots are copied and hash-verified before publishing. Settings,
  cloud files and incomplete saves are excluded. Copying requires a closed game.
- Controller gameplay and native binaries are unchanged from 0.1.30.

## Changes in 0.1.30

- English-only documentation and source notes, reconciled with all current controls.
- Explicit preview ZIP versus source ZIP installation instructions.
- A source-only/incomplete installer explains the correct download before touching
  a game folder, instead of failing with a missing manifest.json message.
- Clear explanation of the intentional separate save/settings profile and manual
  save copying. Original saves are not deleted or imported automatically.
- Gameplay and native binaries are unchanged from 0.1.29.

Use **PSTEE-Xbox-Controller-v0.1.31-preview.zip** to install. The source ZIP is for
GitHub/building. Close the game, uninstall an older managed version, then install.
Launch through Play-Controller-Mod.cmd or ControllerLab.exe. Disable Steam Input.
Read [README.md](README.md) and [CONTROLS.md](CONTROLS.md).

The installer checks the exact executable fingerprint and derives UI locally.
Game executables, archives, full stock UI, stock icons and saves are not bundled.
Automated checks cover input, navigation, stack splitting, guarded movement,
installer restoration/refusals and archive contents. Selected features have
in-game user validation; a complete campaign/menu audit is still pending.
The author's license choice remains deferred until publication.
