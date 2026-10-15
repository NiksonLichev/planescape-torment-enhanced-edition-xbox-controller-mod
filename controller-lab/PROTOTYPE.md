# Controller implementation - 0.1.31

## Supported target and isolation

The exact Windows x64 3.2.2.0 executable is required, SHA-256
`99ae15860cfdbcdaad0f48e005eee21444046b21de848c1deab9367e8246a3c5`.
Full fingerprint and instruction checks precede native binding. Re-examine
other executable builds; do not reuse addresses based only on a version label.
Work in an isolated game copy/profile. Saves are not imported automatically.

ControllerLab.exe starts the adjacent game suspended and registers the DLL on
the game's own Lua thread. Native code reads foreground XInput and supplies
guarded game commands and marked SDL events. Real mouse clicks relinquish
controller ownership without cancelling the user's new PC order. Activation
requires a fresh controller button/trigger followed by neutral controls.

## UI and interaction

ui_build.py patches the user's stock UI and builds spatial navigation metadata.
The non-modal driver polls Tick through a blank render label; visible native
overlays have their own guarded blank poll. Do not disable that callback when
hiding status text. Dialog/world actions dispatch through queued UI input
callbacks rather than re-entering game actions from rendering.

The radial is an original 420x420 opaque circle with two pages and thin yellow
selection BAMs. Stock icons are loaded from game resources. Nearby A actions
use object IDs and validated geometry. Talk supports NPCs and companions.
Up/Down world shortcuts share the radial's Attack/Abilities dispatch and are
suppressed in menus, dialogue, targeting and pending interactions.

Main carried-item focus is slot_inv_30 / equipment.group0; personal0 is Quick
Item. Parent focus survives child descriptions. Menu metadata omits the hidden
inventory dispatcher. Y captures the stack owner, slot, resource, ID and count;
the dispatcher revalidates the request before calling showItemAmountRequester.
The stock quantity popup handles bounded D-pad count, A Done and B cancel.

## Movement and camera

World steering uses a 60 ms low-pass filter, five-degree deadband and 80 ms
stable-correction requirement. Turns over 30 degrees bypass smoothing. Neutral,
mode changes, menus, focus loss and PC handoff clear filter state. Extensions
reuse the accepted direction; menu/target input remains direct.

RUN retains its active MoveToPoint across updates. WALK turns use the same
guarded destination retarget; straight WALK continues through a bounded queued
leg. Stock group generation computes formation destinations; temporary future
moves are consumed and the stock asynchronous path requester updates the route.
No SetCurrentAction or animation-frame writes are used for live retargets.
Guards include ownership/selection, mode, sprite class, area, opcode, pending
move validity, destination bounds and writable aligned memory. Operation 201
with b=2 denotes a live RUN update or WALK turn; 203 records member retargets.

The active action destination is sprite +0x460, opcode +0x3f0 and elapsed ticks
+0x3ec. Stock path requester is RVA 0x41d350; these offsets are build-specific.
Camera follow is an actor ID at world +0xa58, not a boolean selected-ID toggle.
Operation 19 records/relinquishes the mod-owned lock or explicitly releases it
for RS/PC edge panning. User follow away from a PC screen edge is preserved.
Operation 18 uses the stock world view command; RT+RS uses zoom input.

## Validation and packaging

Native model checks cover 48 WALK/RUN renewals, 20 lagging-follower renewals,
80 active RUN updates, 48 WALK turns, formation/action/tick preservation,
invalid-write refusal, camera ownership/focus and movie skip event guards.
Lua checks cover jitter, deliberate turns/reversal/release, PC handoff,
camera/zoom, world shortcuts, dialogue, menu focus, stack splitting and radial UI.
These are isolated fixtures, not physical controller playtests. Runtime feedback
is separate; final smoothness and a complete campaign/menu audit require play.

build_release.py emits a preview installer ZIP and a source ZIP. The source has
no compiled payload/manifest and cannot install directly. Both contain English
documentation only. Public archives exclude game data, stock UI, saves, tools,
personal settings and local backups/logs. Installer fixtures verify exact
restoration, edits/conflicts/fingerprint rejection, reinstall backups and an
actionable source-only archive error before game-path handling.

## Optional save import

The launcher retains its isolated profile requirement. Import-Saves.ps1 copies
complete local BALDUR.gam/BALDUR.SAV slots into that profile without copying
Baldur.lua or cloud files. It validates non-linked paths, rejects same/nested
profiles and active Torment processes, inventories complete slots, skips
identical content and assigns unused names for collisions. A verified slot is
published by an atomic directory move from a private staging folder; an existing
slot is never merged or overwritten. Installer import is opt-in, with a Yes/No
choice in interactive setup and -ImportSaves for command-line use. Import errors
leave the mod installed and report how to retry. Fixture checks use synthetic
profiles/process tables and never write to a real save profile.
