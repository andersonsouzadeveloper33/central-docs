# =============================================================
# build_cliente.ps1 — Gera instalador ZynorDocs para um cliente
# Uso: .\build_cliente.ps1 -TenantId "uuid" -TenantName "Nome"
# =============================================================

param(
    [Parameter(Mandatory=$true)]
    [string]$TenantId,

    [Parameter(Mandatory=$true)]
    [string]$TenantName
)

$ErrorActionPreference = "Stop"
$Root    = $PSScriptRoot
$ISCC    = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
$OutDir  = Join-Path $Root "clientes\$TenantName"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Zynor Docs — Build para: $TenantName" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Atualiza config.json
Write-Host "[1/4] Atualizando config.json..." -ForegroundColor Yellow
$config = @{ tenant_id = $TenantId; tenant_name = $TenantName } | ConvertTo-Json
$config | Out-File -FilePath (Join-Path $Root "config.json") -Encoding utf8
Write-Host "      tenant_id  : $TenantId"
Write-Host "      tenant_name: $TenantName"

# 2. Compila o executável
Write-Host ""
Write-Host "[2/4] Compilando ZynorDocs.exe com PyInstaller..." -ForegroundColor Yellow
$pyArgs = @(
    "-m", "PyInstaller",
    "--onefile", "--windowed",
    "--icon=`"$Root\icon.ico`"",
    "--add-data", "`"$Root\config.json;.`"",
    "--add-data", "`"$Root\icon.ico;.`"",
    "--name", "ZynorDocs",
    "`"$Root\app.py`""
)
python @pyArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: PyInstaller falhou." -ForegroundColor Red
    exit 1
}

# 3. Compila o instalador
Write-Host ""
Write-Host "[3/4] Gerando instalador com Inno Setup..." -ForegroundColor Yellow
if (-not (Test-Path $ISCC)) {
    Write-Host "ERRO: Inno Setup não encontrado em $ISCC" -ForegroundColor Red
    exit 1
}
& $ISCC "$Root\installer\ZynorDocs.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Inno Setup falhou." -ForegroundColor Red
    exit 1
}

# 4. Copia instalador para pasta do cliente
Write-Host ""
Write-Host "[4/4] Copiando instalador para pasta do cliente..." -ForegroundColor Yellow
New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$src = Join-Path $Root "installer_output\ZynorDocs_Setup.exe"
$dst = Join-Path $OutDir "ZynorDocs_Setup_$TenantName.exe"
Copy-Item $src $dst -Force
Write-Host "      Salvo em: $dst"

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Instalador pronto!" -ForegroundColor Green
Write-Host "  $dst" -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
