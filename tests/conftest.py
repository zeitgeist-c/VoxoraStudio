"""Çevre skibi: ağır ses/AI bağımlılıkları (sounddevice, soundfile, torch)
kurulu değilse bu modülleri zincirleme içe aktaran UI testleri
koleksiyona alınmaz; iş mantığı testleri çalışmaya devam eder."""

import importlib.util

_ENV_DEPS = ("sounddevice", "soundfile", "torch")

if any(importlib.util.find_spec(m) is None for m in _ENV_DEPS):
    collect_ignore = [
        "test_audit_regressions.py",
        "test_duration_estimate.py",
        "test_engine_selection_ui.py",
        "test_models_ui.py",
        "test_output_format.py",
        "test_paths.py",
        "test_performance_regressions.py",
        "test_queue_split_lines.py",
        "test_trim_leading_silence.py",
        "test_update_install_ui.py",
        "test_voxora_ui.py",
    ]
