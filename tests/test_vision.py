import csv
import json
import tempfile
import unittest
from pathlib import Path

import vision


def record(identifier="TEST-001", automatic="Pass", reviewed="Pass", **updates):
    row = {"inspection_id": identifier, "timestamp": "2026-01-15T09:00:00Z",
           "application": "Machining", "station": "DEMO-MACH-01", "camera": "CAM-1",
           "part_id": "DEMO-PART-001", "automatic_result": automatic,
           "reviewed_result": reviewed, "defect_label": "Burr" if reviewed == "Fail" else "None",
           "review_note": "Fictional review"}
    return dict(row, **updates)


class VisionTests(unittest.TestCase):
    def setUp(self):
        self.db = vision.connect(":memory:")

    def tearDown(self):
        self.db.close()

    def test_all_review_outcomes(self):
        cases = [("Pass", "Pass", "Correct pass"), ("Fail", "Fail", "Correct reject"),
                 ("Fail", "Pass", "False reject"), ("Pass", "Fail", "False accept"),
                 ("Pass", "", "Unreviewed"), ("Fail", "", "Unreviewed")]
        for automatic, reviewed, expected in cases:
            self.assertEqual(vision.category(record(automatic=automatic, reviewed=reviewed)), expected)

    def test_demo_has_expected_counts_and_denominators(self):
        vision.import_csv(self.db, vision.ROOT / "sample_inspections.csv")
        report = vision.build_report(self.db)
        s = report["summary"]
        self.assertEqual(s["decisions"], 48)
        self.assertEqual(s["reviewed"], 42)
        self.assertEqual(s["categories"], {"Correct pass": 21, "Correct reject": 12,
                         "False reject": 6, "False accept": 3, "Unreviewed": 6})
        self.assertEqual(s["false_reject_pct_of_reviewed_good"], 22.22)
        self.assertEqual(s["false_accept_pct_of_reviewed_bad"], 20)
        self.assertEqual(s["review_agreement_pct"], 78.57)
        self.assertEqual(s["review_coverage_pct"], 87.5)
        self.assertEqual(s["automatic_fail"], 21)
        for app in vision.APPLICATIONS:
            self.assertEqual(report["by_application"][app]["decisions"], 16)

    def test_unreviewed_is_excluded_from_error_rates(self):
        rows = [record("A", "Fail", "Pass"), record("B", "Pass", "Fail"),
                record("C", "Pass", ""), record("D", "Fail", "")]
        s = vision.summarize(rows)
        self.assertEqual(s["reviewed"], 2)
        self.assertEqual(s["false_reject_pct_of_reviewed_good"], 100)
        self.assertEqual(s["false_accept_pct_of_reviewed_bad"], 100)
        self.assertEqual(s["review_agreement_pct"], 0)

    def test_empty_summary_has_no_invented_percentages(self):
        s = vision.summarize([])
        self.assertEqual(s["decisions"], 0)
        self.assertIsNone(s["review_agreement_pct"])
        self.assertIsNone(s["false_reject_pct_of_reviewed_good"])
        self.assertIsNone(s["false_accept_pct_of_reviewed_bad"])

    def test_all_unreviewed_has_no_agreement(self):
        s = vision.summarize([record(reviewed="")])
        self.assertEqual(s["review_coverage_pct"], 0)
        self.assertIsNone(s["review_agreement_pct"])

    def test_defect_counts_only_use_reviewed_failures(self):
        rows = [record("A", "Fail", "Pass", defect_label="Lighting variation"),
                record("B", "Fail", "Fail"), record("C", "Fail", "", defect_label="Suspected burr")]
        self.assertEqual(vision.summarize(rows)["reviewed_defects"], [{"label": "Burr", "count": 1}])

    def test_reimport_skips_exact_duplicates(self):
        rows = [record(), record("TEST-002")]
        vision.import_rows(self.db, rows)
        self.assertEqual(vision.import_rows(self.db, rows), {"inserted": 0, "duplicates_skipped": 2})

    def test_conflicting_id_rolls_back_entire_new_batch(self):
        vision.import_rows(self.db, [record()])
        with self.assertRaisesRegex(ValueError, "different data"):
            vision.import_rows(self.db, [record("TEST-002"), record(review_note="Changed review")])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM inspections").fetchone()[0], 1)

    def test_invalid_row_rolls_back_import(self):
        with self.assertRaisesRegex(ValueError, "automatic_result"):
            vision.import_rows(self.db, [record(), record("TEST-002", automatic="Maybe")])
        self.assertEqual(self.db.execute("SELECT COUNT(*) FROM inspections").fetchone()[0], 0)

    def test_required_columns_and_result_values(self):
        missing = record(); missing.pop("camera")
        for row in [missing, record(application="Unknown"), record(reviewed="Maybe"),
                    record(camera="<script>"), record(reviewed="Fail", defect_label="None"),
                    record(review_note="x" * 601), record(timestamp="2026-01-15T09:00:00")]:
            with self.subTest(row=row):
                with self.assertRaises(ValueError):
                    vision.validate_row(row)

    def test_equivalent_timezone_is_same_record(self):
        vision.import_rows(self.db, [record()])
        result = vision.import_rows(self.db, [record(timestamp="2026-01-15T03:00:00-06:00")])
        self.assertEqual(result["duplicates_skipped"], 1)

    def test_parameterized_sql_preserves_note_text(self):
        note = "'); DROP TABLE inspections; --"
        vision.import_rows(self.db, [record(review_note=note)])
        self.assertEqual(vision.build_report(self.db)["records"][0]["review_note"], note)

    def test_persisted_exports_match_saved_records(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "results.db"
            first = vision.connect(path)
            vision.import_rows(first, [record()]); first.close()
            second = vision.connect(path)
            result = vision.export_report(second, Path(temp) / "out"); second.close()
            output = Path(temp) / "out"
            self.assertEqual(result["summary"]["decisions"], 1)
            self.assertEqual(json.loads((output / "summary.json").read_text())["summary"]["decisions"], 1)
            self.assertNotIn("__REPORT_JSON__", (output / "viewer.html").read_text())
            with (output / "inspection_results.csv").open() as stream:
                self.assertEqual(list(csv.DictReader(stream))[0]["result_category"], "Correct pass")

    def test_json_embedding_cannot_close_script_element(self):
        html = vision.render_viewer({"note": "</script><script>alert('test')</script>"})
        self.assertIn("\\u003c/script\\u003e", html)
        self.assertNotIn("<script>alert", html)

    def test_csv_export_neutralizes_formula_text(self):
        for value in ["=1+1", "+1", "-1", "@SUM(A1)", "  =1"]:
            self.assertEqual(vision.csv_safe(value), "'" + value)
        self.assertEqual(vision.csv_safe("A normal note"), "A normal note")

    def test_duplicate_csv_headers_are_rejected(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.csv"
            path.write_text(",".join((*vision.FIELDS, "camera")) + "\n")
            with self.assertRaisesRegex(ValueError, "unique columns"):
                vision.import_csv(self.db, path)

    def test_camera_decisions_are_not_unique_part_counts(self):
        vision.import_rows(self.db, vision.demo_rows())
        casting = [r for r in vision.build_report(self.db)["records"] if r["application"] == "Casting"]
        self.assertEqual(len(casting), 16)
        self.assertEqual(len({r["part_id"] for r in casting}), 8)
        self.assertEqual({r["camera"] for r in casting}, {"CAM-1", "CAM-2"})

    def test_empty_database_has_clear_report_error(self):
        with self.assertRaisesRegex(ValueError, "No results"):
            vision.build_report(self.db)


if __name__ == "__main__":
    unittest.main()
