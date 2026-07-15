"""Flash storage adapter for config and buffer persistence."""

import json

CONFIG_PATH = "config.json"
BUFFER_PATH = "buffer.json"


def _load_json(path, default=None):
    try:
        with open(path, "r") as f:
            return json.load(f)
    except Exception:
        return default


def _save_json(path, data):
    with open(path, "w") as f:
        json.dump(data, f)


def load_config(default=None):
    return _load_json(CONFIG_PATH, default)


def save_config(config):
    _save_json(CONFIG_PATH, config)


def load_buffer():
    data = _load_json(BUFFER_PATH, [])
    return data if isinstance(data, list) else []


def save_buffer(records):
    _save_json(BUFFER_PATH, records)
