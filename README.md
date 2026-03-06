# ZD PLAYER

Modern bir Linux IPTV oynatıcısı.  
A modern IPTV player for Linux.

> **Yasal Uyarı / Legal Notice**
>
> **Türkçe:** ZD PLAYER yalnızca bir IPTV oynatma istemcisidir. Bu proje herhangi bir yayın, kanal, medya içeriği, abonelik, hesap veya erişim bilgisi sağlamaz, barındırmaz, dağıtmaz ya da paylaşmaz. Uygulama yalnızca kullanıcının kendi yasal olarak yetkili olduğu Xtream API veya M3U kaynaklarını oynatmak için tasarlanmıştır. Kullanıcı tarafından eklenen içeriklerin, yayınların ve hesap bilgilerinin yasallığı ile kullanım sorumluluğu tamamen kullanıcıya aittir. Proje sahibi ve katkıda bulunanlar, kullanıcıların eklediği içeriklerden veya üçüncü taraf servislerin kullanımından doğan sonuçlar hakkında herhangi bir sorumluluk kabul etmez.
>
> **English:** ZD PLAYER is an IPTV playback client only. This project does not provide, host, distribute, or share any streams, channels, media content, subscriptions, accounts, or access credentials. The application is designed solely to play Xtream API or M3U sources that the user is legally authorized to access. The legality and use of all content, streams, and account credentials added by the user are the sole responsibility of the user. The project owner and contributors accept no liability for user-supplied content or for any consequences arising from the use of third-party services.

---

## Türkçe

ZD PLAYER, Xtream API ve M3U oynatma listeleri için geliştirilmiş masaüstü bir IPTV oynatıcıdır. GTK 3 ve GStreamer tabanlıdır ve yerel Linux masaüstü deneyimi sunar.

### Uyumluluk

ZD PLAYER yalnızca Linux Mint ile sınırlı değildir.

- Uygulama Linux Mint üzerinde geliştirilmiş ve test edilmiştir.
- Hazır `.deb` paketi Linux Mint, Ubuntu, Debian ve diğer Debian tabanlı dağıtımlar için uygundur.
- Kaynak koddan çalıştırma yöntemi; Python 3.10+, GTK 3, PyGObject ve GStreamer 1.0 bağımlılıkları sağlandığında çoğu modern Linux dağıtımında çalışmalıdır.
- Fedora, Arch, openSUSE ve diğer dağıtımlarda çalışması mümkündür; ancak paketleme ve bağımlılık adları dağıtıma göre değişebilir.
- Her Linux dağıtımında ayrı ayrı test edilmemiştir.

Kısa özet:

- `.deb` kurulum: Debian tabanlı sistemler için
- Kaynaktan çalıştırma: Uygun bağımlılıklar varsa çoğu Linux sistemi için

### Özellikler

- Xtream API hesapları ekleme, düzenleme ve silme
- M3U oynatma listesi desteği
- `Canlı TV`, `Filmler` ve `Diziler` bölümleri
- Kategori filtreleme ve arama
- Dizi sezon ve bölüm gezintisi
- GStreamer tabanlı yerel oynatma
- Ses izi ve altyazı seçimi
- Tam ekran desteği
- Mouse tekerleği ile ses kontrolü
- Çok dilli arayüz
- Yerel ayar ve hesap saklama

### Paket Kurulumu

Debian tabanlı sistemlerde:

```bash
sudo apt install ./com.zdplayer_1.0_all.deb
```

Kurulumdan sonra uygulama menüsünde `ZD PLAYER` olarak görünür.

### Kaynaktan Çalıştırma

```bash
git clone https://github.com/ZaferBey95/ZD-PLAYER.git
cd ZD-PLAYER
./run.sh
```

Alternatif:

```bash
PYTHONPATH=src python3 -m zdplayer
```

### Gerekli Bileşenler

Kaynak koddan çalıştırmak için tipik olarak şu bileşenler gerekir:

- Python 3.10+
- `python3-gi`
- `python3-requests`
- GTK 3
- GStreamer 1.0
- `gstreamer1.0-plugins-good`
- GTK-GStreamer entegrasyon paketleri

Debian tabanlı sistemlerde `.deb` paketi bu bağımlılıkları doğrudan tanımlar.

### Veri Saklama

- Hesaplar ve uygulama durumu `~/.local/share/zdplayer/` altında tutulur.
- Kullanıcıya ait Xtream veya M3U bilgileri paket dosyasına dahil edilmez.

### Proje Yapısı

```text
src/zdplayer/
  app.py         - Uygulama giriş noktası
  storage.py     - Yerel hesap ve durum saklama
  settings.py    - Uygulama ayarları
  xtream.py      - Xtream API istemcisi
  m3u.py         - M3U işleme desteği
  models.py      - Veri modelleri
  ui/            - GTK arayüz bileşenleri
```

### Ekran Görüntüleri

#### Ana Ekran

![ZD PLAYER ana ekran](assets/screenshots/zdplayer1.png)

#### Giriş Ekranı

![ZD PLAYER giriş ekranı](assets/screenshots/zdplayer2.png)

---

## English

ZD PLAYER is a desktop IPTV player built for Xtream API accounts and M3U playlists. It uses GTK 3 and GStreamer to provide a native Linux desktop experience.

### Compatibility

ZD PLAYER is not limited to Linux Mint only.

- The application was developed and tested on Linux Mint.
- The provided `.deb` package is intended for Linux Mint, Ubuntu, Debian, and other Debian-based distributions.
- Running from source should work on most modern Linux distributions as long as Python 3.10+, GTK 3, PyGObject, and GStreamer 1.0 dependencies are available.
- Fedora, Arch, openSUSE, and other distributions may also run it, but package names and installation steps will differ.
- It has not been individually tested on every Linux distribution.

Short summary:

- `.deb` installation: for Debian-based systems
- Source-based run: for most Linux systems with the required dependencies

### Features

- Add, edit, and remove Xtream API accounts
- M3U playlist support
- Dedicated `Live TV`, `Movies`, and `Series` sections
- Category filtering and search
- Season and episode browsing
- Native playback powered by GStreamer
- Audio track and subtitle selection
- Fullscreen support
- Mouse-wheel volume control
- Multi-language interface
- Local settings and account storage

### Package Installation

On Debian-based systems:

```bash
sudo apt install ./com.zdplayer_1.0_all.deb
```

After installation, the app appears in the application menu as `ZD PLAYER`.

### Run From Source

```bash
git clone https://github.com/ZaferBey95/ZD-PLAYER.git
cd ZD-PLAYER
./run.sh
```

Alternative:

```bash
PYTHONPATH=src python3 -m zdplayer
```

### Requirements

Typical runtime requirements for source execution:

- Python 3.10+
- `python3-gi`
- `python3-requests`
- GTK 3
- GStreamer 1.0
- `gstreamer1.0-plugins-good`
- GTK/GStreamer integration packages

On Debian-based systems, the `.deb` package declares these dependencies directly.

### Data Storage

- Accounts and application state are stored under `~/.local/share/zdplayer/`.
- Personal Xtream or M3U credentials are not bundled into the package.

### Project Structure

```text
src/zdplayer/
  app.py         - Application entry point
  storage.py     - Local account and state storage
  settings.py    - Application settings
  xtream.py      - Xtream API client
  m3u.py         - M3U processing support
  models.py      - Data models
  ui/            - GTK user interface components
```

### Screenshots

#### Main Screen

![ZD PLAYER main screen](assets/screenshots/zdplayer1.png)

#### Login Screen

![ZD PLAYER login screen](assets/screenshots/zdplayer2.png)
