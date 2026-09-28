# Ikon desktop KK Scanner

Taruh ikon final di folder ini dengan nama **`scanner.ico`**.

Build tetap berhasil bila file ikon belum ada. Begitu `assets/scanner.ico` tersedia, build Windows otomatis memakainya untuk:

- `KK Scanner.exe`;
- shortcut Desktop dan Start Menu;
- ikon installer/uninstaller;
- ikon pada splash screen startup.

## Spesifikasi yang disarankan

- Rasio: **1:1 (persegi)**.
- Master desain: **1024 × 1024 px** atau minimal **512 × 512 px**.
- Background transparan jika bentuk logo tidak memenuhi kotak.
- Sisakan safe area sekitar **10–15%** dari setiap sisi agar ikon tidak terlihat terlalu penuh.
- File final Windows: **ICO multi-resolution** yang minimal berisi 16, 24, 32, 48, 64, 128, dan 256 px; 256 px sebaiknya 32-bit RGBA/transparan.
- Nama file harus persis: `scanner.ico`.

Opsional: simpan juga source PNG resolusi tinggi sebagai `scanner.png` untuk dokumentasi/desain, tetapi build desktop hanya membutuhkan `scanner.ico`.
