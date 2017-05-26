import json
import os

# Configuration with default values
cfg = {
    'host': '127.0.0.1',
    'port': 4242,
    'proxies_file': '',
    'require_min_trainer_level': 30,
    'login_retries': 3,
    'login_delay': 6
}


def cfg_get(key, default=None):
    return cfg.get(key, default)


file_path = os.path.join('config.json')
with open(file_path, 'r') as f:
    user_cfg = json.loads(f.read())
    cfg.update(user_cfg)
