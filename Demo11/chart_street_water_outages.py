from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import matplotlib.pyplot as plt


ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "street_filtered.csv"
OUTPUT_CSV = ROOT / "street_water_outage_daily.csv"
OUTPUT_PNG = ROOT / "street_water_outages_over_time.png"

OUTAGE_KEYWORDS = ("NO SUPPLY", "NO WATER", "LOW PRESSURE")
STREET_ORDER = [
    "Spes Bona Avenue",
    "Glaudina Drive",
    "Jacqueline Street",
    "Proot Street",
]
COLORS = {
    "Spes Bona Avenue": "#1f77b4",
    "Glaudina Drive": "#9467bd",
    "Jacqueline Street": "#2ca02c",
    "Proot Street": "#d62728",
}


def load_outage_events() -> tuple[list[datetime], dict[str, set[datetime]]]:
    street_dates: dict[str, set[datetime]] = defaultdict(set)
    all_dates: set[datetime] = set()

    with INPUT_CSV.open("r", encoding="utf-8", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            complaint_type = row["complaint_type"].upper()
            if not any(keyword in complaint_type for keyword in OUTAGE_KEYWORDS):
                continue
            street = row["nearest_street"]
            if street not in STREET_ORDER:
                continue
            date_value = datetime.strptime(row["created_on_date"], "%d.%m.%Y")
            street_dates[street].add(date_value)
            all_dates.add(date_value)

    ordered_dates = sorted(all_dates)
    return ordered_dates, street_dates


def write_daily_summary(ordered_dates: list[datetime], street_dates: dict[str, set[datetime]]) -> None:
    with OUTPUT_CSV.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = ["date", *STREET_ORDER, "total_streets_out"]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for date_value in ordered_dates:
            row = {"date": date_value.strftime("%Y-%m-%d")}
            total = 0
            for street in STREET_ORDER:
                is_out = 1 if date_value in street_dates.get(street, set()) else 0
                row[street] = is_out
                total += is_out
            row["total_streets_out"] = total
            writer.writerow(row)


def build_chart(ordered_dates: list[datetime], street_dates: dict[str, set[datetime]]) -> None:
    fig, (ax_top, ax_bottom) = plt.subplots(
        2,
        1,
        figsize=(15, 9),
        sharex=True,
        gridspec_kw={"height_ratios": [3, 1]},
        constrained_layout=True,
    )

    for index, street in enumerate(STREET_ORDER):
        dates = sorted(street_dates.get(street, set()))
        y_value = [index + 1] * len(dates)
        ax_top.scatter(
            dates,
            y_value,
            s=90,
            color=COLORS[street],
            label=f"{street} ({len(dates)} days)",
            alpha=0.9,
        )

    ax_top.set_yticks(range(1, len(STREET_ORDER) + 1), STREET_ORDER)
    ax_top.set_title("Water Outage Days for Target Streets")
    ax_top.set_ylabel("Street")
    ax_top.grid(axis="x", linestyle=":", alpha=0.4)
    ax_top.legend(loc="upper left")

    totals = []
    for date_value in ordered_dates:
        total = sum(1 for street in STREET_ORDER if date_value in street_dates.get(street, set()))
        totals.append(total)

    ax_bottom.bar(ordered_dates, totals, width=4, color="#4c4c4c", alpha=0.8)
    ax_bottom.set_ylabel("Streets Out")
    ax_bottom.set_xlabel("Date")
    ax_bottom.set_ylim(0, max(totals) + 1 if totals else 1)
    ax_bottom.grid(axis="y", linestyle=":", alpha=0.4)

    fig.savefig(OUTPUT_PNG, dpi=160)
    plt.close(fig)


def main() -> None:
    ordered_dates, street_dates = load_outage_events()
    write_daily_summary(ordered_dates, street_dates)
    build_chart(ordered_dates, street_dates)
    print(f"Wrote {OUTPUT_CSV.name}")
    print(f"Wrote {OUTPUT_PNG.name}")
    for street in STREET_ORDER:
        print(f"{street}: {len(street_dates.get(street, set()))} outage days")


if __name__ == "__main__":
    main()
