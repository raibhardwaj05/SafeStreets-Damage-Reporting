import sys
import os

# Add the parent directory to sys.path so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.models import RoadRisk
from app.risk_predictor import update_all_road_risks

def seed_data():
    app = create_app()
    with app.app_context():
        # Clear existing
        # RoadRisk.query.delete()
        
        sample_roads = [
            {
                "road_name": "Western Express Highway (WEH)",
                "latitude": 19.1584,
                "longitude": 72.8522,
                "potholes_last_year": 15,
                "potholes_2_years_ago": 8,
                "has_waterlogging_history": True,
                "has_drainage": True,
                "traffic_volume": "high",
                "forecast_precipitation": 120.5,
                "forecast_temperature": 32.0
            },
            {
                "road_name": "Linking Road, Bandra",
                "latitude": 19.0596,
                "longitude": 72.8295,
                "potholes_last_year": 5,
                "potholes_2_years_ago": 3,
                "has_waterlogging_history": False,
                "has_drainage": True,
                "traffic_volume": "medium",
                "forecast_precipitation": 45.0,
                "forecast_temperature": 31.0
            },
            {
                "road_name": "LBS Marg, Kurla",
                "latitude": 19.0726,
                "longitude": 72.8845,
                "potholes_last_year": 25,
                "potholes_2_years_ago": 20,
                "has_waterlogging_history": True,
                "has_drainage": False,
                "traffic_volume": "high",
                "forecast_precipitation": 150.0,
                "forecast_temperature": 33.0
            },
            {
                "road_name": "Marine Drive",
                "latitude": 18.9431,
                "longitude": 72.8230,
                "potholes_last_year": 1,
                "potholes_2_years_ago": 0,
                "has_waterlogging_history": False,
                "has_drainage": True,
                "traffic_volume": "medium",
                "forecast_precipitation": 20.0,
                "forecast_temperature": 30.0
            },
            {
                "road_name": "Sion-Panvel Highway",
                "latitude": 19.0431,
                "longitude": 72.9150,
                "potholes_last_year": 12,
                "potholes_2_years_ago": 10,
                "has_waterlogging_history": True,
                "has_drainage": False,
                "traffic_volume": "high",
                "forecast_precipitation": 95.0,
                "forecast_temperature": 34.0
            }
        ]

        for road_data in sample_roads:
            # Check if exists
            existing = RoadRisk.query.filter_by(road_name=road_data["road_name"]).first()
            if not existing:
                road = RoadRisk(**road_data)
                db.session.add(road)
        
        db.session.commit()
        print("Seeded sample road data.")
        
        # Calculate scores
        update_all_road_risks()
        print("Calculated risk scores for seeded data.")

if __name__ == "__main__":
    seed_data()
