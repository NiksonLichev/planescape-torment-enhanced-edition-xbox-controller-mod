"""Build the mod UI from a user-provided stock UI resource."""
import re
from ui_resources import stock_back_lua, patch_cancel_bindings, named_menus
from menu_navigation import build_navigation

def build_ui(source_ui):
    ui = patch_cancel_bindings(source_ui)
    # Each principal screen has a background callback. The Lua wrapper retains a
    # non-modal input driver on screen changes; START and WORLD get explicit guards.
    ui = ui.replace("e:GetObjectGame():SetCampaign('PST')", "e:GetObjectGame():SetCampaign('PST')\n\t\tPSTController.EnsureDriver()")
    ui = ui.replace('openGemMenus(false)', 'openGemMenus(false)\n\t\tPSTController.EnsureDriver()')
    # Replace only WORLD_DIALOG's Return action. It dispatches the captured response
    # on the regular input callback, independent of list scroll and mouse position.
    dialog_start = ui.index("name 'WORLD_DIALOG'")
    return_start = ui.index('\t\ton return', dialog_start)
    button_start = ui.rfind('\tbutton', dialog_start, return_start)
    button_end = ui.index('\n\t}', return_start) + len('\n\t}')
    return_button = ui[button_start:button_end]
    if 'onDialogButtonClick()' not in return_button:
        raise RuntimeError('Unexpected WORLD_DIALOG Return button; refusing UI patch')
    return_button = return_button.replace('getDialogButtonEnabled() and getDialogButtonClickable()',
        '(getDialogButtonEnabled() and getDialogButtonClickable()) or PSTController.pendingDialog ~= nil')
    return_button = return_button.replace('onDialogButtonClick()', 'PSTController.DispatchDialogue()')
    ui = ui[:button_start] + return_button + ui[button_end:]
    # The journal lists otherwise have no controller focus/navigation. Each uses
    # its own one-shot scroll request so a hidden list cannot consume another's.
    journal_start = ui.index("name 'JOURNAL'")
    journal_end = ui.index('\nmenu', journal_start)
    journal_ui = ui[journal_start:journal_end]
    journal_ui = journal_ui.replace('scrollbar func "journalScroll"',
        'scrollbar func "PSTPadScrollEntries"')
    for table_name, panel in [('quests','quests'),('bestiary','bestiary')]:
        journal_ui = re.sub(r'(table\s+"'+table_name+r'")',
            r'\1\n\t\tscrollbar func "PSTPadScroll'+panel.title()+r'"', journal_ui)
    ui = ui[:journal_start]+journal_ui+ui[journal_end:]
    context_start = ui.index('name "WORLD_CONTEXT_BAR"')
    context_end = ui.index('\nmenu', context_start)
    context_ui=ui[context_start:context_end]
    context_ui=re.sub(r'(\t\tactionBar (\d+)\n)',
        lambda match:match[1]+f'\t\tname "PST_CONTEXT_SLOT_{match[2]}"\n\t\tglow lua "PSTController.ContextSlotSelected({match[2]})"\n', context_ui)
    ui=ui[:context_start]+context_ui+ui[context_end:]
    # A dedicated mouse action runs on the regular UI input callback. Neither
    # stock Enter handling nor the engine's double-click timing can consume Y.
    inventory=named_menus(ui)['INVENTORY']
    split_dispatch='''
    button
    {
        name 'PST_SPLIT_DISPATCH'
        area 500 500 2 2
        enabled "PSTController.controllerActive and PSTController.pendingSplit ~= nil"
        action "PSTController.DispatchSplitStack()"
        actionDbl "PSTController.DispatchSplitStack()"
    }
'''
    ui=ui.replace(inventory,inventory[:-1]+split_dispatch+'}',1)
    ui,navigation_lua=build_navigation(ui)
    # A native overlay may not render the normal driver underneath it. Give
    # visible modal dialogs their own guarded render poll, without any input.
    for name,body in named_menus(ui).items():
        if name=='QuitMenu' or re.search(r'^\s*modal\s*$',body,re.M):
            poll='''
    label
    {
        area 0 0 1 1
        ignoreFocus 1
        text lua "(function() PSTController.Tick(); return '' end)()"
        text style "label"
        text point 1
    }
'''
            ui=ui.replace(body,body[:-1]+poll+'}',1)
    ui += '\n`\n' + stock_back_lua(source_ui) + '\n'+navigation_lua+'\n`\n'
    driver = '''
menu
{
    name 'PST_CONTROLLER_DRIVER'
    align center top
    size 1024 768
    ignoreEsc
    ignoreFocus 1
    ignoreNav 1
    button
    {
        area 0 0 0 0
        enabled "PSTController.native ~= nil and PSTController.controllerActive and e:GetActiveEngine() == worldScreen and not Infinity_IsMenuOnStack('WORLD_DIALOG')"
        on return
        action "PSTController.DispatchWorld()"
    }
    button
    {
        area 0 0 0 0
        enabled "PSTController.native ~= nil and PSTController.controllerActive and not Infinity_IsMenuOnStack('WORLD_DIALOG')"
        on escape
        action "PSTController.DispatchBack()"
    }
    label
    {
        area 0 0 1 1
        ignoreFocus 1
        text lua "(function() PSTController.Tick(); return '' end)()"
        text style "label"
        text point 1
    }
    label
    {
        name 'PST_CONTROLLER_NEARBY'
        enabled "PSTController.nearby ~= nil and not PSTController.radial"
        area 0 0 128 30
        text lua "PSTController.NearbyText()"
        text style "button"
        text point 14
        text shadow 1
    }
    label
    {
        enabled "PSTController.radial"
        area 302 155 420 420
        bam 'PSTPRAD'
        sequence 0
        frame 0
    }
    label
    {
        enabled "PSTController.radial"
        area 442 310 140 24
        text lua "'ACTIONS '..PSTController.radialPage..'/2'"
        text style "label"
        text point 12
    }
    label
    {
        enabled "PSTController.radial"
        area 422 342 180 32
        text lua "PSTController.radialEntries[PSTController.radialIndex][1]"
        text style "button"
        text point 18
    }
    label
    {
        enabled "PSTController.radial"
        area 432 380 160 24
        text 'A Confirm - B Back'
        text style "label"
        text point 12
    }
    label
    {
        enabled "PSTController.radial"
        area 432 410 160 24
        text lua "'LB  '..PSTController.radialPage..'/2  RB'"
        text style "label"
        text point 12
    }
'''
    # Centers preserve the existing clockwise LS selection, with enough room for
    # the native 45x85 action icons and the sidebar's 52x52 icons.
    positions = [(512,217),(618,263),(657,365),(618,475),(512,523),(406,475),(367,365),(406,263)]
    for index, (x, y) in enumerate(positions, 1):
        for kind, width, height, condition in [
            ('action',45,85,f"PSTController.RadialBam({index}) == 'TACTBUTT'"),
            ('circle',31,31,f"PSTController.RadialBam({index}) == 'CIRCBUTT'"),
            ('sidebar',52,52,f"PSTController.RadialBam({index}) ~= 'TACTBUTT' and PSTController.RadialBam({index}) ~= 'CIRCBUTT'"),
        ]:
            driver += f'''
    label
    {{
        enabled "PSTController.radial and {condition}"
        area {x-width//2} {y-height//2} {width} {height}
        bam lua "PSTController.RadialBam({index})"
        sequence lua "PSTController.RadialSequence({index})"
        frame lua "PSTController.RadialFrame({index})"
    }}
'''
        for sequence,width,height,condition in [
            (0,64,64,f"PSTController.RadialBam({index}) ~= 'TACTBUTT' and PSTController.RadialBam({index}) ~= 'CIRCBUTT'"),
            (1,57,97,f"PSTController.RadialBam({index}) == 'TACTBUTT'"),
            (2,43,43,f"PSTController.RadialBam({index}) == 'CIRCBUTT'"),
        ]:
            driver+=f'''
    label
    {{
        enabled "PSTController.radial and PSTController.radialIndex == {index} and {condition}"
        area {x-width//2} {y-height//2} {width} {height}
        bam 'PSTPSEL'
        sequence {sequence}
        frame 0
    }}
'''
    driver += '}\n'
    ui += driver
    return ui
