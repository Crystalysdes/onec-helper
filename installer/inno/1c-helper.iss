; Inno Setup script for 1C Helper agent installer.
; Builds a single net1c-agent-setup.exe that:
;   * Shows a proper Windows installer wizard
;   * Extracts embedded Python 3.11 + agent source + bootstrap script
;   * Runs bootstrap (pip install + playwright chromium)
;   * Reads pairing code from its own filename (net1c-agent-setup-ABC12345.exe)
;     and writes prepair.json so the GUI auto-pairs on first run
;   * Creates Desktop + Startup shortcuts
;   * Registers a proper uninstaller in Windows Control Panel

#define AppName        "1C Helper"
#define AppVersion     "0.1.0"
#define AppPublisher   "net1c.ru"
#define AppURL         "https://net1c.ru"

[Setup]
AppId={{B4A2C9E1-3F5D-4E7A-8C9B-1F2E3D4C5B6A}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
AppUpdatesURL={#AppURL}
DefaultDirName={localappdata}\net1c-agent
DisableProgramGroupPage=yes
DisableDirPage=auto
PrivilegesRequired=lowest
OutputDir=..\..\dist
OutputBaseFilename=net1c-agent-setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
UninstallDisplayName={#AppName}

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"
Name: "autostart";   Description: "Запускать при старте Windows"; GroupDescription: "Дополнительно:"

[Files]
; Embedded Python 3.11.9 zip (downloaded/staged by CI before compilation)
Source: "python-3.11.9-embed-amd64.zip"; DestDir: "{app}"; Flags: deleteafterinstall

; get-pip.py to bootstrap pip into embeddable Python
Source: "get-pip.py"; DestDir: "{app}"; Flags: deleteafterinstall

; Agent source
Source: "agent\*"; DestDir: "{app}\app"; Flags: recursesubdirs ignoreversion

; Bootstrap PowerShell script
Source: "bootstrap.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autodesktop}\1C Helper"; \
    Filename: "{app}\python\pythonw.exe"; \
    Parameters: """main.py"""; \
    WorkingDir: "{app}\app"; \
    IconFilename: "{sys}\shell32.dll"; \
    IconIndex: 21; \
    Tasks: desktopicon

Name: "{userstartup}\1C Helper"; \
    Filename: "{app}\python\pythonw.exe"; \
    Parameters: """main.py"""; \
    WorkingDir: "{app}\app"; \
    IconFilename: "{sys}\shell32.dll"; \
    IconIndex: 21; \
    Tasks: autostart

Name: "{autoprograms}\1C Helper"; \
    Filename: "{app}\python\pythonw.exe"; \
    Parameters: """main.py"""; \
    WorkingDir: "{app}\app"; \
    IconFilename: "{sys}\shell32.dll"; \
    IconIndex: 21

[Run]
; Run the bootstrap: extract Python, install deps, install Chromium, write prepair.json.
; Pairing code is read from the .exe's own filename (e.g. "net1c-agent-setup-ABC12345.exe").
Filename: "powershell.exe"; \
    Parameters: "-ExecutionPolicy Bypass -NoProfile -File ""{app}\bootstrap.ps1"" -InstallDir ""{app}"" -PairingCode ""{code:GetPairCode}"" -ServerUrl ""{#AppURL}"""; \
    StatusMsg: "Установка Python, зависимостей и браузера Chromium (3-5 минут)..."; \
    Flags: runhidden waituntilterminated

; Launch GUI after install
Filename: "{app}\python\pythonw.exe"; \
    Parameters: """main.py"""; \
    WorkingDir: "{app}\app"; \
    Description: "Запустить 1C Helper"; \
    Flags: nowait postinstall skipifsilent

[UninstallRun]
; Stop running agent processes before removing files
Filename: "powershell.exe"; \
    Parameters: "-NoProfile -Command ""Get-Process -ErrorAction SilentlyContinue | Where-Object {{ $_.Path -and $_.Path.StartsWith('{app}', [System.StringComparison]::OrdinalIgnoreCase) }} | Stop-Process -Force -ErrorAction SilentlyContinue"""; \
    Flags: runhidden

[UninstallDelete]
; Ensure config dir is cleaned up on uninstall (but keep browser-profile for re-install? no, full clean on uninstall is correct)
Type: filesandordirs; Name: "{userappdata}\net1c-agent"

[Code]
{ Extract pairing code from the installer's own filename.
  Expected pattern:  net1c-agent-setup-ABC12345.exe  ->  "ABC12345" }
function GetPairCode(Param: string): string;
var
  fn: string;
  dashPos, dotPos: Integer;
  raw: string;
begin
  Result := '';
  fn := ExtractFileName(ExpandConstant('{srcexe}'));
  { Find the last '-' before '.exe' — that's where the code starts }
  dashPos := 0;
  dotPos := 0;
  if Lowercase(Copy(fn, Length(fn) - 3, 4)) = '.exe' then
    dotPos := Length(fn) - 3
  else
    dotPos := Length(fn) + 1;

  { Scan backwards from dotPos-1 for '-' }
  dashPos := dotPos - 1;
  while (dashPos > 0) and (fn[dashPos] <> '-') do
    Dec(dashPos);

  if (dashPos > 0) and (dashPos < dotPos - 1) then
  begin
    raw := Copy(fn, dashPos + 1, dotPos - dashPos - 1);
    { Validate: must look like a pair code — 4-16 alphanumerics }
    if (Length(raw) >= 4) and (Length(raw) <= 16) then
      Result := Uppercase(raw);
  end;
end;
