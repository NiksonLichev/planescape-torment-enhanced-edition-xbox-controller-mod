"""Build mod-only Windows installer and source ZIPs from a user-owned game."""
from pathlib import Path
import argparse
import base64
import difflib
import hashlib
import json
import re
import zipfile
from inspect_game import resources
from ui_build import build_ui
from radial_asset import build_ui_assets

LAB=Path(__file__).resolve().parent
ROOT=LAB.parent
EXPECTED_EXE='99ae15860cfdbcdaad0f48e005eee21444046b21de848c1deab9367e8246a3c5'
DOCS=('README.md','CONTROLS.md','RELEASE-NOTES.md')
INSTALLER=('Common.ps1','Install.ps1','Uninstall.ps1','Install.cmd','Uninstall.cmd',
           'Import-Saves.ps1','Import-Saves.cmd')
SOURCES=('M_PSTPAD.lua','ui_build.py','ui_resources.py','menu_navigation.py','radial_asset.py',
         'inspect_game.py','Build-Plugin.ps1','build_release.py',
         'test_controls.py','test_menu_navigation.py','test_distribution.py','test_save_import.py',
         'README.md','PROTOTYPE.md','MENU-CHECKS.md')
NATIVE=('pstcontroller.c','nearby_targets.h','controller_loader.c','test_native.c')

def digest(data):
    return hashlib.sha256(data).hexdigest()

def make_patch(original,target):
    """A delta of byte spans; unchanged game UI is never included in a release."""
    left=original.splitlines(keepends=True)
    right=target.splitlines(keepends=True)
    offsets=[0]
    for line in left:
        offsets.append(offsets[-1]+len(line))
    hunks=[]
    for tag,a,b,c,d in difflib.SequenceMatcher(None,left,right,autojunk=False).get_opcodes():
        if tag!='equal':
            hunks.append({'start':offsets[a],'delete':offsets[b]-offsets[a],
                          'insert':base64.b64encode(b''.join(right[c:d])).decode('ascii')})
    return {'format':1,'sourceSha256':digest(original),'targetSha256':digest(target),'hunks':hunks}

def write_zip(path,name,files):
    with zipfile.ZipFile(path,'w',zipfile.ZIP_DEFLATED,compresslevel=9) as archive:
        for relative,data in sorted(files.items()):
            if relative.startswith('/') or '..' in Path(relative).parts:
                raise ValueError('Unsafe package path')
            # Fixed metadata gives repeatable ZIPs for the same inputs.
            info=zipfile.ZipInfo(name+'/'+relative,date_time=(2026,10,14,0,0,0))
            info.compress_type=zipfile.ZIP_DEFLATED
            info.external_attr=0o644<<16
            archive.writestr(info,data)

def build(game,out):
    if digest((game/'Torment.exe').read_bytes())!=EXPECTED_EXE:
        raise ValueError('Unsupported Torment.exe fingerprint; no release built')
    text=next(data.decode('utf-8-sig').replace('\r\n','\n').replace('\r','\n')
              for name,kind,data in resources(game) if name=='UI' and kind==0x408)
    original=text.encode('utf-8')
    target=build_ui(text).encode('utf-8')
    version=re.search(r"version\s*=\s*'([0-9.]+)'",(LAB/'M_PSTPAD.lua').read_text())[1]
    patch=make_patch(original,target)
    release={name:(ROOT/'distribution'/name).read_bytes() for name in DOCS+INSTALLER}
    release.update({
        'payload/M_PSTPAD.lua':(LAB/'M_PSTPAD.lua').read_bytes(),
        'payload/pstcontroller.dll':(LAB/'native/pstcontroller.dll').read_bytes(),
        'payload/ControllerLab.exe':(LAB/'native/ControllerLab.exe').read_bytes(),
        'payload/ui-patch.json':json.dumps(patch,separators=(',',':')).encode(),
    })
    release.update({'payload/'+name:data for name,data in build_ui_assets().items()})
    manifest={'version':version,'preview':True,'exeSha256':EXPECTED_EXE,
              'payload':[{'path':name,'sha256':digest(data)} for name,data in sorted(release.items()) if name.startswith('payload/')]}
    release['manifest.json']=json.dumps(manifest,indent=2).encode()
    source={name:(ROOT/'distribution'/name).read_bytes() for name in DOCS}
    source['.gitignore']=(ROOT/'distribution/gitignore.template').read_bytes()
    source.update({'controller-lab/'+name:(LAB/name).read_bytes() for name in SOURCES})
    source.update({'controller-lab/native/'+name:(LAB/'native'/name).read_bytes() for name in NATIVE})
    source.update({'distribution/'+name:(ROOT/'distribution'/name).read_bytes() for name in DOCS+INSTALLER+('gitignore.template',)})
    for name in DOCS:
        if version not in source[name].decode('utf-8') and name!='CONTROLS.md':
            raise ValueError('Release documentation version is stale: '+name)
    out.mkdir(parents=True,exist_ok=True)
    name='PSTEE-Xbox-Controller-v'+version
    release_zip=out/(name+'-preview.zip')
    source_zip=out/(name+'-source.zip')
    write_zip(release_zip,name,release)
    write_zip(source_zip,name+'-source',source)
    sums=''.join(digest(path.read_bytes())+'  '+path.name+'\n' for path in (release_zip,source_zip))
    (out/'SHA256SUMS.txt').write_text(sums,encoding='ascii')
    # Local-only stock fixture for developers; deliberately excluded by whitelist.
    backup=LAB/'backups/UI.menu.original'
    if not backup.exists():
        backup.parent.mkdir(parents=True,exist_ok=True)
        backup.write_bytes(original)
    print(f'Built {version}: {len(patch["hunks"])} UI hunks; no stock UI/game archives bundled')
    for path in (release_zip,source_zip,out/'SHA256SUMS.txt'):
        print(path)
    return release_zip,source_zip

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game-dir',type=Path,required=True)
    parser.add_argument('--out-dir',type=Path,default=ROOT/'dist')
    args=parser.parse_args()
    build(args.game_dir,args.out_dir)
