# VoxoraStudio — Yerel çok dilli seslendirme stüdyosu

> English: [README.md](./README.md)

PyQt6 arayüzlü, tamamen yerel metinden sese üretim stüdyosu. Program **EMA
Lightning** motoruyla kurulur (Türkçe, tek ses, 48 kHz, CPU'da bile hızlı);
**Chatterbox** (16 dil + ses klonlama) ve **VoxCPM2** (30 dil + ses tasarımı)
istenirse program içinden indirilir.

![Üretim stüdyosu](./docs/screenshots/01-uretim.png)

## Özellikler

- **Üç ses motoru, kullanıcı seçer** — EMA Lightning pakette gelir; Chatterbox
  ve VoxCPM2 Modeller sekmesinden indirilir. Hiçbiri zorla indirilmez.
- **Ses klonlama** — referans örnek (5–20 sn öneri); Chatterbox ve VoxCPM2.
- **Ses tasarımı** — referans ses olmadan, tarifle yeni ses (yalnız VoxCPM2).
- **Donanım kapısı** — VoxCPM2 yalnız NVIDIA/CUDA olan bilgisayarlarda
  seçilebilir ve indirilebilir; CUDA yoksa düğme kapalı ve nedeni yazılı.
- **İnce ayar** — dil, hız, ifade, netlik, yaratıcılık, tekrar azaltma + presetler.
- **Uzun metin parçalama** — parça işleme + süre tahmini.
- **WAV + MP3 + OPUS** — ffmpeg ile biçime göre kalite seçimi.
- **Üretim geçmişi** — otomatik kayıt, geri al, toplu sil, Geri Dönüşüm'e taşı.
- **Kurulumlu sürüm** — Windows kurulum dosyası, tek tık güncelleme,
  korunan ayarlar/modeller.

## Kurulum (kullanıcı)

`VoxoraStudio-X.Y.Z-Setup.exe` dosyasını çalıştırın (~180 MB).

| Ne | Nerede | Güncelleme siler mi? |
|---|---|---|
| Program (EXE + kütüphaneler + ffmpeg + EMA modeli) | `C:\Program Files\VoxoraStudio` | Evet — yerine yenisi yazılır |
| Ayarlar, geçmiş, çıktılar, loglar | `%LOCALAPPDATA%\VoxoraStudio` | **Hayır** |
| İndirilen motorlar ve modeller | `%LOCALAPPDATA%\VoxoraStudio\engines` + `\models` | **Hayır** |

Kurulum masaüstü ve Başlat Menüsü kısayolları oluşturur. Kaldırmada ayarlar,
çıktılar ve indirilmiş modeller korunur.

### Ses motorları

| Motor | Boyut | Diller | Nereden |
|---|---|---|---|
| **EMA Lightning** | 44 MB | Türkçe | Paketle gelir — indirme yok |
| **Chatterbox Multilingual** | 3,5 GB | 16 | Modeller ▸ İndir |
| **VoxCPM2** | 5,2 GB | 30 + ses tasarımı | Modeller ▸ İndir (yalnız CUDA) |

Motor paketleri (`.vxp`) kullanıcı klasörüne açılır; sistem Python'una hiçbir
şey kurulmaz, program klasörüne yazılmaz. Her dosya SHA-256 ile doğrulanır,
indirme yarıda kalırsa kaldığı yerden devam eder.

### Güncelleme

**Ayarlar ▸ Güncelleme** iki yoldan birini kullanır:

- **Hızlı güncelleme (delta, ~48 MB):** yalnız değişen dosyalar iner.
- **Tam kurulum (~180 MB):** delta yoksa tam setup iner ve sessiz kurulur.

Her iki yolda da Windows bir kez yönetici izni ister ve program kendini
yeniden başlatır. İndirilmiş motorlar ve modeller dokunulmadan kalır.

## Hızlı başlangıç (geliştirme)

Gereksinim: Python 3.11 + ffmpeg (MP3 için) + Inno Setup 6 (kurulum dosyası için).

```bat
setup.bat          :: internet/donanım kontrolü, sanal ortam
install_check.bat  :: kurulum doğrulama
run.bat            :: konsolsuz başlat (debug: VOXORA_SHOW_CONSOLE=1)
build.bat          :: dist\VoxoraStudio-X.Y.Z\ + dist\installer\VoxoraStudio-X.Y.Z-Setup.exe
```

İsteğe bağlı motorları geliştirmek için: `pip install -r requirements-dev.txt`
(torch, chatterbox-tts, voxcpm). Bunlar pakete girmez.

Test: `smoke_test.py`, `python -m pytest -q`.

Eski otomasyonlar için `TXTOTTS_SHOW_CONSOLE` ve `TXTOTTS_HIDDEN` değişkenleri
geriye dönük uyumluluk amacıyla kabul edilir (`VOXORA_SHOW_CONSOLE` /
`VOXORA_HIDDEN` olarak eşlenir).

Kaynak kopyada (`python app.py`) veri yine depo kökündeki `state/`, `logs/`,
`outputs/` altında tutulur; ayrım yalnız paketlenmiş kurulumda geçerlidir.

## Proje yapısı

```text
app.py               giriş noktası
app/main_window.py   ana pencere, sayfalar
app/paths.py         program / kullanıcı verisi / model yolu ayrımı
app/hardware.py      CUDA + GPU + RAM + disk tespiti (motor kapısı)
app/engines.py       motor kayıtları: dil, yetenek, boyut, donanım koşulu
app/model_manager.py motor kurulum durumu, indir/kaldır akışı
app/engine_pack.py   .vxp motor paketi: üret, doğrula, kur, kaldır
app/downloader.py    ilerlemeli, iptal edilebilir, SHA-256 doğrulamalı indirici
app/ema_onnx.py      EMA Lightning ONNX motoru (torch gerekmez)
app/voxcpm_engine.py VoxCPM2 motoru (yalnız CUDA)
app/first_run.py     ilk açılış sihirbazı
app/updater.py       kurulum dosyası indirme + sessiz kurulum
installer/           Inno Setup betiği (VoxoraStudio.iss)
tts_engine.py        motor yönlendirici (ortak yüzey: numpy)
models/ema-onnx/     paketlenen EMA ağırlıkları
assets/engine_packs.json   motor paketi sürüm pinleri
scripts/             setup_env, gpu_detect, delta üretimi
```

## Katkı

Küçük PR, commit'e model dosyası/çıktı konmaz. Bkz. [.github/PULL_REQUEST_TEMPLATE.md](./.github/PULL_REQUEST_TEMPLATE.md).

## Lisans

Bkz. [LICENSE](./LICENSE) (bekliyor — teyit edilecek).

Motor lisansları: EMA Lightning (Apache-2.0), Chatterbox (MIT),
VoxCPM2 (Apache-2.0). Ticari kullanım serbest.
