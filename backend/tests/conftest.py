import os
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
GROUND_TRUTH = ROOT / "bench" / "samples" / "anton_yvan_boris_ground_truth.musicxml"
PHOTO = ROOT / "bench" / "samples" / "anton_yvan_boris_photo.jpg"


@pytest.fixture
def settings(tmp_path, monkeypatch):
    monkeypatch.setenv("PP_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("PP_ENGINE", "fake")
    monkeypatch.setenv("PP_FAKE_MUSICXML", str(GROUND_TRUTH))
    monkeypatch.setenv("PP_FRONTEND_DIR", str(tmp_path / "nofrontend"))
    monkeypatch.setenv("PP_MAX_SIDE_PX", "800")
    from partition_player.config import load_settings

    return load_settings()
