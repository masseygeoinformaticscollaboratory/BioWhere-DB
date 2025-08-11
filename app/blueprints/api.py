from __future__ import annotations
import json, re
from typing import Any, Dict, List, Tuple, Optional
from flask import Blueprint, jsonify, request, current_app
from psycopg2 import sql
from ..db import get_conn
from ..config import Settings

bp = Blueprint("api", __name__)

def _settings() -> Settings:
    # pull values from app.config or rebuild from env if needed
    from ..config import Settings as S
    return S.from_env()

def _require(source: Dict[str, Any], *fields: str) -> Optional[str]:
    missing = [f for f in fields if not source.get(f)]
    return f"Missing required fields: {', '.join(missing)}" if missing else None

@bp.post("/search")
def search():
    print("HERE")
    cfg = _settings()
    term = (request.form.get("search_term") or "").strip()
    if len(term) <= cfg.SEARCH_MIN_LEN:
        return jsonify(data=[], meta={"count": 0})

    query = """
        SELECT featureName, id
        FROM FeatureName
        WHERE featureName ILIKE %s
        ORDER BY featureName
        LIMIT 50
    """
    with get_conn(readonly=True) as conn, conn.cursor() as cur:
        cur.execute(query, (f"%{term}%",))
        rows = cur.fetchall()
    data = [{"featurename": r[0], "id": r[1]} for r in rows]
    print(data)
    return jsonify(data=data, meta={"count": len(data)})

@bp.post("/get_initial_source")
def get_initial_source():
    feature_name_id = request.form.get("feature_name_id")
    if not feature_name_id:
        return jsonify(error="feature_name_id required"), 400

    q = """
        SELECT s.source
        FROM featurename fn
        LEFT JOIN source s ON s.featurename_id = fn.id
        WHERE fn.id = %s
        ORDER BY s.lastupdatedate DESC NULLS LAST
        LIMIT 1
    """
    with get_conn(readonly=True) as conn, conn.cursor() as cur:
        cur.execute(q, (feature_name_id,))
        row = cur.fetchone()
    return jsonify(source=row[0] if row else None)

@bp.post("/get_feature_metadata")
def get_feature_metadata():
    feature_name_id = request.form.get("feature_name_id")
    feature_name = request.form.get("feature_name")
    source = request.form.get("source")
    if msg := _require(request.form, "feature_name_id", "feature_name", "source"):
        return jsonify(error=msg), 400

    sql_general = """
        SELECT ft.featureclass, f.featuredescription
        FROM featurename fn
        LEFT JOIN feature f ON f.id = fn.feature_id
        LEFT JOIN featuretype ft ON ft.feature_id = fn.feature_id
        LEFT JOIN source s ON s.featureType_id = ft.id
        WHERE fn.id = %s AND s.source = %s
        LIMIT 1
    """
    sql_names = """
        SELECT fn2.featurename, fn2.language
        FROM featurename fn2
        WHERE fn2.feature_id = (SELECT feature_id FROM featurename WHERE id = %s LIMIT 1)
          AND fn2.featurename <> %s
        ORDER BY fn2.featurename
        LIMIT 100
    """
    sql_whakapapa = """
        SELECT w.whakapapa
        FROM featurename fn
        LEFT JOIN featurename_whakapapa fnw ON fnw.featurename_id = fn.id
        LEFT JOIN whakapapa w ON w.id = fnw.whakapapa_id
        WHERE fn.id = %s AND (w.whakapapausage = 'info_origi' OR w.whakapapausage IS NULL)
        ORDER BY w.lastupdatedate DESC NULLS LAST
        LIMIT 1
    """

    with get_conn(readonly=True) as conn, conn.cursor() as cur:
        cur.execute(sql_general, (feature_name_id, source))
        general = cur.fetchone()
        if not general:
            return jsonify(data=None)
        feature_type, feature_description = general

        cur.execute(sql_names, (feature_name_id, feature_name))
        names = cur.fetchall()
        other_names = [n for (n, lang) in names if lang != "mi"]
        maori_name = next((n for (n, lang) in names if lang == "mi"), None)

        cur.execute(sql_whakapapa, (feature_name_id,))
        wrow = cur.fetchone()
        whakapapa = wrow[0] if wrow else None

    return jsonify({
        "feature_type": feature_type,
        "feature_description": feature_description,
        "source": source,
        "other_names": ", ".join(other_names),
        "maori_name": maori_name,
        "whakapapa": whakapapa,
    })

@bp.post("/run_query")
def run_query():
    sql_text = (request.form.get("sql") or "").strip()
    if not sql_text:
        return jsonify(error="sql required"), 400
    if ";" in sql_text or not sql_text.lower().startswith("select"):
        return jsonify(error="Only a single SELECT is allowed."), 400
    if re.search(r"\b(drop|delete|insert|update|alter|truncate|create)\b", sql_text, re.I):
        return jsonify(error="Only SELECT queries are allowed."), 400

    with get_conn(readonly=True) as conn, conn.cursor() as cur:
        cur.execute(sql_text)
        cols = [d.name for d in cur.description]
        rows = cur.fetchall()
    return jsonify(data=[dict(zip(cols, r)) for r in rows], meta={"count": len(rows)})

@bp.post("/get_geometries")
def get_geometries():
    feature_name = (request.form.get("feature_name") or "").strip()
    if not feature_name:
        return jsonify(error="feature_name required"), 400

    query = """
        SELECT ST_AsGeoJSON(p.geometry), 'point', fn.id, s.source
        FROM SpatialGeometryRepresentation_point p
        JOIN SpatialGeometryRepresentation sgr ON p.spatialGeometryRepresentation_id = sgr.id
        JOIN FeatureName fn ON sgr.feature_id = fn.feature_id
        LEFT JOIN source s ON s.spatialGeometryRepresentation_id = sgr.id
        WHERE fn.featureName = %s
        UNION ALL
        SELECT ST_AsGeoJSON(l.geometry), 'line', fn.id, s.source
        FROM SpatialGeometryRepresentation_line l
        JOIN SpatialGeometryRepresentation sgr ON l.spatialGeometryRepresentation_id = sgr.id
        JOIN FeatureName fn ON sgr.feature_id = fn.feature_id
        LEFT JOIN source s ON s.spatialGeometryRepresentation_id = sgr.id
        WHERE fn.featureName = %s
        UNION ALL
        SELECT ST_AsGeoJSON(pg.geometry), 'polygon', fn.id, s.source
        FROM SpatialGeometryRepresentation_polygon pg
        JOIN SpatialGeometryRepresentation sgr ON pg.spatialGeometryRepresentation_id = sgr.id
        JOIN FeatureName fn ON sgr.feature_id = fn.feature_id
        LEFT JOIN source s ON s.spatialGeometryRepresentation_id = sgr.id
        WHERE fn.featureName = %s
    """
    with get_conn(readonly=True) as conn, conn.cursor() as cur:
        cur.execute(query, (feature_name, feature_name, feature_name))
        rows = cur.fetchall()
    data = [{"geometry": r[0], "type": r[1], "featurename_id": r[2], "source": r[3]} for r in rows]
    return jsonify(data=data, meta={"count": len(data)})

@bp.post("/add_whakapapa")
def add_whakapapa():
    feature_name_id = request.form.get("feature_name_id")
    whakapapa_text = (request.form.get("whakapapa_text") or "").strip()
    updated_by = request.form.get("updated_by")
    if msg := _require(request.form, "feature_name_id", "whakapapa_text", "updated_by"):
        return jsonify(error=msg), 400
    if not whakapapa_text:
        return jsonify(error="No text provided"), 400

    with get_conn(readonly=False) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO whakapapa (whakapapa, whakapapausage, lastupdateuser, lastupdatedate)
            VALUES (%s, 'info_origi', %s, current_timestamp) RETURNING id
            """,
            (whakapapa_text, updated_by),
        )
        w_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO featurename_whakapapa (featurename_id, whakapapa_id, lastupdateuser, lastupdatedate)
            VALUES (%s, %s, %s, current_timestamp)
            """,
            (feature_name_id, w_id, updated_by),
        )
    return jsonify(success=True)

@bp.post("/add_ancestor")
def add_ancestor():
    feature_name_id = request.form.get("feature_name_id")
    ancestor_text = (request.form.get("ancestor_text") or "").strip()
    updated_by = request.form.get("updated_by")
    if msg := _require(request.form, "feature_name_id", "ancestor_text", "updated_by"):
        return jsonify(error=msg), 400
    if not ancestor_text:
        return jsonify(error="No text provided"), 400

    with get_conn(readonly=False) as conn, conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO whakapapa (whakapapa, whakapapausage, lastupdateuser, lastupdatedate)
            VALUES (%s, 'info_ancestor', %s, current_timestamp) RETURNING id
            """,
            (ancestor_text, updated_by),
        )
        w_id = cur.fetchone()[0]
        cur.execute(
            """
            INSERT INTO featurename_whakapapa (featurename_id, whakapapa_id, lastupdateuser, lastupdatedate)
            VALUES (%s, %s, %s, current_timestamp)
            """,
            (feature_name_id, w_id, updated_by),
        )
    return jsonify(success=True)

@bp.post("/add_feature")
def add_feature():
    data = request.get_json(force=True, silent=False)
    required = ("name", "feature_type", "creator", "feature_description", "geometry")
    if msg := _require(data, *required):
        return jsonify(error=msg), 400

    name = data["name"]
    feature_type = data["feature_type"]
    creator = data["creator"]
    feature_description = data["feature_description"]
    whakapapa = data.get("whakapapa")
    try:
        geotype = data["geometry"]["geometry"]["type"]
        geostr = json.dumps(data["geometry"]["geometry"])
    except Exception:
        return jsonify(error="Invalid GeoJSON structure"), 400

    table_map = {
        "Point": "spatialgeometryrepresentation_point",
        "LineString": "SpatialGeometryRepresentation_line",
        "MultiLineString": "SpatialGeometryRepresentation_line",
        "Polygon": "SpatialGeometryRepresentation_polygon",
        "MultiPolygon": "SpatialGeometryRepresentation_polygon",
    }
    table_name = table_map.get(geotype)
    if not table_name:
        return jsonify(error=f"Unsupported geometry type: {geotype}"), 400

    with get_conn(readonly=False) as conn, conn.cursor() as cur:
        cur.execute(
            "INSERT INTO feature (featuredescription, lastupdateuser, lastupdatedate) VALUES (%s, %s, current_date) RETURNING id",
            (feature_description, creator),
        )
        feature_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO featurename (feature_id, featurename, lastupdateuser, lastupdatedate) VALUES (%s, %s, %s, current_date) RETURNING id",
            (feature_id, name, creator),
        )
        feature_name_id = cur.fetchone()[0]

        cur.execute(
            "INSERT INTO featuretype (feature_id, featureclass, lastupdateuser, lastupdatedate) VALUES (%s, %s, %s, current_date)",
            (feature_id, feature_type, creator),
        )

        cur.execute(
            """
            INSERT INTO SpatialGeometryRepresentation (lastUpdateDate, lastUpdateUser, timePeriod, spatialAccuracy, feature_id, localityDescription_id)
            VALUES (current_date, %s, NULL, NULL, %s, NULL) RETURNING id
            """,
            (creator, feature_id),
        )
        sgr_id = cur.fetchone()[0]

        cur.execute(
            sql.SQL("""
                INSERT INTO {} (geodeticReferenceSystem, geometry, lastUpdateDate, lastUpdateUser, spatialGeometryRepresentation_id)
                VALUES (%s, ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), current_date, %s, %s)
            """).format(sql.Identifier(table_name)),
            ("EPSG 4326", geostr, creator, sgr_id),
        )

        if whakapapa:
            cur.execute(
                "INSERT INTO Whakapapa (whakapapa, whakapapaUsage, lastUpdateDate, lastUpdateUser) VALUES (%s, %s, current_timestamp, %s) RETURNING id",
                (whakapapa, "info_origi", creator),
            )
            w_id = cur.fetchone()[0]
            cur.execute(
                "INSERT INTO FeatureName_Whakapapa (featureName_id, whakapapa_id, lastUpdateDate, lastUpdateUser) VALUES (%s, %s, current_timestamp, %s)",
                (feature_name_id, w_id, creator),
            )

    return jsonify(success=True)
