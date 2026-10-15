-- PST:EE Xbox prototype. Native input stays inside the foreground game process.
PSTController = {
    version = '0.1.31', status = 'Starting Xbox mod', error = nil,
    buttons = 0, lastTick = 0, lastMove = 0, repeatAt = {},
    armed = false, radial = false, radialIndex = 1, dialogIndex = 1,
    drive = true, moving = false, pausedForRadial = false,
    controllerActive = false,
    slot = 0, cursorX = nil, cursorY = nil,
    -- Small steering corrections must settle; deliberate turns stay immediate.
    moveTurnInterval = 35,
}
local pad = PSTController
local loader, loadError
if type(PSTPadNative) == 'function' then
    pad.native = PSTPadNative
elseif package and package.loadlib then
    loader, loadError = package.loadlib('override/pstcontroller.dll', 'luaopen_pstcontroller')
else
    loadError = 'Lua package.loadlib is unavailable'
end
if pad.native then
    -- The startup loader registered this on the engine's own Lua thread.
elseif loader then
    local ok, native = pcall(loader)
    if ok and type(native) == 'function' then pad.native = native
    else pad.error = ok and 'Unsupported executable or missing SDL exports' or tostring(native) end
else pad.error = tostring(loadError) end

local function down(mask, bit)
    return math.floor(mask / bit) % 2 == 1
end
local function clamp(value, lo, hi)
    return math.max(lo, math.min(hi, value))
end
local function axis(x, y, deadzone)
    x, y = x / 32768, y / 32768
    local length = math.sqrt(x * x + y * y)
    if length <= deadzone then return 0, 0, 0 end
    local magnitude = clamp((length - deadzone) / (1 - deadzone), 0, 1)
    return x / length * magnitude, y / length * magnitude, magnitude
end
local function resetSteeringFilter()
    pad.steerX,pad.steerY,pad.steerCandidateX,pad.steerCandidateY,pad.steerCandidateAt=nil,nil,nil,nil,nil
end
local function movementDirection(lx,ly,lm,elapsed,now)
    local x,y=lx/lm,ly/lm
    local previousX,previousY=pad.moveDirectionX,pad.moveDirectionY
    -- Start/reverse/large turns have no smoothing delay. Never interpolate a
    -- reversal through zero or carry an old direction across a neutral stick.
    if not previousX or x*previousX+y*previousY<0.8660254 then
        pad.steerX,pad.steerY=x,y
        pad.steerCandidateAt=nil
        return x,y,previousX~=nil
    end
    local alpha=1-math.exp(-elapsed/0.060)
    local fx=(pad.steerX or previousX)*(1-alpha)+x*alpha
    local fy=(pad.steerY or previousY)*(1-alpha)+y*alpha
    local length=math.sqrt(fx*fx+fy*fy)
    fx,fy=fx/length,fy/length
    pad.steerX,pad.steerY=fx,fy
    -- Five-degree angular deadband; persistent gentle turns remain analog.
    -- Extensions reuse the accepted heading so noise cannot bypass the filter
    -- when the next waypoint is queued. This does not filter menu/target input.
    if fx*previousX+fy*previousY>=0.9961947 then
        pad.steerCandidateAt=nil
    else
        if not pad.steerCandidateAt or fx*pad.steerCandidateX+fy*pad.steerCandidateY<0.9986295 then
            pad.steerCandidateX,pad.steerCandidateY,pad.steerCandidateAt=fx,fy,now
        elseif now-pad.steerCandidateAt>=80 then
            return fx,fy,true
        end
    end
    return previousX,previousY,false
end
local function press(bit, now)
    if not down(pad.buttons, bit) then pad.repeatAt[bit] = nil; return false end
    if not down(pad.previousButtons or 0, bit) then pad.repeatAt[bit] = now + 340; return true end
    if pad.repeatAt[bit] and now >= pad.repeatAt[bit] then pad.repeatAt[bit] = now + 110; return true end
    return false
end
local function edge(bit)
    return down(pad.buttons, bit) and not down(pad.previousButtons or 0, bit)
end
local function key(code)
    pad.native(3, code, 1)
    pad.native(3, code, 0)
end
local function menu(name)
    return pad.overlayName==name or Infinity_IsMenuOnStack(name)
end
local function dialogRows()
    local choices = {}
    for index, entry in ipairs(dialogTable or {}) do
        if entry.marker ~= nil and getDialogRowClickable(index) then choices[#choices + 1] = index end
    end
    return choices
end
local function stopMovement(preserveGameAction, preserveMousePosition)
    if pad.nativeDriving then
        pad.native(11,(preserveGameAction or Infinity_GetInCutsceneMode()) and 0 or 1)
        pad.nativeDriving=false
    end
    if pad.moving then
        if not preserveGameAction then game:CancelCurrentAction() end
        pad.moving = false
    end
    pad.moveDirectionX, pad.moveDirectionY = nil, nil
    resetSteeringFilter()
    if pad.driveCursorHidden then
        pad.native(5, pad.worldCursorHidden and 1 or 0)
        pad.driveCursorHidden = false
        if not preserveMousePosition and pad.driveCursorX and pad.driveCursorY then pad.native(1,pad.driveCursorX,pad.driveCursorY) end
        if preserveMousePosition then pad.cursorX,pad.cursorY=nil,nil
        else pad.cursorX,pad.cursorY=pad.driveCursorX,pad.driveCursorY end
        pad.driveCursorX,pad.driveCursorY=nil,nil
    end
    if pad.cameraLockedByMod then
        pad.native(19,0)
        pad.cameraLockedByMod = false
    end
end
local function closeRadial()
    pad.radial = false
    if pad.pausedForRadial and e:GetActiveEngine() == worldScreen then
        worldScreen:TogglePauseGame(true)
    end
    pad.pausedForRadial = false
end
local function runSetting()
    local value=game:GetAlwaysRun()
    return value==true or value==1
end
local function releaseHighlights()
    if pad.tabHeld then
        worldScreen:SetHighlightEnabled(pad.highlightBeforeLT==true)
        pad.tabHeld=false; pad.highlightBeforeLT=nil
    end
end
local function updateHighlights(lt,allowed)
    local held=allowed and (lt>60 or (pad.tabHeld and lt>=40))
    if held then
        local current=worldScreen:HighlightEnabled()
        current=current==true or current==1
        if not pad.tabHeld then pad.highlightBeforeLT=current; pad.tabHeld=true end
        -- Screen transitions and the stock toolbar can clear the engine flag.
        -- LT owns the held state and repairs it without a synthetic Tab event.
        if not current then worldScreen:SetHighlightEnabled(true) end
    else releaseHighlights() end
end
local function releaseController()
    pad.controllerActive=false
    pad.worldCursorHidden=false; pad.native(5,0)
    -- The real click may already have issued its own PC order. Relinquish the
    -- controller route without cancelling that order or warping the real mouse.
    stopMovement(true,true)
    closeRadial()
    releaseHighlights()
    pad.pendingBack,pad.pendingWorld,pad.pendingDialog,pad.pendingTarget=nil,nil,nil,nil
    pad.pendingSplit,pad.pendingQuantity,pad.quantityOwner=nil,nil,nil
    pad.targetMode,pad.targetId,pad.activation,pad.nearby=nil,nil,nil,nil
    pad.requestedTargetMode,pad.lastTargetContextState,pad.cancelledTargetContext=nil,nil,nil
    pad.zoomDirection,pad.zoomTriggerHeld,pad.zoomRepeat=nil,nil,nil
    pad.repeatAt={}; pad.runEnabled=nil
    pad.navigationFocus={}; pad.navigationInitial={}; pad.navigationCurrent=nil; pad.inventoryFocused=false
    pad.navigationScrollRequest={}; pad.navigationPending=nil
end

pad.radialPages = {{
    { 'Inventory', 'inventory', 'FOOT7', 0 }, { 'Journal', 'journal', 'FOOT5', 0 }, { 'Map', 'map', 'FOOT6', 0 },
    { 'Character', 'character', 'FOOT4', 0 }, { 'Attack', 'attack', 'TACTBUTT', 0 }, { 'Talk', 'talk', 'TACTBUTT', 4 },
    { 'Items', 'items', 'TACTBUTT', 2 }, { 'Abilities', 'abilities', 'TACTBUTT', 3 },
}, {
    { 'Spells', 'spells', 'TACTBUTT', 1 }, { 'Rest', 'rest', 'FOOT1', 0 }, { 'Mage Book', 'magebook', 'FOOT3', 0 },
    { 'Stop', 'stop', 'CIRCBUTT', 1 }, { 'Formation', 'formation', 'CIRCBUTT', 14 }, { 'Ground loot', 'loot', 'CIRCBUTT', 13 },
    { 'Priest Book', 'priestbook', 'FOOT2', 0 }, { 'Quick save', 'quicksave', 'TAB0', 0 },
}}
pad.radialPage = 1
pad.radialEntries = pad.radialPages[1]
function pad.RadialText(index)
    local label = pad.radialEntries[index][1]
    if pad.radialIndex == index then return '> ' .. label .. ' <' end
    return label
end
function pad.RadialBam(index)
    return pad.radialEntries[index][3]
end
function pad.RadialSequence(index)
    return pad.radialEntries[index][4]
end
function pad.RadialFrame(index)
    -- Only the tactical BAM has frame 2 in the requested sequence.
    return pad.radialIndex==index and pad.RadialBam(index)=='TACTBUTT' and 2 or 0
end
function pad.EnsureDriver()
    if not Infinity_IsMenuOnStack('PST_CONTROLLER_DRIVER') then
        Infinity_PushMenu('PST_CONTROLLER_DRIVER')
    end
end

-- Confirm from the UI's queued Return action, not from the render callback.
-- Clicking a row's computed screen position fails after dialog history scrolls.
function pad.DispatchDialogue()
    local pending = pad.pendingDialog
    pad.pendingDialog = nil
    if not pending then return onDialogButtonClick() end
    if not menu('WORLD_DIALOG') then return end
    if pending.continue then return onDialogButtonClick() end
    -- Reject a queued response if a mouse/keyboard choice already changed it.
    for _, entry in ipairs(dialogTable or {}) do
        if entry == pending.entry and entry.marker == pending.marker then
            chatboxScrollToBottom = 0
            worldScreen:OnDialogReplyClick(pending.marker)
            worldPlayerDialogSelection = 0
            return
        end
    end
end

function pad.DispatchWorld()
    if not pad.controllerActive then pad.pendingWorld=nil; pad.pendingTarget=nil; return end
    local action = pad.pendingWorld
    pad.pendingWorld = nil
    pad.native(12,110,({context=1,interact=2,target=3,talk=4,attack=5,all=6})[action] or 0,game:GetState())
    local target=pad.pendingTarget
    pad.pendingTarget=nil
    if e:GetActiveEngine() ~= worldScreen or menu('WORLD_DIALOG') or Infinity_GetInCutsceneMode() then return end
    if action == 'context' then
        local index=pad.pendingContextIndex
        pad.pendingContextIndex=nil
        pad.native(12,120,index or -1,pad.pendingContextState or -1)
        if menu('WORLD_CONTEXT_BAR') and index~=nil and pad.pendingContextState==contextBarState
            and buttonArray:GetButtonEnabled(index) and buttonArray:GetButtonEnabled(index)~=0 then
            pad.lastTargetContextState=contextBarState
            buttonArray:OnLButtonPressed(index)
            pad.native(12,121,index,game:GetState())
            pad.requestedTargetMode=pad.contextAction=='attack' and 'attack' or 'spell'
            if pad.contextAction=='attack' and game:GetState()==0 then
                game:SetState(2); game:SetIconIndex(12)
            end
            if game:GetState()~=0 then Infinity_PopMenu('WORLD_CONTEXT_BAR') end
        end
    elseif action == 'all' then game:SelectAll()
    elseif action == 'stop' then game:CancelCurrentAction()
    elseif action == 'attack' or action == 'items' or action == 'abilities' or action == 'spells' then
        if action=='spells' then
            local canCast=pst:SpellContextClickable()
            if not canCast or canCast==0 then
                pad.actionNotice='No spells available for this character'; pad.actionNoticeUntil=pad.lastTick+2000
                return
            end
        end
        pad.contextAction=action
        pad.contextFocused=false; pad.contextIndex=nil; pad.contextAnalogDirection=nil
        pad.lastTargetContextState=nil
        actionbarResetState()
        local states = {attack=const.ACTIONBAR_STATE_WEAPONS, items=const.ACTIONBAR_STATE_ITEMS,
            abilities=const.ACTIONBAR_STATE_SPECIAL_ABILITES, spells=const.ACTIONBAR_STATE_SPELLS}
        showContextMenu(states[action])
    elseif action == 'talk' then
        stopMovement()
        Infinity_PopMenu('WORLD_CONTEXT_BAR')
        game:SetState(2); game:SetIconIndex(18)
        pad.requestedTargetMode='talk'
    elseif (action == 'interact' or action=='target') and target then
        if action=='target' and (game:GetState()~=target.state or game:GetIconIndex()~=target.icon) then return end
        stopMovement()
        -- Capture the object ID at A's edge. Native revalidates its generation,
        -- area and eligibility; it never substitutes a different nearby object.
        if action=='interact' then
            if target.kind==0x31 then game:SetState(2); game:SetIconIndex(18)
            else actionbarResetState() end
        end
        pad.native(12,122,target.id,target.mode or 0)
        if pad.native(15,target.id,target.mode or 0)~=1 then actionbarResetState() end
        pad.requireMoveNeutral=true; pad.interactionHoldUntil=pad.lastTick+250
        pad.nearby=nil
    elseif action == 'formation' then toggleFormationsMenu()
    elseif action == 'loot' then
        if menu('WORLD_QUICKLOOT') then worldScreen:StopGroundItems() else worldScreen:StartGroundItems() end
    elseif action == 'inventory' then e:GetActiveEngine():OnLeftPanelButtonClick(3)
    elseif action == 'journal' then e:GetActiveEngine():OnLeftPanelButtonClick(2)
    elseif action == 'map' then e:GetActiveEngine():OnLeftPanelButtonClick(1)
    elseif action == 'character' then e:GetActiveEngine():OnLeftPanelButtonClick(4)
    elseif action == 'magebook' then e:GetActiveEngine():OnLeftPanelButtonClick(5)
    elseif action == 'priestbook' then e:GetActiveEngine():OnLeftPanelButtonClick(6)
    elseif action == 'rest' then e:GetActiveEngine():OnRestButtonClick()
    elseif action == 'options' then e:GetActiveEngine():OnLeftPanelButtonClick(7)
    elseif action == 'quicksave' then worldScreen:OnQuickSaveButtonClick(false) end
end

function pad.NearbyText()
    if not pad.nearby then return '' end
    local labels={[0x31]='Talk',[0x11]='Open',[0x21]='Door',[0x41]='Inspect',[0x42]='Travel'}
    return (pad.targetMode and (pad.targetMode=='attack' and 'Attack' or pad.targetMode=='talk' and 'Talk' or 'Cast')
        or labels[pad.nearby.kind] or 'Use')..' (A)'
end
local function displayTarget(target,width,height)
    pad.nearby=target
    if not target then return end
    local scale=Infinity_GetINIValue('Graphics','Scale UI',1)~=0 and math.min(width/1024,height/768) or 1
    local left=(width-1024*scale)/2
    Infinity_SetArea('PST_CONTROLLER_NEARBY',clamp((target.x-left)/scale-64,0,896),clamp(target.y/scale-68,32,620),128,30)
end
local function updateNearby(enabled,width,height,playerX,playerY,now)
    if not enabled then pad.nearby=nil; return end
    local targets={}
    for n=1,128 do
        local valid,id,x,y,kind,distance,count=pad.native(6,n,0)
        if valid==1 then
            local dx,dy=x-playerX,y-playerY
            local length=math.sqrt(dx*dx+dy*dy)
            local facing=length>4 and pad.facingX and ((dx*pad.facingX+dy*pad.facingY)/length) or 0
            targets[#targets+1]={id=id,x=x,y=y,kind=kind,distance=distance,mode=0,
                score=distance+(kind==0x41 and 70 or 0)-50*facing}
        elseif not count or n>=count then break end
    end
    table.sort(targets,function(a,b) if a.score==b.score then return a.id<b.id end; return a.score<b.score end)
    local index=1
    for n,target in ipairs(targets) do
        if target.id==pad.autoTargetId and (pad.manualNearbyId==target.id or target.score<targets[1].score+15) then index=n end
    end
    local shift=press(4,now) and -1 or press(8,now) and 1 or 0
    if #targets>0 and shift~=0 then
        index=((index-1+shift)%#targets)+1; pad.manualNearbyId=targets[index].id
    end
    local target=targets[index]
    pad.autoTargetId=target and target.id or nil
    displayTarget(target,width,height)
end
local function targetNavigation(now,lx,ly,magnitude,width,height)
    local mode=pad.targetMode=='spell' and 2 or pad.targetMode=='talk' and 3 or 1
    local targets={}
    for n=1,128 do
        local valid,id,x,y,kind,distance,count=pad.native(6,n,mode)
        if valid==1 then targets[#targets+1]={id=id,x=x,y=y,kind=kind,distance=distance,mode=mode}
        elseif not count or n>=count then break end
    end
    local index=1
    for n,target in ipairs(targets) do if target.id==pad.targetId then index=n end end
    local shift=0
    if press(4,now) or press(1,now) then shift=-1 end
    if press(8,now) or press(2,now) then shift=1 end
    local direction=0
    if magnitude>0.35 then
        direction=math.abs(lx)>=math.abs(ly) and (lx>0 and 1 or -1) or (ly>0 and -1 or 1)
    end
    if direction==0 then pad.targetAnalogDirection=nil
    elseif direction~=pad.targetAnalogDirection then
        pad.targetAnalogDirection=direction; pad.targetRepeat=now+340; shift=direction
    elseif now>=(pad.targetRepeat or now) then pad.targetRepeat=now+110; shift=direction end
    if #targets>0 and shift~=0 then index=((index-1+shift)%#targets)+1 end
    local target=targets[index]
    pad.targetId=target and target.id or nil
    displayTarget(target,width,height)
end

function pad.ContextSlotSelected(index)
    return menu('WORLD_CONTEXT_BAR') and pad.contextIndex==index
end
local function contextNavigation(now,lx,ly,magnitude,width,height)
    local choices={}
    for index=0,math.min(12,buttonArray:GetNumberOccupiedSlots())-1 do
        local enabled=buttonArray:GetButtonEnabled(index)
        if enabled and enabled~=0 then choices[#choices+1]=index end
    end
    local position=1
    for n,index in ipairs(choices) do if index==pad.contextIndex then position=n end end
    local shift=0
    if press(4,now) or press(1,now) then shift=-1 end
    if press(8,now) or press(2,now) then shift=1 end
    local direction=0
    if magnitude>0.35 then
        if math.abs(lx)>=math.abs(ly) then direction=lx>0 and 1 or -1
        else direction=ly>0 and -1 or 1 end
    end
    if direction==0 then pad.contextAnalogDirection=nil
    elseif direction~=pad.contextAnalogDirection then
        pad.contextAnalogDirection=direction; pad.contextAnalogRepeat=now+340; shift=direction
    elseif now>=(pad.contextAnalogRepeat or now) then
        pad.contextAnalogRepeat=now+110; shift=direction
    end
    if shift~=0 then position=((position-1+shift)%math.max(1,#choices))+1 end
    pad.contextIndex=choices[position]
    if not pad.contextFocused and pad.contextIndex~=nil and Infinity_GetAreaScreen and Infinity_GetScreenSize then
        local x,y,w,h=Infinity_GetAreaScreen('PST_CONTEXT_SLOT_'..pad.contextIndex)
        local sw,sh=Infinity_GetScreenSize()
        if x and y and w and h and w>0 and h>0 and sw and sh and sw>0 and sh>0 then
            pad.cursorX,pad.cursorY=(x+w/2)*width/sw,(y+h/2)*height/sh
            pad.native(1,math.floor(pad.cursorX+0.5),math.floor(pad.cursorY+0.5))
            pad.contextFocused=true
        end
    end
    if edge(4096) and pad.contextIndex~=nil then
        pad.native(12,100,pad.contextIndex,contextBarState or -1)
        pad.pendingContextIndex=pad.contextIndex
        pad.pendingContextState=contextBarState
        pad.pendingWorld='context'; pad.pendingWorldAt=now; key(13)
    end
end

function pad.DispatchBack()
    if not pad.pendingBack then return end
    pad.pendingBack = nil
    local returnContext=pad.cancelledTargetContext or ((pad.targetMode or pad.activation) and pad.lastTargetContextState)
    pad.cancelledTargetContext=nil
    pad.activation,pad.pendingTarget,pad.targetMode,pad.requestedTargetMode=nil,nil,nil,nil
    -- Use the same cancellation as the stock button, including option rollback
    -- and popup callbacks. Do not jump past child dialogs to the world engine.
    if menu('POPUP_THREEBUTTON') and Popup3Button then
        for _, side in ipairs({'left','mid','right'}) do
            if Popup3Button[side..'Text']=='CANCEL_BUTTON' then
                Infinity_PopMenu('POPUP_THREEBUTTON')
                if Popup3Button[side..'Func'] then Popup3Button[side..'Func']() end
                return
            end
        end
        return -- No cancel choice: B must not pick Save/Quit or another action.
    end
    if menu('WORLD_MAP') then worldMapScreen:StopWorldMap(false); return end
    for _, name in ipairs({'WORLD_HELP','WORLD_HELP_TABLET','INVENTORY_HELP','CHARACTER_HELP',
        'SPELLS_HELP','MAP_HELP','WORLD_HELP_DESCRIPTION'}) do
        if menu(name) then Infinity_PopMenu(name); return end
    end
    for _, handler in ipairs(pad.stockBackHandlers or {}) do
        if menu(handler[1]) then handler[2](); return end
    end
    -- Regular UI Escape bindings get first refusal. This is the fallback for
    -- the game's world overlays, which otherwise deliberately ignore Escape.
    for _, name in ipairs({'ITEM_DESCRIPTION','SPELL_DESCRIPTION','WORLD_HELP','WORLD_HELP_TABLET',
        'INVENTORY_HELP','CHARACTER_HELP','SPELLS_HELP','MAP_HELP','WORLD_HELP_DESCRIPTION','WORLD_FORMATION'}) do
        if menu(name) then Infinity_PopMenu(name); return end
    end
    if menu('WORLD_CONTAINER') then worldScreen:StopContainer(); return end
    if menu('WORLD_QUICKLOOT') then worldScreen:StopGroundItems(); return end
    if menu('WORLD_CONTEXT_BAR') then Infinity_PopMenu('WORLD_CONTEXT_BAR'); game:CancelCurrentAction(); return end
    for _, name in ipairs({'STORE_CHOOSER','STORE_BUYSELL','STORE_IDENTIFY','STORE_ROOMS','STORE_HEALING'}) do
        if menu(name) then storeScreen:OnMainDoneButtonClick(); return end
    end
    if returnContext and e:GetActiveEngine()==worldScreen then
        game:CancelCurrentAction(); actionbarResetState(); showContextMenu(returnContext); return
    end
    if e:GetActiveEngine() == worldScreen then game:CancelCurrentAction(); actionbarResetState()
    else e:GetActiveEngine():SelectEngine(worldScreen) end
end

function pad.JournalScroll(top, height, contentHeight, panel)
    local delta = pad.journalScrollDelta and pad.journalScrollDelta[panel]
    if delta then
        pad.journalScrollDelta[panel] = nil
        if panel == 'entries' then journalScrollToBottom = nil end
        return clamp(top + delta, math.min(0,height-contentHeight), 0)
    end
    if panel == 'entries' then return journalScroll(top,height,contentHeight) end
end
function PSTPadScrollEntries(top,height,contentHeight) return pad.JournalScroll(top,height,contentHeight,'entries') end
function PSTPadScrollQuests(top,height,contentHeight) return pad.JournalScroll(top,height,contentHeight,'quests') end
function PSTPadScrollBestiary(top,height,contentHeight) return pad.JournalScroll(top,height,contentHeight,'bestiary') end

local function journalNavigation(now)
    if press(4,now) or press(8,now) then
        local modes = {const.JOURNAL_MODE_QUESTS,const.JOURNAL_MODE_JOURNAL,const.JOURNAL_MODE_BESTIARY}
        local index=1; for n,value in ipairs(modes) do if value==journalMode then index=n end end
        local offset=down(pad.buttons,8) and 1 or -1
        journalMode=modes[((index-1+offset)%#modes)+1]
        pad.journalScrollDelta={}
    end
    if edge(16384) then
        if journalMode==const.JOURNAL_MODE_QUESTS then
            currentQuestType=currentQuestType==const.ENTRY_TYPE_INPROGRESS and const.ENTRY_TYPE_COMPLETE or const.ENTRY_TYPE_INPROGRESS
            selectedQuest=nil
        elseif journalMode==const.JOURNAL_MODE_BESTIARY then
            currentBestiaryClass=currentBestiaryClass==const.BESTIARY_CLASS_PC and const.BESTIARY_CLASS_NPC or const.BESTIARY_CLASS_PC
            selectedBestiaryCreature=nil
        end
    end
    local up,lower=press(1,now),press(2,now)
    if up or lower then
        local choices,selected,panel={},nil,'entries'
        if journalMode==const.JOURNAL_MODE_QUESTS then
            panel='quests'; selected=selectedQuest
            for n in ipairs(quests or {}) do if questEnabled(n) then choices[#choices+1]=n end end
        elseif journalMode==const.JOURNAL_MODE_BESTIARY then
            panel='bestiary'; selected=selectedBestiaryCreature
            for n in ipairs(bestiary or {}) do if getBestiaryEnabled(n) then choices[#choices+1]=n end end
        end
        if #choices>0 then
            local index=0; for n,value in ipairs(choices) do if value==selected then index=n end end
            index=clamp(index+(lower and 1 or -1),1,#choices)
            if panel=='quests' then selectedQuest=choices[index]; setQuestViewed(selectedQuest)
            else selectedBestiaryCreature=choices[index] end
        end
        pad.journalScrollDelta=pad.journalScrollDelta or {}
        pad.journalScrollDelta[panel]=(up and 1 or -1)*60
    end
end

-- Names are assigned to stock controls by the installer. Resolve their live
-- screen bounds rather than guessing coordinates from a particular resolution.
pad.navigationStack={}
pad.navigationFocus={}
pad.navigationInitial={}
pad.navigationScroll={}
pad.navigationScrollRequest={}
-- equipment.group0 is the first main inventory cell. equipment.personal0
-- belongs to the separate Quick Item row despite its internal "personal" name.
pad.inventoryInitialSlot='slot_inv_30'
function pad.MenuOpened(name)
    pad.MenuClosed(name)
    pad.navigationStack[#pad.navigationStack+1]=name
    pad.navigationInitial[name]=true
    pad.navigationFocus[name]=nil
    if name=='QuitMenu' or name:match('^POPUP_') then
        pad.confirmNeedsRelease=down(pad.buttons,4096)
    end
    if name=='INVENTORY' then pad.inventoryFocused=false end
    if name=='POPUP_REQUESTER' and pad.pendingSplit then
        pad.quantityOwner=pad.pendingSplit; pad.pendingSplit=nil
    end
end
function pad.MenuClosed(name)
    for index=#pad.navigationStack,1,-1 do
        if pad.navigationStack[index]==name then table.remove(pad.navigationStack,index) end
    end
    if name=='INVENTORY' then pad.inventoryFocused=false end
    if name=='POPUP_REQUESTER' then pad.pendingQuantity=nil; pad.quantityOwner=nil end
end
function pad.MenuListScroll(name,top,height,contentHeight,original)
    local requested=pad.navigationScrollRequest[name]
    pad.navigationScrollRequest[name]=nil
    local result
    if requested and pad.controllerActive then result=clamp(top+requested,math.min(0,height-contentHeight),0)
    elseif original then result=original(top,height,contentHeight) end
    pad.navigationScroll[name]={top=result or top,height=height,contentHeight=contentHeight}
    return result
end
local function navigationMenu()
    local specs=pad.navigationMenus
    if not specs then return end
    for index=#pad.navigationStack,1,-1 do
        local name=pad.navigationStack[index]
        if specs[name] and menu(name) then return name=='SPELLS_X' and menu('SPELLS') and 'SPELLS' or name end
    end
    -- Usually only needed when switching to Xbox after a menu was already open.
    for name in pairs(specs) do if menu(name) then return name end end
end
function pad.NavigationNodes(name,width,height)
    local nodes={}
    if not Infinity_GetAreaScreen or not Infinity_GetScreenSize then return nodes end
    local sw,sh=Infinity_GetScreenSize()
    if not sw or not sh or sw<=0 or sh<=0 then return nodes end
    local sx,sy=width/sw,height/sh
    local function add(spec,id,x,y,w,h,row,column)
        if w<=0 or h<=0 or x+w<=0 or y+h<=0 or x>=sw or y>=sh then return end
        nodes[#nodes+1]={id=id,name=spec.name,spec=spec,x=(x+w/2)*sx,y=(y+h/2)*sy,
            left=math.max(0,x*sx),top=math.max(0,y*sy),right=math.min(width,(x+w)*sx),
            bottom=math.min(height,(y+h)*sy),row=row,column=column}
    end
    local function collect(specs)
        for _,spec in ipairs(specs or {}) do
            local ready,value=pcall(spec.ready)
            local ok,x,y,w,h=pcall(Infinity_GetAreaScreen,spec.name)
            if ready and value and value~=0 and ok and type(x)=='number' and type(y)=='number'
                and type(w)=='number' and type(h)=='number' and w>0 and h>0 then
                if spec.kind=='list' then
                    local rowOK,rowHeight=pcall(spec.rowHeight)
                    local rowsOK,rows=pcall(spec.rows or function() return 0 end)
                    if rowOK and rowsOK and type(rowHeight)=='number' and rowHeight>0 and rows>0 then
                        local scroll=pad.navigationScroll[spec.name] or {top=0}
                        local first=math.max(1,math.floor(-scroll.top/rowHeight)+1)
                        local last=math.min(rows,math.ceil((h-scroll.top)/rowHeight))
                        for row=first,last do
                            local rowY=y+scroll.top+(row-1)*rowHeight
                            local top,bottom=math.max(y,rowY),math.min(y+h,rowY+rowHeight)
                            local offset=0
                            for column,percent in ipairs(spec.columns or {100}) do
                                local colWidth=w*percent/100
                                if bottom-top>=rowHeight/2 then
                                    add(spec,spec.name..':'..row..':'..column,x+offset,top,colWidth,bottom-top,row,column)
                                end
                                offset=offset+colWidth
                            end
                        end
                    end
                else add(spec,spec.name,x,y,w,h) end
            end
        end
    end
    collect(pad.navigationMenus[name])
    if name=='SPELLS' and menu('SPELLS_X') then collect(pad.navigationMenus.SPELLS_X) end
    return nodes
end
local function focusNode(name,node)
    pad.navigationFocus[name]=node.id
    pad.cursorX,pad.cursorY=node.x,node.y
    pad.native(1,math.floor(node.x+0.5),math.floor(node.y+0.5))
end

function pad.QueueSplitStack(width,height)
    if navigationMenu()~='INVENTORY' or pad.pendingSplit then return false end
    for _,node in ipairs(pad.NavigationNodes('INVENTORY',width,height)) do
        if node.spec.inventorySlot and pad.cursorX>=node.left and pad.cursorX<node.right
            and pad.cursorY>=node.top and pad.cursorY<node.bottom then
            local character=characters and characters[id]
            local slot=character and character.equipment and character.equipment[node.spec.inventorySlot]
            local item=slot and slot.item
            if item and tonumber(item.count) and tonumber(item.count)>1 and (not item.isBag or item.isBag==0) then
                pad.pendingSplit={character=id,slot=node.spec.inventorySlot,slotId=slot.id,res=item.res,count=tonumber(item.count),at=pad.lastTick,width=width,height=height}
                -- Dispatch from a dedicated inventory button's queued click.
                -- Stock Return and simulated double-click timing proved
                -- unreliable in the native inventory slot implementation.
                local ok,x,y,w,h=pcall(Infinity_GetAreaScreen,'PST_SPLIT_DISPATCH')
                local sw,sh=Infinity_GetScreenSize()
                if ok and x and y and w and h and w>0 and h>0 and sw>0 and sh>0 then
                    pad.native(12,301,slot.id,tonumber(item.count))
                    pad.native(4,math.floor((x+w/2)*width/sw+0.5),math.floor((y+h/2)*height/sh+0.5),1)
                    return true
                end
                pad.pendingSplit=nil
                break
            end
            pad.native(12,304,slot and slot.id or -1,item and tonumber(item.count) or -1)
            break
        end
    end
    pad.actionNotice='Select a stack with more than one item'; pad.actionNoticeUntil=pad.lastTick+2000
    return false
end
local function splitOwnerValid(owner)
    local character=owner and characters and characters[owner.character]
    local slot=character and character.equipment and character.equipment[owner.slot]
    local item=slot and slot.item
    return owner and id==owner.character and slot and slot.id==owner.slotId and item
        and item.res==owner.res and tonumber(item.count)==owner.count
end
function pad.DispatchSplitStack()
    local pending=pad.pendingSplit; pad.pendingSplit=nil
    if not pending or not pad.controllerActive or navigationMenu()~='INVENTORY'
        or pad.lastTick-pending.at>250 or not splitOwnerValid(pending) then return end
    showItemAmountRequester(pending.slot)
    local opened=menu('POPUP_REQUESTER')
    if opened then
        pad.quantityOwner=pending
        for _,node in ipairs(pad.NavigationNodes('POPUP_REQUESTER',pending.width,pending.height)) do
            if node.spec.quantityDone then focusNode('POPUP_REQUESTER',node); break end
        end
    end
    pad.native(12,302,opened and 1 or 0,pending.count)
end
function pad.ConfirmQuantity(width,height)
    if pad.quantityOwner and not splitOwnerValid(pad.quantityOwner) then
        pad.actionNotice='Inventory changed; choose the stack again'; pad.actionNoticeUntil=pad.lastTick+2000
        return
    end
    local count=tonumber(itemRequestAmt); local maximum=tonumber(requester and requester.requesterMax)
    if count and maximum and count>=1 and count<=maximum then
        for _,node in ipairs(pad.NavigationNodes('POPUP_REQUESTER',width,height)) do
            if node.spec.quantityDone then
                if Infinity_FocusTextEdit then Infinity_FocusTextEdit('') end
                pad.native(4,math.floor(node.x+0.5),math.floor(node.y+0.5),1)
                return
            end
        end
    end
end
function pad.QuantityNavigation(now,width,height)
    local maximum=tonumber(requester and requester.requesterMax)
    if not maximum or maximum<1 then return false end
    local amount=clamp(math.floor(tonumber(itemRequestAmt) or 1),1,maximum)
    local increase=press(1,now) or press(8,now)
    local decrease=press(2,now) or press(4,now)
    itemRequestAmt=clamp(amount+(increase and 1 or 0)-(decrease and 1 or 0),1,maximum)
    if edge(4096) and not pad.confirmNeedsRelease and not pad.pendingQuantity then
        pad.ConfirmQuantity(width,height)
    elseif edge(8192) then
        if Infinity_FocusTextEdit then Infinity_FocusTextEdit('') end
        pad.pendingBack=now; key(27)
    end
    pad.status='Xbox | D-pad: amount  A: confirm  B: cancel | '..itemRequestAmt..'/'..maximum
    return true
end
function pad.MenuNavigation(now,width,height,moved,allowDpad)
    if not pad.controllerActive then return false end
    if not menu('INVENTORY') then pad.inventoryFocused=false end
    local name=navigationMenu()
    if not name then pad.navigationCurrent=nil; return false end
    local nodes=pad.NavigationNodes(name,width,height)
    if #nodes==0 then return false end
    local focused,nearest,distance
    local wanted=pad.navigationFocus[name]
    if name=='INVENTORY' and not pad.inventoryFocused then wanted=pad.inventoryInitialSlot end
    local initializing=pad.navigationInitial[name] or (pad.navigationCurrent~=name and not wanted)
    if initializing then
        local first=nodes[1]
        for _,node in ipairs(nodes) do
            if node.spec.initial then first=node; break end
            if (node.spec.kind=='slot' or node.spec.spell) and not (first.spec.kind=='slot' or first.spec.spell) then first=node end
        end
        wanted=first.id
    end
    local pending=pad.navigationPending and pad.navigationPending.menu==name
    if pending then wanted=pad.navigationPending.id end
    for _,node in ipairs(nodes) do
        if node.id==wanted then focused=node end
        local dx,dy=node.x-pad.cursorX,node.y-pad.cursorY
        local d=dx*dx+dy*dy
        if distance==nil or d<distance then nearest,distance=node,d end
    end
    local changed=pad.navigationCurrent~=name
    if focused and (changed or pending or initializing or (name=='INVENTORY' and not pad.inventoryFocused)) then
        focusNode(name,focused); pad.navigationPending=nil
    elseif changed then focusNode(name,nearest); focused=nearest end
    pad.navigationCurrent=name
    pad.navigationInitial[name]=nil
    if name=='INVENTORY' and focused then pad.inventoryFocused=true end
    if moved then
        -- A stick is free aim; the next D-pad step starts from the nearest slot.
        focused=nearest; pad.navigationFocus[name]=nil
    end
    focused=focused or nearest
    if not allowDpad then return true end
    local direction,dx,dy
    if press(1,now) then direction,dx,dy='up',0,-1
    elseif press(2,now) then direction,dx,dy='down',0,1
    elseif press(4,now) then direction,dx,dy='left',-1,0
    elseif press(8,now) then direction,dx,dy='right',1,0 end
    if not direction then return true end
    -- Scroll a focused list row into view before considering an outside button.
    if focused.row and dy~=0 then
        local nextRow=focused.row+dy
        local ok,rows=pcall(focused.spec.rows)
        if ok and nextRow>=1 and nextRow<=rows then
            local id=focused.name..':'..nextRow..':'..focused.column
            for _,node in ipairs(nodes) do if node.id==id then focusNode(name,node); return true end end
            local rowOK,rowHeight=pcall(focused.spec.rowHeight)
            if rowOK then
                pad.navigationScrollRequest[focused.name]=-dy*rowHeight
                pad.navigationPending={menu=name,id=id}
                return true
            end
        end
    end
    local best,score
    local hint=focused.spec[direction]
    for _,node in ipairs(nodes) do
        if hint and node.name==hint then best=node; break end
        if node.id~=focused.id then
            local vx,vy=node.x-focused.x,node.y-focused.y
            local forward=vx*dx+vy*dy
            local cross=math.abs(vx*dy-vy*dx)
            -- Favor the same row/column and then the nearest forward control.
            local candidate=forward+cross*3+cross*cross/math.max(1,forward)
            if forward>2 and (not score or candidate<score) then best,score=node,candidate end
        end
    end
    if best then focusNode(name,best)
    else focusNode(name,focused) end
    return true
end

function pad.Step()
    if not pad.native then return 'Xbox mod unavailable: ' .. tostring(pad.error) end
    local connected, buttons, rawLX, rawLY, rawRX, rawRY, lt, rt,
        mx, my, width, height, now, focused, playerX, playerY, positionValid, selectedCount, physicalClicks, moviePlaying = pad.native(0)
    if now - pad.lastTick < 16 then return pad.status end
    local elapsed = pad.lastTick == 0 and 0.016 or clamp((now - pad.lastTick) / 1000, 0, 0.05)
    pad.lastTick = now
    if pad.pendingBack and now-pad.pendingBack>250 then pad.pendingBack=nil end
    if pad.pendingSplit and now-pad.pendingSplit.at>250 then
        pad.native(12,303,pad.pendingSplit.slotId,pad.pendingSplit.count)
        pad.pendingSplit=nil
    end
    if pad.pendingQuantity and now-pad.pendingQuantity.at>250 then pad.pendingQuantity=nil end
    if pad.pendingWorld and now-(pad.pendingWorldAt or now)>250 then
        pad.native(12,130,now-(pad.pendingWorldAt or now),game:GetState()); pad.pendingWorld=nil
    end
    pad.previousButtons, pad.buttons = pad.buttons, buttons
    physicalClicks=physicalClicks or 0
    local mouseClicked=pad.physicalClicks~=nil and physicalClicks~=pad.physicalClicks
    pad.physicalClicks=physicalClicks
    local previousLT,previousRT=pad.previousLT or 0,pad.previousRT or 0
    pad.previousLT,pad.previousRT=lt,rt
    -- Hysteresis prevents tiny fluctuations near the threshold from stopping
    -- and restarting the route. A neutral stick still stops immediately.
    local lx, ly, lm = axis(rawLX, rawLY, pad.moving and 0.13 or 0.19)
    local rx, ry, rm = axis(rawRX, rawRY, 0.20)
    if connected == 0 or focused == 0 then
        if mouseClicked then releaseController() end
        pad.zoomDirection,pad.zoomTriggerHeld,pad.zoomRepeat=nil,nil,nil
        pad.nearby,pad.pendingTarget=nil,nil
        pad.activation,pad.targetMode,pad.requestedTargetMode=nil,nil,nil
        pad.worldCursorHidden=false; pad.native(5,0)
        pad.pendingDialog = nil
        pad.pendingBack, pad.pendingWorld = nil, nil
        pad.pendingSplit,pad.pendingQuantity=nil,nil
        stopMovement()
        releaseHighlights()
        closeRadial()
        pad.armed = false
        pad.status = connected == 0 and 'Xbox disconnected' or 'Xbox idle — focus the game'
        return pad.status
    end
    if mouseClicked then
        releaseController()
        pad.native(12,310,0,physicalClicks)
        pad.status='PC controls | press a controller button to switch'
        return pad.status
    end
    if moviePlaying==1 then
        -- Native movie input runs before Lua/UI. Do not also click the stale
        -- menu cursor, and require A release before accepting a menu action.
        if down(buttons,4096) then pad.controllerActive=true end
        pad.armed=false; pad.status='Xbox | A: skip movie'
        return pad.status
    end
    if not pad.controllerActive then
        if e:GetActiveEngine()==worldScreen and not menu('WORLD_DIALOG') and not navigationMenu()
            and not Infinity_GetInCutsceneMode() and Infinity_TextEditHasFocus()==0 and fullActionbarClickable()
            and width>0 and height>0 and (mx<=2 or my<=2 or mx>=width-3 or my>=height-3)
            and worldScreen:GetScrollLocked() then pad.native(19,2) end
        local buttonPressed=false
        for _,bit in ipairs({1,2,4,8,16,32,64,128,256,512,4096,8192,16384,32768}) do
            if edge(bit) then buttonPressed=true end
        end
        if lt>=100 and previousLT<100 or rt>=100 and previousRT<100 then buttonPressed=true end
        if buttonPressed then
            pad.controllerActive=true; pad.drive=true; pad.runEnabled=runSetting()
            pad.armed=false; pad.cursorX,pad.cursorY=mx,my
            pad.native(12,310,1,physicalClicks)
            pad.status='Xbox active | release controls to begin'
        else pad.status='PC controls | press a controller button to switch' end
        return pad.status
    end
    if not pad.armed then
        if buttons == 0 and lm == 0 and rm == 0 and lt < 30 and rt < 30 then pad.armed = true end
        pad.status = 'Xbox connected — release controls to begin'
        return pad.status
    end
    if width <= 0 or height <= 0 then return pad.status end
    if not down(buttons,4096) then pad.confirmNeedsRelease=false end
    if navigationMenu()=='POPUP_REQUESTER' then
        pad.navigationCurrent='POPUP_REQUESTER'
        stopMovement(); releaseHighlights(); pad.worldCursorHidden=false; pad.native(5,0)
        if pad.QuantityNavigation(now,width,height) then return pad.status end
    end
    local inDialog = menu('WORLD_DIALOG')
    local inJournal = menu('JOURNAL')
    local inContext = menu('WORLD_CONTEXT_BAR')
    if not inContext then pad.contextIndex=nil; pad.contextAnalogDirection=nil; pad.contextFocused=false end
    if not inDialog then pad.pendingDialog = nil end
    local inWorld = e:GetActiveEngine() == worldScreen and not inDialog
        and not menu('WORLD_CONTAINER') and not Infinity_GetInCutsceneMode() and fullActionbarClickable()
    -- This binding returns a number; Lua treats numeric zero as true.
    local editing = Infinity_TextEditHasFocus() ~= 0
    if editing then
        stopMovement()
        inWorld, inDialog = false, false
    end
    -- Controller walk/run is a persistent choice, rather than a temporary
    -- AlwaysRun=true override around each route. Dialogs cannot change it.
    if pad.runEnabled==nil then pad.runEnabled=runSetting() end
    if inWorld and runSetting()~=pad.runEnabled then game:SetAlwaysRun(pad.runEnabled) end
    local talking = inWorld and game:GetState()==2 and game:GetIconIndex()==18
    local navigatingWorldMenu = inContext or navigationMenu()~=nil
        or menu('WORLD_FORMATION') or menu('WORLD_QUICKLOOT') or menu('WORLD_CONTAINER')
    if lm==0 then pad.requireMoveNeutral=false end
    if inWorld and pad.drive and not pad.radial and not navigatingWorldMenu and game:GetState()==0 and lm>0 then
        pad.facingX,pad.facingY=lx/lm,-ly/lm; pad.manualNearbyId=nil
    end
    pad.worldCursorHidden=inWorld and pad.drive and not navigatingWorldMenu
    pad.native(5,pad.worldCursorHidden and 1 or 0)
    if inWorld and not navigatingWorldMenu and game:GetState()~=0 and not pad.activation then
        local icon=game:GetIconIndex()
        pad.targetMode=talking and 'talk' or (icon==12 or icon==16) and 'attack' or 'spell'
    else pad.targetMode=nil; pad.targetId=nil; pad.targetAnalogDirection=nil end
    if inWorld and game:GetState()==0 and not inContext and not pad.activation then pad.lastTargetContextState=nil end
    if pad.activation then
        local activation=pad.activation
        if edge(8192) then pad.cancelledTargetContext=pad.lastTargetContextState end
        if not inWorld or navigatingWorldMenu or edge(8192) or now>activation.deadline then
            pad.activation=nil
        elseif now>=activation.ready then
            local result=pad.native(8,activation.id,activation.mode)
            if result==2 then activation.ready=now+100
            else
                pad.activation=nil; pad.interactionHoldUntil=now+200
                if result~=1 then actionbarResetState() end
            end
        end
    end

    local justOpened = false
    if edge(32768) and inWorld and not navigatingWorldMenu then
        stopMovement()
        if pad.radial then closeRadial()
        else
            pad.radial, pad.radialIndex = true, 1
            justOpened = true
            if not worldScreen:CheckIfPaused() then
                worldScreen:TogglePauseGame(true)
                pad.pausedForRadial = true
            end
        end
    end
    updateHighlights(lt,e:GetActiveEngine()==worldScreen and not inDialog and not editing
        and not Infinity_GetInCutsceneMode() and not navigatingWorldMenu and not pad.radial)
    if pad.radial then
        pad.zoomDirection,pad.zoomTriggerHeld,pad.zoomRepeat=nil,nil,nil
        pad.nearby=nil
        if not inWorld then closeRadial(); return pad.status end
        if lm > 0.35 then
            local angle = math.atan2(lx, ly)
            pad.radialIndex = (math.floor((angle + math.pi / 8) / (math.pi / 4)) % 8) + 1
        end
        if edge(256) or edge(512) then
            pad.radialPage=pad.radialPage==1 and 2 or 1
            pad.radialEntries=pad.radialPages[pad.radialPage]
        end
        if press(2, now) or press(4, now) then pad.radialIndex = (pad.radialIndex % 8) + 1 end
        if press(1, now) or press(8, now) then pad.radialIndex = ((pad.radialIndex + 6) % 8) + 1 end
        if edge(8192) or (edge(32768) and not justOpened) then closeRadial()
        elseif edge(4096) then
            local action = pad.radialEntries[pad.radialIndex][2]
            closeRadial()
            if type(action)=='string' then pad.pendingWorld=action; pad.pendingWorldAt=now; key(13)
            else key(action) end
        end
        pad.status = 'Xbox | actions '..pad.radialPage..'/2 | LB/RB: page  stick / D-pad: choose  A: open  B: cancel'
        return pad.status
    end

    -- World shortcuts use fresh edges. Menus, dialogue and target selection
    -- retain all four directions for navigation.
    if inWorld and not navigatingWorldMenu and not pad.targetMode and not pad.activation
        and not pad.pendingWorld and game:GetState()==0 and (edge(1) or edge(2)) then
        stopMovement()
        pad.pendingWorld=edge(1) and 'attack' or 'abilities'; pad.pendingWorldAt=now
        key(13)
        pad.status=edge(1) and 'Xbox | opening Attack' or 'Xbox | opening Special Ability'
        return pad.status
    end

    -- RT modifies the right stick only in the world. Menus retain their slow
    -- cursor; no zoom while a dialog, context panel or interaction is pending.
    local zoomWorld=inWorld and not navigatingWorldMenu and not editing
        and not pad.activation and not pad.pendingWorld
    pad.zoomTriggerHeld=zoomWorld and (rt>=100 or (pad.zoomTriggerHeld and rt>60))
    local zoomDirection=0
    local zoomThreshold=pad.zoomDirection and 0.24 or 0.36
    if pad.zoomTriggerHeld and math.abs(rawRY)/32768>zoomThreshold and math.abs(rawRY)>=math.abs(rawRX) then
        zoomDirection=rawRY>0 and 1 or -1
    end
    if zoomDirection==0 then pad.zoomDirection,pad.zoomRepeat=nil,nil
    elseif zoomDirection~=pad.zoomDirection then
        pad.native(16,zoomDirection); pad.zoomDirection=zoomDirection; pad.zoomRepeat=now+220
    elseif now>=(pad.zoomRepeat or now) then
        pad.native(16,zoomDirection); pad.zoomRepeat=now+150
    end

    local cameraPanning=inWorld and pad.drive and not navigatingWorldMenu and not editing
        and not talking and not pad.targetMode and not pad.activation and not pad.pendingWorld
        and game:GetState()==0 and rt<=60 and rm>0
    if cameraPanning then
        -- Manual pan explicitly releases follow, without the stock selected-ID
        -- toggle (which can relock another actor after a selection change).
        if pad.cameraLockedByMod or worldScreen:GetScrollLocked() then
            pad.native(19,2)
            pad.cameraLockedByMod=false
        end
        pad.cameraRemainderX=(pad.cameraRemainderX or 0)+rx*620*elapsed
        pad.cameraRemainderY=(pad.cameraRemainderY or 0)-ry*620*elapsed
        local dx=math.modf(pad.cameraRemainderX)
        local dy=math.modf(pad.cameraRemainderY)
        pad.cameraRemainderX,pad.cameraRemainderY=pad.cameraRemainderX-dx,pad.cameraRemainderY-dy
        if dx~=0 or dy~=0 then pad.native(18,dx,dy) end
    else pad.cameraRemainderX,pad.cameraRemainderY=nil,nil end

    if edge(64) and inWorld then
        pad.runEnabled=not pad.runEnabled; game:SetAlwaysRun(pad.runEnabled)
        pad.moveDirectionX,pad.moveDirectionY=nil,nil
        resetSteeringFilter()
        pad.native(12,311,pad.runEnabled and 1 or 0,0)
    end
    if edge(128) and inWorld then
        stopMovement(); pad.pendingWorld='all'; pad.pendingWorldAt=now; key(13)
    end
    -- Xbox Back/View is distinct from B (cancel) and Start (pause).
    if edge(32) and inWorld then
        stopMovement(); pad.pendingWorld='options'; pad.pendingWorldAt=now; key(13)
    end
    if edge(16) and inWorld then stopMovement(); key(32) end
    if edge(512) and not inDialog then
        stopMovement()
        pad.slot = (pad.slot + 1) % math.max(1, Infinity_GetNumCharacters()); key(49 + pad.slot)
    end
    if edge(256) and not inDialog then
        stopMovement()
        pad.slot = (pad.slot + math.max(1, Infinity_GetNumCharacters()) - 1) % math.max(1, Infinity_GetNumCharacters()); key(49 + pad.slot)
    end

    if inDialog then
        stopMovement()
        local choices = dialogRows()
        pad.dialogIndex = clamp(pad.dialogIndex, 1, math.max(1, #choices))
        if press(2, now) then pad.dialogIndex = math.min(#choices, pad.dialogIndex + 1) end
        if press(1, now) then pad.dialogIndex = math.max(1, pad.dialogIndex - 1) end
        local row = choices[pad.dialogIndex]
        if row then
            glowTest = row
            worldPlayerDialogSelection = row
        end
        if edge(4096) and not pad.pendingDialog then
            if dialogViewMode or #(dialogOverflowTable or {}) > 0 or not row then
                pad.pendingDialog = { continue = true }
            else
                local entry = dialogTable[row]
                pad.pendingDialog = { entry = entry, marker = entry.marker }
            end
            key(13)
            pad.dialogIndex = 1
        end
    end

    local cx, cy, magnitude = rx, ry, rm
    if not inWorld or not pad.drive or (navigatingWorldMenu and not inContext) then
        if lm > rm then cx, cy, magnitude = lx, ly, lm end
    end
    -- In the action bar LS selects slots; RS retains optional fine cursor aim.
    if inContext then cx,cy,magnitude=rx,ry,rm end
    if inWorld and pad.drive and not navigatingWorldMenu then cx,cy,magnitude=0,0,0 end
    if zoomDirection~=0 then cx,cy,magnitude=0,0,0 end
    -- Manual pointer aim retains A's ordinary click. Once LS drives again,
    -- proximity takes over; resting RS must not drag the drive cursor around.
    if magnitude>0 or (rt>60 and not zoomWorld) then pad.manualAimUntil=now+750 end
    if inWorld and pad.drive and not talking and lm>0 and rm==0 then pad.manualAimUntil=nil end
    updateNearby(inWorld and pad.drive and not talking and not navigatingWorldMenu
        and game:GetState()==0 and not worldScreen:CheckIfPaused()
        and not pad.activation and not pad.pendingWorld and now>=(pad.interactionHoldUntil or 0)
        and now>=(pad.manualAimUntil or 0),width,height,playerX,playerY,now)
    if pad.targetMode and not pad.activation then targetNavigation(now,lx,ly,lm,width,height) end
    if magnitude>0 and pad.driveCursorHidden then stopMovement(); mx,my=pad.cursorX,pad.cursorY end
    if magnitude > 0 then
        if pad.cursorX == nil or math.abs(mx - pad.cursorX) > 3 or math.abs(my - pad.cursorY) > 3 then
            pad.cursorX, pad.cursorY = mx, my
        end
        local uiScale = Infinity_GetINIValue('Graphics', 'Scale UI', 1) ~= 0 and math.min(width / 1024, height / 768) or 1
        local speed = 620 * uiScale * (rt > 60 and 0.28 or 1)
        pad.cursorX = clamp(pad.cursorX + cx * speed * elapsed, 0, width - 1)
        pad.cursorY = clamp(pad.cursorY - cy * speed * elapsed, 0, height - 1)
        pad.native(1, math.floor(pad.cursorX + 0.5), math.floor(pad.cursorY + 0.5))
    else pad.cursorX, pad.cursorY = mx, my end

    local activeNavigationMenu=navigationMenu()
    local journalRoot=inJournal and (not activeNavigationMenu or activeNavigationMenu=='JOURNAL')
    if journalRoot and not editing then journalNavigation(now) end
    if inContext and not editing then contextNavigation(now,lx,ly,lm,width,height) end
    local hasMenuNavigation=false
    if not inDialog then
        if not journalRoot and not inContext and not pad.targetMode and (not inWorld or navigatingWorldMenu) then
            hasMenuNavigation=pad.MenuNavigation(now,width,height,magnitude>0,true)
        end
        if edge(32768) and activeNavigationMenu=='INVENTORY' and not editing then
            pad.QueueSplitStack(width,height)
            return pad.status
        end
        if edge(4096) and not pad.confirmNeedsRelease and not inContext and not pad.activation then
            stopMovement()
            if pad.nearby then
                pad.native(12,101,pad.nearby.id,game:GetState())
                pad.nearby.state,pad.nearby.icon=game:GetState(),game:GetIconIndex()
                pad.pendingTarget=pad.nearby; pad.pendingWorld=pad.targetMode and 'target' or 'interact'; pad.pendingWorldAt=now; key(13)
            elseif not pad.targetMode and (not inWorld or not pad.drive or hasMenuNavigation) then pad.native(2, pad.cursorX or mx, pad.cursorY or my, 1) end
        end
        if edge(16384) and not inJournal then stopMovement(); pad.native(2, pad.cursorX or mx, pad.cursorY or my, 3) end
        if edge(8192) then
            stopMovement(); pad.pendingBack=now; key(27)
        end
    end
    if inWorld and pad.drive and not talking and not navigatingWorldMenu
        and not pad.targetMode and not pad.activation and not pad.requireMoveNeutral
        and now>=(pad.interactionHoldUntil or 0)
        and not pad.pendingWorld and not edge(8192) and not edge(4096)
        and not worldScreen:CheckIfPaused() and lm > 0 then
        if not pad.driveCursorHidden then
            pad.driveCursorX,pad.driveCursorY=mx,my
            pad.native(5,1); pad.driveCursorHidden=true
        end
        if not cameraPanning and not pad.moving and not worldScreen:GetScrollLocked() then
            pad.cameraLockedByMod=pad.native(19,1)==1
            pad.moving=true
            -- Let the camera update for one frame, without the old 100ms delay.
            if pad.cameraLockedByMod then return pad.status end
        end
        local dx,dy,turned=movementDirection(lx,ly,lm,elapsed,now)
        local starting = pad.moveDirectionX == nil
        local remaining=pad.native(10)
        if now>=(pad.nextMovementLog or 0) then
            pad.nextMovementLog=now+500; pad.native(12,200,remaining,selectedCount)
        end
        local refresh=4000
        local turnDue=turned and now-pad.lastMove>=pad.moveTurnInterval
        local recovery=now-pad.lastMove>=refresh
        local extend=not starting and not turnDue and not recovery
            and remaining>=0 and remaining<=120 and now-pad.lastMove>=150
        local due=starting or turnDue or extend or recovery
        if positionValid ~= 0 and due and playerX >= 0 and playerY >= 0 then
            if game:GetState() == 0 then
                local _,issued=pad.native(9,math.floor(dx*10000),math.floor(-dy*10000),extend and 1 or 0)
                if issued~=0 then
                    pad.nativeDriving=true
                    pad.lastMove, pad.moving = now, true
                    pad.moveDirectionX, pad.moveDirectionY = dx, dy
                    pad.steerCandidateAt=nil
                end
            end
        end
    else stopMovement() end
    if inDialog then pad.status = 'Xbox | D-pad: answer  A: confirm | RS: cursor'
    elseif inContext then pad.status='Xbox | LS / D-pad: weapon / action  A: choose  B: close'
    elseif pad.activation then pad.status='Xbox | Activating selected target...  B: cancel'
    elseif pad.targetMode then pad.status='Xbox | LS / D-pad: target  A: '..pad.targetMode..'  B: cancel'
    elseif inWorld then
        pad.status = 'Xbox | LS: move  RS: camera  L3: '..(pad.runEnabled and 'RUN' or 'WALK')..'  A: interact  Y: actions  D-up: Attack  D-down: Ability  R3: all  RT+RS: zoom'
        if pad.drive and positionValid == 0 then pad.status = pad.status .. ' | position unavailable' end
    elseif inJournal then pad.status = 'Xbox | D-pad left/right: tab  up/down: entries / scroll  X: filter  B: close'
    elseif activeNavigationMenu=='INVENTORY' then pad.status='Xbox | D-pad: slots  A: move  X: inspect  Y: split stack  B: back'
    elseif editing then pad.status = 'Xbox | cursor + A: click  B: back | text entry uses keyboard'
    else pad.status = 'Xbox | D-pad: buttons / slots  sticks: cursor  A: choose  X: right-click  B: back' end
    if pad.actionNotice and now<(pad.actionNoticeUntil or 0) then pad.status=pad.status..' | '..pad.actionNotice end
    return pad.status
end

function pad.Tick()
    if pad.error then return 'Xbox mod unavailable: ' .. pad.error end
    local ok, result = pcall(pad.Step)
    if not ok then
        pad.error = tostring(result)
        pad.worldCursorHidden=false
        if pad.native then pcall(pad.native,5,0) end
        pcall(stopMovement)
        pcall(releaseHighlights)
        pcall(closeRadial)
        return 'Xbox mod paused: ' .. pad.error
    end
    return result
end

-- Screen changes already call this from their onOpen callbacks. Keep the driver
-- on the current UI stack; queued SDL input avoids re-entering screen switches.
local originalSetBackground = Infinity_SetBackground
Infinity_SetBackground = function(...)
    originalSetBackground(...)
    pcall(pad.EnsureDriver)
end
local originalSetOverlay=Infinity_SetOverlay
if originalSetOverlay then
    Infinity_SetOverlay=function(name)
        local previous=pad.overlayName
        originalSetOverlay(name)
        if previous then pad.MenuClosed(previous) end
        pad.overlayName=name
        if name then pad.MenuOpened(name); pad.EnsureDriver() end
    end
end

-- Pure invariants, run once when the mod is loaded; failures disable the mod.
local ok, testError = pcall(function()
    assert(not down(0, 4096) and down(4096, 4096) and down(4097, 4096))
    local x, y, magnitude = axis(0, 0, 0.24)
    assert(x == 0 and y == 0 and magnitude == 0)
    x, y, magnitude = axis(32767, 32767, 0.24)
    assert(magnitude <= 1 and math.abs(math.sqrt(x*x+y*y) - magnitude) < 0.00001)
    assert(clamp(-1, 0, 10) == 0 and clamp(11, 0, 10) == 10)
end)
if not ok then pad.error = 'Self-check: ' .. tostring(testError) end
