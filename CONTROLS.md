# Xbox controls - 0.1.31

## PC and controller switching

The game starts in PC mode. **Click the real mouse** to use mouse/keyboard at
any time. This closes the mod radial and releases controller movement without
cancelling the new mouse order. Mouse movement or typing alone does not switch.

To activate Xbox mode, **press and release a controller button** (A is convenient)
or LT/RT, then release both sticks, buttons and triggers. The activation press
does not also execute an action. Stick movement alone does not activate it.
There is no top-screen mode/status line.

## Every button and combination

| Control | Action |
| --- | --- |
| Left stick (LS) | Move the selected character or group. In the radial, choose an action. In an action panel or target mode, change the selected slot/target. In other menus, move the cursor freely. |
| Right stick (RS) | Pan the world camera. In menus, move the cursor; in action panels, provide fine cursor aim. World panning is suppressed during dialogue, targeting, action panels and the radial. |
| A | Activate the nearby Talk/Open/Inspect/Use prompt; confirm an action/target; choose a dialogue answer or continue; click the focused menu button/slot. During an active intro/movie, skip it. |
| B | Cancel/back one step, close the radial, or cancel targeting. Where applicable, return from target selection to its action panel. |
| X | Right-click at the menu cursor, for example to inspect an inventory item. In Journal, switch the current quest/bestiary filter. |
| Y | Open/close the radial in the world. In Inventory, split the focused item stack. |
| D-pad Up | In neutral world gameplay, open **Attack**. In menus, action panels, radial, targets, dialogue and Journal, retain directional navigation. |
| D-pad Down | In neutral world gameplay, open **Select Special Ability**. In menus, action panels, radial, targets, dialogue and Journal, retain directional navigation. |
| D-pad Left/Right | Cycle nearby interaction targets in the world; choose adjacent menu buttons/slots/list cells, radial entries, actions or targets. In Journal, switch tabs. |
| LB / RB | Previous/next party member. With the radial open, switch radial pages. Party switching is disabled during dialogue. |
| LT (hold) | Highlight interactive world objects/points of interest. Releasing restores the prior highlight setting. Nearby A prompts do not require LT. |
| RT (hold) | Slow the free menu cursor for precision. |
| RT + RS Up/Down | Zoom the world camera in/out. Release the stick/trigger to stop. Suppressed in menus, dialogue and action panels. |
| L3 (press LS) | Toggle WALK/RUN. The choice persists until changed. |
| R3 (press RS) | Select the whole party. |
| Start / Menu | Pause/unpause in the world. |
| Back / View | Open Options from the world. This is separate from B. |
| Xbox / Guide / Share | No mod binding; handled by Windows, Steam or controller software. |

Up/Down shortcuts only apply when no menu, radial, action panel or targeting
mode is open. After opening Attack or Special Ability, use LS/D-pad to select
an available action and A to confirm. D-pad Left/Right keep their nearby-target
function; no Inventory/Journal shortcuts are assigned to them.

## Movement and camera

LS movement supports a single character or the selected group. Small direction
fluctuations are filtered; deliberate turns remain responsive and releasing
LS stops immediately. RUN retains its active move during route renewals. WALK
turns retain the active move; straight WALK segments use queued continuation.
The normal controller world cursor is hidden.

RS releases camera follow before panning. In PC mode, moving the real mouse to
a screen edge releases a remaining follow lock so stock edge scrolling can run.
Mouse position away from the edge preserves player-selected camera follow.
RT modifies RS to zoom instead of pan.

## Two-page radial menu

Press Y in the world. Use LS/D-pad to choose, **A** to open, **B** to cancel
and **LB/RB** to switch pages. The selected icon has a thin yellow frame.
The compact circle has an opaque background and the action name in its center.

| Page | Actions, clockwise from the top |
| --- | --- |
| 1 | Inventory, Journal, Map, Character, Attack, Talk, Items, Abilities |
| 2 | Spells, Rest, Mage Book, Stop, Formation, Ground loot, Priest Book, Quick save |

Spells opens the casting panel; Mage Book and Priest Book open memorization
screens. Availability follows the selected character's abilities. Rest and
Quick save follow the game's restrictions. Talk supports NPCs and companions.
Nearby prompts show white action-first text such as **Talk (A)**, without a panel.

## Inventory and item transfer

Opening Inventory starts on the **first square of the main carried-item grid**,
not the Quick Item row. D-pad changes slots; both sticks remain free cursors.
**A** selects/picks up or places an item; **X** opens its description; **B** returns.
To transfer an item, pick it up with A, switch character with LB/RB, then place
it with A. Returning from a description preserves the previous slot focus.

To split a stack:

1. Focus a stack containing more than one item and press **Y**.
2. In the original quantity dialog, **Up/Right adds 1**, **Down/Left subtracts 1**.
   Hold a direction to repeat; the amount is clamped to the available stack.
3. **A** confirms the amount; **B** cancels without splitting.
4. Transfer/place the separated items with the normal A / LB-RB / A flow.

Single items and bags do not open splitting. Container/ground loot screens,
spellbooks and action panels start at their first available item/spell/action.
Returning from details preserves the parent focus.

## Menus, dialogue and movies

D-pad selects buttons, slots, checkboxes and list cells. At a list edge, it
scrolls to the next available row. A activates the focused control; B backs out
one level. In Journal, Left/Right changes tabs, Up/Down selects or scrolls
entries, and X changes the current filter. Text entry still uses the keyboard.

During dialogue, Up/Down selects an answer and A confirms or continues. In
confirmation popups, D-pad selects a button and A confirms it. The quit dialog
starts on **No**; holding A cannot confirm a newly opened popup.

During an active intro/movie, **A skips the current movie**. Release and press
again to skip the next one. Movie input does not also activate a menu button.

This preview has not received a complete campaign/menu playtest. Some advanced
operations may require the free menu cursor or temporary PC mode.
