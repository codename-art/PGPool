from threading import Lock

import time

cache_lock = Lock()
encounter_cache = {}


def get_cached_count():
    return len(encounter_cache)


def get_cached_encounter(encounter_id):
    return encounter_cache.get(encounter_id, False)


def cache_encounter(encounter_id, encounter_data):
    cache_lock.acquire()
    encounter_cache[encounter_id] = encounter_data
    cache_lock.release()


def cleanup_cache():
    # Remove all entries from encounter cache older than 1 hour.
    now = time.time()
    cache_lock.acquire()
    num_deleted = 0
    for encounter_id in encounter_cache.keys():
        encounter = encounter_cache[encounter_id]
        if now - encounter['encountered_time'] > 60 * 60:
            del encounter_cache[encounter_id]
            num_deleted += 1
    cache_lock.release()
    return num_deleted
