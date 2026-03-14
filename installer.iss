#define AppName "Clipart Generator"
#ifndef AppVersion
  #define AppVersion "0.2.5"
#endif
#define AppPublisher "Clipart Generator"
#define AppExeName "Clipart Generator.exe"

[Setup]
AppId={{B8D6B3F4-4E5F-4B6E-9D13-9A8E3B2F3C7A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma
SolidCompression=yes
WizardStyle=modern
OutputDir=release
OutputBaseFilename=ClipartGenerator-Setup-{#AppVersion}
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"

[Tasks]
Name: "desktopicon"; Description: "Ð¡Ð¾Ð·Ð´Ð°Ñ‚ÑŒ ÑÑ€Ð»Ñ‹Ðº Ð½Ð° Ñ€Ð°Ð±Ð¾Ñ‡ÐµÐ¼ ÑÑ‚Ð¾Ð»Ðµ"; GroupDescription: "Ð”Ð¾Ð¿Ð¾Ð»Ð½Ð¸Ñ‚ÐµÐ»ÑŒÐ½Ñ‹Ðµ Ð·Ð°Ð´Ð°Ñ‡Ð¸:"; Flags: unchecked

[Files]
Source: "dist\Clipart Generator\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Ð—Ð°Ð¿ÑƒÑÑ‚Ð¸Ñ‚ÑŒ {#AppName}"; Flags: nowait postinstall skipifsilent

