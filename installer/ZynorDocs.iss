#define MyAppName "Zynor Docs"
#define MyAppVersion "2.0"
#define MyAppPublisher "Zynor"
#define MyAppExeName "ZynorDocs.exe"

[Setup]
AppId={{A3F2C1D4-8E5B-4F7A-9C2D-1B3E6F8A0D5C}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
OutputDir=..\installer_output
OutputBaseFilename=ZynorDocs_Setup
SetupIconFile=..\icon.ico
Compression=lzma
SolidCompression=yes
WizardStyle=modern
; Permite instalação sem privilégios de admin (por usuário)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

[Languages]
Name: "portuguese"; MessagesFile: "compiler:Languages\Portuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar ícone na Área de Trabalho"; GroupDescription: "Ícones adicionais:"; Flags: unchecked
Name: "resetconfig"; Description: "Reinstalar do zero (apaga configurações e exige nova ativação de licença)"; GroupDescription: "Tipo de instalação:"; Flags: unchecked; Check: ConfigExists

[Files]
; Executável principal
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; Ícone separado para atalhos
Source: "..\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

; Não copiamos mais config.json: o instalador é genérico (mesmo para todo
; cliente) e o tenant_id é gravado em %APPDATA%\ZynorDocs\config.json pelo
; próprio app, na tela de ativação de licença (license_activate).

[Icons]
; Menu Iniciar
; AppUserModelID precisa bater com o registrado em SetCurrentProcessExplicitAppUserModelID
; (app_new.py), senão o Windows pode voltar a agrupar/exibir o ícone errado na taskbar
; quando o atalho é fixado (pin) antes da primeira execução.
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; AppUserModelID: "ZynorDocs.App"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

; Área de Trabalho (opcional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon; AppUserModelID: "ZynorDocs.App"

[Run]
; Abre o app ao fim da instalação (opcional)
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove arquivos gerados em runtime pelo app (opcional — comente se quiser preservar)
; Type: filesandordirs; Name: "{app}"

[Code]
{ Retorna True se já existe um config.json em %APPDATA%\ZynorDocs — ativa a task de reset }
function ConfigExists(): Boolean;
begin
  Result := FileExists(ExpandConstant('{userappdata}\ZynorDocs\config.json'));
end;

{ Antes de copiar arquivos: se o usuário escolheu reinstalar, apaga o config }
procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssInstall then
    if WizardIsTaskSelected('resetconfig') then
      DeleteFile(ExpandConstant('{userappdata}\ZynorDocs\config.json'));
end;
