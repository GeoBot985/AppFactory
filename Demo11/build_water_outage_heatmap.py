from __future__ import annotations

import csv
from pathlib import Path
from statistics import mean

import folium
from folium.plugins import HeatMap
from pyproj import Transformer


ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "Service_requests_2025_to_2026.csv"
OUTPUT_HTML = ROOT / "water_outage_heatmap.html"

OUTAGE_KEYWORDS = ("NO SUPPLY", "NO WATER", "LOW PRESSURE")
VALID_LON_RANGE = (18.0, 19.0)
VALID_LAT_RANGE = (-34.2, -33.5)

# Focus on the same local area used for the four-street analysis.
BBOX = {
    "south": -33.900,
    "west": 18.590,
    "north": -33.884,
    "east": 18.602,
}


def resolve_lon_lat(transformer: Transformer, x_raw: str, y_raw: str) -> tuple[float | None, float | None]:
    a = float(x_raw)
    b = float(y_raw)
    for easting, northing in ((abs(a), abs(b)), (abs(b), abs(a)), (a, b), (b, a)):
        lon, lat = transformer.transform(easting, northing)
        if VALID_LON_RANGE[0] <= lon <= VALID_LON_RANGE[1] and VALID_LAT_RANGE[0] <= lat <= VALID_LAT_RANGE[1]:
            return lon, lat
    return None, None


def load_points() -> list[tuple[float, float]]:
    transformer = Transformer.from_crs("EPSG:2048", "EPSG:4326", always_xy=True)
    points: list[tuple[float, float]] = []

    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
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
            if not (BBOX["west"] <= lon <= BBOX["east"] and BBOX["south"] <= lat <= BBOX["north"]):
                continue
            points.append((lat, lon))

    return points


def build_map(points: list[tuple[float, float]]) -> None:
    if not points:
        raise RuntimeError("No local water outage points found for the heatmap")

    center_lat = mean(point[0] for point in points)
    center_lon = mean(point[1] for point in points)
    map_ = folium.Map(location=[center_lat, center_lon], zoom_start=15, control_scale=True)

    HeatMap(
        data=points,
        radius=18,
        blur=14,
        min_opacity=0.35,
        max_zoom=18,
    ).add_to(map_)

    folium.LayerControl(collapsed=False).add_to(map_)
    map_.save(str(OUTPUT_HTML))


def main() -> None:
    points = load_points()
    build_map(points)
    print(f"Wrote {OUTPUT_HTML.name}")
    print(f"Heatmap points: {len(points)}")


if __name__ == "__main__":
    main()
