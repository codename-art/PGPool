import json
import os
import random

import math
from base64 import b64decode

import geopy.distance
import psutil


def rss_mem_size():
    process = psutil.Process(os.getpid())
    mem = process.memory_info().rss
    unit = 'bytes'
    if mem > 1024:
        unit = 'KB'
        mem /= 1024
    if mem > 1024:
        unit = 'MB'
        mem /= 1024
    if mem > 1024:
        unit = 'GB'
        mem /= 1024
    return "{:>4.1f} {}".format(mem, unit)


def normalize_encounter_id(eid):
    if not eid:
        return eid
    try:
        return long(eid)
    except:
        return long(b64decode(eid))


def normalize_spawn_point_id(sid):
    if not sid:
        return sid
    try:
        sid_int = int(sid)
        return "{:x}".format(sid_int)
    except:
        return sid


def get_pokemon_name(pokemon_id):
    if not hasattr(get_pokemon_name, 'pokemon'):
        file_path = os.path.join('pokemon.json')

        with open(file_path, 'r') as f:
            get_pokemon_name.pokemon = json.loads(f.read())
    return get_pokemon_name.pokemon[str(pokemon_id)]


def get_move_name(move_id):
    if not hasattr(get_move_name, 'mapping'):
        with open("pokemon_moves.json", 'r') as f:
            get_move_name.mapping = json.loads(f.read())
    return get_move_name.mapping.get(str(move_id))


def calc_pokemon_level(cp_multiplier):
    if cp_multiplier < 0.734:
        level = 58.35178527 * cp_multiplier * cp_multiplier - 2.838007664 * cp_multiplier + 0.8539209906
    else:
        level = 171.0112688 * cp_multiplier - 95.20425243
    level = (round(level) * 2) / 2.0
    return int(level)


def calc_iv(at, df, st):
    return float(at + df + st) / 45 * 100
