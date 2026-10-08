#define MyAppName "MarketAI"
#define MyAppVersion "1.0.3"
#define MyAppPublisher "MarketAI Community"
#define MyAppExeName "MarketAI.exe"

[Setup]
AppId={{4F4209D1-15F2-4DBE-A493-91C47AE1963D}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir=..\dist-installer
OutputBaseFilename=MarketAI-Setup-v{#MyAppVersion}
SetupIconFile=..\marketai.ico
UninstallDisplayIcon={app}\{#MyAppExeName}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=yes
UsePreviousAppDir=yes
UsePreviousGroup=yes
UsePreviousTasks=yes
VersionInfoVersion=1.0.3.0
VersionInfoCompany={#MyAppPublisher}
VersionInfoDescription=MarketAI Community - Inteligência Comercial
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
MinVersion=10.0.17763
LicenseFile=..\..\LICENSE
InfoBeforeFile=..\docs\PRIVACIDADE.txt
InfoAfterFile=..\docs\RELEASE-NOTES.txt
AppMutex=Local\MarketAI.Desktop.v1.0
UninstallDisplayName=MarketAI v1.0.3 Community

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos adicionais:"; Flags: unchecked

[Files]
Source: "..\dist\MarketAI.exe"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\.env.example"; DestDir: "{app}"; Flags: ignoreversion
Source: "..\..\LICENSE"; DestDir: "{app}\docs"; DestName: "LICENSE.txt"; Flags: ignoreversion
Source: "..\docs\PRIVACIDADE.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\TERCEIROS.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\RELEASE-NOTES.txt"; DestDir: "{app}\docs"; Flags: ignoreversion
Source: "..\docs\CHECKLIST-COMERCIAL.txt"; DestDir: "{app}\docs"; Flags: ignoreversion

[Icons]
Name: "{group}\MarketAI"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\{#MyAppExeName}"
Name: "{group}\Licença Open Source"; Filename: "{app}\docs\LICENSE.txt"
Name: "{group}\Política de Privacidade"; Filename: "{app}\docs\PRIVACIDADE.txt"
Name: "{group}\Notas da versão"; Filename: "{app}\docs\RELEASE-NOTES.txt"
Name: "{group}\Desinstalar MarketAI"; Filename: "{uninstallexe}"
Name: "{autodesktop}\MarketAI"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir MarketAI"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[Code]
function InitializeSetup(): Boolean;
begin
  Result := True;
end;
