"""Exercise the Lua input state machine with Lua 5.2 and a mocked game.

No controller, SDL events, or live game process are touched by this test.
"""
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).parent / 'tools' / 'python'))
from lupa.lua52 import LuaRuntime

root = Path(__file__).resolve().parent
from ui_resources import stock_back_lua, BACK_MENUS, named_menus, escape_action, patch_cancel_bindings
runtime = LuaRuntime()
runtime.execute('''
trace = {}
snapshot = {1,0,0,0,0,0,0,0,300,300,1024,768,100,1,500,400,1,1,0}
menus = {}; editing = 0; worldActive = false; paused = false; locked = false
gameState=0; gameIcon=0
alwaysRun=false
nearby={}
function record(...) trace[#trace+1] = {...} end
function PSTPadNative(op, a,b,c)
    if op==19 then
        record(op,a)
        if a==1 then locked=true; cameraFollowID=selectedCameraID or 1; cameraOwnerID=cameraFollowID
        elseif a==0 then
            if cameraOwnerID and cameraOwnerID==cameraFollowID then locked=false; cameraFollowID=nil end
            cameraOwnerID=nil
        elseif a==2 then locked=false; cameraFollowID=nil; cameraOwnerID=nil end
        return 1
    end
    if op==6 then return table.unpack(nearby[a] or {0,0,0,0,0,0}) end
    if op==7 then record(op,a); return 1 end
    if op==8 then record(op,a); return 1 end
    if op==15 then record(op,a,b); return 1 end
    if op==10 then return routeRemaining or 300 end
    if op==9 then record(op,a,b,c); return 300, rejectedSteering and 0 or 1 end
    if op ~= 0 then record(op,a,b,c) end
    return table.unpack(snapshot)
end
worldScreen = {
    HighlightEnabled = function() return highlighted==true end,
    SetHighlightEnabled = function(_,value) highlighted=value; record('highlight',value) end,
    CheckIfPaused = function() return paused end,
    TogglePauseGame = function() paused = not paused; record('pause',paused) end,
    GetScrollLocked = function() return locked end,
    LockScrollSelected = function() locked = not locked; record('lock',locked) end,
    OnDialogReplyClick = function(_, marker) record('dialog',marker) end,
    StopGroundItems = function() menus.WORLD_QUICKLOOT=nil; record('close-loot') end,
    StopContainer = function() menus.WORLD_CONTAINER=nil; record('close-container') end,
    StartGroundItems = function() menus.WORLD_QUICKLOOT=true end,
    OnLeftPanelButtonClick = function(_,index) record('panel',index) end,
    OnQuickSaveButtonClick = function() record('quicksave') end,
    OnRestButtonClick = function() record('rest') end,
}
pst={SpellContextClickable=function() return canCast~=false end}
game = {
    CancelCurrentAction = function() record('stop') end,
    SelectAll = function() record('all') end,
    GetState = function() return gameState end,
    GetIconIndex = function() return gameIcon end,
    SetState = function(_, value) gameState=value; record('state',value) end,
    SetIconIndex = function(_, value) gameIcon=value; record('icon',value) end,
    GetAlwaysRun = function() return alwaysRun end,
    SetAlwaysRun = function(_, value) alwaysRun=value; record('run',value) end,
}
otherScreen={SelectEngine=function(_,screen) assert(screen==worldScreen); worldActive=true; menus={}; record('return-world') end}
e = {GetActiveEngine = function() if worldActive then return worldScreen else return otherScreen end end}
e.RestoreHidden=function() record('restore-hidden') end
function Infinity_SetOverlay(name) if not name then menus.QuitMenu=nil end; record('overlay',name) end
function Infinity_ShutdownGame() record('shutdown') end
function Infinity_IsMenuOnStack(name) return menus[name] or false end
function Infinity_PushMenu(name) menus[name] = true end
function Infinity_PopMenu(name) menus[name or mockTop] = nil end
function Infinity_SetBackground() end
function Infinity_TextEditHasFocus() return editing end
function Infinity_GetInCutsceneMode() return false end
function fullActionbarClickable() return worldActive end
function Infinity_GetNumCharacters() return 2 end
function Infinity_GetINIValue() return 1 end
function Infinity_SetArea(...) record('area',...) end
function getDialogRowClickable(index) return true end
function Infinity_SelectDialogueOption() error('screen-coordinate dialogue click must not be used') end
function onDialogButtonClick() record('continue') end
const = {ACTIONBAR_STATE_WEAPONS=1,ACTIONBAR_STATE_ITEMS=2,ACTIONBAR_STATE_SPECIAL_ABILITES=3,ACTIONBAR_STATE_SPELLS=4,
    JOURNAL_MODE_QUESTS=0,JOURNAL_MODE_JOURNAL=1,JOURNAL_MODE_BESTIARY=2,
    ENTRY_TYPE_INPROGRESS=0,ENTRY_TYPE_COMPLETE=1,BESTIARY_CLASS_PC=0,BESTIARY_CLASS_NPC=1}
function actionbarResetState() gameState=0; gameIcon=0; record('reset') end
function showContextMenu(state) contextBarState=state; record('context',state) end
buttonArray={
    GetNumberOccupiedSlots=function() return 3 end,
    GetButtonEnabled=function(_,index) return index~=1 end,
    OnLButtonPressed=function(_,index) record('button',index) end,
}
function questEnabled(n) return quests[n].visible end
function setQuestViewed(n) record('view',n) end
function getBestiaryEnabled(n) return bestiary[n].visible end
function journalScroll() return nil end
function toggleFormationsMenu() menus.WORLD_FORMATION=not menus.WORLD_FORMATION end
function optionsFromStart() return false end
function Infinity_ChangeOption(...) record('restore-option',...) end
function Infinity_StopKeybind() record('stop-keybind') end
function setKeymap(...) record('restore-keymap',...) end
function Infinity_Log() end
languages={}; Popup2Button={cancelFunc=function() record('cancel-popup') end}
loadScreen={OnMainCancelButtonClick=function() menus.LOAD=nil; record('close-load') end}
saveScreen={OnMainCancelButtonClick=function() menus.SAVE=nil; record('close-save') end}
storeScreen={OnMainDoneButtonClick=function() menus={}; record('close-store') end}
worldMapScreen={StopWorldMap=function() menus.WORLD_MAP=nil; record('close-worldmap') end}
''')
runtime.execute((root / 'M_PSTPAD.lua').read_text(encoding='utf-8'))
runtime.execute("assert(not PSTController.controllerActive, 'startup must allow normal PC input'); PSTController.controllerActive=true")
runtime.execute(stock_back_lua((root/'backups'/'UI.menu.original').read_text(encoding='utf-8-sig')))
runtime.execute('''
local pad = PSTController
local function tick(buttons, elapsed)
    snapshot[2] = buttons or 0; snapshot[13] = snapshot[13] + (elapsed or 100)
    local result = pad.Tick()
    assert(pad.error == nil, tostring(pad.error))
    return result
end
local function count(kind)
    local n = 0; for _,event in ipairs(trace) do if event[1] == kind then n=n+1 end end
    return n
end
-- Neutral rearm, one A click per press, and B's queued Escape.
tick(); trace = {}; tick(4096); tick(4096)
assert(count(2) == 1, 'A should click once, not repeat')
tick(); tick(8192); assert(trace[#trace][1] == 3 and trace[#trace][2] == 27)
-- Numeric zero must allow gameplay; camera follow precedes movement.
tick(); worldActive = true; snapshot[3] = 25000; trace = {}
tick(); tick(); assert(count(9) == 1 and locked, 'left stick should steer in world coordinates')
assert(not alwaysRun, 'stick movement must retain the chosen WALK setting')
tick(0,25); tick(0,25); tick(0,25)
assert(count(9) == 1, 'steady direction should not continuously restart the path')
snapshot[3] = 0; snapshot[4] = 25000; tick(0,25)
assert(count(9) == 2, 'turning should not wait for the steady refresh interval')
-- Once moving, stay active between the start and release thresholds.
snapshot[3] = 5000; snapshot[4] = 0; tick(0,25)
assert(pad.moving, 'near-deadzone fluctuation should not restart movement')
snapshot[3] = 0; tick(); assert(count('stop') == 1 and not locked, 'release should stop and restore camera')
assert(count(5)>=2 and count(11)==1 and not alwaysRun, 'release stops the owned native route without changing walk/run')
-- Multi-selection refreshes less often, while turning and releasing stay fast.
snapshot[18]=2; snapshot[3]=25000; trace={}; tick(); tick()
local commands=count(9); assert(commands==1); tick(); tick(); tick(); assert(count(9)==commands)
snapshot[3]=0; snapshot[4]=25000; tick(0,25); assert(count(9)==commands+1)
routeRemaining=50; tick(0,200); assert(count(9)==commands+2)
assert(trace[#trace][1]==9 and trace[#trace][4]==1,'near-arrival must append without replacing the active move')
local acceptedAt=pad.lastMove
rejectedSteering=true; tick(0,200)
assert(pad.lastMove==acceptedAt,'a full waypoint queue must not postpone stuck-route recovery')
rejectedSteering=false
routeRemaining=300
snapshot[4]=0; tick(); assert(not alwaysRun and not pad.driveCursorHidden)
snapshot[18]=1
-- Unknown actor position must never steer using a guessed location.
snapshot[17] = 0; snapshot[3] = 25000; trace = {}; tick(); tick()
assert(count(9) == 0, 'missing position must suppress movement')
snapshot[3] = 0; snapshot[17] = 1; tick()
-- Dialog selection uses actual rows, not the label's visual index.
menus.WORLD_DIALOG = true
dialogTable = {{text='narration'}, {marker='answer-one'}, {marker='answer-two'}}
trace = {}; tick(2); tick(); tick(4096)
assert(count('dialog') == 0 and count(3) == 2, 'dialog must queue input instead of reentering UI rendering')
pad.DispatchDialogue()
assert(count('dialog') == 1 and trace[#trace][2] == 'answer-two', 'D-pad/A should confirm the response marker')
-- Long history and a scrolled list do not change the marker selected by A.
dialogTable = {}; for n=1,80 do dialogTable[n] = {text='history'} end
dialogTable[81] = {marker=7}; dialogTable[82] = {marker=19}
trace = {}; tick(); tick(2); tick(); tick(4096); pad.DispatchDialogue()
assert(count('dialog') == 1 and trace[#trace][2] == 19)
-- A stale queued response must not choose from a new conversation.
tick(); tick(4096); dialogTable = {{marker=99}}; trace = {}; pad.DispatchDialogue()
assert(count('dialog') == 0)
-- Continue / Show more uses the stock callback.
tick(); dialogOverflowTable = {{marker=101}}; tick(4096); trace = {}; pad.DispatchDialogue()
assert(count('continue') == 1); dialogOverflowTable = {}
tick(); menus.WORLD_DIALOG = false
-- Y opens the radial on the same edge and owns only its own pause.
trace = {}; tick(32768); assert(pad.radial and paused)
tick(); tick(4096); assert(not pad.radial and not paused)
assert(pad.pendingWorld=='inventory', 'radial inventory should queue its stock panel action')
pad.DispatchWorld(); assert(trace[#trace][1]=='panel' and trace[#trace][2]==3)
tick(); paused = true; tick(32768); tick(); tick(8192)
assert(paused, 'closing radial must preserve an existing pause')
paused = false; tick()
-- Loss of focus releases held highlights and requires neutral again.
snapshot[7] = 100; tick(); assert(pad.tabHeld)
snapshot[14] = 0; trace = {}; tick(4096)
assert(not pad.armed and not pad.tabHeld and count(2) == 0)
snapshot[14] = 1; tick(4096); assert(not pad.armed)
snapshot[7] = 0; tick(); assert(pad.armed)
-- Text fields suppress steering while retaining virtual cursor click.
editing = 1; snapshot[3] = 25000; trace = {}; tick(4096)
assert(count(4) == 0 and count(2) == 1)
-- World actions are dispatched from a UI input callback and preserve targeting.
editing=0; snapshot[3]=0; trace={}; pad.pendingWorld='attack'; pad.DispatchWorld()
assert(trace[#trace][1]=='context' and trace[#trace][2]==const.ACTIONBAR_STATE_WEAPONS)
pad.pendingWorld='talk'; pad.DispatchWorld()
assert(trace[#trace][1]=='icon' and trace[#trace][2]==18)
-- Talk now selects actual NPC IDs with LS, without a manual world cursor.
nearby={{1,100,500,400,0x31,50},{1,200,550,400,0x31,60}}
tick(); snapshot[3]=25000; trace={}; tick()
assert(pad.targetId==200 and count(1)==0 and count(4)==0 and not pad.driveCursorHidden)
tick(4096); assert(pad.pendingWorld=='target' and count(2)==0)
pad.DispatchWorld(); assert(count(15)==1 and count(7)==0 and count(8)==0)
tick(4096,100); assert(count(15)==1 and not pad.activation)
snapshot[3]=0; gameState=0; gameIcon=0; nearby={}; tick(0,300)
-- Context D-pad skips disabled slots; A queues a semantic button selection.
menus.WORLD_CONTEXT_BAR=true; contextBarState=1; trace={}; tick()
assert(pad.contextIndex==0)
tick(8); assert(pad.contextIndex==2)
tick(); tick(4096); assert(count(2)==0)
pad.DispatchWorld(); assert(count('button')==1 and gameState==2 and gameIcon==12 and not menus.WORLD_CONTEXT_BAR)
tick(); assert(pad.targetMode=='attack', 'weapon selection must enter target picker')
menus.WORLD_CONTEXT_BAR=true; contextBarState=1; gameState=0; gameIcon=0; pad.contextIndex=2
tick(); snapshot[3]=-25000; trace={}; tick(0,25)
assert(pad.contextIndex==0 and count(1)==0 and count(4)==0, 'LS must select a context slot without mouse aim or walking')
tick(0,25); assert(pad.contextIndex==0, 'held analog must observe the initial repeat delay')
snapshot[3]=0; tick(); snapshot[3]=25000; tick(0,25)
assert(pad.contextIndex==2, 'returning LS to neutral must rearm the next selection')
snapshot[3]=0; tick()
-- Back/View opens Options, independently of B/Escape and Start/pause.
tick(); tick(32); assert(pad.pendingWorld=='options')
menus.WORLD_CONTEXT_BAR=nil; pad.pendingWorld=nil; tick()
trace={}; tick(128); assert(pad.pendingWorld=='all')
pad.DispatchWorld(); assert(count('all')==1, 'R3 should select the whole party')
tick()
-- B closes one overlay at a time rather than cancelling behind it.
menus.WORLD_QUICKLOOT=true; menus.WORLD_CONTAINER=true; trace={}
pad.pendingBack=pad.lastTick; pad.DispatchBack(); assert(not menus.WORLD_CONTAINER and menus.WORLD_QUICKLOOT)
pad.pendingBack=pad.lastTick; pad.DispatchBack(); assert(not menus.WORLD_QUICKLOOT and count('stop')==0)
-- Journal D-pad selects visible entries, changes tabs, and scrolls each panel.
worldActive=false; menus.JOURNAL=true; journalMode=0; currentQuestType=0; currentBestiaryClass=0
quests={{visible=true},{visible=false},{visible=true}}; bestiary={{visible=true}}
trace={}; tick(); tick(2); assert(selectedQuest==1)
tick(); tick(2); assert(selectedQuest==3)
local top=PSTPadScrollQuests(0,100,400); assert(top<0)
assert(PSTPadScrollQuests(top,100,400)==nil, 'scroll request must be consumed once')
tick(); tick(8); assert(journalMode==1)
tick(); tick(2); assert(PSTPadScrollEntries(0,100,400)<0)
tick(); tick(8); assert(journalMode==2)
tick(); tick(2); assert(selectedBestiaryCreature==1)
tick(); tick(16384); assert(currentBestiaryClass==const.BESTIARY_CLASS_NPC)
-- Automatic proximity needs no LT. A captures an object ID and runs from
-- Return's callback; it must not click the stale ground cursor or resume LS.
menus={}; worldActive=true; gameState=0; gameIcon=0; snapshot[3]=0; snapshot[7]=0
nearby={{1,12345,540,420,0x31,80}}; tick(); trace={}; tick()
assert(pad.nearby.id==12345 and pad.NearbyText()=='Talk (A)' and not pad.tabHeld)
snapshot[3]=25000; tick(4096)
assert(pad.pendingWorld=='interact' and count(2)==0 and count(4)==0)
nearby={{1,67890,550,420,0x31,75}}; pad.DispatchWorld()
assert(trace[#trace][1]==15 and trace[#trace][2]==12345, 'A must not substitute a new target')
assert(gameState==2 and gameIcon==18)
trace={}; tick(4096,50); assert(count(8)==0)
tick(4096,50); assert(count(15)==0, 'held A must not repeat the direct object action')
snapshot[3]=0; gameState=0; gameIcon=0; tick(0,300)
-- Containers use neutral world state, and manual RS aiming still clicks.
nearby={{1,890,520,440,0x11,55}}; tick(); assert(pad.NearbyText()=='Open (A)')
trace={}; tick(4096); pad.DispatchWorld(); assert(count('reset')==1 and count(15)==1)
tick(0,100); assert(count(15)==1)
tick(0,300); snapshot[5]=25000; trace={}; tick()
assert(pad.nearby and count(1)==0, 'RS must not expose a free world cursor in controller mode')
snapshot[5]=0; tick(0,800); assert(pad.nearby)
menus.WORLD_CONTEXT_BAR=true; tick(); assert(not pad.nearby)
menus.WORLD_CONTEXT_BAR=nil; snapshot[14]=0; tick(); assert(not pad.nearby and not pad.pendingTarget)
-- Spell selection includes allies and preserves the spell's engine targeting
-- state while cycling with LS. B cancels before any staged click is emitted.
snapshot[14]=1; tick(); gameState=3; gameIcon=7; pad.requestedTargetMode='spell'
nearby={{1,901,500,410,0x31,30},{1,902,600,420,0x31,70}}; tick()
snapshot[3]=25000; trace={}; tick(); assert(pad.targetId==902 and pad.targetMode=='spell' and count(1)==0)
tick(4096); pad.DispatchWorld(); assert(gameState==3 and gameIcon==7)
tick(8192,25); assert(not pad.activation and count(8)==0)
pad.DispatchBack(); assert(gameState==0 and not pad.targetMode)
-- Description regions must not steal a nearby container's Open badge.
worldActive=true; menus={}; snapshot[3]=0; tick(0,300)
nearby={{1,1001,505,400,0x41,10},{1,1002,565,400,0x11,65}}; trace={}; tick()
assert(pad.nearby.id==1002 and pad.NearbyText()=='Open (A)')
tick(8); assert(pad.nearby.id==1001 and pad.NearbyText()=='Inspect (A)')
assert(count(1)==0, 'D-pad nearby selection must not warp a hidden world cursor')
-- Exercise A on every radial entry through the actual controller queue.
nearby={}; paused=false; snapshot[3]=0; snapshot[4]=0
for page,entries in ipairs(pad.radialPages) do
    for index,entry in ipairs(entries) do
        menus={}; worldActive=true; gameState=0; gameIcon=0; tick()
        pad.radial=true; pad.radialPage=page; pad.radialEntries=entries; pad.radialIndex=index
        trace={}; tick(4096)
        assert(not pad.radial, entry[1]..' must leave radial')
        if type(entry[2])=='number' then
            assert(trace[#trace][1]==3 and trace[#trace][2]==entry[2], entry[1]..' hotkey')
        else
            assert(pad.pendingWorld==entry[2], entry[1]..' queued action')
            pad.DispatchWorld()
            if entry[2]=='attack' then assert(contextBarState==const.ACTIONBAR_STATE_WEAPONS)
            elseif entry[2]=='talk' then assert(gameState==2 and gameIcon==18)
            elseif entry[2]=='items' then assert(contextBarState==const.ACTIONBAR_STATE_ITEMS)
            elseif entry[2]=='abilities' then assert(contextBarState==const.ACTIONBAR_STATE_SPECIAL_ABILITES)
            elseif entry[2]=='spells' then assert(contextBarState==const.ACTIONBAR_STATE_SPELLS)
            elseif entry[2]=='all' then assert(count('all')==1)
            elseif entry[2]=='stop' then assert(count('stop')==1)
            elseif entry[2]=='formation' then assert(menus.WORLD_FORMATION)
            elseif entry[2]=='loot' then assert(menus.WORLD_QUICKLOOT)
            elseif entry[2]=='options' then assert(trace[#trace][1]=='panel' and trace[#trace][2]==7)
            elseif entry[2]=='character' then assert(trace[#trace][1]=='panel' and trace[#trace][2]==4)
            elseif entry[2]=='magebook' then assert(trace[#trace][1]=='panel' and trace[#trace][2]==5)
            elseif entry[2]=='priestbook' then assert(trace[#trace][1]=='panel' and trace[#trace][2]==6)
            elseif entry[2]=='inventory' then assert(trace[#trace][1]=='panel' and trace[#trace][2]==3)
            elseif entry[2]=='journal' then assert(trace[#trace][1]=='panel' and trace[#trace][2]==2)
            elseif entry[2]=='map' then assert(trace[#trace][1]=='panel' and trace[#trace][2]==1)
            elseif entry[2]=='rest' then assert(count('rest')==1)
            elseif entry[2]=='quicksave' then assert(count('quicksave')==1) end
        end
        -- Each world overlay must close through a fresh physical-B edge.
        tick(); tick(8192); assert(pad.pendingBack)
        pad.DispatchBack(); assert(not menus.WORLD_FORMATION and not menus.WORLD_QUICKLOOT)
        assert(gameState==0 and not pad.pendingBack)
    end
end
-- B leaves principal screens through SelectEngine and closes help first.
for _,name in ipairs({'INVENTORY','CHARACTER','AREA_MAP','SPELLS','JOURNAL'}) do
    menus={[name]=true}; worldActive=false; tick(); trace={}; tick(8192)
    pad.DispatchBack(); assert(worldActive and count('return-world')==1,name..' B')
end
menus={WORLD_MAP=true,AREA_MAP=true}; worldActive=false; tick(); tick(8192); pad.DispatchBack()
assert(not menus.WORLD_MAP and menus.AREA_MAP,'world map B must return to the area map')
menus={}; worldActive=true; canCast=false; pad.pendingWorld='spells'; trace={}; pad.DispatchWorld()
assert(count('context')==0 and pad.actionNotice,'unavailable spells need feedback, not an empty context')
canCast=true
for _,name in ipairs({'INVENTORY_HELP','CHARACTER_HELP','SPELLS_HELP','MAP_HELP','WORLD_HELP','WORLD_HELP_TABLET'}) do
    menus={[name]=true,INVENTORY=true}; worldActive=false; tick(); trace={}; tick(8192)
    pad.DispatchBack(); assert(not menus[name] and menus.INVENTORY and count('return-world')==0,name..' B depth')
end
-- Native Talk candidates include the companion; Lua preserves mode 3 and ID.
menus={}; worldActive=true; nearby={{1,7001,550,420,0x31,60},{1,7002,580,420,0x31,80}}
snapshot[3]=0; tick(); pad.pendingWorld='talk'; pad.DispatchWorld(); tick()
tick(8); assert(pad.targetId==7002 and pad.nearby.mode==3)
tick(); trace={}; tick(4096); pad.DispatchWorld()
assert(count(15)==1 and trace[#trace][1]==15 and trace[#trace][2]==7002 and trace[#trace][3]==3)
tick(); tick(8192); pad.DispatchBack()
-- A child Cancel must restore settings and leave its parent screen alive.
fontSizeCancel=3; gammaCancel=4; brightnessCancel=5; musicCancel=6
for _,handler in ipairs(pad.stockBackHandlers) do
    local name=handler[1]
    menus={[name]=true}; mockTop=name; worldActive=false; trace={}
    if name~='ESC_MENU' then menus.ESC_MENU=true end
    tick(); tick(8192); pad.DispatchBack()
    assert(not menus[name], name..' must close')
    if name~='ESC_MENU' then assert(menus.ESC_MENU and count('return-world')==0,name..' must retain parent') end
    if name=='OPTIONS_GRAPHICS' then assert(count('restore-option')==3)
    elseif name=='OPTIONS_SOUND' then assert(count('restore-option')==1)
    elseif name=='OPTIONS_KEYBINDINGS' then assert(count('restore-keymap')==1 and count('stop-keybind')==1)
    elseif name=='POPUP_TWOBUTTON' then assert(count('cancel-popup')==1) end
end
menus={OPTIONS_FEEDBACK=true,OPTIONS_GAMEPLAY=true,ESC_MENU=true}; mockTop='OPTIONS_FEEDBACK'; worldActive=false
tick(); tick(8192); pad.DispatchBack(); assert(not menus.OPTIONS_FEEDBACK and menus.OPTIONS_GAMEPLAY and menus.ESC_MENU)
-- B on a three-button popup invokes only the explicitly labelled Cancel.
for _,side in ipairs({'left','mid','right'}) do
    menus={POPUP_THREEBUTTON=true}; Popup3Button={[side..'Text']='CANCEL_BUTTON',[side..'Func']=function() record('cancel-three') end}
    tick(); trace={}; tick(8192); pad.DispatchBack(); assert(not menus.POPUP_THREEBUTTON and count('cancel-three')==1)
end
menus={POPUP_THREEBUTTON=true}; Popup3Button={leftText='SAVE_BUTTON',leftFunc=function() error('B must not save') end}
tick(); tick(8192); pad.DispatchBack(); assert(menus.POPUP_THREEBUTTON)
-- RT+vertical RS zooms only in the world; holding repeats at a bounded rate.
menus={}; worldActive=true; gameState=0; gameIcon=0; nearby={}; pad.pendingBack=nil
snapshot[3]=0; snapshot[4]=0; snapshot[5]=0; snapshot[6]=0; snapshot[8]=0; tick()
snapshot[8]=200; snapshot[6]=25000; trace={}; tick()
assert(count(16)==1 and count(1)==0 and count(2)==0 and count(9)==0)
assert(pad.zoomDirection==1 and trace[#trace][1]~=1)
tick(0,100); assert(count(16)==1)
tick(0,120); assert(count(16)==2)
snapshot[6]=-25000; tick(0,25); assert(count(16)==3 and pad.zoomDirection==-1)
snapshot[6]=0; tick(); tick(0,400); assert(count(16)==3 and not pad.zoomDirection)
snapshot[6]=25000; snapshot[8]=0; tick(); assert(count(16)==3)
snapshot[8]=200; menus.WORLD_CONTEXT_BAR=true; tick(); assert(count(16)==3)
menus.WORLD_CONTEXT_BAR=nil; pad.radial=true; tick(); assert(count(16)==3)
pad.radial=false; menus.WORLD_DIALOG=true; tick(); assert(count(16)==3)
menus={INVENTORY=true}; worldActive=false; trace={}; tick()
assert(count(16)==0 and count(1)>0, 'RT+RS retains the slow menu cursor')
snapshot[14]=0; menus={}; worldActive=true; trace={}; tick()
assert(count(16)==0 and not pad.zoomDirection and not pad.zoomTriggerHeld)
snapshot[14]=1; tick(); assert(not pad.armed and count(16)==0)
snapshot[6]=0; snapshot[8]=0; tick(); assert(pad.armed)
-- RS pans the camera without clicks or cursor motion. It releases only the
-- follow lock owned by controller walking and permits simultaneous LS travel.
menus={}; worldActive=true; gameState=0; gameIcon=0; pad.activation=nil; pad.pendingWorld=nil
pad.moving=false; pad.nativeDriving=false; locked=false; tick()
snapshot[3]=25000; tick(); assert(pad.cameraLockedByMod and locked)
snapshot[5]=25000; trace={}; tick()
assert(count(18)==1 and count(1)==0 and count(2)==0 and count(9)==1)
assert(not locked and not pad.cameraLockedByMod,'manual pan releases mod follow')
snapshot[3]=0; tick(); assert(count(18)==2,'camera works while standing still')
snapshot[5]=0; trace={}; tick(); assert(count(18)==0,'neutral RS stops immediately')
snapshot[5]=25000; menus.WORLD_DIALOG=true; trace={}; tick(); assert(count(18)==0)
menus={WORLD_CONTEXT_BAR=true}; trace={}; tick(); assert(count(18)==0 and count(1)>0)
menus={}; gameState=1; gameIcon=12; trace={}; tick(); assert(count(18)==0,'targeting cannot pan')
gameState=0; gameIcon=0; pad.radial=true; trace={}; tick(); assert(count(18)==0)
pad.radial=false; menus={INVENTORY=true}; worldActive=false; trace={}; tick()
assert(count(18)==0 and count(1)>0,'inventory retains its cursor')
menus={}; worldActive=true; snapshot[14]=0; trace={}; tick(); assert(count(18)==0)
snapshot[14]=1; tick(); snapshot[5]=0; tick(); assert(pad.armed)
-- PC mode does not run the pan path; ordinary mouse edge scrolling stays stock.
snapshot[19]=(snapshot[19] or 0)+1; trace={}; tick(); assert(not pad.controllerActive)
snapshot[5]=25000; tick(); assert(count(18)==0)
snapshot[5]=0; tick(); tick(4096); tick(); tick(); assert(pad.controllerActive and pad.armed)
-- Follow remains releasable after the selected character changes.
selectedCameraID=11; locked=false; snapshot[3]=25000; tick(); tick()
assert(locked and pad.cameraLockedByMod and cameraFollowID==11)
selectedCameraID=22; snapshot[3]=0; tick(); assert(not locked and not pad.cameraLockedByMod)
-- RS can override a follow lock retained across old plugin/session state.
locked=true; cameraFollowID=77; pad.cameraLockedByMod=false
snapshot[5]=25000; trace={}; tick(); assert(not locked and count(18)==1)
snapshot[5]=0; tick()
-- In PC mode, a screen-edge mouse releases stale follow once and performs no
-- synthetic movement/click/warp. A normal central mouse keeps user follow.
pad.controllerActive=false; locked=true; cameraFollowID=88; snapshot[9]=300; snapshot[10]=300
trace={}; tick(); assert(locked and count(19)==0)
snapshot[9]=0; trace={}; tick(); assert(not locked and not pad.controllerActive)
assert(count(19)==1 and count(18)==0 and count(1)==0 and count(2)==0 and count(9)==0)
trace={}; tick(); assert(#trace==0)
snapshot[9]=300; locked=true; cameraFollowID=99; menus.WORLD_DIALOG=true
snapshot[9]=0; trace={}; tick(); assert(locked and count(19)==0)
menus={}; locked=false; snapshot[9]=300; tick(4096); tick(); tick()
selectedCameraID=nil
''')
patched_menus = named_menus(patch_cancel_bindings((root/'backups'/'UI.menu.original').read_text(encoding='utf-8-sig')))
for name in BACK_MENUS:
    callback = escape_action(patched_menus[name])
    assert callback is not None, name
    runtime.execute("menus={['"+name+"']=true}; mockTop='"+name+"'; worldActive=false; PSTController.pendingBack=100; trace={}")
    runtime.execute(callback)
    runtime.execute("assert(not menus['"+name+"'] and PSTController.pendingBack==nil, 'local Escape cancellation')")
runtime.execute("menus={OPTIONS_FEEDBACK=true,OPTIONS_GAMEPLAY=true,ESC_MENU=true}; mockTop='OPTIONS_FEEDBACK'; worldActive=false; PSTController.pendingBack=100")
runtime.execute(escape_action(patched_menus['OPTIONS_FEEDBACK']))
runtime.execute("assert(not menus.OPTIONS_FEEDBACK and menus.OPTIONS_GAMEPLAY and menus.ESC_MENU and not PSTController.pendingBack, 'one-level local B')")
for name in ('INVENTORY','CHARACTER','AREA_MAP','WORLD_FORMATION','WORLD_CONTEXT_BAR',
             'WORLD_CONTAINER','WORLD_QUICKLOOT','WORLD_HELP','WORLD_HELP_TABLET',
             'INVENTORY_HELP','CHARACTER_HELP','SPELLS_HELP','MAP_HELP',
             'STORE_CHOOSER','STORE_BUYSELL','STORE_IDENTIFY','STORE_ROOMS','STORE_HEALING'):
    callback=escape_action(patched_menus[name])
    assert callback is not None, name
    runtime.execute("menus={['"+name+"']=true}; worldActive=false; PSTController.pendingBack=100; trace={}")
    runtime.execute(callback)
    runtime.execute("assert(not menus['"+name+"'] and not PSTController.pendingBack, 'local main/overlay B')")
runtime.execute('''
local pad=PSTController
local function tick(buttons,elapsed)
    snapshot[2]=buttons or 0; snapshot[13]=snapshot[13]+(elapsed or 100)
    pad.Tick(); assert(not pad.error,tostring(pad.error))
end
local function count(kind)
    local value=0; for _,event in ipairs(trace) do if event[1]==kind then value=value+1 end end
    return value
end
menus={}; worldActive=true; paused=false; locked=false; gameState=0; gameIcon=0
snapshot[3]=0; snapshot[4]=0; snapshot[5]=0; snapshot[6]=0; snapshot[7]=0; snapshot[8]=0; snapshot[14]=1
pad.controllerActive=true; pad.armed=true; pad.runEnabled=false; alwaysRun=false; tick()
trace={}; tick(64); assert(alwaysRun and pad.runEnabled and count('all')==0)
tick(64); assert(count('run')==1,'holding L3 must not repeat the toggle')
tick(); snapshot[3]=25000; tick(); tick(); assert(alwaysRun and pad.nativeDriving)
snapshot[3]=0; tick(); assert(alwaysRun,'stick release must retain RUN')
tick(64); assert(not alwaysRun and not pad.runEnabled)
tick(); snapshot[3]=25000; trace={}; tick(); tick()
assert(not alwaysRun and count('run')==0,'WALK must never force AlwaysRun on')
snapshot[3]=0; tick(); trace={}; tick(128); pad.DispatchWorld()
assert(count('all')==1 and not alwaysRun,'R3 retains Select all and cannot change run')
tick(); pad.pendingWorld='talk'; pad.DispatchWorld(); menus.WORLD_DIALOG=true
alwaysRun=true; tick(); assert(alwaysRun,'do not override an active scripted dialogue')
menus.WORLD_DIALOG=nil; gameState=0; gameIcon=0; tick()
assert(not alwaysRun and not pad.runEnabled,'dialogue return must restore the chosen WALK setting')
-- Relinquishing the controller after a real click preserves the PC order,
-- selection/aim, mouse position and run setting. Drift cannot reactivate it.
snapshot[3]=25000; tick(); tick(); assert(pad.nativeDriving)
gameState=2; gameIcon=12; snapshot[19]=snapshot[19]+1; trace={}; tick()
assert(not pad.controllerActive and not pad.nativeDriving and not pad.worldCursorHidden)
assert(count('stop')==0 and count(1)==0,'handoff must not cancel the PC order or warp its mouse')
assert(gameState==2 and gameIcon==12)
local released=false; for _,event in ipairs(trace) do if event[1]==11 and event[2]==0 then released=true end end
assert(released,'handoff must relinquish rather than clear the new PC route')
trace={}; tick(); tick(); assert(#trace==0 and not pad.controllerActive,'idle PC mode must not mutate input/UI')
-- The first new controller button acquires mode, then neutral re-arms actions.
alwaysRun=true; trace={}; tick(4096)
assert(pad.controllerActive and not pad.armed and pad.runEnabled and count(2)==0)
tick(4096); assert(not pad.armed)
snapshot[3]=0; tick(); assert(pad.armed)
-- A second real click while a controller button is held keeps PC mode until
-- a fresh edge, rather than oscillating every frame.
snapshot[19]=snapshot[19]+1; tick(4096); assert(not pad.controllerActive)
tick(4096); assert(not pad.controllerActive)
tick(); tick(64); assert(pad.controllerActive and not pad.armed)
tick(); assert(pad.armed); gameState=0; gameIcon=0
-- Handoff dismisses only a pause owned by the radial and releases held Tab.
pad.radial=true; pad.pausedForRadial=true; paused=true; pad.tabHeld=true
pad.pendingWorld='talk'; pad.pendingBack=pad.lastTick; pad.pendingDialog={marker='stale'}
snapshot[19]=snapshot[19]+1; trace={}; tick()
assert(not pad.radial and not paused and not pad.tabHeld)
assert(not pad.pendingWorld and not pad.pendingBack and not pad.pendingDialog and not pad.nearby)
tick(8192); tick(); assert(pad.controllerActive and pad.armed)
pad.radial=true; pad.pausedForRadial=false; paused=true
snapshot[19]=snapshot[19]+1; tick(); assert(paused and not pad.radial,'preserve a player-owned pause')
paused=false
-- Trigger activation is also an explicit button; stick movement alone is not.
snapshot[3]=25000; snapshot[5]=25000; tick(); assert(not pad.controllerActive)
snapshot[8]=200; tick(); assert(pad.controllerActive and not pad.armed)
''')
runtime.execute('''
local pad=PSTController
local function tick(buttons)
 snapshot[2]=buttons or 0; snapshot[13]=snapshot[13]+100; pad.Tick()
 assert(not pad.error,tostring(pad.error))
end
menus={}; worldActive=true; editing=0; gameState=0; gameIcon=0; nearby={}
snapshot[3]=0; snapshot[4]=0; snapshot[5]=0; snapshot[6]=0; snapshot[7]=0; snapshot[8]=0; snapshot[14]=1
pad.controllerActive=true; pad.armed=true; pad.radial=false; pad.tabHeld=false; highlighted=false
tick(); trace={}; snapshot[7]=100; tick()
assert(highlighted and pad.tabHeld,'LT must enable stock world highlights')
for _,event in ipairs(trace) do assert(not(event[1]==3 and event[2]==9),'LT must not queue synthetic Tab') end
-- Repair an engine-cleared flag while held, with hysteresis and repeated presses.
highlighted=false; tick(); assert(highlighted,'LT must repair a cleared engine flag')
local actionbarClickable=fullActionbarClickable
function fullActionbarClickable() return false end
highlighted=false; tick(); assert(highlighted,'LT must not depend on actionbar clickability')
fullActionbarClickable=actionbarClickable
snapshot[7]=45; tick(); assert(highlighted and pad.tabHeld)
snapshot[7]=39; tick(); assert(not highlighted and not pad.tabHeld)
for n=1,3 do snapshot[7]=100; tick(); assert(highlighted); snapshot[7]=0; tick(); assert(not highlighted) end
-- Preserve a highlight enabled from the original toolbar before holding LT.
highlighted=true; snapshot[7]=100; tick(); snapshot[7]=0; tick(); assert(highlighted)
highlighted=false; snapshot[7]=100; tick(); tick(32768)
assert(pad.radial and not highlighted and not pad.tabHeld,'radial early return must release LT')
tick(); tick(8192); assert(not pad.radial)
tick(); assert(highlighted,'holding LT on radial return re-enables highlights')
menus.WORLD_CONTAINER=true; tick(); assert(not highlighted)
menus.WORLD_CONTAINER=nil; tick(); assert(highlighted)
snapshot[14]=0; tick(); assert(not highlighted and not pad.tabHeld)
snapshot[14]=1; snapshot[7]=0; tick(); tick(); assert(pad.armed)
-- Mouse handoff restores the previous highlight state and PC mode stays quiet.
snapshot[7]=100; tick(); assert(highlighted)
snapshot[19]=snapshot[19]+1; tick(); assert(not highlighted and not pad.controllerActive)
trace={}; tick(); assert(#trace==0)
snapshot[7]=0; tick(4096); tick(); tick()
assert(pad.controllerActive and pad.armed)
-- Native movie polling owns A while playback is active, never Lua cursor clicks.
snapshot[20]=1; trace={}; tick(4096); tick(4096)
assert(pad.controllerActive and not pad.armed and pad.status=='Xbox | A: skip movie')
for _,event in ipairs(trace) do assert(event[1]~=2 and event[1]~=3,'movie A must not also click or activate Return') end
snapshot[20]=0; trace={}; tick(4096); assert(not pad.armed and #trace==0)
tick(); tick(); assert(pad.armed,'movie-to-menu transition requires a released A')
local actions={}; for _,page in ipairs(pad.radialPages) do for _,entry in ipairs(page) do actions[entry[2]]=true end end
assert(actions.magebook and actions.priestbook and actions.spells,'both books and casting must remain available')
-- Only the two explicitly requested world shortcuts are added.
nearby={}; pad.pendingWorld=nil; tick(); trace={}; tick(1); assert(pad.pendingWorld=='attack')
pad.DispatchWorld(); assert(contextBarState==const.ACTIONBAR_STATE_WEAPONS)
tick(1); assert(not pad.pendingWorld,'holding up must not reopen the action panel')
tick(); tick(2); assert(pad.pendingWorld=='abilities')
pad.DispatchWorld(); assert(contextBarState==const.ACTIONBAR_STATE_SPECIAL_ABILITES)
menus.WORLD_CONTEXT_BAR=true; tick(); trace={}; tick(1)
assert(not pad.pendingWorld and pad.contextIndex~=nil)
menus.WORLD_CONTEXT_BAR=nil; gameState=2; gameIcon=12; tick(); tick(2); assert(not pad.pendingWorld)
gameState=0; gameIcon=0; tick(); tick(4); assert(not pad.pendingWorld)
tick(); tick(8); assert(not pad.pendingWorld,'left/right remain interaction target cycling')
''')
runtime.execute('''
local pad=PSTController
local function tick(elapsed)
 snapshot[2]=0; snapshot[13]=snapshot[13]+(elapsed or 25); pad.Tick()
 assert(not pad.error,tostring(pad.error))
end
local function angle(degrees)
 local radians=math.rad(degrees)
 snapshot[3]=math.floor(math.cos(radians)*25000)
 snapshot[4]=math.floor(math.sin(radians)*25000)
end
local function moves()
 local result={}; for _,event in ipairs(trace) do if event[1]==9 then result[#result+1]=event end end
 return result
end
menus={}; worldActive=true; editing=0; gameState=0; gameIcon=0; nearby={}
snapshot[3]=0; snapshot[4]=0; snapshot[5]=0; snapshot[6]=0; snapshot[7]=0; snapshot[8]=0; snapshot[14]=1
pad.controllerActive=true; pad.armed=true; pad.radial=false; pad.pendingWorld=nil
-- Replay 25ms alternating hand jitter around both a cardinal and diagonal
-- heading, for WALK/RUN and solo/group. No small alternating turn commands.
for members=1,2 do for _,running in ipairs({false,true}) do for _,base in ipairs({0,45}) do
 snapshot[3]=0; snapshot[4]=0; tick(); alwaysRun=running; pad.runEnabled=running
 snapshot[18]=members; routeRemaining=300; trace={}; angle(base); tick(); tick()
 assert(#moves()==1)
 for n=1,60 do angle(base+(n%2==0 and 16 or -16)); tick() end
 assert(#moves()==1,'hand jitter must not repeatedly replace the route')
 assert(pad.nativeDriving and pad.moving and pad.runEnabled==running)
 -- Near arrival must not leak the unfiltered stick angle into a new leg.
 routeRemaining=50
 for n=1,12 do angle(base+(n%2==0 and 16 or -16)); tick() end
 local commands=moves(); assert(#commands>=2)
 for n=2,#commands do
  local command=commands[n]
  local dot=(command[2]*math.cos(math.rad(base))-command[3]*math.sin(math.rad(base)))/10000
  assert(dot>0.996,'waypoint extensions must retain the stable heading')
  assert(command[4]==1,'jitter must not turn an extension into route replacement')
 end
 -- A held gentle turn is accepted promptly instead of freezing the heading.
 routeRemaining=300; trace={}; angle(base+12)
 for n=1,10 do tick() end
 assert(#moves()>=1 and #moves()<=2,'a sustained gentle turn must settle within 250ms')
 local dot=pad.moveDirectionX*math.cos(math.rad(base+12))+pad.moveDirectionY*math.sin(math.rad(base+12))
 assert(dot>0.998,'settled analog direction must follow the intended turn')
 -- Large deliberate turns bypass filtering; neutral stops on the next tick.
 trace={}; angle(base+102); tick(); assert(#moves()==1,'large turn must stay immediate')
 angle(base-78); tick(); tick(); assert(#moves()==2,'reversal must not interpolate through zero')
 snapshot[3]=0; snapshot[4]=0; tick()
 assert(not pad.moving and not pad.nativeDriving and pad.steerX==nil and pad.steerCandidateAt==nil)
end end end
snapshot[18]=1; routeRemaining=300
-- PC handoff must discard smoothing state, with no stale heading on re-entry.
angle(0); tick(); tick(); snapshot[19]=snapshot[19]+1; tick()
assert(not pad.controllerActive and pad.steerX==nil and pad.moveDirectionX==nil)
snapshot[3]=0; snapshot[4]=0
''')
print('PASS: steering jitter replay, WALK/RUN solo/group, cardinal/diagonal, stable extensions, gentle/sharp turns, reversal and immediate release/PC reset')
print('PASS: Lua controls; world up Attack/down Ability; menu/target navigation; camera, zoom, PC handoff and prior controls')
