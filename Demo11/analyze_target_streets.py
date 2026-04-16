from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from statistics import mean

import folium
import requests
from folium.plugins import MarkerCluster
from pyproj import Transformer
from shapely.geometry import LineString, Point


ROOT = Path(__file__).resolve().parent
INPUT_CSV = ROOT / "Service_requests_2025_to_2026.csv"
OUTPUT_FILTERED = ROOT / "street_filtered.csv"
OUTPUT_OUTAGES = ROOT / "street_outage_summary.csv"
OUTPUT_MAP = ROOT / "street_outage_map.html"

SOURCE_CRS = "EPSG:2048"  # Hartebeesthoek94 / Lo19
TARGET_CRS = "EPSG:4326"
DISTANCE_THRESHOLD_METERS = 80.0
VALID_LON_RANGE = (18.0, 19.0)
VALID_LAT_RANGE = (-34.2, -33.5)
PRECEDENCE = ["BELVEDERE", "AVONDALE", "DE TIJGER"]
COLORS = {
    "Spes Bona Avenue": "blue",
    "Glaudina Drive": "purple",
    "Jacqueline Street": "green",
    "Proot Street": "red",
}
STREET_QUERIES = {
    "Spes Bona Avenue": "Spes Bona Avenue, Parow, Cape Town, South Africa",
    "Glaudina Drive": "Glaudina Drive, Parow, Cape Town, South Africa",
    "Jacqueline Street": "Jacqueline Street, Parow, Cape Town, South Africa",
    "Proot Street": "Proot Street, Parow, Cape Town, South Africa",
}


@dataclass
class StreetGeometry:
    requested_name: str
    osm_name: str
    osm_id: str
    line_wgs84: LineString
    line_local: LineString


@dataclass
class StreetTicket:
    created_on: datetime
    created_on_text: str
    suburb_raw: str
    suburb_norm: str
    complaint_type: str
    notification: str
    object_id: str
    lon: float
    lat: float
    nearest_street: str
    nearest_distance_m: float


def normalize_suburb(raw: str) -> str:
    value = raw.strip().upper()
    if "BELVEDERE" in value:
        return "BELVEDERE"
    if "AVONDALE" in value:
        return "AVONDALE"
    if "DE TIJGER" in value:
        return "DE TIJGER"
    return value


def fetch_street_geometries() -> list[StreetGeometry]:
    headers = {"User-Agent": "AppFactory-Demo11-StreetAnalysis/1.0"}
    names = list(STREET_QUERIES.values())
    found: dict[str, tuple[str, str, list[list[float]]]] = {}

    for requested_name, query in STREET_QUERIES.items():
        response = requests.get(
            "https://nominatim.openstreetmap.org/search",
            params={"q": query, "format": "jsonv2", "limit": 5},
            headers=headers,
            timeout=60,
        )
        response.raise_for_status()
        results = response.json()
        for item in results:
            if item.get("osm_type") == "way":
                osm_id = f"W{item['osm_id']}"
                found[requested_name] = (osm_id, item.get("display_name", requested_name), [])
                break
        if requested_name not in found:
            raise RuntimeError(f"Could not resolve OSM way for {requested_name}")

    lookup_ids = ",".join(value[0] for value in found.values())
    response = requests.get(
        "https://nominatim.openstreetmap.org/lookup",
        params={"osm_ids": lookup_ids, "format": "jsonv2", "polygon_geojson": 1},
        headers=headers,
        timeout=60,
    )
    response.raise_for_status()
    lookup_items = {f"W{item['osm_id']}": item for item in response.json()}

    to_local = Transformer.from_crs(TARGET_CRS, SOURCE_CRS, always_xy=True)
    streets: list[StreetGeometry] = []
    for requested_name in names:
        pass

    for requested_name in STREET_QUERIES.keys():
        osm_id, display_name, _ = found[requested_name]
        item = lookup_items[osm_id]
        geojson = item.get("geojson") or {}
        coordinates = geojson.get("coordinates") or []
        if geojson.get("type") != "LineString" or len(coordinates) < 2:
            raise RuntimeError(f"Unexpected geometry for {requested_name}")
        line_wgs84 = LineString(coordinates)
        local_coords = [to_local.transform(lon, lat) for lon, lat in coordinates]
        line_local = LineString(local_coords)
        streets.append(
            StreetGeometry(
                requested_name=requested_name,
                osm_name=item.get("name", requested_name),
                osm_id=osm_id,
                line_wgs84=line_wgs84,
                line_local=line_local,
            )
        )
    return streets


def resolve_lon_lat(transformer: Transformer, x_raw: str, y_raw: str) -> tuple[float | None, float | None, tuple[float, float] | None]:
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
            return lon, lat, (easting, northing)
    return None, None, None


def load_target_tickets(streets: list[StreetGeometry]) -> list[StreetTicket]:
    to_wgs84 = Transformer.from_crs(SOURCE_CRS, TARGET_CRS, always_xy=True)
    tickets: list[StreetTicket] = []

    with INPUT_CSV.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            x_raw = row["X_Y_Co_ordinate_1"].strip()
            y_raw = row["X_Y_Co_ordinate_2"].strip()
            try:
                lon, lat, local_xy = resolve_lon_lat(to_wgs84, x_raw, y_raw)
            except ValueError:
                continue
            if lon is None or lat is None or local_xy is None:
                continue

            point_local = Point(local_xy)
            nearest = None
            nearest_distance = None
            for street in streets:
                distance = street.line_local.distance(point_local)
                if nearest_distance is None or distance < nearest_distance:
                    nearest_distance = distance
                    nearest = street

            if nearest is None or nearest_distance is None or nearest_distance > DISTANCE_THRESHOLD_METERS:
                continue

            created_on_text = row["Created_On_Date"].strip()
            created_on = datetime.strptime(created_on_text, "%d.%m.%Y")
            tickets.append(
                StreetTicket(
                    created_on=created_on,
                    created_on_text=created_on_text,
                    suburb_raw=row["Suburb"].strip(),
                    suburb_norm=normalize_suburb(row["Suburb"]),
                    complaint_type=row["C3_Complaint_Type"].strip(),
                    notification=row["Notification"].strip(),
                    object_id=row["ObjectId"].strip(),
                    lon=lon,
                    lat=lat,
                    nearest_street=nearest.requested_name,
                    nearest_distance_m=nearest_distance,
                )
            )

    tickets.sort(key=lambda item: (item.created_on, item.nearest_street, item.object_id))
    return tickets


def write_filtered_csv(tickets: list[StreetTicket]) -> None:
    with OUTPUT_FILTERED.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "created_on_date",
            "suburb_raw",
            "suburb_norm",
            "nearest_street",
            "nearest_distance_m",
            "complaint_type",
            "notification",
            "object_id",
            "longitude",
            "latitude",
        ]
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for item in tickets:
            writer.writerow(
                {
                    "created_on_date": item.created_on_text,
                    "suburb_raw": item.suburb_raw,
                    "suburb_norm": item.suburb_norm,
                    "nearest_street": item.nearest_street,
                    "nearest_distance_m": f"{item.nearest_distance_m:.2f}",
                    "complaint_type": item.complaint_type,
                    "notification": item.notification,
                    "object_id": item.object_id,
                    "longitude": f"{item.lon:.7f}",
                    "latitude": f"{item.lat:.7f}",
                }
            )


def build_outage_summary(tickets: list[StreetTicket]) -> list[dict[str, object]]:
    grouped: dict[str, list[StreetTicket]] = defaultdict(list)
    for ticket in tickets:
        grouped[ticket.created_on_text].append(ticket)

    outages: list[dict[str, object]] = []
    for date_text, items in grouped.items():
        suburb_counts = Counter(item.suburb_norm for item in items)
        street_counts = Counter(item.nearest_street for item in items)
        assigned_suburb = next((name for name in PRECEDENCE if suburb_counts[name] > 0), suburb_counts.most_common(1)[0][0])
        dominant_street = street_counts.most_common(1)[0][0]
        outages.append(
            {
                "date": datetime.strptime(date_text, "%d.%m.%Y"),
                "date_text": date_text,
                "ticket_count": len(items),
                "assigned_suburb": assigned_suburb,
                "dominant_street": dominant_street,
                "spes_bona_count": street_counts.get("Spes Bona Avenue", 0),
                "glaudina_count": street_counts.get("Glaudina Drive", 0),
                "jacqueline_count": street_counts.get("Jacqueline Street", 0),
                "proot_count": street_counts.get("Proot Street", 0),
                "centroid_lat": mean(item.lat for item in items),
                "centroid_lon": mean(item.lon for item in items),
            }
        )

    outages.sort(key=lambda item: item["date"])
    return outages


def write_outage_summary(outages: list[dict[str, object]]) -> None:
    with OUTPUT_OUTAGES.open("w", encoding="utf-8", newline="") as handle:
        fieldnames = [
            "date",
            "assigned_suburb",
            "dominant_street",
            "ticket_count",
            "spes_bona_count",
            "glaudina_count",
            "jacqueline_count",
            "proot_count",
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
                    "dominant_street": outage["dominant_street"],
                    "ticket_count": outage["ticket_count"],
                    "spes_bona_count": outage["spes_bona_count"],
                    "glaudina_count": outage["glaudina_count"],
                    "jacqueline_count": outage["jacqueline_count"],
                    "proot_count": outage["proot_count"],
                    "centroid_lat": f"{outage['centroid_lat']:.7f}",
                    "centroid_lon": f"{outage['centroid_lon']:.7f}",
                }
            )


def build_map(streets: list[StreetGeometry], tickets: list[StreetTicket], outages: list[dict[str, object]]) -> None:
    center_lat = mean(ticket.lat for ticket in tickets)
    center_lon = mean(ticket.lon for ticket in tickets)
    map_ = folium.Map(location=[center_lat, center_lon], zoom_start=15, control_scale=True)

    street_layer = folium.FeatureGroup(name="Target streets", show=True)
    for street in streets:
        coords = [(lat, lon) for lon, lat in street.line_wgs84.coords]
        folium.PolyLine(
            locations=coords,
            color=COLORS.get(street.requested_name, "black"),
            weight=5,
            tooltip=street.requested_name,
        ).add_to(street_layer)
    street_layer.add_to(map_)

    cluster = MarkerCluster(name="Street-matched tickets", show=True).add_to(map_)
    for ticket in tickets:
        popup = folium.Popup(
            html=(
                f"<b>{ticket.created_on_text}</b><br>"
                f"Street: {ticket.nearest_street}<br>"
                f"Distance: {ticket.nearest_distance_m:.1f} m<br>"
                f"Suburb: {ticket.suburb_raw}<br>"
                f"Complaint: {ticket.complaint_type}<br>"
                f"Notification: {ticket.notification}<br>"
                f"ObjectId: {ticket.object_id}"
            ),
            max_width=360,
        )
        folium.CircleMarker(
            location=[ticket.lat, ticket.lon],
            radius=4,
            color=COLORS.get(ticket.nearest_street, "gray"),
            fill=True,
            fill_opacity=0.75,
            popup=popup,
            tooltip=f"{ticket.created_on_text} | {ticket.nearest_street}",
        ).add_to(cluster)

    outage_layer = folium.FeatureGroup(name="Outage days", show=True)
    for outage in outages:
        popup = folium.Popup(
            html=(
                f"<b>{outage['date_text']}</b><br>"
                f"Assigned suburb: {outage['assigned_suburb']}<br>"
                f"Dominant street: {outage['dominant_street']}<br>"
                f"Tickets: {outage['ticket_count']}<br>"
                f"Spes Bona: {outage['spes_bona_count']}<br>"
                f"Glaudina: {outage['glaudina_count']}<br>"
                f"Jacqueline: {outage['jacqueline_count']}<br>"
                f"Proot: {outage['proot_count']}"
            ),
            max_width=320,
        )
        folium.Marker(
            location=[outage["centroid_lat"], outage["centroid_lon"]],
            tooltip=f"{outage['date_text']} | {outage['dominant_street']} | {outage['ticket_count']} tickets",
            popup=popup,
            icon=folium.Icon(color="cadetblue", icon="info-sign"),
        ).add_to(outage_layer)
    outage_layer.add_to(map_)

    folium.LayerControl(collapsed=False).add_to(map_)
    map_.save(str(OUTPUT_MAP))


def main() -> None:
    streets = fetch_street_geometries()
    tickets = load_target_tickets(streets)
    outages = build_outage_summary(tickets)
    write_filtered_csv(tickets)
    write_outage_summary(outages)
    build_map(streets, tickets, outages)

    street_counts = Counter(ticket.nearest_street for ticket in tickets)
    print(f"Filtered tickets: {len(tickets)}")
    print(f"Outage days: {len(outages)}")
    for street_name in STREET_QUERIES:
        print(f"{street_name}: {street_counts.get(street_name, 0)}")
    print(f"Wrote {OUTPUT_FILTERED.name}")
    print(f"Wrote {OUTPUT_OUTAGES.name}")
    print(f"Wrote {OUTPUT_MAP.name}")


if __name__ == "__main__":
    main()
