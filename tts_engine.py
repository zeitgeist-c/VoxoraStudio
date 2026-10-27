"""Voxora Studio — ses motoru seçimi ve ortak ses boru hattı.

Üç motor ailesi (tanımlar ``app.engines`` içinde):

  ema (varsayılan, paketle gelir)
    EMA Lightning, ONNX Runtime ile. Türkçe, tek ses, 48 kHz.
    ``torch`` GEREKMEZ. CPU'da ölçülen RTF ~0,03 (gerçek zamandan 30 kat hızlı).

  chatterbox (indirilir)
    Chatterbox Multilingual V3, PyTorch ile. 16 dil + ses klonlama, 24 kHz.
    ``torch`` ister; motor paketi kurulunca kullanılabilir.
    Cihaz sırası: CUDA → CPU. DirectML denenmez: EMA ölçümünde AMD GPU'da
    onnxruntime DirectML CPU'dan 15 kat yavaştı.

  voxcpm2 (indirilir, yalnız CUDA)
    VoxCPM2, PyTorch + diffüzyon AR. 30 dil, ses tasarımı, 48 kHz.
    NVIDIA sürücüsü olmayan makinede hiç seçilemez (bkz. ``app.engines``).

Ortak yüzey numpy'dir: ``synthesize(...) -> (np.ndarray float32 mono, sr)``.
Torch yalnız Chatterbox/VoxCPM2 motorlarının kendi içinde kullanılır; arayüz,
kayıt ve oynatma katmanı torch görmez. Bu, paketten torch'u çıkarmanın
önkoşuludur.
"""
from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Protocol

import numpy as np

from app import engines as engine_registry

log = logging.getLogger(__name__)

__all__ = [
    "Engine",
    "EmaEngineAdapter",
    "TorchEngine",
    "TTSEngine",
    "adjust_speed",
    "trim_leading_silence",
]


class Engine(Protocol):
    """Tüm motorların ortak yüzeyi (numpy)."""

    sample_rate: int

    def synthesize(self, text: str, **kwargs) -> np.ndarray: ...


def trim_leading_silence(
    audio: np.ndarray,
    sr: int,
    threshold: float = 0.005,
    max_trim_ms: int = 500,
    pre_buffer_ms: int = 20,
) -> np.ndarray:
    """Sentez çıktısının başındaki sessizliği kırp.

    Mutlak genlik eşiğiyle ilk sesli örneği bulur, öncesini atar. En fazla
    ``max_trim_ms`` kırpılır; kırpma noktasından ``pre_buffer_ms`` önce
    tutulur (atak geçişi yumuşasın). Girdi zayıfsa (sr<=0, boş, hepsi sessiz)
    orijinal dizi döner.

    Args:
        audio: float32 mono dizi.
        sr: Örnekleme hızı (Hz).
        threshold: Genlik eşiği (0.0-1.0 normalize).
        max_trim_ms: Bu kadar ms'den fazla kırpılmaz.
        pre_buffer_ms: Kırpma noktası öncesi korunacak tampon (ms).

    Returns:
        Kırpılmış dizi; kırpılacak bir şey yoksa orijinali.
    """
    if audio is None or sr is None or sr <= 0:
        return audio
    data = np.asarray(audio)
    if data.size == 0:
        return audio
    flat = data.reshape(-1)
    max_samples = int(max_trim_ms * sr / 1000)
    pre_samples = int(pre_buffer_ms * sr / 1000)
    first = _first_loud_sample(flat, threshold, max_samples + pre_samples)
    if first < 0:
        return audio  # Hep sessiz (ya da kırpma penceresi dışında): dokunma
    keep_from = max(0, first - pre_samples)
    if keep_from >= max_samples:
        keep_from = 0  # Çok uzun sessizlik; pre-buffer verme
    if keep_from <= 0:
        return audio
    return data[..., keep_from:]


def _first_loud_sample(flat: np.ndarray, threshold: float, limit: int) -> int:
    """Eşiği aşan ilk örneğin indeksi; ``limit`` örnekten sonrasına bakılmaz.

    Neden parçalı: ``np.flatnonzero(np.abs(flat) > threshold)`` tüm dizinin
    mutlak değerini ve indeks listesini belleğe çıkarıyordu. 10 dakikalık
    48 kHz kayıtta ek tepe bellek 259 MB ölçüldü (dizinin kendisi 115 MB);
    64 KB'lık bloklarla aynı sonuç 0,6 MB ile bulunuyor.

    ``limit`` neden yeterli: kırpma yalnız ilk sesli örnek ``max_trim_ms +
    pre_buffer_ms`` penceresinin içindeyse yapılır (bkz. ``keep_from`` mantığı);
    sonrasında ilk sesli örnek bulunsa da sonuç "dokunma" olurdu.

    Returns:
        İndeks ya da pencere içinde sesli örnek yoksa ``-1``.
    """
    total = min(flat.size, max(0, int(limit)))
    block = 1 << 16
    for start in range(0, total, block):
        piece = flat[start:min(start + block, total)]
        above = np.flatnonzero(np.abs(piece) > threshold)
        if above.size:
            return start + int(above[0])
    return -1


def adjust_speed(audio: np.ndarray, speed: float, sample_rate: int) -> np.ndarray:
    """Zaman gerinimi — yalnız hızı kendi uygulamayan motorlar için.

    EMA hızı modelin içinde uygular (``accepts_speed``); Chatterbox ve
    VoxCPM2 için burada gerilir. librosa varsa faz vocoder'ı kullanılır,
    yoksa doğrusal yeniden örnekleme (hızlı, kalite biraz düşük).
    """
    if audio is None or abs(float(speed) - 1.0) < 0.01:
        return audio
    data = np.asarray(audio, dtype=np.float32).reshape(-1)
    if data.size == 0:
        return audio
    try:
        import librosa

        return np.asarray(
            librosa.effects.time_stretch(data, rate=float(speed)), dtype=np.float32
        )
    except Exception as exc:  # librosa yoksa ya da başarısızsa
        log.warning("Tempo işleme başarısız, yeniden örnekleme kullanılıyor: %s", exc)
        target = max(1, int(round(data.size / float(speed))))
        source_index = np.linspace(0, data.size - 1, target, dtype=np.float32)
        return np.interp(source_index, np.arange(data.size), data).astype(np.float32)


class EmaEngineAdapter:
    """``app.ema_onnx.EmaOnnxEngine`` için ince uyarlama.

    ONNX motoru zaten numpy döndürür; burada yalnız ortak yüzeye oturtulur
    (``sample_rate`` özelliği ve kullanılmayan parametrelerin yutulması).
    """

    accepts_speed = True
    single_language = True

    def __init__(self, status_callback: Callable[[str], None] | None = None):
        from app import ema_onnx

        self._engine = ema_onnx.EmaOnnxEngine(status_callback=status_callback)
        self.sample_rate = ema_onnx.SAMPLE_RATE
        self.device_name = "cpu"

    def load(self):
        self._engine.load()
        return self

    def synthesize(
        self,
        text: str,
        language_id=None,
        exaggeration=None,
        cfg_weight=None,
        audio_prompt_path=None,
        temperature=None,
        repetition_penalty=None,
        min_p=None,
        top_p=None,
        speed: float = 1.0,
        **kwargs,
    ) -> np.ndarray:
        """EMA tek dillidir: dil/ifade/klonlama parametreleri yok sayılır."""
        return self._engine.synthesize(text, speed=float(speed))


class TorchEngine:
    """Chatterbox PyTorch tabanlı sentez (CUDA veya CPU).

    PyTorch tensörünü numpy'a çevirir: dış katman torch görmez.
    """

    accepts_speed = False

    def __init__(self, model, device_name: str = "cpu"):
        self.model = model
        self.device_name = device_name
        self.sample_rate = int(model.sr)

    def synthesize(
        self,
        text: str,
        language_id: str = "tr",
        exaggeration: float = 0.5,
        cfg_weight: float = 0.5,
        audio_prompt_path: str | None = None,
        temperature: float = 0.8,
        repetition_penalty: float = 2.0,
        min_p: float = 0.05,
        top_p: float = 1.0,
        speed: float = 1.0,
        **kwargs,
    ) -> np.ndarray:
        tensor = self.model.generate(
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
        try:
            array = tensor.detach().cpu().numpy()
        except AttributeError:  # zaten numpy ise
            array = np.asarray(tensor)
        return np.asarray(array, dtype=np.float32).reshape(-1)


class TTSEngine:
    """Motor yönlendiricisi: seçilen motorun en iyi cihazını kurar."""

    def __init__(
        self,
        language_id: str | None = None,
        exaggeration=None,
        cfg_weight=None,
        status_callback: Callable[[str], None] | None = None,
        engine_name: str | None = None,
    ):
        spec = engine_registry.spec(engine_name or engine_registry.DEFAULT_ENGINE)
        self.engine_spec = spec
        self.engine_name = spec.key
        self.language_id = language_id or (spec.languages[0] if spec.languages else "tr")
        self.exaggeration = exaggeration
        self.cfg_weight = cfg_weight
        self._status_callback = status_callback
        self.device_name, self.engine = self._select_engine()
        self.sample_rate = int(getattr(self.engine, "sample_rate", spec.sample_rate))
        self._status(f"Aktif motor: {self.display_name} ({self.device_name})")

    @property
    def display_name(self) -> str:
        return self.engine_spec.label

    def _status(self, message: str) -> None:
        log.info(message)
        if self._status_callback:
            self._status_callback(message)

    def _select_engine(self) -> tuple[str, Engine]:
        if self.engine_name == "ema":
            return self._select_ema()
        if self.engine_name == "voxcpm2":
            return self._select_voxcpm2()
        return self._select_chatterbox()

    # --- EMA (paketle gelir, torch yok) --------------------------------------
    def _select_ema(self) -> tuple[str, Engine]:
        self._status("EMA Lightning motoru hazırlanıyor (ONNX, CPU)…")
        adapter = EmaEngineAdapter(status_callback=self._status).load()
        return "cpu", adapter

    # --- Chatterbox (indirilir) ---------------------------------------------
    def _select_chatterbox(self) -> tuple[str, Engine]:
        from app import hardware

        profile = hardware.detect()
        if profile.cuda:
            try:
                return self._chatterbox_on("cuda", profile.gpu_name or "CUDA")
            except Exception as exc:
                self._status(f"CUDA yüklenemedi, CPU'ya geçiliyor: {exc}")
                log.warning("Chatterbox CUDA yüklenemedi: %s", exc)
        return self._chatterbox_on("cpu", "CPU")

    def _chatterbox_on(self, device: str, device_label: str) -> tuple[str, Engine]:
        from app import engine_pack, model_manager

        # Kütüphaneler motor paketinden gelir (sistem Python'una kurulmaz).
        if not engine_pack.add_engine_to_path("chatterbox"):
            raise RuntimeError(
                "Chatterbox motor dosyaları kurulu değil. "
                "Ayarlar ▸ Modeller bölümünden indirebilirsiniz."
            )
        try:
            from chatterbox.mtl_tts import ChatterboxMultilingualTTS
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "Chatterbox motor dosyaları eksik veya bozuk. "
                "Ayarlar ▸ Modeller bölümünden yeniden kurun."
            ) from exc

        # Ağırlık klasörü kullanıcı verisinde; paket varsayılan HF önbelleğine
        # bakmasın diye HF_HOME buraya çevrilir.
        weights = model_manager.weights_dir("chatterbox")
        if not weights.is_dir():
            raise RuntimeError(
                "Chatterbox model ağırlıkları bulunamadı. "
                "Ayarlar ▸ Modeller bölümünden indirebilirsiniz."
            )
        import os

        os.environ["HF_HOME"] = str(weights.parent)
        os.environ["HF_HUB_OFFLINE"] = "1"  # ağırlıklar yerelde; ağa çıkma

        self._status(f"Chatterbox modeli {device_label} üzerinde yükleniyor…")
        model = ChatterboxMultilingualTTS.from_local(str(weights), device=device)
        return device, TorchEngine(model, device_label)

    # --- VoxCPM2 (indirilir, yalnız CUDA) -----------------------------------
    def _select_voxcpm2(self) -> tuple[str, Engine]:
        from app import hardware

        profile = hardware.detect()
        if not profile.cuda:
            raise RuntimeError(
                "VoxCPM2 yalnız NVIDIA ekran kartı olan bilgisayarlarda çalışır. "
                "Bu bilgisayarda CUDA bulunamadı."
            )
        from app import engine_pack

        if not engine_pack.add_engine_to_path("voxcpm2"):
            raise RuntimeError(
                "VoxCPM2 motor dosyaları kurulu değil. "
                "Ayarlar ▸ Modeller bölümünden indirebilirsiniz."
            )
        from app import voxcpm_engine
        self._status("VoxCPM2 modeli CUDA üzerinde yükleniyor…")
        adapter = voxcpm_engine.VoxCpmAdapter(
            status_callback=self._status, device="cuda"
        ).load()
        return "cuda", adapter

    # --- ortak --------------------------------------------------------------
    def synthesize(self, text: str, **kwargs) -> tuple[np.ndarray, int]:
        """Tek çağrı: (float32 mono dizi, örnekleme hızı).

        Hızı motor kendi uygulamıyorsa burada gerilir.
        """
        speed = float(kwargs.pop("speed", 1.0) or 1.0)
        if getattr(self.engine, "accepts_speed", False):
            audio = self.engine.synthesize(text, speed=speed, **kwargs)
        else:
            audio = self.engine.synthesize(text, **kwargs)
            audio = adjust_speed(audio, speed, self.sample_rate)
        return np.asarray(audio, dtype=np.float32).reshape(-1), self.sample_rate
