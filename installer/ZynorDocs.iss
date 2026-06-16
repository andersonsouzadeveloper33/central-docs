#define MyAppName "Zynor Docs"
#define MyAppVersion "1.0"
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

[Files]
; Executável principal
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion

; config.json — copiado mas NÃO sobrescrito se já existir (preserva dados do cliente)
Source: "..\config.json"; DestDir: "{app}"; Flags: onlyifdoesntexist

; Ícone separado para atalhos
Source: "..\icon.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Menu Iniciar
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"
Name: "{group}\Desinstalar {#MyAppName}"; Filename: "{uninstallexe}"

; Área de Trabalho (opcional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; IconFilename: "{app}\icon.ico"; Tasks: desktopicon

[Run]
; Abre o app ao fim da instalação (opcional)
Filename: "{app}\{#MyAppExeName}"; Description: "Abrir {#MyAppName} agora"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; Remove arquivos gerados em runtime pelo app (opcional — comente se quiser preservar)
; Type: filesandordirs; Name: "{app}"
