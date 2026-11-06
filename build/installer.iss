; Inno Setup script. Per-user install (no admin rights) = smaller attack surface.
#define AppName "Lumen Launcher"
#define AppVersion "0.3.0"

[Setup]
AppName={#AppName}
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Lumen
PrivilegesRequired=lowest
OutputBaseFilename=LumenSetup-{#AppVersion}
OutputDir=..\dist\installer
Compression=lzma2
SolidCompression=yes
; SignTool=signtool   ; configure your code-signing cert in Inno's IDE or ISCC /S

[Files]
Source: "..\dist\Lumen\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\Lumen.exe"

[Run]
Filename: "{app}\Lumen.exe"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
