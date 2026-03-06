# ZD PLAYER

Türkçe ve English açıklamalar aşağıdadır.

## Türkçe

ZD PLAYER, Linux Mint için geliştirilmiş yerel bir IPTV oynatıcıdır. Xtream API ve M3U oynatma listelerini destekler.

### Özellikler

- Birden fazla Xtream hesabı ekleme, düzenleme ve silme
- Hesapları JSON olarak yerelde saklama
- `Canlı TV`, `Filmler` ve `Diziler` sekmeleri
- Her içerik türü için kategori filtreleme ve arama
- Dizilerde sezon ve bölüm listeleme
- GStreamer ile uygulama içinde oynatma
- Modern kontrol çubuğu: oynat/duraklat, durdur, tam ekran
- Sağ tık menüsü ile ses izi ve altyazı seçimi
- Mouse tekerleği ile ses seviyesi ayarlama
- Çift tıklama ile tam ekran geçişi
- Video tam ekranda iken kontrollerin otomatik gizlenmesi
- `Esc` / `F11` ile tam ekrandan çıkış

### Çalıştırma

```bash
git clone https://github.com/ZaferBey95/ZD-PLAYER.git
cd ZD-PLAYER
./run.sh
```

Alternatif:

```bash
PYTHONPATH=src python3 -m zdplayer
```

### Mimari

```text
src/zdplayer/
  models.py      - Hesap, kategori, katalog, dizi ve profil modelleri
  storage.py     - Hesapların yerel kalıcılığı
  xtream.py      - Xtream API istemcisi
  app.py         - Uygulama giriş noktası
  ui/
    __init__.py  - Paket dışa aktarımları
    css.py       - GTK3 tema stilleri
    helpers.py   - Yardımcı fonksiyonlar
    dialogs.py   - Hesap ekleme / düzenleme pencereleri
    sidebar.py   - Hesap özeti, içerik tipi seçici ve kategori listesi
    browser.py   - Arama ve içerik listesi
    player.py    - GStreamer oynatıcı ve kontroller
    detail.py    - Seçili içerik detayları ve dizi paneli
    window.py    - Ana pencere
```

### Notlar

- Hesap bilgileri `~/.local/share/zdplayer/state.json` içinde tutulur.
- Canlı TV çıkışı için bazı sağlayıcılar `m3u8`, bazıları `ts` ister.
- Ses ve altyazı seçimi, akışta ilgili track bilgisi varsa sağ tık menüsüyle yapılır.
- Video üzerinde mouse tekerleği ile ses seviyesi ayarlanabilir.

### Ekran Görüntüleri

#### Ana Ekran

![ZD PLAYER ana ekran](assets/screenshots/zdplayer1.png)

#### Giriş Ekranı

![ZD PLAYER giriş ekranı](assets/screenshots/zdplayer2.png)

## English

ZD PLAYER is a local IPTV player built for Linux Mint. It supports Xtream API accounts and M3U playlists.

### Features

- Add, edit, and remove multiple Xtream accounts
- Store accounts locally in JSON format
- Dedicated `Live TV`, `Movies`, and `Series` sections
- Category filtering and search for each content type
- Season and episode browsing for series
- In-app playback powered by GStreamer
- Modern control bar with play/pause, stop, and fullscreen
- Audio track and subtitle selection via right-click menu
- Mouse wheel volume control
- Double-click fullscreen toggle
- Auto-hiding controls in fullscreen mode
- Exit fullscreen with `Esc` or `F11`

### Run

```bash
git clone https://github.com/ZaferBey95/ZD-PLAYER.git
cd ZD-PLAYER
./run.sh
```

Alternative:

```bash
PYTHONPATH=src python3 -m zdplayer
```

### Architecture

```text
src/zdplayer/
  models.py      - Account, category, catalog, series, and profile models
  storage.py     - Local account persistence
  xtream.py      - Xtream API client
  app.py         - Application entry point
  ui/
    __init__.py  - Package exports
    css.py       - GTK3 theme styling
    helpers.py   - Helper utilities
    dialogs.py   - Account add / edit dialogs
    sidebar.py   - Account summary, content type selector, and category list
    browser.py   - Search and content list
    player.py    - GStreamer player and controls
    detail.py    - Selected content details and series panel
    window.py    - Main window
```

### Notes

- Account data is stored in `~/.local/share/zdplayer/state.json`.
- Some providers expect `m3u8` output for live TV, while others require `ts`.
- Audio and subtitle selection is available from the right-click menu when the stream exposes those tracks.
- Volume can be adjusted with the mouse wheel over the video area.

### Screenshots

#### Main Screen

![ZD PLAYER main screen](assets/screenshots/zdplayer1.png)

#### Login Screen

![ZD PLAYER login screen](assets/screenshots/zdplayer2.png)
