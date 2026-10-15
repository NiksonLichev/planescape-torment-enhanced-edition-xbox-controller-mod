# PST:EE Xbox Controller Mod - preview 0.1.31

Xbox/XInput controller support for Planescape: Torment Enhanced Edition on
Windows x64: character and party movement, camera control, nearby interaction,
dialogue, menu navigation and a compact two-page radial menu.

**[Complete controls](CONTROLS.md)** | **[Release notes](RELEASE-NOTES.md)**

## Download

[**Download v0.1.31 for Windows — ready to install**](https://github.com/NiksonLichev/planescape-torment-enhanced-edition-xbox-controller-mod/releases/download/v0.1.31/PSTEE-Xbox-Controller-v0.1.31-preview.zip)

Extract the complete ZIP and run **Install.cmd**.

The source ZIP is for developers and is not a ready-to-install package.
## Screenshots

<img width="1919" height="1079" alt="Screenshot 2026-10-15 164750" src="https://github.com/user-attachments/assets/43535f1c-fd88-41dd-8664-3f98a46e8fba" />
<img width="1919" height="1079" alt="Screenshot 2026-10-15 164739" src="https://github.com/user-attachments/assets/b5bbfcef-6fea-4130-ae13-04763a76fe40" />


## Install and start

1. Make a writable copy of your own game folder. Keep the original installation.
2. Close that copy. Extract the **entire preview ZIP** into a separate folder.
   Keep Install.cmd, Install.ps1, Common.ps1, manifest.json and payload together.
3. Run **Install.cmd from the extracted preview folder**. Select the game
   folder containing Torment.exe, not the mod's source or payload folder.
   Alternatively: `Install.cmd -GamePath "D:\Games\PSTEE-copy"`.
4. For Steam, set the game's controller option to **Disable Steam Input** to
   avoid intercepted or duplicate keyboard/mouse input.
5. In the selected game folder, start **Play-Controller-Mod.cmd** or
   **ControllerLab.exe**. Starting Torment.exe directly does not load the bridge.
6. Press and release A once, then release all controls to activate Xbox mode.
   The activation press is consumed. Press A again for an action; Y opens the radial.

No Python or compiler is needed to install the preview. The installer verifies
the supported executable, reads stock UI from the user's own KEY/BIFF resources,
applies the UI delta and keeps replaced files in `.pstcontroller/backups`.
Torment.exe is not modified on disk. A successful installation creates the
launcher, override files, Play-Controller-Mod.cmd and `.pstcontroller/state.json`.

If a source-only or incomplete archive is used, installation stops before
selecting or modifying a game folder and explains which ZIP is required.

## Saves and the separate profile

**The separate profile is intentional.** The selected game copy uses
**Documents/Planescape Torment - Controller Lab** for settings and saves.
The installer changes engine.lua in that copy; original saves are not deleted,
moved or imported. They will not automatically appear in the new profile.

During interactive installation, choose **Yes** when asked to copy existing
local saves. Choose **No** to keep a fresh Controller Lab profile. With a supplied
GamePath, use **-ImportSaves** to copy or **-SkipSaveImport** to skip the prompt.

You can import later: close the game and run **Import-Saves.cmd** from the
extracted preview folder. It copies complete local slots from
Documents/Planescape Torment - Enhanced Edition into the Controller Lab save
folder. Original saves, existing target saves, Baldur.lua and cloud files are
kept. Name collisions receive a free slot number; identical copies are skipped
on later runs. Each copied file is verified before its slot becomes visible.

For a different original profile, run:

```powershell
.\Import-Saves.ps1 -SourceProfile "D:\Profiles\My original PSTEE profile"
```

This copies local save folders rather than cloud-only entries. Copies are
independent: progress made with the controller does not alter the original save.
Modded copies using this same profile name share its settings and saves.

## Switch between PC and controller

A **real mouse click** returns to PC controls and releases controller movement.
Press and release a controller button or trigger, then release all controls,
to return to Xbox mode. Moving the mouse, typing or moving a stick alone does
not change modes. Mode switches have no top-screen status text.

## Upgrade or uninstall

Close the game. Run **Uninstall.cmd** from the preview folder and select the
same copy. Then install the new preview. The uninstaller restores original
files and keeps backups and the separate save profile. If installed files were
edited later, it stops rather than overwriting those edits. Preserve backups
for manual recovery. Do not delete `.pstcontroller` to bypass an install error.

## Compatibility and limits

- Supported executable: Windows x64 PST:EE **3.2.2.0**, SHA-256
  `99ae15860cfdbcdaad0f48e005eee21444046b21de848c1deab9367e8246a3c5`.
  Other Steam/GOG executable fingerprints are refused until examined.
- Xbox/XInput controllers. Linux/Proton, Steam Deck and other controller APIs
  have not been verified.
- Requires stock UI; other custom UI mods are not merged automatically.
- Main controls have automated checks and selected in-game validation. A full
  campaign/menu playtest is still pending. Text entry uses the keyboard; some
  advanced operations may need the menu cursor or temporary PC mode.
- Local loader/runtime logs are written for diagnosis. The top status line is hidden.

If controls do not respond, check the launcher used, game focus, controller
connection and Steam Input setting. For a Menu Error, keep its exact text and
mod version. Diagnostic reports can include controller-loader.log and
controller-runtime.log after removing personal information.

## Build from source

Use the source ZIP as a project, not an installer. With Python 3.10+ and Zig 0.15.2:

```powershell
.\controller-lab\Build-Plugin.ps1 -Check -CompilerPath C:\tools\zig\zig.exe
python -B controller-lab\build_release.py --game-dir "D:\Games\PSTEE-copy"
```

The builder reads your own supported game, creates the preview/source ZIPs and
SHA256SUMS.txt in dist, and keeps stock fixtures out of both archives.
For Lua checks, install `lupa==2.8` into controller-lab/tools/python, then run:

```powershell
python -m pip install --target controller-lab/tools/python lupa==2.8
python -B controller-lab/test_menu_navigation.py
python -B controller-lab/test_distribution.py
```

## Credits

Created by NiksonLichev with development assistance from OpenAI Codex.
