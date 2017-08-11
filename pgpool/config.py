import json
import os

# Configuration with default values
import configargparse

cfg = {
    'host': '127.0.0.1',
    'port': 4242,
    'db_host': 'localhost',
    'db_port': 3306,
    'db_name': '',
    'db_user': '',
    'db_pass': '',
    'db_max_connections': 20
}


def cfg_get(key, default=None):
    return cfg.get(key, default)


parser = configargparse.ArgParser()
parser.add_argument('-c', '--config',
                    help=('Specify different config file. Default: config.json'),
                    default='config.json')
args = parser.parse_args()

with open(args.config, 'r') as f:
    user_cfg = json.loads(f.read())
    cfg.update(user_cfg)
