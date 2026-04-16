from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean

import folium
from folium.plugins import MarkerCluster
from pyproj import Transformer


ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "filtered.csv"
OUTPUT_POINTS_CSV = ROOT / "filtered_mapped.csv"
OUTPUT_OUTAGES_CSV = ROOT / "outage_summary.csv"
OUTPUT_MAP_HTML = ROOT / "outage_map.html"

SOURCE_CRS = "EPSG:2048"  # Hartebeesthoek94 / Lo19
TARGET_CRS = "EPSG:4326"
PRECEDENCE = ["BELVEDERE", "AVONDALE", "DE TIJGER"]
COLORS = {
    "BELVEDERE": "red",
    "AVONDALE": "blue",
    "DE TIJGER": "green",
}
VALID_LON_RANGE = (18.0, 19.0)
VALID_LAT_RANGE = (-34.2, -33.5)


@dataclass
class TicketPoint:
    created_on: datetime
    created_on_text: str
    suburb_raw: str
    suburb_norm: str
    notification: str
    complaint_type: str
    object_id: str
    x_raw: float
    y_raw: float
    lon: float
    lat: float


@dataclass
class TicketRecord:
    created_on: datetime
    created_on_text: str
    suburb_raw: str
    suburb_norm: str
    notification: str
    complaint_type: str
    object_id: str
    x_raw: str
    y_raw: str
    lon: float | None
    lat: float | None


def normalize_suburb(raw: str) -> str:
    value = raw.strip().upper()
    if "BELVEDERE" in value:
        return "BELVEDERE"
    if "AVONDALE" in value:
        return "AVONDALE"
    if "DE TIJGER" in value:
        return "DE TIJGER"
    return value


def load_records() -> list[TicketRecord]:
    transformer = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)
    records: list[TicketRecord] = []

    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle, delimiter=";")
        for row in reader:
            created_on_text = row["Created_On_Date"].strip()
            created_on = datetime.strptime(created_on_text, "%d.%m.%Y")

            x_raw = row["X_Y_Co_ordinate_1"].strip()
            y_raw = row["X_Y_Co_ordinate_2"].strip()
            lon = None
            lat = None
            try:
                lon, lat = _resolve_lon_lat(transformer, x_raw, y_raw)
            except ValueError:
                pass

            records.append(
                TicketRecord(
                    created_on=created_on,
                    created_on_text=created_on_text,
                    suburb_raw=row["Suburb"].strip(),
                    suburb_norm=normalize_suburb(row["Suburb"]),
                    notification=row["Notification"],
                    complaint_type=row["C3_Complaint_Type"],
                    object_id=row["ObjectId"],
                    x_raw=x_raw,
                    y_raw=y_raw,
                    lon=lon,
                    lat=lat,
                )
            )

    records.sort(key=lambda item: (item.created_on, item.suburb_norm, item.object_id))
    return records


def _resolve_lon_lat(transformer: Transformer, x_raw: str, y_raw: str) -> tuple[float | None, float | None]:
    a = float(x_raw)
    b = float(y_raw)
    candidates = [
        (abs(a), abs(b)),
        (abs(b), abs(a)),
        (a, b),
        (b, a),
    ]
    for easting, northing in candidates:
        lon, lat = transformer.transform(easting, northing)
        if VALID_LON_RANGE[0] <= lon <= VALID_LON_RANGE[1] and VALID_LAT_RANGE[0] <= lat <= VALID_LAT_RANGE[1]:
            return lon, lat
    return None, None


def build_outage_summary(records: list[TicketRecord]) -> list[dict[str, object]]:
    grouped: dict[str, list[TicketPoint]] = defaultdict(list)
    for point in records:
        grouped[point.created_on_text].append(point)

    outages: list[dict[str, object]] = []
    for date_text, items in grouped.items():
        suburb_counts = Counter(item.suburb_norm for item in items)
        chosen = next((suburb for suburb in PRECEDENCE if suburb_counts[suburb] > 0), suburb_counts.most_common(1)[0][0])
        geo_items = [item for item in items if item.lat is not None and item.lon is not None]
        outages.append(
            {
                "date": datetime.strptime(date_text, "%d.%m.%Y"),
                "date_text": date_text,
                "assigned_suburb": chosen,
                "ticket_count": len(items),
                "belvedere_count": suburb_counts.get("BELVEDERE", 0),
                "avondale_count": suburb_counts.get("AVONDALE", 0),
                "de_tijger_count": suburb_counts.get("DE TIJGER", 0),
                "mapped_ticket_count": len(geo_items),
                "centroid_lat": mean(item.lat for item in geo_items) if geo_items else None,
                "centroid_lon": mean(item.lon for item in geo_items) if geo_items else None,
            }
        )

    outages.sort(key=lambda item: item["date"])
    return outages


def write_points_csv(records: list[TicketRecord]) -> None:
    with OUTPUT_POINTS_CSV.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "created_on_date",
            "suburb_raw",
            "suburb_norm",
            "notification",
            "complaint_type",
            "object_id",
            "x_raw",
            "y_raw",
            "longitude",
            "latitude",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for point in records:
            writer.writerow(
                {
                    "created_on_date": point.created_on_text,
                    "suburb_raw": point.suburb_raw,
                    "suburb_norm": point.suburb_norm,
                    "notification": point.notification,
                    "complaint_type": point.complaint_type,
                    "object_id": point.object_id,
                    "x_raw": point.x_raw,
                    "y_raw": point.y_raw,
                    "longitude": f"{point.lon:.7f}" if point.lon is not None else "",
                    "latitude": f"{point.lat:.7f}" if point.lat is not None else "",
                }
            )


def write_outage_csv(outages: list[dict[str, object]]) -> None:
    with OUTPUT_OUTAGES_CSV.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "date",
            "assigned_suburb",
            "ticket_count",
            "mapped_ticket_count",
            "belvedere_count",
            "avondale_count",
            "de_tijger_count",
            "centroid_lat",
            "centroid_lon",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for outage in outages:
            writer.writerow(
                {
                    "date": outage["date_text"],
                    "assigned_suburb": outage["assigned_suburb"],
                    "ticket_count": outage["ticket_count"],
                    "mapped_ticket_count": outage["mapped_ticket_count"],
                    "belvedere_count": outage["belvedere_count"],
                    "avondale_count": outage["avondale_count"],
                    "de_tijger_count": outage["de_tijger_count"],
                    "centroid_lat": f"{outage['centroid_lat']:.7f}" if outage["centroid_lat"] is not None else "",
                    "centroid_lon": f"{outage['centroid_lon']:.7f}" if outage["centroid_lon"] is not None else "",
                }
            )


def build_map(records: list[TicketRecord], outages: list[dict[str, object]]) -> None:
    points = [point for point in records if point.lat is not None and point.lon is not None]
    center_lat = mean(point.lat for point in points)
    center_lon = mean(point.lon for point in points)
    map_ = folium.Map(location=[center_lat, center_lon], zoom_start=13, control_scale=True)

    cluster = MarkerCluster(name="Ticket points").add_to(map_)
    for point in points:
        popup = folium.Popup(
            html=(
                f"<b>{point.created_on_text}</b><br>"
                f"Suburb: {point.suburb_raw}<br>"
                f"Assigned group: {point.suburb_norm}<br>"
                f"Notification: {point.notification}<br>"
                f"Complaint: {point.complaint_type}<br>"
                f"ObjectId: {point.object_id}"
            ),
            max_width=360,
        )
        folium.CircleMarker(
            location=[point.lat, point.lon],
            radius=4,
            color=COLORS.get(point.suburb_norm, "gray"),
            fill=True,
            fill_opacity=0.75,
            popup=popup,
            tooltip=f"{point.created_on_text} | {point.suburb_raw}",
        ).add_to(cluster)

    outages_layer = folium.FeatureGroup(name="Outage days", show=True)
    for outage in outages:
        if outage["centroid_lat"] is None or outage["centroid_lon"] is None:
            continue
        popup = folium.Popup(
            html=(
                f"<b>{outage['date_text']}</b><br>"
                f"Assigned suburb: {outage['assigned_suburb']}<br>"
                f"Tickets: {outage['ticket_count']}<br>"
                f"Mapped tickets: {outage['mapped_ticket_count']}<br>"
                f"Belvedere: {outage['belvedere_count']}<br>"
                f"Avondale: {outage['avondale_count']}<br>"
                f"De Tijger: {outage['de_tijger_count']}"
            ),
            max_width=320,
        )
        folium.Marker(
            location=[outage["centroid_lat"], outage["centroid_lon"]],
            tooltip=f"{outage['date_text']} | {outage['assigned_suburb']} | {outage['ticket_count']} tickets",
            popup=popup,
            icon=folium.Icon(color=COLORS.get(outage["assigned_suburb"], "gray"), icon="info-sign"),
        ).add_to(outages_layer)
    outages_layer.add_to(map_)

    folium.LayerControl(collapsed=False).add_to(map_)
    map_.save(str(OUTPUT_MAP_HTML))


def main() -> None:
    records = load_records()
    outages = build_outage_summary(records)
    write_points_csv(records)
    write_outage_csv(outages)
    build_map(records, outages)
    print(f"Wrote {OUTPUT_POINTS_CSV.name}")
    print(f"Wrote {OUTPUT_OUTAGES_CSV.name}")
    print(f"Wrote {OUTPUT_MAP_HTML.name}")
    print(f"Tickets: {len(records)}")
    print(f"Mapped tickets: {sum(1 for item in records if item.lat is not None and item.lon is not None)}")
    print(f"Outage days: {len(outages)}")


if __name__ == "__main__":
    main()
