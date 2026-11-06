import json
import threading
import urllib.error
import urllib.request

import pytest
import yaml

from edash.config import EXAMPLE_CONFIG
from edash.errors import ConfigError
from edash.host.editor import model
from edash.host.editor.server import EditorServer
from edash.render.fonts import Fonts


@pytest.fixture
def example_data():
    return yaml.safe_load(EXAMPLE_CONFIG.read_text(encoding="utf-8"))


def _field(widget, name):
    return next(f for f in model.widget_fields()[widget] if f["name"] == name)


def test_widget_fields_describe_options():
    assert _field("reminder", "every")["kind"] == "duration" and _field("reminder", "every")["required"]
    assert _field("reminder", "days")["kind"] == "weekdays" and _field("reminder", "days")["default"] == "mon-fri"
    assert _field("reminder", "highlight_for")["default"] == "10m"
    assert _field("reminder", "icon")["kind"] == "choice" and "drop" in _field("reminder", "icon")["choices"]
    assert _field("status", "align")["choices"] == ["left", "center", "right"]
    size = _field("text", "size")
    assert (size["kind"], size["nullable"], size["min"], size["max"]) == ("int", True, 6, 300)
    date_format = _field("clock", "date_format")
    assert date_format["nullable"] and date_format["default"] == "default"


def test_render_screen_returns_boxes_for_every_widget(example_data, now):
    reply = model.render_screen(example_data, "main", now, Fonts())
    assert reply["screen"] == "main"
    assert reply["size"] == (800, 480)
    assert len(reply["boxes"]) == len(example_data["screens"][0]["widgets"])
    assert len(reply["grid"]["cols"]) == 12 and len(reply["grid"]["rows"]) == 8
    assert "_away" in reply["screens"]
    assert reply["active_screen"] == "main"


def test_render_screen_falls_back_to_first_screen(example_data, now):
    assert model.render_screen(example_data, "missing", now, Fonts())["screen"] == "main"


def test_render_screen_reports_config_errors(example_data, now):
    example_data["screens"][0]["widgets"][0]["pos"] = [11, 0]
    with pytest.raises(ConfigError, match="exceeds the 12x8 grid"):
        model.render_screen(example_data, "main", now, Fonts())


def test_yaml_round_trip_uses_flow_lists(example_data):
    text = model.dump_yaml(example_data)
    assert "pos: [0, 0]" in text
    assert model.parse_yaml(text) == example_data


def test_save_keeps_a_backup_and_rejects_invalid_data(example_data, tmp_path):
    path = tmp_path / "config.yaml"
    path.write_text("old: true\n", encoding="utf-8")
    model.save_config(example_data, path)
    assert (tmp_path / "config.yaml.bak").read_text(encoding="utf-8") == "old: true\n"
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == example_data

    with pytest.raises(ConfigError):
        model.save_config({"screens": []}, path)
    assert yaml.safe_load(path.read_text(encoding="utf-8")) == example_data


@pytest.fixture
def server(tmp_path):
    srv = EditorServer(EXAMPLE_CONFIG, tmp_path / "config.yaml")
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv
    srv.shutdown()
    srv.server_close()


def _post(server, path, body=None, token=None, host=None):
    request = urllib.request.Request(
        f"http://127.0.0.1:{server.port}{path}",
        data=json.dumps(body or {}).encode(),
        headers={"X-Edash-Token": token if token is not None else server.token, "Content-Type": "application/json"},
    )
    if host:
        request.add_header("Host", host)
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read())


def test_server_requires_token_and_local_host(server):
    for kwargs in ({"token": "wrong"}, {"host": "evil.example:80"}):
        with pytest.raises(urllib.error.HTTPError) as info:
            _post(server, "/api/load", **kwargs)
        assert info.value.code == 403


def test_server_loads_renders_and_saves(server):
    loaded = _post(server, "/api/load")
    assert loaded["path"] == str(server.save_path)
    assert "reminder" in loaded["fields"]

    rendered = _post(server, "/api/render", {"data": loaded["data"], "screen": "idle", "at": "2026-10-19T20:00"})
    assert rendered["screen"] == "idle" and rendered["active_screen"] == "idle"

    assert _post(server, "/api/save", {"data": loaded["data"]}) == {"path": str(server.save_path)}
    assert server.save_path.exists()
    assert _post(server, "/api/save", {"data": {}})["errors"]


def test_server_serves_static_files_only(server):
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=10) as response:
        assert b"eDash Editor" in response.read()
    with pytest.raises(urllib.error.HTTPError) as info:
        urllib.request.urlopen(f"http://127.0.0.1:{server.port}/static/../model.py", timeout=10)
    assert info.value.code == 404
