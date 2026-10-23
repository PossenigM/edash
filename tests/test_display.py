import sys
import types

from edash.device.display import WaveshareDisplay


class _FakeEPD:
    width, height = 800, 480


def _fake_driver(monkeypatch, seen):
    import os

    module = types.ModuleType("waveshare_epd.epd7in5_V2")

    def make_epd():
        seen["LG_WD"] = os.environ.get("LG_WD")
        return _FakeEPD()

    module.EPD = make_epd
    package = types.ModuleType("waveshare_epd")
    package.epd7in5_V2 = module
    monkeypatch.setitem(sys.modules, "waveshare_epd", package)
    monkeypatch.setitem(sys.modules, "waveshare_epd.epd7in5_V2", module)


def test_lgpio_gets_a_writable_working_directory(monkeypatch, tmp_path):
    seen = {}
    _fake_driver(monkeypatch, seen)
    monkeypatch.delenv("LG_WD", raising=False)
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    monkeypatch.setattr("tempfile.tempdir", None)

    display = WaveshareDisplay()

    assert seen["LG_WD"] == str(tmp_path)
    assert display.size == (800, 480)


def test_existing_lg_wd_is_kept(monkeypatch):
    seen = {}
    _fake_driver(monkeypatch, seen)
    monkeypatch.setenv("LG_WD", "/run/custom")

    WaveshareDisplay()

    assert seen["LG_WD"] == "/run/custom"
