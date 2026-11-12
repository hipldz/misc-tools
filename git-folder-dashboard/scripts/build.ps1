param([switch]$InstallDependencies, [switch]$SkipTests)

$ErrorActionPreference = 'Stop'
$projectRoot = Split-Path -Parent $PSScriptRoot
$pythonPath = Join-Path $projectRoot '.venv/Scripts/python.exe'
if (-not (Test-Path -LiteralPath $pythonPath)) {
    throw 'Create .venv first: python -m venv .venv'
}
Push-Location $projectRoot
try {
    $buildArguments = @('scripts/build.py')
    if ($InstallDependencies) { $buildArguments += '--install-dependencies' }
    if ($SkipTests) { $buildArguments += '--skip-tests' }
    & $pythonPath @buildArguments
    if ($LASTEXITCODE -ne 0) { throw 'Build failed.' }
} finally {
    Pop-Location
}
