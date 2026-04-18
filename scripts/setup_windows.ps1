$ErrorActionPreference = "Stop"

$ProjectDir = Resolve-Path (Join-Path $PSScriptRoot "..")

if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
    throw "git not found. Install Git for Windows before installing Stagewarden."
}

$Python = $env:PYTHON_BIN
if (-not $Python) {
    $Python = "py"
}

try {
    & $Python -3.11 --version | Out-Null
    $PythonArgs = @("-3.11")
} catch {
    $Python = "python"
    $PythonArgs = @()
}

& $Python @PythonArgs -m pip install --user -e $ProjectDir

$UserBase = (& $Python @PythonArgs -c "import site; print(site.USER_BASE)").Trim()
$ScriptsDir = Join-Path $UserBase "Scripts"
$CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($CurrentPath -notlike "*$ScriptsDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$CurrentPath;$ScriptsDir", "User")
    Write-Host "Added to user PATH: $ScriptsDir"
    Write-Host "Open a new terminal before running stagewarden."
}

Write-Host "Stagewarden installed."
Write-Host "Run: stagewarden"
