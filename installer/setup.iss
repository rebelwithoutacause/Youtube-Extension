; Inno Setup script for YouTube Content Research Tool.
; Build the exe first (python scripts\build.py) — it also generates
; installer\version.iss (#define AppVersion) consumed below.
; Compile with: ISCC installer\setup.iss

#define AppName "YouTube Content Research Tool"
#define AppPublisher "rebelwithoutacause"
#define AppURL "https://github.com/rebelwithoutacause/Youtube-Extension"
#define AppExeName "YouTubeContentResearch.exe"
#include "version.iss"

[Setup]
AppId={{7BE91303-3374-402F-B6AA-0D2C413CAFF0}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
OutputDir=Output
OutputBaseFilename=YouTubeContentResearchSetup-{#AppVersion}
SetupIconFile=..\assets\app.ico
UninstallDisplayIcon={app}\{#AppExeName}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible
DisableWelcomePage=no

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional shortcuts:"

[Files]
Source: "..\dist\{#AppExeName}"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\extension\*"; DestDir: "{app}\extension"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{group}\Browser Extension Folder"; Filename: "{app}\extension"
Name: "{group}\README"; Filename: "{app}\README.md"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "Launch {#AppName}"; Flags: postinstall skipifsilent nowait
Filename: "{app}\extension"; Description: "Open the extension folder (for Chrome/Edge ""Load unpacked"")"; Flags: postinstall shellexec skipifsilent unchecked
Filename: "{app}\README.md"; Description: "View the README"; Flags: postinstall shellexec skipifsilent unchecked

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
var
  ApiKeyPage: TInputQueryWizardPage;

procedure InitializeWizard;
begin
  ApiKeyPage := CreateInputQueryPage(wpSelectDir,
    'Configure your YouTube API key',
    'This app needs your own free YouTube Data API v3 key(s) — no key is bundled.',
    'Get a free key at https://console.cloud.google.com (enable "YouTube Data API v3", ' +
    'then create an API key under Credentials). You can enter up to three keys for ' +
    'automatic key rotation once one hits its daily quota.' + #13#10 + #13#10 +
    'You can leave this blank and set it up later — the app will ask for a key the ' +
    'first time you run it.');
  ApiKeyPage.Add('Primary API key:', False);
  ApiKeyPage.Add('Second API key (optional):', False);
  ApiKeyPage.Add('Third API key (optional):', False);
end;

function BuildKeyList: String;
var
  Keys: String;
  I: Integer;
  Value: String;
begin
  Keys := '';
  for I := 0 to 2 do
  begin
    Value := Trim(ApiKeyPage.Values[I]);
    if Value <> '' then
    begin
      if Keys <> '' then
        Keys := Keys + ',';
      Keys := Keys + Value;
    end;
  end;
  Result := Keys;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ConfigDir, ConfigFile, Keys: String;
begin
  if CurStep = ssPostInstall then
  begin
    Keys := BuildKeyList;
    if Keys <> '' then
    begin
      ConfigDir := ExpandConstant('{userappdata}\YouTubeContentResearch');
      ForceDirectories(ConfigDir);
      ConfigFile := ConfigDir + '\.env';
      SaveStringToFile(ConfigFile, 'YOUTUBE_API_KEYS=' + Keys + #13#10, False);
    end;
  end;
end;

function InitializeUninstall(): Boolean;
begin
  Result := True;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  ConfigDir: String;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    ConfigDir := ExpandConstant('{userappdata}\YouTubeContentResearch');
    if DirExists(ConfigDir) then
    begin
      if MsgBox('Also remove your saved YouTube API key configuration (' + ConfigDir + ')?',
                mbConfirmation, MB_YESNO) = IDYES then
        DelTree(ConfigDir, True, True, True);
    end;
  end;
end;
