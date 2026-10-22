"""EMA Lightning — ONNX ile Türkçe seslendirme (PyTorch gerekmez).

Neden ONNX: EMA'nın PyTorch sürümü 365 MB'lık torch paketini zorunlu kılıyordu.
Topluluğun ONNX dönüşümü (``ozcancelik/ema-lightning-onnx``, Apache-2.0) aynı
modeli 44 MB ağırlıkla ve ``onnxruntime`` ile çalıştırıyor. Ölçüm (bu makine,
16 iş parçacığı, CPU):

    PyTorch : yükleme 0,25 sn · sentez 0,39 sn · RTF 0,14
    ONNX    : yükleme 1,18 sn · sentez 0,09 sn · RTF 0,04

Yani ONNX hem 3,4 kat hızlı hem de paketten torch'u tamamen çıkarıyor.
DirectML (AMD GPU) ölçüldü ve REDDEDİLDİ: RTF 0,39 — CPU'dan 15 kat yavaş.
Bu yüzden bu motor her zaman CPUExecutionProvider kullanır.

Boru hattı ``ema_lightning`` paketinin davranışının portudur (bölme, metin
önişlemcisi, kare planlama, pencere çözme). Sayısal sonuç upstream
``export/verify.py`` ile float hassasiyetinde eşleşir.
"""
from __future__ import annotations

import json
import logging
import re
import unicodedata
import wave
from pathlib import Path

import numpy as np

log = logging.getLogger(__name__)

__all__ = [
    "REPO",
    "FILES",
    "SAMPLE_RATE",
    "EmaOnnxEngine",
    "chunk_text",
    "Frontend",
    "models_ready",
    "ensure_models",
    "resolve_models_dir",
]

#: Ağırlık deposu (Apache-2.0).
REPO = "ozcancelik/ema-lightning-onnx"

#: Paketlemek/indirmek için gereken dört dosya.
FILES = ("text.onnx", "sound.onnx", "decoder.onnx", "meta.json")

SAMPLE_RATE = 48_000
FRAMES_PER_SECOND = 25
HOP = 1920            # kare başına çözücü örneği
WINDOW = 100          # ilk pencereden sonra kare sayısı
FIRST_WINDOW = 25
CONTEXT = 8
MAX_FRAMES = 3000
SEED = 0

# --- metin bölme (ema_lightning.chunker portu) -------------------------------
LETTERS_PER_SECOND = 18.0
MAX_SECONDS = 10.0
MAX_LETTERS = 250
SENTENCE_PAUSE = 0.25
CLAUSE_PAUSE = 0.12
_CUTS = (
    (re.compile(r"[.!?]+[\"']*(?= )"), SENTENCE_PAUSE),
    (re.compile(r"[,;:](?= )"), CLAUSE_PAUSE),
    (re.compile(r"\S(?= )"), CLAUSE_PAUSE),
)
_LETTER = re.compile(r"[^\W\d_]")


def chunk_text(text: str, speed: float = 1.0) -> list[tuple[str, float]]:
    """[(parça, sonrasındaki sessizlik saniyesi)] — her parça noktalama ile biter."""
    limit = int(min(MAX_LETTERS, LETTERS_PER_SECOND * MAX_SECONDS * speed))
    pieces: list[tuple[str, float]] = []
    rest = text.strip()
    while rest:
        cut, pause = len(rest), 0.0
        if len(rest) > limit:
            cut = limit
            for pattern, gap in _CUTS:
                ends = [m.end() for m in pattern.finditer(rest, 0, limit + 1)]
                if ends:
                    cut, pause = ends[-1], gap
                    break
        piece, rest = rest[:cut].strip(), rest[cut:].strip()
        if _LETTER.search(piece):
            pieces.append((_finish(piece), pause))
    if pieces:
        pieces[-1] = (pieces[-1][0], 0.0)
    return pieces


def _finish(piece: str) -> str:
    if piece.rstrip("\"'")[-1:] in (".", "!", "?"):
        return piece
    return piece.rstrip(",;:- ") + "."


# --- metin önişlemcisi (ema_lightning.frontend portu) ------------------------
_UNSAFE = re.compile(
    "[\x00-\x08\x0b-\x1f\x7f-\x9f\u061c\u200e\u200f\u202a-\u202e\u2066-\u2069]"
)
_TYPOGRAPHY = str.maketrans({
    "’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'",
    "“": '"', "”": '"', "„": '"', "«": '"', "»": '"',
    "–": "-", "—": "-", "−": "-", "…": "...",
})
_TURKISH = frozenset("çğıöşüÇĞİÖŞÜ")


class Frontend:
    """Yazılı Türkçe girer, modelin kendi alfabesinde metin çıkar."""

    def __init__(self, vocab):
        self.vocab = frozenset(vocab)
        try:
            from normalizer_tr import Normalizer

            self.normalizer = Normalizer()
        except Exception:  # normalizer yoksa ham metinle devam
            self.normalizer = None

    def __call__(self, text: str) -> str:
        text = _UNSAFE.sub(" ", text.encode("utf-8", "ignore").decode("utf-8"))
        if not text.strip():
            return ""
        spoken = [self._spoken(block) for block in _blocks(text)]
        return self.alphabet(" ".join(spoken))

    def _spoken(self, text: str) -> str:
        if self.normalizer is None:
            return text
        try:
            return self.normalizer.normalize(
                text, ambiguity_policy="fallback").normalized_text
        except Exception:
            # Tek bir cümleyi kaybetmektense ham metni okumak yeğdir.
            return text

    def alphabet(self, text: str) -> str:
        text = text.translate(_TYPOGRAPHY).replace("İ", "i").replace("I", "ı")
        text = text.lower()
        out = []
        for char in text:
            if char not in _TURKISH:
                char = "".join(
                    c for c in unicodedata.normalize("NFKD", char)
                    if not unicodedata.combining(c)
                )
            out.append(char if char and all(c in self.vocab for c in char) else " ")
        return re.sub(r"\s+", " ", "".join(out)).strip()


def _blocks(text: str, size: int = 8 * 1024):
    words, block, used = text.split(), [], 0
    for word in words:
        weight = len(word.encode("utf-8")) + 1
        if block and used + weight > size:
            yield " ".join(block)
            block, used = [], 0
        block.append(word)
        used += weight
    if block:
        yield " ".join(block)


# --- kare planlama (upstream export/verify.py plan() portu) ------------------
def _plan(ids, cw, wstart, dur, speed: float = 1.0):
    dur = np.asarray(dur, dtype=np.float32) / speed
    length = len(ids)
    n_words = int(cw[-1]) + 1
    counts = np.zeros(n_words)
    np.add.at(counts, cw, dur)
    counts = np.clip(np.round(counts), 1, 250).astype(np.int64)
    frames = min(int(counts.sum()), MAX_FRAMES)
    fw = np.repeat(np.arange(n_words), counts)[:frames]
    starts = np.cumsum(counts) - counts
    fp = ((np.arange(frames) - starts[fw]) / counts[fw]).astype(np.float32)
    c = np.maximum(dur, 1e-4).astype(np.float32)
    done = np.cumsum(c)
    before = done - c
    total = np.zeros(n_words, np.float32)
    np.add.at(total, cw, c)
    cp = np.clip(
        (done - before[wstart] - 0.5 * c) / np.maximum(total[cw], 1e-8), 0, 1
    )
    wlen = np.maximum(np.bincount(cw, minlength=n_words).astype(np.float32), 1)
    woff = np.cumsum(wlen) - wlen
    cg = woff[cw] + cp * wlen[cw]
    fg = woff[fw] + fp * wlen[fw]
    return fw, cg.astype(np.float32), fg.astype(np.float32), length


def _windows(frames: int):
    spans, start = [], 0
    while start < frames:
        end = min(frames, start + (FIRST_WINDOW if start == 0 else WINDOW))
        spans.append((start, end))
        start = end
    return spans


# --- model yeri ---------------------------------------------------------------
def resolve_models_dir() -> Path:
    """Ağırlık klasörü: paketle gelen kopya kazanır, yoksa kullanıcı klasörü."""
    from app import paths as app_paths

    bundled = app_paths.bundled_models_dir() / "ema-onnx"
    if models_ready(bundled):
        return bundled
    return app_paths.models_dir() / "ema-onnx"


def models_ready(where: Path | str | None = None) -> bool:
    root = Path(where) if where else resolve_models_dir()
    return all((root / name).is_file() for name in FILES)


def ensure_models(progress=None) -> Path:
    """Ağırlık klasörünü döndür; yoksa indir (paketle gelen kopya varsa hiç ağa çıkma)."""
    root = resolve_models_dir()
    if models_ready(root):
        return root
    if progress:
        progress("EMA Lightning model dosyaları indiriliyor (44 MB)…")
    try:
        from huggingface_hub import snapshot_download
    except ModuleNotFoundError as exc:  # pragma: no cover
        raise RuntimeError(
            "EMA modeli indirilemedi: huggingface_hub bulunamadı."
        ) from exc
    root.mkdir(parents=True, exist_ok=True)
    snapshot_download(
        repo_id=REPO,
        local_dir=str(root),
        allow_patterns=list(FILES),
    )
    if not models_ready(root):
        raise RuntimeError("EMA model indirmesi tamamlanamadı.")
    return root


# --- motor --------------------------------------------------------------------
class EmaOnnxEngine:
    """EMA Lightning ONNX oturumları; ``synthesize`` Türkçe metni sese çevirir.

    Oturumlar tembel açılır: motor seçilip de kullanılmazsa 1,2 saniyelik
    yükleme bedeli ödenmez.
    """

    #: Motorun hız parametresi kendi içinde uygulanır; dışarıdan time-stretch yok.
    accepts_speed = True
    #: Bu motor için dil seçimi yok (tek dil).
    single_language = True
    sample_rate = SAMPLE_RATE

    def __init__(self, where: Path | str | None = None, status_callback=None):
        self._where = Path(where) if where else None
        self._status_callback = status_callback
        self._sessions: dict | None = None
        self._meta: dict | None = None
        self._frontend: Frontend | None = None

    def _status(self, message: str) -> None:
        log.info(message)
        if self._status_callback:
            self._status_callback(message)

    @property
    def ready(self) -> bool:
        return self._sessions is not None

    def load(self, progress=None):
        if self._sessions is not None:
            return self
        try:
            import onnxruntime as ort
        except ModuleNotFoundError as exc:
            raise RuntimeError(
                "EMA motoru için onnxruntime gerekli; kurulumda eksik."
            ) from exc
        root = self._where or ensure_models(progress or self._status)
        with open(Path(root) / "meta.json", encoding="utf-8") as handle:
            self._meta = json.load(handle)
        options = ort.SessionOptions()
        # DirectML ölçüldü ve reddedildi (CPU'dan 15 kat yavaş); her zaman CPU.
        self._sessions = {
            name: ort.InferenceSession(
                str(Path(root) / f"{name}.onnx"),
                options,
                providers=["CPUExecutionProvider"],
            )
            for name in ("text", "sound", "decoder")
        }
        self._frontend = Frontend(self._meta["vocab"])
        self._status("EMA Lightning hazır (ONNX, CPU).")
        return self

    def synthesize(
        self,
        text: str,
        language_id: str | None = None,
        exaggeration=None,
        cfg_weight=None,
        audio_prompt_path=None,
        temperature=None,
        repetition_penalty=None,
        min_p=None,
        top_p=None,
        speed: float = 1.0,
        stop=None,
        progress=None,
    ) -> np.ndarray:
        """Metni seslendir; 48 kHz float32 mono dizi döner.

        Dil, ifade ve klonlama parametreleri yok sayılır: EMA tek dil, tek ses.
        """
        self.load()
        pieces = chunk_text(self._frontend(text), speed)
        if not pieces:
            raise ValueError("Okunacak metin yok.")
        stoi = {char: index for index, char in enumerate(self._meta["vocab"])}
        out: list[np.ndarray] = []
        for index, (piece_text, pause) in enumerate(pieces):
            if stop is not None and stop.is_set():
                raise InterruptedError("Seslendirme durduruldu.")
            if progress:
                progress(f"Parça {index + 1}/{len(pieces)} okunuyor…")
            seed = (SEED * 1_000_003 + index) % 2 ** 63
            out.append(self._piece(piece_text, stoi, speed, seed))
            if pause > 0:
                out.append(np.zeros(int(pause * SAMPLE_RATE), dtype=np.float32))
        if not out:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(out)

    def _piece(self, text: str, stoi: dict, speed: float, seed: int) -> np.ndarray:
        ids = np.array([stoi.get(char, 1) for char in text], dtype=np.int64)
        starts = [
            i for i, char in enumerate(text)
            if char != " " and (i == 0 or text[i - 1] == " ")
        ] or [0]
        bounds = [0] + starts[1:] + [len(text)]
        cw: list[int] = []
        wstart: list[int] = []
        for word, (a, b) in enumerate(zip(bounds, bounds[1:])):
            cw += [word] * (b - a)
            wstart += [a] * (b - a)
        cw_arr = np.array(cw, dtype=np.int64)
        wstart_arr = np.array(wstart, dtype=np.int64)
        hidden, duration = self._sessions["text"].run(None, {"ids": ids[None]})
        fw, cg, fg, _length = _plan(ids, cw_arr, wstart_arr, duration[0], speed)
        rng = np.random.RandomState(seed % (2 ** 32))
        noise = rng.randn(4, len(fw), 64).astype(np.float32)[None]
        (latent,) = self._sessions["sound"].run(
            None,
            {
                "h": hidden,
                "cg": cg[None],
                "fg": fg[None],
                "cw": cw_arr[None],
                "fw": fw[None].astype(np.int64),
                "noise": noise,
            },
        )
        parts: list[np.ndarray] = []
        for start, end in _windows(len(fw)):
            low = max(0, start - CONTEXT)
            high = min(len(fw), end + CONTEXT)
            (audio,) = self._sessions["decoder"].run(
                None,
                {"z": np.ascontiguousarray(latent[:, low:high].transpose(0, 2, 1))},
            )
            parts.append(audio[0, (start - low) * HOP:(end - low) * HOP])
        return np.concatenate(parts)


def write_wav(audio: np.ndarray, path: Path | str, sample_rate: int = SAMPLE_RATE) -> Path:
    """Float32 [-1, 1] diziyi 16-bit PCM WAV olarak yaz."""
    target = Path(path)
    pcm = np.clip(np.asarray(audio, dtype=np.float32), -1.0, 1.0)
    pcm = (pcm * 32767).astype(np.int16)
    with wave.open(str(target), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(sample_rate)
        handle.writeframes(pcm.tobytes())
    return target
