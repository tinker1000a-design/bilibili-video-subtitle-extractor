$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $skillRoot '.runtime'
$pythonPath = Join-Path $runtimePath 'Scripts\python.exe'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required to create the isolated Python environment.'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & uv venv --python 3.12 $runtimePath
    if ($LASTEXITCODE -ne 0) { throw 'Creating the Python runtime failed.' }
}
& uv pip install --python $pythonPath -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installing subtitle dependencies failed.' }
foreach ($exeName in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $exeName -ErrorAction SilentlyContinue)) {
        throw "$exeName is missing from PATH. Native-caption extraction still supports --native-only."
    }
}
Write-Output "Ready: $pythonPath"
