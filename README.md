# PGPool

**WORK IN PROGRES** - Webservice for account management.

Goal: Applications ask PGPool for accounts, use them, update them on a regular basis (using MrMime library) and release them at the end.

More documentation to come...

## Quick Start

PGPool currently only works if you use any product using MrMime library (e.g. PGScout, PGNumbra, my RocketMap fork).

Copy `config.json.sample` to `config.json` and adjust settings for database. Run PGPool with `python pgpool.py`.

In your application that should be linked to PGPool create or edit `mrmime_config.json` and set at least `pgpool_url` and `pgpool_system_id`:

```
{
    "pgpool_url": "http://localhost:4242",
    "pgpool_system_id": "name_of_system"
}

```

Other options are possible, their default values are:
```
{
    "pgpool_auto_update": true,         
    "pgpool_update_interval": 60
}
```

* `pgpool_auto_update`: Whether MrMime updates PGPool account details automatically
* `pgpool_update_interval`: Update account details in PGPool after this many seconds

Don't forget: **HEAVY WORK IN PROGRESS**!