from types import SimpleNamespace

from edash.host.platform.linux import LinuxPlatform, systemd_unit, udev_rule
from edash.host.platform.windows import WindowsPlatform


def test_udev_rule_matches_gadget_and_ignores_modemmanager():
    rule = udev_rule()
    assert 'ATTRS{idVendor}=="1d6b"' in rule and 'ATTRS{idProduct}=="0104"' in rule
    assert 'ID_MM_DEVICE_IGNORE}="1"' in rule and 'TAG+="uaccess"' in rule
    assert 'SYMLINK+="edash"' in rule


def test_systemd_unit_runs_host(tmp_path):
    unit = systemd_unit(tmp_path / "config.yaml")
    assert "-m edash.host run --config" in unit and "WantedBy=default.target" in unit


def test_linux_sorts_app_interface_first():
    ports = [SimpleNamespace(device="/dev/ttyACM1", location="1-2:1.2"), SimpleNamespace(device="/dev/ttyACM0", location="1-2:1.0")]
    ports.sort(key=LinuxPlatform()._port_sort_key)
    assert ports[0].device == "/dev/ttyACM0"


def test_windows_sorts_com_ports_numerically():
    ports = [SimpleNamespace(device="COM12"), SimpleNamespace(device="COM3")]
    ports.sort(key=WindowsPlatform()._port_sort_key)
    assert [p.device for p in ports] == ["COM3", "COM12"]
