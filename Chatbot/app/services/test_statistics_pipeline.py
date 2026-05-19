import unittest
import re
from datetime import date


class _DummyLLM:
    def generate(self, prompt: str, model=None, options=None) -> str:  # pragma: no cover
        return "chat"


class TestStatisticsPipeline(unittest.TestCase):
    def test_intent_classifier_maps_examples_to_statistics(self):
        from app.services.intent import IntentDetectionService

        svc = IntentDetectionService(llm_client=_DummyLLM())
        examples = [
            "top diagnoses",
            "how many admissions",
            "trend",
            "most common",
            "distribution",
            "counts by",
            "top 5 diagnoses last month",
        ]
        for ex in examples:
            with self.subTest(example=ex):
                self.assertEqual(svc.detect_intent(ex), "statistics")

    def test_parser_top_diagnoses_last_month(self):
        from app.services.statistics.parser import parse_statistics_request

        parsed = parse_statistics_request(
            "What were the top 5 diagnoses last month?",
            reference_date=date(2026, 4, 22),
        )
        self.assertEqual(parsed["metric"], "count")
        self.assertEqual(parsed["entity"], "diagnosis")
        self.assertEqual(parsed["group_by"], "diagnosis")
        self.assertEqual(parsed["top_n"], 5)
        self.assertEqual(parsed["time_range"]["type"], "last_month")
        self.assertEqual(parsed["time_range"]["start_date"], "2026-03-01")
        self.assertEqual(parsed["time_range"]["end_date_exclusive"], "2026-04-01")

    def test_parser_admissions_this_week(self):
        from app.services.statistics.parser import parse_statistics_request

        parsed = parse_statistics_request(
            "How many admissions were there this week?",
            reference_date=date(2026, 4, 22),
        )
        self.assertEqual(parsed["entity"], "admissions")
        self.assertEqual(parsed["intent"], "admissions_count")
        self.assertEqual(parsed["time_range"]["type"], "this_week")
        self.assertEqual(parsed["time_range"]["start_date"], "2026-04-20")
        self.assertEqual(parsed["time_range"]["end_date_exclusive"], "2026-04-23")

    def test_parser_defaults_to_all_time_when_missing_time_range(self):
        from app.services.statistics.parser import parse_statistics_request

        parsed = parse_statistics_request(
            "How many admissions were there?",
            reference_date=date(2026, 4, 22),
        )
        self.assertEqual(parsed["entity"], "admissions")
        self.assertEqual(parsed["intent"], "admissions_count")
        self.assertEqual(parsed["time_range"]["type"], "all_time")
        self.assertEqual(parsed["time_range"]["start_date"], "1900-01-01")
        self.assertEqual(parsed["time_range"]["end_date_exclusive"], "2026-04-23")

    def test_sql_builder_is_aggregate_only(self):
        from app.services.statistics.query_builder import build_statistics_sql, validate_statistics_sql

        parsed = {
            "intent": "top_diagnoses",
            "metric": "count",
            "entity": "diagnosis",
            "group_by": "diagnosis",
            "top_n": 5,
            "time_range": {
                "type": "last_month",
                "start_date": "2026-03-01",
                "end_date_exclusive": "2026-04-01",
            },
        }
        sql, _ = build_statistics_sql(parsed, db_type="sqlite")
        validate_statistics_sql(sql)  # should not raise

        sql_l = sql.lower()
        self.assertIn("count(*)", sql_l)
        self.assertIn("from patient_diagnoses", sql_l)
        self.assertIn("left join icd_diagnosis", sql_l)
        self.assertIn("group by", sql_l)
        self.assertIn("order by", sql_l)
        self.assertIn("limit 5", sql_l)
        self.assertNotIn("select *", sql_l)
        self.assertIsNone(re.search(r"\\bfrom\\s+patients\\b", sql_l))

    def test_sql_builder_all_time_skips_date_predicate_for_diagnosis(self):
        from app.services.statistics.query_builder import build_statistics_sql, validate_statistics_sql

        parsed = {
            "intent": "top_diagnoses",
            "metric": "count",
            "entity": "diagnosis",
            "group_by": "diagnosis",
            "top_n": 10,
            "time_range": {
                "type": "all_time",
                "start_date": "1900-01-01",
                "end_date_exclusive": "2026-04-27",
            },
        }
        sql, _ = build_statistics_sql(parsed, db_type="postgresql")
        validate_statistics_sql(sql)
        sql_l = sql.lower()
        self.assertIn("from patient_diagnoses", sql_l)
        self.assertNotIn("created_date", sql_l.split("where", 1)[-1])  # no date filters in all_time

    def test_sql_builder_departments_uses_patient_encounters_and_department(self):
        from app.services.statistics.query_builder import build_statistics_sql, validate_statistics_sql

        parsed = {
            "intent": "busiest_departments",
            "metric": "count",
            "entity": "departments",
            "group_by": "department",
            "top_n": 5,
            "time_range": {
                "type": "all_time",
                "start_date": "1900-01-01",
                "end_date_exclusive": "2026-04-27",
            },
        }
        sql, _ = build_statistics_sql(parsed, db_type="postgresql")
        validate_statistics_sql(sql)
        sql_l = sql.lower()
        self.assertIn("from patient_encounters", sql_l)
        self.assertIn("left join department", sql_l)
        self.assertNotIn("from ap_encounter", sql_l)
        self.assertNotIn("ap_department", sql_l)

    def test_sql_builder_postgresql_casts_created_date_to_date(self):
        from app.services.statistics.query_builder import build_statistics_sql, validate_statistics_sql

        parsed = {
            "intent": "top_diagnoses",
            "metric": "count",
            "entity": "diagnosis",
            "group_by": "diagnosis",
            "top_n": 5,
            "time_range": {
                "type": "last_month",
                "start_date": "2026-03-01",
                "end_date_exclusive": "2026-04-01",
            },
        }
        sql, _ = build_statistics_sql(parsed, db_type="postgresql")
        validate_statistics_sql(sql)
        self.assertIn("::date", sql.lower())
        self.assertIn("from patient_diagnoses", sql.lower())
        self.assertIn("left join icd_diagnosis", sql.lower())

    def test_formatter_structure(self):
        from app.services.statistics.formatter import format_statistics_response
        from app.services.statistics.query_builder import StatisticsQueryMeta

        parsed = {
            "intent": "top_diagnoses",
            "metric": "count",
            "entity": "diagnosis",
            "group_by": "diagnosis",
            "top_n": 5,
            "time_range": {"type": "last_month"},
        }
        meta = StatisticsQueryMeta(
            title="Top 5 Diagnoses Last Month",
            visualization_type="bar_chart",
            table_columns=("Diagnosis", "Count"),
            x_label="Diagnosis",
            y_label="Count",
        )
        rows = [{"diagnosis": "Hypertension", "count": 124}]
        out = format_statistics_response(parsed=parsed, rows=rows, meta=meta)
        self.assertEqual(out["mode"], "statistics")
        self.assertIn("title", out)
        self.assertIn("summary", out)
        self.assertIn("visualization", out)
        self.assertIn("table", out)
        self.assertIn("chart_data", out)
        self.assertEqual(out["visualization"]["type"], "bar_chart")
        self.assertEqual(out["table"]["columns"], ["Diagnosis", "Count"])

    def test_service_missing_time_range_defaults_to_all_time(self):
        from app.services.statistics.service import StatisticsService

        class DummyRepo:
            db_type = "sqlite"

            def execute_query(self, sql):  # pragma: no cover
                # Return a minimal top-diagnoses row shape.
                return [{"diagnosis": "X", "count": 1}]

        svc = StatisticsService(hospital_repo=DummyRepo())
        res = svc.handle("top diagnoses", reference_date=date(2026, 4, 22))
        self.assertEqual(res.get("mode"), "statistics")
        self.assertEqual((res.get("data_json") or {}).get("mode"), "statistics")
        self.assertEqual(((res.get("data_json") or {}).get("filters") or {}).get("date_range"), "all_time")

    def test_chat_orchestrator_routes_statistics_mode(self):
        from app.services.chat_orchestrator import ChatOrchestratorService

        class DummySessionMemory:
            def get_session(self, session_id):  # pragma: no cover
                return {}

            def save_session(self, session_id, session):  # pragma: no cover
                return None

        class DummyIntent:
            def detect_intent(self, text, session=None):  # pragma: no cover
                return "statistics"

        class DummyCorrection:
            def correct_spelling_and_enhance_query(self, raw):  # pragma: no cover
                return raw, False

        class DummyAudit:
            def insert_interaction(self, **kwargs):  # pragma: no cover
                return 1

            def update_interaction(self, *args, **kwargs):  # pragma: no cover
                return None

        class DummyStatistics:
            def handle(self, message, **kwargs):  # pragma: no cover
                return {
                    "intent": "statistics",
                    "mode": "statistics",
                    "text": "OK",
                    "data_json": {
                        "mode": "statistics",
                        "title": "Top 5 Diagnoses Last Month",
                        "summary": "OK",
                        "visualization": {"type": "bar_chart"},
                        "table": {"columns": ["Diagnosis", "Count"], "rows": [["X", 1]]},
                        "chart_data": {"x": ["X"], "y": [1]},
                        "filters": {"date_range": "last_month"},
                    },
                }

        orch = ChatOrchestratorService(
            session_memory=DummySessionMemory(),
            intent_service=DummyIntent(),
            correction_service=DummyCorrection(),
            audit_repo=DummyAudit(),
            statistics_service=DummyStatistics(),
        )

        res = orch.process_chat(
            raw_message="top 5 diagnoses last month",
            user_id="u101",
            session_id="s1",
            role="doctor",
            approved=True,
            correction_rejected=False,
        )
        self.assertEqual(res.get("mode"), "statistics")
        self.assertEqual((res.get("data_json") or {}).get("mode"), "statistics")


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
