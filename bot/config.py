import copy
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "state"
SITE_DIR = ROOT / "site"


def load_config(path=None):
    path = Path(path or ROOT / "config.yaml")
    raw = yaml.safe_load(path.read_text())
    defaults = raw.get("defaults", {})
    markets = {}
    for key, m in raw["markets"].items():
        cfg = copy.deepcopy(defaults)
        for k, v in m.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
        cfg["key"] = key
        markets[key] = cfg
    return markets
