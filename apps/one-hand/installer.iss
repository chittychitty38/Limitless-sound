; Inno Setup script: wraps LimitlessOneHand.exe in a normal Windows installer.
#define AppVersion GetEnv("APP_VERSION")
#if AppVersion == ""
  #define AppVersion "0.1.0"
#endif

[Setup]
AppId={{6E1F3C2A-8B47-4D0E-9C61-3A5F0B7D2E91}
AppName=Limitless One-Hand
AppVersion={#AppVersion}
AppPublisher=Limitless Sound
DefaultDirName={autopf}\Limitless One-Hand
DefaultGroupName=Limitless One-Hand
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=Limitless-One-Hand-windows
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Files]
Source: "dist\LimitlessOneHand.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Limitless One-Hand"; Filename: "{app}\LimitlessOneHand.exe"
Name: "{autodesktop}\Limitless One-Hand"; Filename: "{app}\LimitlessOneHand.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Put an icon on the desktop"

[Run]
Filename: "{app}\LimitlessOneHand.exe"; Description: "Open Limitless One-Hand now"; Flags: nowait postinstall skipifsilent
