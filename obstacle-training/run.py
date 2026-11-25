"""Runs the whole pipeline: export -> train -> check -> install -> reload.

    python run.py                  train on ALL reviewed roofs, starting from the frozen base model, and install the result if it passes the check
    python run.py --dry-run        export (downloads/caches the satellite frames), confirm the base model loads, train nothing, change nothing
    python run.py --no-register    train and check, but leave the result in work/<run>/ only (the live model is not touched)
    python run.py --force          install even if the check fails (not recommended)

Every run starts from the SAME frozen base (weights/_base) and trains on EVERY reviewed roof, so runs never stack and nothing is forgotten.
The live model is backed up to weights/_backup before it is replaced; the running obstacle-service is told to reload.
"""
import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import config
import export_dataset


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--epochs", type=int, default=config.EPOCHS)
    ap.add_argument("--repeat", type=int, default=config.REPEAT, help="copies of each roof per epoch (more updates)")
    ap.add_argument("--base", type=Path, default=config.BASE_MODEL, help="the model to start from (default: the frozen base in weights/_base)")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-register", action="store_true")
    ap.add_argument("--force", action="store_true", help="install even if the check fails")
    a = ap.parse_args()

    config.WORK_DIR.mkdir(parents=True, exist_ok=True)
    lock = config.WORK_DIR / ".lock"
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        print(f"Another training run seems to be active ({lock}). If not, delete that file and retry.")
        return 2
    os.write(fd, str(os.getpid()).encode())
    os.close(fd)

    try:
        import register

        started_at = datetime.now(timezone.utc).isoformat()
        run_dir = config.WORK_DIR / datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir.mkdir(parents=True)

        register.ensure_base(config.LIVE_MODEL, a.base)
        exp = export_dataset.export(run_dir / "dataset", a.repeat)
        print(f"[1/3] exported {len(exp['sites'])} reviewed roof(s): {exp['positives']} confirmed obstacle(s), "
              f"{sum(u['ignored'] for u in exp['sites'])} ignored false alarm(s)")
        for sk in exp["skipped"]:
            print(f"      skipped {sk['id'][:8]}: {sk['why']}")
        if a.dry_run:
            from ultralytics import YOLO

            print(f"[dry-run] base model loads, classes {YOLO(str(a.base)).names}. Nothing trained, nothing changed.")
            return 0

        import train

        print(f"[2/3] training {config.LIVE_MODEL.name}, starting from {a.base.name}, {a.epochs} epochs x {a.repeat} copies on {config.DEVICE} ...")
        info = train.train(exp["data_yaml"], run_dir, a.base, a.epochs, config.LIVE_MODEL.name, exp["imgsz"])
        print(f"      done in {info['seconds']} s, candidate: {info['candidate']}")

        check = train.self_check(info["candidate"], run_dir / "dataset")
        base_check = train.self_check(a.base, run_dir / "dataset")
        info["self_check"], info["base_check"] = check, base_check
        print(f"      check on the training roofs (same picture and confidence as the service):")
        print(f"        trained model: found {check['found']} of {check['labels']} obstacles, {check['extra']} extra")
        print(f"        starting model: found {base_check['found']} of {base_check['labels']} obstacles, {base_check['extra']} extra")

        ok, why = train.should_install(check, base_check, exp["positives"])
        if a.no_register:
            print("[3/3] --no-register: left in the work folder, the live model is not touched.")
            result = {"candidate": str(info["candidate"])}
        elif not ok and not a.force:
            print(f"[3/3] NOT installed: {why}. The live model was left as it was.")
            return 3
        else:
            if not ok:
                print(f"      --force: installing although {why}")
            run_info = {
                "started_at": started_at, "roofs": exp["sites"], "positives": exp["positives"], "epochs": a.epochs, "repeat": a.repeat,
                "seconds": info["seconds"], "self_check": check, "base_check": base_check, "final_train_losses": info["final_train_losses"],
            }
            reg = register.install(info["candidate"], config.LIVE_MODEL, a.base, run_info)
            print(f"[3/3] installed {reg['weights'].name} (previous version kept at {reg['backup']})")
            print(f"      {register.reload_service(config.SERVICE_URL)}")
            result = {"weights": str(reg["weights"]), "backup": str(reg["backup"])}

        (run_dir / "run.json").write_text(
            json.dumps({**result, "roofs": exp["sites"], "train": {k: v for k, v in info.items() if k != "candidate"}}, indent=2), encoding="utf-8"
        )
        return 0
    finally:
        lock.unlink(missing_ok=True)


if __name__ == "__main__":
    t0 = time.time()
    code = main()
    print(f"total {round(time.time() - t0, 1)} s")
    sys.exit(code)
