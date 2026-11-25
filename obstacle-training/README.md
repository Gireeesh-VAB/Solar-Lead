# obstacle-training

Retrains the obstacle model from what customers do with its detections, and installs the result into **obstacle-service** - safely.
Stand-alone like obstacle-service: it reads the solar-fitness database (read-only), imports the service's own framing code, and writes
only to its own folders and to the service's `weights/`.

## Where the training data comes from

The solar-fitness app shows each detection to the customer as a candidate to **Confirm**, **Edit** (re-draw, then confirm) or **Ignore**.
That review is the label:

| Customer did | Stored as | Used for training as |
|---|---|---|
| Confirm / Edit | `obstacle_candidates.status = confirmed` (outline = the corrected one) | an obstacle outline to find |
| Ignore | `status = ignored` | a false alarm: **no label** (background), so the model learns to stop drawing it. A roof with only ignored detections is a "nothing here" example |
| not reviewed yet | `status = pending` | skipped |
| drew an obstacle the model **missed** ("Draw an obstacle" in the app) | a `confirmed` candidate with `source = customer_drawn`; the outline is the customer's own | an obstacle outline to find - **this is how the model learns what it misses** |
| tapped a spot themselves | a fixed-size square, not a real outline | **not used** |

## How a run works

```
obstacle_candidates (confirmed / ignored)  -- read-only SELECT through docker/psql
   -> one satellite frame per roof: obstacle-service's own satellite_frame code (same crop + enlarge as detection), cached in data/frames
   -> outlines converted from lng/lat to that frame's pixels, written as a YOLO-seg dataset (each roof x3 per epoch, + 1 check copy)
   -> train a COPY of the frozen base model (weights/_base) for 25 epochs on CPU
   -> self-check: how many confirmed obstacles do the new model AND the starting model find on those roofs?
   -> install only if the new one finds at least as many (never one that found nothing / got worse)
        backup of the live file -> weights/_backup/, atomic swap, a line in runs.jsonl, then POST /reload so the running service uses it now
```

**Every run starts from the same frozen base and trains on ALL reviewed roofs.** Runs never stack on each other, nothing is forgotten, and a
bad run cannot poison the next one. (Training the live file again and again on a hand-picked few roofs is what made an earlier model forget
corrections and finally detect nothing - so this page deliberately cannot pick roofs.)

## Use

```
.\trainer_ui\start_ui.ps1        ->  http://127.0.0.1:8766   (reviewed roofs with previews, "Check the data", "Start training", installed models)
python run.py --dry-run          export + download/cache the frames + confirm the base model loads; trains nothing, changes nothing
python run.py                    train on all reviewed roofs and install the result if it passes the check
python run.py --no-register      train and check, but leave the result in work/<run>/ (the live model is untouched)
python run.py --epochs 50 --repeat 3 --force
```

Needs: the solar-fitness Postgres container running (`solarfit-postgres-1`), a Maps key (environment, `obstacle-service/.env`, or borrowed -
read only, never printed - from the solar-fitness backend `.env`), and PyTorch/ultralytics (the solar-fitness backend's environment has them).
Time on this PC (i5, CPU): about 2 minutes per reviewed roof at 25 epochs.

## Folder

| Path | What |
|---|---|
| `run.py` | the whole pipeline |
| `export_dataset.py` | reviewed candidates -> YOLO dataset (+ preview pictures) |
| `frames.py` | the satellite frame per roof, cached; the Maps key lookup |
| `train.py` | training, the self-check, the install guard (`should_install`) |
| `register.py` | backup, atomic install, ledger, `POST /reload` |
| `db.py` | read-only psql access (refuses anything but SELECT) |
| `config.py` | paths and settings (all overridable by environment variables) |
| `trainer_ui/` | the local page (127.0.0.1 only) |
| `tests/` | 20 tests: no network, no models, no database |
| `data/` | cached frames + previews - **local only, git-ignored** |
| `work/` | per-run datasets and training output - git-ignored |
| `runs.jsonl` | one line per installed model - git-ignored |

## Things worth knowing

- **Few roofs = a small signal.** With a handful of reviewed roofs the model can only learn those roofs. It becomes meaningfully better as
  customers review more scans. The check numbers are on the *training* roofs (they show the corrections were learned and nothing broke), not a
  measure of accuracy on new roofs.
- **Misses are captured only when a customer draws them.** The app's "Draw an obstacle" button turns a miss into a real outline (a
  `customer_drawn` confirmed candidate), and a drawn obstacle the customer later removes becomes a false alarm (background). A miss nobody
  draws, and a quick tap (a fixed square), are not recorded as labels.
- **Frames are fetched when training needs them**, with the same recipe as detection, not when the customer scanned. Google's imagery can
  differ slightly in vintage; if a roof's outline changes the cached frame is refreshed.
- **The self-check's "extra" counts every detection outside a confirmed outline on the whole picture** (neighbouring roofs included), before the
  service's on-roof filter. Use it to compare the new model with the starting model, not as the number you will see in the app.
- **Training rights:** the imagery is Google satellite pictures, saved locally for training only. Confirm Google's terms allow training before
  using models trained on it beyond internal evaluation.
- **To go back:** copy a file from `obstacle-service/weights/_backup/` over `obstacle_combined_v2.pt` and `POST /reload`
  (or restart the service). The frozen base is `weights/_base/obstacle_combined_v2.base.pt`.
