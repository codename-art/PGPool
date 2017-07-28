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


def write_moveset_grades():
    with open('pokemon_moveset_grades.json', 'w') as outfile:
        json.dump(all_movesets, outfile, indent=2)


def get_moveset_grades(pokemon_id, pokemon_name, move1, move2):
    global all_movesets
    if not pokemon_name in all_movesets:
        all_movesets[pokemon_name] = scrape_movesets(pokemon_id)
        write_moveset_grades()

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
    try:
        movesets = {}
        r = requests.get('https://pokemongo.gamepress.gg/pokemon/{}'.format(pokemon_id))
        soup = BeautifulSoup(r.text, "html.parser")

        result = soup.find('div', 'view-moveset').div.table.tbody
        for row in result.find_all('tr'):
            qm_td = row.find('td', 'views-field-field-quick-move')
            qm = qm_td.article.h2.a.span.text

            cm_td = row.find('td', 'views-field-field-charge-move')
            cm = cm_td.article.h2.a.span.text

            off_grade_td = row.find('td', 'views-field-field-offensive-moveset-grade')
            off_grade = off_grade_td.div.text

            def_grade_td = row.find('td', 'views-field-field-defensive-moveset-grade')
            def_grade = def_grade_td.div.text

            moveset_key = "{} / {}".format(qm, cm)
            movesets[moveset_key] = {
                'offense': off_grade,
                'defense': def_grade
            }
        return movesets
    except:
        return {}


# ===========================================================================


if os.path.isfile('pokemon_moveset_grades.json'):
    read_moveset_grades()
