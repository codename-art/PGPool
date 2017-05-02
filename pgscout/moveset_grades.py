import json
import os

import requests
from bs4 import BeautifulSoup

from pgscout.utils import get_move_name

all_movesets = {}


# ===========================================================================


def read_moveset_grades():
    global all_movesets
    with open('pokemon_moveset_grades.json', 'r') as infile:
        all_movesets = json.load(infile)


def write_moveset_rankings():
    with open('pokemon_moveset_grades.json', 'w') as outfile:
        json.dump(all_movesets, outfile, indent=2)


def get_moveset_grades(pokemon_id, pokemon_name, move1, move2):
    global all_movesets
    if not pokemon_name in all_movesets:
        all_movesets[pokemon_name] = scrape_movesets(pokemon_id)
        write_moveset_rankings()

    movesets = all_movesets.get(pokemon_name, {})
    moveset_key = "{} / {}".format(get_move_name(move1), get_move_name(move2))
    empty_moveset = {
        'offense': '-',
        'defense': '-'
    }
    result = empty_moveset.copy()
    result.update(movesets.get(moveset_key, {}))
    return result


def scrape_movesets(pokemon_id):
    movesets = {}

    r = requests.get('https://pokemongo.gamepress.gg/pokemon/{}'.format(pokemon_id))
    soup = BeautifulSoup(r.text, "html.parser")

    result = soup.find_all('div', 'field-collection-item--name-field-recommend-offensive-moves')
    for r in result:
        parse_moveset(movesets, r, 'offense')

    result = soup.find_all('div', 'field-collection-item--name-field-recommended-defensive-move')
    for r in result:
        parse_moveset(movesets, r, 'defense')

    return movesets


def parse_moveset(movesets, row, stance):
    css_class = 'offensive' if stance == 'offense' else 'defensive'

    m1_el = row.find('div', 'field--name-field-{}-quick-move'.format(css_class))
    m2_el = row.find('div', 'field--name-field-{}-charge-move'.format(css_class))
    rating_el = row.find('div', 'move-rating')

    if m1_el and m2_el and rating_el:
        m1 = m1_el.a.text
        m2 = m2_el.a.text
        rating = rating_el.text
        moveset_key = "{} / {}".format(m1, m2)
        moveset = movesets.get(moveset_key, {})
        moveset[stance] = rating
        movesets[moveset_key] = moveset


# ===========================================================================


if os.path.isfile('pokemon_moveset_grades.json'):
    read_moveset_grades()
