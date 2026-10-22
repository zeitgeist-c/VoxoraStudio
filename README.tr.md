# VoxoraStudio — Yerel çok dilli seslendirme stüdyosu

> English: [README.md](./README.md)

Chatterbox Multilingual V3 ve EMA Lightning tabanlı, PyQt6 arayüzlü metinden sese üretim stüdyosu. Türkçe + çok dilli, referans örnekle ses klonlama; EMA ile hızlı tek sesli Türkçe üretim — CPU/CUDA/DirectML ile tam yerel çalışır.

![Üretim stüdyosu](./docs/screenshots/01-uretim.png)

## Özellikler

- **İki ses motoru** — Chatterbox V3 (çok dilli + klonlama) ve EMA Lightning (Türkçe, tek ses, ~34 MB, CPU'da bile çok hızlı).
- **Ses klonlama** — referans örnek (5–20 sn öneri) + rehber düğmesi.
- **İnce ayar** — dil, hız, ifade, netlik, yaratıcılık, tekrar azaltma + hazır presetler.
- **Uzun metin parçalama** — parça işleme + süre tahmini, karakter/kelime/parça bilgisi.
- **WAV + MP3 + OPUS** — ffmpeg ile biçime göre kalite seçimi.
- **Otomatik donanım** — CPU/CUDA seçimi + DirectML/ONNX.
- **Üretim geçmişi** — otomatik kayıt (`outputs`), geri al, toplu sil, Geri Dönüşüm'e taşı.
- **Hızlı giriş** — pano yapıştırma, metin temizleme, kısayollar (Ctrl+Enter, Ctrl+S…).
- **Kalıcı durum** — ayarlar ve geçmiş kullanıcı veri klasöründe, loglar ayrı.
- **İlerleme arayüzü** — model/üretim ilerleme pencereleri, ilk üretimde referans-ses uyarısı.
- **Kurulumlu sürüm** — Windows kurulum dosyası, tek tık güncelleme, korunan ayarlar/modeller.

## Kurulum (kullanıcı)

`VoxoraStudio-X.Y.Z-Setup.exe` dosyasını çalıştırın.

| Ne | Nerede | Güncelleme siler mi? |
|---|---|---|
| Program (EXE + kütüphaneler + ffmpeg) | `C:\Program Files\VoxoraStudio` | Evet — yerine yenisi yazılır |
| Ayarlar, geçmiş, çıktılar, loglar | `%LOCALAPPDATA%\VoxoraStudio` | **Hayır** |
| Ses modelleri (Chatterbox ~3.2 GB, EMA ~34 MB) | `%USERPROFILE%\.cache\huggingface` | **Hayır** |

Kurulum masaüstü ve Başlat Menüsü kısayolları oluşturur; her güncellemede
kendisi yeniler. Kaldırmada ayarlar, çıktılar ve modeller korunur.

Uygulama içi **Ayarlar ▸ Güncelleme** iki yoldan birini kullanır:

- **Hızlı güncelleme (delta, ~90 MB):** Yayında kurulu sürümünüzü taban alan
  bir delta varsa yalnız değişen dosyalar iner, doğrulanır ve yerine yazılır.
  Ayarlar, çıktılar ve modeller dokunulmadan kalır.
- **Tam kurulum (364-382 MB):** Delta yoksa ya da uygulanamazsa tam setup iner
  ve sessiz kurulur (aynı sonuç, daha büyük indirme).

Her iki yolda da Windows bir kez yönetici izni ister (Program Files'a yazılıyor)
ve program kendini yeniden başlatır. Model dosyaları değişmediyse yeniden
indirilmez.

## Hızlı başlangıç (geliştirme)

Gereksinim: Python 3.11 + ffmpeg (MP3 için) + Inno Setup 6 (kurulum dosyası için).

```bat
setup.bat          :: internet/donanım/ffmpeg kontrolü, CUDA yoksa CPU
install_check.bat  :: kurulum doğrulama
run.bat            :: konsolsuz başlat (debug: VOXORA_SHOW_CONSOLE=1)
build.bat          :: dist\VoxoraStudio-0.6.1\ + dist\installer\VoxoraStudio-0.6.1-Setup.exe
```

Test: `smoke_test.py` (light/full), `python -m unittest discover -s tests -v`.

Eski otomasyonlar için `TXTOTTS_SHOW_CONSOLE` ve `TXTOTTS_HIDDEN` değişkenleri geriye dönük uyumluluk amacıyla kabul edilir (`VOXORA_SHOW_CONSOLE` / `VOXORA_HIDDEN` olarak eşlenir).

Kaynak kopyada (`python app.py`) veri yine depo kökündeki `state/`, `logs/`,
`outputs/` altında tutulur; ayrım yalnız paketlenmiş kurulumda geçerlidir.

## Proje yapısı

```text
app.py               giriş noktası (arayüz app/ paketinde)
app/                 main_window, dialogs, workers, theme, icons, widgets
app/paths.py         program / kullanıcı verisi yolu ayrımı
app/updater.py       kurulum dosyası indirme + sessiz kurulum
installer/           Inno Setup betiği (VoxoraStudio.iss)
tts_engine.py        TTS motoru
audio_compressor.py  MP3/OPUS dışa aktarma
audio_player.py      önizleme oynatma
chunker.py           uzun metin bölme
config.py            ayarlar (app_state.py, state/)
scripts/             setup_env, gpu_detect, export_onnx
tests/  outputs/  models/  logs/  docs/
```

## Katkı

Küçük PR, commit'e model dosyası/çıktı konmaz. Bkz. [.github/PULL_REQUEST_TEMPLATE.md](./.github/PULL_REQUEST_TEMPLATE.md).

## Lisans

Bkz. [LICENSE](./LICENSE) (bekliyor — teyit edilecek).
