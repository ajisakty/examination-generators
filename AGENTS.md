# AGENTS.md — aturan untuk agen AI

Kamu bekerja sebagai programmer junior di proyek Exam Generator (Python 3.12, aplikasi desktop offline).
Baca `PLAN.md` untuk tujuan, teknologi, dan daftar fase.

## Cara kerja
1. Kerjakan SATU fase per permintaan, sesuai yang disebut pengguna. Jangan lompat ke fase lain.
2. Sebelum menulis kode, tulis rencana singkat: file yang akan dibuat atau diubah, langkah-langkah, dan cara mengetesnya. Tunggu persetujuan pengguna.
3. Kerjakan dalam langkah kecil. Setelah selesai, jalankan `pytest` dan laporkan hasilnya apa adanya (lulus atau gagal). Jangan bilang selesai kalau tes gagal.
4. Kalau ada hal yang tidak jelas atau tidak ada di `PLAN.md`: TANYA. Jangan menebak.
5. Jangan menulis ulang atau menghapus file besar. Ubah seperlunya saja.
6. Jangan menambah library, database, API/server, atau akses internet tanpa izin.
7. Jangan menjalankan `git push` atau `git reset --hard`. Jangan menghapus file di luar folder proyek.

## Aturan kode
- Kode di `core/` tidak boleh punya tampilan (tanpa `print` dan jendela). Hasilnya berupa data.
- Proses yang lama (misalnya memindai banyak lembar) menerima fungsi `progress_callback`.
- `core/exam_pdf.py` sudah teruji: jangan ubah perilaku PDF-nya tanpa izin.
- Pesan error untuk pengguna dalam Bahasa Indonesia, jelas, dan menyebut baris/kolom yang salah.
- Setiap fase harus punya tes `pytest`.
- Jangan campur istilah: **Question Code** = kode unik per soal; **Course Code** = kode satu ujian.

## Prinsip scanner
- Ragu = tandai "perlu review". Tidak boleh menebak diam-diam.
- Pakai ambang adaptif per lembar, jangan angka tetap.

## Data
- Isi `tests/fixtures/` bisa memuat soal rahasia dan data peserta. Jangan di-commit, jangan dikirim ke internet.
- Excel kunci jawaban itu rahasia.

## Tambahan (hasil review)
- Kalau diminta memindahkan file, salin isinya apa adanya. Jangan menulis ulang. Setelah itu tunjukkan perbandingan hasilnya dengan versi lama.
- Tampilan PDF soal mengikuti `legacy/exam_pdf_original.py` (sampul, petunjuk, tabel identitas, header, footer, font Carlito di `assets/fonts`). Jangan mengubah tampilan tanpa izin; `tests/test_exam_pdf_parity.py` harus tetap lulus.
- Tes scanner harus mencakup form 3 opsi dan 4 opsi. Tes yang lulus hanya pada satu varian dianggap belum selesai.
