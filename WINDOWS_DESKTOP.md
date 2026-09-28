# KK Scanner Desktop untuk Windows

Versi desktop membungkus aplikasi FastAPI yang sama dengan pywebview. Operator tidak perlu memasang Python, menjalankan terminal, atau membuka localhost secara manual.

## Runtime

Saat KK Scanner dibuka:

1. Window splash langsung muncul dengan status **Menyiapkan aplikasi**.
2. Launcher membuat data directory di `%LOCALAPPDATA%\KKScanner`.
3. SQLite disimpan di `%LOCALAPPDATA%\KKScanner\kk_scanner.db`.
4. Launcher mencari port kosong pada `127.0.0.1`.
5. FastAPI/Uvicorn dijalankan di background pada loopback tersebut.
6. Splash memperbarui status saat database dan `/healthz` diperiksa.
7. Setelah server siap, window yang sama beralih ke dashboard KK Scanner.
8. Saat window terakhir ditutup, launcher meminta Uvicorn shutdown dan proses selesai.

Mode desktop menggunakan `APP_ENV=desktop` dan `DESKTOP_AUTO_LOGIN=true`. Auto-login hanya berlaku pada launcher desktop yang bind ke loopback. Mode web/development/production tetap memakai login seperti sebelumnya.

## Microsoft Edge WebView2 Runtime

Installer mengecek WebView2 Runtime melalui registry resmi Microsoft. Pada Windows x64 yang dicek terutama adalah:

`HKLM\SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}`

serta instalasi per-user pada HKCU.

Jika runtime belum ada, installer mengunduh **Evergreen Bootstrapper** resmi Microsoft dan menjalankan:

```text
MicrosoftEdgeWebview2Setup.exe /silent /install
```

Runtime hanya diunduh ketika diperlukan sehingga ukuran `KK-Scanner-Setup-*.exe` tidak perlu membawa paket WebView2 penuh. Saat tahap dependency/app installation sedang berlangsung, setup menolak penutupan agar instalasi tidak rusak. Pada tahap wizard biasa, tombol Close/Cancel tetap menampilkan konfirmasi terlebih dahulu.

## Build yang lebih ramping

`requirements.txt` tetap menjadi dependency lengkap untuk versi web/development. Build desktop memakai dua file terpisah:

- `requirements-desktop.txt`: runtime yang benar-benar diperlukan executable desktop;
- `requirements-build.txt`: runtime desktop + `pytest` + `pyinstaller` hanya untuk mesin build.

Driver PostgreSQL (`psycopg`), Alembic, dan extras `uvicorn[standard]` tidak dibawa ke environment desktop. SQLite tetap menggunakan modul bawaan Python. OpenCV, NumPy, Pillow, PyMuPDF, OpenPyXL, HTTPX, dan library scanner lain tetap dipertahankan supaya fitur aplikasi tidak dipangkas.

## Build lokal Windows

Prasyarat mesin build:

- Windows 10/11 x64
- Python 3.12 x64
- Inno Setup 6+

Jalankan PowerShell:

```powershell
.\build_windows.ps1 -Version 1.1.0
```

Output:

```text
installer\output\KK-Scanner-Setup-1.1.0.exe
```

PyInstaller menggunakan mode `onedir`, lalu Inno Setup membungkus folder hasil build menjadi satu installer.

## Ikon aplikasi

Upload file berikut ke repository:

```text
assets/scanner.ico
```

Build tetap berjalan tanpa file tersebut. Jika file tersedia, `Scanner.spec` dan `Scanner.iss` otomatis menggunakannya.

Spesifikasi rekomendasi:

- rasio 1:1;
- master 1024×1024 px atau minimal 512×512 px;
- transparan bila diperlukan;
- safe margin 10–15%;
- ICO multi-resolution: 16, 24, 32, 48, 64, 128, dan 256 px.

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

## Penghapusan hasil scan

Halaman **Hasil** menyediakan penghapusan batch, sedangkan detail batch menyediakan penghapusan satu hasil scan. Penghapusan membersihkan data turunan seperti KK, anggota keluarga, thumbnail, attempts, issues, corrections, dan riwayat export yang sudah tidak valid. Jika item terakhir pada suatu batch dihapus, batch kosong ikut dibersihkan.

## Vision AI

Pembacaan PDF KK selectable tetap lokal. `ENABLE_VISION_FALLBACK` default `false`, sehingga launcher desktop tidak membutuhkan API AI untuk alur PDF normal.

Jika Vision AI ingin dipakai, konfigurasi provider/API key harus ditambahkan dengan mekanisme konfigurasi yang aman; jangan hard-code key ke executable atau repository.
