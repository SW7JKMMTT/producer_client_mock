#!/usr/bin/env python3
import logging
import begin
from faker import Factory
from urllib.parse import urljoin
import numpy as np
import requests
import pprint as pp
from datetime import timedelta
from haversine import haversine
import time
import os
import sys

fake = Factory.create('en_US')
base_path = "/services-1.0.0"
logging.getLogger("requests").setLevel(logging.WARNING)
logging.getLogger("requests").propagate = True

def make_new_user(server, superuser):
    su_auth_header = authenticate_user(server, superuser)
    password = fake.password()
    user_data = {
            "username" : fake.user_name(),
            "givenname": fake.first_name(),
            "surname"  : fake.last_name(),
            "password" : password
    }
    r = requests.post(server + '/user', json=user_data, headers=su_auth_header)
    if r.status_code is not 200:
        logging.info('\n--{:=^50}--\n{}'.format(' New User NOT Created ', r.json()['message']))
        sys.exit(1)
    logging.info('\n--{:=^50}--\n{}'.format(' New User Created ', pp.pformat(r.json())))
    return r.json()['username'], password

def authenticate_user(server, user):
    user_data = {"username": user[0], "password": user[1]}
    r = requests.post(server + '/auth', json=user_data)
    if r.status_code is not 200:
        logging.info('\n--{:=^50}--\n{}'.format(' User NOT Authenticated ', r.json()['message']))
        sys.exit(1)
    logging.info('\n--{:=^50}--\n{}'.format(' User Authenticated ', pp.pformat(r.json())))
    return {"Authorization": "Sleepy token=" + r.json()['token']}

def make_vehicle(server, auth_header):
    car_data = {
            "make" : fake.company(),
            "model" : fake.word().capitalize(),
            "vintage" : fake.year(),
            "vin" : fake.ean13()
    }
    r = requests.post(server + '/vehicle', json=car_data, headers=auth_header)
    if r.status_code is not 200:
        logging.info('\n--{:=^50}--\n{}'.format(' Vehicle NOT Created ', r.json()['message']))
        sys.exit(1)
    logging.info('\n--{:=^50}--\n{}'.format(' Vehicle Created ', pp.pformat(r.json())))
    return str(r.json()['id'])

def make_route(server, auth_header, vehicle_id):
    route_data = { "vehicleid": vehicle_id, "routeState": "CREATED" }
    r = requests.post(server + '/route', json=route_data, headers=auth_header)
    if r.status_code is not 200:
        logging.info('\n--{:=^50}--\n{}'.format(' Route NOT Created ', r.json()['message']))
        sys.exit(1)
    logging.info('\n--{:=^50}--\n{}'.format(' Route Created ', pp.pformat(r.json())))
    return str(r.json()['id'])

def change_route_state(server, auth_header, route_id, state):
    route_data = { "routeState": state }
    r = requests.put(server + '/route/' + route_id, json=route_data, headers=auth_header)
    if r.status_code is not 200:
        logging.info('\n--{:=^50}--\n{}'.format(' Route State NOT Changed ', r.json()['message']))
        sys.exit(1)
    logging.info('\n--{:=^50}--\n{}'.format(' Route State Changed ', pp.pformat(r.json())))

def make_waypoint(server, auth_header, route_id, latitude, longitude, timestamp):
    waypoint_data = {
            "latitude" : latitude,
            "longitude": longitude,
            "timestamp": int(timestamp * 1000)
    }
    r = requests.post(server + '/route/' + route_id + '/waypoint', json=waypoint_data, headers=auth_header)
    if r.status_code is not 200:
        logging.info('\n--{:=^50}--\n{}'.format(' Waypoint NOT Created ', r.json()['message']))
        raise Exception()
    # else:
        # logging.info('\n--{:=^50}--\n{}'.format(' Waypoint Created ', pp.pformat(r.json())))

def make_datapoint(server, auth_header, route_id, speed, fuellevel, timestamp):
    datapoint_data = {
            "vehicleDataPoints": [
                {
                    "type": "currentspeed",
                    "value": speed
                },
                {
                    "type": "fuellevel",
                    "value": fuellevel
                }
            ],
            "timestamp": int(timestamp * 1000)
    }
    r = requests.post(server + '/route/' + route_id + '/datapoint', json=datapoint_data, headers=auth_header)
    if r.status_code is not 200:
        logging.info('\n--{:=^50}--\n{}'.format(' Datapoint NOT Created ', r.json()['message']))
        raise Exception()
    # else:
        # logging.info('\n--{:=^50}--\n{}'.format(' Datapoint Created ', pp.pformat(r.json())))

def get_route_from_google_maps(start, end, force=False):
    import googlemaps
    import polyline
    if not 'GOOGLE_MAPS_API_KEY' in os.environ.keys():
        logging.info("Google Maps API Key must be in environment variables as: GOOGLE_MAPS_API_KEY")
        sys.exit(0)
    api_key = os.environ['GOOGLE_MAPS_API_KEY']
    gmaps = googlemaps.Client(key=api_key)
    try:
        directions = gmaps.directions(start, end, mode="driving", alternatives=True)
    except Exception as e:
        logging.info("ERROR: ", str(e))
        sys.exit(1)
    route = None
    if not force and len(directions) > 1:
        logging.info("Multiple routes found.\nChoose one:")
        for i, route in enumerate(directions):
            distance = sum([leg['distance']['value'] for leg in route['legs']])
            logging.info('  {}. {} ({:.2f} km)'.format(i, route['summary'], distance / 1000))
        while True:
            choice = input('Choose #: ')
            if choice.isdigit() and int(choice) in range(len(directions)):
                route = directions[int(choice)]
                break
    else:
        route = directions[0]
    duration = 0
    coordinates = []
    for leg in route['legs']:
        for step in leg['steps']:
            pline = step['polyline']['points']
            points = polyline.decode(pline)
            times = [duration]
            for i, point in enumerate(points[1:]):
                percent_distance = (haversine(points[i], point) * 1000) / step['duration']['value']
                times.append(duration + (step['duration']['value'] * percent_distance))
            times = np.linspace(duration, duration + step['duration']['value'], len(points))
            duration += step['duration']['value']
            coordinates.extend(zip(points, times))
    return coordinates, duration, sum([leg['distance']['value'] for leg in route['legs']])

@begin.start(auto_convert=True)
@begin.logging
def main(server: 'URL of the server' = "http://sw708e16.cs.aau.dk",
         user: 'If not supplied a new user will be made' = (None, None),
         superuser: 'Used to make new user' = ("deadpool", "hunter2"),
         delay: 'Delay between POSTing waypoints' = 1.0,
         x_factor: 'Speed factor' = 1.0,
         start: 'coordinates or address of starting point' = None,
         end: 'coordinates or address of ending point' = None,
         non_interactive: 'Disable user input (force choices to first)' = False,
         calc_speed_steps: 'Number of data steps to include in speed calculation' = 4):
    if start and end:
        coordinates, duration, distance = get_route_from_google_maps(start, end, force=non_interactive)
    else:
        print("You must define start and end points.")
        sys.exit(1)
    server = urljoin(server, base_path)
    logging.info(server)
    duration = duration * (1/x_factor)
    if user[0] is None:
        user = make_new_user(server, superuser)
    auth_header = authenticate_user(server, user)
    vehicle_id = make_vehicle(server, auth_header)
    route_id = make_route(server, auth_header, vehicle_id)
    change_route_state(server, auth_header, route_id, "ACTIVE")

    lats = np.array([p[0] for p, t in coordinates])
    lons = np.array([p[1] for p, t in coordinates])
    times = np.array([t * (1/x_factor) for p, t in coordinates])
    s = time.time()
    i = 0
    logging.info('\n--{:=^50}--\nDuration {}, Distance {:.2f} km, Avg. speed {:.2f} km/h'.format(' DRIVING ', timedelta(seconds=int(duration)), distance/1000, (distance/duration)*3.6))
    try:
        while True:
            _t = time.time()
            t = (_t - s) * x_factor
            if t > times[-1]:
                break
            lat = np.interp(t, times, lats)
            lon = np.interp(t, times, lons)
            s_idx = np.searchsorted(times, t)
            e_idx = min((s_idx + calc_speed_steps, len(times) - 1))
            t_delta = times[e_idx] - t
            r_delta = [(lat, lon)]
            r_delta.extend([(la, lo) for la, lo in zip(lats[s_idx:e_idx], lons[s_idx:e_idx])])
            dist = sum([haversine((r_delta[j][0], r_delta[j][1]), (r_delta[j+1][0], r_delta[j+1][1])) for j in range(len(r_delta) - 1)]) * 1000.
            speed = dist / t_delta
            fuellevel = 100 - ((t / 60) % 100)
            make_datapoint(server, auth_header, route_id, speed=speed, fuellevel=fuellevel, timestamp=_t)
            make_waypoint(server, auth_header, route_id, latitude=lat, longitude=lon, timestamp=_t)
            i += 1
            logging.debug('Must travel {:.2f} m, at {:.2f} km/h, in {:.2f} s [fuel {:.1f} %]'.format(dist, speed * 3.6, t_delta, fuellevel))
            print('{} points made | estimated time left: {}'.format(i, timedelta(seconds= int(duration - (_t - s)))), end='\r')
            if time.time() - _t < delay:
                time.sleep(max((delay - (time.time() - _t),0)))
    except KeyboardInterrupt:
        pass
    print("")
    change_route_state(server, auth_header, route_id, "COMPLETE")
