import logging
import sys
import time
from base64 import b64decode, b64encode
from collections import deque

import geopy
from pgoapi import PGoApi
from pgoapi.exceptions import AuthException
from pgoapi.utilities import get_cell_ids, f2i

from pgscout.config import cfg_get
from pgscout.moveset_grades import get_moveset_grades
from pgscout.stats import inc_for_pokemon
from pgscout.utils import jitter_location, TooManyLoginAttempts, has_captcha, calc_pokemon_level, \
    get_player_level, calc_iv

log = logging.getLogger(__name__)


class Scout(object):
    def __init__(self, auth, username, password, job_queue):
        self.auth = auth
        self.username = username
        self.password = password
        self.job_queue = job_queue

        # Stats
        self.last_request = None
        self.last_msg = ""
        self.total_scouts = 0

        # Holds timestamps of scout requests of the last hour
        self.history = deque()

        # instantiate pgoapi
        self.api = PGoApi()
        self.api.activate_hash_server(cfg_get('hash_key'))

    def run(self):
        self.log_info("Waiting for job...")
        while True:
            job = self.job_queue.get()
            try:
                self.log_info(u"Scouting a {} at {}, {}".format(job.pokemon_name, job.lat, job.lng))
                # Initialize API
                (lat, lng, alt) = jitter_location([job.lat, job.lng, job.altitude])
                self.api.set_position(lat, lng, alt)
                self.check_login()

                if job.encounter_id and job.spawn_point_id:
                    job.result = self.scout_by_encounter_id(job)
                else:
                    if self.find_pokemon(job):
                        job.result = self.scout_by_encounter_id(job)
                    else:
                        job.result = self.scout_error("Could not determine encounter_id for {} at {}, {}".format(job.pokemon_name, job.lat, job.lng))
            except:
                job.result = self.scout_error(repr(sys.exc_info()))
            finally:
                job.processed = True
                self.update_history()

    def log_info(self, msg):
        self.last_msg = msg
        log.info(msg)

    def log_debug(self, msg):
        self.last_msg = msg
        log.debug(msg)

    def log_warning(self, msg):
        self.last_msg = msg
        log.warning(msg)

    def log_error(self, msg):
        self.last_msg = msg
        log.error(msg)

    def update_history(self):
        now = time.time()
        self.history.append(now)
        earliest = self.history[0]
        while now - earliest > 60*60:
            self.history.popleft()
            earliest = self.history[0]
        self.total_scouts += 1

    def parse_wild_pokemon(self, response):
        wild_pokemon = []
        cells = response.get('responses', {}).get('GET_MAP_OBJECTS', {}).get('map_cells', [])
        for cell in cells:
            wild_pokemon += cell.get('wild_pokemons', [])
        return wild_pokemon

    def find_pokemon(self, job):
        tries = 0
        max_tries = 3
        wild_pokemon = []
        while tries < max_tries:
            tries += 1
            try:
                (lat, lng, alt) = self.jittered_location(job)
                self.log_info("Looking for {} at {}, {} - try {}".format(job.pokemon_name, lat, lng, tries))
                cell_ids = get_cell_ids(lat, lng)
                timestamps = [0, ] * len(cell_ids)
                req = self.api.create_request()
                req.get_map_objects(latitude=f2i(lat),
                                    longitude=f2i(lng),
                                    since_timestamp_ms=timestamps,
                                    cell_id=cell_ids)
                response = self.perform_request(req)

                wild_pokemon = self.parse_wild_pokemon(response)
                if len(wild_pokemon) > 0:
                    break
            except Exception as e:
                self.log_error('Exception on GMO try {}: {}'.format(tries, repr(e)))

        if len(wild_pokemon) == 0:
            self.log_info("Still no wild Pokemon found. Giving up.")
            return False

        # find all pokemon with desired id
        candidates = filter(lambda pkm: pkm['pokemon_data']['pokemon_id'] == job.pokemon_id, wild_pokemon)

        target = None
        if len(candidates) == 1:
            # exactly one pokemon of this id found
            target = candidates[0]
        elif len(candidates) > 1:
            # multiple pokemon found, pick one with lowest distance to search position
            loc = (job.lat, job.lng)
            min_dist = False
            for pkm in candidates:
                d = geopy.distance.distance(loc, (pkm["latitude"], pkm["longitude"])).meters
                if not min_dist or d < min_dist:
                    min_dist = d
                    target = pkm

        # no pokemon found
        if target is None:
            self.log_info("No wild {} found at {}, {}.".format(job.pokemon_name, lat, lng))
            return False

        # now set encounter id and spawn point id
        self.log_info("Got encounter_id for {} at {}, {}.".format(job.pokemon_name, target['latitude'], target['longitude']))
        job.encounter_id = b64encode(str(target['encounter_id']))
        job.spawn_point_id = target["spawn_point_id"]
        return True

    def scout_by_encounter_id(self, job):
        (lat, lng, alt) = self.jittered_location(job)

        self.log_info("Performing encounter request at {}, {}".format(lat, lng))
        response = self.encounter_request(job.encounter_id, job.spawn_point_id, lat,
                                          lng)

        return self.parse_encounter_response(response, job.pokemon_id, job.pokemon_name)

    def parse_encounter_response(self, response, pokemon_id, pokemon_name):
        if response is None:
            return self.scout_error("Encounter response is None.")

        if has_captcha(response):
            return self.scout_error("Scout account captcha'd.")

        encounter = response.get('responses', {}).get('ENCOUNTER', {})

        if encounter.get('status', None) == 3:
            return self.scout_error("Pokemon already despawned.")

        if 'wild_pokemon' not in encounter:
            return self.scout_error("No wild pokemon info found.")

        scout_level = get_player_level(response)
        if scout_level < cfg_get("require_min_trainer_level"):
            return self.scout_error(
                "Trainer level {} is too low. Needs to be {}+".format(scout_level, cfg_get("require_min_trainer_level")))

        pokemon_info = encounter['wild_pokemon']['pokemon_data']
        cp = pokemon_info['cp']
        pokemon_level = calc_pokemon_level(pokemon_info['cp_multiplier'])
        probs = encounter['capture_probability']['capture_probability']

        at = pokemon_info.get('individual_attack', 0)
        df = pokemon_info.get('individual_defense', 0)
        st = pokemon_info.get('individual_stamina', 0)
        iv = calc_iv(at, df, st)
        moveset_grades = get_moveset_grades(pokemon_id, pokemon_name, pokemon_info['move_1'], pokemon_info['move_2'])

        response = {
            'success': True,
            'height': pokemon_info['height_m'],
            'weight': pokemon_info['weight_kg'],
            'gender': pokemon_info['pokemon_display']['gender'],
            'iv_percent': iv,
            'iv_attack': at,
            'iv_defense': df,
            'iv_stamina': st,
            'move_1': pokemon_info['move_1'],
            'move_2': pokemon_info['move_2'],
            'rating_attack': moveset_grades['offense'],
            'rating_defense': moveset_grades['defense'],
            'cp': cp,
            'level': pokemon_level,
            'catch_prob_1': probs[0],
            'catch_prob_2': probs[1],
            'catch_prob_3': probs[2],
            'scout_level': scout_level,
            'encountered_time': time.time()
        }
        self.log_info(u"Found a {:.1f}% ({}/{}/{}) L{} {} with {} CP (scout level {}).".format(iv, at, df, st, pokemon_level,
                                                                                  pokemon_name, cp, scout_level))
        inc_for_pokemon(pokemon_id)
        return response

    def check_login(self):
        # Logged in? Enough time left? Cool!
        if self.api._auth_provider and self.api._auth_provider._ticket_expire:
            remaining_time = self.api._auth_provider._ticket_expire / 1000 - time.time()
            if remaining_time > 60:
                self.log_debug(
                    'Credentials remain valid for another {} seconds.'.format(remaining_time))
                return

        # Try to login. Repeat a few times, but don't get stuck here.
        num_tries = 0
        # One initial try + login_retries.
        while num_tries < 3:
            try:
                self.api.set_authentication(
                    provider=self.auth,
                    username=self.username,
                    password=self.password)
                break
            except AuthException:
                num_tries += 1
                self.log_error(
                    'Failed to login. ' +
                    'Trying again in {} seconds.'.format(6))
                time.sleep(6)

        if num_tries >= 3:
            self.log_error(
                'Failed to login for {} tries. Giving up.'.format(
                    num_tries))
            raise TooManyLoginAttempts('Exceeded login attempts.')

        self.log_debug('Login successful. Waiting 20 more seconds.')
        time.sleep(20)

    def encounter_request(self, encounter_id, spawn_point_id, latitude, longitude):
        req = self.api.create_request()
        req.encounter(
            encounter_id=long(b64decode(encounter_id)),
            spawn_point_id=spawn_point_id,
            player_latitude=float(latitude),
            player_longitude=float(longitude))
        return self.perform_request(req)

    def perform_request(self, req, delay=12):
        req.check_challenge()
        req.get_hatched_eggs()
        req.get_inventory()
        req.check_awarded_badges()
        req.download_settings()
        req.get_buddy_walked()
        d = float(delay)
        if self.last_request and time.time() - self.last_request < d:
            time.sleep(d - (time.time() - self.last_request))
        response = req.call()
        self.last_request = time.time()
        return response

    def scout_error(self, error_msg):
        self.log_error("Error: {}".format(error_msg))
        return {
            'success': False,
            'error': error_msg
        }

    def jittered_location(self, job):
        (lat, lng, alt) = jitter_location([job.lat, job.lng, job.altitude])
        self.api.set_position(lat, lng, alt)
        return lat, lng, alt
