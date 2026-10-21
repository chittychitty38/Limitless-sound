; Windows installer for Limitless Control (Inno Setup 6).
; Built by CI:  iscc /DMyVersion=0.1.0 packaging\windows\installer.iss

#ifndef MyVersion
  #define MyVersion "0.1.0"
#endif

[Setup]
AppId={{6B0E6C1A-6F3D-4C55-9B64-5C1A7E1B2D40}
AppName=Limitless Control
AppVersion={#MyVersion}
AppPublisher=Limitless Sound
DefaultDirName={autopf}\Limitless Control
DefaultGroupName=Limitless Control
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=LimitlessControl-{#MyVersion}-Windows-Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\Limitless Control.exe

[Tasks]
Name: "startup"; Description: "Start Limitless Control when I sign in to Windows"; GroupDescription: "Options:"
Name: "desktopicon"; Description: "Add a desktop shortcut"; GroupDescription: "Options:"

[Files]
Source: "..\..\dist\Limitless Control\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Limitless Control"; Filename: "{app}\Limitless Control.exe"
Name: "{autodesktop}\Limitless Control"; Filename: "{app}\Limitless Control.exe"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "Limitless Control"; ValueData: """{app}\Limitless Control.exe"" --background"; Flags: uninsdeletevalue; Tasks: startup

[Run]
Filename: "{app}\Limitless Control.exe"; Description: "Open Limitless Control now"; Flags: nowait postinstall skipifsilent
