"""Reject native binaries collected from unrelated tool runtimes on PATH."""
from __future__ import annotations

import ast
import os
from pathlib import Path
import sys


def main() -> int:
    toc = ast.literal_eval(Path(sys.argv[1]).read_text(encoding="utf-8"))
    allowed = [Path(__file__).resolve().parents[1], Path(sys.base_prefix).resolve(),
               Path(os.environ.get("SystemRoot", r"C:\Windows")).resolve()]
    invalid = []

    def visit(value):
        if isinstance(value, (list, tuple)):
            if len(value) == 3 and value[2] in ("BINARY", "EXTENSION"):
                source = Path(value[1]).resolve()
                if not any(source.is_relative_to(root) for root in allowed):
                    invalid.append(str(source))
            else:
                for item in value:
                    visit(item)

    visit(toc)
    if invalid:
        print("Unrelated native build inputs:\n" + "\n".join(invalid))
        return 1
    print("Native build inputs are restricted to project, Python and Windows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
