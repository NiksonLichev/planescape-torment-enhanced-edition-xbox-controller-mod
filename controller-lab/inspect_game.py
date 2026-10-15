"""Read KEY/BIFF resources and PE strings without modifying the game."""
from pathlib import Path
import argparse
import hashlib
import json
import re
import struct


def resources(root):
    key = (root / 'chitin.key').read_bytes()
    if key[:8] != b'KEY V1  ':
        raise ValueError('Unsupported KEY header')
    bif_count, resource_count, bif_offset, resource_offset = struct.unpack_from('<4I', key, 8)
    bifs = []
    for i in range(bif_count):
        _, offset, length, _ = struct.unpack_from('<IIHH', key, bif_offset + i * 12)
        bifs.append(key[offset:offset + length].rstrip(b'\0').decode('ascii'))
    for i in range(resource_count):
        name, kind, locator = struct.unpack_from('<8sHI', key, resource_offset + i * 14)
        if kind not in (0x408, 0x409):
            continue
        name = name.rstrip(b'\0').decode('ascii')
        with (root / bifs[locator >> 20]).open('rb') as bif:
            header = bif.read(20)
            if header[:8] != b'BIFFV1  ':
                raise ValueError('Unsupported BIFF header')
            count, _, table_offset = struct.unpack_from('<3I', header, 8)
            bif.seek(table_offset)
            entries = bif.read(count * 16)
            matches = []
            for j in range(count):
                entry = struct.unpack_from('<IIIHH', entries, j * 16)
                if entry[0] & 0x3fff == locator & 0x3fff:
                    matches.append(entry)
            if len(matches) != 1 or matches[0][3] != kind:
                raise ValueError(f'Invalid resource index: {name}')
            _, offset, length, _, _ = matches[0]
            bif.seek(offset)
            payload = bif.read(length)
            if len(payload) != length:
                raise ValueError(f'Truncated resource: {name}')
            yield name, kind, payload


def inspect(root):
    exe = (root / 'Torment.exe').read_bytes()
    pe_offset = struct.unpack_from('<I', exe, 0x3c)[0]
    if exe[pe_offset:pe_offset + 4] != b'PE\0\0':
        raise ValueError('Not a PE executable')
    ascii_strings = {m.group().decode('ascii') for m in re.finditer(rb'[\x20-\x7e]{4,}', exe)}
    names = [
        'Enable Joystick Control', 'Enable Drive Mode', 'Joystick Dead Zone',
        'Joystick Cursor Speed', 'Joystick Magnet Radius', 'GetDriveModeEnabled',
        'CONTROLLER_START_MENU', 'Infinity_ClickWorldAt',
        'Infinity_ClickObjectInWorld', 'Infinity_SelectDialogueOption',
    ]
    ui_lua = list(resources(root))
    ui = next(data.decode('utf-8-sig') for name, kind, data in ui_lua if name == 'UI' and kind == 0x408)
    includes = next(data.decode('utf-8-sig') for name, kind, data in ui_lua if name.lower() == 'includes')
    # This fingerprint was manually examined: its Lua GetDriveModeEnabled binding
    # passes zero to lua_pushboolean at RVA 0x45ecc5. It is NOT a general patch.
    known_hash = '99ae15860cfdbcdaad0f48e005eee21444046b21de848c1deab9367e8246a3c5'
    digest = hashlib.sha256(exe).hexdigest()
    return {
        'game_root': str(root.resolve()),
        'exe_sha256': digest,
        'pe_machine': hex(struct.unpack_from('<H', exe, pe_offset + 4)[0]),
        'examined_build': '3.2.2.0' if digest == known_hash else 'unverified',
        'drive_getter_static_result': 'constant false' if digest == known_hash else 'requires new analysis',
        'engine_config': (root / 'engine.lua').read_text().splitlines(),
        'engine_strings': {name: name in ascii_strings for name in names},
        'ui_controller_name_present': 'CONTROLLER_START_MENU' in ui,
        'ui_joystick_references': len(re.findall(r'joystick|gamepad|controller|GetDriveModeEnabled', ui, re.I)),
        'loads_M_lua_files': '"M_"' in includes,
        'ui_lua_resources': [{'name': name, 'type': hex(kind), 'bytes': len(data)} for name, kind, data in ui_lua],
        'runtime_controller_behavior': 'not yet verified',
    }


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('game_root', type=Path)
    args = parser.parse_args()
    print(json.dumps(inspect(args.game_root), indent=2))
