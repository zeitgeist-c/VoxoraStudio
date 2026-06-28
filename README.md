# txttoTTS

Chatterbox Multilingual V3 tabanlı, PyQt6 arayüzlü Türkçe metin -> ses dönüştürücü.

**Versiyon:** v0.1.1 (2026-06-27) — bkz. [gitlog.txt](gitlog.txt)

## Durum

Sade masaüstü akışı hazır:

- Türkçe ve çok dilli Chatterbox TTS
- PyQt6 masaüstü arayüzü
- Otomatik CPU/CUDA seçimi
- Model yükleme ve üretim ilerleme pencereleri
- Hazır ses ayarları
- Dil, hız, ifade, netlik, yaratıcılık ve tekrar azaltma ayarları
- Referans ses / ses örneği desteği
- WAV ve MP3 kayıt
- Çıktı geçmişi
- Panodan metin yapıştırma
- Metni temizleme
- Canlı karakter/kelime/parça bilgisi
- Tahmini ses süresi
- Üretim sekmesinde son ayar özeti
- Geçmişten metni geri alma

## Kurulum

### Python 3.11

```powershell
winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
```

### ffmpeg (MP3 için önerilir)

```powershell
winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
```

### Proje kurulumu

```powershell
cd C:\Projeler\txttoTTS
setup.bat
```

`setup.bat`, kurulum başında internet, donanım ve ffmpeg durumunu kontrol eder. NVIDIA GPU varsa CUDA destekli PyTorch kurulumunu otomatik dener; doğrulanamazsa CPU kurulumuna düşer. AMD/Intel Arc gibi DirectML uyumlu GPU varsa `onnxruntime-directml` kurulur; ONNX model yoksa uygulama güvenli şekilde CPU modunda çalışır.

Kurulumdan sonra hızlı kontrol:

```powershell
install_check.bat
```

## Başka PC'ye Kurulum

1. `txttoTTS` klasörünü diğer Windows bilgisayara kopyala.
2. Python 3.11 yoksa kur:

```powershell
winget install Python.Python.3.11 --accept-package-agreements --accept-source-agreements
```

3. MP3 kaydı için ffmpeg kur:

```powershell
winget install Gyan.FFmpeg --accept-package-agreements --accept-source-agreements
```

4. Proje klasöründe kurulumu başlat:

```powershell
setup.bat
```

5. Kurulumu kontrol et:

```powershell
install_check.bat
```

6. Programı çalıştır:

```powershell
run.bat
```

İlk çalıştırmada Chatterbox model dosyaları indirilebilir; bu birkaç dakika sürebilir.

## Çalıştırma

```powershell
run.bat
```

veya:

```powershell
C:\Projeler\txttoTTS\run.bat
```

## Kullanım

1. Üretim sekmesindeki metin alanına metni yaz veya Yapıştır düğmesiyle panodaki metni al.
2. Gerekirse Metni Temizle düğmesiyle fazla boşlukları ve kopyalama kaynaklı satır kırıklarını düzelt.
3. Ayarlar sekmesinde dil, hız, hazır ayar veya ses örneği seç.
4. Üretim sekmesindeki bilgi satırından karakter, kelime, parça ve tahmini süreyi kontrol et.
5. Üret düğmesine bas.
6. Üretim bitince ses otomatik çalınır.
7. Kaydet WAV veya Kaydet MP3 ile dışa aktar.
8. Üretilen sesler Geçmiş sekmesinde listelenir; istersen metni tekrar üretim alanına geri alabilirsin.

## Klavye Kısayolları

| Kısayol | İşlev |
| --- | --- |
| Ctrl+Enter | Üret |
| Ctrl+S | Kaydet WAV |
| Ctrl+Shift+S | Kaydet MP3 |
| Ctrl+Shift+V | Ses Örneği Seç |

## Ses Örneği

Ses Örneği bölümünde üretilecek sesin benzemesini istediğin konuşmadan örnek seçebilirsin.

> **İlk üretimde referans ses örneği seçmeniz önerilir; aksi halde ses robotik olabilir.**
> Üretim sekmesinde uyarı banner'ı ve ilk üretimde onay penceresi bunu hatırlatır.

- Önerilen süre: 5-20 saniye
- İdeal hedef: 10-15 saniye
- Tek kişi konuşmalı
- Arka plan sessiz olmalı
- Müzik, yankı ve mikrofon patlaması olmamalı

Ses Örneği Rehberi düğmesi, okunabilecek örnek metni ve kayıt ipuçlarını gösterir.

## NVIDIA CUDA / GPU

Kurulum otomatik GPU kontrolü yapar.

- NVIDIA GPU varsa CUDA destekli PyTorch kurulumu denenir.
- CUDA doğrulanırsa uygulama otomatik GPU kullanır.
- CUDA kurulamazsa CPU moduna güvenli şekilde düşer.
- Uygulama açıldığında durum satırında kullanılan cihaz görünür: `cuda` veya `cpu`.

## ONNX / DirectML (AMD/Intel Arc GPU)

Plan 17+ ile AMD ve Intel Arc GPU'larda DirectML hızlandırma:

```bash
python scripts/export_onnx.py    # T3 ONNX export (models/chatterbox_t3.onnx)
```

`scripts/gpu_detect.has_directml_capable_gpu()` True dönerse DirectML provider otomatik seçilir.

## MP3 Kalite

Ayarlar sekmesinde MP3 bitrate seçilebilir: Konuşma (128 kbps) / Podcast (192 kbps, varsayılan) / Yüksek kalite (320 kbps).
Seçim kalıcıdır; pencere kapatılıp açılsa da korunur.

## Üretim Sayacı

Durum çubuğunda "Toplam: X üretim" gösterilir; her başarılı üretimde artar, pencere kapatılsa kalıcıdır.

## Geçmiş

"Kayıt Klasörü" Ayarlar sekmesinden seçilebilir; otomatik WAV kayıtları seçilen klasöre gider.
"Toplu Sil" tüm geçmişi temizlemek için kullanılabilir.
"Geri Dönüşüm'e Taşı" seçeneği dosyaları Windows Geri Dönüşüm'e taşır (send2trash ile). "Sadece listeden kaldır" yalnızca geçmişten kaldırır.
Yeni üretimlerde preset adı ve hız `[Anlatıcı • 0.90x]` formatında gösterilir.

## Notlar

- Varsayılan otomatik kayıt klasörü: `outputs/` (Ayarlar sekmesinden değiştirilebilir)
- Loglar: `logs/`
- Ayar/geçmiş durumu: `state/`
- CPU modunda ilk sentez yavaş olabilir.

## Test

Smoke test ortamı doğrular:

```powershell
.venv\Scripts\python.exe smoke_test.py             # light: unit test + import + ortam
.venv\Scripts\python.exe smoke_test.py --full      # TTS motor + sentez (ağır)
```

Unit test'leri tek başına çalıştırmak için:

```powershell
.venv\Scripts\python.exe -m unittest discover -s tests -v
```
