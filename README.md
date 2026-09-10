# Ethno-Botanical Image Annotation Tool

Topic 3 deliverable: a Flask + SQLite web app for annotating plant
images with species, Urhobo name, image type, and multiple medicinal
use tags (each with a qualitative effectiveness rating). Includes a
three-tier species-suggestion cascade and a lightweight admin/labeller
access split.

## Quick start

```bash
cd annotation_tool
python -m venv venv
source venv/bin/activate          # Windows: venv\Scripts\activate

pip install -r requirements.txt   # torch/torchvision are optional --
                                   # see note below if you want a
                                   # faster install without them

cp .env.example .env
# edit .env: set SECRET_KEY and ADMIN_PASSCODE at minimum

export FLASK_APP=app.py           # Windows: set FLASK_APP=app.py
flask init-db                     # creates database.db from schema.sql
python seed_data.py               # seeds the starter use-category list

flask run
# open http://127.0.0.1:5000
```

## How species suggestion works

Three tiers, in order (see the algorithm-flow and cascade diagrams
from our design discussion):

1. **Local reference library** -- MobileNetV2 (ImageNet weights, no
   fine-tuning) used purely as a feature extractor. Every confirmed
   annotation adds its embedding to `image_embeddings`, so this tier
   gets stronger the more you annotate. Runs fully offline.
2. **Online PlantNet fallback** -- only triggers when tier 1 has no
   embeddings yet (cold start) or scores below `SIMILARITY_THRESHOLD`.
   Needs an internet connection and a free API key in `.env`. Can only
   ever suggest a species name -- never Urhobo name or medicinal use,
   since no global database has that.
3. **Manual entry** -- the labeller types the species directly. Always
   available, always the final fallback if tiers 1 and 2 come up empty
   or the API call fails/times out.

If you don't want `torch`/`torchvision` installed at all (e.g. testing
the rest of the app quickly), just skip those two lines in
`requirements.txt` -- every other route works fine, and species
suggestion falls straight through to tier 2/3.

## Access model

No user accounts. Labellers just type their name on the upload form.
A single shared admin passcode (`ADMIN_PASSCODE` in `.env`) gates:

- Managing the use-category list (add/remove)
- Reviewing flagged images (no species match, or low-confidence match)
- Exporting the dataset (CSV/JSON)

This is a session flag, not a full auth system -- appropriate for a
small, known group of field assistants rather than public access.

## Project structure

```
annotation_tool/
├── app.py                 Flask app, all routes
├── config.py               App configuration (reads from environment)
├── db.py                   SQLite connection helpers + `flask init-db`
├── schema.sql               Database schema (5 tables, see ERD)
├── seed_data.py             Starter use-category list
├── models/
│   ├── similarity.py        Tier 1: MobileNetV2 embeddings + cosine similarity
│   └── plantnet.py          Tier 2: PlantNet API fallback
├── static/
│   ├── style.css
│   └── uploads/              Uploaded image files land here
├── templates/
│   ├── base.html
│   ├── upload.html
│   ├── annotate.html
│   ├── browse.html
│   ├── admin_login.html
│   ├── admin_manage.html
│   └── admin_export.html
├── requirements.txt
└── .env.example
```

## Use categories: fixed-but-extensible

`use_categories` is seeded with a starter list in `seed_data.py`
(edit that file to match your actual fieldwork categories before
running it). New categories can still be added anytime via the admin
panel -- this keeps exported data clean (no "Fever" vs "fever"
duplicates) without locking the list forever.

## Six-week plan mapping

- **Week 1** -- schema (`schema.sql`) + Flask scaffolding + upload flow: done here
- **Week 2** -- similarity-matching suggestion feature: done here (`models/similarity.py`)
- **Weeks 3-4** -- annotation UI + annotate the real starter dataset: UI is done here; the actual annotating is your fieldwork
- **Week 5** -- export functionality + validation: export routes done here; validation is a manual pass over the CSV/JSON once real data exists
- **Week 6** -- protocol write-up + polish + final report: outside this codebase
