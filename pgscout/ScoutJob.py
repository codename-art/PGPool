import random

from pgscout.utils import get_pokemon_name


class ScoutJob(object):
    def __init__(self, pokemon_id, encounter_id, spawn_point_id, lat, lng):
        self.pokemon_id = int(pokemon_id)
        self.pokemon_name = get_pokemon_name(pokemon_id)
        self.encounter_id = encounter_id
        self.spawn_point_id = spawn_point_id
        self.lat = float(lat)
        self.lng = float(lng)
        self.processed = False
        self.result = {}

        # Use fixed random altitude per job
        self.altitude = random.randint(12, 108)