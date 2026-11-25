"""English README screenshots for VoxoraStudio (offscreen Qt)."""
import os
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from unittest.mock import patch  # noqa: E402

from PyQt6.QtWidgets import QApplication  # noqa: E402
from PyQt6.QtGui import QFontDatabase, QFont  # noqa: E402

from app import main_window  # noqa: E402
from app.main_window import MainWindow  # noqa: E402


def build_window():
    patches = (
        patch.object(main_window, "load_settings", return_value={"ui_language": "en"}),
        patch.object(main_window, "load_history", return_value=[]),
        patch.object(main_window, "save_settings"),
        patch.object(main_window, "save_history"),
        patch.object(main_window.audio_player, "stop"),
        patch.object(MainWindow, "_init_engine_async", autospec=True),
        patch.object(MainWindow, "_maybe_show_first_run", autospec=True),
    )
    for p in patches:
        p.start()
    return MainWindow()


def main():
    app = QApplication.instance() or QApplication([])
    for _f in ("C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"):
        try:
            QFontDatabase.addApplicationFont(_f)
        except Exception:
            pass
    app.setFont(QFont("Segoe UI", 10))
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs", "screenshots")
    os.makedirs(out, exist_ok=True)
    names = ["01-production", "02-archive", "03-tools", "04-models", "05-settings"]
    win = build_window()
    win.resize(1366, 800)
    win.show()
    app.processEvents()
    time.sleep(0.5)
    for i, name in enumerate(names):
        win._switch_page(i, animate=False)
        app.processEvents()
        time.sleep(0.3)
        win.grab().save(os.path.join(out, f"{name}.png"))
        print("saved", name, flush=True)
    win.close()
    win.deleteLater()
    print("done", flush=True)


if __name__ == "__main__":
    main()
