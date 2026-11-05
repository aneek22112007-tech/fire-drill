from pathlib import Path

from samplelib.config import load, repo_root
from samplelib.ops import fn_seed


def test_fn_seed():
    assert fn_seed() == "ok"


def test_version_is_semver():
    text = (repo_root() / "VERSION").read_text(encoding="utf-8").strip()
    parts = text.split(".")
    assert len(parts) == 3
    assert all(part.isdigit() for part in parts)


def test_config_loads():
    config = load()
    assert config["service"] == "sample"
    assert config["environment"] == "staging"
    assert isinstance(config["max_connections"], int)
    assert config["max_connections"] <= 100


