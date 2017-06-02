import hashlib
import logging
import math
import random
import time

import geopy
from pgoapi import PGoApi
from pgoapi.exceptions import AuthException
from pgoapi.protos.pogoprotos.inventory.item.item_id_pb2 import *

from pgscout.config import cfg_get
from pgscout.proxy import have_proxies, get_new_proxy

log = logging.getLogger(__name__)


class POGOAccount(object):

    def __init__(self, auth_service, username, password):
        self.auth_service = auth_service
        self.username = username
        self.password = password

        self._api = PGoApi(device_info=self._generate_device_info())
        self._api.activate_hash_server(cfg_get('hash_key'))

        self._proxy_url = None

        # Tutorial state and warn/ban flags
        self.player_state = {}

        # Trainer statistics
        self.player_stats = {}

        self.captcha_url = None

        # Inventory information
        self.inventory = None
        self.inventory_balls = 0
        self.inventory_total = 0

        # Timestamp when last API request was made
        self._last_request = None

        # Timestamp for incremental inventory updates
        self._last_timestamp_ms = None

        # Last log message (for GUI/console)
        self.last_msg = ""

    def set_position(self, lat, lng, alt):
        self._api.set_position(lat, lng, alt)

    def create_request(self):
        return self._api.create_request()

    def perform_request(self, prep_req, delay=12):
        # Wait before we perform the request
        d = float(delay)
        if self._last_request and time.time() - self._last_request < d:
            time.sleep(d - (time.time() - self._last_request))

        req = self.create_request()
        prep_req(req)
        req.check_challenge()
        req.get_hatched_eggs()
        self._add_get_inventory_request(req)
        req.check_awarded_badges()
        req.get_buddy_walked()
        return self._call_request(req)

    # Use API to check the login status, and retry the login if possible.
    def check_login(self):

        # Logged in? Enough time left? Cool!
        if self._api._auth_provider and self._api._auth_provider._ticket_expire:
            remaining_time = self._api._auth_provider._ticket_expire / 1000 - time.time()
            if remaining_time > 60:
                return True

        if have_proxies() and not self._proxy_url:
            self._proxy_url = get_new_proxy()
            self._api.set_proxy({
                'http': self._proxy_url,
                'https': self._proxy_url
            })
            self.log_info("Using proxy: {}".format(self._proxy_url))

        # Try to login. Repeat a few times, but don't get stuck here.
        num_tries = 0
        # One initial try + login_retries.
        while num_tries < cfg_get('login_retries'):
            try:
                num_tries += 1
                self.log_info("Login try {}.".format(num_tries))
                if self._proxy_url:
                    self._api.set_authentication(
                        provider=self.auth_service,
                        username=self.username,
                        password=self.password,
                        proxy_config={
                            'http': self._proxy_url,
                            'https': self._proxy_url
                        })
                else:
                    self._api.set_authentication(
                        provider=self.auth_service,
                        username=self.username,
                        password=self.password)
                self.log_info("Login successful after {} tries.".format(num_tries))
                break
            except AuthException:
                self.log_error(
                    'Failed to login. Trying again in {} seconds.'.format(
                        cfg_get('login_delay')))
                time.sleep(cfg_get('login_delay'))

        if num_tries >= cfg_get('login_retries'):
            self.log_error(
                'Failed to login in {} tries. Giving up.'.format(num_tries))
            return False
        return self._perform_after_login_steps()

    # Returns warning/banned flags and tutorial state.
    def update_player_state(self):
        request = self._api.create_request()
        request.get_player(
            player_locale={'country': 'US',
                           'language': 'en',
                           'timezone': 'America/Denver'})

        responses = self._call_request(request)

        get_player = responses.get('GET_PLAYER', {})
        self.player_state = {
            'tutorial_state': get_player.get('player_data', {}).get('tutorial_state', []),
            'warn': get_player.get('warn', False),
            'banned': get_player.get('banned', False)
        }

    def is_logged_in(self):
        # Logged in? Enough time left? Cool!
        if self._api._auth_provider and self._api._auth_provider._ticket_expire:
            remaining_time = self._api._auth_provider._ticket_expire / 1000 - time.time()
            return remaining_time > 60
        return False

    def is_warned(self):
        return None if not self.is_logged_in() else (
            self.player_state.get('warn') is True)

    def is_banned(self):
        return None if not self.is_logged_in() else (
            self.player_state.get('banned') is True)

    def has_captcha(self):
        return None if not self.is_logged_in() else (
            self.captcha_url and len(self.captcha_url) > 1)

    # =======================================================================

    def _generate_device_info(self):
        device_info = {
            'device_brand': 'Apple',
            'device_model': 'iPhone',
            'hardware_manufacturer': 'Apple',
            'firmware_brand': 'iPhone OS'
        }

        # Generate random device info.
        # Original by Noctem.
        IPHONES = {
            'iPhone5,1': 'N41AP',
            'iPhone5,2': 'N42AP',
            'iPhone5,3': 'N48AP',
            'iPhone5,4': 'N49AP',
            'iPhone6,1': 'N51AP',
            'iPhone6,2': 'N53AP',
            'iPhone7,1': 'N56AP',
            'iPhone7,2': 'N61AP',
            'iPhone8,1': 'N71AP',
            'iPhone8,2': 'N66AP',
            'iPhone8,4': 'N69AP',
            'iPhone9,1': 'D10AP',
            'iPhone9,2': 'D11AP',
            'iPhone9,3': 'D101AP',
            'iPhone9,4': 'D111AP'
        }
        devices = tuple(IPHONES.keys())

        IOS10_VERSIONS = ('10.1.1', '10.2.1', '10.3.2')

        # Make random numbers reproducible.
        local_random = random.Random()
        seed = int(hashlib.sha1(self.username).hexdigest(), 16)
        seed += cfg_get('random_seed_salt')
        local_random.seed(seed)

        device = local_random.choice(devices)
        device_info['device_model_boot'] = device
        device_info['hardware_model'] = IPHONES[device]
        device_info['device_id'] = '%032x' % local_random.randrange(16**32)
        device_info['firmware_type'] = local_random.choice(IOS10_VERSIONS)

        self.log_info("Using an {} on iOS {} with device ID {}".format(device,
            device_info['firmware_type'], device_info['device_id']))

        return device_info

    def _call_request(self, request):
        response = request.call()
        self._last_request = time.time()

        if not 'responses' in response:
            return {}

        # Return only the responses
        responses = response['responses']

        self._update_account_information(responses)

        return responses

    def _get_inventory_delta(self, inv_response):
        inventory_items = inv_response.get('inventory_delta', {}).get(
            'inventory_items', [])
        inventory = {}
        no_item_ids = (
            ITEM_UNKNOWN,
            ITEM_TROY_DISK,
            ITEM_X_ATTACK,
            ITEM_X_DEFENSE,
            ITEM_X_MIRACLE,
            ITEM_POKEMON_STORAGE_UPGRADE,
            ITEM_ITEM_STORAGE_UPGRADE
        )
        for item in inventory_items:
            iid = item.get('inventory_item_data', {})
            if 'item' in iid and iid['item']['item_id'] not in no_item_ids:
                item_id = iid['item']['item_id']
                count = iid['item'].get('count', 0)
                inventory[item_id] = count
            elif 'egg_incubators' in iid and 'egg_incubator' in iid['egg_incubators']:
                for incubator in iid['egg_incubators']['egg_incubator']:
                    item_id = incubator['item_id']
                    inventory[item_id] = inventory.get(item_id, 0) + 1
        return inventory

    def _update_inventory_totals(self):
        ball_ids = [
            ITEM_POKE_BALL,
            ITEM_GREAT_BALL,
            ITEM_ULTRA_BALL,
            ITEM_MASTER_BALL
        ]
        balls = 0
        total_items = 0
        for item_id in self.inventory:
            if item_id in ['total', 'balls']:
                continue
            if item_id in ball_ids:
                balls += self.inventory[item_id]
            total_items += self.inventory[item_id]
        self.inventory_balls = balls
        self.inventory_total = total_items

    def _update_account_information(self, responses):
        if 'GET_INVENTORY' in responses:
            api_inventory = responses['GET_INVENTORY']

            # Set an (empty) inventory if necessary
            if self.inventory is None:
                self.inventory = {}

            # Update inventory (balls, items)
            inventory_delta = self._get_inventory_delta(api_inventory)
            self.inventory.update(inventory_delta)
            self._update_inventory_totals()

            # Update stats (level, xp, encounters, captures, km walked, etc.)
            self._update_player_stats(api_inventory)

            # Update last timestamp for inventory requests
            self._last_timestamp_ms = api_inventory[
                'inventory_delta'].get('new_timestamp_ms', 0)

            # Cleanup
            del responses['GET_INVENTORY']

        # Check for captcha
        if 'CHECK_CHALLENGE' in responses:
            self.captcha_url = responses['CHECK_CHALLENGE'].get('challenge_url')


    def _add_get_inventory_request(self, request):
        if self._last_timestamp_ms:
            request.get_inventory(last_timestamp_ms=self._last_timestamp_ms)
        else:
            request.get_inventory()

    def _update_player_stats(self, api_inventory):
        inventory_items = api_inventory.get('inventory_delta', {}).get(
            'inventory_items', [])
        for item in inventory_items:
            item_data = item.get('inventory_item_data', {})
            if 'player_stats' in item_data:
                self.player_stats.update(item_data['player_stats'])

    def _perform_after_login_steps(self):
        time.sleep(random.uniform(2, 4))

        try:  # 0 - empty request
            request = self._api.create_request()
            self._call_request(request)
            time.sleep(random.uniform(.43, .97))
        except Exception as e:
            self.log_debug(
                'Login failed. Exception in call request: {}'.format(repr(e)))

        try:  # 1 - get_player
            # Get warning/banned flags and tutorial state.
            self.update_player_state()
            time.sleep(random.uniform(.53, 1.1))
        except Exception as e:
            self.log_debug(
                'Login failed. Exception in get_player: {}'.format(repr(e)))

        if self.player_state.get('banned'):
            self.log_error("Account BANNED! :-(((")
            return False

        # 2 - download_remote_config needed?

        try:  # 3 - get_player_profile
            request = self._api.create_request()
            request.get_player_profile()
            request.check_challenge()
            request.get_hatched_eggs()
            self._add_get_inventory_request(request)
            request.check_awarded_badges()
            request.download_settings()
            request.get_buddy_walked()
            self._call_request(request)
            time.sleep(random.uniform(.2, .3))
        except Exception as e:
            self.log_debug(
                'Login failed. Exception in ' + 'get_player_profile: {}'.format(
                    repr(e)))

        if self.has_captcha():
            self.log_error("Account CAPTCHA'd! :-|")
            return False

        try:  # 4 - level_up_rewards
            request = self._api.create_request()
            request.level_up_rewards(level=self.player_stats['level'])
            request.check_challenge()
            request.get_hatched_eggs()
            self._add_get_inventory_request(request)
            request.check_awarded_badges()
            request.download_settings()
            request.get_buddy_walked()
            self._call_request(request)
            time.sleep(random.uniform(.45, .7))
        except Exception as e:
            self.log_debug(
                'Login failed. Exception in level_up_rewards: {}'.format(
                    repr(e)))

        self.log_info('After-login procedure completed. Cooling down a bit...')
        time.sleep(random.uniform(10, 20))
        return True

    def jitter_location(self, lat, lng, maxMeters=10):
        origin = geopy.Point(lat, lng)
        b = random.randint(0, 360)
        d = math.sqrt(random.random()) * (float(maxMeters) / 1000)
        destination = geopy.distance.distance(kilometers=d).destination(origin,
                                                                        b)
        return (destination.latitude, destination.longitude)

    def log_info(self, msg):
        self.last_msg = msg
        log.info("[{}] {}".format(self.username, msg))

    def log_debug(self, msg):
        self.last_msg = msg
        log.debug("[{}] {}".format(self.username, msg))

    def log_warning(self, msg):
        self.last_msg = msg
        log.warning("[{}] {}".format(self.username, msg))

    def log_error(self, msg):
        self.last_msg = msg
        log.error("[{}] {}".format(self.username, msg))
