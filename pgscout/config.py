import json

# Configuration with default values
import configargparse

cfg = {
    'host': '127.0.0.1',
    'port': 4242,
    'proxies_file': '',
    'require_min_trainer_level': 30
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
