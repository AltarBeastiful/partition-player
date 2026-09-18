import time

from fastapi.testclient import TestClient

from conftest import PHOTO


def wait_done(client: TestClient, job_id: str, timeout: float = 30.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "failed"):
            return job
        time.sleep(0.2)
    raise AssertionError("job did not finish")


def test_upload_recognize_download(settings):
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        assert client.get("/api/health").json()["engine"] == "fake"
        r = client.post("/api/jobs", files={"file": ("photo.jpg", PHOTO.read_bytes(), "image/jpeg")})
        assert r.status_code == 202, r.text
        job = wait_done(client, r.json()["id"])
        assert job["status"] == "done", job
        assert job["result"]["stats"]["measures"] == 19
        score = client.get(f"/api/jobs/{job['id']}/score.musicxml")
        assert score.status_code == 200 and b"<score-partwise" in score.content


def test_rejects_non_images(settings):
    from partition_player.api import create_app

    with TestClient(create_app(settings)) as client:
        r = client.post("/api/jobs", files={"file": ("x.txt", b"hello", "text/plain")})
        assert r.status_code == 415
        assert client.get("/api/jobs/nope").status_code == 404
