import requests_cache
from dateutil.parser import isoparse

from flask import Blueprint, jsonify, request, current_app
from ..services.sat_data import sat_data

sat_data()
requests_cache.install_cache(cache_name='local_cache', expire_after=3600)
bp = Blueprint('tracking', __name__, url_prefix='/tracking')

@bp.route('/iss-data-raw', methods=['POST'])
def getISSDataRaw():
  current_app.logger.error('**********')
  current_app.logger.error(request.json)

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

@bp.route('/iss-data', methods=['POST'])
def getISSData():
  current_app.logger.error('**********')
  current_app.logger.error(request.json)

  data = sat_data()

  start_dt = isoparse(request.json.get('from')) if request.json.get('from') is not None else None
  end_dt = isoparse(request.json.get('to')) if request.json.get('to') is not None else None

  res = []
  for position in data['points']:
    date = position['date']
    if (start_dt is not None and date < start_dt) or (end_dt is not None and date > end_dt):
      continue
    res.append(position)

  return jsonify({ 'points': res, 'shadowIntervals': data['shadow_intervals'] })