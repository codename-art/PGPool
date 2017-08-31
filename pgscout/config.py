# Configuration with default values
import logging
import sys

import configargparse
from mrmime import init_mr_mime
from mrmime.cyclicresourceprovider import CyclicResourceProvider

from pgscout.proxy import check_proxies

log = logging.getLogger(__name__)

args = None


def cfg_get(key, default=None):
    global args
    return getattr(args, key)


def parse_args():
    global args
    defaultconfigfiles = []
    if '-c' not in sys.argv and '--config' not in sys.argv:
        defaultconfigfiles = ['config.ini']

    parser = configargparse.ArgParser(
        default_config_files=defaultconfigfiles)

    parser.add_argument('-c', '--config',
                        is_config_file=True, help='Specify configuration file.')

    parser.add_argument('-hs', '--host', default='127.0.0.1',
                        help='Host or IP to bind to.')

    parser.add_argument('-p', '--port', type=int, default=4242,
                        help='Port to bind to.')

    parser.add_argument('-hk', '--hash-key', required=True, action='append',
                        help='Hash key to use.')

    parser.add_argument('-pf', '--proxies-file',
                        help='Load proxy list from text file (one proxy per line).')

    parser.add_argument('-l', '--level', type=int, default=30,
                        help='Minimum trainer level required. Lower levels will yield an error.')

    parser.add_argument('-sb', '--shadowban-threshold', type=int, default=5,
                        help='Mark an account as shadowbanned after this many errors. ' +
                             'If --pgpool_url is specified the account gets swapped out.')

    parser.add_argument('-pgpu', '--pgpool-url',
                        help='Address of PGPool to load accounts from and/or update their details.')

    parser.add_argument('-pgpsid', '--pgpool-system-id',
                        help='System ID for PGPool. Required if --pgpool-url given.')

    accs = parser.add_mutually_exclusive_group(required=True)
    accs.add_argument('-pgpn', '--pgpool-num-accounts', type=int, default=0,
                      help='Use this many L30+ accounts from PGPool. --pgpool-url required.')

    accs.add_argument('-a', '--accounts-file',
                      help='Load accounts from CSV file containing "auth_service,username,passwd" lines.')

    args = parser.parse_args()


def init_resoures_from_file(resource_file):
    resources = []
    if resource_file:
        try:
            with open(resource_file) as f:
                for line in f:
                    # Ignore blank lines and comment lines.
                    if len(line.strip()) == 0 or line.startswith('#'):
                        continue
                    resources.append(line.strip())
        except IOError:
            log.exception('Could not load {} from {}.'.format(resource_file))
            exit(1)
    return resources


def cfg_init():
    log.info("Loading PGScout configuration...")

    parse_args()

    # MrMime config
    mrmime_cfg = {
        'pgpool_system_id': args.pgpool_system_id
    }
    if args.pgpool_url:
        mrmime_cfg['pgpool_url'] = args.pgpool_url
        log.info("Attaching to PGPool at {}".format(args.pgpool_url))
    init_mr_mime(mrmime_cfg)

    # Collect hash keys
    args.hash_key_provider = CyclicResourceProvider()
    for hk in args.hash_key:
        args.hash_key_provider.add_resource(hk)

    # Collect proxies
    args.proxies = check_proxies(cfg_get('proxies_file'))
    args.proxy_provider = CyclicResourceProvider()
    for proxy in args.proxies:
        args.proxy_provider.add_resource(proxy)


def use_pgpool():
    return bool(args.pgpool_url and args.pgpool_system_id and args.pgpool_num_accounts > 0)

