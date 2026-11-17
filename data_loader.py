"""Loads the class, professor, review and travel data from CSV files in data/.

If we ever get an official feed from Los Rios, only this file needs to change - the rest of
the app just calls these load_... functions.
"""
from pathlib import Path

import pandas as pd

DATA_DIR = Path(__file__).parent / "data"


def load_catalog() -> pd.DataFrame:
    """One row per class MEETING. A class with two meeting times has two rows with the same
    class_number; a card with a LEC and a LAB shares one `offering` value."""
    df = pd.read_csv(DATA_DIR / "classes.csv", dtype=str).fillna("")
    df["oid"] = df["course_code"] + "|" + df["offering"]
    return df


def load_professors() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "professors.csv")


def load_campuses() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "campuses.csv", dtype=str)


def load_meta() -> dict[str, str]:
    """Small settings like when the seat counts were collected (data/meta.csv)."""
    df = pd.read_csv(DATA_DIR / "meta.csv", dtype=str).fillna("")
    return dict(zip(df["key"], df["value"]))


def load_travel() -> pd.DataFrame:
    return pd.read_csv(DATA_DIR / "travel_times.csv")


def load_reviews() -> dict[str, list[dict]]:
    """Returns {professor name: [review, ...]} with the newest review first."""
    df = pd.read_csv(DATA_DIR / "reviews.csv", dtype=str).fillna("")
    df = df.sort_values("date", ascending=False)
    return {prof: g.to_dict("records") for prof, g in df.groupby("professor")}
