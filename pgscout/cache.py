from threading import Lock

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
    # TODO
    pass