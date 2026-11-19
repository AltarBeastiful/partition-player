"""The helper of the partition-player-fix skill: what it takes as a score address."""
import importlib.util
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location("pp", Path(__file__).parents[2] / "skills" / "partition-player-fix" / "pp.py")
pp = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(pp)


def test_a_score_url_gives_the_site_and_the_job():
    assert pp.parse_target("https://x.example/s/ab12CD", {}) == ("https://x.example", "ab12CD")
    assert pp.parse_target("http://localhost:8000/s/ab12/?x=1", {}) == ("http://localhost:8000", "ab12")


def test_a_bare_id_needs_the_site_address():
    assert pp.parse_target("ab12", {"PP_URL": "https://x.example/"}) == ("https://x.example", "ab12")
    with pytest.raises(SystemExit):
        pp.parse_target("ab12", {})
    with pytest.raises(SystemExit):
        pp.parse_target("https://x.example/other", {})


def test_spans_with_a_words_file_place_words_and_without_check_notes(tmp_path):
    words = tmp_path / "w.txt"
    words.write_text("Lors-que")
    spans = pp.parse_spans([f"0:0:1:{words}", "0:2:3"], "a triplet")
    assert spans[0] == {"staff": 0, "from": 0, "to": 1, "lyrics_source": "Lors-que"}
    assert spans[1] == {"staff": 0, "from": 2, "to": 3, "note": "a triplet"}
