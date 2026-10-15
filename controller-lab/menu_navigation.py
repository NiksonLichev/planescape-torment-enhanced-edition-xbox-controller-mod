"""Generate controller focus metadata from the copied game's stock UI."""
import re
from ui_resources import named_menus, block_end


def child_blocks(body):
    """Direct children only; template widgets are not live menu instances."""
    index, quote = 1, None
    while index < len(body)-1:
        char = body[index]
        if quote:
            if char == '\\':
                index += 2
                continue
            if char == quote:
                quote = None
        elif body.startswith('--', index):
            end = body.find('\n', index)
            index = len(body) if end < 0 else end
            continue
        elif char in ('"', "'"):
            quote = char
        elif char == '{':
            end = block_end(body, index)
            kind = re.search(r'(\w+)\s*$', body[:index])
            if kind:
                yield kind[1], index, end, body[index:end]
            index = end
            continue
        index += 1


def own_properties(body):
    output = list(body)
    for _, start, end, _ in child_blocks(body):
        output[start:end] = ' ' * (end-start)
    return ''.join(output)


def quoted_property(text, key):
    match = re.search(r'\b'+key+r'\s+(?:lua\s+)?([\'"])(.*?)\1', text, re.S | re.I)
    return match[2] if match else None


def enabled_expressions(properties):
    expressions=[]
    for key in ('enabled','clickable','interactable'):
        value=quoted_property(properties,key)
        if value is None:
            numeric=re.search(r'\b'+key+r'\s+(-?\d+)\b',properties,re.I)
            if numeric:
                value=numeric[1]
        if value is not None:
            expressions.append(value)
    return expressions


def lua_string(value):
    return "'"+value.replace('\\','\\\\').replace("'","\\'").replace('\n','\\n')+"'"


def add_widget_property(body,kind,property_text):
    # The engine's list parser reads column blocks before widget properties.
    # Putting name/scrollbar before the first column produces a Menu Error.
    insert=1
    if kind=='list':
        insert=max((end for child_kind,_,end,_ in child_blocks(body)
                    if child_kind=='column'),default=1)
    return body[:insert]+'\n        '+property_text+'\n'+body[insert:]


def availability(expressions):
    parts=['function()']
    for expression in expressions:
        parts.append('local value=('+expression+'); if value==nil or value==false or value==0 then return false end')
    parts.append('return true end')
    return ' '.join(parts)


WORLD_PANELS={'WORLD_FORMATION','WORLD_CONTAINER','WORLD_QUICKLOOT','WORLD_MAP',
              'WORLD_HELP','WORLD_HELP_TABLET','WORLD_HELP_TABLET_LEFT','WORLD_HELP_TABLET_RIGHT','WORLD_HELP_DESCRIPTION'}


def build_navigation(text):
    specs=[]
    scroll_functions=[]
    for menu_name, original in named_menus(text).items():
        if menu_name.startswith(('BACKGROUND_', 'WORLD_')) and menu_name not in WORLD_PANELS:
            continue
        if menu_name in ('PST_CONTROLLER_DRIVER','cheatConsole','cheatMenu','luaHistoryMenu'):
            continue
        properties=own_properties(original)
        menu_conditions=enabled_expressions(properties)
        patched=original
        controls=[]
        replacements=[]
        for kind, start, end, body in child_blocks(original):
            own=own_properties(body)
            if kind not in ('button','slot','slider','list','text','label'):
                continue
            if re.search(r'\b(?:ignoreEvents|ignoreFocus\s+1)\b',own):
                continue
            native_button=any(quoted_property(own,key) for key in ('spellinfo','memorizedspellinfo'))
            if kind in ('button','text','label') and quoted_property(own,'action') is None and not native_button:
                continue
            if kind=='list' and not any(quoted_property(own,key) for key in ('action','actionalt','actionDbl')):
                continue
            # Invisible keyboard dispatch buttons are not navigation targets.
            area=re.search(r'\barea\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\b',own)
            if area and (int(area[3])==0 or int(area[4])==0):
                continue
            name=quoted_property(own,'name')
            if name=='PST_SPLIT_DISPATCH':
                continue  # Internal queued action, never an inventory focus target.
            replacement=body
            if not name:
                name=f'PST_NAV_{menu_name}_{len(controls)+1}'
                replacement=add_widget_property(body,kind,'name '+lua_string(name))
            conditions=menu_conditions+enabled_expressions(own)
            if native_button:
                info=quoted_property(own,'spellinfo') or quoted_property(own,'memorizedspellinfo')
                conditions.append('('+info+') ~= nil and not ('+info+').isPlaceholder')
            fields=['name='+lua_string(name),'kind='+lua_string(kind),
                    'ready='+availability(conditions)]
            action=quoted_property(own,'action') or ''
            slotinfo=quoted_property(own,'slotinfo') or ''
            inventory_slot=re.fullmatch(r'characters\[id\]\.equipment\.(\w+)',slotinfo)
            if menu_name=='INVENTORY' and inventory_slot:
                fields.append('inventorySlot='+lua_string(inventory_slot[1]))
            if menu_name=='POPUP_REQUESTER' and quoted_property(own,'text')=='DONE_BUTTON':
                fields.append('quantityDone=true')
            if native_button:
                fields.append('spell=true')
            if (slotinfo.endswith('.group0') or
                    (menu_name=='WORLD_CONTAINER' and re.search(r'OnContainerButtonClick\(\s*0\s*\)',action)) or
                    (menu_name=='WORLD_QUICKLOOT' and re.search(r'groundItemClick\(\s*0\s*\)',action)) or
                    (native_button and re.fullmatch(r'bookSpells\[1\]',info))):
                fields.append('initial=true')
            elif menu_name=='QuitMenu' and quoted_property(own,'text')=='NO_BUTTON':
                fields.append('initial=true')
            if kind=='list':
                columns=[]
                child_heights=[]
                for column_kind,_,_,column_body in child_blocks(body):
                    if column_kind=='column':
                        width=re.search(r'\bwidth\s+(\d+)\b',own_properties(column_body))
                        if width:
                            columns.append(width[1])
                        for _,_,_,element in child_blocks(column_body):
                            element_area=re.search(r'\barea\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)\b',own_properties(element))
                            if element_area and int(element_area[4])>0:
                                child_heights.append(int(element_area[2])+int(element_area[4]))
                fields.append('columns={'+','.join(columns or ['100'])+'}')
                row=quoted_property(own,'rowheight')
                numeric=re.search(r'\browheight\s+(\d+)\b',own)
                inferred=str(max(child_heights)) if child_heights else '38'
                fields.append('rowHeight=function() return '+(row or (numeric[1] if numeric else inferred))+' end')
                table=quoted_property(own,'table')
                if table:
                    fields.append('rows=function() local value=('+table+'); return type(value)=="table" and #value or 0 end')
                # UI supplies the actual list scroll offset; retain any stock
                # callback and add one-shot controller scrolling at an edge.
                scroll_name='PSTPadListScroll_'+name
                scroll_match=re.search(r'\bscrollbar\s+func\s+([\'"])(.*?)\1',replacement)
                original_scroll=scroll_match[2] if scroll_match else None
                if scroll_match:
                    replacement=replacement[:scroll_match.start()]+replacement[scroll_match.start():scroll_match.end()].replace(original_scroll,scroll_name)+replacement[scroll_match.end():]
                else:
                    replacement=add_widget_property(replacement,kind,'scrollbar func '+lua_string(scroll_name))
                scroll_functions.append('function '+scroll_name+'(top,height,contentHeight) return PSTController.MenuListScroll('+lua_string(name)+',top,height,contentHeight,'+(original_scroll or 'nil')+') end')
            for direction in ('left','right','up','down'):
                hint=quoted_property(own,'nav'+direction)
                if hint:
                    fields.append(direction+'='+lua_string(hint))
            controls.append('{'+','.join(fields)+'}')
            if replacement!=body:
                replacements.append((start,end,replacement))
        if not controls:
            continue
        for start,end,replacement in reversed(replacements):
            patched=patched[:start]+replacement+patched[end:]
        # Record actual open order so nested dialogs win over their parents.
        for callback, method in (('onOpen','MenuOpened'),('onClose','MenuClosed')):
            code='PSTController.'+method+'('+lua_string(menu_name)+'); '
            pattern=r'(\b'+callback+r'\s+[\'"])'
            if re.search(pattern,patched,re.I):
                patched=re.sub(pattern,lambda match:match[1]+code,patched,count=1,flags=re.I)
            else:
                patched=patched[:1]+'\n    '+callback+' "'+code+'"\n'+patched[1:]
        text=text.replace(original,patched,1)
        specs.append('['+lua_string(menu_name)+']={'+','.join(controls)+'}')
    metadata='PSTController.navigationMenus={\n'+',\n'.join(specs)+'\n}\n'+'\n'.join(scroll_functions)
    return text,metadata
