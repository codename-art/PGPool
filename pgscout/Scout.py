import logging
import time
from base64 import b64encode
from collections import deque

import geopy
from mrmime.pogoaccount import POGOAccount
from mrmime.utils import jitter_location
from pgoapi.protos.pogoprotos.networking.responses.encounter_response_pb2 import *
from pgoapi.utilities import get_cell_ids, f2i

from pgscout.config import cfg_get
from pgscout.moveset_grades import get_moveset_grades
from pgscout.stats import inc_for_pokemon
from pgscout.utils import calc_pokemon_level, calc_iv

log = logging.getLogger(__name__)


# Collect this many samples to determine an encounters/hour value.
NUM_PAUSE_SAMPLES = 3

ENCOUNTER_RESULTS = {
    0: "ENCOUNTER_ERROR",
    1: "ENCOUNTER_SUCCESS",
    2: "ENCOUNTER_NOT_FOUND",
    3: "ENCOUNTER_CLOSED",
    4: "ENCOUNTER_POKEMON_FLED",
    5: "ENCOUNTER_NOT_IN_RANGE",
    6: "ENCOUNTER_ALREADY_HAPPENED",
    7: "POKEMON_INVENTORY_FULL",
    8: "ENCOUNTER_BLOCKED_BY_ANTICHEAT"
}


class Scout(POGOAccount):
    def __init__(self, auth, username, password, job_queue, hash_key_provider, proxy_provider):
        super(Scout, self).__init__(auth, username, password,
                                    hash_key_provider=hash_key_provider, proxy_provider=proxy_provider)

        self.job_queue = job_queue
        self.shadowbanned = False
        self.active = True

        # Stats
        self.previous_encounter = None
        self.total_encounters = 0

        # Collects the last few pauses between encounters to measure a "encounters per hour" value
        self.past_pauses = deque()
        self.encounters_per_hour = float(0)

    def run(self):
        self.log_info("Waiting for job...")
        while True:
            if self.shadowbanned:
                self.log_warning("Account shadowbanned. Stopping.")
                break

            job = self.job_queue.get()
            try:
                self.log_info(u"Scouting a {} at {}, {}".format(job.pokemon_name, job.lat, job.lng))
                # Initialize API
                (lat, lng) = jitter_location(job.lat, job.lng)
                self.set_position(lat, lng, job.altitude)
                if not self.check_login():
                    job.result = self.scout_error(self.last_msg)
                    continue

                # Check if banned.
                if self.is_banned():
                    job.result = self.scout_error("Account banned")
                    break

                if job.encounter_id and job.spawn_point_id:
                    job.result = self.scout_by_encounter_id(job)
                else:
                    if self.find_pokemon(job):
                        job.result = self.scout_by_encounter_id(job)
                    else:
                        job.result = self.scout_error("Could not determine encounter_id for {} at {}, {}".format(job.pokemon_name, job.lat, job.lng))
            except :
                job.result = self.scout_error(repr(sys.exc_info()))
            finally:
                job.processed = True
                self.update_history()

        # We broke out of the main loop, so something is f*cked up with this scout.
        self.active = False

    def update_history(self):
        if self.previous_encounter:
            # Determine current pause
            now = time.time()
            pause = now - self.previous_encounter
            self.past_pauses.append(pause)
            if len(self.past_pauses) > NUM_PAUSE_SAMPLES:
                self.past_pauses.popleft()
            avg_pause = reduce(lambda x, y: x + y, self.past_pauses) / len(
                self.past_pauses)
            self.encounters_per_hour = 3600 / avg_pause

        self.total_encounters += 1
        self.previous_encounter = time.time()

    def parse_wild_pokemon(self, responses):
        wild_pokemon = []
        cells = responses.get('GET_MAP_OBJECTS', {}).get('map_cells', [])
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
                (lat, lng) = self.jittered_location(job)
                self.log_info("Looking for {} at {}, {} - try {}".format(job.pokemon_name, lat, lng, tries))
                cell_ids = get_cell_ids(lat, lng)
                timestamps = [0, ] * len(cell_ids)
                response = self.perform_request(
                    lambda req: req.get_map_objects(latitude=f2i(lat),
                                                    longitude=f2i(lng),
                                                    since_timestamp_ms=timestamps,
                                                    cell_id=cell_ids))

                wild_pokemon = self.parse_wild_pokemon(response)
                if len(wild_pokemon) > 0:
                    break
            except Exception as e:
                self.log_error('Exception on GMO try {}: {}'.format(tries, repr(e)))

        if len(wild_pokemon) == 0:
            self.log_info("Still no wild Pokemon found. Giving up.")
            return False

        # find all pokemon with desired id
        candidates = filter(
            lambda pkm: pkm['pokemon_data']['pokemon_id'] == job.pokemon_id,
            wild_pokemon)

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
        job.encounter_id = target['encounter_id']
        job.spawn_point_id = target["spawn_point_id"]
        return True

    def scout_by_encounter_id(self, job):
        (lat, lng) = self.jittered_location(job)

        self.log_info("Performing encounter request at {}, {}".format(lat, lng))
        responses = self.perform_request(lambda req: req.encounter(
            encounter_id=job.encounter_id,
            spawn_point_id=job.spawn_point_id,
            player_latitude=float(lat),
            player_longitude=float(lng)))
        return self.parse_encounter_response(responses, job)

    def parse_encounter_response(self, responses, job):
        if not responses:
            return self.scout_error("Empty encounter response.")

        if self.has_captcha():
            return self.scout_error("Scout account captcha'd.")

        encounter = responses.get('ENCOUNTER', {})
        enc_status = encounter.get('status', None)

        # Check for shadowban - ENCOUNTER_BLOCKED_BY_ANTICHEAT
        if enc_status == 8:
            self.shadowbanned = True

        if enc_status != 1:
            return self.scout_error(ENCOUNTER_RESULTS[enc_status])

        if 'wild_pokemon' not in encounter:
            return self.scout_error("No wild pokemon info found.")

        scout_level = self.player_stats['level']
        if scout_level < cfg_get("require_min_trainer_level"):
            return self.scout_error(
                "Trainer level {} is too low. Needs to be {}+".format(
                    scout_level, cfg_get("require_min_trainer_level")))

        pokemon_info = encounter['wild_pokemon']['pokemon_data']
        cp = pokemon_info['cp']
        pokemon_level = calc_pokemon_level(pokemon_info['cp_multiplier'])
        probs = encounter['capture_probability']['capture_probability']

        at = pokemon_info.get('individual_attack', 0)
        df = pokemon_info.get('individual_defense', 0)
        st = pokemon_info.get('individual_stamina', 0)
        iv = calc_iv(at, df, st)
        moveset_grades = get_moveset_grades(job.pokemon_id, job.pokemon_name,
                                            pokemon_info['move_1'],
                                            pokemon_info['move_2'])

        responses = {
            'success': True,
            'encounter_id': job.encounter_id,
            'encounter_id_b64': b64encode(str(job.encounter_id)),
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
            'cp_multiplier': pokemon_info['cp_multiplier'],
            'level': pokemon_level,
            'catch_prob_1': probs[0],
            'catch_prob_2': probs[1],
            'catch_prob_3': probs[2],
            'scout_level': scout_level,
            'encountered_time': time.time()
        }

        # Add form of Unown
        if job.pokemon_id == 201:
            responses['form'] = pokemon_info['pokemon_display'].get('form',
                                                                    None)

        self.log_info(
            u"Found a {:.1f}% ({}/{}/{}) L{} {} with {} CP (scout level {}).".format(
                iv, at, df, st, pokemon_level, job.pokemon_name, cp, scout_level))
        inc_for_pokemon(job.pokemon_id)
        return responses

    def scout_error(self, error_msg):
        self.log_error("Error: {}".format(error_msg))
        return {
            'success': False,
            'error': error_msg
        }

    def jittered_location(self, job):
        (lat, lng) = jitter_location(job.lat, job.lng)
        self.set_position(lat, lng, job.altitude)
        return lat, lng
