# KK Scanner Desktop untuk Windows

Versi desktop membungkus aplikasi FastAPI yang sama dengan pywebview. Operator tidak perlu memasang Python, menjalankan terminal, atau membuka localhost secara manual.

## Runtime

Saat KK Scanner dibuka:

1. Launcher membuat data directory di `%LOCALAPPDATA%\KKScanner`.
2. SQLite disimpan di `%LOCALAPPDATA%\KKScanner\kk_scanner.db`.
3. FastAPI/Uvicorn dijalankan hanya pada `127.0.0.1` dan port kosong yang dipilih otomatis.
4. pywebview membuka UI KK Scanner sebagai window desktop.
5. Saat window terakhir ditutup, launcher meminta Uvicorn shutdown dan proses selesai.

Mode desktop menggunakan `APP_ENV=desktop` dan `DESKTOP_AUTO_LOGIN=true`. Auto-login hanya berlaku pada launcher desktop yang bind ke loopback. Mode web/development/production tetap memakai login seperti sebelumnya.

## Build lokal Windows

Prasyarat:

- Windows 10/11 x64
- Python 3.12 x64
- Inno Setup 6
- Microsoft Edge WebView2 Runtime

Jalankan PowerShell:

```powershell
.\build_windows.ps1 -Version 1.0.0
```

Output:

```text
installer\output\KK-Scanner-Setup-1.0.0.exe
```

PyInstaller menggunakan mode `onedir`, lalu Inno Setup membungkus folder hasil build menjadi satu installer.

## Data operator

Program dipasang ke:

```text
%LOCALAPPDATA%\Programs\KK Scanner
```

Data operasional tetap berada di:

```text
%LOCALAPPDATA%\KKScanner
```

Uninstall aplikasi tidak menghapus database operator secara otomatis.

## Vision AI

Pembacaan PDF KK selectable tetap lokal. `ENABLE_VISION_FALLBACK` default `false`, sehingga launcher desktop tidak membutuhkan API AI untuk alur PDF normal.

Jika Vision AI ingin dipakai, konfigurasi provider/API key harus ditambahkan dengan mekanisme konfigurasi yang aman; jangan hard-code key ke executable atau repository.
