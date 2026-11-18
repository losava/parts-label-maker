; Per-user Parts Label installer. No administrator rights required.
; Build with:  ISCC /DMyAppVersion=1.0.0 packaging\windows\parts_label.iss
; The version passed on the command line must match version.py.

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

#define MyAppName "Parts Label"
#define MyAppPublisher "losava"
#define MyAppURL "https://github.com/losava/parts-label-maker"
#define MyAppExeName "PartsLabel.exe"

[Setup]
AppId={{8F4E2C1A-6B7D-4E9A-9C3F-1D5A7B2E4F60}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}/releases
DefaultDirName={localappdata}\Parts Label
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\..\dist
OutputBaseFilename=PartsLabel-Setup-{#MyAppVersion}
SetupIconFile=..\parts-label.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
CloseApplications=yes
RestartApplications=no
UsePreviousAppDir=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Files]
Source: "..\..\dist\PartsLabel\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{userprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent

; User data (%APPDATA%\PartsLabel) is intentionally not removed.
; The parts list usually lives in the shop LABEL MAKER folder and must survive uninstall.
