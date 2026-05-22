param(
    [string]$PythonExe = ".\.venv\Scripts\python.exe",
    [string]$IsccExe,
    [string]$SignToolExe = $env:SIGNTOOL_EXE,
    [switch]$SkipBuild,
    [switch]$SkipInstaller,
    [switch]$SkipSign,
    [switch]$Clean
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

function Invoke-Checked([string]$FilePath, [string[]]$Arguments) {
    & $FilePath @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "Command failed: $FilePath $($Arguments -join ' ')"
    }
}

function Resolve-IsccPath([string]$RequestedPath) {
    if ($RequestedPath -and (Test-Path $RequestedPath)) {
        return (Resolve-Path $RequestedPath).Path
    }

    $command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    foreach ($candidate in @(
        "$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles(x86)\Inno Setup 6\ISCC.exe",
        "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
    )) {
        if ($candidate -and (Test-Path $candidate)) {
            return $candidate
        }
    }

    return $null
}

function Resolve-SignToolPath([string]$RequestedPath) {
    if ($RequestedPath -and (Test-Path $RequestedPath)) {
        return (Resolve-Path $RequestedPath).Path
    }

    $command = Get-Command signtool.exe -ErrorAction SilentlyContinue
    if ($command) {
        return $command.Source
    }

    return $null
}

function Sign-Artifact([string]$Path) {
    if ($SkipSign) {
        return
    }

    $signToolPath = Resolve-SignToolPath $SignToolExe
    if (-not $signToolPath) {
        Write-Warning "signtool.exe not found. Skipping code signing."
        return
    }

    $timestampUrl = if ($env:WINDOWS_TIMESTAMP_URL) {
        $env:WINDOWS_TIMESTAMP_URL
    } else {
        "http://timestamp.digicert.com"
    }

    $arguments = @("sign", "/fd", "SHA256", "/tr", $timestampUrl, "/td", "SHA256")

    if ($env:WINDOWS_PFX_PATH) {
        $arguments += @("/f", $env:WINDOWS_PFX_PATH)
        if ($env:WINDOWS_PFX_PASSWORD) {
            $arguments += @("/p", $env:WINDOWS_PFX_PASSWORD)
        }
    } elseif ($env:WINDOWS_CERT_THUMBPRINT) {
        $arguments += @("/sha1", $env:WINDOWS_CERT_THUMBPRINT)
    } else {
        Write-Warning "No code signing certificate configured. Skipping code signing."
        return
    }

    $arguments += $Path
    Write-Step "Signing $Path"
    Invoke-Checked $signToolPath $arguments
}

Set-Location $ProjectRoot

if (-not (Test-Path $PythonExe)) {
    throw "Python executable not found: $PythonExe"
}

$releaseJson = & $PythonExe -c "import json; from app.release import APP_DESCRIPTION, APP_DISPLAY_NAME, APP_EXE_NAME, APP_PUBLISHER, APP_VERSION; print(json.dumps({'APP_DESCRIPTION': APP_DESCRIPTION, 'APP_DISPLAY_NAME': APP_DISPLAY_NAME, 'APP_EXE_NAME': APP_EXE_NAME, 'APP_PUBLISHER': APP_PUBLISHER, 'APP_VERSION': APP_VERSION}))"
if ($LASTEXITCODE -ne 0) {
    throw "Unable to load release metadata from app.release"
}

$release = $releaseJson | ConvertFrom-Json
$buildDir = Join-Path $ProjectRoot "build"
$distDir = Join-Path $ProjectRoot "dist"
$releaseDir = Join-Path $ProjectRoot "release"

if ($Clean) {
    Write-Step "Cleaning previous build outputs"
    Remove-Item $buildDir, $distDir, $releaseDir -Recurse -Force -ErrorAction SilentlyContinue
}

New-Item -ItemType Directory -Force -Path $releaseDir | Out-Null

$appDistDir = Join-Path $distDir $release.APP_EXE_NAME
$appExePath = Join-Path $appDistDir ("{0}.exe" -f $release.APP_EXE_NAME)

if (-not $SkipBuild) {
    Write-Step "Building frozen application with PyInstaller"
    Invoke-Checked $PythonExe @("-m", "PyInstaller", "--noconfirm", "--clean", "build.spec")
} else {
    Write-Step "Skipping PyInstaller build and reusing existing dist output"
}

if (-not (Test-Path $appExePath)) {
    throw "Expected build output was not produced: $appExePath"
}

Sign-Artifact $appExePath

if (-not $SkipInstaller) {
    $resolvedIscc = Resolve-IsccPath $IsccExe
    if (-not $resolvedIscc) {
        throw "Inno Setup 6 (ISCC.exe) was not found. Install it or rerun with -SkipInstaller."
    }

    Write-Step "Compiling Inno Setup installer"
    Invoke-Checked $resolvedIscc @(
        "/DAppVersion=$($release.APP_VERSION)",
        "/DAppPublisher=$($release.APP_PUBLISHER)",
        "/DAppDisplayName=$($release.APP_DISPLAY_NAME)",
        "/DAppExeName=$($release.APP_EXE_NAME)",
        "/DAppDescription=$($release.APP_DESCRIPTION)",
        "/DSourceDir=$appDistDir",
        "/DReleaseDir=$releaseDir",
        "installer.iss"
    )

    $setupPath = Join-Path $releaseDir ("{0}-Setup-{1}.exe" -f $release.APP_EXE_NAME, $release.APP_VERSION)
    if (-not (Test-Path $setupPath)) {
        throw "Expected installer output was not produced: $setupPath"
    }

    Sign-Artifact $setupPath
    Write-Step "Installer ready: $setupPath"
} else {
    Write-Step "Installer build skipped"
}

Write-Step "Frozen application ready: $appExePath"