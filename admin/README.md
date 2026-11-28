# English Day Admin (Web)

Web admin untuk memantau aktivitas belajar siswa SMAN 10 Gowa: ringkasan sekolah,
direktori siswa dan kelas, performa per modul, riwayat latihan, dan hasil evaluasi AI.
Perencanaan halaman mengikuti dokumen PM "Perencanaan Web Admin – English Day";
tampilan mengacu ke referensi Stitch (warna `#1D4ED8`, font Plus Jakarta Sans + Inter).

> **Status: slicing UI dengan data demo.** Backend belum punya endpoint admin, jadi
> semua angka berasal dari `DemoAdminRepository` (±500 siswa, 12 kelas, data tetap
> setiap kali dijalankan). Lihat [Menyambungkan ke backend](#menyambungkan-ke-backend).

## Menjalankan

Butuh Flutter 3.41.x (sama dengan aplikasi siswa).

```bash
cd admin
flutter pub get
flutter run -d chrome
```

Login demo (juga tertulis di halaman login saat mode debug):
**admin@sman10gowa.sch.id** / **admin123**

## Halaman

| URL | Halaman | Dokumen PM |
|---|---|---|
| `/login` | Login (email + password, show/hide, validasi) | 3.A |
| `/dashboard` | Total/Active Students, Total Classes, Average Score, Learning Activity per modul, Student Performance per grade, Recent Activity | 3.B |
| `/students` | Tab **Students**: cari nama/ID, filter grade, tabel, pagination | 3.C.1 |
| `/students?tab=classes` | Tab **Classes**: filter grade, kartu kelas per grade | 3.C.2 |
| `/classes/:id` | Detail kelas: ringkasan, performa modul, daftar siswa | 3.C.2 ("View Class") |
| `/students/:id` | Student Detail: info, Learning Overview, Module Performance, Learning History per modul | 3.D |
| `/students/:id/exercises/:id` | Exercise Detail sesuai modul (Writing: teks + koreksi; Reading/Listening: jawaban; Speaking: transkrip) + evaluasi AI | 3.E |

Profil dan **Logout** ada di menu avatar kanan atas (dokumen PM bagian 5). Setiap halaman
punya URL sendiri, jadi bisa di-bookmark dan tombol back browser berfungsi. Di layar
< 1000 px sidebar berubah menjadi menu laci.

Elemen Stitch yang **tidak** dibuat karena tidak ada di dokumen PM: Export Roster,
Sync Directory, lonceng notifikasi, pencarian global, Curriculum Benchmark, statistik
pemasaran di halaman login.

## Struktur kode

```
lib/
├── main.dart, app.dart          # Router (go_router) + redirect ke /login
├── core/
│   ├── app_info.dart            # Nama sekolah, tahun ajaran
│   ├── format.dart              # Format tanggal, skor, durasi
│   ├── theme/admin_theme.dart   # Warna & font dari referensi Stitch
│   └── widgets/                 # Shell (sidebar/top bar), tabel, kartu, pagination
├── data/
│   ├── models.dart              # Student, SchoolClass, ExerciseRecord/Detail, Dashboard
│   ├── admin_repository.dart    # Interface yang dipakai semua halaman
│   ├── demo_admin_repository.dart  # Data demo (sementara)
│   └── providers.dart           # Riverpod: repository, sesi admin, data per halaman
└── features/                    # auth, dashboard, students (list, kelas, siswa, latihan)
```

Halaman hanya mengenal `AdminRepository`. Saat endpoint backend siap, buat
`ApiAdminRepository` (pola koneksi sama dengan aplikasi siswa: dio + token + refresh)
dan ganti satu baris di `adminRepositoryProvider`. Tidak ada halaman yang perlu diubah.

## Menyambungkan ke backend

Yang perlu disiapkan tim backend sebelum web admin bisa memakai data asli:

1. **Peran admin.** Akun admin dibuat oleh sekolah/backend, tidak bisa didaftar sendiri
   (saat ini peran "teacher" dipilih sendiri saat register dan tidak memberi akses apa pun).
2. **Data sekolah pada siswa.** Nomor induk (Student ID), grade, dan kelas. Backend saat
   ini hanya menyimpan nama, email, dan peran.
3. **Endpoint admin** (hanya untuk peran admin), kira-kira:
   - `GET /admin/dashboard` – total siswa, siswa aktif, jumlah kelas, rata-rata skor,
     aktivitas per modul, rata-rata per grade, aktivitas terbaru
   - `GET /admin/students?query=&grade=&class_id=&page=` – daftar siswa + rata-rata skor
   - `GET /admin/classes?grade=` dan `GET /admin/classes/{id}`
   - `GET /admin/students/{id}` – ringkasan, skor per modul, riwayat latihan
   - `GET /admin/students/{id}/attempts/{attempt_id}` – isi latihan + evaluasi AI
4. **Skala skor yang sama.** Web admin memakai 0–100. Writing/Speaking dari backend
   berskala band 0–9, Reading/Listening berupa jumlah benar, jadi perlu dinormalkan.
5. **Learning Time.** Perlu dicatat (mis. lama setiap attempt); saat ini belum ada.

## Test

```bash
flutter analyze
flutter test    # data demo + alur login, dashboard, students, classes, logout
```
