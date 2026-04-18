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

$UserBase = (& $Python @PythonArgs -c "import site; print(site.USER_BASE)").Trim()
$ScriptsDir = Join-Path $UserBase "Scripts"

$InstallMode = "editable"
& $Python @PythonArgs -m pip install --user -e $ProjectDir
if ($LASTEXITCODE -ne 0) {
    $InstallMode = "source launcher"
    New-Item -ItemType Directory -Force -Path $ScriptsDir | Out-Null
    $CmdLauncher = Join-Path $ScriptsDir "stagewarden.cmd"
    $PsLauncher = Join-Path $ScriptsDir "stagewarden.ps1"
    "@echo off`r`nset PYTHONPATH=$ProjectDir;%PYTHONPATH%`r`n$Python $($PythonArgs -join ' ') -m stagewarden.main %*`r`n" | Set-Content -Encoding ASCII $CmdLauncher
    '$env:PYTHONPATH = "' + $ProjectDir + ';' + '$env:PYTHONPATH"' + "`r`n& `"$Python`" $($PythonArgs -join ' ') -m stagewarden.main @args`r`n" | Set-Content -Encoding ASCII $PsLauncher
    Write-Host "Editable install failed; installed source launcher fallback."
}

$CurrentPath = [Environment]::GetEnvironmentVariable("Path", "User")

if ($CurrentPath -notlike "*$ScriptsDir*") {
    [Environment]::SetEnvironmentVariable("Path", "$CurrentPath;$ScriptsDir", "User")
    Write-Host "Added to user PATH: $ScriptsDir"
    Write-Host "Open a new terminal before running stagewarden."
}

Write-Host "Stagewarden installed ($InstallMode)."
Write-Host "Run: stagewarden"
