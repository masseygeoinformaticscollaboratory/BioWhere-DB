import string

import buffer as buffer
import npm

from flask import Flask, render_template, request, jsonify
import psycopg2

app = Flask(__name__)

# Database configuration
db_config = {
    "database": "Biowhere",
    "user": "postgres",
    "host": "127.0.0.1",
    "password": "2666",
    "port": 5432,
}


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/search', methods=['POST'])
def search():
    search_term = request.form['search_term']

    if len(search_term) > 3:
        results = search_in_database(search_term)
    else:
        results = []

    return jsonify(results)


def search_in_database(search_term):
    try:
        connection = psycopg2.connect(**db_config)
        cursor = connection.cursor()
        cursor.execute("SELECT featureName FROM FeatureName WHERE featureName ILIKE %s", (f"%{search_term}%",))
        results = cursor.fetchall()
        cursor.close()
        connection.close()
        return results
    except Exception as e:
        print(f"Error in search_in_database: {e}")
        return []


@app.route('/get_geometries', methods=['POST'])
def get_geometries():
    feature_name = request.form['feature_name']
    geometries = retrieve_geometries_from_database(feature_name)
    return jsonify(geometries)


def retrieve_geometries_from_database(feature_name):
    try:
        connection = psycopg2.connect(**db_config)
        cursor = connection.cursor()

        query = """
        SELECT ST_AsGeoJSON(geometry) AS geometry, 'point' AS type
        FROM SpatialGeometryRepresentation_point
        WHERE spatialGeometryRepresentation_id IN (
            SELECT id FROM SpatialGeometryRepresentation
            WHERE feature_id IN (
                SELECT feature_id FROM FeatureName
                WHERE featureName = %s
            )
        )
        UNION ALL
        SELECT ST_AsGeoJSON(geometry) AS geometry, 'line' AS type
        FROM SpatialGeometryRepresentation_line
        WHERE spatialGeometryRepresentation_id IN (
            SELECT id FROM SpatialGeometryRepresentation
            WHERE feature_id IN (
                SELECT feature_id FROM FeatureName
                WHERE featureName = %s
            )
        )
        UNION ALL
        SELECT ST_AsGeoJSON(geometry) AS geometry, 'polygon' AS type
        FROM SpatialGeometryRepresentation_polygon
        WHERE spatialGeometryRepresentation_id IN (
            SELECT id FROM SpatialGeometryRepresentation
            WHERE feature_id IN (
                SELECT feature_id FROM FeatureName
                WHERE featureName = %s
            )
        );
        """

        fName = feature_name

        cursor.execute(query, (fName, fName, fName,))

        result = cursor.fetchall()

        cursor.close()
        connection.close()

        # Extract the GeoJSON values from the result
        geometries = [row[0] for row in result]

        return geometries

    except Exception as e:
        print(f"Error in retrieve_geometries_from_database: {e}")
        return []


if __name__ == '__main__':
    app.run(debug=True)
