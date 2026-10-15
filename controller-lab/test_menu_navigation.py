"""Targeted focus/navigation checks in Lua 5.2; never sends live game input."""
import re
from pathlib import Path
from test_controls import runtime, root
from menu_navigation import build_navigation, child_blocks, own_properties, quoted_property
from ui_resources import named_menus, patch_cancel_bindings

source=(root/'backups'/'UI.menu.original').read_text(encoding='utf-8-sig')
patched,metadata=build_navigation(patch_cancel_bindings(source))
runtime.execute(metadata)  # Compile every generated availability/row closure.
g=runtime.globals()
specs=g.PSTController.navigationMenus
assert specs['INVENTORY'] and specs['OPTIONS_GAMEPLAY'] and specs['CHARACTER']
assert len(specs['SPELLS'])>=42, 'stock spell buttons without explicit action must be navigable'
assert specs['WORLD_DIALOG'] is None, 'dialog has its own semantic navigation'
names=set()
for menu_name,menu_body in named_menus(patched).items():
    for kind,_,_,body in child_blocks(menu_body):
        if kind in ('slot','slider','list','button','label','text'):
            name=quoted_property(own_properties(body),'name')
            if name and name.startswith('PST_NAV_'):
                assert name not in names
                names.add(name)
            if kind=='list':
                columns=[end for child_kind,_,end,_ in child_blocks(body) if child_kind=='column']
                for property_name in ('name','scrollbar'):
                    generated=re.search(r'\b'+property_name+r'\s+(?:func\s+)?[\'"]PST(?:_NAV_|PadListScroll_)',body)
                    if generated and columns:
                        assert generated.start()>max(columns), 'list properties must follow all column blocks'
for menu_name in ('INVENTORY','ESC_MENU','OPTIONS_GAMEPLAY','ITEM_DESCRIPTION','CHARACTER'):
    body=named_menus(patched)[menu_name]
    assert f"PSTController.MenuOpened('{menu_name}')" in body
    assert f"PSTController.MenuClosed('{menu_name}')" in body

# Stock static coordinates, including the main carried-item inventory grid.
runtime.execute('areas={}; logicalW=1024; logicalH=768')
for menu_body in named_menus(patched).values():
    for kind,_,_,body in child_blocks(menu_body):
        own=own_properties(body)
        name=quoted_property(own,'name')
        area=re.search(r'\barea\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\b',own)
        if name and area:
            g.areas[name]=runtime.table_from([int(area[i]) for i in range(1,5)])

runtime.execute('''
function Infinity_GetAreaScreen(name) return table.unpack(areas[name] or {}) end
function Infinity_GetScreenSize() return logicalW,logicalH end
characters={[1]={HP={current=20}}}; id=1
local pad=PSTController
pad.error=nil; pad.controllerActive=true; pad.armed=true; pad.navigationStack={}
pad.navigationFocus={}; pad.navigationScroll={}; pad.navigationScrollRequest={}
pad.navigationPending=nil; pad.navigationCurrent=nil; pad.inventoryFocused=false
pad.buttons=0; pad.previousButtons=0; pad.cursorX=300; pad.cursorY=300
menus={INVENTORY=true}; worldActive=false
pad.MenuOpened('INVENTORY')
assert(pad.MenuNavigation(100,1024,768,false,true))
assert(pad.navigationFocus.INVENTORY=='slot_inv_30','first main inventory cell, not Quick Item')
assert(pad.cursorX==499.5 and pad.cursorY==536.5,'first main inventory cell center')
local function nav(bit,width,height,moved)
    pad.previousButtons=0; pad.buttons=bit; pad.repeatAt={}
    pad.MenuNavigation(200,width or 1024,height or 768,moved or false,true)
    assert(not pad.error,tostring(pad.error))
end
nav(8); assert(pad.navigationFocus.INVENTORY=='slot_inv_32','right adjacent carried-item slot')
nav(2); assert(pad.navigationFocus.INVENTORY=='slot_inv_33','down adjacent carried-item slot')
-- Held neutral render ticks never drag the cursor back after a stick move.
pad.cursorX=700; pad.cursorY=350; nav(0,1024,768,true)
pad.cursorX=702; pad.cursorY=351; nav(0)
assert(pad.cursorX==702 and pad.cursorY==351)
nav(4); assert(pad.navigationFocus.INVENTORY=='slot_inv_3','D-pad starts near manual aim')
-- Child modal owns focus; returning to parent restores the last selected slot.
pad.navigationMenus.TEST_MODAL={{name='modal_done',kind='button',ready=function() return true end}}
areas.modal_done={450,300,100,40}; menus.TEST_MODAL=true; pad.MenuOpened('TEST_MODAL')
nav(0); assert(pad.cursorX==500 and pad.cursorY==320)
menus.TEST_MODAL=nil; pad.MenuClosed('TEST_MODAL'); nav(0)
assert(pad.navigationFocus.INVENTORY=='slot_inv_3' and pad.cursorX==629.5)
-- Reopening inventory and rendering at half resolution uses the same slot.
menus.INVENTORY=nil; pad.MenuClosed('INVENTORY'); pad.MenuNavigation(250,512,384,false,true)
menus.INVENTORY=true; pad.MenuOpened('INVENTORY'); nav(0,512,384)
assert(pad.cursorX==249.75 and pad.cursorY==268.25)
nav(8,512,384); assert(pad.cursorX==274.75)
-- Disabled/zero/invalid widgets cannot become a target; live bounds are used.
menus={TEST_MODAL=true}; pad.MenuOpened('TEST_MODAL')
pad.navigationMenus.TEST_MODAL={
 {name='left',kind='button',ready=function() return true end},
 {name='disabled',kind='button',ready=function() return 0 end},
 {name='broken',kind='button',ready=function() error('missing screen data') end},
 {name='zero',kind='button',ready=function() return true end},
 {name='right',kind='button',ready=function() return true end}}
areas.left={0,0,40,40}; areas.disabled={50,0,40,40}; areas.broken={60,0,40,40}
areas.zero={70,0,0,0}; areas.right={100,0,40,40}
pad.navigationFocus.TEST_MODAL='left'; nav(0); nav(8)
assert(pad.navigationFocus.TEST_MODAL=='right')
areas.right={200,0,40,40}; nav(4); nav(8); assert(pad.cursorX==220)
-- Visible list cells include the checkbox column. At the bottom, scroll once
-- and focus the next data row when the UI reports its new offset.
local list={name='list',kind='list',ready=function() return true end,
 rowHeight=function() return 30 end,rows=function() return 8 end,columns={90,10}}
pad.navigationMenus.TEST_MODAL={list}; areas.list={100,100,200,90}
pad.navigationCurrent=nil; pad.navigationFocus.TEST_MODAL='list:1:1'; nav(0)
nav(8); assert(pad.navigationFocus.TEST_MODAL=='list:1:2')
nav(2); nav(2); assert(pad.navigationFocus.TEST_MODAL=='list:3:2')
nav(2); assert(pad.navigationScrollRequest.list==-30)
assert(pad.MenuListScroll('list',0,90,240,nil)==-30)
nav(0); assert(pad.navigationFocus.TEST_MODAL=='list:4:2')
local originalCalled=false
assert(pad.MenuListScroll('list',-30,90,240,function() originalCalled=true; return -60 end)==-60)
assert(originalCalled)
-- PC mode never warps the cursor or consumes controller list scroll requests.
pad.controllerActive=false; pad.cursorX=17; pad.cursorY=19; trace={}
assert(not pad.MenuNavigation(400,1024,768,false,true))
assert(pad.cursorX==17 and pad.cursorY==19 and #trace==0)
pad.navigationScrollRequest.list=-30
assert(pad.MenuListScroll('list',-60,90,240,nil)==nil)
-- Exercise the real Step path: menu entry, D-pad + A same frame, PC click,
-- neutral rearm and controller acquisition while Inventory is already open.
menus={INVENTORY=true}; pad.navigationStack={}; pad.MenuOpened('INVENTORY')
pad.controllerActive=true; pad.armed=true; pad.error=nil
pad.navigationCurrent=nil; pad.navigationPending=nil
snapshot={1,0,0,0,0,0,0,0,300,300,1024,768,1000,1,500,400,1,1,100}
pad.physicalClicks=100; pad.buttons=0; pad.previousButtons=0; pad.lastTick=0
local function tick(bit)
 snapshot[2]=bit or 0; snapshot[13]=snapshot[13]+100; pad.Tick()
 assert(pad.error==nil,tostring(pad.error))
end
tick(); assert(pad.cursorX==499.5 and pad.cursorY==536.5)
trace={}; tick(8+4096)
local clicked=false
for _,event in ipairs(trace) do
 if event[1]==2 then assert(event[2]==549.5 and event[3]==536.5); clicked=true end
end
assert(clicked,'A uses the newly focused slot in the same frame')
snapshot[19]=101; snapshot[9]=17; snapshot[10]=19; tick()
assert(not pad.controllerActive and not pad.inventoryFocused)
local pcCursor=pad.cursorX
trace={}; tick(); assert(pad.cursorX==pcCursor and #trace==0)
tick(4096); tick(); tick()
assert(pad.controllerActive and pad.inventoryFocused and pad.cursorX==499.5)
-- World overlay navigation must show a pointer, accept A and suppress movement.
worldActive=true; gameState=0; gameIcon=0; menus={WORLD_FORMATION=true}
pad.MenuClosed('INVENTORY'); pad.MenuOpened('WORLD_FORMATION')
tick(); trace={}; tick(4+4096)
local overlayClicked=false
for _,event in ipairs(trace) do
 assert(event[1]~=9,'menu D-pad must never start walking')
 if event[1]==2 then overlayClicked=true end
end
assert(overlayClicked and not pad.worldCursorHidden,'A must click in world panels too')
''')
runtime.execute('''
local pad=PSTController
pad.controllerActive=true; pad.armed=true; pad.navigationStack={}; pad.navigationFocus={}; pad.navigationInitial={}
pad.navigationCurrent=nil; pad.navigationPending=nil; pad.error=nil
pad.buttons=0; pad.previousButtons=0; pad.repeatAt={}; pad.cursorX=900; pad.cursorY=600
local function nav()
 assert(pad.MenuNavigation(3000,1024,768,false,true))
end
for _,name in ipairs({'WORLD_CONTAINER','WORLD_QUICKLOOT'}) do
 menus={[name]=true}; worldActive=true; pad.MenuOpened(name)
 local initial
 for _,spec in ipairs(pad.navigationMenus[name]) do if spec.initial then initial=spec.name; break end end
 assert(initial,'loot menu must identify the first item cell, ahead of arrows/buttons')
 nav(); assert(pad.navigationFocus[name]==initial,name..' must start on first square')
 local firstX,firstY=pad.cursorX,pad.cursorY
 pad.buttons=8; pad.repeatAt={}; nav(); pad.buttons=0
 local last=pad.navigationFocus[name]
 assert(last~=initial,'loot D-pad navigation must remain usable')
 menus.TEST_MODAL=true; pad.MenuOpened('TEST_MODAL'); nav()
 menus.TEST_MODAL=nil; pad.MenuClosed('TEST_MODAL'); nav()
 assert(pad.navigationFocus[name]==last,'returning from item details preserves parent focus')
 menus[name]=nil; pad.MenuClosed(name)
 menus[name]=true; pad.MenuOpened(name); nav()
 assert(pad.navigationFocus[name]==initial and pad.cursorX==firstX and pad.cursorY==firstY,'reopening resets the first cell')
end
-- Mage/priest use the shared stock spell UI. Focus the first available book
-- spell, rather than a level arrow or an empty memorization placeholder.
function getMageBookEnabled() return true end
function isWizSpellMode() return true end
bookSpells={{isPlaceholder=false},{isPlaceholder=false}}; bottomSpells={}; bottomSpellsPlaceHolder={}
menus={SPELLS=true}; worldActive=false; pad.MenuOpened('SPELLS'); nav()
assert(pad.navigationFocus.SPELLS=='BUTTON_BOOKSPELL_1','spellbook starts on its first spell')
-- An empty first spell cannot be focused: choose the first available spell.
bookSpells[1]={isPlaceholder=true}; pad.MenuOpened('SPELLS'); nav()
assert(pad.navigationFocus.SPELLS=='BUTTON_BOOKSPELL_2','spellbook skips an unavailable first slot')
-- Context bars (weapon/item/spell/ability) also place the visible cursor at
-- the first enabled action once, then allow free cursor movement.
menus={WORLD_CONTEXT_BAR=true}; worldActive=true; gameState=0; gameIcon=0
pad.navigationStack={}; pad.navigationCurrent=nil; pad.contextIndex=nil; pad.contextFocused=false
areas.PST_CONTEXT_SLOT_0={14,6,52,52}; areas.PST_CONTEXT_SLOT_2={126,6,52,52}
snapshot[2]=0; snapshot[3]=0; snapshot[4]=0; snapshot[5]=0; snapshot[6]=0; snapshot[7]=0; snapshot[8]=0
snapshot[13]=snapshot[13]+100; pad.Tick(); assert(not pad.error,tostring(pad.error))
assert(pad.contextIndex==0 and pad.cursorX==40 and pad.cursorY==32,'context starts at the first enabled square')
pad.cursorX=500; pad.cursorY=600; snapshot[9]=500; snapshot[10]=600; snapshot[13]=snapshot[13]+100; pad.Tick()
assert(pad.cursorX==500 and pad.cursorY==600,'context must not keep pulling the cursor back')
''')
runtime.execute('''
local pad=PSTController
pad.controllerActive=true; pad.armed=true; pad.error=nil; pad.navigationCurrent=nil
pad.navigationStack={}; pad.navigationInitial={}; pad.navigationFocus={}; pad.navigationPending=nil
menus={}; worldActive=false; snapshot[20]=0; snapshot[14]=1
snapshot[3]=0; snapshot[4]=0; snapshot[5]=0; snapshot[6]=0; snapshot[7]=0; snapshot[8]=0
local function tick(bit)
 snapshot[9]=pad.cursorX; snapshot[10]=pad.cursorY -- follow the native cursor warp
 snapshot[2]=bit or 0; snapshot[13]=snapshot[13]+100; pad.Tick()
 assert(not pad.error,tostring(pad.error))
end
tick(); Infinity_SetOverlay('QuitMenu')
assert(not menus.QuitMenu and pad.overlayName=='QuitMenu','overlay is deliberately absent from normal menu stack')
tick(); assert(pad.cursorX==607 and pad.cursorY==347,'quit overlay starts on No')
local no=pad.navigationFocus.QuitMenu
tick(8); assert(pad.cursorX==791 and pad.cursorY==347 and pad.navigationFocus.QuitMenu~=no,'D-pad selects Yes')
tick(); trace={}; tick(4096)
local click=false
for _,event in ipairs(trace) do
 if event[1]==2 then assert(event[2]==791 and event[3]==347); click=true end
 assert(event[1]~='shutdown','UI confirmation remains a queued click')
end
assert(click,'A activates the D-pad selected button')
-- Reopening a popup during the same held A cannot click its new selection.
Infinity_SetOverlay(nil); Infinity_SetOverlay('QuitMenu'); assert(pad.confirmNeedsRelease)
trace={}; tick(4096)
for _,event in ipairs(trace) do assert(event[1]~=2,'held A cannot confirm a newly opened popup') end
tick(); tick(8+4096)
local sameFrame=false
for _,event in ipairs(trace) do if event[1]==2 then assert(event[2]==791); sameFrame=true end end
assert(sameFrame,'D-pad plus A uses the newly selected Yes in the same frame')
Infinity_SetOverlay(nil); assert(not pad.overlayName)
-- Other two-button popups retain local D-pad navigation on top of their parent.
menus={START=true,POPUP_TWOBUTTON=true}; pad.MenuOpened('START'); pad.MenuOpened('POPUP_TWOBUTTON')
tick(); assert(pad.navigationCurrent=='POPUP_TWOBUTTON')
assert(pad.cursorX==607 and pad.cursorY==347)
tick(8); assert(pad.cursorX==791); tick(); tick(4); assert(pad.cursorX==607)
''')
from ui_build import build_ui
quit_ui=named_menus(build_ui(source))['QuitMenu']
assert 'PSTController.Tick()' in quit_ui, 'native overlays require their own render poll'
from ui_resources import button_actions
requester_ui=named_menus(source)['POPUP_REQUESTER']
done=next(action for body,action in button_actions(requester_ui) if re.search(r'text\s+[\'"]DONE_BUTTON[\'"]',body))
runtime.execute('function PSTController.StockQuantityDone()\n'+done+'\nend')
generated_inventory=named_menus(build_ui(source))['INVENTORY']
dispatch_body,dispatch_action=next((body,action) for body,action in button_actions(generated_inventory)
    if "name 'PST_SPLIT_DISPATCH'" in body)
assert 'on return' not in dispatch_body and 'on return' not in dispatch_action
assert "PST_SPLIT_DISPATCH" not in metadata, 'internal action must never enter D-pad navigation'
runtime.execute('function clickSplitDispatchButton()\n'+dispatch_action+'\nend')
dispatch_area=re.search(r'area\s+(\d+)\s+(\d+)\s+(\d+)\s+(\d+)',dispatch_body)
g.areas.PST_SPLIT_DISPATCH=runtime.table_from([int(dispatch_area[i]) for i in range(1,5)])
assert [int(dispatch_area[i]) for i in range(1,5)]==[500,500,2,2]

start=source.index('function showItemAmountRequester(')
end=source.index('function GetAbilityIdentifyString()',start)
runtime.execute(source[start:end])  # Real stock stack-count/open/split functions.
start=source.index('function slotDoubleClick(')
end=source.index('function getTempHP()',start)
runtime.execute(source[start:end])
start=source.index('function itemRequesterDoneClickable(')
end=source.index('\nend',start)+4
runtime.execute(source[start:end])
runtime.execute('''
local pad=PSTController
local oldPop=Infinity_PopMenu
function Infinity_PopMenu(name)
 local closed=name or mockTop; oldPop(closed)
 if closed=='POPUP_REQUESTER' then pad.MenuClosed(closed); editing=0 end
end
function popupRequester(maximum,callback,selling,item)
 requester={requesterMax=maximum,requesterFunc=callback,selling=selling,item=item}
 itemRequestAmt=1; menus.POPUP_REQUESTER=true; mockTop='POPUP_REQUESTER'
 pad.MenuOpened('POPUP_REQUESTER'); editing=1 -- the game's number edit may own focus
end
function Infinity_FocusTextEdit(name) assert(name==''); editing=0 end
local splitCount=0
function Infinity_SplitItemStack(slot,amount,anchor)
 assert(slot==30 and anchor=='slot_inv_30')
 assert(amount>=1 and amount<=characters[id].equipment.group0.item.count)
 splitCount=amount; characters[id].equipment.group0.item.count=characters[id].equipment.group0.item.count-amount
end
characters={[1]={HP={current=20},equipment={group0={id=30,item={count=4,isBag=0,res='RAGS'}},group1={id=31,item={count=1,isBag=0,res='RAGS'}}}}}; id=1
pad.controllerActive=true; pad.armed=true; pad.navigationStack={}; pad.navigationFocus={}; pad.navigationInitial={}
pad.navigationCurrent=nil; pad.navigationPending=nil; pad.pendingSplit=nil; pad.pendingQuantity=nil
pad.quantityOwner=nil; pad.overlayName=nil; pad.confirmNeedsRelease=false
menus={INVENTORY=true}; worldActive=false; editing=0; pad.MenuOpened('INVENTORY')
snapshot[20]=0; snapshot[14]=1; snapshot[3]=0; snapshot[4]=0; snapshot[5]=0; snapshot[6]=0; snapshot[7]=0; snapshot[8]=0
local function tick(bit,elapsed)
 snapshot[9]=pad.cursorX or 500; snapshot[10]=pad.cursorY or 537
 snapshot[2]=bit or 0; snapshot[13]=snapshot[13]+(elapsed or 100)
 pad.Tick(); assert(not pad.error,tostring(pad.error))
end
-- Deliver the queued native gesture through the stock slot double-click and
-- the stock Done button; do not manually invoke a controller dispatch function.
local function deliverSplit()
 local gesture
 for _,event in ipairs(trace) do
  assert(not (event[1]==3 and event[2]==13),'Y must never queue Enter')
  assert(event[1]~=17 and event[1]~=2,'Y must not click the item slot or simulate a double click')
  if event[1]==4 then gesture=event end
 end
 assert(gesture and gesture[2]==501 and gesture[3]==501,'Y clicks the dedicated inventory dispatcher')
 clickSplitDispatchButton() -- generated UI button's exact action, on the event loop
end
local function deliverDone()
 local done
 for _,event in ipairs(trace) do
  assert(not (event[1]==3 and event[2]==13),'A must click Done instead of Enter')
  if event[1]==4 then done=event end
 end
 assert(done,'quantity A must synchronize hover and click the live Done node')
 for _,node in ipairs(pad.NavigationNodes('POPUP_REQUESTER',1024,768)) do
  if node.spec.quantityDone then
   assert(done[2]==math.floor(node.x+0.5) and done[3]==math.floor(node.y+0.5))
  end
 end
 pad.StockQuantityDone() -- exact stock button action in this mock event loop
end
tick(); trace={}; tick(32768)
assert(pad.pendingSplit and pad.pendingSplit.slot=='group0')
deliverSplit(); assert(menus.POPUP_REQUESTER and itemRequestAmt==1 and pad.quantityOwner)
assert(not pad.pendingSplit)
tick(); tick(8); assert(itemRequestAmt==2,'right increments even with the number edit focused')
tick(); trace={}; tick(4096); assert(splitCount==0 and editing==0,'confirmation is queued after clearing edit focus')
deliverDone(); assert(not menus.POPUP_REQUESTER and splitCount==2)
assert(characters[1].equipment.group0.item.count==2 and menus.INVENTORY)
tick(); assert(pad.navigationFocus.INVENTORY=='slot_inv_30')
tick(32768); deliverSplit(); tick(); tick(4); assert(itemRequestAmt==1)
tick(); tick(8); tick(8,400); tick(8,400); assert(itemRequestAmt==2)
tick(); tick(8192); pad.DispatchBack(); assert(not menus.POPUP_REQUESTER and splitCount==2)
assert(characters[1].equipment.group0.item.count==2,'cancel leaves the stack untouched')
characters[1].equipment.group0.item.count=1; tick(); trace={}; tick(32768)
assert(not pad.pendingSplit)
for _,event in ipairs(trace) do assert(event[1]~=17 and event[1]~=2 and event[1]~=4) end
pad.cursorX=17; pad.cursorY=19; tick(); trace={}; tick(32768); assert(not pad.pendingSplit)
characters[1].equipment.group0.item.count=4; pad.MenuOpened('INVENTORY'); tick(); trace={}; tick(32768)
deliverSplit(); tick(); characters[1].equipment.group0.item.count=3
trace={}; tick(4096)
for _,event in ipairs(trace) do assert(event[1]~=4,'changed stack cannot be confirmed') end
assert(menus.POPUP_REQUESTER and splitCount==2)
tick(); tick(8192); pad.DispatchBack()
characters[1].equipment.group0.item.count=4; tick(); trace={}; tick(32768); deliverSplit(); tick()
id=2; trace={}; tick(4096)
for _,event in ipairs(trace) do assert(event[1]~=4,'changed character cannot be confirmed') end
id=1; tick(); tick(8192); pad.DispatchBack()
-- A captured dispatch cannot open the wrong stack after mutation or PC handoff.
characters[1].equipment.group0.item.count=4; pad.MenuOpened('INVENTORY'); tick(); trace={}; tick(32768)
assert(pad.pendingSplit); characters[1].equipment.group0.item.res='OTHER'
deliverSplit(); assert(not menus.POPUP_REQUESTER and not pad.pendingSplit)
characters[1].equipment.group0.item.res='RAGS'; tick(); trace={}; tick(32768)
assert(pad.pendingSplit); pad.controllerActive=false
clickSplitDispatchButton(); assert(not menus.POPUP_REQUESTER and not pad.pendingSplit)
pad.controllerActive=true


''')
from radial_asset import build_selection_bam
import struct
bam=build_selection_bam()
assert bam[:8]==b'BAM V1  '
frames,cycles=struct.unpack_from('<HB',bam,8)
assert frames==3 and cycles==3
fo,po,lo=struct.unpack_from('<3I',bam,12)
for i,(width,height) in enumerate(((64,64),(57,97),(43,43))):
    w,h,_,_,data_offset=struct.unpack_from('<HHhhI',bam,fo+i*12)
    assert (w,h)==(width,height) and data_offset&0x80000000
    pixels=bam[data_offset&0x7fffffff:(data_offset&0x7fffffff)+w*h]
    assert len(pixels)==w*h and pixels[(h//2)*w+w//2]==0,'frame center must stay transparent'
    assert pixels[w//2]==1 and pixels[w+w//2]==2 and pixels[2*w+w//2]==2
    assert pixels[3*w+w//2]==0,'frame must contain two yellow pixels and one dark outer edge'
    yellow=pixels[w+1]
    blue,green,red,_=struct.unpack_from('<4B',bam,po+yellow*4)
    assert red>=250 and green>=200 and blue<100,'selection must be bright yellow'
generated=build_ui(source)
assert "bam 'PSTPSEL'" in generated and 'PSTController.DispatchSplitStack()' in generated and 'PSTController.DispatchQuantity()' not in generated
print('PASS: dedicated UI split flow Y/D-pad/A/B on four rags; 2-of-4, clamp/cancel/stale stack guards; transparent yellow frames; popup, focus and existing controls')
