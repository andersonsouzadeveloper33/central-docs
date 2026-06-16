# Zynor Docs — Guia de Build e Distribuição

## Pré-requisitos

- Python 3.x com PyInstaller: `pip install pyinstaller`
- [Inno Setup 6](https://jrsoftware.org/isdl.php) instalado em `C:\Program Files (x86)\Inno Setup 6\`
- Pillow (para gerar ícone): `pip install pillow`

---

## Gerar instalador para um cliente

Execute o script `build_cliente.ps1` passando o `tenant_id` e o nome do cliente:

```powershell
.\build_cliente.ps1 -TenantId "uuid-do-cliente" -TenantName "NomeDoCliente"
```

O script executa 4 etapas automaticamente:

| Etapa | O que faz |
|-------|-----------|
| 1 | Atualiza `config.json` com os dados do cliente |
| 2 | Compila `ZynorDocs.exe` via PyInstaller |
| 3 | Gera `ZynorDocs_Setup.exe` via Inno Setup |
| 4 | Salva o instalador em `clientes\NomeDoCliente\` |

O instalador final fica em:
```
clientes\NomeDoCliente\ZynorDocs_Setup_NomeDoCliente.exe
```

---

## Exemplo — cliente Naira

```powershell
.\build_cliente.ps1 -TenantId "29e713d4-893f-4a38-b82a-de764fabad8f" -TenantName "Naira"
```

---

## Build manual (sem o script)

### 1. Atualizar config.json
Edite `config.json` com o `tenant_id` e `tenant_name` do cliente.

### 2. Compilar o executável
```powershell
python -m PyInstaller --onefile --windowed --icon="icon.ico" --add-data "config.json;." --add-data "icon.ico;." --name "ZynorDocs" "app.py"
```

### 3. Gerar o instalador
```powershell
& "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" "installer\ZynorDocs.iss"
```

O instalador gerado estará em `installer_output\ZynorDocs_Setup.exe`.

---

## Regenerar o ícone

Se a logo mudar, rode:
```powershell
python gerar_ico.py
```
Requer `logo.png` na raiz do projeto e Pillow instalado.

---

## Estrutura de arquivos relevantes

```
centraldocs/
├── app.py                  # Código principal
├── config.json             # Configuração do tenant (alterada por cliente)
├── icon.ico                # Ícone do app
├── logo.png                # Logo fonte para gerar o ícone
├── gerar_ico.py            # Script para converter logo.png → icon.ico
├── build_cliente.ps1       # Script de build automatizado por cliente
├── installer/
│   └── ZynorDocs.iss       # Script do Inno Setup
├── installer_output/       # Instalador gerado (ZynorDocs_Setup.exe)
├── clientes/               # Um subdiretório por cliente com seu instalador
│   └── NomeDoCliente/
│       └── ZynorDocs_Setup_NomeDoCliente.exe
└── dist/
    └── ZynorDocs.exe       # Executável compilado pelo PyInstaller
```
