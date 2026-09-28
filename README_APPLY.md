# KK Scanner Desktop Improvements

Patch ini disiapkan terhadap kondisi `main` pada commit `d1c1755fc9f7174ac980afb5ea92afe2b166a2c9` (release v1.0.0, 28 Sep 2026).

## Isi perubahan

- splash/startup screen langsung muncul sambil FastAPI/Uvicorn dan SQLite disiapkan;
- status startup nyata dan tampilan error startup;
- hapus satu hasil scan atau satu batch dengan modal konfirmasi;
- pembersihan child records dan invalidasi riwayat export yang sudah tidak konsisten;
- dependency desktop dipisahkan dari web/build dependency agar paket PyInstaller lebih ramping;
- WebView2 Runtime dideteksi saat setup dan otomatis diunduh/di-install jika belum ada;
- installer tidak bisa ditutup saat fase kritis, dan memberi warning bila dibatalkan di fase biasa;
- wiring ikon `assets/scanner.ico` ke EXE, installer, shortcut/taskbar (via executable/pywebview), dan splash;
- unit test untuk deletion service.

## Cara paling mudah menerapkan

Dari root repo lokal yang berada pada `main` terbaru:

```bash
git apply --check KK-Scanner-desktop-improvements.patch
git apply KK-Scanner-desktop-improvements.patch
python -m pytest -q
```

Lalu review perubahan, commit, dan push.

Alternatif: salin isi ZIP patch ke root repository dengan struktur folder yang sama dan izinkan replace file yang sudah ada.

## Logo/icon

Upload satu file final ke:

```text
assets/scanner.ico
```

Build tetap berjalan jika file belum ada. Rekomendasi sumber desain: 1024×1024 px, 1:1, transparan bila perlu, safe margin 10–15%. File ICO sebaiknya multi-resolution 16/24/32/48/64/128/256 px.

## Validasi yang sudah dilakukan

- Python syntax compilation: lulus.
- JavaScript syntax check (`node --check`): lulus.
- Unit test deletion service dengan model SQLAlchemy repo: 2/2 lulus.
- `git diff --check`: lulus.
- `git apply --check` terhadap baseline v1.0.0: lulus.

Build Windows/Inno Setup final tetap perlu dijalankan oleh GitHub Actions/Windows setelah patch diterapkan, karena environment kerja ini bukan Windows dan tidak memiliki Inno Setup runtime.
