import json
import os

cfg = {}


def cfg_get(key):
    return cfg[key]


file_path = os.path.join('config.json')
with open(file_path, 'r') as f:
    cfg = json.loads(f.read())
