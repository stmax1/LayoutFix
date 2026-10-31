; Установщик LayoutFix (Inno Setup 6)
; Сборка: build.bat  или  ISCC.exe installer.iss /DMyAppVersion=1.0.0

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif
#define MyAppName "LayoutFix"
#define MyAppExe  "LayoutFix.exe"
#define MyAppPublisher "Maxim"

[Setup]
AppId={{6E1B6B0C-2E7A-4D1F-9C55-3B8F0E5A7D21}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; по умолчанию ставится без прав администратора (в профиль пользователя),
; при желании можно выбрать установку для всех пользователей
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
OutputDir=output
OutputBaseFilename={#MyAppName}-Setup-{#MyAppVersion}
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes
RestartApplications=no

[Languages]
Name: "russian"; MessagesFile: "compiler:Languages\Russian.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "autostart"; Description: "Запускать LayoutFix вместе с Windows"; GroupDescription: "Дополнительно:"
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "Дополнительно:"; Flags: unchecked

[Files]
Source: "dist\{#MyAppName}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Настройки {#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--settings"
Name: "{group}\Удалить {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
; автозапуск (то же значение переключается галочкой в настройках программы)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; \
  ValueName: "{#MyAppName}"; ValueData: """{app}\{#MyAppExe}"""; Flags: uninsdeletevalue; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExe}"; Parameters: "--settings"; Description: "Запустить {#MyAppName} и открыть настройки"; \
  Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExe}"; Flags: runhidden; RunOnceId: "KillApp"

[UninstallDelete]
Type: filesandordirs; Name: "{userappdata}\{#MyAppName}"

[Code]
// Закрываем запущенную копию перед установкой/обновлением
function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  ResultCode: Integer;
begin
  Exec(ExpandConstant('{sys}\taskkill.exe'), '/F /IM {#MyAppExe}', '', SW_HIDE,
       ewWaitUntilTerminated, ResultCode);
  Sleep(300);
  Result := '';
end;

// Если галочку автозапуска сняли при обновлении — убираем старую запись
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if (CurStep = ssPostInstall) and (not WizardIsTaskSelected('autostart')) then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', '{#MyAppName}');
end;
