"""Kurulum paketi (setup.exe) üzerinden kendini güncelleme.

Akış:
  1. ``check_for_update`` → GitHub'daki en yeni sürümü ve ``VoxoraStudio-X.Y.Z-Setup.exe``
     asset'ini bulur (public ayna repo ``VoxoraStudio``).
  2. ``download`` → kurulumu ``%LOCALAPPDATA%\\VoxoraStudio\\updates``e indirir,
     boyut + SHA-256 doğrular. Doğrulanmamış dosya asla çalıştırılmaz.
  3. ``spawn_installer`` → Inno Setup'ı sessiz kipte çalıştırır. Kurulum,
     çalışan uygulamayı Restart Manager ile düzgünce kapatır, program
     klasöründeki eski dosyaları silip yenilerini yazar, kısayolları yeniler.
  4. Kurulum ``/RESTARTAPPLICATIONS`` ile programı yeniden başlatır.

Neden setup: eski akış ZIP'i kardeş klasöre açıp eski klasörü siliyordu; bu
her sürümde 1.3 GB'lık ikinci bir kopya ve 540 MB indirme demekti. Setup
yerinde günceller: 0.5.4 → 0.5.5 arasında yalnız 3 dosya değişmişti.

Kullanıcı verisi (``%LOCALAPPDATA%\\VoxoraStudio``) ve Hugging Face model
önbelleği (``%USERPROFILE%\\.cache\\huggingface``) program klasörünün dışında
olduğu için güncelleme onlara dokunmaz; modeller yeniden indirilmez.
"""
from __future__ import annotations
from i18n import t, set_language as ui_set_language, language as ui_language, LANGUAGES as UI_LANGUAGES

import ctypes
import hashlib
import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import urllib.error
import urllib.request
from collections import deque
from dataclasses import dataclass
from pathlib import Path, PurePosixPath

from .branding import TECHNICAL_NAME, __version__

RELEASE_REPO = "zeitgeist-c/VoxoraStudio"
API_LATEST = f"https://api.github.com/repos/{RELEASE_REPO}/releases/latest"
USER_AGENT = f"{TECHNICAL_NAME}/{__version__}"
UPDATES_DIRNAME = "updates"
INSTALLER_SUFFIX = "-Setup.exe"
DELTA_SUFFIX = "-delta.vxd"
#: Delta asset adı: ``VoxoraStudio-<hedef>-delta-<taban>.vxd``
DELTA_RE = re.compile(
    rf"^{re.escape(TECHNICAL_NAME)}-(?P<target>\d+\.\d+\.\d+)-delta-"
    rf"(?P<base>\d+\.\d+\.\d+)\.vxd$")

#: Kurulum dosyası adı: ``VoxoraStudio-0.6.0-Setup.exe``
INSTALLER_RE = re.compile(
    rf"^{re.escape(TECHNICAL_NAME)}-(\d+\.\d+\.\d+){re.escape(INSTALLER_SUFFIX)}$")

#: Sessiz kurulum bayrakları. ``/RESTARTAPPLICATIONS`` uygulamayı geri açar;
#: ``/NORESTART`` Windows'u yeniden başlatma teklifini engeller.
SILENT_FLAGS = (
    "/VERYSILENT",
    "/SUPPRESSMSGBOXES",
    "/NORESTART",
    "/RESTARTAPPLICATIONS",
    "/CLOSEAPPLICATIONS",
)

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
    sha256: str          # beklenen özet; yayında yoksa ""
    size: int
    page_url: str
    #: Aynı sürüm için delta paketi (varsa ve bu kuruluma uyuyorsa).
    delta_name: str = ""
    delta_url: str = ""
    delta_sha256: str = ""
    delta_size: int = 0
    #: Yayında bu kurulumun sürümünü taban alan delta var mı?
    delta_base: str = ""


def updates_possible() -> bool:
    """Güncelleme akışı kaynak kopyada değil, kurulu (donmuş) uygulamada anlamlı."""
    return bool(getattr(sys, "frozen", False))


def package_root() -> Path:
    """Çalışan paketin kökü (kuruluysa Program Files altındaki klasör)."""
    from .paths import package_root as _root

    return _root()


def install_root() -> Path:
    """Kurulumun yazdığı program klasörü."""
    from .paths import package_root as _root

    return _root()


def state_dir() -> Path:
    """Uygulamanın güncel state klasörü (kullanıcı veri kökü altında)."""
    from .paths import state_dir as _state

    return _state()


def updates_dir() -> Path:
    """İndirilen kurulum dosyalarının geçici yeri."""
    from .paths import updates_dir as _updates

    return _updates()


def parse_version(text: str) -> tuple:
    """'v0.3.10' / '0.3.10-beta' -> (0, 3, 10); sayısal olmayan kuyruk durur."""
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(text or ""))
    if not match:
        raise UpdateError(t("Sürüm numarası çözümlenemedi: {text!r}", text=text))
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


def parse_release(payload: dict, version_prefix: str = "v",
                  current_version: str = "") -> UpdateInfo:
    """/releases/latest yanıtından Setup ve (varsa) delta asset'ini seç.

    Bu sürümden itibaren güncelleme ya kurulum dosyasıyla ya da delta ile
    yapılır; ZIP asset'i bilinçli olarak yok sayılır.

    Delta, dosya adından taban sürümü okunarak eşleştirilir:
    ``VoxoraStudio-<hedef>-delta-<taban>.vxd``. Yayın notlarında taban
    belirtilmediyse ``delta_base`` boş kalır ve delta kullanılmaz (tam setup).
    """
    tag = str(payload.get("tag_name") or "")
    version = tag[len(version_prefix):] if tag.startswith(version_prefix) else tag
    parse_version(version)  # karşılaştıramayacağımız etiketi baştan reddet
    wanted = f"{TECHNICAL_NAME}-{version}{INSTALLER_SUFFIX}"
    info: UpdateInfo | None = None
    for asset in payload.get("assets") or []:
        if asset.get("name") != wanted:
            continue
        digest = str(asset.get("digest") or "")
        info = UpdateInfo(
            version=version,
            asset_name=wanted,
            download_url=str(asset.get("browser_download_url") or ""),
            sha256=digest.split(":", 1)[1] if ":" in digest else digest,
            size=int(asset.get("size") or 0),
            page_url=str(payload.get("html_url") or ""),
        )
        break
    if info is None:
        raise UpdateError(t("Yayınlanan en yeni sürümde {wanted} kurulum dosyası yok.", wanted=wanted))
    _attach_delta(info, payload, version, current_version)
    return info


def _attach_delta(info: UpdateInfo, payload: dict, version: str,
                  current_version: str) -> None:
    """Sürümün delta asset'i bu kuruluma uyuyorsa bilgileri ekle.

    Dosya adı kalıbı: ``VoxoraStudio-<hedef>-delta-<taban>.vxd``. Delta yalnız
    taban sürümü tam olarak eşleşen kurulumlarda kullanılır; aksi hâlde tam
    setup iner (yanlış taban = bozuk kurulum riski).
    """
    if not current_version:
        return
    for asset in payload.get("assets") or []:
        match = DELTA_RE.match(str(asset.get("name") or ""))
        if not match:
            continue
        if match.group("target") != str(version):
            continue
        if match.group("base") != str(current_version):
            continue
        digest = str(asset.get("digest") or "")
        info.delta_name = str(asset.get("name"))
        info.delta_url = str(asset.get("browser_download_url") or "")
        info.delta_sha256 = digest.split(":", 1)[1] if ":" in digest else digest
        info.delta_size = int(asset.get("size") or 0)
        info.delta_base = match.group("base")
        return


def fetch_latest(current_version: str = "") -> UpdateInfo:
    request = urllib.request.Request(API_LATEST, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise UpdateError(t("Güncelleme sunucusuna ulaşılamadı.")) from exc
    return parse_release(payload, current_version=current_version)


def check_for_update(current: str) -> UpdateInfo | None:
    info = fetch_latest(current_version=current)
    return info if is_newer(info.version, current) else None


def download_delta(info: UpdateInfo, dest: Path, progress=None, cancel=None,
                   phase=None) -> Path:
    """Delta paketini indir ve doğrula (``download``in delta karşılığı)."""
    if not info.delta_url:
        raise UpdateError(t("Bu sürüm için delta paketi yok."))
    delta_info = UpdateInfo(
        version=info.version,
        asset_name=info.delta_name,
        download_url=info.delta_url,
        sha256=info.delta_sha256,
        size=info.delta_size,
        page_url=info.page_url,
    )
    return download(delta_info, dest, progress=progress, cancel=cancel,
                    phase=phase)


def _sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download(info: UpdateInfo, dest: Path, progress=None, cancel=None,
             phase=None) -> Path:
    """Kurulum dosyasını dest'e akıt; boyut ve SHA-256 doğrulanmadan dosya kalmaz.

    Yarım ya da oynanmış dosya çalıştırılamaz; doğrulama hatası ya da iptal
    dosyayı siler. `cancel`, ilerleme geri çağrısının yokladığı threading.Event.
    `phase` verilirse "verify" ile özet doğrulamasının başladığını duyurur.
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
        raise UpdateError(t("Güncelleme indirmesi yarıda kesildi.")) from exc
    if cancel is not None and cancel.is_set():
        dest.unlink(missing_ok=True)
        raise UpdateError("indirme iptal edildi")
    if info.size and written != info.size:
        dest.unlink(missing_ok=True)
        raise UpdateError(t("İndirme dosya tamamlanmadan bitti."))
    if info.sha256:
        if phase:
            phase("verify")
        actual = _sha256_of(dest)
        if actual.lower() != info.sha256.lower():
            dest.unlink(missing_ok=True)
            raise UpdateError(t("İndirilen dosyanın sağlama toplamı uyuşmuyor."))
    else:
        log.warning("Kurulum dosyası için SHA-256 yayınlanmamış: %s", info.asset_name)
    return dest


def _member_is_safe(name: str) -> bool:
    """ZIP girdisi güvenli mi (eski ZIP akışından kalan genel yardımcı)."""
    parts = PurePosixPath(str(name).replace("\\", "/")).parts
    if not parts:
        return False
    if str(name).startswith(("/", "\\")) or ".." in parts:
        return False
    if parts[0][:1] == "/" or re.match(r"^[A-Za-z]:", parts[0]):
        return False
    return True


def _relaunch_script_text(setup_pid: int, exe: Path) -> str:
    """Kurulum bitince programı yeniden açan bağımsız bekçi betiği.

    Neden ayrı bekçi: Inno'nun ``[Run]`` girdisi yükseltilmiş kurulumun çocuğu
    olarak başlar ve kurulum süreci kapanınca Windows onu da götürebilir
    (gözlenen davranış: pencere birkaç saniye açılıp kapanıyor). Bekçi ayrı bir
    süreçtir, kurulumun job object'ine bağlı değildir; kurulum PID'i bitene
    kadar bekler, sonra EXE'yi normal kullanıcı olarak başlatır ve kendini siler.

    Bekleme `tasklist` + `ping` ile yapılır: `timeout` gerçek konsol ister,
    `find` PATH'e göre MSYS'in Unix `find`'ine düşebilir.
    """
    return (
        "@echo off\r\n"
        "setlocal\r\n"
        "set /a TRIES=0\r\n"
        ":wait\r\n"
        "set \"FOUND=\"\r\n"
        f'for /f "tokens=2 delims=," %%A in (\'%SystemRoot%\\System32\\tasklist.exe '
        f'/FI "PID eq {setup_pid}" /NH /FO CSV 2^>NUL\') do '
        f'if "%%~A"=="{setup_pid}" set "FOUND=1"\r\n'
        "if not defined FOUND goto launch\r\n"
        "set /a TRIES+=1\r\n"
        "if %TRIES% GEQ 1800 goto launch\r\n"
        "ping -n 2 127.0.0.1 >NUL\r\n"
        "goto wait\r\n"
        ":launch\r\n"
        f'start "" "{exe}"\r\n'
        'del "%~f0"\r\n')


class _SHELLEXECUTEINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_ulong),
        ("fMask", ctypes.c_ulong),
        ("hwnd", ctypes.c_void_p),
        ("lpVerb", ctypes.c_wchar_p),
        ("lpFile", ctypes.c_wchar_p),
        ("lpParameters", ctypes.c_wchar_p),
        ("lpDirectory", ctypes.c_wchar_p),
        ("nShow", ctypes.c_int),
        ("hInstApp", ctypes.c_void_p),
        ("lpIDList", ctypes.c_void_p),
        ("lpClass", ctypes.c_wchar_p),
        ("hkeyClass", ctypes.c_void_p),
        ("dwHotKey", ctypes.c_ulong),
        ("hIconOrMonitor", ctypes.c_void_p),
        ("hProcess", ctypes.c_void_p),
    ]


#: ShellExecuteEx hata kodları (kullanıcıya anlaşılır metin için).
_ERROR_CANCELLED = 1223


def _shell_execute_runas(exe: Path, parameters: str) -> int:
    """Yükseltilmiş kurulumu UAC onayıyla başlat; süreç PID'ini döndür.

    ``subprocess.Popen`` yükseltme isteyen EXE'de ``WinError 740`` verir:
    CreateProcess UAC istemez, ShellExecute ister. Bu yüzden ShellExecuteExW
    ``runas`` fiiliyle çağrılır ve ``SEE_MASK_NOCLOSEPROCESS`` ile süreç
    tanıtıcısı alınıp PID'e çevrilir (bekçi bu PID'i bekler).

    Kullanıcı UAC'yi reddederse ``UpdateError`` yükseltilir; kurulum hiç
    başlamamıştır, uygulama açık kalır.
    """
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    SW_SHOWNORMAL = 1
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = str(exe)
    info.lpParameters = parameters
    info.nShow = SW_SHOWNORMAL

    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        code = ctypes.get_last_error()
        if code == _ERROR_CANCELLED:
            raise UpdateError(
                t("Kurulum için yönetici izni verilmedi. Güncelleme kurulmadı; ") +
                t("dilediğinizde tekrar deneyebilirsiniz."))
        raise UpdateError(t("Kurulum başlatılamadı (ShellExecute hata {code}).", code=code))
    if not info.hProcess:
        raise UpdateError(t("Kurulum başlatıldı ancak süreç tanıtıcısı alınamadı."))
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.GetProcessId.argtypes = [ctypes.c_void_p]
        kernel32.GetProcessId.restype = wintypes.DWORD
        kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
        pid = int(kernel32.GetProcessId(info.hProcess))
        kernel32.CloseHandle(info.hProcess)
    except OSError:
        pid = 0
    return pid


def spawn_installer(installer: Path, restart: bool = True) -> int:
    """Kurulumu sessiz kipte başlat; kurulum PID'ini döndür.

    Kurulum Restart Manager ile çalışan uygulamayı kapatır (CloseApplications),
    dosyaları yerinde günceller, kısayolları yeniler. ``restart`` verilirse
    ayrıca bağımsız bir bekçi kurulur: kurulum bitince programı yeniden açar
    (bkz. `_relaunch_script_text`). Bu işlev döndükten sonra uygulama
    kapanmaya hazır olmalıdır; kurulum onu bekler.

    Program Files'a yazan kurulum yükseltme ister; bu yüzden ShellExecute
    ``runas`` kullanılır ve her güncellemede Windows bir kez onay sorar.
    """
    if not installer.is_file():
        raise UpdateError(t("Kurulum dosyası bulunamadı: {installer}", installer=installer))
    flags = list(SILENT_FLAGS)
    if not restart:
        flags = [flag for flag in flags if flag != "/RESTARTAPPLICATIONS"]
    if sys.platform != "win32":  # pragma: no cover - Windows dışı yalnız test
        creation = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        process = subprocess.Popen([str(installer), *flags],
                                   creationflags=creation, close_fds=True)
        return process.pid
    pid = _shell_execute_runas(installer, " ".join(flags))
    log.info("Kurulum başlatıldı: pid=%s %s %s", pid, installer, " ".join(flags))
    if restart:
        spawn_relaunch_watchdog(pid)
    return pid


def spawn_relaunch_watchdog(setup_pid: int) -> Path | None:
    """Kurulum bitince programı açan bekçi betiğini kur (ayrı süreç).

    Betik geçici klasöre yazılır (Program Files'a yazma izni gerekmez) ve
    kendini siler. ``DETACHED_PROCESS`` ile kurulumun job object'inden ayrılır;
    ``CREATE_NO_WINDOW`` ile birlikte verilemez (WinError 87).
    """
    from .paths import package_root

    exe = package_root() / "VoxoraStudio.exe"
    if not exe.is_file():
        log.warning("Bekçi kurulamadı: EXE yok (%s)", exe)
        return None
    try:
        folder = Path(tempfile.gettempdir())
        script = folder / f"voxora-relaunch-{setup_pid}.bat"
        script.write_text(_relaunch_script_text(setup_pid, exe), encoding="ascii")
        detached = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=detached,
                         close_fds=True, cwd=str(folder))
    except OSError:
        log.exception("Yeniden başlatma bekçisi kurulamadı")
        return None
    log.info("Yeniden başlatma bekçisi hazır: %s (kurulum pid=%s)", script, setup_pid)
    return script


def cleanup_updates_dir() -> str:
    """İndirilen kurulum kalıntılarını sil; kısa sonuç metni döndür.

    Kurulum başladıktan sonra kendi dosyasını silemeyebilir; uygulama bir
    sonraki açılışta bu klasörü temizler. Yalnız bu programın ürettiği
    ``-Setup.exe`` kalıbındaki dosyalar silinir.
    """
    global last_cleanup_result
    folder = updates_dir()
    if not folder.is_dir():
        return ""
    removed: list[str] = []
    for entry in folder.iterdir():
        if not entry.is_file() or not INSTALLER_RE.match(entry.name):
            continue
        try:
            entry.unlink()
            removed.append(entry.name)
        except OSError:
            log.warning("İndirme kalıntısı silinemedi: %s", entry)
    if removed:
        last_cleanup_result = t("İndirme kalıntısı silindi.")
        log.info("Güncelleme kalıntıları silindi: %s", ", ".join(removed))
        return last_cleanup_result
    return ""


def run_cleanup_async(on_done=None) -> bool:
    """Kalıntı temizliğini arka planda yap; iş varsa True döndür."""
    folder = updates_dir()
    try:
        if not folder.is_dir():
            return False
        pending = [p for p in folder.iterdir()
                   if p.is_file() and INSTALLER_RE.match(p.name)]
    except OSError:
        return False
    if not pending:
        return False

    def _job():
        cleanup_updates_dir()
        if on_done is not None:
            try:
                on_done()
            except Exception:
                log.exception("Güncelleme temizliği geri çağrısı başarısız")

    threading.Thread(target=_job, name="voxora-update-cleanup",
                     daemon=True).start()
    return True


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


def apply_delta(archive: Path, current_version: str,
                wait_seconds: float = 600.0) -> list[str]:
    """Delta paketini doğrula, hazırla ve **kapanışta** uygulanacak şekilde bırak.

    Neden uygulama sırasında değil: Program Files'taki dosyalar (özellikle
    çalışan ``VoxoraStudio.exe`` ve yüklü DLL'ler) uygulama açıkken kilitlidir;
    Windows bunları ne silmeye ne yeniden adlandırmaya izin verir (WinError 5/32).
    Bu yüzden delta:

      1. Burada doğrulanır ve geçici klasöre çıkarılır (hiçbir şey kilitli değil).
      2. Bir *devir fişi* yazılır: hangi staged klasör, hangi hedef, hangi dosyalar.
      3. Uygulama kapanır; `run_pending_delta` ayrı bir süreçte fişi okur,
         yükseltilmiş yardımcıyla dosyaları yerine yazar ve programı yeniden açar.

    ``apply_delta`` yalnız hazırlık yapar ve fiş yolunu döndürür; yazma işi
    kapanıştadır. Geriye dönük uyum için dönen değer liste değil ``Path``tir —
    çağıran taraf fişi `run_pending_delta` ile tüketir.
    """
    from . import delta as delta_mod

    manifest = delta_mod.read_manifest(archive)
    if not delta_mod.can_apply(manifest, current_version):
        raise UpdateError(
            t(f"Delta paketi sürüm {manifest.base_version} için hazırlanmış; ") +
            t("kurulu sürüm {current_version}. Tam kurulum gerekiyor.", current_version=current_version))
    staged = delta_mod.stage(archive, manifest)
    marker = write_delta_marker(staged, manifest, package_root())
    if marker is None:
        import shutil as _shutil

        _shutil.rmtree(staged, ignore_errors=True)
        raise UpdateError(t("Delta güncelleme fişi yazılamadı."))
    log.info("Delta hazır; kapanışta uygulanacak: %s", marker)
    return [str(marker)]


def write_delta_marker(staged: Path, manifest, root: Path) -> Path | None:
    """Kapanışta okunacak delta fişini yaz (``state/pending_delta.json``)."""
    marker = state_dir() / "pending_delta.json"
    try:
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text(json.dumps({
            "staged": str(staged),
            "target": str(root),
            "version": manifest.version,
            "base_version": manifest.base_version,
            "files": manifest.files,
            "removed": manifest.removed,
        }, ensure_ascii=False, indent=2), encoding="utf-8")
    except OSError:
        log.exception("Delta fişi yazılamadı: %s", marker)
        return None
    return marker


def _safe_delta_path(name: str) -> bool:
    """Delta fişindeki yol tek bir göreli yol mu (``..``, sürücü, UNC yok)."""
    raw = str(name or "")
    normalized = raw.replace("\\", "/")
    if not normalized or normalized.startswith("/"):
        return False
    if re.match(r"^[A-Za-z]:", normalized):
        return False
    parts = PurePosixPath(normalized).parts
    return bool(parts) and ".." not in parts


def validate_pending_delta(payload: dict) -> str:
    """Kapanış fişini doğrula; geçerliyse boş string, değilse hata metni döndür.

    Neden gerekli: ``state/pending_delta.json`` kullanıcının yazabildiği bir
    klasörde durur ve işçi **yönetici olarak** çalışır. Fiş doğrulanmazsa,
    kullanıcı yetkisiyle yazılmış bir fiş yükseltilmiş sürece rastgele dosya
    kopyalatıp sildirebilir (yerel yetki yükseltme). Bu yüzden hedef yalnız
    program klasörü, kaynak yalnız geçici klasör, dosya adları yalnız göreli
    olabilir.
    """
    if not isinstance(payload, dict):
        return t("Delta fişi biçimsiz.")
    staged = Path(str(payload.get("staged") or ""))
    target = Path(str(payload.get("target") or ""))
    if not str(staged) or not str(target):
        return t("Delta fişinde kaynak/hedef eksik.")
    expected_target = package_root().resolve()
    try:
        target_resolved = target.resolve()
    except OSError:
        return t("Delta fişi hedefi çözümlenemedi.")
    if target_resolved != expected_target:
        return t("Delta fişi hedefi program klasörü değil; uygulanmadı.")
    temp_root = Path(tempfile.gettempdir()).resolve()
    try:
        staged_resolved = staged.resolve()
    except OSError:
        return t("Delta fişi kaynağı çözümlenemedi.")
    if staged_resolved != temp_root and temp_root not in staged_resolved.parents:
        return t("Delta fişi kaynağı geçici klasör dışında; uygulanmadı.")
    files = payload.get("files") or []
    if not isinstance(files, list):
        return t("Delta fişinde dosya listesi biçimsiz.")
    for entry in files:
        if not isinstance(entry, dict) or not _safe_delta_path(entry.get("path")):
            return t("Delta fişinde güvensiz yol: {entry!r}", entry=entry)
        digest = str(entry.get("sha256") or "")
        if digest and not re.fullmatch(r"[0-9a-fA-F]{64}", digest):
            return t("Delta fişinde geçersiz sha256: {yol!r}", yol=entry.get('path'))
    for name in payload.get("removed") or []:
        if not _safe_delta_path(name):
            return t("Delta fişinde güvensiz silme yolu: {name!r}", name=name)
    return ""


def run_pending_delta() -> Path | None:
    """Kapanışta delta fişini tüketen bağımsız işçiyi başlat.

    Uygulama kapanmadan önce çağrılır: işçi bu PID'in bitmesini bekler, dosyaları
    yükseltilmiş olarak kopyalar, SHA-256 ile doğrular ve programı yeniden açar.

    **Neden PowerShell, neden EXE değil:** `_internal\base_library.zip` çalışan
    her Python süreci tarafından kilitlenir. Delta bu dosyayı da güncellediği
    için kopyalamayı uygulamanın kendi EXE'siyle yapmak imkânsızdır (bootstrap
    sorunu): süreç kendi kütüphanesini değiştiremez. Bu yüzden kopyalama,
    Python çalıştırmayan bir PowerShell işçisine devredilir.

    Fiş yoksa hiçbir şey yapmaz (None döner).
    """
    import os

    marker = state_dir() / "pending_delta.json"
    if not marker.is_file():
        return None
    exe = package_root() / "VoxoraStudio.exe"
    if not exe.is_file():
        log.warning("Delta işçisi kurulamadı: EXE yok (%s)", exe)
        return None
    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        log.exception("Delta fişi okunamadı: %s", marker)
        return None
    problem = validate_pending_delta(payload)
    if problem:
        # Fiş kullanıcının yazabildiği klasörde: doğrulanmadan yükseltilmiş
        # işçiye verilmez. Bozuk fiş silinir, sonraki açılış temiz başlar.
        log.error("Delta fişi reddedildi: %s", problem)
        marker.unlink(missing_ok=True)
        return None
    result_file = marker.with_name("pending_delta_result.json")
    script = write_delta_worker(payload, marker, result_file, exe, os.getpid())
    if script is None:
        return None
    try:
        detached = getattr(subprocess, "DETACHED_PROCESS", 0)
        subprocess.Popen(["cmd", "/c", str(script)], creationflags=detached,
                         close_fds=True, cwd=str(script.parent))
    except OSError:
        log.exception("Delta işçisi başlatılamadı")
        return None
    log.info("Delta işçisi hazır: %s", script)
    return script


def write_delta_worker(payload: dict, marker: Path, result_file: Path,
                       exe: Path, app_pid: int) -> Path | None:
    """Kapanış işçisini yaz: ``.ps1`` (kopyalar) + ``.bat`` (yükseltir).

    ``.bat`` işçiyi yönetici olarak başlatır (tek UAC), ``.ps1`` uygulamanın
    kapanmasını bekler, dosyaları kopyalar, hash doğrular, sonucu yazar, fişi
    ve geçici klasörü siler, programı normal kullanıcı olarak açar.
    """
    root = Path(tempfile.gettempdir())
    ps1 = root / f"voxora-delta-{app_pid}.ps1"
    bat = root / f"voxora-delta-{app_pid}.bat"
    try:
        ps1.write_text(delta_worker_ps1(payload, marker, result_file, exe,
                                        app_pid), encoding="utf-8")
        bat.write_text(delta_worker_bat(ps1), encoding="ascii")
    except OSError:
        log.exception("Delta işçi betikleri yazılamadı")
        return None
    return bat


def delta_worker_bat(ps1: Path) -> str:
    """İşçiyi yönetici olarak başlatan küçük betik (tek UAC onayı)."""
    return (
        "@echo off\r\n"
        "powershell -NoProfile -WindowStyle Hidden -Command "
        "\"Start-Process -FilePath 'powershell' -ArgumentList '-NoProfile',"
        f"'-ExecutionPolicy','Bypass','-WindowStyle','Hidden','-File','{ps1}' "
        "-Verb RunAs -Wait\"\r\n"
        'del "%~f0"\r\n')


def delta_worker_ps1(payload: dict, marker: Path, result_file: Path,
                     exe: Path, app_pid: int | None) -> str:
    """Kapanış işçisinin PowerShell gövdesi.

    Kopyalama Python çalıştırmaz, bu yüzden ``_internal\base_library.zip``
    kilitli değildir. Her dosya kopyalandıktan sonra SHA-256 ile doğrulanır;
    doğrulama tutmazsa sonuç ``ok:false`` olur.

    ``app_pid`` None ise bekleme döngüsü yazılmaz (uygulama zaten kapalı).
    """
    file_lines = []
    for entry in payload.get("files") or []:
        path = str(entry["path"]).replace("/", "\\")
        digest = str(entry.get("sha256") or "")
        file_lines.append(
            f"  @{{ path = '{_ps_escape(path)}'; "
            f"sha256 = '{_ps_escape(digest)}' }}")
    file_block = ",\n".join(file_lines)
    removed = ", ".join(f"'{_ps_escape(str(name).replace('/', chr(92)))}'"
                        for name in (payload.get("removed") or []))
    wait_block = ""
    if app_pid is not None:
        wait_block = (
            "$deadline = (Get-Date).AddMinutes(10)\n"
            "while ((Get-Date) -lt $deadline) {\n"
            f"  if (-not (Get-Process -Id {app_pid} -ErrorAction SilentlyContinue)) "
            "{ break }\n"
            "  Start-Sleep -Milliseconds 500\n"
            "}\n"
            "Start-Sleep -Seconds 1\n")
    return (
        "$ErrorActionPreference = 'Stop'\n"
        f"$staged = '{_ps_escape(str(payload.get('staged') or ''))}'\n"
        f"$target = '{_ps_escape(str(payload.get('target') or ''))}'\n"
        f"$marker = '{_ps_escape(str(marker))}'\n"
        f"$resultFile = '{_ps_escape(str(result_file))}'\n"
        f"$exe = '{_ps_escape(str(exe))}'\n"
        + wait_block +
        "$files = @(\n" + file_block + "\n)\n"
        f"$removed = @({removed})\n"
        "$written = @()\n"
        "$ok = $true\n"
        "$err = ''\n"
        "try {\n"
        "  foreach ($f in $files) {\n"
        "    $src = Join-Path $staged $f.path\n"
        "    $dst = Join-Path $target $f.path\n"
        "    $dir = Split-Path -Parent $dst\n"
        "    if (-not (Test-Path -LiteralPath $dir)) {\n"
        "      New-Item -ItemType Directory -Path $dir -Force | Out-Null }\n"
        "    if (-not (Test-Path -LiteralPath $src)) {\n"
        "      throw \"kaynak eksik: $($f.path)\" }\n"
        "    # Var olan dosya Once silinir: Copy-Item -Force calisan/kilitli\n"
        "    # hedefe yazamaz, ama silinmis hedefe yeni dosya kopyalanabilir.\n"
        "    if (Test-Path -LiteralPath $dst) {\n"
        "      Remove-Item -LiteralPath $dst -Force\n"
        "    }\n"
        "    Copy-Item -LiteralPath $src -Destination $dst -Force\n"
        "    $hash = (Get-FileHash -LiteralPath $dst -Algorithm SHA256).Hash.ToLower()\n"
        "    if ($f.sha256 -and $hash -ne $f.sha256.ToLower()) {\n"
        "      throw \"dogrulama tutmadi: $($f.path)\" }\n"
        "    $written += $f.path\n"
        "  }\n"
        "  foreach ($r in $removed) {\n"
        "    $p = Join-Path $target $r\n"
        "    if (Test-Path -LiteralPath $p) { Remove-Item -LiteralPath $p -Force }\n"
        "  }\n"
        "  # Silinen dosyalarin bos biraktigi klasorleri temizle (en derinden yukari).\n"
        "  # 0.7.0: torch vb. 5610 dosya silinince 354 bos klasor kaliyordu.\n"
        "  $dirs = New-Object System.Collections.Generic.HashSet[string]\n"
        "  foreach ($r in $removed) {\n"
        "    $d = Split-Path -Parent (Join-Path $target $r)\n"
        "    while ($d -and ($d.Length -gt $target.Length)) {\n"
        "      [void]$dirs.Add($d)\n"
        "      $d = Split-Path -Parent $d\n"
        "    }\n"
        "  }\n"
        "  foreach ($d in $dirs | Sort-Object Length -Descending) {\n"
        "    if (Test-Path -LiteralPath $d) {\n"
        "      if (-not (Get-ChildItem -LiteralPath $d -Force)) {\n"
        "        Remove-Item -LiteralPath $d -Force -ErrorAction SilentlyContinue\n"
        "      }\n"
        "    }\n"
        "  }\n"
        "} catch {\n"
        "  $ok = $false\n"
        "  $err = \"$($_.Exception.Message)\"\n"
        "}\n"
        "@{ ok = $ok; written = $written; error = $err } |\n"
        "  ConvertTo-Json -Depth 4 | Out-String | ForEach-Object {\n"
        "    # BOM'suz UTF-8 yaz: Python json.loads BOM ile patlar.\n"
        "    [System.IO.File]::WriteAllText($resultFile, $_, "
        "(New-Object System.Text.UTF8Encoding $false))\n"
        "  }\n"
        "if ($ok) {\n"
        "  Remove-Item -LiteralPath $marker -Force -ErrorAction SilentlyContinue\n"
        "  # Sonuc dosyasi staged icindeyse silme: cagiran okuyacak.\n"
        "  $inside = $resultFile.StartsWith($staged, "
        "[StringComparison]::OrdinalIgnoreCase)\n"
        "  if (-not $inside) {\n"
        "    Remove-Item -LiteralPath $staged -Recurse -Force "
        "-ErrorAction SilentlyContinue\n"
        "  }\n"
        "}\n"
        "if ($exe -and (Test-Path -LiteralPath $exe)) {\n"
        "  # Programi normal kullanici olarak ac (explorer yukseltilmis kabuktan acar).\n"
        "  Start-Process -FilePath 'explorer.exe' -ArgumentList \"`\"$exe`\"\"\n"
        "}\n"
        "Remove-Item -LiteralPath $PSCommandPath -Force -ErrorAction SilentlyContinue\n")


def _already_elevated() -> bool:
    """Süreç yönetici olarak mı çalışıyor? (UAC'yi tekrar tetiklememek için.)"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except OSError:
        return False


def apply_pending_payload(staged: Path, target: Path, files: list,
                          result_file: Path, wait_pid: int | None = None,
                          exe: Path | None = None) -> bool:
    """İşçiyi yükseltilmiş olarak çalıştır ve sonucu bekle (test/elle onarım).

    Üretimde ``run_pending_delta`` bunu kullanmaz (orada bekçi ayrı süreçtir);
    burada işçi senkron çalıştırılır ki çağıran sonucu hemen görebilsin.
    """
    payload = {"staged": str(staged), "target": str(target),
               "files": files, "removed": []}
    temp = Path(tempfile.gettempdir())
    ps1 = temp / f"voxora-apply-{os.getpid()}.ps1"
    ps1.write_text(delta_worker_ps1(payload, Path(str(result_file) + ".marker"),
                                    result_file, exe or Path(""), wait_pid),
                   encoding="utf-8")
    try:
        if _already_elevated():
            # Çağıran zaten yönetici: UAC tetiklemeden doğrudan çalıştır.
            subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy",
                            "Bypass", "-WindowStyle", "Hidden", "-File",
                            str(ps1)], check=False)
        else:
            _runas(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-WindowStyle", "Hidden", "-File", str(ps1)], wait=True)
    finally:
        ps1.unlink(missing_ok=True)
    for _ in range(300):
        if result_file.is_file():
            break
        import time as _time

        _time.sleep(1)
    if not result_file.is_file():
        return False
    try:
        return bool(json.loads(result_file.read_text(encoding="utf-8-sig")).get("ok"))
    except (OSError, json.JSONDecodeError):
        return False


def _ps_escape(value: str) -> str:
    """PowerShell tek tırnaklı dizesi için kaçış ('' = tek tırnak)."""
    return value.replace("'", "''")


def apply_delta_marker(marker: Path, result_file: Path) -> int:
    """``--apply-delta-marker`` kipi: fişteki deltayı uygula, sonucu yaz.

    Normal akışta kullanılmaz (işçi PowerShell'dir); kaynak kopyada ve testlerde
    kapanış mantığını yalıtmak için elde tutulur.
    """
    import shutil as _shutil

    try:
        payload = json.loads(marker.read_text(encoding="utf-8"))
        problem = validate_pending_delta(payload)
        if problem:
            # Bu kip yükseltilmiş çalışabilir: fiş doğrulanmadan uygulanmaz.
            raise ValueError(problem)
        staged = Path(payload["staged"])
        target = Path(payload["target"])
        result = _apply_marker_payload(staged, target,
                                       payload.get("files") or [],
                                       payload.get("removed") or [])
        result_file.write_text(json.dumps({"ok": True, "written": result},
                                          ensure_ascii=False), encoding="utf-8")
        marker.unlink(missing_ok=True)
        _shutil.rmtree(staged, ignore_errors=True)
        return 0
    except Exception as exc:  # noqa: BLE001 - sonuç dosyasına yazılır
        try:
            result_file.write_text(json.dumps({"ok": False, "error": f"{exc}"},
                                              ensure_ascii=False), encoding="utf-8")
        except OSError:
            pass
        log.exception("Delta fişi uygulanamadı")
        return 1


def _apply_marker_payload(staged: Path, target: Path, files: list,
                          removed: list) -> list[str]:
    """Fişteki dosya listesini yerine yaz."""
    from .delta import DeltaManifest, apply_staged

    manifest = DeltaManifest(
        version="", base_version="",
        files=[dict(item) for item in files],
        removed=[str(name) for name in removed],
        total_bytes=0)
    return apply_staged(staged, manifest, target)
def _runas(argv: list[str], wait: bool = True) -> int:
    """Yardımcıyı UAC onayıyla başlat; süreç PID'ini döndür."""
    import ctypes
    from ctypes import wintypes

    SEE_MASK_NOCLOSEPROCESS = 0x00000040
    if sys.platform != "win32":  # pragma: no cover
        process = subprocess.Popen(argv)
        if wait:
            process.wait()
        return process.pid
    parameters = " ".join(f'"{part}"' for part in argv[1:])
    info = _SHELLEXECUTEINFOW()
    info.cbSize = ctypes.sizeof(info)
    info.fMask = SEE_MASK_NOCLOSEPROCESS
    info.lpVerb = "runas"
    info.lpFile = argv[0]
    info.lpParameters = parameters
    info.nShow = 1
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    shell32.ShellExecuteExW.argtypes = [ctypes.POINTER(_SHELLEXECUTEINFOW)]
    shell32.ShellExecuteExW.restype = wintypes.BOOL
    if not shell32.ShellExecuteExW(ctypes.byref(info)):
        code = ctypes.get_last_error()
        if code == _ERROR_CANCELLED:
            raise UpdateError(
                t("Delta güncelleme için yönetici izni verilmedi. Güncelleme ") +
                t("kurulmadı; dilediğinizde tekrar deneyebilirsiniz."))
        raise UpdateError(t("Delta yardımcısı başlatılamadı (hata {code}).", code=code))
    if not info.hProcess:
        return 0
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.GetProcessId.argtypes = [ctypes.c_void_p]
    kernel32.GetProcessId.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    pid = int(kernel32.GetProcessId(info.hProcess))
    if wait:
        kernel32.WaitForSingleObject.argtypes = [ctypes.c_void_p, wintypes.DWORD]
        kernel32.WaitForSingleObject.restype = wintypes.DWORD
        kernel32.WaitForSingleObject(info.hProcess, 0xFFFFFFFF)  # INFINITE
    kernel32.CloseHandle(info.hProcess)
    return pid
