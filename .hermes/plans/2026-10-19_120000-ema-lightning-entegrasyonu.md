# EMA Lightning motorunu Voxora Studio'ya ekleme (2026-10-19)

Amaç: Voxora'ya ikinci ses motoru olarak EMA Lightning'i eklemek
(`canberkkkkkk/ema-lightning`, Apache-2.0, ~34 MB, yalnız Türkçe, 8.6M parametre).
Chatterbox varsayılan motor olarak kalır.

## Kararlar
- Motor seçimi: Ayarlar ▸ Ses ▸ "Ses motoru" (chatterbox | ema). Varsayılan: chatterbox.
- EMA yalnız Türkçe ve tek seslidir: dil "tr"ye kilitlenir; referans ses ve
  Chatterbox parametreleri (hazır ayar/ifade/netlik/yaratıcılık/tekrar) devre dışı;
  hız + duraklama geçerli kalır.
- Hız: EMA'da modelin kendi `speed` parametresi (0.25–4) kullanılır; dispatcher
  time-stretch uygulamaz (`accepts_speed`). Chatterbox yolu değişmez.
- Motor değişiminde motor arka planda yeniden yüklenir (ModelLoadDialog yeniden kullanılır).
- Ağırlıklar ilk kullanımda HF önbelleğine iner (varsayılan `~/.cache/huggingface`).
- Dil tercihi: EMA aktifken seçili Chatterbox dili `chatterbox_language_id` olarak
  saklanır; geri dönünce geri yüklenir.

## Dosya haritası
1. `tts_engine.py`: `EmaEngine` + `TTSEngine(engine_name=...)` + hız aktarımı; `display_name`.
2. `config.py`: ENGINE_* sabitleri. `app/constants.py`: Engine seçenek etiketleri.
3. `app/workers.py`: `EngineLoader(engine_name=...)`.
4. `app/main_window.py`: engine_combo + durum uygulaması + yeniden yükleme + özet/sistem etiketleri.
5. `requirements.txt`, `build.bat` (collect-all), `scripts/setup_env.py`, `smoke_test.py`, `app.py` (HF env).
6. `tests/test_ema_engine.py`, `tests/test_engine_selection_ui.py`.

## Doğrulama kapıları
- `python -m unittest discover -s tests` (tüm paket) geçer.
- `smoke_test.py` (light) tüm kontroller başarılı.
- Gerçek EMA sentezi: `TTSEngine(engine_name="ema")` ile WAV üretimi + süre/örnekleme kontrolü.
- Offscreen UI: motor değişimi widget durumları; ekran görüntüsü kanıtı.
