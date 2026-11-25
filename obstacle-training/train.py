"""Step 2: train a COPY of the frozen base model on the exported dataset, and check the result.

The base weights file is only read. The result is a stripped weights file written inside the run's work folder (step 3, register.py, is what
installs it). Few roofs, so no validation split and no frozen layers: the aim is for the model to learn the customers' corrections quickly.
"""
import csv
import time
from pathlib import Path

import config


def train(data_yaml: Path, run_dir: Path, base_model: Path, epochs: int, out_name: str, imgsz: int = config.IMGSZ) -> dict:
    from ultralytics import YOLO
    from ultralytics.utils.torch_utils import strip_optimizer

    if not base_model.is_file():
        raise SystemExit(f"Base model not found: {base_model}")

    started = time.time()
    model = YOLO(str(base_model))
    model.train(
        data=str(data_yaml), epochs=epochs, imgsz=imgsz, batch=config.BATCH, device=config.DEVICE, workers=0,
        project=str(run_dir.resolve()), name="train", exist_ok=True,
        val=False, plots=False, verbose=False,
        optimizer="AdamW", lr0=config.LR0, warmup_epochs=0,
        mosaic=0.0, close_mosaic=0, fliplr=0.5, flipud=0.5, degrees=0.0, scale=0.2, translate=0.1, hsv_h=0.01, hsv_s=0.3, hsv_v=0.2,
        seed=0,
    )
    seconds = time.time() - started

    weights_dir = run_dir / "train" / "weights"
    produced = weights_dir / "last.pt"
    if not produced.is_file():
        produced = weights_dir / "best.pt"
    if not produced.is_file():
        raise SystemExit(f"Training finished but no weights were written in {weights_dir}")
    candidate = run_dir / out_name
    strip_optimizer(str(produced), s=str(candidate))  # drops optimizer state: ~6 MB like the other models

    losses: dict = {}
    results_csv = run_dir / "train" / "results.csv"
    if results_csv.is_file():
        with results_csv.open(newline="", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows:
            last = {k.strip(): v for k, v in rows[-1].items()}
            losses = {k: float(v) for k, v in last.items() if k.startswith("train/") and v not in ("", None)}
    return {"candidate": candidate, "seconds": round(seconds, 1), "epochs": epochs, "final_train_losses": losses}


def self_check(model_path: Path, dataset_dir: Path) -> dict:
    """How many of the confirmed obstacles a model finds on the training roofs (the check copy of each), at the service's confidence, and how many
    detections are extra (on a background roof every detection is extra). Used on the candidate AND on the base, to compare."""
    import cv2
    import numpy as np
    from ultralytics import YOLO

    model = YOLO(str(model_path))
    labels = found = extra = 0
    images = sorted((dataset_dir / "images" / "val").glob("*.png"))
    for img_path in images:
        img = cv2.imread(str(img_path))
        h, w = img.shape[:2]
        gts = []
        label_file = dataset_dir / "labels" / "val" / f"{img_path.stem}.txt"
        for line in label_file.read_text().splitlines():
            if not line.strip():
                continue
            v = np.array(line.split()[1:], float).reshape(-1, 2) * [w, h]
            m = np.zeros((h, w), np.uint8)
            cv2.fillPoly(m, [np.round(v).astype(np.int32)], 1)
            gts.append(m)
        r = model.predict(img, conf=config.CHECK_CONF, imgsz=config.IMGSZ, device=config.DEVICE, retina_masks=True, verbose=False)[0]
        preds = []
        for xy in (r.masks.xy if r.masks is not None else []):
            m = np.zeros((h, w), np.uint8)
            cv2.fillPoly(m, [np.round(np.asarray(xy)).astype(np.int32)], 1)
            preds.append(m)
        matched = set()
        for g in gts:
            ious = [(g & q).sum() / max(1, (g | q).sum()) for q in preds]
            if ious and max(ious) >= 0.3:
                found += 1
                matched.add(int(np.argmax(ious)))
        labels += len(gts)
        extra += len(preds) - len(matched)
    return {"images": len(images), "labels": labels, "found": found, "extra": extra, "conf": config.CHECK_CONF}


def should_install(candidate: dict, base: dict, positives: int) -> tuple[bool, str]:
    """The guard before a trained model replaces the live one. Never installs a model that learned nothing or did worse than the model it
    started from on its own training roofs (the signature of a failed or collapsed run)."""
    if positives <= 0:
        return False, "there were no confirmed obstacles to learn from"
    if candidate["found"] == 0:
        return False, "the trained model found none of the confirmed obstacles on its own training roofs (training failed)"
    if candidate["found"] < base["found"]:
        return False, f"the trained model found fewer obstacles ({candidate['found']}) than the model it started from ({base['found']})"
    return True, "ok"
