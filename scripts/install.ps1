# LocalVoice installer for Windows.
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1            # auto-detect GPU
#   powershell -ExecutionPolicy Bypass -File scripts\install.ps1 -Flavor cpu
param(
    [ValidateSet("auto", "gpu", "directml", "cpu")]
    [string]$Flavor = "auto"
)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

if ($Flavor -eq "auto") {
    if (Get-Command nvidia-smi -ErrorAction SilentlyContinue) { $Flavor = "gpu" } else { $Flavor = "directml" }
}
Write-Host "Installing LocalVoice with the '$Flavor' ONNX Runtime..."

$py = $null
foreach ($v in "3.12", "3.13", "3.11", "3.10") {
    try { & py "-$v" -c "import sys" 2>$null; if ($LASTEXITCODE -eq 0) { $py = @("py", "-$v"); break } } catch {}
}
if (-not $py) {
    Write-Error "Python 3.10-3.13 not found. Install it from https://www.python.org/downloads/ (tick 'Add to PATH') and re-run."
}

if (-not (Test-Path .venv)) { & $py[0] $py[1] -m venv .venv }
$venvPy = Join-Path $Root ".venv\Scripts\python.exe"
& $venvPy -m pip install --upgrade pip
& $venvPy -m pip install -e ".[$Flavor]"

Write-Host "Downloading the speech model (one time, ~600 MB)..."
& $venvPy -m localvoice --download

# Start Menu shortcut that runs without a console window.
$pythonw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$lnk = Join-Path ([Environment]::GetFolderPath("Programs")) "LocalVoice.lnk"
$shell = New-Object -ComObject WScript.Shell
$s = $shell.CreateShortcut($lnk)
$s.TargetPath = $pythonw
$s.Arguments = "-m localvoice"
$s.WorkingDirectory = $Root
$s.Description = "Offline push-to-talk dictation"
$s.Save()

Write-Host ""
Write-Host "Done. Start 'LocalVoice' from the Start Menu, then hold Right Ctrl and talk."
Write-Host "Tray icon -> 'Start with Windows' to launch it automatically."
