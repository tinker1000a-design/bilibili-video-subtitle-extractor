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
& uv pip sync --python $pythonPath --require-hashes (Join-Path $PSScriptRoot 'requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Installing subtitle dependencies failed.' }
foreach ($exeName in @('ffmpeg', 'ffprobe')) {
    if (-not (Get-Command $exeName -ErrorAction SilentlyContinue)) {
        Write-Warning "$exeName is missing from PATH. Install: winget install --id=Gyan.FFmpeg -e   (needed only for audio download / ASR; --native-only still works without it)"
    }
}
Write-Output "Ready: $pythonPath"

# Register the skill so a bare video link + "总结" works in a fresh chat window.
# Non-fatal: a machine without any known skill directory should still boot.
try {
    & $pythonPath (Join-Path $PSScriptRoot 'install_skill.py')
    if ($LASTEXITCODE -ne 0) {
        Write-Warning "Skill registration exited with $LASTEXITCODE. Run scripts\install_skill.py manually to see why."
    }
} catch {
    Write-Warning "Skill registration skipped: $($_.Exception.Message)"
}
