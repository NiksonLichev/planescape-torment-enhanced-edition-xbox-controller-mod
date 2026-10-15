# Menu and input check scope - 0.1.31

test_menu_navigation.py runs the Lua controller and real dispatch routines with
mocked game screens. These results do not imply a physical controller playtest
of every screen or a full campaign audit.

| Route | Automated coverage |
| --- | --- |
| Inventory | First carried-item slot, spatial navigation, descriptions, Y split, quantity clamp/cancel/stale owner, parent focus |
| Journal | Tabs, quests/bestiary filters, entries and scrolling |
| Map | Area/World Map opening and nested back behavior |
| Character | Stock panel route and back to world |
| Attack | Radial and world D-pad Up, enabled weapon slot, target selection and back |
| Talk | NPC/companion targeting, confirm/cancel and nearby-object guards |
| Items / Abilities | Enabled slots, targets, back; world D-pad Down for Special Ability |
| Spells | Casting availability, enabled actions and targets |
| Mage Book / Priest Book | Memorization routes, first available spell and parent focus |
| Rest | Stock route and confirmation cancellation |
| Stop / Select all | Stock command and R3 party selection |
| Formation / Ground loot | Stock route, initial focus and back |
| Options | Back/View route, spatial controls, nested cancellation |
| Quick save | Stock route using the isolated profile |
| Confirmation dialogs | D-pad/A, Quit default No, held-A guard, nested B |

Additional coverage includes same-frame direction+A, disabled/list cells,
PC handoff, movement/target guards, camera/zoom, LT highlight reassertion,
movie-to-menu release guards and the thin transparent-center selection frames.
Native movement tests preserve active action/ticks and formation during RUN
updates and WALK turns. Runtime observations and visual feedback are recorded
separately from these fixture checks.
