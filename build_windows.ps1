param(
    [string]$Version = "1.0.0",
    [switch]$SkipTests
)

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

Write-Host "== KK Scanner Windows build =="
Write-Host "Version: $Version"
$env:KK_SCANNER_VERSION = $Version

$iconPath = Join-Path $PSScriptRoot "assets\scanner.ico"
if (-not (Test-Path -LiteralPath $iconPath -PathType Leaf)) {
    throw "Ikon wajib tidak ditemukan: $iconPath"
}

$iconBytes = [System.IO.File]::ReadAllBytes($iconPath)
if ($iconBytes.Length -lt 6 -or $iconBytes[0] -ne 0 -or $iconBytes[1] -ne 0 -or $iconBytes[2] -ne 1 -or $iconBytes[3] -ne 0) {
    throw "assets\scanner.ico bukan file ICO Windows yang valid."
}

python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt

if (-not $SkipTests) {
    python -m pytest -q
    node --test tests/js/batch-queue.test.mjs
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

$checksum = Get-FileHash -LiteralPath $installer.FullName -Algorithm SHA256
$checksumPath = "$($installer.FullName).sha256"
"$($checksum.Hash.ToLowerInvariant())  $($installer.Name)" | Set-Content -LiteralPath $checksumPath -Encoding ascii

Write-Host "Installer siap: $($installer.FullName)"
Write-Host "Checksum SHA-256: $checksumPath"
