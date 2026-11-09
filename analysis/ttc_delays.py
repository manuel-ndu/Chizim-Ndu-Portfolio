"""TTC subway delay analysis.

Downloads the City of Toronto's open TTC subway delay data, cleans it
and writes a small summary (data/ttc_summary.json) that the website charts.
Runs automatically every week on GitHub Actions.
"""
import io
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import requests

BASE = "https://ckan0.cf.opendata.inter.prod-toronto.ca"
PACKAGE = "ttc-subway-delay-data"
OUT = Path(__file__).resolve().parent.parent / "data" / "ttc_summary.json"
LINES = {"YU": "Line 1 Yonge-University", "BD": "Line 2 Bloor-Danforth",
         "SHP": "Line 4 Sheppard", "SRT": "Line 3 Scarborough"}


def get_resources():
    r = requests.get(f"{BASE}/api/3/action/package_show", params={"id": PACKAGE}, timeout=60)
    r.raise_for_status()
    return r.json()["result"]["resources"]


def year_of(res):
    m = re.search(r"(20\d\d)", res.get("name", ""))
    return int(m.group(1)) if m else 0


def load(res):
    """Load one resource as a DataFrame, whatever format it's in."""
    if res.get("datastore_active"):
        url = f"{BASE}/datastore/dump/{res['id']}"
        return pd.read_csv(io.StringIO(requests.get(url, timeout=120).text))
    raw = requests.get(res["url"], timeout=120).content
    fmt = (res.get("format") or "").lower()
    if fmt in ("xlsx", "xls"):
        sheets = pd.read_excel(io.BytesIO(raw), sheet_name=None)
        return pd.concat(sheets.values(), ignore_index=True)
    return pd.read_csv(io.BytesIO(raw))


def clean(df):
    df = df.rename(columns=lambda c: re.sub(r"[^a-z]", "", str(c).lower()))
    need = {"date", "time", "station", "code", "mindelay", "line"}
    missing = need - set(df.columns)
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    df = df[list(need)].copy()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["mindelay"] = pd.to_numeric(df["mindelay"], errors="coerce").fillna(0)
    df["hour"] = pd.to_datetime(df["time"].astype(str), format="%H:%M", errors="coerce").dt.hour
    df["line"] = df["line"].astype(str).str.upper().str.strip().map(LINES)
    df["station"] = (df["station"].astype(str).str.upper().str.strip()
                     .str.replace(r"\s+STATION$|\s+STN$", "", regex=True).str.title())
    df = df.dropna(subset=["date", "line"])
    return df[df["mindelay"] > 0]  # keep incidents that actually delayed trains


def summarise(df, years):
    start = (df["date"].max().to_period("M") - 11).to_timestamp()
    last12 = df[df["date"] >= start]
    monthly = last12.groupby(last12["date"].dt.to_period("M"))["mindelay"].agg(["count", "sum"])
    by_line = last12.groupby("line")["mindelay"].sum().sort_values(ascending=False)
    stations = last12.groupby("station")["mindelay"].sum().nlargest(10)
    hours = last12.groupby("hour")["mindelay"].sum().reindex(range(24), fill_value=0)
    codes = last12.groupby("code")["mindelay"].sum().nlargest(8)
    top_station = stations.index[0]
    peak_hour = int(hours.idxmax())
    return {
        "updated": datetime.now(timezone.utc).strftime("%d %b %Y"),
        "period": f"{last12['date'].min():%b %Y} to {last12['date'].max():%b %Y}",
        "source_years": years,
        "kpis": {
            "incidents": int(len(last12)),
            "hours_lost": int(last12["mindelay"].sum() / 60),
            "avg_delay": round(float(last12["mindelay"].mean()), 1),
            "top_station": top_station,
        },
        "monthly": {"labels": [str(p.strftime("%b %y")) for p in monthly.index.to_timestamp()],
                    "incidents": monthly["count"].astype(int).tolist(),
                    "minutes": monthly["sum"].astype(int).tolist()},
        "by_line": {"labels": by_line.index.tolist(), "minutes": by_line.astype(int).tolist()},
        "stations": {"labels": stations.index.tolist(), "minutes": stations.astype(int).tolist()},
        "hours": {"labels": [f"{h:02d}:00" for h in range(24)], "minutes": hours.astype(int).tolist()},
        "codes": {"labels": codes.index.astype(str).tolist(), "minutes": codes.astype(int).tolist()},
        "insights": [
            f"{top_station} lost the most minutes to delays in the last 12 months.",
            f"Delays peak around {peak_hour:02d}:00.",
            f"{by_line.index[0]} carries {by_line.iloc[0] / by_line.sum():.0%} of all delay minutes.",
        ],
    }


def main():
    resources = [r for r in get_resources() if year_of(r) and
                 (r.get("datastore_active") or (r.get("format") or "").lower() in ("csv", "xlsx", "xls"))]
    newest = sorted({year_of(r) for r in resources})[-2:]  # two latest years cover 12 months
    frames = []
    for r in resources:
        if year_of(r) in newest:
            try:
                frames.append(clean(load(r)))
            except Exception as e:  # one bad file shouldn't stop the run
                print(f"Skipped {r.get('name')}: {e}", file=sys.stderr)
    if not frames:
        sys.exit("No usable data found")
    df = pd.concat(frames).drop_duplicates()
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(summarise(df, newest), indent=1))
    print(f"Wrote {OUT} from {len(df):,} delay records")


if __name__ == "__main__":
    main()
