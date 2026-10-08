# Run the isolated, pinned development tool from the repository root.
param([Parameter(ValueFromRemainingArguments=$true)][string[]]$GraphArguments)
$ErrorActionPreference = "Stop"
$graphifyRoot = Split-Path -Parent $PSScriptRoot
$graphifyExecutable = Join-Path $graphifyRoot ".runtime/graphify-venv/Scripts/graphify.exe"
if (-not (Test-Path -LiteralPath $graphifyExecutable)) {
    throw "Graphify is not installed. Follow research/GRAPHIFY.md."
}
Push-Location -LiteralPath $graphifyRoot
try {
    & $graphifyExecutable @GraphArguments
    $graphifyExitCode = $LASTEXITCODE
} finally {
    Pop-Location
}
exit $graphifyExitCode
