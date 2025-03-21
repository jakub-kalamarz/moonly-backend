# import numpy as np
# import xml.etree.ElementTree as ET
# from dotenv import load_dotenv
# from redis import Redis
# import os
# import pickle
# import numpy
# import requests
# from splines import CatmullRom
# from bs4 import BeautifulSoup
# from urllib.parse import urlencode, urlparse, urlunparse, parse_qs
#
#
# from skyfield.constants import AU_M
# from skyfield.positionlib import ICRS
# from skyfield.api import load
# from skyfield.toposlib import Topos
#
# from skyfield.api import utc
# from datetime import datetime, timedelta
# from services.helpers import (
#     format_epoch, GCRF_to_ITRF, earthPositions, Topos_xyz, linear_interpolation, download, is_in_shadow
# )
#
# load_dotenv()
#
# redis = Redis.from_url(os.getenv('REDIS_URL'))
#
# def get_sat_data():
#     download("https://nasa-public-data.s3.amazonaws.com/iss-coords/current/ISS_OEM/ISS.OEM_J2K_EPH.xml")
#     download("http://www.celestrak.com/SpaceData/EOP-All.txt")
#
#     earth_positions = earthPositions()
#     result = ET.parse("ISS.OEM_J2K_EPH.xml").getroot().find("oem").find("body").find("segment")
#     state_vectors = result.find("data").findall("stateVector")
#     raw_epoches = list(map(format_epoch, state_vectors))
#     eph = load('de421.bsp')
#     earth = eph['earth']
#     sun = eph['sun']
#     ts = load.timescale()
#
#     epoches = []
#     shadow_intervals = []
#     shadow_start = None
#     for i in range(len(raw_epoches) - 1):
#         date = datetime.strptime(raw_epoches[i]['date'], "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=utc)
#
#         if len(epoches) == 0 or (date - epoches[-1]['date']).total_seconds() >= 60 * 4:
#             epoches.append({
#                 'date': date,
#                 'location': raw_epoches[i]['location'],
#                 'velocity': raw_epoches[i]['velocity']
#             })
#
#     spline_points = []
#     for epoch in epoches:
#         spline_points.append((epoch['location'][0], epoch['location'][1], epoch['location'][2]))
#
#     curve = CatmullRom(spline_points)
#     sat = []
#     interpolated_sat = []
#
#     for i in range(len(epoches) - 1):
#         start = epoches[i]['date']
#         end = epoches[i + 1]['date']
#
#         steps = max(1, int((end - start).total_seconds() // 5))
#
#         for j in range(steps):
#             t0 = i
#             t1 = i + 1
#             t = t0 + (t1 - t0) * (j / steps)
#             pt = curve.evaluate(t)
#             date = (start + timedelta(seconds=j*5))
#
#             if j == 0:
#                 r, v = GCRF_to_ITRF(pt, epoches[i]['velocity'], date, earth_positions)
#                 t = Topos_xyz(r[0], r[1], r[2])
#
#                 epos = earth.at(ts.from_datetime(date)).position.km
#                 pos = (earth + Topos(t.latitude.degrees, t.longitude.degrees)).at(ts.from_datetime(date)).position.km
#                 er = numpy.sqrt(((pos - epos) ** 2).sum())
#                 sat.append({
#                     'date': date,
#                     'location': r,
#                     'altitude': ICRS((pt[0] * 1000 / AU_M, pt[1] * 1000 / AU_M,
#                                       pt[2] * 1000 / AU_M)).distance().km - er
#                 })
#
#             sun_m = earth.at(ts.from_datetime(date)).observe(sun).position.m
#             in_shadow = is_in_shadow(sun_m, np.array([pt[0] * 1000, pt[1] * 1000, pt[2] * 1000]))
#             if in_shadow == True and shadow_start is None:
#                 shadow_start = date
#
#             if in_shadow == False and shadow_start is not None:
#                 shadow_intervals.append([shadow_start.timestamp(), date.timestamp()])
#                 shadow_start = None
#
#     if shadow_start is not None:
#         shadow_intervals.append([shadow_start.timestamp(), epoches[-1]['date'].timestamp()])
#
#     redis.set('shadow_intervals', pickle.dumps(shadow_intervals))
#     # Save to temporary key to avoid blocking current value
#     redis.set('sat_data_new', pickle.dumps(sat))
#     redis.rename('sat_data_new', 'sat_data_not_interpolated')
#     redis.set('sat_data_updated_at', datetime.now(tz=utc).isoformat())
#     return interpolated_sat
