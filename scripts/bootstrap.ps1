$ErrorActionPreference = 'Stop'
$skillRoot = Split-Path -Parent $PSScriptRoot
$runtimePath = Join-Path $skillRoot '.runtime'
$pythonPath = Join-Path $runtimePath 'Scripts\python.exe'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'uv is required. Install it first:  powershell -c "irm https://astral.sh/uv/install.ps1 | iex"   (or: winget install --id=astral-sh.uv -e)'
}
if (-not (Test-Path -LiteralPath $pythonPath)) {
    & uv venv --python 3.12 $runtimePath
    if ($LASTEXITCODE -ne 0) { throw 'Creating the Python runtime failed.' }
}
& uv pip install --python $pythonPath -r (Join-Path $PSScriptRoot 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Installing subtitle dependencies failed.' }
foreach ($exeName in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $exeName -ErrorAction SilentlyContinue)) {
        Write-Warning "$exeName is missing from PATH. Install: winget install --id=Gyan.FFmpeg -e   (needed only for audio download / ASR; --native-only still works without it)"
    }
}
Write-Output "Ready: $pythonPath"
