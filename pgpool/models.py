import logging
import time
from datetime import datetime
from timeit import default_timer

import copy
from peewee import DateTimeField, CharField, SmallIntegerField, IntegerField, \
    DoubleField, BooleanField, InsertQuery, Model
from playhouse.flask_utils import FlaskDB
from playhouse.pool import PooledMySQLDatabase
from playhouse.shortcuts import RetryOperationalError

from pgpool.config import cfg_get

log = logging.getLogger(__name__)

flaskDb = FlaskDB()


class MyRetryDB(RetryOperationalError, PooledMySQLDatabase):
    pass


  # "GET_INBOX": {
  #   "result": 1,
  #   "inbox": {
  #     "builtin_variables": [
  #       {
  #         "literal": "tryecvio32",
  #         "name": "CODE_NAME"
  #       },
  #       {
  #         "name": "TEAM",
  #         "key": "UNSET"
  #       },
  #       {
  #         "literal": "8",
  #         "name": "LEVEL"
  #       },
  #       {
  #         "literal": "34740",
  #         "name": "EXPERIENCE"
  #       },
  #       {
  #         "literal": "0",
  #         "name": "POKECOIN_BALANCE"
  #       },
  #       {
  #         "literal": "1500",
  #         "name": "STARDUST_BALANCE"
  #       },
  #       {
  #         "literal": "starshine4815+tryecvio32@gmail.com",
  #         "name": "EMAIL"
  #       },
  #       {
  #         "literal": "Pokemon Trainer Club",
  #         "name": "LOGIN_METHOD"
  #       }
  #     ]
  #   }
  # },

class Account(flaskDb.Model):
    auth_service = CharField(max_length=6, default='ptc')
    username = CharField(primary_key=True)
    password = CharField(null=True)
    email = CharField(null=True)
    last_modified = DateTimeField(index=True, default=datetime.utcnow)
    system_id = CharField(index=True, null=True)       # system which uses the account
    latitude = DoubleField(null=True)
    longitude = DoubleField(null=True)
    # from player_stats
    level = SmallIntegerField(index=True, null=True)
    xp = IntegerField(null=True)
    encounters = IntegerField(null=True)
    balls_thrown = IntegerField(null=True)
    captures = IntegerField(null=True)
    spins = IntegerField(null=True)
    walked = DoubleField(null=True)
    # from get_inbox
    team = CharField(max_length=16, null=True)
    coins = IntegerField(null=True)
    stardust = IntegerField(null=True)
    # account health
    warn = BooleanField(null=True)
    banned = BooleanField(index=True, null=True)
    ban_flag = BooleanField(null=True)
    tutorial_state = CharField(null=True) # a CSV-list of tutorial steps completed
    captcha = BooleanField(index=True, null=True)
    rareless_scans = IntegerField(index=True, null=True)
    shadowbanned = BooleanField(index=True, null=True)
    # inventory info
    balls = SmallIntegerField(null=True)
    total_items = SmallIntegerField(null=True)
    pokemon = SmallIntegerField(null=True)
    eggs = SmallIntegerField(null=True)
    incubators = SmallIntegerField(null=True)
    # other fields
    awarded_to_level = SmallIntegerField(null=True)

    @staticmethod
    def db_format(data):
        return {
            'auth_service': data.get('auth_service'),
            'username': data.get('username'),
            'password': data.get('password'),
            'email': data.get('email'),
            'last_modified': datetime.utcnow(),
            'system_id': data.get('system_id'),
            'latitude': data.get('latitude'),
            'longitude': data.get('longitude'),
            'level': data.get('level'),
            'xp': data.get('xp'),
            'encounters': data.get('encounters'),
            'balls_thrown': data.get('balls_thrown'),
            'captures': data.get('captures'),
            'spins': data.get('spins'),
            'walked': data.get('walked'),
            'team': data.get('team'),
            'coins': data.get('coins'),
            'stardust': data.get('stardust'),
            'warn': data.get('warn'),
            'banned': data.get('banned'),
            'ban_flag': data.get('ban_flag'),
            'tutorial_state': data.get('tutorial_state'),
            'captcha': data.get('captcha'),
            'rareless_scans': data.get('rareless_scans'),
            'shadowbanned': data.get('shadowbanned'),
            'balls': data.get('balls'),
            'total_items': data.get('total_items'),
            'pokemon': data.get('pokemon'),
            'eggs': data.get('eggs'),
            'incubators': data.get('incubators'),
            'awarded_to_level': data.get('awarded_to_level')
        }

    @staticmethod
    def get_unused(system_id, count=1, min_level=1, lat=None, lng=None):
        query = (Account.select()
                        .where(Account.system_id.is_null())
                        .for_update()
                        .limit(count)
                        .order_by(Account.last_modified)
        )
        if min_level > 1:
            query.where((Account.level >= min_level))
        for account in query:
            account.system_id = system_id
            account.save()


def init_database(app):
    log.info('Connecting to MySQL database on %s:%i...',
             cfg_get('db_host'), cfg_get('db_port'))
    db = MyRetryDB(
        cfg_get('db_name'),
        user=cfg_get('db_user'),
        password=cfg_get('db_pass'),
        host=cfg_get('db_host'),
        port=cfg_get('db_port'),
        max_connections=cfg_get('db_max_connections'),
        stale_timeout=300,
        charset='utf8')
    app.config['DATABASE'] = db
    flaskDb.init_app(app)
    return db


def db_updater(q, db):
    # The forever loop.
    while True:
        try:

            while True:
                try:
                    flaskDb.connect_db()
                    break
                except Exception as e:
                    log.warning('%s... Retrying...', repr(e))
                    time.sleep(5)

            # Loop the queue.
            while True:
                data = q.get()
                update_account(data, db)
                q.task_done()

                # Helping out the GC.
                del data

                if q.qsize() > 50:
                    log.warning(
                        "DB queue is > 50 (@%d); try increasing --db-threads.",
                        q.qsize())

        except Exception as e:
            log.exception('Exception in db_updater: %s', repr(e))
            time.sleep(5)


def eval_acc_state_changes(acc_previous, acc):
    pass


def update_account(data, db):
    with db.atomic():
        try:
            acc, created = Account.get_or_create(username=data['username'])
            acc_previous = copy.deepcopy(acc)
            for key, value in data.items():
                if value is not None:
                    setattr(acc, key, value)
            acc.last_modified = datetime.utcnow()
            eval_acc_state_changes(acc_previous, acc)
            acc.save()
            log.info("Updated {}: {}".format(acc.username, str(data)))
        except Exception as e:
            # If there is a DB table constraint error, dump the data and
            # don't retry.
            #
            # Unrecoverable error strings:
            unrecoverable = ['constraint', 'has no attribute',
                             'peewee.IntegerField object at']
            has_unrecoverable = filter(
                lambda x: x in str(e), unrecoverable)
            if has_unrecoverable:
                log.warning('%s. Data is:', repr(e))
                log.warning(data.items())
            else:
                log.warning('%s... Retrying...', repr(e))
                time.sleep(1)


def create_tables(db):
    db.connect()
    tables = [Account]
    for table in tables:
        if not table.table_exists():
            log.info('Creating table: %s', table.__name__)
            db.create_tables([table], safe=True)
        else:
            log.debug('Skipping table %s, it already exists.', table.__name__)
    db.close()


