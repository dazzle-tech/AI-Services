"""API integration tests for ORDisplayPlugin."""

from tests.fixtures.sample_payloads import ANALYZE_AUDIO, CASE_RECORD, full_or_reshape_request


def test_health(client):
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json()["status"] in {"ok", "degraded"}


def test_reshape_does_not_require_headers(client):
    response = client.post("/api/v1/reshape", json=full_or_reshape_request())
    assert response.status_code == 200
    by_id = {item["view_id"]: item for item in response.json()["results"]}
    assert set(by_id) == {
        "or_timeline",
        "or_medications",
        "or_counts",
        "or_checklist",
        "or_roles",
    }
    assert by_id["or_medications"]["data"]["Drugs"] == ["propofol"]
    assert by_id["or_checklist"]["data"]["TimeOutCompleted"] is True


def test_reshape_seeded_view_ids_from_analyze(client):
    response = client.post(
        "/api/v1/reshape",
        json={
            "stage1_output": ANALYZE_AUDIO,
            "context": "operating_room",
            "purpose": "timeline",
            "view_ids": [
                "or_timeline",
                "or_medications",
                "or_counts",
                "or_checklist",
                "or_roles",
            ],
        },
    )
    assert response.status_code == 200
    by_id = {item["view_id"]: item for item in response.json()["results"]}
    assert by_id["or_timeline"]["data"]["EventTypes"] == ["incision", "medication"]
    assert by_id["or_roles"]["data"]["RoleMap"]["SPEAKER_01"]["role"] == "anesthetist"


def test_reshape_case_record_shape(client):
    response = client.post(
        "/api/v1/reshape",
        json={
            "stage1_output": CASE_RECORD,
            "view_ids": ["or_medications", "or_checklist", "or_roles"],
        },
    )
    assert response.status_code == 200
    by_id = {item["view_id"]: item for item in response.json()["results"]}
    assert by_id["or_medications"]["data"]["Doses"] == ["100 mg"]
    assert by_id["or_roles"]["data"]["ProcedureType"] == "laparoscopic cholecystectomy"
    assert by_id["or_checklist"]["data"]["SignOutConfirmed"] == [
        "procedure recorded",
        "specimen labeled",
    ]


def test_register_and_fetch_decoder(client):
    body = {
        "view_id": "or_drugs_only",
        "view_name": "Drugs only",
        "fields": [
            {
                "field_name": "drugs",
                "field_type": "list",
                "source_path": "medications_administered[*].drug",
                "transform": "direct",
                "required": True,
            }
        ],
    }
    created = client.post("/api/v1/decoders", json=body)
    assert created.status_code == 201
    fetched = client.get("/api/v1/decoders/or_drugs_only")
    assert fetched.status_code == 200
    reshape = client.post(
        "/api/v1/reshape",
        json={"stage1_output": ANALYZE_AUDIO, "view_id": "or_drugs_only"},
    )
    assert reshape.status_code == 200
    assert reshape.json()["results"][0]["data"]["drugs"] == ["propofol"]


def test_get_unknown_decoder_404(client):
    response = client.get("/api/v1/decoders/does-not-exist")
    assert response.status_code == 404
