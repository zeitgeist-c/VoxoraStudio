"""Complete a staged runtime from its recorded distribution dependencies.

Uses an existing isolated engine site-packages plus this interpreter's packages.
Never installs into Python or overwrites a published .vxp. Requires separate
clean (-I -S) import AND synthesis verification before packaging/publication.
"""
from __future__ import annotations

import argparse
import importlib.metadata as metadata
import json
import os
from pathlib import Path
import shutil
import sys
import sysconfig

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

# These entry points are not used by ChatterboxMultilingualTTS.from_local.
# Keep their omission visible rather than silently claiming a pip-complete env.
EXCLUDED = {
    "gradio": "demo web UI, not the local inference API",
    "pre-commit": "development hook runner",
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--destination", type=Path, required=True)
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    source = args.source.resolve()
    dest = args.destination.resolve()
    if not source.is_dir() or (dest.exists() and not args.resume):
        parser.error("source must exist and destination must be new")
    if not dest.exists():
        shutil.copytree(source, dest)
    included = {canonicalize_name(d.metadata["Name"]): d
                for d in metadata.distributions(path=[str(dest)])}
    queue = list(included.values())
    added = []
    mismatches = []
    while queue:
        dist = queue.pop()
        for raw in dist.requires or []:
            req = Requirement(raw)
            if req.marker and not req.marker.evaluate({"extra": ""}):
                continue
            name = canonicalize_name(req.name)
            if name in EXCLUDED:
                continue
            dep = included.get(name)
            if dep is None:
                dep = metadata.distribution(req.name)
                base = Path(dep.locate_file("")).resolve()
                for entry in dep.files or []:
                    src = Path(dep.locate_file(entry)).resolve()
                    try:
                        rel = src.relative_to(base)
                    except ValueError:
                        continue  # console scripts are not runtime imports
                    if "__pycache__" in rel.parts or src.suffix in (".pyc", ".pyo"):
                        continue
                    if not src.is_file():
                        raise RuntimeError(f"Recorded distribution file missing: {src}")
                    target = dest / rel
                    target.parent.mkdir(parents=True, exist_ok=True)
                    if target.is_file() and target.read_bytes() != src.read_bytes():
                        raise RuntimeError(f"Runtime file conflict: {rel}")
                    shutil.copy2(src, target)
                included[name] = dep
                queue.append(dep)
                added.append(f"{dep.metadata['Name']}=={dep.version}")
            if req.specifier and not req.specifier.contains(dep.version):
                mismatches.append(f"{dist.metadata['Name']}: {req}, staged {dep.version}")
    # PyInstaller includes only the standard-library modules reachable by EMA.
    # Optional Torch imports more (e.g. timeit). Ship matching interpreter
    # fallback modules in the optional pack, keeping Torch out of the main app.
    stdlib = Path(sysconfig.get_path("stdlib")).resolve()
    excluded_dirs = {"site-packages", "__pycache__", "test", "tests", "idlelib",
                     "tkinter", "turtledemo", "ensurepip", "venv"}
    for directory, dirs, files in os.walk(stdlib):
        dirs[:] = [name for name in dirs if name not in excluded_dirs]
        for name in files:
            if not name.endswith(".py"):
                continue
            src = Path(directory) / name
            target = dest / src.relative_to(stdlib)
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists() and target.read_bytes() != src.read_bytes():
                raise RuntimeError(f"Standard library conflict: {target}")
            shutil.copy2(src, target)
    native = Path(sys.base_prefix) / "DLLs"
    for src in native.iterdir():
        if src.suffix.lower() in (".pyd", ".dll") and not src.name.startswith("_tkinter"):
            shutil.copy2(src, dest / src.name)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", dest / "PYTHON-LICENSE.txt")
    report = {"added": sorted(added), "excluded": EXCLUDED,
              "stdlib_python": sys.version,
              "existing_version_mismatches": sorted(set(mismatches)),
              "distributions": sorted(f"{d.metadata['Name']}=={d.version}" for d in included.values())}
    (dest.parent / f"{dest.name}-completion.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
