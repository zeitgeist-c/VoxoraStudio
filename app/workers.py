"""
Voxora Studio - arka plan iş parçacıkları.

Üç bileşen:
  - TqdmProgressBridge: terminal tqdm çıktısını Qt sinyaline çevirir
  - SynthWorker: sentez işlemini UI'ı bloklamadan yapar
  - EngineLoader: motor yükleme uzun sürerse ayrı thread'de çalıştırır
  - CompressWorker: ses sıkıştırma işlemini UI'ı bloklamadan yapar
"""
from __future__ import annotations

import contextlib
import logging
import re
import sys
import threading
import time
from pathlib import Path

from PyQt6.QtCore import QThread, pyqtSignal

import audio_compressor
from tts_engine import TTSEngine

from . import updater

__all__ = ["TqdmProgressBridge", "SynthWorker", "EngineLoader", "CompressWorker", "UpdateWorker"]

log = logging.getLogger(__name__)


class TqdmProgressBridge:
    """Terminale yazılan TQDM ilerlemesini Qt sinyaline çevirir."""

    _PROGRESS_RE = re.compile(r"(\d+)%.*?\|\s*(\d+)/(\d+)\s*\[(\d+:\d+)<(\d+:\d+),\s*([^\]]+/s)\]")

    def __init__(self, emit_progress, chunk_index: int, total_chunks: int, passthrough=None):
        self.emit_progress = emit_progress
        self.chunk_index = chunk_index
        self.total_chunks = total_chunks
        self.passthrough = passthrough
        self._buffer = ""
        self._last_percent = -1

    def write(self, text: str) -> int:
        if not text:
            return 0
        if self.passthrough:
            self.passthrough.write(text)
            self.passthrough.flush()
        self._buffer = (self._buffer + text)[-1200:]
        match = self._PROGRESS_RE.search(self._buffer.replace("\r", "\n"))
        if match:
            percent = int(match.group(1))
            current = int(match.group(2))
            total = int(match.group(3))
            elapsed = match.group(4)
            remaining = match.group(5)
            rate = match.group(6)
            if percent != self._last_percent:
                self._last_percent = percent
                self.emit_progress.emit(
                    self.chunk_index,
                    self.total_chunks,
                    percent,
                    current,
                    total,
                    elapsed,
                    remaining,
                    rate,
                )
        return len(text)

    def flush(self) -> None:
        if self.passthrough:
            self.passthrough.flush()

    def isatty(self) -> bool:
        return bool(self.passthrough and self.passthrough.isatty())


class SynthWorker(QThread):
    """Uzun işlemleri UI'ı bloklamadan arka planda yapar."""

    chunk_started = pyqtSignal(int, int, str)
    sampling_progress = pyqtSignal(int, int, int, int, int, str, str, str)
    chunk_done = pyqtSignal(int, int, float)
    finished_ok = pyqtSignal(object, int)
    cancelled = pyqtSignal(str)
    failed = pyqtSignal(str)

    def __init__(self, engine: TTSEngine, chunks: list[str], settings: dict):
        super().__init__()
        self.engine = engine
        self.chunks = chunks
        self.settings = settings
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        try:
            if not self.chunks:
                self.failed.emit("Boş metin.")
                return

            waves = []
            sr = None
            total = len(self.chunks)
            for index, text_chunk in enumerate(self.chunks, start=1):
                if self._cancel_requested:
                    self.cancelled.emit("Üretim kullanıcı tarafından durduruldu.")
                    return

                self.chunk_started.emit(index, total, text_chunk)
                started_at = time.perf_counter()
                stdout_stream = TqdmProgressBridge(self.sampling_progress, index, total, sys.__stdout__)
                stderr_stream = TqdmProgressBridge(self.sampling_progress, index, total, sys.__stderr__)
                with contextlib.redirect_stdout(stdout_stream), contextlib.redirect_stderr(stderr_stream):
                    raw = self.settings.copy()
                    pause_seconds = float(raw.pop("pause_between_chunks", 0) or 0)
                    allowed = {
                        "language_id", "exaggeration", "cfg_weight", "audio_prompt_path",
                        "temperature", "repetition_penalty", "min_p", "top_p", "speed",
                    }
                    engine_settings = {k: v for k, v in raw.items() if k in allowed}
                    wav, s = self.engine.synthesize(text_chunk, **engine_settings)
                if self._cancel_requested:
                    self.cancelled.emit("Üretim kullanıcı tarafından durduruldu.")
                    return
                elapsed = time.perf_counter() - started_at
                wav_cpu = wav.cpu()
                waves.append(wav_cpu)
                sr = s
                if pause_seconds > 0 and index < total:
                    import torch

                    pause_samples = int(pause_seconds * sr)
                    if pause_samples > 0:
                        waves.append(torch.zeros(wav_cpu.shape[:-1] + (pause_samples,), dtype=wav_cpu.dtype))
                self.chunk_done.emit(index, total, elapsed)

            if sr is None:
                self.failed.emit("Ses örnekleme oranı alınamadı.")
                return

            import torch

            merged = torch.cat(waves, dim=-1)
            self.finished_ok.emit(merged, sr)
        except Exception as e:
            log.exception("Sentez hatası")
            self.failed.emit(str(e))


class EngineLoader(QThread):
    """Model yükleme uzun sürebilir; ayrı thread'de kullanıcıya bildirir."""

    ok = pyqtSignal(object)
    fail = pyqtSignal(str)
    status = pyqtSignal(str)

    def __init__(self, status_callback=None, parent=None):
        super().__init__(parent)
        self._status_callback = status_callback

    def run(self):
        try:
            self._emit("Kurulu donanım ve hızlandırma seçenekleri kontrol ediliyor...")
            engine = TTSEngine(status_callback=self._emit)
            self.ok.emit(engine)
        except Exception as e:
            log.exception("Motor yüklenemedi")
            self.fail.emit(str(e))

    def _emit(self, message: str):
        log.info(message)
        self.status.emit(message)
        if self._status_callback:
            self._status_callback(message)


class CompressWorker(QThread):
    """Ses dosyalarını arka planda sıkıştırır."""

    file_done = pyqtSignal(object)
    all_finished = pyqtSignal()
    cancelled = pyqtSignal()

    def __init__(self, file_paths: list[str], bitrate: str = "48k", channels: int = 1, output_dir: str | None = None):
        super().__init__()
        self.file_paths = file_paths
        self.bitrate = bitrate
        self.channels = channels
        self.output_dir = output_dir
        self._cancel_requested = False

    def request_cancel(self):
        self._cancel_requested = True

    def run(self):
        for path in self.file_paths:
            if self._cancel_requested:
                self.cancelled.emit()
                return
            try:
                result = audio_compressor.compress_to_opus(
                    path, bitrate=self.bitrate, channels=self.channels, output_dir=self.output_dir
                )
            except Exception as exc:
                # QThread.run'dan kaçan istisna süreci sessizce sonlandırır; burada durdurup raporla.
                log.exception("Sıkıştırma sırasında beklenmeyen hata: %s", path)
                result = audio_compressor.CompressionResult(
                    ok=False,
                    input_path=Path(path),
                    output_path=None,
                    original_size=0,
                    compressed_size=None,
                    ratio=None,
                    duration_seconds=None,
                    codec="libopus",
                    bitrate=self.bitrate,
                    error=str(exc),
                )
            self.file_done.emit(result)
        if self._cancel_requested:
            self.cancelled.emit()
            return
        self.all_finished.emit()


class UpdateWorker(QThread):
    """Güncelleme sunucusunu UI'ı bloklamadan sorgular ya da paketi kurar.

    mode="check": sürümü sorar, `checked` yayınlar (None = zaten güncel).
    mode="install": ZIP'i indirir, doğrular, eski paketin YANINA (kardeş
    klasör) açar, eski klasörler için temizlik fişi bırakır, `installed`
    yayınlar. İptal edilen/bozuk indirme asla hedef klasör oluşturmaz.
    """

    checked = pyqtSignal(object)        # UpdateInfo ya da None (zaten güncel)
    failed = pyqtSignal(str)
    progress = pyqtSignal(int, int, float)  # inen bayt, toplam bayt, bayt/sn
    phase = pyqtSignal(str)             # "verify" (özet doğrulama), "extract" (açma)
    installed = pyqtSignal(str, str)    # sürüm, yeni paket başlatıcı yolu

    _PROGRESS_INTERVAL = 0.15           # GUI'ye saniyede ~6 güncelleme yeter

    def __init__(self, current: str, mode: str = "check", info=None, parent=None):
        super().__init__(parent)
        self._current = current
        self._mode = mode
        self._info = info
        self._cancel = threading.Event()
        self._meter = updater.RateMeter()
        self._last_emit = 0.0

    def request_cancel(self):
        self._cancel.set()

    def is_cancelled(self) -> bool:
        return self._cancel.is_set()

    def run(self):
        if self._mode == "install":
            self._install()
            return
        try:
            info = updater.check_for_update(self._current)
        except updater.UpdateError as exc:
            self.failed.emit(str(exc))
            return
        self.checked.emit(info)

    def _install(self):
        info = self._info
        try:
            root = updater.package_root().resolve()
            archive = root / updater.UPDATE_DIRNAME / info.asset_name
            updater.download(info, archive, progress=self._progress,
                             cancel=self._cancel, phase=self.phase.emit)
            self.phase.emit("extract")
            launcher = updater.extract(archive, info.version, root.parent,
                                       settings_source=root,
                                       state_source=updater.state_dir())
            archive.unlink(missing_ok=True)
            new_root = Path(launcher).parent
            targets = updater.stale_package_dirs(new_root.parent, info.version)
            updater.write_cleanup_marker(new_root, targets)
        except updater.UpdateError as exc:
            if self._cancel.is_set():
                log.info("güncelleme indirmesi iptal edildi")
                return
            self.failed.emit(str(exc))
            return
        except Exception as exc:  # disk dolu, izin hatası: GUI'ye raporla
            log.exception("Güncelleme kurulumu başarısız")
            self.failed.emit(f"Güncelleme kurulamadı: {exc}")
            return
        self.installed.emit(info.version, str(launcher))

    def _progress(self, done: int, total: int):
        # Zaman tabanlı yayın: hız/kalan süre göstergesi canlı kalsın ama GUI
        # iş parçacığı 256 KB'lık her parçada boğulmasın.
        now = time.monotonic()
        self._meter.add(done, now)
        if done == total or now - self._last_emit >= self._PROGRESS_INTERVAL:
            self._last_emit = now
            self.progress.emit(done, total, self._meter.rate())
