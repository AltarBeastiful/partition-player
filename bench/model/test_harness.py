"""Seam 2: the harness end to end on the offline case (scripted route, no keys), and replay of a recording."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import offline  # noqa: E402
from client import MeteredClient, key_of  # noqa: E402
from harness import run_case, summarise, table  # noqa: E402
from partition_player.model.route import Route  # noqa: E402

ROUTE = Route.anthropic("test-key-never-sent", larger_model="")


def test_offline_pass_fixes_one_note_breaks_none_and_rejects_the_bad_operation():
    res = run_case(offline.case(), ROUTE, "fake", lambda m: MeteredClient(m, script=offline.script))
    assert (res.wrong_before, res.fixed, res.broken) == (1, 1, 0)
    assert res.rejections == 1
    assert res.calls == 1 and res.cost is not None


def test_a_model_that_breaks_a_note_fails_the_gate():
    bad = lambda model, prompt: '[{"op": "stepPitch", "measure": 0, "event": 0, "delta": 1}]'  # C4 -> D4: a right note made wrong
    res = run_case(offline.case(), ROUTE, "bad", lambda m: MeteredClient(m, script=bad))
    assert res.broken == 1
    assert "FAIL" in table({"bad": summarise([res])})


def test_the_table_passes_the_gate_when_nothing_is_broken():
    res = run_case(offline.case(), ROUTE, "fake", lambda m: MeteredClient(m, script=offline.script))
    assert "| PASS |" in table({"fake": summarise([res])})


def test_replay_answers_from_a_recording_and_a_miss_is_an_error_not_a_guess():
    case = offline.case()
    from partition_player.model import notes_pass
    prompt = notes_pass.prompt_for(case.engine, case.spans[0])
    reply = {"content": [{"type": "text", "text": "[]"}], "usage": {"input_tokens": 10, "output_tokens": 2}}
    rec = {key_of(ROUTE.model, prompt): reply}
    res = run_case(case, ROUTE, "replay", lambda m: MeteredClient(m, recorded=rec))
    assert (res.fixed, res.broken, res.rejections) == (0, 0, 0) and res.calls == 1
    miss = run_case(case, ROUTE, "miss", lambda m: MeteredClient(m, recorded={}))
    assert miss.calls == 0 and miss.rejections == 1   # recorded as "could not be asked"
