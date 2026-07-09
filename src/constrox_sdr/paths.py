"""Central path/config constants so every module agrees on where things live."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
CONTENT_DIR = ROOT / "content"
REPORTS_DIR = ROOT / "reports"
OUTBOX_DIR = ROOT / "outbox"
HUMAN_TASKS_DIR = ROOT / "human_tasks"
DB_PATH = DATA_DIR / "crm.db"

FACTS_PATH = CONFIG_DIR / "constrox_facts.json"
SCORING_WEIGHTS_PATH = CONFIG_DIR / "scoring_weights.json"
OPERATING_HOURS_PATH = CONFIG_DIR / "operating_hours.json"
PIPELINE_SETTINGS_PATH = CONFIG_DIR / "pipeline_settings.json"
DNC_LIST_PATH = DATA_DIR / "dnc_list.csv"

for d in (DATA_DIR, REPORTS_DIR, OUTBOX_DIR, HUMAN_TASKS_DIR):
    d.mkdir(parents=True, exist_ok=True)
