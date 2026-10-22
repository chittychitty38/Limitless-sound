; Inno Setup script: builds "Limitless Zoom Setup.exe" from the PyInstaller folder.
#define AppVersion GetEnv("APP_VERSION")

[Setup]
AppName=Limitless Zoom
AppVersion={#AppVersion}
AppPublisher=Limitless Sound
DefaultDirName={autopf}\Limitless Zoom
DefaultGroupName=Limitless Zoom
OutputDir=..\dist
OutputBaseFilename=Limitless Zoom Setup
Compression=lzma2
SolidCompression=yes
PrivilegesRequired=lowest
WizardStyle=modern

[Tasks]
Name: "startup"; Description: "Start Limitless Zoom when I sign in"
Name: "desktopicon"; Description: "Create a desktop shortcut"

[Files]
Source: "..\dist\Limitless Zoom\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Limitless Zoom"; Filename: "{app}\Limitless Zoom.exe"
Name: "{userdesktop}\Limitless Zoom"; Filename: "{app}\Limitless Zoom.exe"; Tasks: desktopicon
Name: "{userstartup}\Limitless Zoom"; Filename: "{app}\Limitless Zoom.exe"; Tasks: startup

[Run]
Filename: "{app}\Limitless Zoom.exe"; Description: "Start Limitless Zoom now"; Flags: nowait postinstall skipifsilent
