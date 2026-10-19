"""GitHub public ayna reposu (VoxoraStudio-Releases) üzerinden kendi kendini güncelleme.

Kaynak repo özel kalır; sürüm paketleri (yalnız ZIP) public ayna repoya yüklenir,
böylece portable paket token gömmeden "en yeni sürüm ne?" diye sorabilir. GitHub
API public depolarda kimlik sormaz; IP başına hız sınırı günde bir istek için önemsiz.

Bir sürüm kendinden eski her sürümü kapsar: 0.3.4 kurulu makine doğrudan
``releases/latest``e bakar, ara basamakları indirmez.

WordArc'ın update.py kalıbı; fark: tek EXE yerine onedir klasörün ZIP'i iner,
YENİ klasör eskisinin YANINA (kardeş olarak) açılır, çalışan klasöre hiç
dokunulmaz (yarım indirme uygulamayı asla bozamaz). Program yenisiyle
başladıktan sonra eski sürüm klasörleri temizlenir: eski paket, yenisi
açılırken state'e "temizlik fişi" bırakır; yeni sürüm açılışta fişi okuyup
eski `VoxoraStudio-X.Y.Z` klasörlerini siler (kilitliyse sonraki açılışta
yeniden dener).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import shutil
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .branding import TECHNICAL_NAME, __version__

RELEASE_REPO = "zeitgeist-c/VoxoraStudio-Releases"
API_LATEST = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"
USER_AGENT = f"{TECHNICAL_NAME}/{__version__}"
UPDATE_DIRNAME = ".update"
CLEANUP_MARKER = "update_cleanup.json"
VERSION_DIR_RE = re.compile(rf"^{re.escape(TECHNICAL_NAME)}-(\d+)\.(\d+)\.(\d+)$")
log = logging.getLogger(__name__)

#: Açılış temizliğinin sonucu (varsa): durum satırında kullanıcıya gösterilir.
last_cleanup_result = ""


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


class RateMeter:
    """Kayan pencerede indirme hızı (bayt/sn); GUI'ye her tikte canlı değer verir."""

    def __init__(self, window: float = 4.0):
        self._window = window
        self._samples: deque[tuple[float, int]] = deque()

    def add(self, done: int, now: float) -> None:
        self._samples.append((now, done))
        while len(self._samples) > 2 and now - self._samples[0][0] > self._window:
            self._samples.popleft()

    def rate(self) -> float:
        if len(self._samples) < 2:
            return 0.0
        (t0, b0), (t1, b1) = self._samples[0], self._samples[-1]
        elapsed = t1 - t0
        return (b1 - b0) / elapsed if elapsed > 0 else 0.0


def format_bytes(size: float) -> str:
    """İnsan okur boyut: 512 B / 538.4 MB / 1.25 GB."""
    value = float(max(0.0, size or 0.0))
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if unit == "TB" or value < 1024:
            if unit == "B":
                return f"{int(value)} B"
            return f"{value:.2f} {unit}" if value < 10 else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def format_speed(bytes_per_second: float) -> str:
    """İndirme hızı: 12.4 MB/s; henüz ölçülemediyse '—'."""
    if bytes_per_second <= 0:
        return "—"
    return f"{format_bytes(bytes_per_second)}/s"


def format_eta(seconds: float) -> str:
    """Kalan süre: 45 sn / 3 dk 12 sn / 1 sa 05 dk."""
    total = int(max(0, seconds))
    if total < 60:
        return f"{max(1, total)} sn"
    minutes, sec = divmod(total, 60)
    if minutes < 60:
        return f"{minutes} dk {sec:02d} sn"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} sa {minutes:02d} dk"


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


def download(info: UpdateInfo, dest: Path, progress=None, cancel=None,
             phase=None) -> Path:
    """Asset'i dest'e akıt; boyut ve SHA256 doğrulanmadan dosya asla kalmaz.

    Yarım ya da oynanmış dosya program olamaz; doğrulama hatası ya da iptal
    dosyayı siler. `cancel`, ilerleme geri çağrısının yokladığı threading.Event.
    `phase` verilirse "verify" ile özet doğrulamasının başladığını duyurur
    (çok GB'lık pakette hâlâ çalışıyor izlenimi vermemek için).
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
        if phase:
            phase("verify")
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
    yeniden gerektirmez). Eski klasör burada silinmez; yeni sürüm açıldığında
    `cleanup_after_update` tarafından temizlenir.
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


def stale_package_dirs(parent: Path, keep_version: str) -> list[Path]:
    """`parent` altında bu programın, `keep_version`dan eski sürüm klasörleri.

    Yalnız `VoxoraStudio-X.Y.Z` kalıbına uyan klasörler seçilir; keep sürümü ve
    daha yenileri, kalıba uymayan adlar asla listeye girmez.
    """
    keep = parse_version(keep_version)
    stale: list[Path] = []
    try:
        entries = sorted(parent.iterdir())
    except OSError:
        return stale
    for entry in entries:
        if not entry.is_dir() or not VERSION_DIR_RE.match(entry.name):
            continue
        try:
            if parse_version(entry.name) < keep:
                stale.append(entry)
        except UpdateError:
            continue
    return stale


def write_cleanup_marker(new_root: Path, targets) -> Path | None:
    """Yeni paketin state'ine "kurulunca şu eski klasörleri sil" fişi bırak.

    Fişi yeni sürümün kendisi açılışta okur (`cleanup_after_update`); çalışan
    klasöre bu işlem sırasında hiç dokunulmaz. Klasör listesi boşsa fiş yazılmaz.
    """
    target_list = [str(Path(t)) for t in targets]
    if not target_list:
        return None
    try:
        rel_state = state_dir().resolve().relative_to(package_root().resolve())
    except (ValueError, OSError):
        return None
    marker = new_root / rel_state / CLEANUP_MARKER
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(
            json.dumps({"targets": target_list}, ensure_ascii=False, indent=2),
            encoding="utf-8")
    except OSError:
        log.exception("Güncelleme temizlik fişi yazılamadı: %s", marker)
        return None
    return marker


def cleanup_after_update(on_done=None) -> bool:
    """Bekleyen temizlik fişini arka planda uygula; iş varsa True döndür.

    Yeni sürüm açılışında çağrılır. `on_done`, iş bitince başka bir iş
    parçacığında çalışır (GUI tarafı kuyruklu çağrıyla ana iş parçacığına
    taşımalıdır).
    """
    marker = state_dir() / CLEANUP_MARKER
    if not marker.is_file():
        return False

    def _job():
        cleanup_pending(marker)
        if on_done is not None:
            try:
                on_done()
            except Exception:
                log.exception("Güncelleme temizliği geri çağrısı başarısız")

    threading.Thread(target=_job, name="voxora-update-cleanup",
                     daemon=True).start()
    return True


def cleanup_pending(marker: Path) -> tuple[list[str], list[str]]:
    """Fişteki eski paket klasörlerini sil; silinemeyenleri fişte bırak.

    Dönen değer: (silinen_adlar, kalan_yollar). Kalan varsa fiş daraltılıp
    korunur, böylece sonraki açılışta yeniden denenir.
    """
    global last_cleanup_result
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        targets = [Path(str(t)) for t in (payload.get("targets") or [])
                   if str(t or "").strip()]
    except (OSError, json.JSONDecodeError, AttributeError):
        log.warning("Temizlik fişi okunamadı; kaldırıldı: %s", marker)
        marker.unlink(missing_ok=True)
        return [], []
    root = package_root().resolve()
    keep = parse_version(__version__)
    removed: list[str] = []
    remaining: list[str] = []
    for target in targets:
        if not _cleanable_package_dir(target, root, keep):
            continue
        if _remove_tree(target):
            removed.append(target.name)
            log.info("Eski sürüm klasörü silindi: %s", target)
        else:
            remaining.append(str(target))
            log.warning("Eski sürüm klasörü silinemedi (kilit?): %s", target)
    if remaining:
        try:
            marker.write_text(
                json.dumps({"targets": remaining}, ensure_ascii=False, indent=2),
                encoding="utf-8")
        except OSError:
            log.exception("Kalan temizlik fişi yazılamadı: %s", marker)
    else:
        marker.unlink(missing_ok=True)
    if removed:
        last_cleanup_result = "Eski sürüm silindi: " + ", ".join(removed)
    return removed, remaining


def _cleanable_package_dir(target: Path, root: Path, keep: tuple) -> bool:
    """Silme güvenlik kapısı: kardeş, sürümlü ve yenisi GÜNCELDEN küçük olmalı."""
    try:
        target = target.resolve()
    except OSError:
        return False
    if not target.is_dir() or target == root:
        return False
    try:
        if target.parent != root.parent:
            return False
    except OSError:
        return False
    if not VERSION_DIR_RE.match(target.name):
        return False
    try:
        if parse_version(target.name) >= keep:
            return False
    except UpdateError:
        return False
    try:  # iç içe yerleşim artığıysa şu anki paketi yutan klasörü silme
        root.relative_to(target)
        return False
    except ValueError:
        return True


def _remove_tree(target: Path, attempts: int = 3, delay: float = 1.5) -> bool:
    """Klasörü sil; dosya kilidi yüzünden başarısız olursa birkaç kez dene."""
    for attempt in range(attempts):
        try:
            shutil.rmtree(target)
            return True
        except OSError:
            if attempt == attempts - 1:
                return not target.exists()
            time.sleep(delay)
    return False


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


def swap_script_text(old_pid: int, new_launcher: Path) -> str:
    """Kapanış betiği: eski PID'i bekle, yeni paketi başlat, kendini sil.

    PID kontrolü cmd yerleşikleriyle yapılır: `tasklist` her durumda 0 döndürür,
    `find` ise PATH'e göre MSYS'in Unix `find`'iyle karışabilir (eşleşme olmaz,
    betik beklemeyi atlar). Bu yüzden çıktı CSV olarak alınır, PID alanı
    doğrudan karşılaştırılır.

    Bekleme `ping` ile yapılır: `timeout` gerçek konsol/stdin ister; gizli
    konsolda hata verip beklemesiz döngüye yol açar. Döngü ~10 dakikayla
    sınırlıdır; eski süreç kapanmazsa yine de yeni sürüm başlatılır.
    """
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        "set /a TRIES=0\r\n"
        ":wait\r\n"
        "set \"FOUND=\"\r\n"
        f'for /f "tokens=2 delims=," %%A in (\'%SystemRoot%\\System32\\tasklist.exe '
        f'/FI "PID eq {old_pid}" /NH /FO CSV 2^>NUL\') do '
        f'if "%%~A"=="{old_pid}" set "FOUND=1"\r\n'
        "if not defined FOUND goto launch\r\n"
        "set /a TRIES+=1\r\n"
        "if %TRIES% GEQ 600 goto launch\r\n"
        "ping -n 2 127.0.0.1 >NUL\r\n"
        "goto wait\r\n"
        ":launch\r\n"
        f'start "" "{new_launcher}"\r\n'
        'del "%~f0"\r\n')


def spawn_swap(old_pid: int, new_launcher: Path) -> None:
    """Çalışan paketi taze kopyaya devret.

    Windows çalışan EXE'yi silmez; betik bu işlemi bekler, yeni paketi BAT'ıyla
    başlatır, kendini siler. Eski klasörü SİLMEZ: temizlik, yeni sürüm fişi
    okuduğunda (`cleanup_after_update`) eski PID bittikten sonra yapılır.

    Bayraklar: `DETACHED_PROCESS` ile `CREATE_NEW_CONSOLE` BİRLİKTE verilemez;
    Windows CreateProcess'i `WinError 87 (Parametre hatalı)` ile reddeder ve
    güncelleme "yeniden başlatılıyor" adımında asılı kalır. Gizli konsol için
    tek başına `CREATE_NO_WINDOW` kullanılır.
    """
    script = new_launcher.with_name("voxora-swap.bat")
    script.write_text(swap_script_text(old_pid, new_launcher), encoding="ascii")
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
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
