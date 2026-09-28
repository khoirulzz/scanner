param(
    [string]$Version = "1.0.0",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== KK Scanner Windows build =="
Write-Host "Version: $Version"

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

if (-not $SkipTests) {
    python -m pytest -q
}

Remove-Item -Recurse -Force build, dist -ErrorAction SilentlyContinue
python -m PyInstaller --clean --noconfirm Scanner.spec

if (-not (Test-Path "dist\KK Scanner\KK Scanner.exe")) {
    throw "PyInstaller selesai tetapi executable tidak ditemukan."
}

$iscc = $null
$command = Get-Command ISCC.exe -ErrorAction SilentlyContinue
if ($command) {
    $iscc = $command.Source
}

if (-not $iscc) {
    $candidates = @(
        "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
        "${env:ProgramFiles}\Inno Setup 6\ISCC.exe"
    )
    $iscc = $candidates | Where-Object { Test-Path $_ } | Select-Object -First 1
}

if (-not $iscc) {
    throw "Inno Setup 6 tidak ditemukan. Install Inno Setup lalu jalankan kembali."
}

Remove-Item -Recurse -Force installer\output -ErrorAction SilentlyContinue
& $iscc "/DMyAppVersion=$Version" "installer\Scanner.iss"

$installer = Get-ChildItem "installer\output\KK-Scanner-Setup-*.exe" | Select-Object -First 1
if (-not $installer) {
    throw "Installer tidak ditemukan setelah kompilasi Inno Setup."
}

Write-Host "Installer siap: $($installer.FullName)"
