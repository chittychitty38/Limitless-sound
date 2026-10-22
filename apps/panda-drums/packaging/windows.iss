; Panda Drums for Windows: the VST3 into the shared VST3 folder, the stand-alone app into Program Files.
#define AppVersion GetEnv("APP_VERSION")

[Setup]
AppId={{6F1E2B54-7A8C-4B8E-9C6D-50A11DA5D0C1}
AppName=Panda Drums
AppVersion={#AppVersion}
AppPublisher=The Panda Studios
DefaultDirName={autopf}\Panda Drums
DefaultGroupName=Panda Drums
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=Panda-Drums-Setup-windows
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\Panda Drums.exe
Compression=lzma2
SolidCompression=yes
WizardStyle=modern

[Components]
Name: "vst3"; Description: "VST3 plug-in (Ableton Live, FL Studio, Cubase, Studio One, Reaper...)"; Types: full compact custom; Flags: fixed
Name: "app"; Description: "Stand-alone app"; Types: full

[Files]
Source: "..\build\PandaDrums_artefacts\Release\VST3\Panda Drums.vst3\*"; DestDir: "{commoncf64}\VST3\Panda Drums.vst3"; Components: vst3; Flags: recursesubdirs ignoreversion
Source: "..\build\PandaDrums_artefacts\Release\Standalone\Panda Drums.exe"; DestDir: "{app}"; Components: app; Flags: ignoreversion

[Icons]
Name: "{group}\Panda Drums"; Filename: "{app}\Panda Drums.exe"; Components: app
