from __future__ import annotations

import logging
import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from shutil import which

from file_utils import unique_path

log = logging.getLogger(__name__)


def _no_window_flags() -> int:
    """Windows'ta ffmpeg icin ayri bir terminal penceresi olusmasini engeller."""
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


@dataclass
class CompressionResult:
    ok: bool
    input_path: Path
    output_path: Path | None
    original_size: int
    compressed_size: int | None
    ratio: float | None
    duration_seconds: float | None
    codec: str
    bitrate: str
    error: str | None = None


def _bundled_ffmpeg() -> str | None:
    from file_utils import bundled_bin

    return bundled_bin("ffmpeg.exe")


def _ffmpeg_path() -> str:
    bundled = _bundled_ffmpeg()
    if bundled:
        return bundled
    path = which("ffmpeg")
    if path:
        return path
    return "ffmpeg"


def ffmpeg_available() -> bool:
    try:
        subprocess.run(
            [_ffmpeg_path(), "-version"],
            capture_output=True,
            text=True,
            timeout=5,
            creationflags=_no_window_flags(),
        )
        return True
    except Exception:
        return False


def compress_to_opus(
    input_path: str | Path,
    output_path: str | Path | None = None,
    bitrate: str = "48k",
    channels: int = 1,
    output_dir: str | Path | None = None,
) -> CompressionResult:
    input_path = Path(input_path)
    if not input_path.exists():
        return CompressionResult(
            ok=False,
            input_path=input_path,
            output_path=None,
            original_size=0,
            compressed_size=None,
            ratio=None,
            duration_seconds=None,
            codec="libopus",
            bitrate=bitrate,
            error=f"Girdi dosyası bulunamadı: {input_path}",
        )

    try:
        if output_path is None:
            if output_dir:
                target_dir = Path(output_dir)
            else:
                target_dir = input_path.parent
            target_dir.mkdir(parents=True, exist_ok=True)
            output_path = unique_path(target_dir, f"{input_path.stem}.opus")

        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        if input_path.resolve() == output_path.resolve():
            output_path = unique_path(output_path.parent, output_path.name)
        original_size = input_path.stat().st_size
    except Exception as e:
        return CompressionResult(
            ok=False,
            input_path=input_path,
            output_path=None,
            original_size=0,
            compressed_size=None,
            ratio=None,
            duration_seconds=None,
            codec="libopus",
            bitrate=bitrate,
            error=str(e),
        )

    ffmpeg = _ffmpeg_path()
    if not ffmpeg:
        return CompressionResult(
            ok=False,
            input_path=input_path,
            output_path=None,
            original_size=original_size,
            compressed_size=None,
            ratio=None,
            duration_seconds=None,
            codec="libopus",
            bitrate=bitrate,
            error="FFmpeg bulunamadı.",
        )

    cmd = [
        ffmpeg,
        "-y",
        "-i", str(input_path),
        "-vn",
        "-c:a", "libopus",
        "-b:a", bitrate,
        "-vbr", "on",
        "-compression_level", "10",
        "-ac", str(channels),
        str(output_path),
    ]

    start = time.perf_counter()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            creationflags=_no_window_flags(),
        )
        elapsed = time.perf_counter() - start
    except subprocess.TimeoutExpired:
        return CompressionResult(
            ok=False,
            input_path=input_path,
            output_path=None,
            original_size=original_size,
            compressed_size=None,
            ratio=None,
            duration_seconds=None,
            codec="libopus",
            bitrate=bitrate,
            error="FFmpeg zaman aşımı (300 sn).",
        )
    except Exception as e:
        return CompressionResult(
            ok=False,
            input_path=input_path,
            output_path=None,
            original_size=original_size,
            compressed_size=None,
            ratio=None,
            duration_seconds=None,
            codec="libopus",
            bitrate=bitrate,
            error=str(e),
        )

    if result.returncode != 0:
        return CompressionResult(
            ok=False,
            input_path=input_path,
            output_path=output_path if output_path.exists() else None,
            original_size=original_size,
            compressed_size=output_path.stat().st_size if output_path.exists() else None,
            ratio=None,
            duration_seconds=elapsed,
            codec="libopus",
            bitrate=bitrate,
            error=result.stderr.strip() or f"FFmpeg çıkış kodu: {result.returncode}",
        )

    compressed_size = output_path.stat().st_size
    ratio = compressed_size / original_size if original_size > 0 else 0

    return CompressionResult(
        ok=True,
        input_path=input_path,
        output_path=output_path,
        original_size=original_size,
        compressed_size=compressed_size,
        ratio=ratio,
        duration_seconds=elapsed,
        codec="libopus",
        bitrate=bitrate,
    )
