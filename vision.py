"""Import fictional vision inspection results and export an offline review viewer."""

from __future__ import annotations

import argparse
import csv
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
APPLICATIONS = ("Casting", "Weld inspection", "Machining")
RESULTS = ("Pass", "Fail")
CATEGORIES = ("Correct pass", "Correct reject", "False reject", "False accept", "Unreviewed")
FIELDS = ("inspection_id", "timestamp", "application", "station", "camera", "part_id",
          "automatic_result", "reviewed_result", "defect_label", "review_note")


def normalize_timestamp(value: str) -> str:
    try:
        stamp = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Timestamp must be ISO 8601 with an explicit timezone") from exc
    if stamp.tzinfo is None or stamp.utcoffset() is None:
        raise ValueError("Timestamp requires a timezone")
    if stamp.microsecond:
        raise ValueError("This example uses whole-second timestamps")
    return stamp.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def validate_row(raw: dict) -> dict:
    if set(raw) != set(FIELDS):
        raise ValueError("Expected columns: " + ", ".join(FIELDS))
    if any(raw[k] is None for k in FIELDS):
        raise ValueError("Every column must be present; reviewed_result may be blank")
    row = {k: str(raw[k]).strip() for k in FIELDS}
    for key in ("inspection_id", "station", "camera", "part_id"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,59}", row[key]):
            raise ValueError(f"{key} must be an ID of 1–60 letters, digits, _ or -")
    row["timestamp"] = normalize_timestamp(row["timestamp"])
    if row["application"] not in APPLICATIONS:
        raise ValueError("Unknown application")
    if row["automatic_result"] not in RESULTS:
        raise ValueError("automatic_result must be Pass or Fail")
    if row["reviewed_result"] not in (*RESULTS, ""):
        raise ValueError("reviewed_result must be Pass, Fail, or blank")
    if not row["defect_label"] or len(row["defect_label"]) > 100:
        raise ValueError("defect_label requires 1–100 characters; use None when appropriate")
    if len(row["review_note"]) > 600:
        raise ValueError("review_note cannot exceed 600 characters")
    if row["reviewed_result"] == "Fail" and row["defect_label"] == "None":
        raise ValueError("A reviewed failure needs a defect label")
    return row


def category(row: dict) -> str:
    automatic, reviewed = row["automatic_result"], row["reviewed_result"]
    if reviewed == "":
        return "Unreviewed"
    return {("Pass", "Pass"): "Correct pass", ("Fail", "Fail"): "Correct reject",
            ("Fail", "Pass"): "False reject", ("Pass", "Fail"): "False accept"}[(automatic, reviewed)]


def connect(path: str | Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.execute("""CREATE TABLE IF NOT EXISTS inspections (
        inspection_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, application TEXT NOT NULL,
        station TEXT NOT NULL, camera TEXT NOT NULL, part_id TEXT NOT NULL,
        automatic_result TEXT NOT NULL, reviewed_result TEXT NOT NULL,
        defect_label TEXT NOT NULL, review_note TEXT NOT NULL)""")
    db.commit()
    return db


def import_rows(db: sqlite3.Connection, rows) -> dict:
    inserted = skipped = 0
    with db:
        for number, raw in enumerate(rows, 2):
            try:
                row = validate_row(raw)
                old = db.execute("SELECT * FROM inspections WHERE inspection_id=?",
                                 (row["inspection_id"],)).fetchone()
                if old:
                    if dict(old) != row:
                        raise ValueError("Inspection ID already exists with different data")
                    skipped += 1
                    continue
                db.execute("INSERT INTO inspections VALUES "
                           "(:inspection_id,:timestamp,:application,:station,:camera,:part_id,"
                           ":automatic_result,:reviewed_result,:defect_label,:review_note)", row)
                inserted += 1
            except ValueError as exc:
                raise ValueError(f"CSV row {number}: {exc}") from exc
    return {"inserted": inserted, "duplicates_skipped": skipped}


def import_csv(db: sqlite3.Connection, file: str | Path) -> dict:
    with Path(file).open(newline="", encoding="utf-8-sig") as stream:
        reader = csv.DictReader(stream)
        fields = reader.fieldnames or []
        if len(fields) != len(set(fields)) or set(fields) != set(FIELDS):
            raise ValueError("CSV requires these unique columns: " + ", ".join(FIELDS))
        return import_rows(db, reader)


def percentage(numerator: int, denominator: int) -> float | None:
    return round(100 * numerator / denominator, 2) if denominator else None


def summarize(records: list[dict]) -> dict:
    counts = {name: 0 for name in CATEGORIES}
    for record in records:
        counts[category(record)] += 1
    reviewed = len(records) - counts["Unreviewed"]
    reviewed_good = counts["Correct pass"] + counts["False reject"]
    reviewed_bad = counts["Correct reject"] + counts["False accept"]
    automatic_fail = sum(r["automatic_result"] == "Fail" for r in records)
    defects = Counter(r["defect_label"] for r in records if r["reviewed_result"] == "Fail")
    return {"decisions": len(records), "reviewed": reviewed, "categories": counts,
            "automatic_fail": automatic_fail,
            "automatic_fail_pct": percentage(automatic_fail, len(records)),
            "review_coverage_pct": percentage(reviewed, len(records)),
            "review_agreement_pct": percentage(counts["Correct pass"] + counts["Correct reject"], reviewed),
            "false_reject_pct_of_reviewed_good": percentage(counts["False reject"], reviewed_good),
            "false_accept_pct_of_reviewed_bad": percentage(counts["False accept"], reviewed_bad),
            "reviewed_defects": [{"label": label, "count": count} for label, count in
                                 sorted(defects.items(), key=lambda x: (-x[1], x[0]))]}


def build_report(db: sqlite3.Connection) -> dict:
    records = [dict(r) for r in db.execute("SELECT * FROM inspections ORDER BY timestamp,inspection_id")]
    if not records:
        raise ValueError("No results found; run demo or import a CSV first")
    records = [dict(row, result_category=category(row)) for row in records]
    return {"title": "Machine Vision Results Viewer", "author": "Derick Kopischke",
            "data_kind": "Fictional inspection decisions and sample reviews; frames are schematics",
            "window_start": records[0]["timestamp"], "window_end": records[-1]["timestamp"],
            "summary": summarize(records),
            "by_application": {app: summarize([r for r in records if r["application"] == app])
                               for app in APPLICATIONS}, "records": records}


def render_viewer(report: dict) -> str:
    payload = json.dumps(report, ensure_ascii=True).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return (ROOT / "viewer_template.html").read_text(encoding="utf-8").replace("__REPORT_JSON__", payload)


def csv_safe(value) -> str:
    """Keep imported text from being interpreted as a spreadsheet formula."""
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_report(db: sqlite3.Connection, output: str | Path) -> dict:
    report = build_report(db)
    out = Path(output)
    out.mkdir(parents=True, exist_ok=True)
    (out / "viewer.html").write_text(render_viewer(report), encoding="utf-8")
    (out / "summary.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    with (out / "inspection_results.csv").open("w", newline="", encoding="utf-8") as stream:
        writer = csv.writer(stream)
        writer.writerow((*FIELDS, "result_category"))
        for record in report["records"]:
            writer.writerow([csv_safe(record[key]) for key in (*FIELDS, "result_category")])
    return report


def demo_rows() -> list[dict]:
    start = datetime(2026, 1, 15, 9, tzinfo=timezone.utc)
    reviewed = ["Pass", "Pass", "Fail", "Pass", "Fail", "Pass", "Pass", "Fail",
                "Pass", "Pass", "Fail", "Pass", "Fail", "Pass", "", ""]
    definitions = {
        "Casting": ("CAST", ["Retained material", "Foreign material", "Mold alignment"]),
        "Weld inspection": ("WELD", ["Weld discontinuity", "Missing weld", "Surface porosity"]),
        "Machining": ("MACH", ["Burr at bore", "Missing hole", "Chip in feature"]),
    }
    records = []
    for app, (prefix, defects) in definitions.items():
        for i, review in enumerate(reviewed):
            automatic = review or ("Pass" if i == 14 else "Fail")
            if i in (3, 9):
                automatic = "Fail"
            elif i == 4:
                automatic = "Pass"
            label = defects[i % len(defects)] if review == "Fail" or i == 15 else "None"
            if i in (3, 9):
                label = "Lighting variation"
            note = ("Sample reviewer accepted the condition; lighting variation caused a simulated reject."
                    if i in (3, 9) else "Sample reviewer found a condition missed by the automatic decision."
                    if i == 4 else "Awaiting sample review." if not review else
                    "Automatic decision agrees with the fictional sample review.")
            records.append({"inspection_id": f"DEMO-{prefix}-{i+1:03d}",
                            "timestamp": (start + timedelta(minutes=i)).isoformat().replace("+00:00", "Z"),
                            "application": app, "station": f"DEMO-{prefix}-01",
                            "camera": f"CAM-{i % 2 + 1}" if app == "Casting" else "CAM-1",
                            "part_id": f"DEMO-{prefix}-PART-{i//2+1 if app=='Casting' else i+1:03d}",
                            "automatic_result": automatic, "reviewed_result": review,
                            "defect_label": label, "review_note": note})
    return sorted(records, key=lambda r: (r["timestamp"], r["inspection_id"]))


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default="vision-demo.db")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Load fictional results into an empty database")
    demo.add_argument("--out", default="output")
    load = commands.add_parser("import", help="Import inspection CSV atomically")
    load.add_argument("file")
    report = commands.add_parser("report", help="Generate a saved results viewer")
    report.add_argument("--out", default="output")
    args = parser.parse_args(argv)
    db = None
    try:
        db = connect(args.db)
        if args.command == "demo":
            if db.execute("SELECT COUNT(*) FROM inspections").fetchone()[0]:
                raise ValueError("Demo requires an empty database; choose another --db filename")
            print(json.dumps(import_csv(db, ROOT / "sample_inspections.csv")))
        elif args.command == "import":
            print(json.dumps(import_csv(db, args.file)))
            return 0
        report = export_report(db, args.out)
        summary = report["summary"]
        print(f"Decisions: {summary['decisions']} | Reviewed: {summary['reviewed']}")
        for name, count in summary["categories"].items():
            print(f"{name}: {count}")
        print(f"Open {Path(args.out) / 'viewer.html'} in your browser.")
        return 0
    except (ValueError, OSError, sqlite3.Error, csv.Error) as exc:
        parser.exit(2, f"Error: {exc}\n")
    finally:
        if db is not None:
            db.close()


if __name__ == "__main__":
    raise SystemExit(main())
