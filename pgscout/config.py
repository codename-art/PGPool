import json
import os

# Configuration with default values
cfg = {
    'port': 4242,
    'proxies_file': '',
    'require_min_trainer_level': 30,
    'wait_after_login': 20
}


def cfg_get(key):
    return cfg[key]


file_path = os.path.join('config.json')
with open(file_path, 'r') as f:
    user_cfg = json.loads(f.read())
    cfg.update(user_cfg)
