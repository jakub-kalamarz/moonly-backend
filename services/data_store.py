import os
import json
import logging
from datetime import datetime, timedelta
import numpy as np
import xml.etree.ElementTree as ET
from skyfield.api import load, utc, Topos
from splines import CatmullRom
from services.helpers import (
    format_epoch, GCRF_to_ITRF, earthPositions, Topos_xyz,
    download, is_in_shadow
)
from apscheduler.schedulers.background import BackgroundScheduler
import atexit


# Constants
DATA_DIR = 'data'
SAT_DATA_FILE = os.path.join(DATA_DIR, 'sat_data.json')
SHADOW_FILE = os.path.join(DATA_DIR, 'shadow_intervals.json')
TIMESTAMP_FILE = os.path.join(DATA_DIR, 'updated_at.txt')

# Ensure data directory exists
os.makedirs(DATA_DIR, exist_ok=True)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Cache for data
_sat_data_cache = None
_shadow_intervals_cache = None
_updated_at_cache = None

# Initialize scheduler
scheduler = BackgroundScheduler()

def refresh_satellite_data():
    """CRON-like task for refreshing satellite data"""
    logger.info("Starting scheduled satellite data refresh")
    get_sat_data()
    logger.info("Completed scheduled satellite data refresh")

# Add refresh function to run every 12 hours
scheduler.add_job(refresh_satellite_data, 'interval', hours=12, id='refresh_sat_data')

# Start scheduler when application starts
def start_scheduler():
    """Start the background scheduler if not already running"""
    if not scheduler.running:
        scheduler.start()
        logger.info("Started satellite data refresh scheduler (every 12 hours)")
        # Ensure scheduler is stopped when application exits
        atexit.register(lambda: scheduler.shutdown())

# Function to be used in the main application
def initialize_data_store():
    """Initialize cache and start scheduler"""
    # Load initial data if it exists
    load_data()

    # If data doesn't exist or is empty, generate it
    if _sat_data_cache is None or _shadow_intervals_cache is None:
        get_sat_data()
        load_data()

    # Start scheduler
    start_scheduler()

def _json_datetime_serialize(obj):
    """Helper function to serialize datetime objects to ISO format strings"""
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


def _json_datetime_deserialize(dct):
    """Helper function to deserialize ISO format strings to datetime objects"""
    for key, value in dct.items():
        if key == 'date' and isinstance(value, str):
            try:
                dct[key] = datetime.fromisoformat(value)
            except ValueError:
                pass  # Keep as string if not a valid datetime
    return dct


def save_data(sat_data, shadow_intervals):
    """Save satellite data and shadow intervals to files"""
    try:
        # Save satellite data
        with open(SAT_DATA_FILE, 'w') as f:
            json.dump(sat_data, f, default=_json_datetime_serialize)

        # Save shadow intervals
        with open(SHADOW_FILE, 'w') as f:
            json.dump(shadow_intervals, f)

        # Save timestamp
        now = datetime.now(utc)
        with open(TIMESTAMP_FILE, 'w') as f:
            f.write(now.isoformat())

        return True
    except Exception as e:
        logger.error(f"Error saving data: {e}")
        return False


def load_data():
    """Load satellite data and shadow intervals from files"""
    global _sat_data_cache, _shadow_intervals_cache, _updated_at_cache

    try:
        # Check if files exist
        if not os.path.exists(SAT_DATA_FILE) or not os.path.exists(SHADOW_FILE):
            logger.info("Data files don't exist yet, will generate new data")
            return None, None, None

        # Load timestamp
        with open(TIMESTAMP_FILE, 'r') as f:
            updated_at = datetime.fromisoformat(f.read().strip())

        # Load satellite data
        with open(SAT_DATA_FILE, 'r') as f:
            sat_data = json.load(f, object_hook=_json_datetime_deserialize)

        # Load shadow intervals
        with open(SHADOW_FILE, 'r') as f:
            shadow_intervals = json.load(f)

        # Update cache
        _sat_data_cache = sat_data
        _shadow_intervals_cache = shadow_intervals
        _updated_at_cache = updated_at

        return sat_data, shadow_intervals, updated_at
    except Exception as e:
        logger.error(f"Error loading data: {e}")
        return None, None, None


def get_sat_data():
    """Generate satellite data and save to files"""
    try:
        download("https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml")
        download("http://www.celestrak.com/SpaceData/EOP-All.txt")

        earth_positions = earthPositions()
        result = ET.parse("ISS.OEM_J2K_EPH.xml").getroot().find("oem").find("body").find("segment")
        state_vectors = result.find("data").findall("stateVector")
        raw_epoches = list(map(format_epoch, state_vectors))
        eph = load('de421.bsp')
        earth = eph['earth']
        sun = eph['sun']
        ts = load.timescale()

        epoches = []
        shadow_intervals = []
        shadow_start = None

        for i in range(len(raw_epoches) - 1):
            date = datetime.strptime(raw_epoches[i]['date'], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=utc)

            if len(epoches) == 0 or (date - epoches[-1]['date']).total_seconds() >= 60 * 4:
                epoches.append({
                    'date': date,
                    'location': raw_epoches[i]['location'],
                    'velocity': raw_epoches[i]['velocity']
                })

        spline_points = []
        for epoch in epoches:
            spline_points.append((epoch['location'][0], epoch['location'][1], epoch['location'][2]))

        curve = CatmullRom(spline_points)
        sat = []

        for i in range(len(epoches) - 1):
            start = epoches[i]['date']
            end = epoches[i + 1]['date']

            steps = max(1, int((end - start).total_seconds() // 5))

            for j in range(steps):
                t0 = i
                t1 = i + 1
                t = t0 + (t1 - t0) * (j / steps)
                pt = curve.evaluate(t)
                date = (start + timedelta(seconds=j * 5))

                if j == 0:
                    r, v = GCRF_to_ITRF(pt, epoches[i]['velocity'], date, earth_positions)
                    t = Topos_xyz(r[0], r[1], r[2])

                    # Calculate altitude from orbit parameters instead of using altaz
                    epos = earth.at(ts.from_datetime(date)).position.km
                    pos = (earth + Topos(t.latitude.degrees, t.longitude.degrees)).at(
                        ts.from_datetime(date)).position.km
                    er = np.sqrt(((pos - epos) ** 2).sum())

                    # Calculate altitude as distance from Earth's center minus Earth's radius
                    # Earth radius ~= 6371 km
                    point_distance = np.sqrt(r[0] ** 2 + r[1] ** 2 + r[2] ** 2)
                    altitude = point_distance - 6371  # approximate altitude in km

                    sat.append({
                        'date': date,
                        'location': r,
                        'altitude': altitude
                    })

                sun_m = earth.at(ts.from_datetime(date)).observe(sun).position.m
                in_shadow = is_in_shadow(sun_m, np.array([pt[0] * 1000, pt[1] * 1000, pt[2] * 1000]))
                if in_shadow == True and shadow_start is None:
                    shadow_start = date

                if in_shadow == False and shadow_start is not None:
                    shadow_intervals.append([shadow_start.timestamp(), date.timestamp()])
                    shadow_start = None

        if shadow_start is not None:
            shadow_intervals.append([shadow_start.timestamp(), epoches[-1]['date'].timestamp()])

        # Save data
        save_data(sat, shadow_intervals)

        # Update cache
        global _sat_data_cache, _shadow_intervals_cache, _updated_at_cache
        _sat_data_cache = sat
        _shadow_intervals_cache = shadow_intervals
        _updated_at_cache = datetime.now(utc)

        return sat
    except Exception as e:
        logger.error(f"Error generating satellite data: {e}")
        return []


def sat_data():
    """Get satellite data, either from cache or from files"""
    global _sat_data_cache, _shadow_intervals_cache, _updated_at_cache

    # If cache is empty, try to load from files
    if _sat_data_cache is None or _shadow_intervals_cache is None:
        loaded_sat_data, loaded_shadow_intervals, updated_at = load_data()

        # If files don't exist or are invalid, generate new data
        if loaded_sat_data is None or loaded_shadow_intervals is None:
            get_sat_data()
            # Try loading again after generation
            loaded_sat_data, loaded_shadow_intervals, updated_at = load_data()

            # If still no data, return empty data structure
            if loaded_sat_data is None or loaded_shadow_intervals is None:
                logger.error("Failed to generate or load satellite data")
                return {
                    "points": [],
                    "shadow_intervals": []
                }

    # Return data from cache
    return {
        "points": _sat_data_cache,
        "shadow_intervals": _shadow_intervals_cache
    }


def last_updated():
    """Get the timestamp of when the data was last updated"""
    global _updated_at_cache

    # If cache is empty, try to load from file
    if _updated_at_cache is None:
        try:
            with open(TIMESTAMP_FILE, 'r') as f:
                _updated_at_cache = datetime.fromisoformat(f.read().strip())
        except:
            # If file doesn't exist or is invalid, return None
            return None

    return _updated_at_cache.isoformat()