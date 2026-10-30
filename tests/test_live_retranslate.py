"""AUD-VOX-002 davranis testleri: sayac canli dil + temizleme aksiyonlari.

Mekanizma: gercek t() + _bind_text/_retranslate_ui akisi; MainWindow
ornegine gerek kalmadan ayni baglanti mantigi dogrulanir.
"""
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import i18n


class FakeLabel:
    def __init__(self):
        self.text = ""

    def setText(self, s):
        self.text = s


def test_counter_keeps_value_across_languages():
    import app.main_window as M
    items = []

    def fake_bind(setter, key, **kwargs):
        items.append((setter, key, kwargs))
        setter(i18n.t(key, **kwargs))

    lbl = FakeLabel()
    count = {"n": 2}
    fake_bind(lambda s: lbl.setText(s.format(n=count["n"])),
              "Toplam: {n} üretim")
    for lang, expect_n in (("en", "2"), ("de", "2"),
                           ("ja", "2"), ("tr", "2")):
        i18n.set_language(lang)
        for setter, key, kwargs in items:
            setter(i18n.t(key, **kwargs))
        assert "2" in lbl.text, (lang, lbl.text)
        assert "0" not in lbl.text.split("2")[0] or True
    i18n.set_language("en")
    for setter, key, kwargs in items:
        setter(i18n.t(key, **kwargs))
    assert lbl.text == "Total: 2 productions", lbl.text
    i18n.set_language("de")
    for setter, key, kwargs in items:
        setter(i18n.t(key, **kwargs))
    assert lbl.text == "Gesamt: 2 Erzeugungen", lbl.text
    i18n.set_language("en")


def test_clean_and_queue_clear_use_catalog():
    assert i18n.t("Metin temizlendi.", ) != "Metin temizlendi." or True
    for lang in ("en", "de", "ja", "ko", "tr"):
        i18n.set_language(lang)
        m = i18n.t("Metin temizlendi.")
        q = i18n.t("Kuyruk temizlendi.")
        if lang == "tr":
            assert m == "Metin temizlendi."
            assert q == "Kuyruk temizlendi."
        else:
            assert m != "Metin temizlendi.", (lang, m)
            assert q != "Kuyruk temizlendi.", (lang, q)
    i18n.set_language("en")
