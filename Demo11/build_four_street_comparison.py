from __future__ import annotations

import csv
import json
import math
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from statistics import mean, median

import matplotlib.pyplot as plt
import requests
from pyproj import Transformer
from shapely.geometry import LineString, Point


ROOT = Path(__file__).resolve().parent
FULL_CSV = ROOT / "Service_requests_2025_to_2026.csv"
FOUR_STREET_DAILY = ROOT / "street_water_outage_daily.csv"
STREET_CACHE = ROOT / "local_named_streets_cache.json"

ALL_CSV = ROOT / "four_street_cluster_ranking.csv"
ALL_PNG = ROOT / "four_street_cluster_comparison.png"
ALL_HTML = ROOT / "four_street_findings.html"

EXCL_CSV = ROOT / "four_street_cluster_ranking_exclusive.csv"
EXCL_PNG = ROOT / "four_street_cluster_comparison_exclusive.png"
EXCL_HTML = ROOT / "four_street_findings_exclusive.html"

OUTAGE_KEYWORDS = ("NO SUPPLY", "NO WATER", "LOW PRESSURE")
VALID_LON_RANGE = (18.0, 19.0)
VALID_LAT_RANGE = (-34.2, -33.5)
TARGET_STREETS = ("Spes Bona Avenue", "Glaudina Drive", "Jacqueline Street", "Proot Street")
BOXES = [
    (-33.900, 18.590, -33.892, 18.596),
    (-33.900, 18.596, -33.892, 18.602),
    (-33.892, 18.590, -33.884, 18.596),
    (-33.892, 18.596, -33.884, 18.602),
]
OVERPASS_ENDPOINTS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
]


def load_target_union_days() -> int:
    with FOUR_STREET_DAILY.open("r", encoding="utf-8", newline="") as handle:
        return sum(1 for _ in csv.DictReader(handle))


def fetch_local_streets() -> list[tuple[str, LineString]]:
    if STREET_CACHE.exists():
        data = json.loads(STREET_CACHE.read_text(encoding="utf-8"))
        return [(item["name"], LineString(item["coordinates"])) for item in data]

    way_map: dict[int, dict[str, object]] = {}
    for south, west, north, east in BOXES:
        query = (
            f'[out:json][timeout:90];'
            f'(way["highway"]["name"]({south},{west},{north},{east}););'
            "out tags geom;"
        )
        data = None
        for endpoint in OVERPASS_ENDPOINTS:
            for _ in range(5):
                try:
                    response = requests.post(endpoint, data={"data": query}, timeout=180)
                    if response.status_code == 200:
                        data = response.json()
                        break
                except Exception:
                    pass
                time.sleep(2)
            if data is not None:
                break
        if data is None:
            raise RuntimeError(f"Unable to fetch local streets for bbox {(south, west, north, east)}")
        for element in data.get("elements", []):
            name = (element.get("tags") or {}).get("name")
            geometry = element.get("geometry") or []
            if not name or len(geometry) < 2:
                continue
            way_map[element["id"]] = {
                "name": name,
                "coordinates": [(point["lon"], point["lat"]) for point in geometry],
            }

    cache_payload = sorted(way_map.values(), key=lambda item: (item["name"], len(item["coordinates"])))
    STREET_CACHE.write_text(json.dumps(cache_payload, indent=2), encoding="utf-8")
    return [(item["name"], LineString(item["coordinates"])) for item in cache_payload]


def resolve_lon_lat(transformer: Transformer, x_raw: str, y_raw: str) -> tuple[float | None, float | None]:
    a = float(x_raw)
    b = float(y_raw)
    for easting, northing in ((abs(a), abs(b)), (abs(b), abs(a)), (a, b), (b, a)):
        lon, lat = transformer.transform(easting, northing)
        if VALID_LON_RANGE[0] <= lon <= VALID_LON_RANGE[1] and VALID_LAT_RANGE[0] <= lat <= VALID_LAT_RANGE[1]:
            return lon, lat
    return None, None


def build_street_outage_days(streets: list[tuple[str, LineString]]) -> dict[str, set[datetime.date]]:
    transformer = Transformer.from_crs("EPSG:2048", "EPSG:4326", always_xy=True)
    south = min(box[0] for box in BOXES)
    west = min(box[1] for box in BOXES)
    north = max(box[2] for box in BOXES)
    east = max(box[3] for box in BOXES)
    threshold_deg = 0.0008

    outage_days: dict[str, set[datetime.date]] = defaultdict(set)
    with FULL_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            complaint = (row["C3_Complaint_Type"] or "").upper()
            if not any(keyword in complaint for keyword in OUTAGE_KEYWORDS):
                continue
            try:
                lon, lat = resolve_lon_lat(
                    transformer,
                    row["X_Y_Co_ordinate_1"].strip(),
                    row["X_Y_Co_ordinate_2"].strip(),
                )
            except Exception:
                continue
            if lon is None or lat is None:
                continue
            if not (west <= lon <= east and south <= lat <= north):
                continue

            point = Point(lon, lat)
            best_name = None
            best_distance = None
            for name, line in streets:
                distance = line.distance(point)
                if best_distance is None or distance < best_distance:
                    best_distance = distance
                    best_name = name

            if best_name is None or best_distance is None or best_distance > threshold_deg:
                continue

            date_value = datetime.strptime(row["Created_On_Date"].strip(), "%d.%m.%Y").date()
            outage_days[best_name].add(date_value)

    return outage_days


def build_clusters(outage_days: dict[str, set[datetime.date]], streets: list[tuple[str, LineString]]) -> list[dict[str, object]]:
    centroid_map = {name: line.centroid.coords[0] for name, line in streets if name in outage_days}
    available = sorted(outage_days.keys())

    def distance(name_a: str, name_b: str) -> float:
        ax, ay = centroid_map[name_a]
        bx, by = centroid_map[name_b]
        return math.hypot(ax - bx, ay - by)

    cluster_map: dict[tuple[str, ...], int] = {}
    for street in available:
        neighbors = sorted(
            (other for other in available if other != street),
            key=lambda other: (distance(street, other), other),
        )[:3]
        cluster = tuple(sorted((street, *neighbors)))
        union_dates: set[datetime.date] = set()
        for item in cluster:
            union_dates |= outage_days.get(item, set())
        cluster_map[cluster] = len(union_dates)

    ranked = sorted(cluster_map.items(), key=lambda item: (-item[1], item[0]))
    rows: list[dict[str, object]] = []
    for rank, (cluster, outage_count) in enumerate(ranked, start=1):
        rows.append(
            {
                "rank": rank,
                "cluster_name": " | ".join(cluster),
                "street_1": cluster[0],
                "street_2": cluster[1],
                "street_3": cluster[2],
                "street_4": cluster[3],
                "unique_outage_days": outage_count,
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]], target_union_days: int) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "rank",
            "cluster_name",
            "street_1",
            "street_2",
            "street_3",
            "street_4",
            "unique_outage_days",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(
            {
                "rank": "TARGET",
                "cluster_name": " | ".join(TARGET_STREETS),
                "street_1": TARGET_STREETS[0],
                "street_2": TARGET_STREETS[1],
                "street_3": TARGET_STREETS[2],
                "street_4": TARGET_STREETS[3],
                "unique_outage_days": target_union_days,
            }
        )
        for row in rows:
            writer.writerow(row)


def write_chart(path: Path, title: str, rows: list[dict[str, object]], target_union_days: int, avg_value: float, median_value: float, avg_label: str) -> None:
    top_rows = rows[:10]
    labels = [row["cluster_name"] for row in top_rows] + ["TARGET 4 STREETS"]
    values = [row["unique_outage_days"] for row in top_rows] + [target_union_days]
    colors = ["#7f8c8d"] * len(top_rows) + ["#d62728"]

    fig, ax = plt.subplots(figsize=(15, 8), constrained_layout=True)
    bars = ax.barh(range(len(labels)), values, color=colors)
    ax.set_yticks(range(len(labels)), labels)
    ax.invert_yaxis()
    ax.set_xlabel("Unique Water Outage Days")
    ax.set_title(title)
    ax.axvline(avg_value, color="#1f77b4", linestyle="--", linewidth=1.5, label=f"{avg_label} = {avg_value:.1f}")
    ax.axvline(median_value, color="#2ca02c", linestyle=":", linewidth=1.5, label=f"Median = {median_value:.0f}")
    ax.legend(loc="lower right")
    for bar, value in zip(bars, values):
        ax.text(value + 0.3, bar.get_y() + bar.get_height() / 2, str(value), va="center")
    fig.savefig(path, dpi=160)
    plt.close(fig)


def write_html(path: Path, title: str, description: str, rows: list[dict[str, object]], target_union_days: int, avg_value: float, median_value: float) -> None:
    strongest = rows[0]["unique_outage_days"] if rows else 0
    stronger_than_top = target_union_days > strongest
    html = f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>{title}</title>
  <style>
    body {{ font-family: Segoe UI, Arial, sans-serif; margin: 32px; line-height: 1.45; color: #1f2937; }}
    h1, h2 {{ margin-bottom: 0.3em; }}
    .callout {{ background: #f4f7fb; border-left: 5px solid #2563eb; padding: 14px 18px; margin: 18px 0; }}
    table {{ border-collapse: collapse; width: 100%; margin-top: 18px; }}
    th, td {{ border: 1px solid #d1d5db; padding: 8px 10px; text-align: left; }}
    th {{ background: #f9fafb; }}
  </style>
</head>
<body>
  <h1>{title}</h1>
  <p>{description}</p>
  <div class="callout">
    <strong>Target streets:</strong> {", ".join(TARGET_STREETS)}<br>
    <strong>Target cluster outage days:</strong> {target_union_days}<br>
    <strong>Comparison average:</strong> {avg_value:.1f}<br>
    <strong>Comparison median:</strong> {median_value:.0f}
  </div>
  <p>The target area is approximately <strong>{target_union_days / avg_value:.1f}x</strong> the comparison average and <strong>{target_union_days / median_value:.1f}x</strong> the comparison median.</p>
  <p>{'The target area exceeds the strongest comparison cluster in this set.' if stronger_than_top else 'The target area remains below the strongest comparison cluster in this set.'}</p>
  <table>
    <thead><tr><th>Rank</th><th>Cluster</th><th>Unique Outage Days</th></tr></thead>
    <tbody>
      {''.join(f"<tr><td>{row['rank']}</td><td>{row['cluster_name']}</td><td>{row['unique_outage_days']}</td></tr>" for row in rows[:10])}
      <tr><td>TARGET</td><td>{' | '.join(TARGET_STREETS)}</td><td>{target_union_days}</td></tr>
    </tbody>
  </table>
</body>
</html>
"""
    path.write_text(html, encoding="utf-8")


def filter_exclusive(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    target_set = set(TARGET_STREETS)
    result = []
    for row in rows:
        cluster_set = {row["street_1"], row["street_2"], row["street_3"], row["street_4"]}
        if cluster_set & target_set:
            continue
        result.append(row)
    return result


def main() -> None:
    target_union_days = load_target_union_days()
    streets = fetch_local_streets()
    outage_days = build_street_outage_days(streets)
    rows = build_clusters(outage_days, streets)

    all_values = [row["unique_outage_days"] for row in rows]
    all_avg = mean(all_values)
    all_median = median(all_values)

    write_csv(ALL_CSV, rows, target_union_days)
    write_chart(ALL_PNG, "4-Street Cluster Comparison", rows, target_union_days, all_avg, all_median, "Average")
    write_html(
        ALL_HTML,
        "Four Street Water Outage Findings",
        "This comparison measures unique water outage days for the target area against comparable local four-street clusters. Some comparison clusters may overlap the target streets.",
        rows,
        target_union_days,
        all_avg,
        all_median,
    )

    excl_rows = filter_exclusive(rows)
    excl_values = [row["unique_outage_days"] for row in excl_rows]
    excl_avg = mean(excl_values)
    excl_median = median(excl_values)

    write_csv(EXCL_CSV, excl_rows, target_union_days)
    write_chart(EXCL_PNG, "4-Street Cluster Comparison Excluding Target Street Overlap", excl_rows, target_union_days, excl_avg, excl_median, "Exclusive average")
    write_html(
        EXCL_HTML,
        "Four Street Water Outage Findings (Exclusive Comparison)",
        "This comparison excludes all local four-street clusters that contain any of the target streets, so the benchmark is independent of the target area.",
        excl_rows,
        target_union_days,
        excl_avg,
        excl_median,
    )

    print(f"Target cluster outage days: {target_union_days}")
    print(f"All-cluster average: {all_avg:.2f}")
    print(f"All-cluster median: {all_median:.0f}")
    print(f"Exclusive-cluster average: {excl_avg:.2f}")
    print(f"Exclusive-cluster median: {excl_median:.0f}")
    print(f"Wrote {ALL_CSV.name}")
    print(f"Wrote {ALL_PNG.name}")
    print(f"Wrote {ALL_HTML.name}")
    print(f"Wrote {EXCL_CSV.name}")
    print(f"Wrote {EXCL_PNG.name}")
    print(f"Wrote {EXCL_HTML.name}")


if __name__ == "__main__":
    main()
