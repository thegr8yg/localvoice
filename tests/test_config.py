import json

from localvoice.config import Config


def test_roundtrip_and_unknown_keys(tmp_path):
    path = tmp_path / "config.json"
    cfg = Config.load(path)  # creates defaults
    assert path.exists() and cfg.hotkey == "right ctrl"
    data = json.loads(path.read_text())
    data["model"] = "parakeet-v3"
    data["bogus"] = 1
    path.write_text(json.dumps(data))
    assert Config.load(path).model == "parakeet-v3"


def test_corrupt_file_falls_back_to_defaults(tmp_path):
    path = tmp_path / "config.json"
    path.write_text("{nope")
    assert Config.load(path) == Config()
