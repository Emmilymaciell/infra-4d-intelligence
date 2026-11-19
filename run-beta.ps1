<#
.SYNOPSIS
    Inicia o beta local do INFRA 4D INTELLIGENCE (dados FICTICIOS).

.DESCRIPTION
    Sobe a API FastAPI + interface web em http://127.0.0.1:<Porta>/.
    Pre-requisito: .\bootstrap.ps1 (cria o .venv e instala requirements.txt).
    -Regenerar reconstroi a base sintetica a partir do gerador deterministico.

.EXAMPLE
    .\run-beta.ps1
    .\run-beta.ps1 -Porta 8800 -Regenerar
#>
param(
    [int]$Porta = 8765,
    [switch]$Regenerar
)
$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
$py = Join-Path $Root '.venv\Scripts\python.exe'
if (-not (Test-Path $py)) {
    Write-Host 'O .venv nao existe. Rode primeiro: .\bootstrap.ps1' -ForegroundColor Red
    exit 2
}
$env:PYTHONPATH = Join-Path $Root 'scripts'
if ($Regenerar) {
    & $py -m infra4d.dados_sinteticos
    if ($LASTEXITCODE) { exit $LASTEXITCODE }
}
Write-Host "INFRA 4D INTELLIGENCE - beta com DADOS FICTICIOS" -ForegroundColor Cyan
Write-Host "Abra: http://127.0.0.1:$Porta/   (Ctrl+C para encerrar)" -ForegroundColor Cyan
& $py -m uvicorn infra4d.api:app --host 127.0.0.1 --port $Porta
exit $LASTEXITCODE
