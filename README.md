# Standalone KK Scanner V1

Aplikasi web mandiri untuk membaca PDF Kartu Keluarga Indonesia dengan teks selectable, menyimpan hasil ekstraksi ke database scanner terpisah, memungkinkan review/koreksi manual, batch scanning, dan export XLSX 28 kolom yang kompatibel dengan Import Kependudukan SID Desa Lambanggelun.

> V1 tidak terhubung langsung ke database SID. AI tidak pernah membuat data otomatis menjadi `APPROVED`.

## Arsitektur

```text
Browser (PDF + IndexedDB queue)
  ↓
FastAPI
  ├ PyMuPDF: teks dan posisi sel
  ├ profil blanko KK lanskap
  └ thumbnail untuk review
  ↓
Python deterministic row mapping + validation
  ↓
Human review → APPROVED → XLSX SID
```

Prinsip ekstraksi adalah **TRANSCRIBE ONLY**: jangan menebak karakter, jangan memindahkan nilai antarbaris, dan return null jika tidak terbaca. Dua tabel anggota digabung berdasarkan nomor baris yang tercetak; slot kosong diabaikan. Untuk setiap PDF KK siap cetak satu halaman lanskap, parser memasangkan token `(1)` sampai `(17)` dengan garis grid tabel dan nomor baris aktual, sehingga variasi autofit kolom, margin kanan tabel, dan tinggi header mengikuti struktur dokumen tersebut. Susunan lain ditolak agar kolom tidak bergeser diam-diam.

## Fitur V1

- Admin login berbasis environment variable dan session HTTP-only.
- CSRF protection dan basic rate limiting.
- Single/batch maksimal 50 PDF, tetap diproses sequential agar beban lokal terkendali.
- IndexedDB queue tanpa menyimpan PDF di server.
- Validasi magic-byte, ukuran, satu halaman, PDF terkunci, dan teks selectable.
- Ekstraksi native PyMuPDF berdasarkan objek teks dan koordinat tabel.
- Deterministic row mapping tanpa shifting row.
- Jalur Vision untuk foto dapat diaktifkan terpisah; PDF tidak memakai AI.
- Database attempts, issues, corrections, records/members, export history.
- Thumbnail only persisted; full KK image tidak disimpan permanen.
- Manual edit dan approval ulang dengan deterministic validation.
- XLSX SID 28 kolom; NIK/No KK sebagai string, RT/RW 3 digit, tanggal `dd-mm-yyyy`.
- Dashboard, batch history, data search, export history, `/healthz`.

## Batch lokal

Batch lokal menerima hingga 50 PDF (maksimum 8 MB per PDF). Dokumen tetap diproses satu per satu dan antrean disimpan ke IndexedDB agar penggunaan memori aktif tetap kecil serta proses dapat dilanjutkan setelah gangguan.

## Local development

```bash
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

Environment minimum:

```env
APP_ENV=development
DATABASE_URL=sqlite:///./kk_scanner.db
SECRET_KEY=<long random secret>
APP_ADMIN_USERNAME=admin
APP_ADMIN_PASSWORD=<strong password>
VISION_PROVIDER=groq
VISION_MODEL=qwen/qwen3.8-27b
GROQ_API_KEY=<server-side key>
ENABLE_VISION_FALLBACK=false
```

## Render

`render.yaml` dan `Dockerfile` sudah disediakan. Untuk production set `APP_ENV=production`, PostgreSQL `DATABASE_URL`, secret/session credentials, dan `GROQ_API_KEY`. Start command:

```bash
uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Health check: `GET /healthz`.

## Export SID

Urutan kolom persis:

```text
no_kk, nama_kepala_keluarga, alamat, rt, rw, kode_pos, dusun, desa,
kecamatan, kabupaten, provinsi, no_urut_kk, status_hubungan, nik,
nama_lengkap, jenis_kelamin, tempat_lahir, tanggal_lahir, agama,
pendidikan, jenis_pekerjaan, status_perkawinan, kewarganegaraan,
no_paspor, no_kitas_kitap, nama_ayah, nama_ibu, golongan_darah
```

Satu anggota = satu row. Household fields diulang. Export default paling berguna adalah `Approved yang belum pernah diekspor`. `exported_at` hanya berarti pernah dimasukkan ke XLSX, bukan sudah masuk SID.

## Privacy/security

- `.env`, API key, KK asli, NIK, No KK, nama, alamat, raw image/base64, dan raw AI response tidak boleh masuk log/repository. File PDF diabaikan oleh Git secara default.
- Full-resolution KK tidak disimpan permanen.
- PDF dibaca native dari objek teks dan koordinatnya; isi PDF tidak dikirim ke AI. Watermark gambar seperti `DRAFT` tidak menjadi input ekstraksi.
- Jalur foto lama hanya aktif bila admin secara eksplisit mengatur `ENABLE_VISION_FALLBACK=true`.
- Fixture test harus sintetis/fiktif.
- Jangan integrasikan direct SID write pada V1.

## Testing

```bash
pytest -q
```

Unit tests mencakup deterministic row mismatch, invalid No KK, duplicate NIK, multiple Kepala Keluarga, low-resolution rejection, exact 28-column export, serta preservation No KK/NIK sebagai text.

## Reset data scanner

Skrip ini menghapus seluruh data operasional scanner dari database pada `DATABASE_URL` aktif: batch, KK, anggota, hasil scan, riwayat koreksi, dan riwayat ekspor. Struktur database dan kredensial environment tidak diubah. Jalankan pengecekan terlebih dahulu:

```bash
py -3.12 scripts/reset_kk_data.py --dry-run
```

Jika jumlahnya sudah benar dan siap dihapus permanen:

```bash
py -3.12 scripts/reset_kk_data.py --confirm DELETE_ALL_KK_DATA
```

## V1 boundaries

Tidak ada Redis, Celery, local OCR/PaddleOCR, multi-user role, permanent original-image storage, automatic household merge, atau direct database update ke SID. Akurasi produksi harus diukur melalui `field_corrections` sebelum integrasi SID langsung dipertimbangkan.
