"""Step 3: install a trained model as the live one - safely.

The live file is copied to <weights>/_backup/<name>.<timestamp>.pt first (and the copy verified), then replaced in one atomic step so a
half-written file is never loaded. A line describing the run is appended to runs.jsonl. If a service URL is configured, the running
obstacle-service is told to reload (POST /reload), so a new model never sits unused until someone remembers to restart the service.
"""
import hashlib
import json
import os
import shutil
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

import config


def sha12(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def ensure_base(live: Path = config.LIVE_MODEL, base: Path = config.BASE_MODEL) -> Path:
    """The frozen starting model. Created once, from the live model, if it does not exist yet; never overwritten afterwards."""
    if not base.is_file():
        if not live.is_file():
            raise SystemExit(f"Neither the base model ({base}) nor the live model ({live}) exists.")
        base.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live, base)
    return base


def install(candidate: Path, live: Path, base: Path, run_info: dict, ledger: Path = config.LEDGER) -> dict:
    """Back up `live`, replace it with `candidate` (atomic), record the run. Returns {"weights", "backup", "ledger_entry"}."""
    if not candidate.is_file() or candidate.stat().st_size < 1_000_000:
        raise SystemExit(f"Candidate model looks incomplete: {candidate}")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup = None
    if live.is_file():
        backup = live.parent / "_backup" / f"{live.stem}.{stamp}{live.suffix}"
        backup.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(live, backup)
        if backup.stat().st_size != live.stat().st_size:
            backup.unlink(missing_ok=True)
            raise SystemExit(f"Backup of {live.name} is incomplete - the live model was NOT replaced.")
    staged = live.with_name(live.name + ".new")  # not *.pt, so the service never loads it half-written
    shutil.copy2(candidate, staged)
    os.replace(staged, live)

    entry = {
        "installed_at": datetime.now().isoformat(timespec="seconds"),
        "weights": str(live),
        "weights_sha": sha12(live),
        "backup": str(backup) if backup else None,
        "backup_sha": sha12(backup) if backup else None,
        "base": str(base),
        "base_sha": sha12(base) if base.is_file() else None,
        **run_info,
    }
    ledger.parent.mkdir(parents=True, exist_ok=True)
    with ledger.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
    return {"weights": live, "backup": backup, "ledger_entry": entry}


def reload_service(url: str) -> str:
    """Tell a running obstacle-service to load the new weights. Best effort: returns a one-line outcome, never raises."""
    if not url:
        return "no service URL configured - restart obstacle-service so it loads the new model"
    try:
        req = urllib.request.Request(url.rstrip("/") + "/reload", data=b"", method="POST")
        with urllib.request.urlopen(req, timeout=180) as resp:
            body = json.load(resp)
        return f"obstacle-service reloaded: {', '.join(body.get('models', []))}"
    except (urllib.error.URLError, OSError, ValueError) as exc:
        return f"could not reach obstacle-service at {url} ({type(exc).__name__}) - restart it so it loads the new model"
