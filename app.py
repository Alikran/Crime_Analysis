from flask import Flask, render_template, request
import requests
import folium
import pandas as pd
import json
import geopandas as gpd
from datetime import datetime
from collections import Counter
from folium.plugins import MarkerCluster

# creates an instance of the Flask application
app = Flask(__name__)

# get chicago crime dataset API endpoint
API_ENDPOINT = "https://data.cityofchicago.org/resource/x2n5-8w5q.json?$limit=1000" # Increased limit for more data

# Chicago Wards GeoJSON API endpoint
HOODS_GEOJSON_URL = "https://data.cityofchicago.org/resource/y6yq-dbs2.geojson"
# the function that will be called when the user visits the root URL.
@app.route('/', methods=['GET'])
def index():
    primary_type_filter = request.args.get('primary_type')
    ward_filter = request.args.get('ward')
    date_from_str = request.args.get('date_from')
    date_to_str = request.args.get('date_to')

    all_data_df = get_crime_data()
    map_html = None
    most_common_crimes = None

    if not all_data_df.empty:
        all_data_df['date_of_occurrence'] = pd.to_datetime(all_data_df['date_of_occurrence'])
        all_data_df['hour'] = all_data_df['date_of_occurrence'].dt.hour
        all_data_df['day_of_week'] = all_data_df['date_of_occurrence'].dt.dayofweek  # Monday=0, Sunday=6
        all_data_df['month'] = all_data_df['date_of_occurrence'].dt.month
        all_data_df['year'] = all_data_df['date_of_occurrence'].dt.year
        all_data_df['is_weekend'] = all_data_df['date_of_occurrence'].dt.dayofweek.isin([5, 6]).astype(int) # 1 if weekend, 0 otherwise
        wards_raw = all_data_df['ward'].dropna().unique()
        wards = sorted(list(wards_raw.astype(str))) # Get unique ward numbers as strings

        primary_descriptions = sorted(all_data_df['_primary_decsription'].unique().tolist())

        filtered_crimes_df = all_data_df.copy() # Start with a copy of the full DataFrame

        if primary_type_filter and primary_type_filter != 'All':
            filtered_crimes_df = filtered_crimes_df[filtered_crimes_df['_primary_decsription'] == primary_type_filter]

        if ward_filter and ward_filter != 'All':
            filtered_crimes_df = filtered_crimes_df[filtered_crimes_df['ward'].astype(str) == ward_filter] # Filter by ward

        if date_from_str and date_to_str:
            try:
                date_from = datetime.strptime(date_from_str, '%Y-%m-%d').date()
                date_to = datetime.strptime(date_to_str, '%Y-%m-%d').date()
                filtered_crimes_df = filtered_crimes_df[
                    (filtered_crimes_df['date_of_occurrence'].dt.date >= date_from) &
                    (filtered_crimes_df['date_of_occurrence'].dt.date <= date_to)
                ]
            except ValueError:
                print("Invalid date format")
        
        crime_counts = Counter(filtered_crimes_df["_primary_decsription"])
        most_common_crimes = crime_counts.most_common(10)  # Get the top 10

        print(f"\nNumber of crimes in filtered_crimes_df: {len(filtered_crimes_df)}")
        print(f"First row of filtered_crimes_df (if not empty):\n{filtered_crimes_df.head(1)}")

                # Create the Folium map
        if not filtered_crimes_df.empty:
            # Ensure latitude and longitude are numeric and not NaN
            filtered_crimes_df['latitude'] = pd.to_numeric(filtered_crimes_df['latitude'], errors='coerce')
            filtered_crimes_df['longitude'] = pd.to_numeric(filtered_crimes_df['longitude'], errors='coerce')
            filtered_crimes_df_valid_coords = filtered_crimes_df.dropna(subset=['latitude', 'longitude'])

            print(f"\nNumber of crimes with valid coordinates after filtering: {len(filtered_crimes_df_valid_coords)}")
            print(f"First row with valid coordinates (if any):\n{filtered_crimes_df_valid_coords.head(1)}")

            if not filtered_crimes_df_valid_coords.empty:
                m = folium.Map(location=[41.8781, -87.6298], zoom_start=11) # Chicago's coordinates
                folium.TileLayer('CartoDB positron').add_to(m) # Using OpenStreetMap for now
                marker_cluster = MarkerCluster().add_to(m)
                for index, row in filtered_crimes_df_valid_coords.iterrows():
                    lat = row['latitude']
                    lon = row['longitude']
                    primary_description = row['_primary_decsription']
                    folium.Marker([lat, lon], popup=primary_description).add_to(marker_cluster)
                 # Add Chicago Neigborhoods boundaries from shapefile
                try:
                    response = requests.get(HOODS_GEOJSON_URL)
                    response.raise_for_status()
                    hood_data = response.json()
                    folium.GeoJson(
                        hood_data,
                        name='Chicago Neigborhoods',
                        style_function=lambda feature: {
                            'color': '#41B6E6',
                            'weight': 3,
                            'fillOpacity': 0
                        },
                        highlight_function=lambda feature: {
                        'fillColor': '#EF002B',
                        'color': '#EF002B',
                        'weight': 3,
                        'fillOpacity': 0.5,
                        'cursor': 'pointer',
                    },
                    on_each_feature=lambda feature, layer: layer.on({
                        'click': lambda e: e.target.setStyle({
                            'fillColor': 'green',
                            'fillOpacity': 0.7
                        }).bringToFront() or e.target._map.fitBounds(e.target.getBounds())
                    })
                    ).add_to(m)
                except requests.exceptions.RequestException as e:
                    print(f"Error fetching Neigborhoods boundaries from API: {e}")
                map_html = m._repr_html_() # Get the HTML representation of the map
            else:
                map_html = "<p>No crimes with valid coordinates found based on the filters.</p>"
        else:
            map_html = "<p>No crimes found based on the applied filters.</p>"

        return render_template(
            'index.html',
            crimes=filtered_crimes_df.to_dict('records'),
            primary_types=primary_descriptions,
            wards=wards,
            map_html=map_html,
            most_common_crimes=most_common_crimes
        )
    else:
        return "Failed to fetch crime data."

def get_crime_data():
    try:
        response = requests.get(API_ENDPOINT)
        response.raise_for_status()
        data = response.json()
        return pd.DataFrame(data)
    except requests.exceptions.RequestException as e:
        print(f"Error getting data: {e}")
        return pd.DataFrame()

if __name__ == '__main__':
    app.run(debug=True)