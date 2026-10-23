# 23 Ekim 2026 devam doğrulaması

Başlangıç: `main`, `eebb525`, `v0.7.1`. `.hermes/`, `AGENTS.md` ve `DURUM.md`
kullanıcıya ait izlenmeyen dosyalar olarak korundu. Bulunan hatalar için
v0.7.2 ve Chatterbox çalışma zamanı 1.0.1 hazırlandı. Eski yayımlanmış
sürümler ve motor arşivi değiştirilmedi.

## Kaynak düzeltmeleri

Model indirme işçisi pencere kapanışında beklenen işçiler arasında değildi.
Kapanış artık iptal ister ve indirme işçisi bitmeden pencereyi kapatmaz. İşçi
referansı sonuç sinyalinde bırakılmaz; `finished` sonrasında temizlenir.

CUDA denetimi hem indirme eyleminde hem model kurulum katmanında uygulanır.
VoxCPM2'nin CUDA hatası CPU ile yeniden denemeyi önermez. CUDA bulunmayan
makinede sistem satırı ses üretiminin CPU üzerinde yapılacağını açıklar.

## Tamamlanan kontroller

- Başlangıç kaynakları: 304 test başarılı (339,07 saniye).
- İlk düzeltmelerle: 309 test başarılı (238,00 saniye).
- Motor güncellemesi ve v0.7.2 ile: 310 test başarılı (288,72 saniye).
- Derleme sınırlarıyla ilgili son hedef testler: 53 başarılı (26,68 saniye).
- Son CPU açıklaması ve katalogla hedef testler: 73 başarılı (29,18 saniye).
- İlgili UI/model testleri: 44 başarılı. İndirme sırasında gerçek QThread ile
  kapanış/iptal bekleme regresyonu kapsanır.
- `smoke_test.py --no-units`: başarılı. Bu geliştirme ortamı kontrolüdür;
  kurulu EXE'nin çalışma kanıtı değildir.
- Soket bağlantıları engelliyken EMA gerçek sentezi: 48.000 Hz, 128.640 örnek;
  yükleme ve sentez toplamı 1,46 saniye. Torch gerektiren motor başlatılmadı.
- Sandbox dışında donanım: AMD Radeon RX 6650 XT, CUDA yok, RAM 31,1 GB.

Sandbox içindeki ilk test denemesi geçici dosya yeniden adlandırmalarında
WinError 5 verdi. Normal Windows izinleriyle iki tam test çalışması geçti;
bu nedenle bu izin hatası için ürün kodu değiştirilmedi.

## Yayımlanan katalog ve paket kimliği

Başlangıçtaki GitHub metadatası `gh release view` ile canlı okundu. `engines-v1`
Chatterbox 1.0.0 varlığı eski katalogla aynı boyut ve SHA-256 değerine sahipti:

- Dosya: `VoxoraStudio-Chatterbox-1.0.0.vxp`
- Boyut: 298.533.800 bayt
- SHA-256: `d0953902fb590136ef168befc64b76e5661debab6de5d5d96eb9c51a30947544`

Başlangıç kaynağı, yerel v0.7.0 ve v0.7.1 paketlerindeki `engine_packs.json`
SHA-256 değerleri aynı: `d821f25e11f10c4c5ef1b21d870e945fa9ba3623a256cd4bf472c6e6a74feb7d`.

Yerel v0.7.0 kurulum EXE'si GitHub varlığının SHA-256 değeriyle eşleşti:
`f2641f63d6bdb3534542b8965627fd31f67dae3dd0cfe4f2c994831bf4cdb738`.
Kurulum EXE'sinin içinden katalog ayrıca çıkarılmadı. Doğrudan arşiv içeriği
kanıtı yayımlanan v0.7.0 delta paketinden alındı: yerel
`VoxoraStudio-0.7.0-delta-0.6.0.vxd` SHA-256 değeri GitHub ile aynı
(`0c6ee83e49a980cedde16deaff26e33420888feebc4287658947480140da38af`);
`files/_internal/assets/engine_packs.json` içinde dolu pinler mevcut.

Yerel paketlerin EXE arşivlerinde iç sürümler 0.7.0 / 0.7.1, EMA ONNX modülü
mevcut ve PYZ içinde Torch modülü bulunmuyor.

## Gerçek kurulum ve delta sınırı

İlk kontrolde Program Files'taki EXE arşivinden okunan sürüm **0.6.1** idi. Eski
`_delta_result.json`, artık mevcut olmayan staged manifest dosyasına ilişkin
başarısızlık içeriyor. Bu eski kayıt yeni bir test sonucu olarak sunulmadı.

Gerçek kurulum salt okunarak `build_temp/installed-copy-delta-verification`
altına kopyalandı. Bu kopyada `0.6.1 → 0.7.0 → 0.7.1` zinciri uygulandı.
Son v0.7.1 paketinin 1.558 dosyasının tamamı SHA-256 ile eşleşti; eksik veya
farklı dosya ve fazladan klasör yok. Kopyada önceden bulunan kaldırıcı,
`testcopy.exe` ve eski sonuç kaydı korundu.

Kullanıcı aynı oturumda UAC katılımını açıkça onayladı. Gerçek Program Files
klasörü `build_temp/real-installed-delta/backup` altına kopyalanıp hash'leri
doğrulandı. Üretim `delta_worker_ps1` işçisiyle tek UAC altında zincir gerçek
hedefe uygulandı: **1.558 dosya birebir eşleşti**. Kişisel veri klasörüne
yazılmadı. Uygulamanın kendini kapatıp yeniden açması bu disk güncellemesi
testinin parçası değildi. Ham sonuç: `build_temp/real-installed-delta/comparison.json`.

Son 0.7.1 → 0.7.2 gerçek hedef denemesinde yeni geri dönüş kopyası doğrulandı,
ancak Windows yönetici izni verilmedi (`updater._runas` hatası). İşçi çalışmadı;
gerçek kurulum 0.7.1'de kaldı. Bu izin adımı tekrarlanmadı. Son 0.7.2 delta
kapısı ayrı kopyada geçti: beş dosya uygulandı, 1.558 dosya temiz paketle birebir
eşleşti; fazladan dosya/klasör yok. Gerçek 0.7.2 kurulumu olarak sunulmaz.

## Canlı Chatterbox akışı

`scripts/verify_model_download_ui.py`, üretim Qt düğmesi ve gerçek
`ModelInstallWorker` üzerinden izole bir veri köküne gerçek indirme/kurulum
yapar. Ayar/geçmiş kalıcılığı, ilgisiz başlangıç işleri ve motor yükleyicisi
testte devre dışıdır; indirme, paket kurulumu ve durum ölçümü gerçektir.
Bu test masaüstünde elle kullanım veya yayımlanmış EXE'de sentez kanıtı değildir.

Çalıştırma:

```powershell
.\.venv\Scripts\python.exe scripts/verify_model_download_ui.py --data-root build_temp/chatterbox-ui-e2e --live-download
```

Canlı test 647,0 saniyede başarılı tamamlandı. Boş izole kökte çalışma zamanı
ve altı gerçek model dosyası indirildi; yerel ağırlık önbelleğiyle tohumlama
yapılmadı. Paket SHA-256 doğrulaması ve üretim kurucusu çalıştı. Sonuç:

```json
{"installed": true, "status": "Kurulu", "selected": "chatterbox", "applied": "chatterbox", "progress_events": 1907, "progress_hidden": true, "errors": [], "cuda_only_download_disabled": true}
```

Ham sonuç yerel/izlenmeyen `build_temp/chatterbox-ui-e2e/ui-result.json`
dosyasındadır. Motor seçimi UI'da uygulandı; bu testin yükleyicisi mock olduğu
için bu sonuç tek başına modelin belleğe yüklenip sentez yaptığı anlamına gelmez.

## Chatterbox 1.0.1 onarımı

Geliştirme ortamını dışlayan `python -I -S` kontrolü, eski .vxp içinde `httpx`
bulunmadığını gösterdi. Geliştirme ortamının site-packages dizini eksikliği
örtüyordu. Bağımlılık kapanışı `scripts/complete_engine_runtime.py` ile
tamamlandı; demo Gradio ve geliştirme pre-commit araçları hariç tutuldu.
Sürüm envanteri ve mevcut upstream metadata uyumsuzlukları
`scripts/chatterbox-runtime-1.0.1.json` içindedir. Bu, resolver uyumluluğu
iddiası değildir; gerçek çalışma ayrıca doğrulandı.

Temiz Python ortamında ve arşivden kurulan ilk adayda gerçek Türkçe sentez
başarılıydı. Gerçek donmuş EXE ise `timeit` eksikliğini ortaya çıkardı:
PyInstaller yalnız ana EMA uygulamasının eriştiği standart kütüphaneyi toplar.
Bu nedenle isteğe bağlı motora aynı Python 3.11.9'un standart kütüphane
fallback modülleri ve yerel uzantıları, Python lisansıyla birlikte eklendi.
Ana pakete Torch eklenmedi; sistem Python'una paket kurulmadı.

Son .vxp: **323.872.356 bayt**, **25.193 dosya**,
SHA-256 `da6ff6a80b935eb4a272267e41833d8f9872c12fcf8b2059b970ad9ca4f111a0`.
Gerçek kurucu temiz hedefte bütün dosyaları doğruladı. Motor pinine sürüm
eklendi; eski çalışma zamanı güncellenecek, mevcut ağırlıklar korunacak.
Bu çalışma zamanı CPU sürümüdür; NVIDIA üzerinde hızlanma doğrulanmadı ve
motor açıklaması CPU paketini açıkça belirtir.

Eski 1.0.0 kurulum ve gerçek ağırlıklar üzerinde ikinci Qt UI testi 71,2
saniyede geçti. Yeni 1.0.1 arşivi doğrulanmış indirme önbelleğinden sağlandı;
bu ikinci test yeni HTTPS soğuk indirme kanıtı değildir. Gerçek kurucu eski
motoru yeniledi, mevcut ağırlıkları yeniden indirmedi. Son durum `Kurulu`,
seçilen/uygulanan motor `chatterbox`, hata yok, ilerleme çubuğu gizli ve
VoxCPM2 indirme düğmesi kapalı. İlk soğuk indirme sonucu
`ui-result-1.0.0.json`, onarım sonucu `ui-result.json` içinde korunur.

## Derlenmiş EXE kapısı

İlk iç test build'i Codex araç PATH'inden libheif/poppler DLL'leri aldı ve Qt
açılışı başarısız oldu. `build.bat` artık PATH'i Windows ve proje araçlarına
sınırlar, sürüme özel çalışma klasörü kullanır. `verify_build_sources.py`
yabancı yerel bağımlılık kaynaklarını reddeder. Eski hatalı TOC yeni kapıda
reddedildi; temiz TOC geçti. Hatalı iç build yayımlanmadı.

Temiz EXE, izole LOCALAPPDATA ve ayrı model köküyle Windows arayüzünde açıldı.
Computer Use ile metin kutusuna `Merhaba.` yazılıp Ses Üret ve varsayılan sesle
devam eylemleri kullanıldı. Arayüz `Toplam: 1 üretim` ve
`Üretildi - 0.9 sn @ 24000 Hz` gösterdi. Oluşan WAV: **24.000 Hz, 20.956 örnek**,
tepe genliği 0,4031; sonlu ve sessiz olmayan veri. Bu sentetik kişisel olmayan
metin kullanıldı; asıl kullanıcı ayarları değiştirilmedi.

Son paket EXE'sinden çıkarılan `app.engines`, `app.main_window`,
`app.model_manager`, `app.version`, `tts_engine`, `app.workers` kod nesneleri
aynı dosya adıyla derlenen son kaynaklarla birebir eşleşti. Son katalog da
kaynakla bayt bayt eşleşti; ana PYZ içinde Torch yok.

Mevcut eski güncelleyiciler `-Setup.exe` beklediğinden devirde belirtilen
Setup/delta uyumluluğu korunur. GitHub yayını kamuya açık varlık deposunda,
kaynak/tag ise mevcut kaynak deposunda tutulur. Yayın sonrası hash ve latest
kanıtları ayrıca yerel build kayıtlarında ve teslim mesajında raporlanır.

VoxCPM2 pinleri boş bırakıldı. CUDA'lı Windows makinesinde paket kurulumu ve
gerçek 48 kHz sentez doğrulanmadığından paket üretilmedi veya yayımlanmadı.
