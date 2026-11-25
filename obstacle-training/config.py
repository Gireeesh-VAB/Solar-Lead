"""Settings for the obstacle-model training pipeline. Every value can be overridden with an environment variable."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent

#: The stand-alone obstacle-service this pipeline trains models for (its code is imported so training sees EXACTLY what detection sees).
SERVICE_DIR = Path(os.environ.get("OBSTACLE_SERVICE_DIR", ROOT.parent / "obstacle-service"))
#: The folder the service loads models from. Installed models replace a file here (after a backup); nothing else is written here.
WEIGHTS_DIR = Path(os.environ.get("OBSTACLE_WEIGHTS_DIR", SERVICE_DIR / "weights"))
#: Every run STARTS from this frozen copy of the model (read only, never overwritten). Starting each run from the same original and training on
#: ALL reviewed roofs means runs do not stack on each other: nothing is forgotten and a bad run cannot poison the next one.
BASE_MODEL = Path(os.environ.get("OBSTACLE_BASE_MODEL", WEIGHTS_DIR / "_base" / "obstacle_combined_v2.base.pt"))
#: The file the service loads and a finished run replaces (after copying the current one to _backup).
LIVE_MODEL = Path(os.environ.get("OBSTACLE_LIVE_MODEL", WEIGHTS_DIR / "obstacle_combined_v2.pt"))

#: Local only, git-ignored: satellite frames fetched for training (one per roof) and the preview pictures drawn from them.
DATA_DIR = Path(os.environ.get("OBSTACLE_TRAINING_DATA_DIR", ROOT / "data"))
FRAMES_DIR = DATA_DIR / "frames"
PREVIEWS_DIR = DATA_DIR / "previews"
#: Per-run working folders (dataset, training output, log).
WORK_DIR = Path(os.environ.get("OBSTACLE_TRAIN_WORK_DIR", ROOT / "work"))
#: One JSON line per installed model: when, from which roofs, how it scored, where the backup is.
LEDGER = Path(os.environ.get("OBSTACLE_TRAIN_LEDGER", ROOT / "runs.jsonl"))

#: How to reach the solar-fitness Postgres: a psql command that reads SQL on stdin. READ ONLY use (this pipeline only ever SELECTs).
PSQL_COMMAND = os.environ.get(
    "OBSTACLE_PSQL",
    "docker exec -i solarfit-postgres-1 psql -U solarfit -d solarfit -v ON_ERROR_STOP=1 -At -q",
)
#: The solar-fitness backend .env, read ONLY to borrow the Maps key when neither the environment nor obstacle-service/.env has one.
APP_ENV_FILE = Path(os.environ.get("OBSTACLE_APP_ENV", ROOT.parent / "solar-fitness" / "backend" / ".env"))
#: A running obstacle-service to tell about the new weights (POST /reload) once a model is installed. Empty = do not.
SERVICE_URL = os.environ.get("OBSTACLE_SERVICE_URL", "http://127.0.0.1:8200")

IMGSZ = int(os.environ.get("OBSTACLE_TRAIN_IMGSZ", "640"))  # keep equal to the service's inference size
#: Each roof is written this many times per epoch (random flips/colour make the copies differ), so a few roofs get enough updates.
REPEAT = int(os.environ.get("OBSTACLE_TRAIN_REPEAT", "3"))
EPOCHS = int(os.environ.get("OBSTACLE_TRAIN_EPOCHS", "25"))
BATCH = int(os.environ.get("OBSTACLE_TRAIN_BATCH", "2"))
LR0 = float(os.environ.get("OBSTACLE_TRAIN_LR0", "0.0005"))
DEVICE = os.environ.get("OBSTACLE_TRAIN_DEVICE", "cpu")
#: Confidence the service uses per model (OBSTACLE_MODEL_CONF); the self-check uses the same.
CHECK_CONF = float(os.environ.get("OBSTACLE_MODEL_CONF", "0.25"))
