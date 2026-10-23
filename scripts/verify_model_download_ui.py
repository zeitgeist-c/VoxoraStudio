"""Live Qt integration probe; downloads real Chatterbox files into an isolated root.

Run with --data-root <empty-or-resumable-directory> --live-download.
Only settings/history and unrelated startup work are stubbed. The button,
worker, downloader, package verification and model state use production code.
This is an automated offscreen integration check, not a physical desktop test.
"""
from __future__ import annotations

import argparse
from contextlib import ExitStack
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication, QMessageBox
from app import hardware, main_window, model_manager


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-root", type=Path, required=True)
    parser.add_argument("--live-download", action="store_true", required=True)
    args = parser.parse_args()
    root = args.data_root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = QApplication(["voxora-live-download-probe"])
    app.setQuitOnLastWindowClosed(False)
    hardware.detect()
    with ExitStack() as stack:
        stack.enter_context(patch("app.paths.user_data_root", return_value=root))
        stack.enter_context(patch.dict(os.environ, {"VOXORA_MODELS_DIR": str(root / "models")}))
        for name, value in (("load_settings", {}), ("load_history", [])):
            stack.enter_context(patch.object(main_window, name, return_value=value))
        for name in ("save_settings", "save_history"):
            stack.enter_context(patch.object(main_window, name))
        for name in ("_init_engine_async", "_maybe_show_first_run", "_update_startup_check", "_run_update_cleanup"):
            stack.enter_context(patch.object(main_window.MainWindow, name))
        stack.enter_context(patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.Yes))
        errors = []
        stack.enter_context(patch.object(main_window.MainWindow, "_show_error", side_effect=lambda *a: errors.append(str(a))))
        window = main_window.MainWindow()
        window.show()
        window._switch_page(3, animate=False)
        card = window._model_cards["chatterbox"]
        print(f"BEFORE: {card['status'].text()}; root={root}", flush=True)
        card["action"].click()
        worker = window._model_worker
        if worker is None:
            print("No worker started (already installed or action unavailable).", flush=True)
            return 1
        observed = []
        worker.progress.connect(lambda done, total, *_: observed.append((done, total)))
        timer = QTimer()
        timer.timeout.connect(lambda: print(f"PROGRESS: {window.status_label.text()}", flush=True))
        timer.start(15000)
        result = {}

        def finish():
            timer.stop()
            state = model_manager.state_for("chatterbox")
            window.engine_combo.setCurrentIndex(window.engine_combo.findData("chatterbox"))
            result.update(
                installed=state.installed, status=card["status"].text(),
                selected=window.engine_combo.currentData(),
                applied=window._engine_name, progress_events=len(observed),
                progress_hidden=not card["progress"].isVisible(), errors=errors,
                cuda_only_download_disabled=not window._model_cards["voxcpm2"]["action"].isEnabled(),
            )
            print(json.dumps(result, ensure_ascii=True), flush=True)
            (root / "ui-result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
            app.quit()

        worker.finished.connect(lambda: QTimer.singleShot(0, finish))
        started = time.monotonic()
        app.exec()
        print(f"ELAPSED: {time.monotonic() - started:.1f}s", flush=True)
        window.deleteLater()
        return 0 if result.get("installed") and result.get("applied") == "chatterbox" and observed and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
