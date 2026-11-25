# PLAN.md — Exam Generator (backend dulu)

Panduan kerja untuk agen AI. Anggap kamu programmer junior: kerjakan tugas kecil, satu per satu.
Baca `AGENTS.md` dulu. Kerjakan SATU fase per permintaan. Selalu tulis rencana singkat dulu, tunggu persetujuan, baru tulis kode.

---

## 1. Tujuan

Aplikasi desktop offline (nanti dijadikan .exe) untuk ujian tertulis di kertas. Ada dua fitur yang terpisah:

- **Fitur 1 – Buat soal.** Dari 1 file Excel soal, hasilkan PDF soal Exam A dan Exam B (isi sama, urutan soal B diacak), plus 1 Excel kunci jawaban.
- **Fitur 2 – Analisis hasil.** Dari Excel kunci (hasil Fitur 1) dan PDF scan lembar jawaban, baca jawaban peserta, hitung skor, analisis tiap soal, lalu hasilkan laporan PDF.

Yang dikerjakan sekarang: **backend** (folder `core/`). Tampilan (GUI) dibuat belakangan, jangan disentuh.

## 2. Teknologi (hanya ini; jangan tambah library lain tanpa izin)

| Teknologi | Dipakai untuk |
|---|---|
| Python 3.15 | Bahasa utama |
| openpyxl | Membaca dan menulis Excel (.xlsx) |
| reportlab | Membuat PDF (soal dan laporan) |
| pypdfium2 | Mengubah halaman PDF scan menjadi gambar |
| opencv-python-headless | Mengolah gambar: meluruskan halaman, mengukur tinta di kotak jawaban |
| numpy | Hitungan angka pada gambar |
| pillow | Menyimpan potongan gambar dan gambar overlay |
| pytest | Tes otomatis |
| JSON | Menyimpan profil posisi kotak form |

- Buat `requirements.txt` berisi library di atas. Pasang di virtual environment `.venv`.
- Pemasangan nanti (JANGAN dipasang sekarang): customtkinter (GUI) dan pyinstaller (.exe).
- Semua berjalan offline. Tidak ada database, server/API, internet, atau AI saat aplikasi berjalan.

## 3. Struktur folder

```
exam-generator/
  AGENTS.md, PLAN.md, requirements.txt
  core/            # semua logika (tanpa tampilan)
    exam_pdf.py    # pembuat PDF soal, sudah teruji
  tests/
    fixtures/      # data uji (jangan di-commit)
  assets/          # font dan logo
  tools/           # skrip bantu (kalibrasi form, dll.)
```

Boleh menambah file di dalam `core/` sesuai kebutuhan fase.

## 4. Istilah penting

- **Template Excel**: sheet README, Config, Questions. Config berisi data ujian (judul, nama ujian, Course Code, durasi, jumlah soal, jumlah opsi, total skor, pass mark, dll.). Questions berisi soal. **Cara `core/exam_pdf.py` membaca Excel adalah acuan.**
- **Question Code**: kode unik tiap soal (kolom di sheet Questions). Soal yang sama punya Question Code yang sama di Set A dan Set B. Dipakai untuk analisis.
- **Course Code**: kode untuk satu ujian secara keseluruhan (sheet Config). Jangan tertukar dengan Question Code.
- **Set**: A (urutan asli), B (diacak di dalam tiap ATA), R (remedial, soal sendiri; ditambahkan setelah A/B jalan).
- **Lembar jawaban**: form resmi GMF/U-013 R2, versi 3 opsi (A-C) atau 4 opsi (A-D), 100 nomor. Dicetak resmi lalu dipindai. **Sistem tidak membuat lembar jawaban.**
- **Excel kunci**: keluaran Fitur 1, masukan Fitur 2. Bersifat rahasia.

## 5. Aturan Fitur 1 (singkat)

- Set A = urutan asli (dikelompokkan per ATA seperti sekarang). Set B = urutan soal diacak di dalam tiap ATA. Opsi A-D tidak diacak.
- Acakan memakai seed yang disimpan, jadi hasil bisa dibuat ulang. Set B harus berbeda dari Set A (kalau terlalu mirip, beri peringatan).
- Footer PDF "MODEL" menampilkan huruf set (A/B).
- Excel kunci punya 4 sheet:
  - **Meta**: versi skema, nama ujian, Course Code, jumlah soal, jumlah opsi, total skor, pass mark, tanggal, seed, hash isi kunci.
  - **Set A** dan **Set B**: No, Question Code, ATA, Kunci.
  - **Bank**: Question Code, ATA, teks soal.
- Hash dipakai untuk memberi peringatan kalau kunci diedit manual setelah dibuat.

## 6. Aturan Fitur 2 / scanner (singkat)

- Satu PDF scan berisi banyak lembar untuk **satu set**. Pengguna mengimpor dua kali (sekali untuk A, sekali untuk B).
- Form punya 4 penanda hitam di sudut, plus satu penanda tambahan di kanan-bawah sebagai petunjuk orientasi. Halaman diluruskan memakai penanda ini.
- Cetakan form berwarna **merah**. Tanda peserta berwarna hitam, biru, atau pensil. Tanda (coretan) merah diabaikan.
- Pembacaan memakai **ambang adaptif per lembar** (lembar yang terang dan tinta tipis harus tetap terbaca).
- Status tiap jawaban: **jelas, kosong, ganda, samar**. Kalau ragu, tandai **"perlu review"** dan simpan potongan gambarnya. Tidak boleh menebak diam-diam.
- Bekas hapusan tipis di kotak lain: beri peringatan.
- Yang dibaca selain jawaban: kode exam (A/B/R), ID peserta (6 digit), tanggal (6 digit), kode kursus (3 huruf + 7 digit). Cocokkan kode exam dengan set yang dipilih pengguna, dan kode kursus dengan Meta (abaikan tanda "-" dan huruf akhir set). Kalau beda, beri peringatan.
- Skor = jumlah benar / jumlah soal x 100, **dibulatkan ke bawah**.

## 7. Fase kerja

Tiap fase selesai kalau: rencana disetujui, tes lulus, dan hasilnya sudah di-commit.

### Fase 0 — Persiapan
- Buat folder, `requirements.txt`, tes dasar, dan pindahkan `exam_pdf.py` ke `core/` tanpa mengubah perilakunya.
- Pastikan font dan logo masih ditemukan setelah dipindah.
- Usulkan struktur data (Exam, Question, dan skema Excel kunci). Tunggu persetujuan.
- **Selesai:** `pytest` jalan dan PDF contoh masih terbuat seperti sebelumnya.

### Fase 1 — Baca Excel dan validasi
- Baca Config dan Questions, termasuk kolom Question Code. Dukung ATA beralfabet (misalnya 36A).
- Aturan: Question Code wajib terisi dan unik; jumlah opsi 3 atau 4; jumlah soal maksimal 100.
- Pesan error dalam Bahasa Indonesia, menyebut baris/kolom yang salah. Tampilkan semua error sekaligus.
- **Selesai:** ada tes untuk Excel valid dan tiap jenis kesalahan.

### Fase 2 — Fitur 1: PDF A/B dan Excel kunci
- Buat PDF soal Set A dan Set B, lalu Excel kunci sesuai bagian 5.
- Validasi lintas-set: Question Code yang sama harus punya teks soal, opsi, dan kunci yang sama. Kalau beda, tampilkan error per kode.
- **Selesai:** setiap Question Code muncul tepat sekali per set; kunci A dan B sama setelah dipetakan; seed sama menghasilkan urutan sama; Excel kunci bisa dibaca ulang.

### Fase 3 — Profil form (kalibrasi)
Pecah menjadi tugas kecil:
- **3a.** Cari 4 penanda sudut dan luruskan halaman. Ambang harus adaptif (scan 3 opsi lebih terang dari scan 4 opsi). Orientasi dari penanda tambahan.
- **3b.** Dari scan form KOSONG, buat profil posisi kotak (JSON), satu untuk 3 opsi dan satu untuk 4 opsi. Isinya: kisi jawaban 1-100 (4 blok x 25 baris), kotak kode exam, kisi ID, tanggal, dan kode kursus. Petunjuk: huruf merah cetakan bisa jadi acuan posisi.
- **3c.** Buat gambar overlay (profil digambar di atas scan) supaya bisa dicek dengan mata.
- **3d.** Deteksi varian otomatis (3 atau 4 opsi).
- **Selesai:** semua halaman kosong teralign; jumlah kotak area jawaban 300 (3 opsi) atau 400 (4 opsi).

### Fase 4 — Scanner
Pecah menjadi tugas kecil:
- **4a.** PDF scan gabungan menjadi gambar per halaman, lalu diluruskan.
- **4b.** Baca jawaban: ukur tinta di tiap kotak, tentukan status sesuai bagian 6.
- **4c.** Baca kode exam, ID, tanggal, dan kode kursus.
- **4d.** Keluarkan hasil per lembar (data) dan potongan gambar untuk yang "perlu review".
- **Selesai:** pada data uji (bagian 8), hasil sesuai ground truth; tidak ada salah baca yang lolos tanpa ditandai.

### Fase 5 — Analisis dan laporan PDF
- Skor per lembar. Rate keberhasilan per Question Code (gabungan A+B, plus kolom rate A dan rate B).
- Highlight: rate **di atas 90%** (terlalu mudah) dan **di bawah 50%** (terlalu sulit / periksa soal). Tepat 90% dan 50% tidak ditandai.
- Laporan PDF (reportlab): ringkasan (jumlah peserta per set, rata-rata, jumlah lulus), tabel analisis soal berwarna, daftar soal ter-highlight beserta teks soalnya. **Tanpa nama/ID peserta.**
- Jawaban "perlu review" harus diselesaikan dulu sebelum laporan dibuat (layar review dibuat di tahap GUI).
- **Selesai:** angka cocok dengan hitungan manual dan PDF terbentuk.

### Fase 6 — Uji menyeluruh dan rapikan
- Jalankan alur lengkap Fitur 1 lalu Fitur 2 dengan data uji. Uji 100 lembar (gandakan lembar uji) dan catat waktunya.
- Tulis README singkat cara memakai `core/`. Backend siap dipakai GUI.

## 8. Data uji (di `tests/fixtures/`, jangan di-commit)

- `Exam_Sample_A.xlsx` dan `Exam_Sample_B.xlsx` (32 soal, 4 opsi). Header kolom kode soal di Questions harus berjudul **Question Code**.
- 6 lembar dummy (3 untuk A, 3 untuk B), form 4 opsi, 32 nomor terisi.
- Scan form kosong: varian 3 opsi (4 halaman) dan varian 4 opsi (5 halaman).
- 24 lembar lama (form 3 opsi, 12 soal, tanpa Excel). Tulisan tangan `S:` (jumlah salah) dan nilai di tiap lembar jadi pembanding untuk uji pembacaan. Halaman 1-12 = Exam A, 13-24 = Exam B.

Ground truth 6 lembar dummy (dibaca terhadap kunci masing-masing file, "no." = nomor di lembar soal):

| Lembar | Benar | Salah di no. |
|---|---|---|
| A1 | 28/32 | 5, 7, 10, 11 |
| A2 | 29/32 | 10, 11, 25 |
| A3 | 29/32 | 7, 10, 11 |
| B1 | 31/32 | 16 |
| B2 | 31/32 | 16 |
| B3 | 30/32 | 16, 32 |

Catatan:
- Excel A dan B **sengaja** punya kunci berbeda untuk Question Code 10 dan 11. Ini dipakai untuk menguji pesan error validasi (Fase 2).
- Untuk uji alur lengkap, buat salinan Excel dengan kunci kode 10 dan 11 disamakan, lalu hitung ulang ground truth bersama pengguna.
- Lembar B1 punya bekas silang terhapus yang sangat tipis di kotak kode exam A (silang aktif ada di B). Ini kasus uji peringatan.

## 9. Keputusan

Sudah diputuskan:
- Dua fitur terpisah; Excel kunci menghubungkan keduanya.
- Set B diacak di dalam tiap ATA; opsi tidak diacak.
- Lembar jawaban memakai form resmi (3 atau 4 opsi), dipindai, tidak dibuat sistem.
- Analisis: highlight rate di atas 90% dan di bawah 50%; hasil remedial (R) dianalisis terpisah.

Belum diputuskan (pakai default, jangan dibangun dulu kalau tidak diminta):
- Detail set R (remedial): rancang agar mudah ditambahkan, tapi kerjakan setelah A/B jalan.
- Isi laporan selain yang tertulis di Fase 5.
- Apakah nama peserta perlu muncul (butuh daftar ID ke nama). Default: tidak.
