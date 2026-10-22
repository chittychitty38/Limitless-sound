; Inno Setup: "Limitless-Sound-Setup-windows.exe" from the PyInstaller folder.
#ifndef AppVersion
  #define AppVersion "0.2.0"
#endif

[Setup]
AppId={{0E3B7B7C-3C61-4F4D-9B0C-1D5A6B2E7F10}
AppName=Limitless Sound
AppVersion={#AppVersion}
AppPublisher=Limitless Sound
DefaultDirName={autopf}\Limitless Sound
DefaultGroupName=Limitless Sound
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=Limitless-Sound-Setup-windows
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Limitless Sound.exe

[Tasks]
Name: "startup"; Description: "Start Limitless Sound when I sign in (recommended, so every app can link up)"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Add a desktop shortcut"; GroupDescription: "Options:"

[Files]
Source: "..\dist\Limitless Sound\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Limitless Sound"; Filename: "{app}\Limitless Sound.exe"
Name: "{autodesktop}\Limitless Sound"; Filename: "{app}\Limitless Sound.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Limitless Sound"; ValueData: """{app}\Limitless Sound.exe"" --background"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\Limitless Sound.exe"; Description: "Open Limitless Sound now"; Flags: nowait postinstall skipifsilent
