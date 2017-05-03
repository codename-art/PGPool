from threading import Lock

statistics = {
    # Maps Pokemon ID to total number of scouts for this Pokemon type
    'pokemon': {}
}
stats_lock = Lock()

def inc_for_pokemon(pokemon_id):
    stats_lock.acquire()
    num = statistics['pokemon'].get(pokemon_id, 0)
    num += 1
    statistics['pokemon'][pokemon_id] = num
    stats_lock.release()


def get_pokemon_stats():
    stats_lock.acquire()
    pstats = map(lambda (pid, count): {'pid': pid, 'count': count},
                 statistics['pokemon'].items())
    stats_lock.release()
    pstats.sort(key=lambda x: x['pid'])
    return pstats
