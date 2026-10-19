"""
Voxora Studio - TTS motoru (motor seçimi + cihaz yönetimi).

İki motor ailesi vardır:

  chatterbox (varsayılan) - Chatterbox Multilingual V3, 16 dil + ses klonlama:
    1) PyTorch CUDA (NVIDIA) - en hızlı
    2) ONNX Runtime DirectML (AMD/NVIDIA) - model varsa (Plan 17)
    3) PyTorch CPU - her durumda çalışır

  ema - EMA Lightning: yalnız Türkçe, tek ses, ~34 MB, CPU'da bile hızlı.
    İlk kullanımda ağırlıklar Hugging Face'ten indirilir (~34 MB).

Ortak yüzey: ``engine.synthesize(text, ...) -> torch.Tensor`` ve
``engine.sample_rate``. Hız (speed):
  - EMA hızı modelin kendi parametresiyle uygular (``accepts_speed``);
    dispatcher ayrıca time-stretch yapmaz.
  - Chatterbox çıktısı dispatcher'da ``_adjust_speed`` ile gerilir.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import numpy as np
import torch

from config import (
    DEFAULT_CFG_WEIGHT,
    DEFAULT_ENGINE,
    DEFAULT_EXAGGERATION,
    DEFAULT_LANGUAGE_ID,
    ENGINE_EMA,
    VALID_ENGINES,
)

log = logging.getLogger(__name__)


class Engine(Protocol):
    """Tüm engine'lerin ortak yüzeyi."""

    @property
    def sample_rate(self) -> int: ...

    def synthesize(
        self,
        text: str,
        language_id: str,
        exaggeration: float,
        cfg_weight: float,
        audio_prompt_path: str | None,
        temperature: float,
        repetition_penalty: float,
        min_p: float,
        top_p: float,
    ) -> "torch.Tensor": ...


class TorchEngine:
    """Chatterbox PyTorch tabanlı sentez (CUDA veya CPU)."""

    def __init__(self, model):
        self.model = model

    @property
    def sample_rate(self) -> int:
        return self.model.sr

    def synthesize(
        self,
        text,
        language_id,
        exaggeration,
        cfg_weight,
        audio_prompt_path,
        temperature,
        repetition_penalty,
        min_p,
        top_p,
    ):
        return self.model.generate(
            text,
            language_id=language_id,
            audio_prompt_path=audio_prompt_path,
            exaggeration=exaggeration,
            cfg_weight=cfg_weight,
            temperature=temperature,
            repetition_penalty=repetition_penalty,
            min_p=min_p,
            top_p=top_p,
        )


class EmaEngine:
    """EMA Lightning - küçük, hızlı, Türkçe'ye özel motor (CPU/GPU otomatik).

    Tek kadın sesi okur; referans ses ve örnekleme parametreleri kullanılmaz.
    Hız, modelin kendi ``say(speed=...)`` parametresiyle uygulanır; bu yüzden
    ``accepts_speed`` işaretlidir ve dispatcher time-stretch yapmaz.
    """

    accepts_speed = True

    #: EMA çıktısı varsayılan olarak 48 kHz; ilk sentezde Speech değeriyle tazelenir.
    DEFAULT_SAMPLE_RATE = 48_000

    def __init__(
        self,
        device: str = "auto",
        model=None,
        status_callback: Callable[[str], None] | None = None,
    ):
        self._status_callback = status_callback
        if model is None:
            from ema_lightning import EMA

            self._status(
                "EMA Lightning ağırlıkları hazırlanıyor "
                "(ilk çalıştırmada ~34 MB indirilebilir)..."
            )
            model = EMA(device=device)
        self._model = model
        self._sample_rate = self.DEFAULT_SAMPLE_RATE

    def _status(self, message: str) -> None:
        log.info(message)
        if self._status_callback:
            self._status_callback(message)

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(
        self,
        text,
        language_id=None,
        exaggeration=None,
        cfg_weight=None,
        audio_prompt_path=None,
        temperature=None,
        repetition_penalty=None,
        min_p=None,
        top_p=None,
        speed: float = 1.0,
    ):
        """Metni seslendirir; (1, N) float32 tensörü döner.

        Dil ve ifade parametreleri yok sayılır: EMA yalnız Türkçe ve tek
        seslidir. Boş çıktı (seslendirilecek karakter yok) yerine kısa bir
        sessizlik döner ki uzun üretimler ortada kesilmesin.
        """
        speech = self._model.say(text, speed=float(speed))
        audio = np.asarray(speech.audio, dtype=np.float32).reshape(-1)
        sample_rate = int(getattr(speech, "sample_rate", 0) or self._sample_rate)
        self._sample_rate = sample_rate
        if audio.size == 0:
            log.warning("EMA boş ses üretti; 0.25 sn sessizlik kullanılıyor: %r", text[:60])
            audio = np.zeros(max(1, int(sample_rate * 0.25)), dtype=np.float32)
        return torch.from_numpy(audio).reshape(1, -1)


class OnnxEngine:
    """
    Hibrit engine: T3 ONNX (DirectML) + S3Gen/vocoder PyTorch.

    Plan 17: T3 ONNX + S3Gen/vocoder PyTorch fallback.
    Plan 18/19: S3Gen + vocoder ONNX.

    Şimdilik sadece ONNX session yükleme + provider seçimi yapılır;
    gerçek hibrit inference Plan 17 sonrasında tamamlanacak.
    """

    # Plan 17 (hibrit sentez) tamamlanana dek dispatcher bu motoru seçmemeli.
    SYNTHESIS_READY = False

    def __init__(self, model_dir: str | Path = "models", device: str = "dml"):
        self.device = device
        self._sample_rate = 24_000  # Tahmini; v0.1.1'de export sonrası sabitlenecek.
        self.model_loaded = False

        model_dir = Path(model_dir)
        t3_path = model_dir / "chatterbox_t3.onnx"
        meta_path = model_dir / "chatterbox_t3.meta.json"

        if not t3_path.exists() or not meta_path.exists():
            log.warning("T3 ONNX model bulunamadı: %s", t3_path)
            return

        try:
            import json as _json
            import onnxruntime as ort

            providers = self._select_providers(device)
            sess_options = ort.SessionOptions()
            sess_options.graph_optimization_level = ort.GraphOptimizationLevel.ORT_ENABLE_ALL

            self._t3_session = ort.InferenceSession(
                str(t3_path), sess_options, providers=providers
            )
            self._t3_meta = _json.loads(meta_path.read_text(encoding="utf-8"))
            self.model_loaded = True
            log.info("T3 ONNX yüklendi: %s, providers=%s", t3_path, providers)
        except Exception as e:
            log.error("T3 ONNX yüklenemedi: %s", e)

    def _select_providers(self, device: str) -> list[str]:
        """DirectML varsa onu seç, yoksa CPU."""
        try:
            import onnxruntime as ort
            available = ort.get_available_providers()
            if device == "dml" and "DmlExecutionProvider" in available:
                return ["DmlExecutionProvider", "CPUExecutionProvider"]
        except Exception:
            pass
        return ["CPUExecutionProvider"]

    @property
    def sample_rate(self) -> int:
        return self._sample_rate

    def synthesize(self, text, language_id, exaggeration, cfg_weight, audio_prompt_path, temperature, repetition_penalty, min_p, top_p):
        """Hibrit: T3 ONNX + S3Gen/vocoder PyTorch.

        Plan 17'de T3 ONNX + geri kalan PyTorch. T3 yoksa fallback
        PyTorch tam pipeline kullanır.
        """
        raise NotImplementedError(
            "OnnxEngine hibrit synthesize Plan 17 sonrasında tamamlanacak. "
            "Önce Plan 17 export (export_onnx.py) çalıştırılmalı."
        )


class TTSEngine:
    """Motor dispatcher'ı. Açılışta seçilen motorun en iyi cihazını seçer."""

    def __init__(
        self,
        language_id: str = DEFAULT_LANGUAGE_ID,
        exaggeration: float = DEFAULT_EXAGGERATION,
        cfg_weight: float = DEFAULT_CFG_WEIGHT,
        status_callback: Callable[[str], None] | None = None,
        engine_name: str | None = None,
    ):
        self.language_id = language_id
        self.exaggeration = exaggeration
        self.cfg_weight = cfg_weight
        self._status_callback = status_callback
        self.engine_name = engine_name if engine_name in VALID_ENGINES else DEFAULT_ENGINE
        self.device_name, self.engine = self._select_engine()
        self._status(f"Aktif motor: {type(self.engine).__name__} ({self.device_name})")
        log.info(
            "Aktif motor: %s / %s (cihaz=%s)",
            self.display_name,
            type(self.engine).__name__,
            self.device_name,
        )

    @property
    def display_name(self) -> str:
        """Kullanıcıya gösterilecek motor adı."""
        return "EMA Lightning" if self.engine_name == ENGINE_EMA else "Chatterbox Multilingual"

    def _status(self, message: str) -> None:
        log.info(message)
        if self._status_callback:
            self._status_callback(message)

    def _select_engine(self) -> tuple[str, Engine]:
        if self.engine_name == ENGINE_EMA:
            return self._select_ema_engine()
        return self._select_chatterbox_engine()

    def _select_ema_engine(self) -> tuple[str, Engine]:
        """EMA Lightning: cihaz otomatik (CUDA varsa CUDA, yoksa CPU)."""
        device = "cuda" if torch.cuda.is_available() else "cpu"
        self._status(f"EMA Lightning motoru hazırlanıyor (cihaz: {device})...")
        engine = EmaEngine(device=device, status_callback=self._status)
        return device, engine

    def _select_chatterbox_engine(self) -> tuple[str, Engine]:
        self._status("CUDA kullanılabilirliği kontrol ediliyor...")
        if torch.cuda.is_available():
            try:
                from chatterbox.mtl_tts import ChatterboxMultilingualTTS

                self._status("CUDA bulundu. Chatterbox modeli CUDA üzerinde yükleniyor...")
                self._status("İlk çalıştırmada model dosyaları indirilebilir.")
                model = ChatterboxMultilingualTTS.from_pretrained(device="cuda")
                return "cuda", TorchEngine(model)
            except Exception as e:
                self._status(f"CUDA yüklenemedi, diğer seçeneklere geçiliyor: {e}")
                log.warning("CUDA yüklenemedi: %s", e)

        try:
            self._status("DirectML/ONNX sağlayıcıları kontrol ediliyor...")
            import onnxruntime as ort

            if "DmlExecutionProvider" in ort.get_available_providers():
                self._status("DirectML provider mevcut, ONNX motoru deneniyor...")
                onnx = OnnxEngine(device="dml")
                if onnx.model_loaded and OnnxEngine.SYNTHESIS_READY:
                    return "dml", onnx
                if onnx.model_loaded:
                    self._status("ONNX modeli mevcut ama hibrit sentez henüz hazır değil; CPU moduna geçiliyor.")
                else:
                    self._status("DirectML provider var ama ONNX model henüz yok. CPU moduna geçiliyor.")
        except Exception as e:
            self._status(f"DirectML kontrolü başarısız, CPU moduna geçiliyor: {e}")
            log.warning("DirectML kontrolü başarısız: %s", e)

        from chatterbox.mtl_tts import ChatterboxMultilingualTTS

        self._status("Chatterbox modeli CPU üzerinde yükleniyor...")
        self._status("İlk çalıştırmada model dosyaları indirilebilir.")
        model = ChatterboxMultilingualTTS.from_pretrained(device="cpu")
        return "cpu", TorchEngine(model)

    def synthesize(
        self,
        text: str,
        language_id: str | None = None,
        exaggeration: float | None = None,
        cfg_weight: float | None = None,
        audio_prompt_path: str | None = None,
        temperature: float = 0.8,
        repetition_penalty: float = 2.0,
        min_p: float = 0.05,
        top_p: float = 1.0,
        speed: float = 1.0,
    ) -> tuple["torch.Tensor", int]:
        """Tek çağrı: tensor + sample_rate döner."""
        params = (
            text,
            language_id or self.language_id,
            self.exaggeration if exaggeration is None else exaggeration,
            self.cfg_weight if cfg_weight is None else cfg_weight,
            audio_prompt_path,
            temperature,
            repetition_penalty,
            min_p,
            top_p,
        )
        if getattr(self.engine, "accepts_speed", False):
            # EMA hızı kendi içinde uygular; dışarıdan time-stretch gerekmez.
            wav = self.engine.synthesize(*params, speed=speed)
        else:
            wav = self.engine.synthesize(*params)
            wav = self._adjust_speed(wav, speed)
        return wav, self.engine.sample_rate

    def _adjust_speed(self, wav: "torch.Tensor", speed: float) -> "torch.Tensor":
        if abs(speed - 1.0) < 0.01:
            return wav

        try:
            import librosa
            import numpy as np

            data = wav.squeeze().detach().cpu().numpy().astype(np.float32)
            stretched = librosa.effects.time_stretch(data, rate=float(speed))
            return torch.from_numpy(stretched).to(wav.device).reshape(1, -1)
        except Exception as e:
            log.warning("Tempo işleme başarısız, basit yeniden örnekleme kullanılıyor: %s", e)
            import torch.nn.functional as F

            data = wav.reshape(1, 1, -1)
            new_len = max(1, int(data.shape[-1] / speed))
            return F.interpolate(data, size=new_len, mode="linear", align_corners=False).reshape(1, -1)
