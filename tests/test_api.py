from fastapi.testclient import TestClient

from app.api import app

client = TestClient(app)


def test_health_and_samples():
    assert client.get("/api/health").json()["status"] == "ok"
    samples = client.get("/api/samples").json()
    assert len(samples) == 7


def test_ui_served():
    r = client.get("/")
    assert r.status_code == 200 and "ClaimGuard AI" in r.text


def test_run_sample_and_register():
    r = client.post("/api/samples/CLM-2026-1004/run")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "SIU_INVESTIGATION"
    runs = client.get("/api/claims").json()["runs"]
    assert any(x["run_id"] == body["run_id"] for x in runs)
    assert client.get(f"/api/claims/{body['run_id']}").json()["claim_id"] == "CLM-2026-1004"
    assert "Claim CLM-2026-1004" in client.get(f"/api/claims/{body['run_id']}/report").text


def test_upload(sample_files):
    files = [("files", (p.name, p.read_bytes(), "application/pdf")) for p in sample_files("CLM-2026-1001")]
    r = client.post("/api/claims/upload", files=files)
    assert r.status_code == 200 and r.json()["status"] == "AUTO_APPROVE"


def test_upload_rejects_bad_type():
    r = client.post("/api/claims/upload", files=[("files", ("evil.exe", b"MZ", "application/octet-stream"))])
    assert r.status_code == 415


def test_path_traversal_blocked():
    assert client.get("/api/samples/..%2F..%2Fapp/files/config.py").status_code == 404


def test_workflow_and_model():
    w = client.get("/api/workflow").json()
    assert len(w["agents"]) == 16 and len(w["categories"]) == 9
    assert client.get("/api/model").json()["roc_auc"] > 0.8
