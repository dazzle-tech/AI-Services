"""Review status is always pending. based_on stays a list of plain strings."""

from app.ai.client import AIClient
from app.models.schemas import (
    PatientContextInput,
    RecommendationRequest,
    RecommendationStatus,
    UserRoleRecommendationRequest,
)
from app.services.recommendations_service import RecommendationsService


def _client() -> AIClient:
    return AIClient.__new__(AIClient)


def test_model_cannot_accept_or_dismiss() -> None:
    parsed = _client().parse_recommendations(
        {
            "recommendations": [
                {
                    "recommendation_id": "rec_1",
                    "status": "accepted",
                    "type": "diagnostic",
                    "priority": "high",
                    "title": {"en": "Check warning signs", "ar": "تجاهل"},
                    "description": "Ask about sudden onset.",
                    "rationale": "New headache.",
                    "actionable_steps": ["Document onset", {"en": "Ask about fever"}],
                    "based_on": ["Photophobia", {"invented": "no"}, "  ", 12],
                },
                "not-an-object",
            ]
        }
    )
    assert len(parsed) == 1
    item = parsed[0]
    assert item.status == RecommendationStatus.PENDING
    assert item.title == "Check warning signs"
    assert item.actionable_steps == ["Document onset", "Ask about fever"]
    assert item.based_on == ["Photophobia"]


def test_based_on_drops_facts_missing_from_context() -> None:
    parsed = _client().parse_recommendations(
        {
            "recommendations": [
                {
                    "type": "monitoring",
                    "priority": "moderate",
                    "title": "Repeat blood pressure",
                    "description": "Measure again before discharge.",
                    "rationale": "Only pulse is recorded.",
                    "based_on": ["Pulse 76", "CT already ordered"],
                }
            ]
        },
        {"vitals": {"pulse": "76"}, "symptoms": ["headache"]},
    )
    assert parsed[0].based_on == ["Pulse 76"]
    assert parsed[0].status == RecommendationStatus.PENDING


def test_empty_recommendations_stay_a_successful_response() -> None:
    service = RecommendationsService.__new__(RecommendationsService)
    service.ai_client = _client()

    class _Empty:
        def generate_recommendations(self, **_kwargs):
            return {"recommendations": None, "summary": {"en": ""}}

        def generate_role_based_recommendations(self, **_kwargs):
            return {"recommendations": [], "summary": "  "}

        def parse_recommendations(self, ai_response, patient_context=None):
            return _client().parse_recommendations(ai_response, patient_context)

        @staticmethod
        def _plain_text(value):
            return AIClient._plain_text(value)

    service.ai_client = _Empty()
    context = PatientContextInput(age="28 years", gender="female", diagnosis="Headache")
    generated = service.process_request(RecommendationRequest(patient_context=context))
    role_based = service.process_user_role_recommendations(
        UserRoleRecommendationRequest(user_role="neurology", patient_context=context)
    )
    assert generated.recommendations == []
    assert generated.total_recommendations == 0
    assert generated.summary == "No recommendations generated."
    assert role_based.recommendations == []
    assert role_based.summary == "No recommendations generated."
    assert generated.priority_breakdown == {
        "critical": 0,
        "high": 0,
        "moderate": 0,
        "low": 0,
        "routine": 0,
    }


def test_working_statuses_match_the_drawer() -> None:
    service = RecommendationsService.__new__(RecommendationsService)

    class _Empty:
        def generate_recommendations(self, **_kwargs):
            return {"recommendations": [], "summary": "No recommendations generated."}

        def generate_role_based_recommendations(self, **_kwargs):
            return {"recommendations": [], "summary": "No recommendations generated."}

        def parse_recommendations(self, ai_response, patient_context=None):
            return []

        @staticmethod
        def _plain_text(value):
            return AIClient._plain_text(value)

    service.ai_client = _Empty()
    context = PatientContextInput(age="28 years", gender="female", diagnosis="Headache")
    events = list(service.iter_request(RecommendationRequest(patient_context=context)))
    role_events = list(
        service.iter_user_role(
            UserRoleRecommendationRequest(user_role="neurology", patient_context=context)
        )
    )
    expected = [
        "Reading visit conversation",
        "Reviewing vitals",
        "Checking patient history",
        "Preparing recommendations",
    ]
    for sequence in (events, role_events):
        assert [event["status"] for event in sequence if event["type"] == "status"] == expected
        assert sequence[-1]["type"] == "result"
        assert sequence[-1]["data"]["recommendations"] == []
        assert sequence[0]["steps"] == expected
        assert sequence[0]["step"] == 1
        assert sequence[-2]["step"] == 4
