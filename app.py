from flask import Flask, jsonify, request
import os
from datetime import datetime
from dateutil.parser import isoparse
import logging
from services.data_store import initialize_data_store

# At application startup
initialize_data_store()

# Import our data handler
from services.data_store import get_sat_data
from services.sat_data import sat_data

app = Flask(__name__)
logging.basicConfig(level=logging.INFO)

@app.route('/')
def hello_world():
    return 'Hello, World!'

@app.route('/tracking/iss-data-raw', methods=['POST'])
def get_iss_data_raw():
    app.logger.info('Received request for raw ISS data')
    app.logger.info(request.json)

    data = sat_data()

    start_dt = isoparse(request.json.get('from')) if request.json.get('from') is not None else None
    end_dt = isoparse(request.json.get('to')) if request.json.get('to') is not None else None

    res = []
    for position in data['points']:
        date = position['date']
        if (start_dt is not None and date < start_dt) or (end_dt is not None and date > end_dt):
            continue
        res.append(position)

    return jsonify(res)

@app.route('/tracking/iss-data', methods=['POST'])
def get_iss_data():
    app.logger.info('Received request for ISS data with shadow intervals')
    app.logger.info(request.json)

    data = sat_data()

    start_dt = isoparse(request.json.get('from')) if request.json.get('from') is not None else None
    end_dt = isoparse(request.json.get('to')) if request.json.get('to') is not None else None

    res = []
    for position in data['points']:
        date = position['date']
        if (start_dt is not None and date < start_dt) or (end_dt is not None and date > end_dt):
            continue
        res.append(position)

    return jsonify({'points': res, 'shadowIntervals': data['shadow_intervals']})

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)