# Voxora Studio — İnceleme, Hata Düzeltme, Temizlik, Geliştirme Planı

Tarih: 2026-09-09 | Repo: `C:/Users/mahmu/Projeler/VoxoraStudio` | Branch: `main` (temiz) | Sürüm: `app/version.py` = 0.3.2

## Goal

Voxora Studio'yu 12 etap sırasıyla (incele → tespit → düzelt → doğrula → temizle → doğrula → öner) stabil, temiz, anlaşılır hale getir; her etap doğrulanmadan sonrakine geçme.

## Current context / assumptions

- Tür: PyQt6 masaüstü TTS stüdyosu, Chatterbox Multilingual V3, yerel çalışır. DB yok; durum JSON (`state/settings.json`, `state/history.json` + `.bak`).
- Giriş: `app.py::main()` → `app/main_window.py::MainWindow` (2141 satır, en büyük risk). Yardımcılar: `app/workers.py` (SynthWorker, EngineLoader, CompressWorker, TqdmProgressBridge), `app/dialogs.py` (375), `app/widgets.py` (579), `app/theme.py` (825), `app/constants.py`, `app/branding.py`, `app/icons.py`.
- Çekirdek: `tts_engine.py` (257, TorchEngine/OnnxEngine/TTSEngine, 3 katman: CUDA → ONNX/DirectML → CPU), `chunker.py` (89, `split_into_chunks`), `app_state.py` (72, atomik JSON + .bak), `file_utils.py` (57), `audio_player.py` (85, sounddevice), `audio_compressor.py` (196, pydub+ffmpeg), `config.py` (19), `logging_config.py` (21).
- Scriptler: `scripts/setup_env.py` (267), `scripts/gpu_detect.py` (68), `scripts/export_onnx.py` (74), `scripts/make_versioned_launcher.py` (42). Testler: `tests/test_*.py` 8 dosya (~580 satır). Smoke: `smoke_test.py` (204).
- Yapılandırma: `requirements.txt` (torch==2.6.0, chatterbox-tts, PyQt6, pydub, sounddevice…), `run.bat`, `setup.bat`, `install_check.bat`, `bin/ffmpeg.exe`, `VoxoraStudio*.spec` ×4 + `txttoTTS.spec`, `docs/superpowers/`, `models/chatterbox/`, `outputs/`, `logs/`, `build_temp/`, `dist/`.
- Varsayım: Windows + Python 3.11 (`.venv` veya `.tools/python311`). `python3=3.14` bulaşmış; tüm komutlar `py -3.11` veya `.venv` ile. Ağır model indirme ilk çalışta olur; testler mock ile koşar. Kullanıcı verisi = `state/*.json`, `outputs/` — asla silinmez.
- Genel kural: etaplar karışmaz. Düzeltmede refactor yok, temizlikte davranış değişmez, mimari değişim yalnız öneri olarak raporlanır.

## Architecture / proposed approach

Önce salt-okunur haritalama + test tabanı çıkarılır (bu, sonraki tüm etapların referansı). Sonra risk sırasıyla düzelt (veri kaybı → açılış engeli → yanlış veri → çökme), her düzeltme sonrası ilgili test + smoke koşar. Temizlik yalnız kanıtlı-ölü kodda, küçük gruplarla yapılır. Mimari/güvenlik/performans incelemesi rapor üretir, kod değiştirmez (doğrulanmış küçük güvenlik açığı hariç).

## Step-by-step tasks

### ETAP 1 — Tanıma ve haritalama (değişiklik yok, silme yok)

- [ ] T1.1 Envanter çıkar (5 dk). Komutlar (salt-okunur):
  ```powershell
  cd C:\Users\mahmu\Projeler\VoxoraStudio
  git status --short --branch
  py -3.11 -m pytest --collect-only -q
  py -3.11 -m pytest -q
  ```
  Beklenen: branch `main`, testler yeşil (8 dosya, ~40-60 test). Başarısızlık varsa listele, düzeltme — Etap 2'ye yaz.
- [ ] T1.2 Dosya haritası oku (her biri 2-5 dk, sırayla): `app.py`, `config.py`, `app/version.py`, `app/branding.py`, `app/constants.py`, `chunker.py`, `file_utils.py`, `app_state.py`, `logging_config.py`, `audio_player.py`, `audio_compressor.py`, `tts_engine.py` (101-257. satırlar `OnnxEngine` + `TTSEngine` dahil), `app/workers.py` (101-210. satırlar `SynthWorker.run` + `CompressWorker`), `scripts/gpu_detect.py`, `scripts/setup_env.py`, `scripts/export_onnx.py`, `smoke_test.py`, `app/main_window.py` (tamamı — bölümler halinde: 1-200 import/sabit, 200-800 UI kurulum, 800-1400 üretim akışı, 1400-2141 geçmiş/kayıt/ayar).
- [ ] T1.3 Bağlantı şeması çıkar: `MainWindow` → `workers` → `tts_engine` → `chunker`; `MainWindow` → `app_state` (settings/history); `MainWindow` → `file_utils` + `audio_*`; `setup.bat` → `scripts/setup_env.py` → `requirements.txt`; `build.bat` → hangi `.spec`? (`VoxoraStudio-0.3.2.spec` güncel mi, eski 3 spec ölü mü — Etap 5'e aday yaz).
- [ ] T1.4 Çıktı: `docs/MIMARI-OZET.md` YOK — plan dışı dosya üretme. Etap özeti nihai raporda toplanır. Doğrulama: `git status --short` boş kalır (Etap 1'de çalışma ağacı kirlenmez).

### ETAP 2 — Hata ve risk tespiti (düzeltme yok)

- [ ] T2.1 Otomatik taban (10 dk):
  ```powershell
  py -3.11 -m pytest -q
  py -3.11 smoke_test.py
  py -3.11 -m compileall -q app app.py tts_engine.py chunker.py app_state.py file_utils.py audio_player.py audio_compressor.py
  ```
  Beklenen: pytest geçiyor, smoke `OK`, compile sessiz. Log incele: `logs/VoxoraStudio.log`, `logs/txttoTTS.log` (son 100 satırda traceback var mı?).
- [ ] T2.2 Odaklı statik tarama (ripgrep, her biri 2 dk):
  - `except.*pass` / çıplak `except:` → eksik exception handling adayı.
  - `TODO|FIXME|XXX|HACK` → bilinen borç.
  - `os.remove|shutil.rmtree|unlink` → veri kaybı riski (yalnız `file_utils.safe_remove_to_trash` üzerinden mi?).
  - `subprocess|shell=True` → enjeksiyon/yol riski (`app/main_window.py` içinde `subprocess` kullanımı).
  - `print(` → log yerine stdout kalan debug.
  - `import` listesi vs `requirements.txt` → ölü bağımlılık adayı.
- [ ] T2.3 Runtime deneme (model indirmeden): `py -3.11 app.py` açılıyor mu? Üret'e basmadan kapat. Konsol hatası varsa kaydet. (`VOXORA_SHOW_CONSOLE=1` ile.)
- [ ] T2.4 Hata haritası yaz: her kayıt `{id, şiddet KRİTİK/YÜKSEK/ORTA/DÜŞÜK, dosya:satır, neden, etki, önerilen çözüm}`. Sıralama kuralı: veri kaybı > açılış engeli > yanlış veri > çökme > UX. Örnek adaylar (doğrula, varsayma): `main_window.py` 2141 satırda UI+iş mantığı karışması; `OnnxEngine._sample_rate = 24000` tahmini sabit; eski `.spec` çokluğu; `__pycache__`, `build_temp/`, `dist/` şişkinliği.
- [ ] T2.5 Doğrulama: hata haritası eksiksiz, henüz kod değişmedi (`git status` temiz). TDD yok (test yazımı Etap 3'te, her düzeltmeyle).

### ETAP 3 — Kritik + yüksek düzeltme (refactor yok, özellik yok, tasarım yok)

Her kayıt için TDD döngüsü:
1. Başarısız mini-test yaz (`tests/test_etap3_<konu>.py` geçici — kalıcı olacaksa `tests/` altında tut).
2. `py -3.11 -m pytest tests/test_etap3_<konu>.py -q` → KIRMIZI gör.
3. Minimal düzeltme yap.
4. Aynı komut → YEŞİL. 5. `py -3.11 -m pytest -q` tam süit yeşil. 6. Commit (küçük, mesaj: `fix(etap3): <id> <dosya>`).

- [ ] T3.1 Veri kaybı adayları önce: `app_state.save_json` atomiklik + `.bak` geri yükleme (`tests/test_settings_migration.py` yoksa yaz — `load_json` bozuk dosyada `.bak`'a düşüyor mu?). `safe_remove_to_trash` boş/yok yol (`test_file_utils.py` kapsıyor mu?).
- [ ] T3.2 Açılış engeli: `app.py` import sırası, `app/main_window.py` üst seviye importta model yükleme var mı (varsa tembelleştir)? `scripts/setup_env.py` CUDA fallback gerçekten CPU'ya düşüyor mu?
- [ ] T3.3 Yanlış veri: `chunker.split_into_chunks` sayı koruması (`test_chunker.py` genişlet: "2024.", "3.14", boş metin), `estimate_duration_range` sıfır/negatif speed (`test_duration_estimate.py`), `trim_leading_silence` 500ms sınırı (`test_trim_leading_silence.py`).
- [ ] T3.4 Çökme: `SynthWorker` iptal/boş chunk, `audio_player` cihaz yokken, MP3'te ffmpeg yokken mesaj (`audio_compressor.py` + `bin/ffmpeg.exe` yolu).
- [ ] T3.5 Etap raporu: düzeltilen id'ler, değişen dosyalar, koşulan testler + sonuç. Doğrulama: tam `pytest -q` yeşil + `smoke_test.py` OK. Kalan kritik varsa Etap 4'e sarkmaz — burada biter.

### ETAP 4 — Orta + düşük düzeltme

- [ ] T4.1 Kayıt sırasıyla aynı TDD döngüsüyle düzelt: eksik validasyon mesajı, yanlış durum yönetimi, gereksiz warning, küçük tutarsızlık. Her biri 2-5 dk, tek commit.
- [ ] T4.2 Regresyon turu:
  ```powershell
  py -3.11 -m pytest -q
  py -3.11 smoke_test.py
  $env:VOXORA_SHOW_CONSOLE = "1"; py -3.11 app.py
  ```
  Beklenen: süit yeşil, smoke OK, pencere açılıyor. Etap 3 düzeltmesi bozulan yer varsa dur, düzeltmeden ilerleme.
- [ ] T4.3 Çıktı: Etap 4 raporu (düzelen/ertelenen orta-düşük listesi + gerekçe).

### ETAP 5 — Gereksiz dosya/kod analizi (SİLME YOK)

- [ ] T5.1 Aday tara (her biri ripgrep ile kanıtla, dinamik yüklemeye dikkat: `importlib`, `__import__`, `getattr`, `.spec` içi `datas`, `run.bat`/`setup.bat` referansları):
  - Dosya: `txttoTTS.spec` + `VoxoraStudio-0.3.0.spec` + `VoxoraStudio-0.3.1.spec` (yalnız `VoxoraStudio-0.3.2.spec` güncel mi? `build.bat` hangisini kullanıyor?), `gitlog.txt` (README referans veriyor — dokunma), `__pycache__/`, `build_temp/`, `dist/` (derleme çıktısı, repoda izleniyor mu? `git ls-files dist build_temp | head`), `state/*.bak`, `logs/*.log`, eski `install_check.bat` referansı (README'da var, dosya yok — ölü doküman mı?).
  - Kod: `app/main_window.py` içinde ölü fonksiyon, `theme.py`/`icons.py`/`widgets.py` ölü widget, kullanılmayan import (her dosyada `ruff`/`pyflakes` yoksa gözle: `py -3.11 -m pyflakes` varsa koş), `requirements.txt` içinde `onnxruntime-directml` yorum satırı (koşullu kurulum — dokunma).
- [ ] T5.2 Üç liste üret: (1) güvenle silinebilir, (2) muhtemelen gereksiz-doğrulama gerek, (3) dokunulmaz. Kural: %100 kanıt yoksa liste 1'e girmez. `state/*.json`, `outputs/`, `models/`, `bin/ffmpeg.exe` asla listede yok.
- [ ] T5.3 Doğrulama: liste dosyası commitlenmez; nihai raporda yer alır. Ağaç temiz (`git status` boş).

### ETAP 6 — Güvenli temizlik (küçük gruplar, her grup sonrası test)

Sıra: importlar → fonksiyon/class → yardımcı dosya → geçici dosya → asset → bağımlılık. Her grup:

```powershell
py -3.11 -m pytest -q
py -3.11 -c "import app; import app.main_window; import tts_engine; import chunker; print('import OK')"
```

- [ ] T6.1 Grup 1: ölü importlar (davranış değişmez). Test → commit.
- [ ] T6.2 Grup 2: ölü fonksiyon/class (çağrı yok kanıtlı). Test → commit.
- [ ] T6.3 Grup 3: liste-1 dosyalar (`__pycache__` asla commitle silinmez — `.gitignore`'a eklenir; `build_temp/`/`dist/` izleniyorsa ayrıca karar). Test → commit.
- [ ] T6.4 Grup 4: bağımlılık (yalnız kullanılmadığı %100 ise; `requirements.txt` + `scripts/setup_env.py` birlikte). Test + smoke → commit.
- [ ] T6.5 Çıktı: silinen dosya/kod listesi + her grup test sonucu. Davranış değiştiyse geri al (`git checkout -- <dosya>`), nedenini yaz.

### ETAP 7 — Kod kalitesi ve mimari (önce liste, otomatik büyük refactor YOK)

- [ ] T7.1 Metrik çıkar: `main_window.py` 2141 satır (bölünme adayı: üretim akışı / geçmiş / ayarlar), `theme.py` 825, `widgets.py` 579; en uzun 10 fonksiyonu bul; tekrar kodu ara (chunk/süre/filename helper'ları); magic number tara (`170/130` wpm, `0.45`, `80`, `100` geçmiş limiti, `400` chunk); hard-coded yol tara (`"outputs"`, `"logs"`, `"models"` → `config.py`'de mi?).
- [ ] T7.2 Her öneri kartı: `{problem, önerilen çözüm, fayda, risk, etkilenecek dosyalar, büyüklük S/M/L}`. Örn: MainWindow bölme (L, risk yüksek → öneri, uygulama yok); `estimate_duration_range` sabitleri `config.py`'ye (S, risk düşük).
- [ ] T7.3 Doğrulama: kod değişikliği yok, ağaç temiz. Uygulama yok — Etap 10'a girdi olur.

### ETAP 8 — Güvenlik ve veri güvenilirliği

- [ ] T8.1 Kontrol listesi: kullanıcı metni/yolu validasyonu (uzun metin, özel karakter, `safe_filename_from_text` Türkçe karakter?), yol traversal (`QFileDialog` + `unique_path` dışına yazım?), `subprocess` argümanları (liste mi, string mi?), sır/API anahtarı (`git log -p --all -S "api_key|secret|token" -- . ':!dist' ':!build_temp'`), transaction/yarım kayıt (`save_json` atomik — yeterli; history 100 limiti veri kaybı sayılmaz), trash/restore (`safe_remove_to_trash` geri alınamaz silme yapıyor mu?), logda hassas veri (metin tamamı loga yazılıyor mu?).
- [ ] T8.2 Doğrulanmış küçük açık varsa minimal düzelt (TDD ile). Büyük mimari işi → öneri olarak Etap 10'a. Çıktı: bulgu + düzeltilen listesi.

### ETAP 9 — Performans ve UX (kanıtsız optimizasyon YOK)

- [ ] T9.1 Performans: tekrar hesap (karakter/kelime/parça her tuşta mı?), tekrar DB/IO (settings/history her üretimde mi yazılıyor?), ana thread'de ağır iş (sentez `SynthWorker`'da mı, süre tahmini hafif mi?), büyük metinde chunk sayısı uyarısı (`WARN 20/CONFIRM 50` çalışıyor mu?), gereksiz disk okuma (model her üretimde mi yükleniyor?).
- [ ] T9.2 UX: gereksiz tıklama, anlaşılmaz hata (ffmpeg yok, cihaz yok, model yok mesajları Türkçe mi?), başarı geri bildirimi, uzun işte ilerleme (`SynthesisDialog` + `TqdmProgressBridge` akıyor mu?).
- [ ] T9.3 Çıktı: kanıtlı problem listesi + ölçüm yöntemi. Kod değişikliği yok (hata sayılan yer Etap 3/4'e geri beslenir).

### ETAP 10 — Geliştirme önerileri (projeye özel, genel tavsiye yok)

Üç grup, her öneri: `{ne, neden, kullanıcı faydası, teknik fayda, risk, büyüklük, etkilenen modüller, öncelik}`.
- [ ] T10.1 Hızlı kazanımlar (S): örn. `.gitignore` (`__pycache__/`, `build_temp/`, `dist/` çıktısı), eski `.spec` arşivleme, `install_check.bat` doküman ölü referansı, magic number → `config.py`, eksik boş-durum mesajları.
- [ ] T10.2 Orta (M): `main_window.py` modüler bölünme, test kapsamı (workers iptal akışı, MP3/ffmpeg yok senaryosu), log rotasyonu (`logs/` büyümesi).
- [ ] T10.3 Büyük (L): ONNX hibrit inference tamamlama (`OnnxEngine` iskelet), model yöneticisi ekranı, kuyruklu toplu üretim dayanıklılığı. Risk + öncelik açık yazılır.

### ETAP 11 — Nihai regresyon ve sağlık kontrolü

- [ ] T11.1 Tam tur (sırayla, durmadan):
  ```powershell
  py -3.11 -m pytest -q
  py -3.11 smoke_test.py
  $env:VOXORA_SHOW_CONSOLE = "1"; py -3.11 app.py
  ```
  Kontrol: açılış, üretim sekmesi bilgi satırı, ayarlar, geçmiş oku/yaz, WAV kaydet, MP3 (ffmpeg varsa), geçmişten geri yükle, tema değişimi. Her biri geçti/kaldı işaretlenir.
- [ ] T11.2 Geri dönüş kontrolü: Etap 3/4 düzeltmeleri duruyor mu, temizlik import kırmış mı, yeni regresyon varsa düzelt → turu başa sar.
- [ ] T11.3 Çıktı: PASSED/FAILED tablosu. FAILED varken Etap 12'ye geçilmez.

### ETAP 12 — Nihai rapor

- [ ] T12.1 Başlıklar zorunlu: Proje durumu (sağlık, çalışabilirlik, kritik var mı) → Tespit edilen hatalar (K/Y/O/D) → Düzeltilen hatalar → Değiştirilen dosyalar → Silinen dosya/kod + neden → Testler (pytest, build, runtime, geçti/kaldı) → Kalan bilinen sorunlar → Kod kalitesi → Güvenlik → Performans → Geliştirme önerileri (öncelikli) → Sonuç (stabil mi, kullanıma uygun mu, kritik borç var mı, yeni geliştirmeye engel var mı).
- [ ] T12.2 Commit yok, push yok (kullanıcı onayı olmadan). Rapor sözlü + dosya olarak sunulur.

## Tests / validation

- Her kod görevi TDD: başarısız test → düzelt → yeşil → tam süit. Komut standardı: `py -3.11 -m pytest -q` (tam), `py -3.11 -m pytest tests/test_<ad>.py -q` (odak), `py -3.11 smoke_test.py`, import dumanı `py -3.11 -c "import app.main_window"`.
- Geçiş kriteri: tam süit yeşil + smoke OK + (GUI değiştiyse) pencere açılış denemesi. Testsiz/doğrulanmamış değişiklik "başarılı" sayılmaz.
- Sık commit: etap başına değil, düzeltme/temizlik grubu başına (`fix(etap3): …`, `fix(etap4): …`, `chore(etap6): …`). Push kullanıcı onayıyla.

## Risks, tradeoffs, open questions

- Risk: `main_window.py` 2141 satır — yanlış kesim regresyon üretir. Tedbir: Etap 3/4'te minimal dokunuş, bölme yalnız öneri.
- Risk: `dist/`, `build_temp/`, `.tools/`, `.venv/` devasa — tarama yavaşlar, yanlışlıkla commite girer. Tedbir: aramalarda `dist`, `build_temp`, `.venv`, `.tools`, `__pycache__` hariç tutulur; silme öncesi `git ls-files` ile izlenme durumu bakılır.
- Risk: model indirme/CUDA ortamı her makinede yok. Tedbir: ağır testler mock ile; gerçek sentez testi opsiyonel, yokluğu eksik sayılmaz.
- Risk: kullanıcı verisi (`state/*.json`, `outputs/`) temizlikte gider. Tedbir: asla silinmez, yedek kontrolü (`*.bak`) Etap 3'te doğrulanır.
- Ödün: hız vs güvenlik — kritik düzeltmeler küçük tutulur, güzel-kod refactoru ertelenir.
- Açık sorular (uygulayıcıya): `build.bat` hangi `.spec`'i kullanıyor? `install_check.bat` dosyası gerçekten yok mu (README ölü referans mı)? `dist/` ve `build_temp/` git'te izleniyor mu? Bu üçü Etap 1'de netleşir, Etap 5 listesini belirler.
