"""Exercise packaged save import only against temporary synthetic profiles."""
from pathlib import Path
import os
import subprocess

PS = Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe'

def tree(folder):
    return {p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob('*') if p.is_file()}

def slot(profile, name, data):
    folder = profile / 'save' / name
    folder.mkdir(parents=True)
    (folder / 'BALDUR.gam').write_bytes(data + b'game')
    (folder / 'BALDUR.SAV').write_bytes(data + b'archive')
    (folder / 'BALDUR.bmp').write_bytes(data + b'preview')
    (folder / 'nested').mkdir()
    (folder / 'nested/extra.dat').write_bytes(data + b'extra')
    return folder

def test(package, temporary):
    temporary.mkdir()
    tools = temporary / 'tools'; tools.mkdir()
    script = tools / 'Import-Saves.ps1'
    script.write_bytes((package / 'Import-Saves.ps1').read_bytes())
    common = (package / 'Common.ps1').read_text(encoding='utf-8-sig')
    # The fixture's process table is isolated from desktop games. The public
    # package continues to use the real process check.
    fake_processes = "\nfunction Get-Process { param($Name,$ErrorAction) @() }\n"
    (tools / 'Common.ps1').write_text(common + fake_processes, encoding='utf-8')
    source = temporary / 'original profile'; source.mkdir()
    target = temporary / 'controller profile'; target.mkdir()
    (source / 'Baldur.lua').write_bytes(b'original settings')
    (target / 'Baldur.lua').write_bytes(b'controller settings')
    slot(source, '000000001-Quick-Save', b'original quick ')
    slot(source, '000000012-manual', b'original manual ')
    existing = slot(target, '000000001-Quick-Save', b'controller progress ')
    incomplete = source / 'save/000000013-incomplete'; incomplete.mkdir()
    (incomplete / 'BALDUR.gam').write_bytes(b'incomplete')
    before_source, before_existing = tree(source), tree(existing)

    def run(src=source, dst=target, success=True):
        result = subprocess.run([str(PS), '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(script),
                                 '-SourceProfile', str(src), '-DestinationProfile', str(dst)],
                                capture_output=True, text=True, timeout=30)
        assert (result.returncode == 0) == success, result.stdout + result.stderr
        return result

    result = run()
    assert 'Copied 2 save(s)' in result.stdout
    assert tree(source) == before_source and tree(existing) == before_existing
    assert (target / 'Baldur.lua').read_bytes() == b'controller settings'
    saves = list((target / 'save').iterdir()); assert len(saves) == 3
    imported = [p for p in saves if p != existing]
    assert any(tree(p) == tree(source / 'save/000000001-Quick-Save') for p in imported)
    assert any(tree(p) == tree(source / 'save/000000012-manual') for p in imported)
    assert not any(p.name.startswith('.pstcontroller') for p in saves)
    before_target = tree(target)
    result = run()
    assert 'Copied 0 save(s); skipped 2 identical save(s)' in result.stdout
    assert tree(target) == before_target and tree(source) == before_source
    run(src=source, dst=source, success=False)
    assert tree(source) == before_source
    missing_target = temporary / 'must remain absent'
    run(src=temporary / 'missing source', dst=missing_target, success=False)
    assert not missing_target.exists()
    (tools / 'Common.ps1').write_text(common + "\nfunction Get-Process { param($Name,$ErrorAction) 1 }\n", encoding='utf-8')
    result = run(success=False)
    assert 'Close Planescape Torment' in result.stderr and tree(target) == before_target
    assert tree(source) == before_source
    print('PASS: save import copies complete slots, preserves both profiles/settings, renumbers collisions, skips identical reruns and refuses active game/same profile')
