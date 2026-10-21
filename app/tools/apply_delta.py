"""Delta güncellemeyi yükseltilmiş yetkiyle uygulayan yardımcı.

Uygulama Program Files'ta yönetici olarak çalışmaz; delta dosyalarını oraya
yazmak için bu yardımcı ``runas`` ile başlatılır. Kurulumun dosya kopyalama
işini üstlenir; kayıt defteri ve kısayollara dokunmaz (onlar Setup'ın işi ve
sürümden bağımsızdır).

Kullanım (uygulama tarafından, ShellExecute ``runas`` ile):
    VoxoraStudio.exe --apply-delta <staged_klasör> <hedef_klasör> <sonuç_json>

Bu dosya paket içinde ``_internal/app/tools/`` altına girer; PyInstaller
``app.tools.apply_delta`` modülü olarak da çalıştırılabilir:
    python -m app.tools.apply_delta <staged> <target> <result_json>

Yardımcı, sonucu JSON olarak yazar: {"ok": true, "written": [...]} ya da
{"ok": false, "error": "..."}. Uygulama bu dosyayı bekler.
"""
from __future__ import annotations

import json
import shutil
import sys
import traceback
from pathlib import Path


def _apply(staged: Path, target: Path, manifest_path: Path) -> list[str]:
    """Hazırlanmış dosyaları hedefe taşı (manifest staged içinde)."""
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    written: list[str] = []
    for entry in payload.get("files") or []:
        name = str(entry["path"])
        relative = Path(*name.replace("\\", "/").split("/"))
        source = staged / relative
        destination = (target / relative).resolve()
        # Güvenlik: hedef klasör dışına yazma yok.
        if target.resolve() not in destination.parents and destination != target.resolve():
            raise SystemExit(f"hedef dışı yol: {name}")
        if not source.is_file():
            raise SystemExit(f"kaynak eksik: {name}")
        destination.parent.mkdir(parents=True, exist_ok=True)
        # Çalışan EXE kendini silemez (WinError 5); aynı birimde yeniden
        # adlandırma izinlidir. Eski kopyayı `.old` yapıp sonra artığı sil.
        stale = destination.with_name(destination.name + ".old")
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                pass
        if destination.exists():
            destination.rename(stale)
        try:
            shutil.move(str(source), str(destination))
        except OSError:
            if stale.exists() and not destination.exists():
                stale.rename(destination)
            raise
        if stale.exists():
            try:
                stale.unlink()
            except OSError:
                pass
        written.append(name)
    for name in payload.get("removed") or []:
        relative = Path(*str(name).replace("\\", "/").split("/"))
        candidate = target / relative
        try:
            candidate.unlink(missing_ok=True)
        except OSError:
            pass
    return written


def main(argv: list[str]) -> int:
    if len(argv) != 4:
        print("kullanım: apply_delta <staged> <target> <result_json>", file=sys.stderr)
        return 2
    staged, target, result_path = Path(argv[1]), Path(argv[2]), Path(argv[3])
    try:
        written = _apply(staged, target, staged / "manifest.json")
        result_path.write_text(
            json.dumps({"ok": True, "written": written}, ensure_ascii=False),
            encoding="utf-8")
        # staged klasörünü BURADA silme: sonuç dosyası onun içinde ve çağıran
        # süreç henüz okumadı. Temizliği çağıran yapar (kendi `finally`'si).
        return 0
    except Exception as exc:  # noqa: BLE001 - sonuç dosyasına yazılır
        try:
            result_path.write_text(
                json.dumps({"ok": False, "error": f"{exc}"}, ensure_ascii=False),
                encoding="utf-8")
        except OSError:
            pass
        print(traceback.format_exc(), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
