"""Read named UI.menu blocks without treating braces in Lua strings as UI."""
import re


def block_end(text, start):
    depth, quote, index = 0, None, start
    while index < len(text):
        char = text[index]
        if quote:
            if char == '\\':
                index += 2
                continue
            if char == quote:
                quote = None
        elif text.startswith('--', index):
            newline = text.find('\n', index)
            index = len(text) if newline < 0 else newline
            continue
        elif char in ('"', "'"):
            quote = char
        elif char == '{':
            depth += 1
        elif char == '}':
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise ValueError('Unclosed UI block')


def named_menus(text):
    menus = {}
    for match in re.finditer(r'^menu\s*\{', text, re.M):
        start = text.index('{', match.start())
        body = text[start:block_end(text, start)]
        name = re.search(r'^\s*name\s+([\'"])(.*?)\1', body, re.M)
        if name:
            menus[name[2]] = body
    return menus


def button_actions(body):
    for match in re.finditer(r'^\s*button\s*\{', body, re.M):
        start = body.index('{', match.start())
        button = body[start:block_end(body, start)]
        action = re.search(r'^\s*action\s+([\'"])(.*?)\1', button, re.M | re.S)
        if action:
            yield button, action[2].strip()


def escape_action(body):
    for button, action in button_actions(body):
        if re.search(r'\bon\s+escape\b', button):
            return action
    return None


def cancel_action(body):
    action = escape_action(body)
    if action:
        return action
    for button, action in button_actions(body):
        if re.search(r'^\s*text\s+[\'"]CANCEL_BUTTON[\'"]', button, re.M):
            return action
    for button, action in button_actions(body):
        if re.search(r'^\s*text\s+[\'"]DONE_BUTTON[\'"]', button, re.M):
            return action
    return None


# Child dialogs precede their parents. The generated functions reuse the stock
# Cancel actions, including rollback of pending graphics/sound/keymap changes.
BACK_MENUS = (
    'QuitMenu', 'POPUP_REQUESTER', 'POPUP_TWOBUTTON', 'SAVE_NEWSAVE',
    'ITEM_ABILITIES', 'ITEM_IDENTIFY', 'ITEM_DESCRIPTION', 'SPELL_DESCRIPTION',
    'CHARACTER_BIOGRAPHY', 'CHARACTER_INFORMATION',
    'OPTIONS_FEEDBACK', 'OPTIONS_AUTOPAUSE', 'OPTIONS_KEYBINDINGS',
    'OPTIONS_LANGUAGE', 'OPTIONS_GRAPHICS', 'OPTIONS_SOUND',
    'OPTIONS_DATA_FOLDER', 'OPTIONS_GAMEPLAY', 'SAVE', 'LOAD', 'ESC_MENU',
)


def stock_back_lua(text):
    menus = named_menus(text)
    output = ['PSTController.stockBackHandlers = {']
    for name in BACK_MENUS:
        action = cancel_action(menus[name])
        if name == 'POPUP_TWOBUTTON':
            action = next((value for _, value in button_actions(menus[name])
                           if 'Popup2Button.cancelFunc' in value), None)
        elif name == 'ESC_MENU':
            action = next((value for _, value in button_actions(menus[name])
                           if re.search(r'SelectEngine\(\s*worldScreen\s*\)', value)), None)
        if not action:
            raise ValueError(f'Missing stock Cancel/Done action: {name}')
        output.append("    {'" + name + "', function()\n" + action + '\n    end},')
    output.append('}')
    return '\n'.join(output)


def patch_cancel_bindings(text):
    """Give modal Cancel buttons a local Escape route, preserving their code."""
    menus = named_menus(text)
    for name in BACK_MENUS:
        original = menus[name]
        wanted = cancel_action(original)
        if name == 'POPUP_TWOBUTTON':
            wanted = next(value for _, value in button_actions(original) if 'Popup2Button.cancelFunc' in value)
        elif name == 'ESC_MENU':
            wanted = next(value for _, value in button_actions(original) if re.search(r'SelectEngine\(\s*worldScreen\s*\)', value))
        button = next(button for button, action in button_actions(original) if action == wanted)
        patched = button
        if not re.search(r'\bon\s+escape\b', button):
            patched = patched[:1] + '\n\t\ton escape' + patched[1:]
        # Consume a queued B when the normal UI button handles it, preventing
        # a second fallback from closing the parent in the same event loop.
        patched = re.sub(r'(^\s*action\s+[\'"])', r'\1PSTController.pendingBack=nil;\n', patched, count=1, flags=re.M)
        replacement = original.replace(button, patched, 1)
        text = text.replace(original, replacement, 1)
    # Modal world overlays have no stock Cancel binding and may exclude the
    # global driver from input dispatch. Supply the same fallback locally.
    for name in ('POPUP_THREEBUTTON', 'WORLD_FORMATION', 'WORLD_CONTEXT_BAR',
                 'WORLD_CONTAINER', 'WORLD_QUICKLOOT', 'WORLD_HELP', 'WORLD_HELP_TABLET',
                 'INVENTORY_HELP', 'CHARACTER_HELP', 'SPELLS_HELP', 'MAP_HELP',
                 'INVENTORY', 'CHARACTER', 'AREA_MAP',
                 'STORE_CHOOSER','STORE_BUYSELL','STORE_IDENTIFY','STORE_ROOMS','STORE_HEALING'):
        original = menus[name]
        binding = '''
    button
    {
        area 0 0 0 0
        on escape
        action "PSTController.pendingBack=true; PSTController.DispatchBack()"
    }
'''
        text = text.replace(original, original[:-1] + binding + '}', 1)
    return text


if __name__ == '__main__':
    from pathlib import Path
    text = (Path(__file__).parent / 'backups' / 'UI.menu.original').read_text(encoding='utf-8-sig')
    for name, body in named_menus(text).items():
        if name.startswith(('OPTIONS', 'CHARACTER', 'ITEM', 'SPELL', 'STORE', 'WORLD_HELP')) or name in ('ESC_MENU','JOURNAL','INVENTORY','MAP','RECORD','POPUP_TWOBUTTON','POPUP_THREEBUTTON','POPUP_REQUESTER','SAVE','LOAD','SAVE_NEWSAVE'):
            print(name + ': ' + str(escape_action(body)))
            for button, action in button_actions(body):
                if re.search(r'CANCEL_BUTTON|BACK_BUTTON|DONE_BUTTON|REST_BUTTON', button):
                    print('  button: ' + action)
