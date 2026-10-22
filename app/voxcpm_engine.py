"""VoxCPM2 motoru — yalnız CUDA'da çalışır.

Neden yalnız CUDA: 2B parametreli diffüzyon AR modeli, resmi ölçüme göre
bfloat16'da ~8 GB VRAM ister. CPU'da çalışır ama kullanılamaz hızda kalır
(bu makinede ölçülmedi; kart olmadığı için kurulum kapısı kapalı). Bu yüzden
motor bir güvenlik kapısıyla korunur: NVIDIA sürücüsü yoksa ne indirilebilir
ne seçilebilir (bkz. ``app.engines.availability``).

Paket API'si (``voxcpm``, Apache-2.0)::

    from voxcpm import VoxCPM
    model = VoxCPM.from_pretrained(local_dir, load_denoiser=False, device="cuda")
    wav = model.generate(text, cfg_value=2.0, inference_timesteps=10)

``load_denoiser=False`` kritik: varsayılan gürültü temizleyici ModelScope
ister (``funasr``, ``modelscope`` ~100 MB ve ek model indirmesi). Temizleyici
opsiyonel bir kalite artışıdır; kapatınca bağımlılık yığını küçük kalır.

``optimize`` yalnız CUDA'da anlamlıdır (torch.compile + triton). CUDA yokken
paket ``ValueError`` atar, bu yüzden bayrak cihaza göre verilir.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

__all__ = ["VoxCpmAdapter", "SAMPLE_RATE", "REPO_ID", "WEIGHT_FILES"]

REPO_ID = "openbmb/VoxCPM2"
SAMPLE_RATE = 48_000
#: Yükleme için gereken asgari dosyalar (ağırlık indirmesi bunları ister).
WEIGHT_FILES = (
    "config.json",
    "model.safetensors",
    "audiovae.pth",
    "tokenizer.json",
    "tokenizer_config.json",
    "special_tokens_map.json",
    "tokenization_voxcpm2.py",
)


class VoxCpmAdapter:
    """``voxcpm.VoxCPM`` için ortak motor yüzeyi (numpy)."""

    accepts_speed = False
    single_language = False

    def __init__(
        self,
        status_callback: Callable[[str], None] | None = None,
        device: str = "cuda",
        cfg_value: float = 2.0,
        inference_timesteps: int = 10,
    ):
        self._status_callback = status_callback
        self.device_name = device
        self.sample_rate = SAMPLE_RATE
        self._device = device
        self._cfg_value = float(cfg_value)
        self._timesteps = int(inference_timesteps)
        self._model = None

    def _status(self, message: str) -> None:
        log.info(message)
        if self._status_callback:
            self._status_callback(message)

    def load(self):
        if self._model is not None:
            return self
        from app import model_manager

        try:
            from voxcpm import VoxCPM
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "VoxCPM2 motor dosyaları kurulu değil. "
                "Ayarlar ▸ Modeller bölümünden indirebilirsiniz."
            ) from exc

        root = model_manager.weights_dir("voxcpm2")
        if not root.is_dir():
            raise RuntimeError(
                "VoxCPM2 model ağırlıkları bulunamadı. "
                "Ayarlar ▸ Modeller bölümünden indirebilirsiniz."
            )
        self._status("VoxCPM2 modeli CUDA üzerinde yükleniyor…")
        self._model = VoxCPM.from_pretrained(
            str(root),
            load_denoiser=False,          # ModelScope bağımlılığını getirmesin
            optimize=(self._device == "cuda"),  # CPU'da torch.compile anlamsız/hata
            device=self._device,
        )
        self._status("VoxCPM2 hazır.")
        return self

    def synthesize(
        self,
        text: str,
        language_id: str | None = None,
        exaggeration=None,
        cfg_weight=None,
        audio_prompt_path: str | None = None,
        temperature=None,
        repetition_penalty=None,
        min_p=None,
        top_p=None,
        speed: float = 1.0,
        **kwargs,
    ) -> np.ndarray:
        """Metni seslendir; 48 kHz float32 mono dizi döner.

        VoxCPM2 dil etiketi istemez (30 dili kendisi tanır), bu yüzden
        ``language_id`` yok sayılır. Referans ses verilirse klonlama yapar.
        Ses tasarımı: metnin başına parantez içinde tarif yazılır.
        """
        self.load()
        audio = self._model.generate(
            text,
            reference_wav_path=audio_prompt_path or None,
            cfg_value=float(cfg_weight if cfg_weight is not None else self._cfg_value),
            inference_timesteps=self._timesteps,
        )
        data = np.asarray(audio, dtype=np.float32).reshape(-1)
        if data.size == 0:
            raise RuntimeError("VoxCPM2 boş ses üretti.")
        return data

    @property
    def model_sample_rate(self) -> int:
        """Modelin gerçek örnekleme hızı (yüklendikten sonra okunabilir)."""
        try:
            return int(self._model.tts_model.sample_rate)
        except Exception:
            return SAMPLE_RATE
