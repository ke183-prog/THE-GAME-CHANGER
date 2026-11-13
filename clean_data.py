"""Clean the survey CSV export in this folder.

Usage:
    python clean_data.py

The script keeps every input record, writes a normalized CSV, and creates a
plain-text report describing the changes and data-quality issues found.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from datetime import datetime
from pathlib import Path


INPUT_FILE = Path(__file__).with_name("raw_export.csv.csv")
OUTPUT_FILE = Path(__file__).with_name("cleaned_data.csv")
REPORT_FILE = Path(__file__).with_name("cleaning_report.txt")

HEADER_MAP = {
    "Timestamp": "timestamp",
    "Do you agree to take part in this survey? Your answers are anonymous and you may stop at any time.": "consent",
    "Case ID Simulated Household Response (Male):(S-M-001 to S-M-007) Simulated Household Response (Female):(S-F-001 to S-F-008) Consenting Adult Volunteer (Male):(C-M-001 to C-M-008) Consenting Adult Volunteer (Female):(C-F-001 to C-F-007) Technical Test Cases:(T-001 to T-005)": "case_id",
    "Source of this record": "source",
    "What is your sex?": "sex",
    "Age in years?": "age_years",
    "In the last 30 days, did you drink any alcohol?": "alcohol_last_30_days",
    "Which kinds of alcohol did you drink in the last 30 days? Tick all that apply.": "alcohol_types",
    "In the last 30 days, on how many days did you have 6 or more standard drinks on one occasion?": "heavy_drinking_days",
    "Do you drink alcohol?": "drinks_alcohol",
    "Are you above 18 years of age?": "above_18",
}

OUTPUT_FIELDS = [
    "record_id",
    "timestamp",
    "consent",
    "case_id",
    "source",
    "sex",
    "age_years",
    "alcohol_last_30_days",
    "alcohol_types",
    "heavy_drinking_days",
    "drinks_alcohol",
    "above_18",
]


def compact_header(value: str) -> str:
    """Remove line breaks and collapse whitespace in an exported header."""
    return re.sub(r"\s+", " ", value.replace("\ufeff", "")).strip()


def normalize_yes_no(value: str) -> str:
    value = value.strip()
    if value.upper() == "YES":
        return "Yes"
    if value.upper() == "NO":
        return "No"
    return value


def normalize_alcohol_types(value: str) -> str:
    labels = {
        "COMMERCIAL BEER": "Commercial Beer",
        "HOME BREWED OR TRADITIONAL DRINKS": "Home Brewed or Traditional Drinks",
        "SPIRITS": "Spirits",
        "WINE": "Wine",
        "OTHERS": "Other",
        "DON'T KNOW": "Don't know",
        "PREFER NOT TO SAY": "Prefer not to say",
    }
    parts = [part.strip() for part in value.split(",") if part.strip()]
    return "; ".join(labels.get(part.upper(), part) for part in parts)


def clean_rows(raw_rows: list[dict[str, str]]) -> tuple[list[dict[str, str]], list[str]]:
    notes: list[str] = []
    normalized_rows = [
        {compact_header(key): value for key, value in raw.items()} for raw in raw_rows
    ]
    case_header = next(
        header
        for header in normalized_rows[0]
        if header.startswith("Case ID Simulated Household Response")
    )
    duplicate_counts = Counter(row[case_header].strip() for row in normalized_rows)
    seen_ids: Counter[str] = Counter()
    cleaned: list[dict[str, str]] = []

    for row_number, row in enumerate(normalized_rows, start=2):
        row = {key: value.strip() for key, value in row.items()}
        case_id = row[case_header]
        case_id = case_id.strip()
        seen_ids[case_id] += 1
        record_id = case_id
        if duplicate_counts[case_id] > 1:
            record_id = f"{case_id}-{seen_ids[case_id]}"
            notes.append(f"Row {row_number}: duplicate case_id {case_id!r}; assigned record_id {record_id!r}.")

        source = row["Source of this record"].strip()
        if source == "Simulated response":
            source = "Simulated Household Response"
            notes.append(f"Row {row_number}: standardized source label to {source!r}.")

        timestamp = row["Timestamp"].strip()
        try:
            timestamp = datetime.strptime(timestamp, "%d/%m/%Y %H:%M:%S").isoformat(sep=" ")
        except ValueError:
            notes.append(f"Row {row_number}: could not parse timestamp {timestamp!r}.")

        age_text = row["Age in years?"].strip()
        try:
            age_years = str(int(age_text))
        except ValueError:
            age_years = age_text
            notes.append(f"Row {row_number}: age is not an integer: {age_text!r}.")

        alcohol_last_30_days = normalize_yes_no(
            row["In the last 30 days, did you drink any alcohol?"]
        )
        drinks_alcohol = normalize_yes_no(row["Do you drink alcohol?"])
        if not drinks_alcohol and alcohol_last_30_days:
            drinks_alcohol = alcohol_last_30_days
            notes.append(f"Row {row_number}: filled missing drinks_alcohol from alcohol_last_30_days.")

        above_18 = normalize_yes_no(row["Are you above 18 years of age?"])
        if not above_18 and age_years.isdigit():
            above_18 = "Yes" if int(age_years) > 18 else "No"
            notes.append(f"Row {row_number}: filled missing above_18 from age_years.")

        cleaned.append(
            {
                "record_id": record_id,
                "timestamp": timestamp,
                "consent": normalize_yes_no(row["Do you agree to take part in this survey? Your answers are anonymous and you may stop at any time."]),
                "case_id": case_id,
                "source": source,
                "sex": row["What is your sex?"].strip().title(),
                "age_years": age_years,
                "alcohol_last_30_days": alcohol_last_30_days,
                "alcohol_types": normalize_alcohol_types(
                    row["Which kinds of alcohol did you drink in the last 30 days? Tick all that apply."]
                ),
                "heavy_drinking_days": row[
                    "In the last 30 days, on how many days did you have 6 or more standard drinks on one occasion?"
                ].strip(),
                "drinks_alcohol": drinks_alcohol,
                "above_18": above_18,
            }
        )

    return cleaned, notes


def main() -> None:
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Input file not found: {INPUT_FILE}")

    with INPUT_FILE.open("r", encoding="utf-8-sig", newline="") as source:
        raw_rows = list(csv.DictReader(source))

    cleaned_rows, notes = clean_rows(raw_rows)

    with OUTPUT_FILE.open("w", encoding="utf-8", newline="") as destination:
        writer = csv.DictWriter(destination, fieldnames=OUTPUT_FIELDS)
        writer.writeheader()
        writer.writerows(cleaned_rows)

    with REPORT_FILE.open("w", encoding="utf-8") as report:
        report.write("Data cleaning report\n")
        report.write("====================\n\n")
        report.write(f"Input file: {INPUT_FILE.name}\n")
        report.write(f"Output file: {OUTPUT_FILE.name}\n")
        report.write(f"Records read: {len(raw_rows)}\n")
        report.write(f"Records written: {len(cleaned_rows)}\n")
        report.write("Records removed: 0\n\n")
        report.write("Transformations:\n")
        report.write("- Trimmed whitespace and normalized exported column names.\n")
        report.write("- Converted timestamps to YYYY-MM-DD HH:MM:SS format.\n")
        report.write("- Standardized Yes/No values and alcohol type labels.\n")
        report.write("- Added unique record_id values while preserving duplicate case IDs.\n")
        report.write("- Filled missing derived drinks_alcohol and above_18 values when supported by the same row.\n\n")
        report.write("Quality notes:\n")
        if notes:
            report.write("\n".join(f"- {note}" for note in notes))
            report.write("\n")
        else:
            report.write("- No quality issues found.\n")

    print(f"Wrote {len(cleaned_rows)} records to {OUTPUT_FILE.name}")
    print(f"Wrote cleaning details to {REPORT_FILE.name}")


if __name__ == "__main__":
    main()
