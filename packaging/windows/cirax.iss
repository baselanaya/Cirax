; Cirax Windows installer (Inno Setup 6)
; Build:  iscc /DAPPVER=0.6.0 packaging\windows\cirax.iss
; (/DAPPVER is required — CI always passes it)
; Expects dist\cirax.exe (CLI) and dist\cirax-app\ (GUI onedir) to exist.

#ifndef AppVer
#error Pass /DAPPVER=x.y.z
#endif

[Setup]
AppId={{7C1A2E64-9B3D-4F5A-8E2C-A1B2C3D4E5F6}}
AppName=Cirax
AppVersion={#AppVer}
AppPublisher=Basel Anaya
AppPublisherURL=https://github.com/baselanaya/Cirax
AppSupportURL=https://github.com/baselanaya/Cirax/issues
DefaultDirName={autopf}\Cirax
PrivilegesRequired=lowest
DefaultGroupName=Cirax
DisableProgramGroupPage=yes
OutputDir=..\..\dist\packages
OutputBaseFilename=Cirax-Setup-{#AppVer}-win64
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=..\..\assets\cirax.ico
UninstallDisplayIcon={app}\cirax.ico
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"
Name: "pathentry"; Description: "Add Cirax to your PATH (recommended)"; \
    GroupDescription: "Integration:"

[Files]
Source: "..\..\dist\cirax.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\dist\cirax-app\*"; DestDir: "{app}\cirax-app"; \
    Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\..\assets\cirax.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\Cirax"; Filename: "{app}\cirax-app\cirax-app.exe"
Name: "{group}\Cirax CLI help"; Filename: "{cmd}"; \
    Parameters: "/k cirax --help"; Tasks: pathentry
Name: "{autodesktop}\Cirax"; Filename: "{app}\cirax-app\cirax-app.exe"; \
    Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Environment"; ValueType: expandsz; \
    ValueName: "Path"; ValueData: "{olddata};{app}"; \
    Tasks: pathentry; Check: NeedsAddPath('{app}')

[Run]
Filename: "{app}\cirax-app\cirax-app.exe"; \
    Description: "{cm:LaunchProgram,Cirax}"; Flags: nowait postinstall skipifsilent

[Code]
function NeedsAddPath(Param: string): boolean;
var
  OrigPath: string;
  AppDir: string;
begin
  AppDir := ExpandConstant(Param);
  if not RegQueryStringValue(HKEY_CURRENT_USER,
      'Environment', 'Path', OrigPath) then
  begin
    Result := True;
    exit;
  end;
  Result := Pos(';' + Uppercase(AppDir) + ';',
                ';' + Uppercase(OrigPath) + ';') = 0;
end;
