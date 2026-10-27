"""Apply already verified deltas to an explicitly named installation after backup.

Requires the user to approve Windows UAC. Does not launch the application or
alter its user-data directory. Keeps backup, staging and results for recovery.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
from app import delta, updater


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(block)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--probe-root", type=Path, required=True)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--base-version", required=True)
    parser.add_argument("--delta", type=Path, action="append", required=True)
    args = parser.parse_args()
    target = args.target.resolve(strict=True)
    probe = args.probe_root.resolve()
    if probe.exists() or target == probe or target in probe.parents or probe in target.parents:
        parser.error("probe root must be new and separate from installation")
    probe.mkdir(parents=True)
    backup = probe / "backup"
    shutil.copytree(target, backup)
    for original in target.rglob("*"):
        if original.is_file() and digest(original) != digest(backup / original.relative_to(target)):
            raise RuntimeError(f"Backup mismatch: {original}")
    print(f"Verified backup: {backup}", flush=True)
    version = args.base_version
    results = []
    wrapper = ["$ErrorActionPreference = 'Stop'"]
    for index, archive in enumerate(args.delta):
        manifest = delta.read_manifest(archive)
        if not delta.can_apply(manifest, version):
            raise RuntimeError(f"Delta base mismatch: {archive}")
        stage = delta.stage(archive, manifest)
        payload = {"staged": str(stage), "target": str(target),
                   "files": manifest.files, "removed": manifest.removed}
        result = probe / f"result-{index}.json"
        worker = probe / f"worker-{index}.ps1"
        # Keep result inside staging so production cleanup preserves rollback evidence.
        staged_result = stage / "verification-result.json"
        worker.write_text(updater.delta_worker_ps1(
            payload, probe / f"marker-{index}.json", staged_result,
            probe / "do-not-relaunch.exe", None), encoding="utf-8-sig")
        escaped_worker = str(worker).replace("'", "''")
        escaped_result = str(staged_result).replace("'", "''")
        escaped_copy = str(result).replace("'", "''")
        wrapper.extend([
            f"& '{escaped_worker}'",
            f"$r = Get-Content -LiteralPath '{escaped_result}' -Raw | ConvertFrom-Json",
            f"Copy-Item -LiteralPath '{escaped_result}' -Destination '{escaped_copy}'",
            "if (-not $r.ok) { throw $r.error }",
        ])
        results.append(result)
        version = manifest.version
    script = probe / "apply.ps1"
    script.write_text("\n".join(wrapper), encoding="utf-8-sig")
    print("UAC: approve the PowerShell delta worker.", flush=True)
    updater._runas(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                    "-WindowStyle", "Hidden", "-File", str(script)], wait=True)
    for result in results:
        data = json.loads(result.read_text(encoding="utf-8-sig"))
        if not data.get("ok"):
            raise RuntimeError(data)
    expected = args.expected.resolve(strict=True)
    mismatch = []
    count = 0
    for source in expected.rglob("*"):
        if source.is_file():
            count += 1
            dest = target / source.relative_to(expected)
            if not dest.is_file() or digest(source) != digest(dest):
                mismatch.append(str(source.relative_to(expected)))
    report = {"version": version, "compared_files": count, "mismatch": mismatch,
              "backup": str(backup), "target": str(target)}
    (probe / "comparison.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report), flush=True)
    return int(bool(mismatch))


if __name__ == "__main__":
    raise SystemExit(main())
