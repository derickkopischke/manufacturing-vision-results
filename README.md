# Machine Vision Results Viewer

A Python and SQLite portfolio project by **Derick Kopischke** for exploring saved inspection decisions, comparing automatic pass/fail results with sample manual reviews, and investigating false rejects and false accepts.

My manufacturing experience includes dual-camera MoldWatcher systems in casting and KEYENCE VS-Series applications in weld inspection and machining. This separate coding demonstration focuses on the results-review workflow around an inspection system.

The project uses **fictional records, fictional reference reviews, and illustrated schematic frames**. It contains no employer records or camera captures. It does not perform image recognition or connect to a camera, vendor application, or PLC.

## Run the viewer

Use **Python 3.12 or newer with SQLite support**. The project uses only Python's standard library, with no additional packages to install. It was tested with Python 3.12.

Download and extract the repository ZIP, then open a terminal in the extracted project folder. Or clone the repository:

```sh
git clone https://github.com/derickkopischke/manufacturing-vision-results.git
cd manufacturing-vision-results
python vision.py --db demo.db demo --out output
```

On Windows, use `py` instead of `python` if needed. On macOS or Linux, use `python3` if that is your installed command.

Open **`output/viewer.html`** in your browser. It works directly from the local file without a web server or internet connection.

To explore an existing example without running Python, download the repository and open **[examples/viewer.html](examples/viewer.html)** locally. GitHub's HTML file viewer shows source code rather than running the viewer.

The demo needs an empty database and will not overwrite existing inspections. To repeat it, choose a new filename, such as `--db another-demo.db`.

## Explore the results

- Filter by casting, weld inspection, or machining.
- Filter by correct pass, correct reject, false reject, false accept, or unreviewed.
- Search inspection, part, station, or camera IDs.
- Select a record to see its automatic decision, sample review, condition label, and review note.
- Move between records with Previous and Next.
- Toggle the schematic review-area annotation.
- Compare automatic decisions with sample reviews in a two-by-two table.
- Review conditions found in sample-reviewed failures.
- Download the current filtered selection as CSV.

The illustrated frames show a mold/cavity, a welded joint, or a machined feature. Review-area markers are drawn references, **not actual detection boxes**. No image pixels are processed.

## Sample dataset

There are **48 inspection decisions**: 16 each for casting, weld inspection, and machining. Casting includes two camera records for each of eight fictional parts. Counts therefore represent **camera decisions**, not unique parts or a combined two-camera part-release decision.

| Outcome | Definition | Sample count |
| --- | --- | ---: |
| Correct pass | Automatic Pass / reviewed Pass | 21 |
| Correct reject | Automatic Fail / reviewed Fail | 12 |
| False reject | Automatic Fail / reviewed Pass | 6 |
| False accept | Automatic Pass / reviewed Fail | 3 |
| Unreviewed | No reference review supplied | 6 |

The dataset deliberately includes mismatches to make the review workflow visible. Its percentages are examples of the calculations, not claims about any camera system or production performance.

## Calculations

All viewer cards, comparisons, and exports use the current filtered selection.

- **Review coverage:** reviewed decisions ÷ all decisions.
- **Review agreement:** matching automatic/reviewed decisions ÷ reviewed decisions.
- **False reject rate:** false rejects ÷ all reviewed Pass decisions.
- **False accept rate:** false accepts ÷ all reviewed Fail decisions.
- **Automatic Fail count:** all automatic Fail decisions, including unreviewed records.
- **Condition counts:** only conditions on records whose sample review is Fail.

Unreviewed records are excluded from agreement and error-rate denominators. A zero denominator is shown as a dash instead of 0%. Manual reviews are fictional reference labels rather than independently verified ground truth.

For the complete dataset, review coverage is 42/48 = 87.5%, agreement is 33/42 = 78.57%, false reject rate is 6/27 = 22.22%, and false accept rate is 3/15 = 20%. The viewer rounds displayed percentages to one decimal place.

## Import your own sample CSV

Use fictional or appropriately cleared records in the format of `sample_inspections.csv`:

```sh
python vision.py --db practice.db import sample_inspections.csv
python vision.py --db practice.db report --out practice-output
```

Place `--db` before the subcommand. Put `--out` after `demo` or `report`.

| Field | Meaning |
| --- | --- |
| `inspection_id` | Unique ID for one inspection decision. |
| `timestamp` | ISO 8601 timestamp with an explicit timezone, at whole-second precision; normalized to UTC. |
| `application` | `Casting`, `Weld inspection`, or `Machining`. |
| `station` | Demonstration station ID. |
| `camera` | Camera ID; casting samples use CAM-1 and CAM-2. |
| `part_id` | Part reference; multiple camera records may share one reference. |
| `automatic_result` | `Pass` or `Fail`. |
| `reviewed_result` | `Pass`, `Fail`, or blank when unreviewed. |
| `defect_label` | Condition label, including nuisance conditions; use `None` when appropriate. Reviewed Fail requires a condition. |
| `review_note` | Optional explanatory text, up to 600 characters. |

ID fields accept up to 60 letters, digits, underscores, and hyphens, starting with a letter or digit. All columns are required, including empty values for optional review fields. Native MoldWatcher or KEYENCE export formats would need to be mapped to this schema first; no vendor-format parser is included.

Identical reimports are skipped. Reusing an inspection ID with changed data is rejected, and any new records from that import batch are rolled back. Imports are immutable in this demonstration; to correct reference reviews, rebuild a fresh database from the corrected CSV. There is no in-browser review-editing workflow.

## Files and exports

| File | Purpose |
| --- | --- |
| `vision.py` | Validation, SQLite imports, review calculations, CLI, and report export. |
| `viewer_template.html` | Offline viewer, schematic rendering, filters, navigation, and CSV download. |
| `sample_inspections.csv` | Deterministic fictional records generated by `demo_rows()` in `vision.py`. |
| `tests/test_vision.py` | Calculation, import, rollback, persistence, and export checks. |
| `examples/viewer.html` | Saved interactive example. |
| `examples/summary.json` | Complete sample report and records. |
| `examples/inspection_results.csv` | Sample records with calculated outcome categories. |
| `examples/demo-output.txt` | Terminal output from the sample run. |

The same export files are generated in the directory selected by `--out`. SQLite databases and generated `output/` files are excluded from version control.

Imported SQL values use query parameters. Displayed text uses DOM text nodes; embedded JSON escapes HTML delimiters. CSV exports prefix formula-like text with an apostrophe for spreadsheet handling. Exported CSV includes the derived `result_category` column and is intended for review; the import schema remains the ten original columns.

## Run the checks

```sh
python -m unittest discover -s tests -v
```

There are 18 checks covering the outcome definitions, error-rate denominators, unreviewed records, duplicate handling, invalid-input rollback, timezone normalization, persistence, script-element escaping, and spreadsheet-formula text.

## Scope and possible extensions

This is a saved-results review tool, not an inspection engine. It does not implement OpenCV, model training, threshold optimization, camera acquisition, real-image overlays, equipment interlocks, or operator permissions.

Possible extensions include mapping an approved vendor CSV export, linking approved reference images, adding versioned review corrections, and separating validation batches by inspection recipe.

## About the author

I'm interested in practical manufacturing software that helps people understand a process, investigate unexpected results, and work confidently with technical systems.

[Professional portfolio](https://derick-kopischke.fitsky18.chatgpt.site) · [GitHub](https://github.com/derickkopischke) · [LinkedIn](https://www.linkedin.com/in/derick-kopischke-84654b2ab/)

Related projects: [Manufacturing CMMS Workflow](https://github.com/derickkopischke/manufacturing-cmms-workflow) · [Manufacturing SCADA Simulator](https://github.com/derickkopischke/manufacturing-scada-simulator).
