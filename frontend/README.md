# English Day · SMAN 10 Gowa (Mobile EduTech App)

Implementasi Frontend Flutter lengkap untuk aplikasi pembelajaran bahasa Inggris **English Day** SMAN 10 Gowa, dislicing secara presisi 1:1 dari 58 desain visual pada folder [`docs/design/`](../docs/design/) di root repo.

Login, dashboard, profil, Writing, Reading, dan Listening sudah tersambung ke backend
(`/api/v1`, lihat [Menghubungkan ke backend](#menghubungkan-ke-backend)). Speaking masih
memakai data dummy. Galeri desain (debug) selalu memakai data demo tanpa server.

---

## 📱 Daftar Modul & Layar (58 State Desain)

Aplikasi mencakup seluruh state visual yang dirancang dalam folder desain:

### 1. Akun & Otentikasi
- **Splash Screen** (`Akun · splash.png`) — Tampilan awal branding English Day SMAN 10 Gowa.
- **Login** (`Akun · login.png`) — Form masuk (email & password dengan toggle show/hide).
- **Login Loading** (`Akun · login-loading.png`) — State tombol `Masuk…` dengan progress indicator.
- **Login Error** (`Akun · login-error.png`) — Banner peringatan `Email atau password salah` + tombol `Coba lagi`.
- **Register** (`Akun · register.png`) — Form pendaftaran akun, pilihan peran (Siswa / Guru).
- **Register Error** (`Akun · register-error.png`) — Validasi field (nama wajib diisi, format email, password min. 8 karakter, konfirmasi password tidak cocok).

### 2. Dashboard
- **Dashboard - Lanjutkan Latihan** (`Dashboard · lanjutkan latihan.png`) — Header sapaan personal `Halo, Rina`, avatar inisial `RA`, card resume latihan terakhir (`Reading · The Lost Kite`), dan 4 menu modul latihan.
- **Dashboard - Pengguna Baru** (`Dashboard · pengguna baru.png`) — Tampilan dashboard awal tanpa kartu resume latihan.

### 3. Writing (Latihan Menulis)
- **Input Kosong** (`Writing · input empty.png`) — Kertas bergaris (lined paper) untuk menulis kalimat/paragraf dengan counter karakter `0/500`.
- **Input Terisi** (`Writing · input filled.png`) — Input berisi contoh kalimat bahasa Inggris.
- **Input Loading** (`Writing · input loading.png`) — Tombol `Mengecek…` aktif dengan teks tersimpan info.
- **Input Lambat / AI Slow** (`Writing · input slow.png`) — Banner oranye: *"Masih memproses. Kamu bisa menunggu atau batalkan."*
- **Input Timeout / Error** (`Writing · input error.png`) — Banner merah: *"AI belum merespons. Coba lagi dalam beberapa saat."*
- **Input Limit Karakter** (`Writing · input limit.png`) — Peringatan melebihi batas 500 karakter (`Kurangi X karakter agar bisa dicek`).
- **Hasil Loading** (`Writing · hasil loading.png`) — Efek shimmer / skeleton paragraf saat menyiapkan koreksi.
- **Hasil Koreksi** (`Writing · hasil corrections.png`) — Teks bergaris dengan kata salah dicoret merah dan kata perbaikan di atasnya, serta versi perbaikan bersih.
- **Penjelasan Aturan Tata Bahasa** (`Writing · hasil sheet.png`) — Bottom sheet detail aturan (contoh: *Bentuk lampau / past tense*).
- **Hasil Kalimat Benar** (`Writing · hasil correct.png`) — Tampilan sukses ketika tidak ada kesalahan grammar.

### 4. Reading (Latihan Membaca)
- **Pengaturan Reading** (`Reading · pengaturan.png`) — Pemilihan level kesulitan (Easy A2, Medium B1, Hard B2) dan topik (Sekolah, Olahraga, Teknologi, Budaya, Alam, Acak).
- **Cerita Loading** (`Reading · cerita loading.png`) — Shimmer / skeleton pembentukan cerita oleh AI.
- **Cerita Slow & Error** (`Reading · cerita slow.png`, `Reading · cerita error.png`) — State lambat dan timeout pembuatan cerita.
- **Tampilan Cerita** (`Reading · cerita story.png`, `Reading · cerita continuation.png`) — Cerita pendek bergaya tipografi serif dengan highlight stabilo kuning pada kosakata kunci.
- **Kosakata Sheet** (`Reading · cerita sheet.png`) — Modal bottom sheet penjelasan arti dan contoh kalimat kata yang distabilo.
- **Kuis Reading** (`Reading · kuis empty.png`, `selected`, `correct`, `wrong`) — 5 soal pilihan ganda interaktif dengan indikator progres dan feedback pembahasan instan.
- **Hasil Kuis** (`Reading · kuis result.png`) — Skor akhir dengan badge stabilo kuning, ringkasan dan review pembahasan per soal.

### 5. Speaking (Latihan Berbicara)
- **Izin Mikrofon** (`Izin mikrofon · permintaan.png`, `ditolak permanen.png`) — Layar persetujuan akses mikrofon dan penanganan izin ditolak permanen.
- **Percakapan Speaking** (`Speaking · empty.png`, `idle.png`) — Bubble obrolan dua arah dengan tombol audio AI.
- **Merekam Suara** (`Speaking · recording.png`) — Animasi sound wave, tombol stop, dan live transcription ucapan pengguna.
- **Memproses & AI Berbicara** (`Speaking · processing.png`, `speaking.png`) — State AI menganalisis dan merespons audio.
- **Slow & Error** (`Speaking · slow.png`, `error.png`) — Notifikasi koneksi lambat dan deteksi suara tidak terdengar jelas.

### 6. Listening (Latihan Menyimak)
- **Intro** (`Listening · empty.png`) — Halaman pembuka latihan audio listening.
- **Loading & Slow** (`Listening · loading.png`, `slow.png`) — Penyiapan streaming audio.
- **Audio Player Interaktif** (`Listening · playing.png`) — Play/pause audio player, scrubber progres, replay, dan pengatur kecepatan playback (0.75x, 1x).
- **Pertanyaan & State Terkunci** (`Listening · questions.png`, `locked.png`) — Soal pemahaman listening dengan transkrip terkunci sebelum dijawab.
- **Error Audio** (`Listening · error.png`) — Penanganan kegagalan koneksi audio.
- **Hasil & Review** (`Listening · result.png`, `review.png`) — Skor latihan dan evaluasi benar/salah setiap nomor.
- **Transkrip Terbuka** (`Listening · transcript.png`) — Transkrip lengkap percakapan dengan kalimat bukti kunci distabilo.

### 7. Profil & Fitur Global
- **Profil Pengguna** (`Profil.png`) — Data profil dummy (Rina Amelia, Siswa, SMAN 10 Gowa), menu ubah nama, ubah password, dan tentang aplikasi.
- **Konfirmasi Keluar** (`Profil · konfirmasi keluar.png`) — Bottom sheet dialog konfirmasi logout.
- **Offline Mode** (`Global · offline.png`) — Layar peringatan tidak ada koneksi internet + tombol coba lagi.
- **Banner Status AI** (`Global · banner AI.png`) — Demonstrasi variasi banner status AI global.
- **Sesi Habis** (`Global · sesi habis.png`) — Bottom sheet pemberitahuan sesi berakhir.
- **Notifikasi Teks Disalin** (`Global · teks disalin.png`) — Floating snackbar konfirmasi copy text.
- **Showcase Komponen UI** (`Komponen · tombol.png`, `input dan pilihan.png`, `jawaban dan percakapan.png`) — Katalog komponen desain sistem token.

---

## 🎨 Galeri Desain UI (Interactive Showcase)

Untuk mempermudah verifikasi dan review slicing 1:1 terhadap seluruh 58 file gambar desain:
1. Buka aplikasi dan masuk ke menu **Profil** (avatar di pojok kanan atas Dashboard).
2. Pilih menu **Tentang aplikasi**.
3. Di dalam halaman ini terdapat **Galeri UI (58 layar)** yang dikelompokkan rapi berdasarkan kategori. Anda dapat mengklik setiap item untuk membuka layar dan state persis seperti mockup Figma / PNG.

Galeri hanya tersedia di **build debug** (`flutter run`). Di build release, menu
**Tentang aplikasi** menampilkan info aplikasi biasa.

---

## 🚀 Cara Menjalankan

Gunakan **Flutter 3.41.x (stable)** agar `pubspec.lock` sama untuk semua anggota tim
(cek dengan `flutter --version`).

```bash
# Dari root repo, masuk ke folder frontend
cd frontend

# Ambil dependencies
flutter pub get

# Jalankan di Emulator Android/iOS / Windows desktop
flutter run
# atau di Chrome (lihat catatan CORS di bawah)
flutter run -d chrome --web-port 5000
```

### Menghubungkan ke backend

Login, register, dashboard, profil, Writing, Reading dan Listening memakai API backend
(`/api/v1`). Jalankan backend dulu (butuh **Docker Desktop**), lihat [README root](../README.md):

```bash
cd backend
make start
```

Alamat API dipilih otomatis ([`lib/core/config/api_config.dart`](lib/core/config/api_config.dart)):

| Menjalankan di | Alamat API |
|---|---|
| Emulator Android | `http://10.0.2.2:8000/api/v1` |
| Chrome, Windows, simulator iOS | `http://localhost:8000/api/v1` |
| HP sungguhan / server lain | `flutter run --dart-define=API_BASE_URL=http://192.168.1.20:8000/api/v1` |

**Chrome (CORS):** browser menolak request ke backend kecuali origin-nya diizinkan.
Tambahkan origin Flutter web ke `backend/.env` (konfigurasi lokal, tidak di-commit),
lalu `make restart`:

```env
CORS_ORIGINS=["http://localhost:5000"]
```

dan selalu jalankan Chrome dengan port yang sama: `flutter run -d chrome --web-port 5000`.

**HP sungguhan:** di `backend/.env` set `API_BIND=0.0.0.0` dan tambahkan IP laptop ke
`ALLOWED_HOSTS` (lihat README root), lalu pakai `--dart-define` seperti tabel di atas.

**AI sungguhan vs AI palsu:** secara default backend development memakai AI palsu (`fake`):
soal, koreksi dan audio hanya contoh (koreksi Writing cuma mengenali beberapa pola, audio
berupa bunyi "beep"). Untuk AI sungguhan isi `AI_PROVIDER=router` dan `ROUTER_API_KEY=...`
di `backend/.env` (minta key ke tim backend), lalu `make restart`. Aplikasi tidak perlu diubah.

**Setelah menarik perubahan yang menambah package** (mis. `audioplayers` untuk Listening):
hentikan `flutter run` (`q`) lalu jalankan lagi; hot restart (`R`) tidak cukup untuk
plugin baru.

Tanpa backend, aplikasi menampilkan layar **"Tidak ada koneksi internet"** saat ada sesi
tersimpan, atau pesan error di layar login. Galeri desain (Profil → Tentang aplikasi)
tetap bisa dibuka karena memakai data demo.

---

## 📁 Struktur Kode

Kode disusun **per fitur**. State management memakai **Riverpod**
(`flutter_riverpod`, `ProviderScope` dipasang di `main.dart`).

```
lib/
├── main.dart                          # Entry point: ProviderScope + EnglishDayApp
├── app.dart                           # MaterialApp + sheet "sesi berakhir" global
├── core/                              # Dipakai semua fitur
│   ├── config/
│   │   ├── api_config.dart            # Alamat API (otomatis per platform / --dart-define)
│   │   └── app_info.dart              # Nama aplikasi, sekolah, versi
│   ├── models/choice_question.dart    # Soal pilihan ganda + jawaban yang dinilai server
│   ├── navigation/route_observer.dart # Layar tahu saat tampil lagi (dashboard refresh)
│   ├── network/
│   │   ├── api_client.dart            # dio: token, refresh antre (single-flight), Idempotency-Key
│   │   ├── api_exception.dart         # Error backend {code, message, ...} + pesan Indonesia
│   │   ├── jobs.dart                  # Job AI + polling GET /jobs/{id}
│   │   └── providers.dart             # apiClientProvider, tokenStorageProvider
│   ├── storage/token_storage.dart     # Simpan token (flutter_secure_storage)
│   ├── text/text_span_offsets.dart    # Offset code point (backend) → UTF-16 (Dart)
│   ├── theme/app_theme.dart           # Design tokens (AppColors, AppText/GoogleFonts, AppTheme)
│   └── widgets/
│       ├── answer_widgets.dart        # AnswerOption, AnswerFeedback, ChatBubble, SoundWave
│       ├── app_button.dart            # AppButton (primary, secondary, danger, loading), AppTextAction
│       ├── app_text_field.dart        # AppTextField, FieldError, AppChoiceChip
│       ├── common.dart                # AppScaffold, BottomActionBar, AppCard, StatusBanner, Skeleton, InfoStateView
│       └── lined_paper.dart           # LinedPaper, LinedText, CorrectionText (kertas bergaris)
├── features/                          # Satu folder per fitur, satu file per layar
│   ├── auth/                          # ✅ tersambung API
│   │   ├── data/                      # User, AuthRepository (/auth/*, /users/me)
│   │   ├── application/               # SessionController (status login seluruh app)
│   │   └── presentation/              # splash, login, register
│   ├── dashboard/                     # ✅ tersambung API
│   │   ├── data/dashboard.dart        # DashboardData, dashboardProvider (GET /dashboard)
│   │   └── presentation/              # dashboard (+ sheet sesi habis)
│   ├── writing/                       # ✅ tersambung API (koreksi oleh AI)
│   │   ├── data/                      # WritingResult (koreksi), WritingRepository
│   │   ├── application/               # WritingSession (soal → draft → submit → evaluasi)
│   │   └── presentation/              # input, hasil koreksi
│   ├── reading/                       # ✅ tersambung API (cerita & kuis dari AI)
│   │   ├── data/                      # ReadingStory (+kosakata), ReadingRepository
│   │   ├── application/               # ReadingSession (cerita → jawab per soal → skor)
│   │   └── presentation/              # pengaturan, cerita, kuis, hasil
│   ├── listening/                     # ✅ tersambung API (audio dari backend)
│   │   ├── data/                      # ListeningExercise, transkrip, ListeningRepository
│   │   ├── application/               # ListeningSession, ListeningAudio (audioplayers)
│   │   └── presentation/              # listening (intro → audio → soal → hasil)
│   ├── speaking/presentation/         # izin mikrofon, percakapan (masih dummy)
│   ├── profile/presentation/          # ✅ profil & keluar (ubah nama/password: belum)
│   └── system/presentation/           # offline
└── dev/                               # Alat developer, BUKAN untuk pengguna akhir
    ├── demo_scope.dart                # Akun & dashboard demo untuk galeri (tanpa server)
    ├── demo_reading.dart              # Reading demo untuk galeri
    ├── demo_listening.dart            # Listening demo untuk galeri (audio disimulasikan)
    ├── dummy_data.dart                # Data dummy sementara (sampai fitur tersambung ke API)
    ├── gallery_screen.dart            # Galeri 58 state desain (debug only)
    └── showcase/                      # Katalog komponen & banner AI
```

Aturan untuk anggota tim:

- Layar baru masuk ke `features/<fitur>/presentation/`. Komponen yang dipakai lebih
  dari satu fitur masuk ke `core/widgets/`.
- Saat sebuah fitur disambungkan ke API, tambahkan `features/<fitur>/data/` (model +
  repository) dan `features/<fitur>/application/` (provider/controller Riverpod).
- Kode di `features/` yang masih meng-import `dev/dummy_data.dart` berarti **belum
  tersambung ke API**. Cek sisa pekerjaan dengan `grep -rl "dev/dummy_data" lib/features`.
- Pakai import `package:english_day/...` (bukan relatif) supaya aman saat file dipindah.

## 🧪 Test

```bash
flutter analyze
flutter test        # termasuk render seluruh 58 state galeri (test/gallery_test.dart)
```
