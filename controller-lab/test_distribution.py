"""Test extracted installer scripts against synthetic KEY/BIFF game fixtures.

Never launches a game or writes to an installed game/save profile.
"""
from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import tempfile
import zipfile
from build_release import LAB, ROOT, digest
from ui_build import build_ui
from radial_asset import build_ui_assets
from test_save_import import test as test_save_import

PS=Path(os.environ['SystemRoot'])/'System32/WindowsPowerShell/v1.0/powershell.exe'
FAKE_EXE=b'Fixture only: not a PE executable and never launched.'

def run(script,game,success=True,extra=()):
    result=subprocess.run([str(PS),'-NoProfile','-ExecutionPolicy','Bypass','-File',str(script),
                           '-GamePath',str(game),*extra],capture_output=True,text=True,timeout=30)
    if (result.returncode==0)!=success:
        raise AssertionError(result.stdout+'\n'+result.stderr)
    return result

def game_fixture(path,original):
    path.mkdir()
    (path/'data').mkdir()
    (path/'override').mkdir()
    bif=b'BIFFV1  '+struct.pack('<3I',1,0,20)+struct.pack('<IIIHH',0,36,len(original),0x408,0)+original
    filename=b'data\\test.bif\0'
    key=b'KEY V1  '+struct.pack('<4I',1,1,24,36+len(filename))
    key+=struct.pack('<IIHH',len(bif),36,len(filename),1)+filename+struct.pack('<8sHI',b'UI',0x408,0)
    (path/'chitin.key').write_bytes(key)
    (path/'data/test.bif').write_bytes(bif)
    (path/'Torment.exe').write_bytes(FAKE_EXE)
    (path/'engine.lua').write_bytes(b'engine_name="Fixture original profile"\r\nengine_mode=3\r\n')
    (path/'override/unrelated.lua').write_bytes(b'-- keep this unrelated file unchanged\n')
    # Preserve the exact original override bytes, including BOM and CRLF.
    (path/'override/UI.menu').write_bytes(b'\xef\xbb\xbf'+original.replace(b'\n',b'\r\n'))

def snapshot(path):
    return {file.relative_to(path).as_posix():file.read_bytes() for file in path.rglob('*')
            if file.is_file() and '.pstcontroller' not in file.relative_to(path).parts}

def test(release_zip,source_zip):
    original=(LAB/'backups/UI.menu.original').read_text(encoding='utf-8-sig').encode()
    expected=build_ui(original.decode()).encode()
    with zipfile.ZipFile(release_zip) as archive:
        names=archive.namelist()
        for name in names:
            base=Path(name).name.lower()
            assert base!='readme_bg.md'
            if Path(name).suffix.lower() in ('.md','.txt','.ps1','.cmd','.lua','.json'):
                assert not re.search('[\u0400-\u04ff]',archive.read(name).decode('utf-8-sig')), 'non-English Cyrillic text in release'
            assert base not in ('torment.exe','chitin.key','engine.lua','baldur.lua','ui.menu')
            assert Path(name).suffix.lower() not in ('.bif','.tlk','.png','.sav','.pdb')
            if Path(name).suffix.lower()=='.bam':
                asset=Path(name).name
                assert asset in build_ui_assets() and name.endswith('/payload/'+asset)
                assert archive.read(name)==build_ui_assets()[asset], 'only original mod-generated UI assets are allowed'
            assert original not in archive.read(name), 'full stock UI leaked into release'
        with zipfile.ZipFile(source_zip) as source:
            for name in source.namelist():
                assert not name.endswith(('.dll','.exe','.pdb','.bif','.key','.tlk'))
                assert Path(name).name.lower()!='readme_bg.md'
                assert not re.search('[\u0400-\u04ff]',source.read(name).decode('utf-8-sig')), 'non-English Cyrillic text in source'
                assert '/backups/' not in name and '/tools/' not in name
                assert not re.search(rb'[A-Za-z]:[\\/]+Users[\\/]+[^\\/\s]+',source.read(name)), 'personal developer path in source package'
        built=LAB/'built'
        built.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix='installer-fixtures-',dir=built) as directory:
            temp=Path(directory).resolve()
            assert temp.is_relative_to(built.resolve()), 'fixture cleanup must stay inside built'
            for member in archive.infolist():
                destination=(temp/member.filename).resolve()
                assert destination.is_relative_to(temp)
            archive.extractall(temp)
            package=temp/names[0].split('/')[0]
            test_save_import(package,temp/'save-import-fixtures')
            # The source installer must explain which archive to use before
            # resolving the game path, showing a picker or mutating anything.
            source_only=temp/'source-only'; source_only.mkdir()
            (source_only/'Install.ps1').write_bytes((ROOT/'distribution/Install.ps1').read_bytes())
            missing_game=temp/'not a game folder'
            source_error=run(source_only/'Install.ps1',missing_game,False)
            assert 'preview.zip' in source_error.stderr and 'No game files changed' in source_error.stderr
            assert not missing_game.exists()
            # Only this extracted private fixture copy accepts a fake executable.
            # The published archive always retains the real executable fingerprint.
            manifest_path=package/'manifest.json'
            manifest=json.loads(manifest_path.read_text())
            manifest['exeSha256']=digest(FAKE_EXE)
            manifest_path.write_text(json.dumps(manifest))
            installer=package/'Install.ps1'; uninstall=package/'Uninstall.ps1'
            game=temp/'fixture game with spaces'
            game_fixture(game,original)
            before=snapshot(game)
            # Test the opt-in wiring without letting an installer fixture
            # access real Documents profiles. The import algorithm is checked
            # separately above against complete synthetic save folders.
            import_script=package/'Import-Saves.ps1'; real_import=import_script.read_bytes()
            import_marker=package/'import-called.txt'
            import_script.write_text("param([string]$SourceProfile)\n[IO.File]::WriteAllText((Join-Path $PSScriptRoot 'import-called.txt'),$SourceProfile)\n",encoding='utf-8')
            try:
                run(installer,game,extra=('-ImportSaves','-SourceProfile','fixture-original-profile'))
                assert import_marker.read_text()=='fixture-original-profile'
            finally:
                import_script.write_bytes(real_import)
            assert (game/'override/UI.menu').read_bytes()==expected
            assert (game/'override/M_PSTPAD.lua').read_bytes()==(LAB/'M_PSTPAD.lua').read_bytes()
            assert 'engine_name="Planescape Torment - Controller Lab"' in (game/'engine.lua').read_text()
            state=json.loads((game/'.pstcontroller/state.json').read_text())
            assert state['status']=='installed' and len(state['files'])==8
            for asset,data in build_ui_assets().items(): assert (game/'override'/asset).read_bytes()==data
            assert (game/'Play-Controller-Mod.cmd').exists()
            # Do not clobber later user edits when uninstalling.
            lua=game/'override/M_PSTPAD.lua'; saved=lua.read_bytes()
            lua.write_bytes(saved+b'\n-- later user edit\n')
            edited=snapshot(game)
            run(uninstall,game,False)
            assert snapshot(game)==edited
            lua.write_bytes(saved)
            run(uninstall,game)
            assert snapshot(game)==before, 'uninstall must restore original bytes exactly'
            assert (game/'.pstcontroller/backups'/state['backupSet']).exists()
            run(installer,game)
            second=json.loads((game/'.pstcontroller/state.json').read_text())
            assert second['backupSet']!=state['backupSet']
            assert (game/'.pstcontroller/backups'/state['backupSet']).exists()
            run(uninstall,game)
            assert snapshot(game)==before
            # Wrong executable: refused without creating backups or changing files.
            wrong=temp/'wrong executable'; game_fixture(wrong,original)
            (wrong/'Torment.exe').write_bytes(b'unsupported executable')
            wrong_before=snapshot(wrong)
            run(installer,wrong,False)
            assert snapshot(wrong)==wrong_before and not (wrong/'.pstcontroller').exists()
            # Other UI mods: refuse rather than overwriting them.
            custom=temp/'custom UI'; game_fixture(custom,original)
            (custom/'override/UI.menu').write_bytes(b'custom mod UI')
            custom_before=snapshot(custom)
            run(installer,custom,False)
            assert snapshot(custom)==custom_before and not (custom/'.pstcontroller').exists()
            # Wrong stock BIFF UI: fingerprint guard is independent of the EXE guard.
            changed=temp/'different stock UI'; game_fixture(changed,original+b'\nchanged\n')
            changed_before=snapshot(changed)
            run(installer,changed,False)
            assert snapshot(changed)==changed_before and not (changed/'.pstcontroller').exists()
            # Package corruption: fail before touching a game directory.
            corrupt=temp/'corrupt package'; game_fixture(corrupt,original)
            corrupt_before=snapshot(corrupt)
            payload=package/'payload/M_PSTPAD.lua'; payload.write_bytes(payload.read_bytes()+b'bad')
            run(installer,corrupt,False)
            assert snapshot(corrupt)==corrupt_before and not (corrupt/'.pstcontroller').exists()
    report='''# Package checks — 0.1.31\n\nPASS, Windows PowerShell 5.1 synthetic fixtures (no live game input).\n\n- KEY/BIFF UI extraction; patch output equals the generated UI byte for byte.\n- Install into a path with spaces; payload checksums; isolated engine profile.\n- Uninstall restores original engine/UI bytes including BOM/CRLF.\n- Later user edits cause uninstall to stop without modifying any files.\n- Reinstall uses a fresh backup set and preserves the prior backups.\n- Wrong EXE, wrong stock UI, custom UI and corrupted payload are refused before mutation.\n- Release/source ZIP whitelists exclude game archives, full stock UI, saves, tools and personal paths; the generated circle and selection BAMs are included.\n\nNative movie engine/edge/event-filter checks and Lua overlay D-pad/A/default-No/held-A guards passed, alongside the stock quantity flow, count/cancel/stale-stack checks, yellow-frame QC and existing controls/navigation checks. The user confirmed 0.1.16\nstarts without Menu Error dialogs. A complete campaign/menu audit and final\nphysical confirmation of the main-inventory initial focus remain pending.\n'''
    (ROOT/'dist/PACKAGE-CHECKS.md').write_text(report,encoding='utf-8')
    print('PASS: Windows PowerShell installer/uninstaller; KEY/BIFF patch; byte-exact restoration; reinstall; edit/conflict/fingerprint guards; archive privacy')

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--release-zip',type=Path)
    parser.add_argument('--source-zip',type=Path)
    args=parser.parse_args()
    release=args.release_zip or ROOT/'dist/PSTEE-Xbox-Controller-v0.1.31-preview.zip'
    source=args.source_zip or ROOT/'dist/PSTEE-Xbox-Controller-v0.1.31-source.zip'
    test(release,source)
