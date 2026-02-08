# Gemini Desktop Automation

Aplikasi desktop untuk automasi Gemini AI dengan interface modern dan fitur lengkap.

> **⚡ Desktop-Only Version** - Aplikasi ini TIDAK memiliki web interface. Semua fitur diakses melalui desktop app.

## ✨ Fitur Utama

- **Multi-Account Management** - Kelola banyak akun Google Gemini Bisnis sekaligus
- **Auto Registration** - Registrasi otomatis akun baru dengan temporary email (headless mode)
- **Smart Rotation** - Sistem rotasi akun otomatis dengan rate limit handling
- **Chat Automation** - Generate text, gambar, dan video dengan AI
- **Built-in Gallery** - Preview dan manage hasil generasi (gambar & video)
- **Video Player** - OS default player untuk smooth video playback
- **Modern UI** - Interface modern dengan CustomTkinter dan color scheme professional
- **Dashboard Stats** - Monitor real-time stats akun dan request

## 📋 Requirements

- Python 3.9+
- Windows/Linux/MacOS
- Browser (untuk auto-registration)

## 🚀 Quick Start

### 1. Install Dependencies

Install semua dependencies yang diperlukan:

```bash
pip install -r requirements.txt
```

**Dependencies utama:**
- `fastapi` - Backend API framework
- `uvicorn` - ASGI server
- `customtkinter` - Modern GUI framework
- `playwright` - Browser automation
- `undetected-chromedriver` - Anti-detection browser
- `duckduckgo-search` - Free temp mail provider
- `httpx` - HTTP client
- `python-dotenv` - Environment configuration
- `pillow` - Image processing
- `pydantic` - Data validation

Setelah install dependencies, install Playwright browsers:

```bash
python -m playwright install chromium
```

### 2. Konfigurasi

Buat file `.env` dari `.env.example`:

```bash
cp .env.example .env
```

**Minimal Configuration:**
```env
# Kunci Admin untuk login ke aplikasi desktop (WAJIB)
ADMIN_KEY=Pasardigital26

# Port Server (optional, default 7860)
# PORT=7860
```

**Optional Settings** (bisa diatur di app Settings):
- Proxy configuration
- Temp mail provider (DuckMail, FreeMail, dll)
- Browser settings
- Rate limit cooldown

### 3. Run Application

**Jalankan secara manual:**

Buka **2 terminal** dan jalankan:

**Terminal 1 - Backend API:**
```bash
python main.py
```
Tunggu sampai muncul pesan "Application startup complete"

**Terminal 2 - Desktop GUI:**
```bash
python msverify.py
```

GUI akan terbuka dan siap digunakan.

## 🎯 Cara Pakai

### Tab Chat
1. Klik tab "Chat" di sidebar
2. Pilih model AI (Gemini 2.0, 2.5, dll)
3. Ketik prompt Anda
4. Klik "Generate" atau tekan Enter
5. Hasil akan muncul di panel sebelah kanan

### Tab Image
1. Klik tab "Image" 
2. Masukkan deskripsi gambar yang diinginkan
3. Pilih model (Gemini Imagen 3.0 Fast/Quality)
4. Klik "Generate"
5. Preview otomatis muncul setelah selesai

### Tab Video
1. Klik tab "Video"
2. Tulis deskripsi video (prompt yang detail lebih baik)
3. Pilih model Veo 2.0
4. Tunggu proses (biasanya 1-2 menit)
5. Play video langsung di built-in player

### Gallery
- Klik tab "Gallery" untuk lihat semua hasil generasi
- Preview gambar dengan klik card
- Play video dengan built-in player
- Delete file yang tidak diperlukan
- Buka folder dengan tombol "Open Folder"

### Account Management
1. Tab "Accounts" - Lihat semua akun yang terdaftar
2. Tombol "+" - Tambah akun manual (email & password)
3. "Auto Register" - Registrasi otomatis akun baru
4. "Refresh" - Refresh cookie akun yang expired
5. Status badge menunjukkan kondisi akun

## ⚙️ Settings

### Browser Settings
- **Headless Mode**: Untuk server/VPS tanpa display
- **Browser Engine**: UC (unstable) atau DP (stable, recommended)

### Mail Provider
- **DuckMail**: Cepat, reliable
- **FreeMail**: Alternatif gratis
- **GPTMail**: Custom domain support
- **Moemail**: High availability

### Rate Limit
- **Chat Cooldown**: Default 2 jam
- **Image Cooldown**: Default 4 jam  
- **Video Cooldown**: Default 4 jam
- Otomatis skip akun yang sedang cooldown

## 📁 Struktur Project

```
geminibisnis/
├── main.py                 # Backend API (FastAPI) - START FIRST!
├── msverify.py             # Desktop GUI app
├── requirements.txt        # Dependencies
├── .env                    # Configuration
├── core/                   # Core automation logic
│   ├── account.py         # Multi-account management
│   ├── auth.py            # Authentication
│   ├── gemini_automation.py  # Browser automation
│   ├── register_service.py   # Auto registration
│   ├── login_service.py   # Login automation
│   └── mail_providers/    # Temp email clients
├── data/                   # Storage (auto created)
│   ├── images/            # Generated images
│   ├── videos/            # Generated videos
│   └── uptime.json        # Metrics & stats
└── util/                   # Utility functions
```

## 🔧 Troubleshooting

### Registrasi Gagal
- Matikan headless mode di Settings
- Coba ganti browser engine (UC ↔ DP)
- Pastikan proxy tidak block Google

### Rate Limit Terus
- Tambah lebih banyak akun
- Naikkan cooldown time di Settings
- Gunakan API key sebagai backup

### Video Tidak Keluar
- Pastikan pakai model Veo 2.0
- Prompt harus cukup detail (min 20 kata)
- Tunggu sampai progress bar selesai

### Video Lag/Crash
- Aplikasi menggunakan OS default player (bukan built-in)
- Video akan terbuka di aplikasi sistem Anda
- Lebih smooth dan tidak memberatkan aplikasi

### Cookie Expired
- Klik "Refresh Expired" untuk auto-refresh semua
- Atau refresh manual per akun di Account tab

### Dashboard Kosong
- Pastikan sudah ada akun yang aktif
- Lakukan beberapa request dulu untuk generate stats
- Stats update real-time setelah request completed

## 🎨 Features Highlights

- ✅ **Pure Desktop** - Tidak ada web interface, ringan dan cepat
- ✅ **Auto Registration** - Browser headless mode by default
- ✅ **Smart Video Player** - Menggunakan OS default player (no lag!)
- ✅ **Real-time Dashboard** - Monitor stats dan akun status
- ✅ **Indonesian Interface** - UI dan pesan error dalam bahasa Indonesia

## 📝 License

MIT License - Copyright (c) 2026 Masanto

## 🤝 Support

Jika ada issue atau pertanyaan, silakan buat issue di GitHub repository.

---

**Built with ❤️ using Python, CustomTkinter, FastAPI, and Gemini AI**
