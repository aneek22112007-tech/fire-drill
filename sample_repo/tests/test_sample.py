from pathlib import Path

from samplelib.config import load, repo_root
from samplelib.ops import fn_seed


def test_fn_seed():
    assert fn_seed() == "ok"


