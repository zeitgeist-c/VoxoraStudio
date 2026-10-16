"""GitHub public ayna reposu (VoxoraStudio-Releases) üzerinden kendi kendini güncelleme.

Kaynak repo özel kalır; sürüm paketleri (yalnız ZIP) public ayna repoya yüklenir,
böylece portable paket token gömmeden "en yeni sürüm ne?" diye sorabilir. GitHub
API public depolarda kimlik sormaz; IP başına hız sınırı günde bir istek için önemsiz.

Bir sürüm kendinden eski her sürümü kapsar: 0.3.4 kurulu makine doğrudan
``releases/latest``e bakar, ara basamakları indirmez.

WordArc'ın update.py kalıbı; fark: tek EXE yerine onedir klasörün ZIP'i iner,
YENİ klasör yanına açılır, çalışan klasöre hiç dokunulmaz (yarım indirme
uygulamayı asla bozamaz).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .branding import TECHNICAL_NAME, __version__

RELEASE_REPO = "zeitgeist-c/VoxoraStudio-Releases"
API_LATEST = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"
USER_AGENT = f"{TECHNICAL_NAME}/{__version__}"
UPDATE_DIRNAME = ".update"
log = logging.getLogger(__name__)


class UpdateError(Exception):
    """Kullanıcıya aynen duyurulacak her şey: ağ, biçim, sağlama."""


@dataclass
class UpdateInfo:
    version: str
    asset_name: str
    download_url: str
    sha256: str          # beklenen özet; sürüm yayınlamada yoksa ""
    size: int
    page_url: str


def updates_possible() -> bool:
    """Güncelleme akışı kaynak kopyada değil, paketlenmiş EXE'de anlamlı."""
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Çalışan paketin kökü: frozen'da EXE'nin klasörü, kaynakta depo kökü."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def parse_version(text: str) -> tuple:
    """'v0.3.10' / '0.3.10-beta' -> (0, 3, 10); sayısal olmayan kuyruk durur."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    if not match:
        raise UpdateError(f"Sürüm numarası çözümlenemedi: {text!r}")
    return tuple(int(part) for part in match.groups())


def is_newer(candidate: str, current: str) -> bool:
    return parse_version(candidate) > parse_version(current)


def parse_release(payload: dict, version_prefix: str = "v") -> UpdateInfo:
    """/releases/latest yanıtından ZIP asset'ini seç."""
    tag = str(payload.get("tag_name") or "")
    version = tag[len(version_prefix):] if tag.startswith(version_prefix) else tag
    parse_version(version)  # karşılaştıramayacağımız etiketi baştan reddet
    asset_name = f"{TECHNICAL_NAME}-{version}.zip"
    for asset in payload.get("assets") or []:
        if asset.get("name") != asset_name:
            continue
        digest = str(asset.get("digest") or "")
        return UpdateInfo(
            version=version,
            asset_name=asset_name,
            download_url=str(asset.get("browser_download_url") or ""),
            sha256=digest.split(":", 1)[1] if ":" in digest else digest,
            size=int(asset.get("size") or 0),
            page_url=str(payload.get("html_url") or ""),
        )
    raise UpdateError(f"Yayınlanan en yeni sürümde {asset_name} paketi yok.")


def fetch_latest() -> UpdateInfo:
    request = urllib.request.Request(API_LATEST, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError("Güncelleme sunucusuna ulaşılamadı.") from exc
    return parse_release(payload)


def check_for_update(current: str) -> UpdateInfo | None:
    info = fetch_latest()
    return info if is_newer(info.version, current) else None


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(info: UpdateInfo, dest: Path, progress=None, cancel=None) -> Path:
    """Asset'i dest'e akıt; boyut ve SHA256 doğrulanmadan dosya asla kalmaz.

    Yarım ya da oynanmış dosya program olamaz; doğrulama hatası ya da iptal
    dosyayı siler. `cancel`, ilerleme geri çağrısının yokladığı threading.Event.
    """
    class Cancelled(Exception):
        pass

    request = urllib.request.Request(info.download_url,
                                     headers={"User-Agent": USER_AGENT})
    dest.parent.mkdir(parents=True, exist_ok=True)
    written = 0
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            total = int(response.headers.get("Content-Length") or info.size)
            with dest.open("wb") as out:
                try:
                    while True:
                        chunk = response.read(1024 * 256)
                        if not chunk:
                            break
                        out.write(chunk)
                        written += len(chunk)
                        if progress:
                            progress(written, total)
                        if cancel is not None and cancel.is_set():
                            raise Cancelled()
                except Cancelled:
                    pass
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        dest.unlink(missing_ok=True)
        raise UpdateError("Güncelleme indirmesi yarıda kesildi.") from exc
    if cancel is not None and cancel.is_set():
        dest.unlink(missing_ok=True)
        raise UpdateError("indirme iptal edildi")
    if info.size and written != info.size:
        dest.unlink(missing_ok=True)
        raise UpdateError("İndirme dosya tamamlanmadan bitti.")
    if info.sha256:
        actual = _sha256_of(dest)
        if actual.lower() != info.sha256.lower():
            dest.unlink(missing_ok=True)
            raise UpdateError("İndirilen dosyanın sağlama toplamı uyuşmuyor.")
    return dest


def _member_is_safe(name: str) -> bool:
    parts = PurePosixPath(str(name).replace("\\", "/")).parts
    if not parts:
        return False
    if str(name).startswith(("/", "\\")) or ".." in parts:
        return False
    if parts[0][:1] == "/" or re.match(r"^[A-Za-z]:", parts[0]):
        return False
    return True


def state_dir() -> Path:
    """Uygulamanın güncel state klasörü (frozen onedir'da _internal/state)."""
    from app_state import STATE_DIR
    return Path(STATE_DIR)


def _relocate(value, old_root: Path, new_root: Path) -> tuple[str, tuple[Path, Path] | None]:
    """Eski paketin altındaki yolu yeni pakete çevir; (yeni_değer, (kaynak,hedef))."""
    path = Path(str(value or ""))
    if not str(value or ""):
        return "", None
    try:
        rel = path.resolve().relative_to(old_root.resolve())
    except ValueError:
        return str(path), None
    return str(new_root / rel), (path, new_root / rel)


def migrate_user_data(old_root: Path, new_root: Path, old_state: Path) -> None:
    """Kullanıcı verisini eski paketten yeni pakete taşı.

    state/*.json yeni pakette yoksa kopyalanır (varsa bozulmaz); ayarlarda eski
    paket klasörüne işaret eden yollar yenilerine çevrilir ve işaret ettikleri
    klasör/dosya kopyalanır; models/ taşınır (aynı diskte anlıktır, indirmeyi
    yeniden gerektirmez). Eski klasör silinmez — temizlik kullanıcıya ait.
    """
    rel_state = old_state.resolve().relative_to(old_root.resolve())
    new_state = new_root / rel_state
    new_state.mkdir(parents=True, exist_ok=True)
    for name in ("settings.json", "history.json"):
        src, dst = old_state / name, new_state / name
        if not dst.exists() and src.exists():
            shutil.copy2(src, dst)

    settings_file = new_state / "settings.json"
    if settings_file.exists():
        try:
            settings = json.loads(settings_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            settings = None
        if isinstance(settings, dict):
            changed = False
            for key in ("output_dir", "compress_output_dir",
                        "audio_prompt_path", "voice_prompt_path"):
                old_value = settings.get(key)
                new_value, pair = _relocate(old_value, old_root, new_root)
                if pair is None or new_value == old_value:
                    continue
                src, dst = pair
                try:
                    if src.is_dir():
                        shutil.copytree(src, dst, dirs_exist_ok=True)
                    elif src.is_file():
                        dst.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copy2(src, dst)
                except OSError:
                    log.exception("Güncelleme göçü atlandı: %s -> %s", src, dst)
                    continue
                settings[key] = new_value
                changed = True
            if changed:
                settings_file.write_text(
                    json.dumps(settings, ensure_ascii=False, indent=2),
                    encoding="utf-8")

    for name in ("models", "outputs"):
        src, dst = old_root / name, new_root / name
        if not src.is_dir() or not any(src.iterdir()):
            continue
        try:
            if name == "models" and not dst.exists():
                shutil.move(str(src), str(dst))
            else:
                shutil.copytree(src, dst, dirs_exist_ok=True)
        except OSError:
            log.exception("Güncelleme göçü atlandı: %s", src)


def extract(archive: Path, version: str, into_parent: Path,
            settings_source: Path | None = None,
            state_source: Path | None = None) -> Path:
    """ZIP'i kardeş klasöre aç; başlatıcı yolunu döndür.

    Çalışan klasöre dokunulmaz; hedef klasör zaten varsa (yarım deneme)
    silinip yeniden açılır — asla çalışan bir klasör olamaz, çünkü adı
    sürüm taşır ve şu anki sürüm kendi adını taşıyan klasörden çalışır.
    """
    stem = f"{TECHNICAL_NAME}-{version}"
    target = into_parent / stem
    try:
        zf = zipfile.ZipFile(archive)
    except zipfile.BadZipFile as exc:
        raise UpdateError("İndirilen paket bozuk: ZIP açılamadı.") from exc
    with zf:
        for name in zf.namelist():
            if not _member_is_safe(name):
                raise UpdateError(f"Paket içinde güvensiz yol: {name!r}")
        names = [n.replace("\\", "/") for n in zf.namelist()]
        if not any(n.startswith(f"{stem}/") for n in names):
            raise UpdateError(f"Paket beklenen {stem}/ klasörüyle başlamıyor.")
        if target.exists():
            shutil.rmtree(target)
        zf.extractall(into_parent)

    exe = target / f"{stem}.exe"
    if not exe.is_file():
        raise UpdateError(f"Paket içinde {stem}.exe bulunamadı.")
    if settings_source is not None and state_source is not None:
        migrate_user_data(Path(settings_source), target, Path(state_source))
    launcher = target / f"{stem}.bat"
    return launcher if launcher.is_file() else exe


def spawn_swap(old_pid: int, new_launcher: Path) -> None:
    """Çalışan paketi taze kopyaya devret.

    Windows çalışan EXE'yi silmez; betik bu işlemi bekler, yeni paketi BAT'ıyla
    başlatır, kendini siler. Eski klasör KASITLI olarak silinmez: içinde
    kullanıcı verisi olabilir, temizliği kullanıcı onayıyla kendisi yapar.
    """
    script = new_launcher.with_name("voxora-swap.bat")
    script.write_text(
        "@echo off\r\n"
        ":wait\r\n"
        f'tasklist /FI "PID eq {old_pid}" 2>NUL | find " {old_pid} " >NUL\r\n'
        "if not errorlevel 1 (timeout /t 1 /nobreak >NUL & goto wait)\r\n"
        f'start "" "{new_launcher}"\r\n'
        'del "%~f0"\r\n',
        encoding="ascii")
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | \
        getattr(subprocess, "CREATE_NEW_CONSOLE", 0)
    subprocess.Popen(["cmd", "/c", str(script)], creationflags=flags,
                     close_fds=True)
    log.info("swap hazır: pid=%s new=%s", old_pid, new_launcher)


def last_check_is_old(stamp: str, max_age_seconds: float = 24 * 3600) -> bool:
    """Kayıtlı ISO damga yoksa ya da pencereden eskiyse True."""
    import datetime
    if not stamp:
        return True
    try:
        when = datetime.datetime.fromisoformat(stamp)
    except ValueError:
        return True
    age = (datetime.datetime.now() - when.replace(tzinfo=None)).total_seconds()
    return age > max_age_seconds


def now_stamp() -> str:
    import datetime
    return datetime.datetime.now().isoformat(timespec="seconds")
