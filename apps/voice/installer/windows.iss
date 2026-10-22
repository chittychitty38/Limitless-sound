; Inno Setup script: turns dist\Limitless Voice\ into LimitlessVoiceSetup.exe
; Built by CI: iscc /DAppVersion=0.2.0 installer\windows.iss

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif

[Setup]
AppId={{6E0C7F1A-3D2B-4F7E-9C51-5B0A1D2E7C44}
AppName=Limitless Voice
AppVersion={#AppVersion}
AppPublisher=Limitless Sound
DefaultDirName={autopf}\Limitless Voice
DefaultGroupName=Limitless Voice
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=LimitlessVoiceSetup-{#AppVersion}
SetupIconFile=..\limitless_voice\assets\icon.ico
UninstallDisplayIcon={app}\LimitlessVoice.exe
Compression=lzma2
SolidCompression=yes
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Put an icon on the desktop"; GroupDescription: "Shortcuts:"
Name: "startup"; Description: "Start Limitless Voice when I sign in"; GroupDescription: "Shortcuts:"; Flags: unchecked

[Files]
Source: "..\dist\Limitless Voice\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Limitless Voice"; Filename: "{app}\LimitlessVoice.exe"
Name: "{autodesktop}\Limitless Voice"; Filename: "{app}\LimitlessVoice.exe"; Tasks: desktopicon
Name: "{userstartup}\Limitless Voice"; Filename: "{app}\LimitlessVoice.exe"; Tasks: startup

[Run]
Filename: "{app}\LimitlessVoice.exe"; Description: "Open Limitless Voice now"; Flags: nowait postinstall skipifsilent
