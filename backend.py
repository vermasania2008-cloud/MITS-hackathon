"""SQLite storage and simple analytics for the sustainability dashboard."""

from __future__ import annotations

from contextlib import closing
from datetime import date, datetime, timedelta, timezone
import math
import os
from pathlib import Path
import random
import sqlite3

import pandas as pd


ROOT = Path(__file__).resolve().parent
DATABASE_PATH = Path(
    os.getenv("SUSTAINABILITY_DATABASE_PATH", str(ROOT / "data" / "sustainability.db"))
)
METRICS = (
    "electricity_kwh",
    "water_litres",
    "total_waste_kg",
    "recyclable_waste_kg",
    "non_recyclable_waste_kg",
    "carbon_emissions_kg",
)


def _connect(database_path: Path | str) -> sqlite3.Connection:
    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    return connection


def initialize_database(database_path: Path | str = DATABASE_PATH) -> None:
    """Create the table and add clearly labelled sample data to a new database."""
    path = Path(database_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with closing(_connect(path)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS sustainability_records (
                id INTEGER PRIMARY KEY,
                record_date TEXT NOT NULL,
                electricity_kwh REAL CHECK (electricity_kwh IS NULL OR electricity_kwh >= 0),
                water_litres REAL CHECK (water_litres IS NULL OR water_litres >= 0),
                total_waste_kg REAL CHECK (total_waste_kg IS NULL OR total_waste_kg >= 0),
                recyclable_waste_kg REAL CHECK (recyclable_waste_kg IS NULL OR recyclable_waste_kg >= 0),
                non_recyclable_waste_kg REAL CHECK (non_recyclable_waste_kg IS NULL OR non_recyclable_waste_kg >= 0),
                carbon_emissions_kg REAL CHECK (carbon_emissions_kg IS NULL OR carbon_emissions_kg >= 0),
                is_sample INTEGER NOT NULL DEFAULT 0 CHECK (is_sample IN (0, 1)),
                updated_at TEXT NOT NULL,
                UNIQUE(record_date, is_sample)
            )
            """
        )
        count = connection.execute(
            "SELECT COUNT(*) FROM sustainability_records"
        ).fetchone()[0]
        seed_sample = os.getenv("SUSTAINABILITY_SEED_SAMPLE", "1").lower()
        if count == 0 and seed_sample not in {"0", "false", "no"}:
            _insert_sample_data(connection, date.today())


def reporting_period(end: date | None = None) -> tuple[date, date, date, date]:
    """Return two consecutive periods, each exactly 30 calendar days long."""
    period_end = end or date.today()
    start = period_end - timedelta(days=29)
    previous_end = start - timedelta(days=1)
    return start, period_end, previous_end - timedelta(days=29), previous_end


def get_source(database_path: Path | str = DATABASE_PATH) -> str | None:
    """Prefer office records; otherwise show the sample set if it exists."""
    with closing(_connect(database_path)) as connection:
        if connection.execute(
            "SELECT 1 FROM sustainability_records WHERE is_sample = 0 LIMIT 1"
        ).fetchone():
            return "office"
        if connection.execute(
            "SELECT 1 FROM sustainability_records WHERE is_sample = 1 LIMIT 1"
        ).fetchone():
            return "sample"
    return None


def get_records(
    start: date,
    end: date,
    source: str | None,
    database_path: Path | str = DATABASE_PATH,
) -> pd.DataFrame:
    """Load a range and include blank rows for dates without measurements."""
    frame = pd.DataFrame(columns=["record_date", *METRICS])
    if source in {"office", "sample"}:
        sample_flag = int(source == "sample")
        with closing(_connect(database_path)) as connection:
            rows = connection.execute(
                """
                SELECT record_date, electricity_kwh, water_litres, total_waste_kg,
                       recyclable_waste_kg, non_recyclable_waste_kg,
                       carbon_emissions_kg
                FROM sustainability_records
                WHERE record_date BETWEEN ? AND ? AND is_sample = ?
                ORDER BY record_date
                """,
                (start.isoformat(), end.isoformat(), sample_flag),
            ).fetchall()
        if rows:
            frame = pd.DataFrame([dict(row) for row in rows])

    frame["record_date"] = pd.to_datetime(frame["record_date"], errors="coerce")
    frame = frame.dropna(subset=["record_date"]).set_index("record_date")
    frame = frame.reindex(pd.date_range(start, end, freq="D"))
    frame.index.name = "record_date"
    for metric in METRICS:
        if metric not in frame:
            frame[metric] = None
    return frame.reset_index()


def last_updated(source: str | None, database_path: Path | str = DATABASE_PATH) -> str | None:
    if source not in {"office", "sample"}:
        return None
    with closing(_connect(database_path)) as connection:
        row = connection.execute(
            "SELECT MAX(updated_at) FROM sustainability_records WHERE is_sample = ?",
            (int(source == "sample"),),
        ).fetchone()
    return row[0] if row else None


def prepare_records(
    records: pd.DataFrame, electricity_factor: float | None = None
) -> pd.DataFrame:
    """Use reported emissions first; estimate electricity only if configured."""
    frame = records.copy()
    if electricity_factor is not None:
        calculated = frame["electricity_kwh"] * electricity_factor
        frame["carbon_emissions_kg"] = frame["carbon_emissions_kg"].combine_first(
            calculated
        )
    return frame


def summarize(
    current: pd.DataFrame, previous: pd.DataFrame
) -> tuple[dict[str, dict[str, float | None]], list[str]]:
    """Return metric totals and a few observations supported by the records."""
    summaries: dict[str, dict[str, float | None]] = {}
    for metric in METRICS:
        current_values = pd.to_numeric(current[metric], errors="coerce")
        previous_values = pd.to_numeric(previous[metric], errors="coerce")
        total = float(current_values.sum()) if current_values.notna().any() else None
        change = None
        if (
            current_values.notna().all()
            and previous_values.notna().all()
            and previous_values.sum() != 0
        ):
            change = float((current_values.sum() - previous_values.sum()) / previous_values.sum() * 100)
        summaries[metric] = {"total": total, "change": change}

    insights: list[str] = []
    for metric, label in (
        ("electricity_kwh", "Electricity use"),
        ("water_litres", "Water use"),
        ("total_waste_kg", "Waste generated"),
    ):
        change = summaries[metric]["change"]
        if change is not None:
            direction = "decreased" if change < 0 else "increased"
            insights.append(f"{label} {direction} by {abs(change):.1f}% from the previous 30 days.")

    water = pd.to_numeric(current["water_litres"], errors="coerce")
    if water.notna().any():
        peak_date = current.loc[water.idxmax(), "record_date"].date()
        insights.append(f"Water use was highest on {peak_date:%d %b}.")

    total_waste = pd.to_numeric(current["total_waste_kg"], errors="coerce")
    recycled = pd.to_numeric(current["recyclable_waste_kg"], errors="coerce")
    paired = pd.concat((total_waste, recycled), axis=1).dropna()
    if not paired.empty and paired.iloc[:, 0].sum() > 0:
        share = paired.iloc[:, 1].sum() / paired.iloc[:, 0].sum() * 100
        insights.append(f"Recycling accounted for {share:.1f}% of measured waste.")
    return summaries, insights


def save_record(record: dict[str, object], database_path: Path | str = DATABASE_PATH) -> None:
    """Insert or explicitly update an office record for a date."""
    try:
        record_date = date.fromisoformat(str(record["record_date"]))
    except (KeyError, ValueError) as error:
        raise ValueError("Enter a valid record date in YYYY-MM-DD format.") from error
    if record_date.isoformat() != record["record_date"]:
        raise ValueError("Enter a valid record date in YYYY-MM-DD format.")

    values: list[float | None] = []
    for metric in METRICS:
        raw_value = record.get(metric)
        if raw_value in (None, ""):
            values.append(None)
            continue
        try:
            value = float(raw_value)
        except (TypeError, ValueError) as error:
            raise ValueError(f"{metric} must be a non-negative number.") from error
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{metric} must be a non-negative number.")
        values.append(value)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with closing(_connect(database_path)) as connection, connection:
        connection.execute(
            """
            INSERT INTO sustainability_records (
                record_date, electricity_kwh, water_litres, total_waste_kg,
                recyclable_waste_kg, non_recyclable_waste_kg, carbon_emissions_kg,
                is_sample, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
            ON CONFLICT(record_date, is_sample) DO UPDATE SET
                electricity_kwh = excluded.electricity_kwh,
                water_litres = excluded.water_litres,
                total_waste_kg = excluded.total_waste_kg,
                recyclable_waste_kg = excluded.recyclable_waste_kg,
                non_recyclable_waste_kg = excluded.non_recyclable_waste_kg,
                carbon_emissions_kg = excluded.carbon_emissions_kg,
                updated_at = excluded.updated_at
            """,
            (record_date.isoformat(), *values, now),
        )


def _insert_sample_data(connection: sqlite3.Connection, end: date) -> None:
    randomizer = random.Random(12)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    sample_rows = []
    for offset in range(60):
        record_date = end - timedelta(days=59 - offset)
        is_weekend = record_date.weekday() >= 5
        workday_factor = 0.6 if is_weekend else 1.0
        electricity = (86 + 8 * math.sin(offset / 5) + randomizer.uniform(-4, 4)) * workday_factor
        water = (1650 + 170 * math.sin(offset / 6) + randomizer.uniform(-60, 60)) * workday_factor
        total_waste = (34 + 5 * math.sin(offset / 7) + randomizer.uniform(-2, 2)) * workday_factor
        recycled = total_waste * 0.52
        sample_rows.append(
            (
                record_date.isoformat(),
                round(electricity, 2),
                round(water, 2),
                round(total_waste, 2),
                round(recycled, 2),
                round(total_waste - recycled, 2),
                None,
                1,
                now,
            )
        )
    connection.executemany(
        """
        INSERT INTO sustainability_records (
            record_date, electricity_kwh, water_litres, total_waste_kg,
            recyclable_waste_kg, non_recyclable_waste_kg, carbon_emissions_kg,
            is_sample, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        sample_rows,
    )
