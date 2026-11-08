#define AppName "Lumen Offline Profiles"
#define AppVersion "1.0.0"
#define AppExeName "LumenOffline.exe"

[Setup]
AppId={{B7F1F1E5-4A0A-4BF0-9C91-2B65C3B3D0A1}
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={autopf}\Lumen Offline Profiles
DefaultGroupName={#AppName}
OutputDir=..\dist
OutputBaseFilename=LumenOfflineSetup
Compression=lzma
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\assets\lumen-app.ico
ArchitecturesInstallIn64BitMode=x64compatible

[Files]
Source: "..\dist\LumenOffline\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\Lumen Offline Profiles"; Filename: "{app}\{#AppExeName}"
Name: "{commondesktop}\Lumen Offline Profiles"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Additional icons:"
