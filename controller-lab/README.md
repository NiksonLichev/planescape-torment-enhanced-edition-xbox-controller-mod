# Controller Lab - developer workspace

Current release: **0.1.31**. Read the public [README](../distribution/README.md)
and [controls](../distribution/CONTROLS.md) for installation and gameplay.
[PROTOTYPE.md](PROTOTYPE.md) describes the implementation and guard conditions;
[MENU-CHECKS.md](MENU-CHECKS.md) records the current navigation check scope.

Use a separate writable game copy and the Controller Lab profile. Never use the
original game installation as a development target. The launcher checks the
supported executable and loads the native bridge; Torment.exe is unchanged on disk.

The stock GetDriveModeEnabled binding returns constant false on the examined
Windows executable. INI joystick/drive switches alone do not enable the console
controller interface. This mod supplies its own XInput/Lua/UI bridge.

Build native code with Build-Plugin.ps1 -Check, generate packages with
build_release.py --game-dir, and run test_menu_navigation.py plus
test_distribution.py. Local tools, stock fixtures, copied game data, backups,
logs and save profiles are excluded from public packages.
