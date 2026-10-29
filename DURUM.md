# VoxoraStudio — DURUM (ortak — Desktop + Telegram okur)

**Güncelleme:** 2026-10-30
**Versiyon:** v0.7.4 — tek repo zeitgeist-c/VoxoraStudio Release
**Branch:** main
**Son commit:** `eebb525` (release: v0.7.1 …) · etiket `v0.7.1` iki repoda
**Ağaç:** temiz (yalnız kullanıcıya ait untracked: `.hermes/`, `AGENTS.md`, `DURUM.md`)

## Arayüz yenileme (v0.5.0, 2026-10-17)
- Kullanıcı dört kararla seçti: ana yay A (violet koyu) + arşiv B (liste solda/detay sağda) + Araçlar A (liste solda) + Ayarlar A (sol kategori menüsü).
- Sol kenar çubuğu yerine üst nav (Üretim/Arşiv/Araçlar/Ayarlar); üretim sayısı sağ üstte.
- Üretim iki sütun: solda Metin + Kuyruk, sağda Ses Profili + Sonuç. İstatistik pill'leri sade etikete indi (yatay taşmayı önledi).
- Arşiv: liste solda, sağda seçili kaydın detayı (ad, dalga, süre/ayar/dosya, eylemler).
- Araçlar merkezi: sol araç listesi (Sıkıştır, Sistem Bilgisi) + sağda aracın sayfası; sıkıştırma çıktı ayarı Ayarlar>Çıktı'ya taşındı.
- Ayarlar: sol kategori menüsü (Ses/Çıktı/Görünüm/Güncelleme/Sıfırla) + tek kart sağda.
- Palet: koyu tema violet A değerleri (pencere #0B0D16, kart #121628, vurgu #8B7CF6); topnav/subnav QSS eklendi.
- Doğrulama: 71 test (1 atlandı), 4 sayfanın gerçek grab'ı vision ile incelendi, min genişlik ölçümleri 1080px'e sığıyor.
- Mockup/kanıt dosyaları: `AppData/Local/hermes/cache/scratch/voxora-tasarim/` (repo dışı).

## Güncelleme sistemi (v0.4.0, 2026-10-17)
- WordArc kalıbı: public ayna repo `zeitgeist-c/VoxoraStudio-Releases` (yalnız ZIP asset, kod yok; tokensuz `releases/latest` sorgusu).
- `app/updater.py`: semver karşılaştırma, indirmede boyut+SHA256 doğrulama (GitHub asset digest), ZIP-güvenliği (zip-slip/sürücü yolu reddi), kardeş klasöre açma (`VoxoraStudio-Y/`), swap.bat ile yeni paketten yeniden başlama; çalışan klasöre ve kullanıcı verisine dokunulmaz, eski klasör silinmez.
- Kullanıcı verisi göçü: `state/*.json` yoksa kopyalanır; ayarlardaki eski paket yolları (output/voice) yeni klasöre çevrilip dosyalar taşınır/kopyalanır; `models/` taşınır, `outputs/` kopyalanır.
- Akış: açılıştan 30 sn sonra + günde 1 sessiz denetim (durum çubuğunda iz), Ayarlar ▸ Güncelleme kartında Denetle / İndir ve Kur / Vazgeç; `update_last_check` settings.json'da.
- `scripts/make_update_package.py`: sürüm klasöründen GERÇEK ZIP üretir (state/logs/outputs/.update hariç). `build.bat` artık ZIP de üretir.
- ⚠ Önceki `VoxoraStudio-0.3.4.zip` Release asset'i uzantısı .zip olan TAR arşiviymiş (zipfile açamıyor, tar açıyor). Yeni ZIP gerçek ZIP; ayna repoya yalnız gerçek ZIP yüklenmeli.
- Testler: `tests/test_updater.py` 13 yeni test; toplam 71 geçti, 1 atlandı.

## v0.5.1 hata düzeltmesi (2026-10-17)
- Belirti: paket EXE'de motor yüklerken `'NoneType' object is not callable` (chatterbox\mtl_tts.py:155).
- Kök neden 1: setuptools 81+ `pkg_resources`'ı kaldırıyor; `perth/perth_net/__init__.py` `from pkg_resources import resource_filename` başarısız olup hatayı yutuyor, `PerthImplicitWatermarker = None` kalıyor; Chatterbox `None()` çağırıyor. 0.3.4'ten beri ortam sürümüne bağlı olarak var.
- Kök neden 2: noconsole EXE'de stdout yok; huggingface_hub indirme çubuğu tqdm `OSError: [Errno 22]` atıyor.
- Çözüm: requirements.txt'ye `setuptools<81` pini; build.bat'e `--hidden-import "pkg_resources"`; app.py'de `HF_HUB_DISABLE_PROGRESS_BARS=1` + `TQDM_DISABLE=1` (konsolsuz paket).
- Doğrulama: venv'de PerthImplicitWatermarker örnekle + tam sentez (24 kHz, 53333 örnek); izole klasörde paketin KENDİ EXE'siyle motor yükleme "Aktif motor: TorchEngine (cpu)"; 71 test.
- Release: her iki repo `v0.5.1`, SHA256 `60077e39…5d02`, canlı updater 0.5.0→0.5.1 görüyor.

## v0.5.2 sürüm kaydı tamamlama (2026-10-17)
- Kod değişikliği yok; sürüm 0.5.2'ye yükseltildi, EXE/BAT/ZIP aynı kaynakla yeniden üretildi.
- `gitlog.txt` geri dolduruldu: v0.4.0 (güncelleme sistemi), v0.5.0 (arayüz yenileme), v0.5.1 (pkg_resources/tqdm düzeltmesi) blokları eklendi.
- Kapılar: 71 passed + 1 skipped (pytest/unittest), smoke light TÜM KONTROLLER BAŞARILI.
- Paket kanıtı: izole klasörde paketin KENDİ EXE'si → "Aktif motor: TorchEngine (cpu)", logda sıfır Traceback; ZIP 7087 girdi, tek kök, veri sızması yok.
- Release: her iki repo `v0.5.2`, SHA256 `3c3c24db…3a95`; canlı updater 0.5.1→0.5.2 görüyor, 0.5.2 "güncel".

## Güncelleme akışı düzeltmesi (v0.5.3, 2026-10-17)
- Kullanıcı iki sorun bildirdi: indirme göstergesi canlı veri göstermiyor; güncelleme sonrası eski sürüm klasörleri silinmiyor.
- Kök neden 1 (kritik): `app/workers.py` `UpdateWorker._install` içinde `updater` modülü import edilmemişti (`NameError`); canlı 0.5.0 logunda kanıtlı — "İndir ve Kur" hiç çalışmamış, bar sadece dönüyordu.
- Kök neden 2: eski sürüm silme kodu hiç yoktu (kasıtlı "silinmez" yorumu) ve paket İÇ İÇE açılıyordu (`VoxoraStudio-Y/VoxoraStudio-X`), silinemez yapıdaydı.
- Düzeltme — `app/updater.py`: `RateMeter`, `format_bytes/speed/eta`, `download(..., phase=)` + `phase("verify")`, `stale_package_dirs`, `write_cleanup_marker`, `cleanup_after_update`, `cleanup_pending`, `_cleanable_package_dir` güvenlik kapısı, `_remove_tree` (3 deneme), `swap_script_text` ayrıştırması, `last_cleanup_result`.
- Düzeltme — `app/workers.py`: modül düzeyi `from . import updater` (NameError fix); yeni sinyaller `progress(int,int,float)` + `phase(str)`; RateMeter'lı zaman tabanlı (~0.15 sn) yayın; yeni paket artık eskisinin YANINA (kardeş) açılıyor; temizlik fişi yazımı.
- Düzeltme — `app/main_window.py`: canlı satır "X / Y (%p) • 12.4 MB/s • kalan ~3 dk 12 sn" + 0..1000 bar; `phase` metinleri (doğrulanıyor/ayıklanıyor); vazgeç akışı; açılışta `cleanup_after_update` (2,5 sn gecikme) + sonuç bildirimi.
- Temizlik kuralı: yalnız aynı üst klasördeki, `^VoxoraStudio-\d+\.\d+\.\d+$` kalıplı ve sürümü çalışandan KÜÇÜK kardeş klasörler silinir; yeni paketin state'ine `update_cleanup.json` fişi bırakılır; kilitliyse (çalışan klasör) fiş daraltılıp sonraki açılışa bırakılır.
- Testler: `tests/test_updater.py` +11 (Format 3, RateMeter 2, Temizlik 4, Swap 1, InstallWorker regresyon 1; dosya toplam 21); paket geneli 82 passed + 1 skipped.
- Doğrulama: çevrimdışı E2E simülasyonu (gerçek `file://` indirme + SHA256 + fiş + yeni açılışta temizlik) "E2E OK"; UI kontrol scripti tüm durum metinlerini doğruladı, 3 ekran görüntüsü (teklif/indiriliyor/doğrulama) incelendi.
- ⚠ Canlı 0.5.0-0.5.2 paketleri bu NameError yüzünden kendi kendini güncelleyemez; düzeltilmiş sürüme geçiş için bir kez ELLE ZIP kurulumu şart (sonrası normal akış).
- Paket/Release: `build.bat` ile EXE/BAT/ZIP üretildi (`dist\VoxoraStudio-0.5.3.zip`, 7087 girdi, 538.4 MB); izole klasörde paketin KENDİ EXE'si "Aktif motor: TorchEngine (cpu)", logda sıfır Traceback; ZIP tek kök, kullanıcı verisi sızıntısı yok.
- Release: her iki repo `v0.5.3` (ZIP asset), SHA256 `4e51591b…60396a7` GitHub digest ile birebir; canlı algılama 0.5.0/0.5.2 → 0.5.3 görüyor, 0.5.3 "güncel".
- Canlı geçiş (elle, kullanıcı onayıyla): `Downloads\Programs\VoxoraStudio-0.5.3` yan klasöre kuruldu, ayar/geçmiş taşındı (`output_dir` yeni klasöre çevrildi); eski `VoxoraStudio-0.5.0` klasörü + eski 0.5.0 ZIP Geri Dönüşüm Kutusu'na taşındı — yalnız 0.5.3 kaldı.

## EMA Lightning — ikinci ses motoru (2026-10-19, ağaçta; yayınlanmadı)
- Karar: **Chatterbox varsayılan kalır**; `ema-lightning` 1.1.2 (Apache-2.0, ~34 MB, yalnız Türkçe, tek kadın sesi, 48 kHz) ikinci motor olarak gömüldü. Lisans temiz → ticari dağıtıma engel yok; Chatterbox MIT olarak yerinde.
- `tts_engine.py`: `EmaEngine` (modelin kendi `speed` parametresi; `accepts_speed = True` ile dispatcher time-stretch'i atlar, çıktı 48 kHz) + `TTSEngine(engine_name=...)` + `display_name`; bilinmeyen motor adı sessizce Chatterbox'a düşer.
- Sabitler: `config.py` → `ENGINE_CHATTERBOX` / `ENGINE_EMA` / `DEFAULT_ENGINE` / `VALID_ENGINES`; `app/constants.py` → `ENGINE_OPTIONS`.
- `app/main_window.py`: Ayarlar ▸ Ses ▸ **"Ses motoru"** combo'su. EMA seçilince dil "tr"ye kilitlenir; hazır ayar / ifade / netlik / yaratıcılık / tekrar azaltma ve referans ses düğmeleri kapanır; **hız + duraklama geçerli kalır**. Motor değişiminde model arka planda `ModelLoadDialog` ile yeniden yüklenir (üretim sürerken değişim engellenir, combo eski değere döner). Chatterbox dil tercihi `chatterbox_language_id` ile korunur. Ayarları sıfırlama motoru/dili varsayılana çeker; cihaz ve sistem bilgisi etiketleri motor adını gösterir.
- Özet satırı EMA'da: "EMA Lightning • Türkçe • 0.90x • Duraklama 0.35 sn • Tek ses"; Ses Profili kartı "EMA Lightning tek kadın sesiyle okur; referans ses kullanılmaz."
- Ağırlıklar ilk kullanımda HF önbelleğine iner (`~/.cache/huggingface/hub/models--canberkkkkkk--ema-lightning`, ~33 MB); sonrası tamamen çevrimdışı.
- Paket hazırlığı: `requirements.txt` → `ema-lightning>=1.1.2`; `build.bat` import kontrolü + `--collect-all ema_lightning` / `--collect-all normalizer_tr`; `install_check.bat`, `scripts/setup_env.py` (`check_ema_import`), `smoke_test.py` kontrol satırları; `app.py` → `HF_HUB_DISABLE_SYMLINKS_WARNING=1`.
- Testler: `tests/test_ema_engine.py` (10), `tests/test_engine_selection_ui.py` (8) → **paket geneli 101 test geçti, 1 atlandı**.
- Doğrulama (gerçek, uygulamanın kendi akışı, offscreen): EMA yükleme (CPU) → EMA sentezi 48 kHz WAV + otomatik dosya kaydı → Chatterbox'a geçiş (TorchEngine/cpu, dil "en" geri geldi) + kısa sentez (24 kHz) → EMA'ya dönüş; tüm adımlar başarılı. Yerleşim kontrolü: motor combo'su kart sınırları içinde (taşma yok), 4 referans düğmesi görünür ama kapalı, Chatterbox'a özel 6 alan kapalı, hız/duraklama açık.
- Smoke: "TÜM KONTROLLER BAŞARILI" (`ema-lightning import: OK (1.1.2)`).
- ⚠ Sürüm bump / build / Release / commit / push YAPILMADI — kullanıcı onayı ("tmm") bekliyor.
- ⚠ Offscreen ekran görüntülerinde yazı tipi çizilmiyor (tofu) — bu ortam artefaktı; gerçek pencere ekran görüntüleri (`docs/screenshots/`) sorunsuz.

### Görsel düzeltme — açılır kutu/sayı kutusu okları (2026-10-19, aynı ağaçta)
- Kullanıcı "Ses motoru'nu nereden seçiyoruz göremedim" dedi; incelemede kök neden bulundu: `app/theme.py` QSS'inde `QComboBox::drop-down` ve `QSpinBox/QDoubleSpinBox::up-button/down-button` biçimlendirilmiş ama `::down-arrow` / `::up-arrow` için hiç görsel verilmemişti — Qt alt-kontrol biçimlendirildiğinde kendi okunu çizmediği için **tüm açılır kutular ve sayı kutuları düz metin alanı gibi görünüyordu** (yalnız motor kutusu değil: Dil, Hazır ayar, Tema, MP3 kalite, Hız/İfade/Netlik...).
- Düzeltme: `app/assets/spin-down-light.svg` + `app/assets/spin-up-light.svg` eklendi (koyu tema mevcut `spin-down/up.svg` dosyalarını kullanır, bu dosyalar şimdiye dek hiç referans edilmiyordu); `_stylesheet` temaya göre `image: url(...)` gömüyor (`QComboBox::down-arrow`, `QSpinBox/QDoubleSpinBox::up-arrow/down-arrow`). `asset_path()` kullanıldığı için paketli EXE'de de çalışır (`--add-data app\assets` zaten var).
- Yerleşim: `engine_combo` ızgarada 3 kolona yayılıyordu (861 px genişlik; formun geri kalanı 374 px) → tek kolona indirildi; en uzun madde metni 213 px, 374 px'e rahat sığıyor.
- Doğrulama: her iki tema için QSS'teki `url()` yolları diskte var; gerçek pencere görüntülerinde motor kutusunda aşağı ok, Hız/İfade/Netlik/… sayı kutularında yukarı-aşağı oklar görünüyor (vision ile doğrulandı); 100 test + 1 atlandı, smoke "TÜM KONTROLLER BAŞARILI".
- Kanıt görselleri (repo dışı): `AppData/Local/hermes/cache/scratch/voxora-ema-gorseller/` (tüm sekmeler + işaretli motor satırı).

## v0.5.4 sürümü (yayınlandı — 2026-10-19)
- Kullanıcı kararı: yedek + **üçüncü basamak** bump (0.5.3 → 0.5.4). Kapsam: EMA Lightning ikinci motoru + açılır kutu/sayı kutusu oku düzeltmesi.
- Kapılar: 100 passed + 1 skipped (pytest), smoke "TÜM KONTROLLER BAŞARILI", sürüm kaynağı `app/version.py` + `tests/test_voxora_contracts.py` + README'ler 0.5.4'e senkron.
- Paket: `build.bat` → `dist\VoxoraStudio-0.5.4\` + `VoxoraStudio-0.5.4.bat` + `VoxoraStudio-0.5.4.zip` (**7164 girdi, 539.8 MB** / 566.040.487 bayt). ZIP tek kök, iç içe sürüm klasörü yok, kullanıcı verisi (state/logs/outputs/.update) sızıntısı yok.
- Donmuş paket doğrulaması (izole klasör, paketin KENDİ EXE'si): temiz durumda "Aktif motor: Chatterbox Multilingual / TorchEngine (cihaz=cpu)", `engine=ema` ile "Aktif motor: EMA Lightning / EmaEngine (cihaz=cpu)"; her iki açılışta logda Traceback/ERROR yok. Gömülü dosya eşitliği: `ema_lightning` 10/10, `normalizer_tr` 4/4.
- ⚠ Kalan: paketli GUI'de otomatik üretim denenemedi (pencere öne alma/odak güvenilir olmadı; tuş gönderimi başka pencereye gidebilir — bu yüzden zorlanmadı). Kullanıcı 0.5.4'ü açıp **Ayarlar ▸ Ses ▸ Ses motoru ▸ EMA Lightning** ile bir cümle üretmeli.
- SHA256 (ZIP): `cf0e8d09…8f28` — yerel dosya, ana repo asset digest'i ve ayna repo asset digest'i birebir aynı.
- Release: her iki repo `v0.5.4` (ZIP asset) — `zeitgeist-c/VoxoraStudio` (Voxora Studio 0.5.4) ve `zeitgeist-c/VoxoraStudio-Releases` (VoxoraStudio 0.5.4). Canlı `releases/latest` = **v0.5.4**, asset digest eşleşiyor → 0.5.3 kurulumları uygulama içinden güncelleyebilir.
- **Güncelleme kanalı E2E (canlı asset ile):** `updater.fetch_latest()` → 0.5.4; `check_for_update("0.5.3")` teklif veriyor, `check_for_update("0.5.4")` "güncel"; indirme 566.040.487 bayt / 41 sn (13,2 MB/s), SHA256 GitHub digest'iyle birebir, ZIP bütünlüğü temiz (7164 girdi), güvenli çıkarma başarılı. Sürüm karşılaştırması 0.5.10 > 0.5.9 (sayısal) ✓.

### Aynı sürüm üzerine yazma (2026-10-19, kullanıcı kararı: "versiyon yükseltmeyelim")
- Eklenen: üst barda marka yazısının yanında **sürüm rozeti** (`v0.5.4`) — `app/main_window.py` + `app/theme.py` (koyu/açık tema QSS); sürüm tek kaynaktan (`app/version.py`).
- Yeniden build: `dist/VoxoraStudio-0.5.4.*` yerinde yenilendi — ZIP **566.040.542 bayt**, yeni SHA256 `a7bc77d5…c959`.
- Doğrulama: 100 passed + 1 skipped; gerçek pencere görüntüsü (koyu + açık tema, 1080 px'te taşma yok); donmuş paket üst barında rozet görüntüsüyle kanıtlandı; donmuş pakette motor yükleme (TorchEngine/cpu) ve log temizliği tekrar doğrulandı.
- Commit `eae5cfe` → `main`'e push; `v0.5.4` etiketi bu commit'e taşındı (`--force`); iki repodaki ZIP asset `--clobber` ile yenilendi, release notları güncellendi.
- Not: 0.5.4'ü zaten kurmuş bir makine aynı sürüm numarasını görüp güncelleme istemez (sürüm karşılaştırması); 0.5.3 ve altı yeni dosyayı alır.

### Güncelleme sonrası yeniden başlatma düzeltmesi (2026-10-19, aynı sürüm yeniden yazıldı)
- **Canlı bulgu:** Kullanıcının 0.5.3 → 0.5.4 güncellemesi "Sürüm 0.5.4 hazır. Program yeniden başlatılıyor…" adımında asılı kaldı. Kurulu paketin log'unda: `OSError: [WinError 87] Parametre hatalı` → `app/updater.py:536 spawn_swap`.
- **Kök neden 1:** `subprocess.Popen`'a `DETACHED_PROCESS | CREATE_NEW_CONSOLE` **birlikte** verilmiş; Windows CreateProcess bu kombinasyonu reddediyor. Düzeltme: tek başına `CREATE_NO_WINDOW` (gizli konsol, pencere gözükmez).
- **Kök neden 2 (aynı akışta, taklitsiz devir testiyle çıktı):** swap betiğindeki `tasklist ... | find " PID "` boru hattı PATH'e göre MSYS'in Unix `find`'ine düşüyor, eşleşme olmuyor ve betik **beklemeyi atlayıp yeni sürümü eski sürüm kapanmadan** açıyordu. Düzeltme: `tasklist /FO CSV /NH` çıktısının 2. alanı doğrudan karşılaştırılır (`for /f` + `if "%%~A"=="PID"`), `%SystemRoot%\System32\tasklist.exe` tam yoluyla.
- **Ek sağlamlaştırma:** bekleme `ping -n 2` ile (`timeout` gizli konsolda hata verip beklemesiz döngüye yol açar); döngü ~10 dakikayla sınırlı (eski süreç kapanmazsa yine de yeni sürüm başlatılır); devir betiği kurulamazsa program asılı kalmaz, uyarı verip yeni sürümün yolunu gösterir.
- **Kanıt:** taklitsiz gerçek devir testi iki ortamda (Git Bash PATH'i ve uygulamanın sade Windows PATH'i): eski süreç yaşarken yeni sürüm açılmıyor, süreç bitince açılıyor, betik kendini siliyor. Kalıcı regresyon: `tests/test_swap_live.py` + `test_updater.SwapScriptTests`. Testler: 102 passed, 1 skipped. Donmuş paket açılışı: motor yükleniyor, log temiz.
- **Yayın:** ZIP 566.041.124 bayt, SHA256 `e378e1e2…5edc2fd95`; commit `68fef33`; `v0.5.4` etiketi bu commit'e taşındı; iki repoda asset `--clobber` ile yenilendi.
- **Şerh:** Bu düzeltme, güncellemeyi *başlatan* tarafta çalışır. Kullanıcının kurulu 0.5.3'ü eski kodu taşıdığı için 0.5.3'ten yapılan güncellemede yeniden başlatma yine takılır; bundan sonraki güncellemeler (düzeltilmiş 0.5.4 → sonraki) sorunsuz yeniden başlar.
- **Kullanıcı makinesi (2026-10-19 05:50-05:53):** `Downloads\Programs\VoxoraStudio-0.5.4` yarım kalan hatalı kopya silinip düzeltilmiş ZIP'ten yeniden kuruldu; açılışta doğrulandı (Chatterbox/cpu, log temiz, pencere açılıyor). Eski `VoxoraStudio-0.5.3` klasörü artık yok (yarım kurulumun temizlik fişi/elle silme), bu yüzden ayar devri yapılamadı; ayarlar geliştirme deposundan (`state/settings.json`: tema dark, hazır ayar "Referans sese sadık", dil en, çıktı `Downloads\Music`, referans ses `D:/Render-Handbrake/Ses Örneği.wav`) geri yüklendi.
- **Canlı E2E (yayınlanan asset):** indirme 539,8 MB → SHA256 → çıkarma (8522 dosya) → temizlik fişi → ayar devri → devir betiği → **yeni sürüm açıldı** (log: EmaEngine, ardından "Güncelleme sonrası eski sürüm temizliği": eski klasör silindi) → betik kendini sildi. Toplam 54 sn.

## v0.5.5 — Çıktı biçimi ve kalite seçimi (2026-10-19, yayınlandı)
- Kullanıcı isteği: "kalite, yüksek kalite güzel seçilebilir olsun; MP3, WAV ya da OPUS olmasını seçebilelim". Üç maket (HTML, offscreen önizleme) sunuldu; kullanıcı **Maket 2**'yi seçti: üç biçim kutucuğu + biçime göre değişen kalite kutusu.
- `config.py`: `OUTPUT_FORMAT_WAV/MP3/OPUS`, `VALID_OUTPUT_FORMATS`, `DEFAULT_OUTPUT_FORMAT="mp3"`, `DEFAULT_MP3_BITRATE="320k"`, `DEFAULT_OPUS_BITRATE="64k"`, `OUTPUT_FORMAT_EXTENSIONS`.
- `app/constants.py`: `OUTPUT_FORMAT_OPTIONS` (ad + kısa açıklama), `OUTPUT_QUALITY_OPTIONS` (MP3 128/192/320 · OPUS 32/64/96 · WAV kayıpsız), `OUTPUT_FORMAT_HELP`, `quality_options_for()`, `format_label()`.
- `app/widgets.py`: yeni **`FormatTile`** (nokta + ad + açıklama, `selected` dinamik özelliği, tıklama + boşluk/Enter); `app/theme.py`: `#formatTile` QSS (koyu/açık tema; seçilide vurgu çerçevesi + dolu nokta).
- `app/main_window.py`: Ayarlar ▸ Çıktı ▸ Kayıt ve Kalite kartında kutucuk satırı + kalite combo + yardım/not satırı; `_refresh_format_tiles`, `_refresh_quality_options`, `_on_output_format_selected`, `_on_output_quality_changed`; ayar anahtarları `output_format` + `mp3_bitrate` (eski anahtar korundu) + `opus_bitrate`; geçmişten geri yükleme ve sıfırlama bu anahtarları taşır; dosya seçicileri `.opus` kabul eder.
- Otomatik kayıt: `_auto_save_generated_wav` → **`_auto_save_generated_audio`** (seçilen biçimde yazar); `_export_compressed()` elle "MP3 olarak kaydet" ile otomatik kaydın ortak yolu; ffmpeg yok/hatalıysa dosya aynı adla WAV yazılır + durum çubuğuna not düşülür (üretim kaybolmaz).
- Testler: `tests/test_output_format.py` (16 test) — tablo tutarlılığı, varsayılanlar, kutucuk/kalite davranışı, biçim başına kalite hatırlama, ayar kalıcılığı/geri yükleme/sıfırlama, geçmişten geri yükleme, **gerçek ffmpeg** ile wav/mp3/opus çıktısı + codec/bitrate ölçümü + mp3<wav boyut + ffmpeg hatasında WAV düşüşü. Paket geneli **118 passed + 1 skipped**; smoke light "TÜM KONTROLLER BAŞARILI".
- Görsel doğrulama: gerçek pencerede koyu (MP3/320) ve açık (OPUS/96) tema kart grab'ı + sayısal yerleşim denetimi (taşma/kırpılma/elide yok); mockup + kanıt görselleri `AppData/Local/hermes/cache/scratch/voxora-055-kanitlar/`.
- Paket: `build.bat` → `dist\VoxoraStudio-0.5.5\` + `.bat` + `.zip` (**7164 girdi, 539,8 MB / 566.049.050 bayt**); ZIP tek kök, iç içe sürüm klasörü yok, kullanıcı verisi sızıntısı yok, `testzip` temiz, mutlak/sürücülü yol yok.
- Donmuş paket kanıtı (izole klasör, paketin KENDİ EXE'si): Chatterbox/TorchEngine (cpu) temiz açılış; `engine=ema` ile "Aktif motor: EMA Lightning / EmaEngine (cihaz=cpu)"; **gerçek üretim**: `_internal\outputs\…mp3` (154.604 bayt, ffprobe codec **mp3**, ~325 kbps, 3,8 sn) + arşiv kaydı + log temiz; gömülü `ema_lightning` 10/10, `normalizer_tr` 4/4.
- ⚠ İki tuzak (sonraki doğrulamalar için): (1) donmuş pakette state yolu `_internal\state\` — ayar dosyası oraya yazılmalı (yanlış yola yazılınca motor değişmiyor); (2) paketli GUI'de düz tıklama + SendKeys metni editöre ulaştırmıyor — **UI Automation ile `ControlType.Edit/Document` öğesine `SetFocus()` + SendKeys** yöntemi çalışıyor.
- Paket içi kod kanıtı (arşiv denetimi): `dist\VoxoraStudio-0.5.5\VoxoraStudio-0.5.5.exe` → `CArchiveReader` → `PYZ.pyz` çıkarıldı (93,4 MB) → `app.constants` (yeni yardım metni + `OUTPUT_FORMAT_OPUS`), `app.theme` (`#formatTile` QSS blokları), `app.main_window` ("Çıktı biçimi", `opus_bitrate`, `*.opus` filtresi, yeni otomatik kayıt docstring'i) ve `config` (`OUTPUT_FORMAT_OPUS`, `DEFAULT_OPUS_BITRATE`) modüllerinde yeni kod sabitleri bulundu; `app.version` "0.5.5" taşıyor.
- Sürüm kaydı: `app/version.py` + `tests/test_voxora_contracts.py` + README'ler 0.5.5'e senkron; `gitlog.txt` v0.5.5 bloğu eklendi. Commit `0ceaa67`, etiket `v0.5.5` (main'e push edildi).
- Release: her iki repo `v0.5.5` (ZIP asset) — SHA256 `d53176be…778c`; yerel/ana repo/ayna repo/canlı `releases/latest` digest'i birebir aynı; canlı kanal 0.5.4 → 0.5.5 teklif ediyor.
- **Canlı E2E (yayınlanan asset):** indirme 539,8 MB (canlı hız göstergesi) → SHA256 (GitHub digest) → çıkarma (8522 dosya) → temizlik fişi → ayar devri → devir betiği → yeni sürüm açıldı (EMA motoru) → "Güncelleme sonrası eski sürüm temizliği: eski klasör silindi" → betik kendini sildi. Toplam 52,2 sn.
- **Kullanıcı geçişi (07:12-07:13, uygulama içinden):** `Downloads\Programs\VoxoraStudio-0.5.5` kuruldu, eski `VoxoraStudio-0.5.4` klasörü silindi (07:13:08'de kilit uyarısı düşmüş ama klasör sonradan gitti; `_internal/state/update_cleanup.json` fişi duruyor — hedefi artık yok, sonraki açılışta zararsız kapanır). Ayarlar taşındı (engine ema, preset Anlatıcı); kullanıcı yeni karttan **OPUS · Yüksek kalite (96 kbps)** seçti. Yeni sürüm logu temiz, EMA motoru yüklendi.
- **Donmuş pakette OPUS doğrulaması (kullanıcının seçimiyle):** `output_format=opus`, `opus_bitrate=96k` ile gerçek üretim → `…opus` **38.201 bayt**, ffprobe **codec opus**, ~80 kbps, 3,8 sn (aynı cümle MP3 320 kbps'te 154.604 bayt idi → ~4 kat küçük). Log temiz, arşiv kaydı düştü.

## v0.7.0 — Motor paketi mimarisi (2026-10-23, yayınlandı)

**Karar (kullanıcı):** Setup içine yalnız EMA gömülsün; Chatterbox ve VoxCPM2
isteyen indirsin. VoxCPM2 CUDA yoksa hiç seçilemesin/indirilemesin.

### Yapı

| Motor | Boyut | Diller | Nereden |
|---|---|---|---|
| EMA Lightning | 44 MB | Türkçe | Paketle gelir |
| Chatterbox | 3,5 GB | 16 | Modeller ▸ İndir |
| VoxCPM2 | 5,2 GB | 30 + ses tasarımı | Modeller ▸ İndir (yalnız CUDA) |

- `app/hardware.py` — `nvidia-smi` ile CUDA, GPU adı/VRAM, RAM, iş parçacığı,
  boş disk. Şüphede "yok" tarafına düşer (yanlış pozitif 5 GB indirtip eli boş
  bırakır). Bu makinede: `cuda=False`, AMD RX 6650 XT, 31,1 GB RAM, 16 iş parçacığı.
- `app/engines.py` — motor kaydı: diller, klonlama, ses tasarımı, örnekleme,
  hız yöntemi, boyut, lisans, donanım koşulu. Arayüzdeki `if engine == "ema"`
  dalları kalktı.
- `app/model_manager.py`, `app/engine_pack.py` (.vxp), `app/downloader.py`,
  `app/ema_onnx.py`, `app/voxcpm_engine.py`, `app/first_run.py`.
- Modeller sekmesi (5. üst nav) + ilk açılış sihirbazı + ses tasarımı alanı.

### EMA ONNX'e taşındı

| | PyTorch | ONNX |
|---|---|---|
| Yükleme | 0,25 sn | 1,18 sn |
| Sentez (3,1 sn ses) | 0,39 sn | 0,09 sn |
| RTF | 0,14 | **0,031** |

DirectML ölçüldü ve **reddedildi**: AMD GPU'da RTF 0,39 — CPU'dan 15 kat yavaş.
Paketten 365 MB torch çıktı.

### Boyut

| | 0.6.1 | 0.7.0 |
|---|---|---|
| Paket | 1255 MB / 7163 dosya | **546 MB / 1558 dosya** |
| Setup | 364 MB | **180 MB** |
| Delta | 89 MB | **48 MB** |

### Gerçek hatalar (hepsi yakalandı ve düzeltildi)

1. `package_root()` `sys.executable.parent` döndürüyordu; `--add-data` dosyaları
   `_internal/` altına düşer. Paket EMA ağırlıklarını bulamayıp HF'den indirmeye
   çalışıyordu → `sys._MEIPASS`. Regresyon: `tests/test_paths.py`.
2. İlk açılış sihirbazı modal `exec()` ile ana olay döngüsünü kilitliyordu
   (test 90 sn timeout) → `show()` + `setModal(False)`.
3. `.vxp` payload köke açılıyordu, `installed_version` site-packages arıyordu.
4. Hash uyuşmazlığında `.part` kalıyordu → silinip temiz yeniden deneme.
5. `expected_size=0` iken indirme hiç başlamıyordu.
6. `build.bat` hedef klasör varken iç içe açıyordu (`dist/X/VoxoraStudio/`);
   bozuk 0.6.1 klasörü ve deltası bu yüzden üretilmişti → silindi, hedef önce
   siliniyor + `assert`.

### Doğrulama

- **302 test geçti**, smoke test TÜM KONTROLLER BAŞARILI.
- Paketin kendi EXE'si açıldı: **sıfır ağ isteği**, `EMA Lightning hazır
  (ONNX, CPU)`, `Aktif motor: EMA Lightning (cpu)`, kullanıcı klasörüne model
  indirmedi.
- Paket ağırlıklarından gerçek sentez: 3,32 sn ses @ 48 kHz, RTF 0,048.
- Motor paketi E2E: `ema-1.1.2.vxp` 30,4 MB üret → doğrula → kur → sentez
  (RTF 0,051) → kaldır. Chatterbox paketi: 22033 dosya, 285 MB, kurulum sonrası
  `chatterbox.mtl_tts` **kurulu paketten** import edildi.
- HF indirici gerçek ağda: 17,3 MB indi, SHA-256 doğrulandı, tekrar indirmede
  ağa çıkmadı.
- Release SHA256 `aa6e22ec…` = yerel build = ana repo = ayna repo = canlı latest.

### Ölü kod

`OnnxEngine` (SYNTHESIS_READY=False), `scripts/export_onnx.py`, 9 adet
`VoxoraStudio-*.spec`, `make_update_package`/`make_versioned_launcher` .pyc,
`tmp-wordarc-*.png`, `test_onnx_engine.py`.

### Not: indirilebilir motor paketleri henüz yayınlanmadı

`assets/engine_packs.json` pinleri hazır ama `.vxp` dosyaları ve `engines-v1`
etiketi GitHub'a yüklenmedi. Bu yüzden Modeller sekmesinde Chatterbox/VoxCPM2
"Henüz yayınlanmadı" gösterir; indirme düğmesi kapalıdır. Yayınlamak için:
motor kütüphanelerini `engine_pack.build_pack` ile paketle, `engines-v1`
etiketiyle `VoxoraStudio-Releases`'a yükle, `engine_packs.json`'a size+sha256 yaz.

## v0.7.1 — Delta boş klasör düzeltmesi (2026-10-23, yayınlandı)

Hata: delta `removed` listesi 5610 dosyayı silince boş kalan 354 klasör
(torch artığı, 544 KB) kurulumda kalıyordu. Hem `apply_staged` hem üretim
PowerShell işçisi etkileniyordu. Çözüm: post-order özyinelemeli klasör
temizliği; dosya içeren klasöre dokunulmaz. Regresyon:
`tests/test_delta_cleanup.py`.

### Yayın

- Setup 180 MB, sha256 `b007459e…`; delta'lar: 0.7.0 tabanlı **17 MB**,
  0.6.0 ve 0.5.5 tabanlı 48 MB. 0.5.4 tabanlı delta bilinçli üretilmedi
  (`MAX_BASES=3`); updater tam taban eşleşmesi arar, 0.5.4'ten gelen tam
  setup indirir (güvenli).
- Yerel SHA = ana repo = ayna repo = canlı `latest` doğrulandı.
- Not: `delta-0.7.0.vxd` ilk yüklemede iki kez üretilen dosyadan gitti
  (ZIP zaman damgası farkı); ana repo `--clobber` ile yerel dosyayla
  eşitlendi (`048931b1…`).

### Doğrulama

- 304 test, smoke TÜM KONTROLLER BAŞARILI.
- Paketin kendi EXE'si: 0 ağ isteği, EMA paketten yüklendi, kullanıcı
  klasörüne model indirilmedi.
- Paket ağırlıklarıyla sentez: RTF 0,033 (3,32 sn ses @ 48 kHz).
- 0.7.0 → 0.7.1 delta E2E (izole kopya): 1558 dosya birebir, klasör farkı 0.
- 0.6.1 → 0.7.0 E2E (üç yol: marker kipi, üretim PS işçisi, yükseltilmiş
  `_runas`): 1558 dosya birebir, torch 0 dosya/0 klasör.

## Canlı delta E2E (2026-10-23, tamamlandı)

Kurulu 0.6.1 kopyasından taban türetildi (`scripts/delta_gercek_testi.py`
0.7.0'a güncellendi, taban sürümü parametre oldu). `0.6.1 → 0.7.0` deltası
üretildi: 48 MB, 7 dosya yazılır, 5610 dosya silinir (torch, transformers,
diffusers gider). Delta yayına eklenmedi — 0.6.1'den gelecek kullanıcı yok.

**Gerçek hata bulundu ve düzeltildi:** delta `removed` listesi yalnız dosyaları
siliyordu; boş kalan klasörleri bırakıyordu. 0.6.1→0.7.0 geçişinde 354 boş
klasör (torch vb., 544 KB) kurulumda kalıyordu. İki ayrı bug:

1. `app/delta.py` `apply_staged` ve `app/updater.py` PowerShell işçisi: silinen
   dosyaların üst klasörlerini hiç temizlemiyordu.
2. İlk düzeltmedeki yukarı doğru tarama iki nedenle yarım kalıyordu: dolu
   görünen klasör `seen`e girip bir daha denenmiyordu; iç içe boş klasörler
   taşıyan klasör "dolu" sanılıyordu.

**Çözüm:** post-order (önce en derin) özyinelemeli silme, `removed`
listesindeki dosyaların üst klasörlerine uygulanır; dosya içeren klasöre
dokunulmaz. Hem Python yolu (`apply_staged`) hem üretim PowerShell işçisi
(`delta_worker_ps1`) aynı mantığı taşır. Regresyon:
`tests/test_delta_cleanup.py`.

**E2E sonuçları (izole 0.6.1 kopyası):**

- marker kipi: rc=0, 1558 dosya birebir eşleşti, torch 0 dosya/0 klasör kaldı
- üretim PowerShell işçisi: rc=0, 3,6 sn, 1558 dosya birebir, torch tam silindi
- klasör karşılaştırması (0.7.0 paketiyle): fark 0

UAC doğrulandı: Program Files'e yazarken işçi yükseltme ister (beklenen);
kullanıcı alanındaki hedefte yükseltme gerekmez.

## Sırada

- VoxCPM2'yi CUDA'lı makinede gerçek sentezle sına; sonra paketi üret, pini
  doldur, `engines-v1`'e yükle, Setup'ı yeniden derle ve asset'leri değiştir.
- Ardından: Serbest Defter blog yazılarını EMA ile sese çevirme akışı.

## v0.6.1 — Güncelleme kurulumu çökmesi düzeltmesi (2026-10-22, yayınlandı)
- **Hata (0.6.0 yayınında canlı):** `main_window._on_update_installed`, v0.5.x'ten kalma `updater.spawn_swap` çağrısını taşıyordu; simge 0.6.0'da silindi. Qt, slot içindeki yakalanmayan istisnada süreci düşürür (testle kanıtlı: exit 127) → "İndir ve Kur" indirme biter bitmez program sessizce kapanır, kurulum başlamaz.
- **Düzeltme:** `_launch_update_installer` → `updater.spawn_installer(Path(launcher))`; kurulum hatasında (`UpdateError`/`OSError`) program açık kalır + dosya yolu gösterilir. Ölü `phase=="extract"` dalı silindi. Regresyon: `tests/test_update_install_ui.py` (3 test; ölü simge taraması dahil). Kapılar: **182 passed, 1 skipped** + smoke BAŞARILI.
- **Build:** `build_temp` içindeki eski `localpycs` klasörü silinemeyince (Defender/Scheduled Clenaup kilidi, `WinError 5`) `build_temp_stale_061` olarak kenara alındı, build temiz dizinde tamamlandı. Paket 7163 dosya, veri sızması yok; Setup **382.125.160 bayt** SHA256 `d8eb46c4…83f12c3b`; delta 0.6.0 `61b9489e…`, 0.5.5 `e42f938f…`, 0.5.4 `dc1a2a64…` (üçü de 2 değişen dosya, testzip temiz).
- **Donmuş paket kanıtı:** PYZ arşivinde `app.main_window` → `spawn_installer` var, `spawn_swap` yok; `app.version` = 0.6.1. **Gerçek üretim:** izole pakette EMA hazır, UIA ile cümle gönderildi, MP3 147.884 bayt / 3,64 sn / codec mp3 / ~325 kbps; çıktı+arşiv `%LOCALAPPDATA%`, program klasörüne sızma YOK, log TEMİZ. Test artığı mp3 Geri Dönüşüm'den silindi, geçmişi temizlendi, ayarlar yedekten (`settings.json.yedek-061`) geri yüklendi.
- **Commit `7c49b03` · tag `v0.6.1` · main push** · iki repoda Release (Setup + 3 delta).
- **Yayın doğrulaması:** dört asset de `uploaded`; yerel SHA-256 = ana repo = ayna repo = canlı `latest` (Setup `d8eb46c4…`, delta-0.6.0 `61b9489e…`, delta-0.5.5 `e42f938f…`, delta-0.5.4 `dc1a2a64…`).
- **Canlı istemci seçimi (gerçek API):** 0.5.4 → delta-0.5.4, 0.5.5 → delta-0.5.5, 0.6.0 → delta-0.6.0, 0.6.1 → "güncel". Yayınlanan delta-0.6.0 gerçek HTTP ile indirildi (93.679.729 bayt), SHA-256 tuttu, `can_apply(0.6.0)` doğru, stage 2 dosyayı çıkardı — kurulu kopyaya dokunulmadan geçici hedefte.
- **Bu makine (kurulu 0.6.0 kendi kendini güncelleyemediği için elle setup):** sessiz kurulum tamam, `{app}` EXE + `base_library.zip` 0.6.1 paketiyle bayt bayt aynı, kaldırma kaydı `DisplayVersion=0.6.1`, program Restart Manager sonrası kendiliğinden açıldı (log: EmaEngine/cpu, temiz). `build_temp_stale_061` silindi; Program Files'taki eski test artıkları (`testcopy.exe`, `VoxoraStudio.exe.old`, `_delta_result.json`) duruyor — silme yetkisi verilmedi.
- **İlk canlı delta sınaması** artık 0.6.1 → 0.6.2'de kullanıcı akışında görülecek (istemci 0.6.1 tabanına karşı delta üretilince).

## v0.6.0 kurulum denetimi + güncelleme çökmesi düzeltmesi (2026-10-22)
- **Kullanıcı isteği:** "setupolu yapıya çevirmiştik, hatalar almıştım, doğru olduğundan emin değilim" → uçtan uca yeniden denetim.
- **Kritik bulgu (canlı hatadır, yayındaki paketlerde duruyor):** `app/main_window.py` `_on_update_installed`, v0.5.x'ten kalma `updater.spawn_swap(...)` çağrısını taşıyordu; `spawn_swap` v0.6.0'da kaldırıldı. Çağrı Qt sinyali içinde → Qt, slot'taki yakalanmayan istisnada **süreci düşürüyor** (baştaki `sys.excepthook` devreye girmez; bu ayrı bir testle doğrulandı: exit 127, çıkış mesajı yok). Yani kurulu 0.6.0, ileride "İndir ve Kur" derse indirme biter bitmez sessizce kapanacaktı; kurulum hiç başlamayacaktı.
- **Neden testler görmedi:** tek çağrı yolu GUI'deki "İndir ve Kur" düğmesiydi; `tests/test_updater.py` `spawn_installer`'ı doğrudan test ediyor, sinyal bağlantısını hiç test etmiyordu. 179 testin hepsi geçiyordu.
- **Düzeltme:** `_launch_update_installer` — `updater.spawn_installer(Path(launcher))` çağrılır (sessiz kurulum + yeniden açma bekçisi), kapanış akışı aynı kalır. Kurulum başlatılamazsa (`UpdateError`/`OSError`) uygulama **açık kalır**, hata kutusu + indirilen dosyanın yolu gösterilir. Ölü `phase == "extract"` dalı kaldırıldı (hiçbir yer `extract` yayınlamıyor).
- **Yeni regresyon:** `tests/test_update_install_ui.py` 3 test — (1) `installed` sinyali `spawn_installer`'ı çağırır + kapanış başlar, (2) kurulum hatasında uygulama kapanmaz, (3) statik tarama: kaldırılmış updater simgelerinin (`spawn_swap`, `swap_script_text`, `stale_package_dirs`, `write_cleanup_marker`, `cleanup_pending`, `cleanup_after_update`) `app/` altında çağrısı kalmadığını denetler. Paket geneli **182 passed, 1 skipped**; smoke `TÜM KONTROLLER BAŞARILI`.
- **Doğrulanan şeyler (sağlam):** yerel Setup/delta SHA-256 = ana repo digest = ayna repo digest = canlı `releases/latest`; kurulu `C:\Program Files\VoxoraStudio` 7163 dosyası `dist/VoxoraStudio-0.6.0` ile **bayt bayt aynı** (0 fark), EXE + `base_library.zip` özdeş; `main_window.py`/`updater.py` mtimes (02:00/02:01) build'den (02:08) önce → build bayat değil; `_internal` altında `state/logs/outputs/.update` yok; kurulu log temiz (0 Traceback/ERROR); ayarlar/çıktılar `%LOCALAPPDATA%\VoxoraStudio` altında; README sürüm satırları 0.6.0.
- **Kalan / karar bekliyor:** yayındaki `VoxoraStudio-0.6.0-Setup.exe` ve iki delta bu hatayı içeriyor → düzeltme ancak **0.6.1 build + yayın** ile kullanıcıya ulaşır (yalnız GUI'den "İndir ve Kur" akışını ilgilendirir; silip elle kurulum yapan kullanıcı etkilenmez). Delta yalnız tam eşleşen taban sürümde seçildiği için 0.6.1 delta'ları 0.6.0 tabanına karşı üretilecek.
- **Koskocan artıklar (Program Files, kod tarafından üretilmiyor, silmek yönetici izni ister):** `testcopy.exe` (93,8 MB, 0.5.5 EXE kopyası, 19 Eki), `VoxoraStudio.exe.old` (93,8 MB, delta işçisinin `.old` artığı), `_delta_result.json` (başarısız delta denemesinin kaydı — `Temp\voxora-delta-*` silinince manifest'i bulamadı; zararsız). Birlikte ~187 MB.
- **Not:** `0.5.x` kurulumları bundan etkilenmez — kendi `spawn_swap`'ları yerinde ve 0.6.0'ı ZIP'siz göremezler; ilk geçiş yine elle Setup ile.

## v0.6.0 — Yayın (2026-10-22)
- **Commit:** `f5484ab` · **Tag:** `v0.6.0` · `main` push edildi.
- **Yayın:** iki repoda `v0.6.0` Release — `VoxoraStudio-0.6.0-Setup.exe` (382.116.684 bayt), `VoxoraStudio-0.6.0-delta-0.5.5.vxd` + `-delta-0.5.4.vxd` (93.679.707 bayt). Üç asset de `uploaded`.
- **Digest doğrulaması:** yerel = ana repo = ayna repo = canlı `latest`. Setup `sha256:5b5f7bb4…`, delta `sha256:32000d4b…`.
- **İstemci seçimi (canlı API ile):** 0.5.5 → delta (0.5.5 taban), 0.5.4 → delta (0.5.4 taban), 0.5.3 → tam setup, 0.6.0 → güncel.
- **Canlı indirme E2E:** delta gerçek HTTP ile indirildi — 93.679.707 bayt, SHA-256 birebir eşleşti.
- **Kurulum + üretim:** Program Files'a sessiz kurulum `exit=0`, kurulu EXE build ile aynı, gerçek MP3 3,64 sn / 320 kbps / codec mp3, çıktı `%LOCALAPPDATA%\VoxoraStudio\outputs`, program klasöründe kullanıcı verisi yok, **log temiz**.
- **Delta E2E (kurulu kopya):** 0.5.5'e çevrilmiş kurulumda fiş → PowerShell işçisi → **7163 dosya, uyuşmayan 0**.
- **Yedek öncesi yakalanan iki gerçek hata:** (1) `main_window._run_update_cleanup` silinmiş `cleanup_after_update`'i çağırıyordu — her açılışta log'a `AttributeError` yazıyordu; `run_cleanup_async`'e bağlandı. (2) `app/updater.py` içinde yedi fonksiyon (`cleanup_updates_dir`, `run_cleanup_async`, `last_check_is_old`, `now_stamp`, `apply_delta`, `write_delta_marker`, `run_pending_delta`, `apply_delta_marker`, `_apply_marker_payload`) ikiz tanımlıydı; eski kopya bloğu (53+ satır) silindi. Ders: **build'den sonra kaynak değişirse build bayatlar** — mtime karşılaştırması yapılmadan yedek kapanışına girilmez.
- **Kapılar:** `179 passed, 1 skipped`; smoke `TÜM KONTROLLER BAŞARILI`.

## v0.6.0 — Kurulum dosyası, yerinde güncelleme ve delta (2026-10-21)
- **Karar (kullanıcı):** Program Files (tüm kullanıcılar, yönetici izni), ayrı Models setup'ı, önce tam setup sonra delta, masaüstü + Başlat Menüsü kısayolları seçilebilir, kullanıcı verisi `%LOCALAPPDATA%\VoxoraStudio`.
- **Yapı:** `app/paths.py` tek yetkili yol kaynağı. Donmuş pakette program kökü `{app}`, veri kökü `%LOCALAPPDATA%\VoxoraStudio`; kaynak kopyada ikisi de depo kökü (testler ve `python app.py` değişmedi). `app_state.py`, `logging_config.py`, `main_window._default_output_dir` buradan besleniyor.
- **EXE adı sabitlendi:** `VoxoraStudio.exe` (sürümsüz). `branding.EXECUTABLE_NAME` değişti; sürümlü ad kısayolları her sürümde kırıyordu.
- **Güncelleme yeniden yazıldı:** `app/updater.py` artık Setup.exe arar/indirir/doğrular ve `spawn_installer` ile sessiz kurar. `extract`, `stale_package_dirs`, `write_cleanup_marker`, `cleanup_pending`, `swap_script_text`, `spawn_swap` kaldırıldı. `workers.UpdateWorker._install` yalnız indirir; kurulumu GUI kapanış akışı başlatır.
- **Kurulum betiği:** `installer/VoxoraStudio.iss`. Sabit klasör, `CloseApplications=yes` + `RestartApplications=yes`, `[InstallDelete]` ile temiz kurulum davranışı, kaldırmada veri/model korunur ve yeri söylenir.
- **build.bat:** 5 adım; PyInstaller `VoxoraStudio.exe` üretir, `dist\VoxoraStudio-X.Y.Z\`e taşınır (Python `shutil.move`; `move /y` Defender yüzünden "Erişim engellendi" veriyordu), ISCC ile Setup derlenir, SHA-256 basılır. `make_update_package.py` ve `make_versioned_launcher.py` silindi.
- **Ölçüm:** paket 1255 MB / 7163 dosya; Setup **382 MB** (eski ZIP 540 MB). 0.5.4 → 0.5.5 farkı: 3 dosya (EXE 89,5 MB + base_library.zip 1,4 MB + BAT), 7161 dosya aynı.
- **Eski kurulum devri:** `paths.migrate_legacy_state` ilk açılışta `Downloads\Programs\VoxoraStudio-X.Y.Z\_internal\state` ayar/geçmişini kopyalar, `_internal` sarmalayıcısını atarak yolları veri köküne çevirir, işaret dosyası yazar (bir kez). Eski klasör silinmez.
- **Gerçek doğrulama (hepsi bu makinede):**
  - Kurulum: sessiz kurulum `exit=0`, kısayollar oluştu (masaüstü OneDrive'da), kaldırma kaydı yazıldı.
  - Kurulu EXE ile üretim: EMA motoru yüklendi, UIA ile metin yazıldı, **gerçek MP3** 147.884 bayt / 3,63 sn / 320 kbps / codec mp3. Çıktı ve arşiv `%LOCALAPPDATA%\VoxoraStudio` altında; program klasöründe `settings.json`/`history.json`/log **yok**.
  - Güncelleme: aynı setup üzerine kuruldu, eski sürümlü EXE silindi, `unins000` korundu, ayarlar/çıktılar/modeller durdu.
  - Kaldırma: program klasörü boşaldı (yalnız test artıkları), ayarlar + MP3 + 4,4 GB model cache korundu.
  - Testler: `127 passed, 1 skipped`; smoke light `TÜM KONTROLLER BAŞARILI`.
- **Düzeltilen iki gerçek hata:** (1) `{userprofile}` Inno sabiti değil — `{%USERPROFILE}`; boş `InitializeSetup` kaldırıldı. (2) Devralınan `output_dir` `_internal\outputs` oluyordu; `_internal` öneki atılıyor + regresyon testi eklendi.

### Delta güncelleme (2. faz)
- **Ölçüm:** 0.5.5 → 0.6.0 için 7163 dosyanın yalnız **2'si** değişti (`VoxoraStudio.exe` 89,5 MB + `_internal/base_library.zip` 1,4 MB), 1 dosya silindi. Delta **89,3 MB** — tam setup 364 MB'tan 4 kat küçük.
- **Paket biçimi** (`.vxd`, aslında ZIP): `manifest.json` (version, base_version, files[path/sha256/size], removed, total_bytes) + `files/<göreli yol>`. Üretici `scripts/make_delta_package.py`; build sonunda `scripts/make_delta_candidates.py` dist'teki son 3 sürüme karşı delta üretir (`VoxoraStudio-<hedef>-delta-<taban>.vxd`).
- **İstemci seçimi:** `updater.parse_release(current_version=...)` yalnız taban sürümü **tam eşleşen** delta'yı seçer (`DELTA_RE`). Eşleşme yoksa tam setup iner. Yanlış taban = bozuk kurulum riski, bu yüzden katı.
- **Kritik tasarım kararı — delta kapanışta uygulanır, çalışırken değil:** Çalışan Python süreci `_internal\base_library.zip`'i kilitler; Windows kilitli dosyayı ne silmeye ne yeniden adlandırmaya izin verir (`WinError 32`). Delta bu dosyayı güncellediği için uygulamanın kendi EXE'siyle uygulanamaz (bootstrap sorunu). Akış: `apply_delta` yalnız **doğrular + geçici klasöre çıkarır + `state/pending_delta.json` fişini yazar** → uygulama kapanır → Python çalıştırmayan PowerShell işçisi (`run_pending_delta`) dosyaları yükseltilmiş olarak kopyalar, SHA-256 doğrular, fişi/staged'i siler, programı normal kullanıcı olarak açar. Tek UAC onayı.
- **İşçi betiği:** `delta_worker_ps1` (kopyalama+doğrulama) ve `delta_worker_bat` (`Start-Process ... -Verb RunAs`). Sonuç JSON **BOM'suz UTF-8** yazılmalı (`[System.IO.File]::WriteAllText` + `UTF8Encoding($false)`); `Set-Content -Encoding UTF8` BOM ekliyor ve Python `json.loads` patlıyordu. Sonuç dosyası staged klasörünün içindeyse staged silinmez.
- **Güvenlik kapıları:** her dosya SHA-256 doğrulanır (hem `stage()` hem işçi); doğrulanmamış delta program klasörüne hiç ulaşmaz. Yol kaçışı `resolve()` + `root in target.parents` ile engellenir — `relative_to` tek başına yetmiyordu (`a/b/../evil` kaçışı gizliyor), gerçek testte yakalandı.
- **Gerçek doğrulama (uçtan uca, kurulu kopya):** 0.5.5'e çevrilmiş `C:\Program Files\VoxoraStudio` üzerinde `apply_delta` fiş yazdı (hedefe dokunmadı) → PowerShell işçisi yükseltilmiş çalıştı → **7163 dosya 0.6.0 ile birebir aynı (0 uyuşmayan)**. Kurulu program sonrasında gerçek MP3 üretti (3,64 sn, MP3, çıktı `%LOCALAPPDATA%\VoxoraStudio\outputs`).
- **Test:** `tests/test_delta.py` 25 test (compare, manifest, stage/apply, rename-sonra-taşı, taşıma hatasında geri alma, fiş yazımı, yanlış taban reddi, işçi bekleyişi/RunAs/hash/BOM), `tests/test_updater.py` 36; tam paket `179 passed, 1 skipped`.
- **Bilinen sınır:** delta yalnız tam eşleşen taban sürümde kullanılır; taban uyuşmazsa istemci tam setup'a düşer. İlk canlı delta 0.6.0 → 0.6.1 yayınında sınanacak.

## Bağımlılık (2026-09-26)
- Değişiklik yok: starlette 0.52.1 + transformers 5.2.0 açıkları majör geçiş ister (gradio/fastapi/chatterbox uyumu, ayrı iş). torch 2.6.0 pini bilinçli. 58 test geçti, 1 atlandı (taban).
