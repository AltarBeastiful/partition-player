"""Applying a draft never overwrites an edit made since it was fetched, the measure count stays, the estimate
prices the chosen model, and the Claude Code answers come in over HTTP (ADR 0010: my own edits win)."""
import xml.etree.ElementTree as ET

from test_model_pass import GOOD, SOURCE, FakeModel, body, start


def texts(client, jid):
    xml = client.get(f"/api/jobs/{jid}/score.musicxml").text
    return [t.text for t in ET.fromstring(xml).find("part").iter("text")]


def drafted(settings):
    client, jid = start(settings, FakeModel(GOOD), seed="Lers-que nous è-tions")
    draft = client.post(f"/api/jobs/{jid}/model-pass", json=body(confirm=True)).json()
    return client, jid, draft


def hand_edit_after_fetch(client, jid):
    """The user retypes the lyrics by hand while the draft sits there unapplied."""
    assert client.patch(f"/api/jobs/{jid}/lyrics", json={"verses": ["Hand-que nous è-tions"]}).status_code == 200


def test_a_place_edited_since_the_draft_was_fetched_is_not_overwritten_and_stays_a_proposed_reading(settings):
    client, jid, draft = drafted(settings)
    ids = [c["id"] for c in draft["changes"]]  # the client saw no conflict and ticked everything
    hand_edit_after_fetch(client, jid)
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": ids})
    assert r.status_code == 200
    assert texts(client, jid)[0] == "Hand"  # the hand edit won
    assert texts(client, jid)[3] == "é"  # the other place the model fixed was applied
    state = r.json()
    skipped = state["model_apply"]["skipped"]
    assert len(skipped) >= 1
    by_id = {x["id"].split("-", 1)[1]: x["status"] for x in state["model_readings"]}
    assert all(by_id[s] == "proposed" for s in skipped)
    assert any(v == "accepted" for v in by_id.values())


def test_ticking_a_conflict_knowingly_overwrites_it(settings):
    client, jid, draft = drafted(settings)
    hand_edit_after_fetch(client, jid)
    shown = client.get(f"/api/jobs/{jid}/model-draft").json()["changes"]
    conflicts = [c["id"] for c in shown if c["conflict"]]
    assert conflicts
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in shown], "overwrite": conflicts})
    assert r.status_code == 200 and r.json()["model_apply"]["skipped"] == []
    assert texts(client, jid)[0] == "Lors"


def test_a_lyric_that_was_not_written_is_not_called_accepted(settings):
    client, jid, draft = drafted(settings)
    hand_edit_after_fetch(client, jid)
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in draft["changes"]]}).json()
    accepted = {x["id"].split("-", 1)[1] for x in r["model_readings"] if x["status"] == "accepted"}
    assert not accepted & set(r["model_apply"]["skipped"])


def test_apply_refuses_a_write_that_would_change_the_measure_count(settings, monkeypatch):
    from partition_player.pipeline.lyrics import inject

    client, jid, draft = drafted(settings)
    before = client.get(f"/api/jobs/{jid}/score.musicxml").text
    real = inject.inject

    def losing(part, placements):
        real(part, placements)
        part.remove(part.findall("measure")[-1])

    monkeypatch.setattr(inject, "inject", losing)
    r = client.post(f"/api/jobs/{jid}/model-draft/apply", json={"ticked": [c["id"] for c in draft["changes"]]})
    assert r.status_code == 409 and "measure" in r.json()["error"]
    assert client.get(f"/api/jobs/{jid}/score.musicxml").text == before
    assert client.get(f"/api/jobs/{jid}/model-draft").status_code == 200  # the draft is kept


def test_the_validator_names_a_changed_measure_count():
    import pytest
    from partition_player.model import lyrics_pass

    a = ET.fromstring("<score-partwise><part id='P1'><measure/><measure/></part></score-partwise>")
    b = ET.fromstring("<score-partwise><part id='P1'><measure/></part></score-partwise>")
    lyrics_pass.check_measure_count(a, a)
    with pytest.raises(lyrics_pass.SpanError, match="measure"):
        lyrics_pass.check_measure_count(a, b)


def test_the_estimate_prices_the_model_it_names(settings):
    client, jid = start(settings, FakeModel(GOOD))
    haiku = client.post(f"/api/jobs/{jid}/model-pass", json=body()).json()
    sonnet = client.post(f"/api/jobs/{jid}/model-pass", json=body(larger=True)).json()
    assert haiku["cost_known"] and sonnet["cost_known"]
    assert sonnet["estimated_cost_usd"] > 2 * haiku["estimated_cost_usd"]
    other = client.post(f"/api/jobs/{jid}/model-pass", json=body(route="deepseek")).json()
    assert other["cost_known"] is False and other["estimated_cost_usd"] is None and other["estimated_tokens"] > 0


def test_the_claude_code_answers_can_be_posted_over_http(settings):
    client, jid = start(settings, FakeModel(GOOD))
    answers = {"model": "claude-code-test", "answers": [
        {"span": {"staff": 0, "from": 0, "to": 1, "lyrics_source": SOURCE}, "verse": 1,
         "reply": [{"text": t, "note": n} for t, n in GOOD]}]}
    r = client.post(f"/api/jobs/{jid}/model-pass/import", json=answers)
    assert r.status_code == 200 and r.json()["route"] == {"kind": "claude-code", "model": "claude-code-test"} and r.json()["changes"]
    assert client.get(f"/api/jobs/{jid}/model-draft").json()["id"] == r.json()["id"]
