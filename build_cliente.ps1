# =============================================================
# build_cliente.ps1 — Gera o instalador genérico do Zynor Docs
# Uso: .\build_cliente.ps1
# O app não carrega mais tenant_id no build: o instalador é o
# mesmo para todo mundo, e a vinculação ao tenant acontece em
# runtime via tela de ativação de licença (license_activate).
# =============================================================

$ErrorActionPreference = "Stop"
$Root    = $PSScriptRoot
$ISCC    = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Zynor Docs — Build genérico" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

# 1. Compila o executável
Write-Host "[1/3] Compilando ZynorDocs.exe com PyInstaller..." -ForegroundColor Yellow
$pyArgs = @(
    "-m", "PyInstaller",
    "--onefile", "--windowed",
    "--icon=`"$Root\icon.ico`"",
    "--add-data", "`"$Root\icon.ico;.`"",
    "--add-data", "`"$Root\ui;ui`"",
    "--name", "ZynorDocs",
    "`"$Root\app_new.py`""
)
python @pyArgs
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: PyInstaller falhou." -ForegroundColor Red
    exit 1
}

# 2. Compila o instalador
Write-Host ""
Write-Host "[2/3] Gerando instalador com Inno Setup..." -ForegroundColor Yellow
if (-not (Test-Path $ISCC)) {
    Write-Host "ERRO: Inno Setup não encontrado em $ISCC" -ForegroundColor Red
    exit 1
}
& $ISCC "$Root\installer\ZynorDocs.iss"
if ($LASTEXITCODE -ne 0) {
    Write-Host "ERRO: Inno Setup falhou." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Green
Write-Host "  Instalador pronto!" -ForegroundColor Green
Write-Host "  $Root\installer_output\ZynorDocs_Setup.exe" -ForegroundColor Green
Write-Host "  Distribua o mesmo instalador para todos os clientes." -ForegroundColor Green
Write-Host "  Cada um digita seu próprio código de ativação no primeiro uso." -ForegroundColor Green
Write-Host "============================================" -ForegroundColor Green
Write-Host ""
