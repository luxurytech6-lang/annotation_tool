"""
seed_dataset.py
================
Pulls a small, license-checked "seed batch" of plant images from two
sources to bootstrap the Tier-1 reference library (image_embeddings)
of the Ethno-Botanical Image Annotation Tool BEFORE real fieldwork
images exist:

  1. iNaturalist   -- research-grade, community-identified observations
  2. Pl@ntNet       -- via GBIF's "Pl@ntNet observations" dataset
                       (CC-licensed subset of the Pl@ntNet app), key:
                       7a3679ef-5582-4aaa-81f0-8c2545cafc81

Only images licensed CC0, CC-BY, or CC-BY-SA are downloaded, since
those permit reuse in an academic project. A manifest.csv is written
alongside the images recording the exact source, license, and
required attribution for every file -- keep this, you will need it
for an appendix note on data provenance.

USAGE
-----
    pip install requests
    python seed_dataset.py

Images land in ./seed_dataset/<scientific_name>/<source>_<n>.jpg
Adjust SPECIES and PER_SOURCE_LIMIT below as needed.

NOTE: This script must be run on a machine with normal internet
access -- it will not run inside a sandboxed/offline environment.
"""

import csv
import os
import time
import requests

# ---------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------

# Species already used in the project's mockups/config; extend freely.
SPECIES = [
    "Ocimum gratissimum",     # scent leaf
    "Azadirachta indica",     # neem
    "Vernonia amygdalina",    # bitter leaf
    "Moringa oleifera",       # moringa
    "Carica papaya",          # pawpaw
    "Psidium guajava",        # guava
    "Citrus aurantiifolia",   # lime
    "Aloe vera",
]

PER_SOURCE_LIMIT = 8          # images per species, per source
OUT_DIR = "seed_dataset"
GBIF_PLANTNET_DATASET_KEY = "7a3679ef-5582-4aaa-81f0-8c2545cafc81"
ALLOWED_LICENSES_INAT = {"cc0", "cc-by", "cc-by-sa"}
ALLOWED_LICENSES_GBIF = {
    "CC0_1_0", "CC_BY_4_0", "CC_BY_SA_4_0",
    "http://creativecommons.org/publicdomain/zero/1.0/legalcode",
    "http://creativecommons.org/licenses/by/4.0/legalcode",
    "http://creativecommons.org/licenses/by-sa/4.0/legalcode",
}
REQUEST_DELAY = 1.0  # seconds between API calls, per API etiquette
HEADERS = {"User-Agent": "EthnoBotanicalAnnotationTool-SeedScript/1.0 (academic project)"}

manifest_rows = []


def safe_name(s):
    return s.replace(" ", "_").replace("/", "_")


def download_file(url, dest_path):
    try:
        r = requests.get(url, headers=HEADERS, timeout=20)
        r.raise_for_status()
        with open(dest_path, "wb") as f:
            f.write(r.content)
        return True
    except Exception as e:
        print(f"    ! download failed: {e}")
        return False


# ---------------------------------------------------------------
# Source 1: iNaturalist
# ---------------------------------------------------------------

def fetch_inaturalist(species, limit, out_folder):
    print(f"  [iNaturalist] querying {species} ...")
    params = {
        "taxon_name": species,
        "quality_grade": "research",
        "photos": "true",
        "photo_license": ",".join(ALLOWED_LICENSES_INAT),
        "per_page": limit * 2,  # over-fetch a little; some entries may lack usable photos
        "order_by": "votes",
    }
    try:
        resp = requests.get(
            "https://api.inaturalist.org/v1/observations",
            params=params, headers=HEADERS, timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    ! iNaturalist query failed: {e}")
        return 0

    saved = 0
    for obs in data.get("results", []):
        if saved >= limit:
            break
        for photo in obs.get("photos", []):
            if saved >= limit:
                break
            license_code = (photo.get("license_code") or "").lower()
            if license_code not in ALLOWED_LICENSES_INAT:
                continue
            # request the "medium" size image
            url = photo.get("url", "").replace("square", "medium")
            if not url:
                continue
            fname = f"inaturalist_{saved+1:02d}.jpg"
            dest = os.path.join(out_folder, fname)
            time.sleep(REQUEST_DELAY)
            if download_file(url, dest):
                attribution = obs.get("user", {}).get("login", "unknown")
                manifest_rows.append({
                    "species": species, "source": "iNaturalist",
                    "file": dest, "license": license_code,
                    "attribution": f"iNaturalist user '{attribution}', observation {obs.get('id')}",
                    "source_url": f"https://www.inaturalist.org/observations/{obs.get('id')}",
                })
                saved += 1
    print(f"    -> saved {saved} image(s)")
    return saved


# ---------------------------------------------------------------
# Source 2: Pl@ntNet observations, via GBIF
# ---------------------------------------------------------------

def fetch_plantnet_via_gbif(species, limit, out_folder):
    print(f"  [Pl@ntNet/GBIF] querying {species} ...")
    params = {
        "scientificName": species,
        "datasetKey": GBIF_PLANTNET_DATASET_KEY,
        "mediaType": "StillImage",
        "limit": limit * 2,
    }
    try:
        resp = requests.get(
            "https://api.gbif.org/v1/occurrence/search",
            params=params, headers=HEADERS, timeout=20,
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"    ! GBIF query failed: {e}")
        return 0

    saved = 0
    for rec in data.get("results", []):
        if saved >= limit:
            break
        license_str = rec.get("license", "")
        if license_str not in ALLOWED_LICENSES_GBIF:
            continue
        for media in rec.get("media", []):
            if saved >= limit:
                break
            url = media.get("identifier")
            if not url:
                continue
            fname = f"gbif_plantnet_{saved+1:02d}.jpg"
            dest = os.path.join(out_folder, fname)
            time.sleep(REQUEST_DELAY)
            if download_file(url, dest):
                manifest_rows.append({
                    "species": species, "source": "Pl@ntNet (via GBIF)",
                    "file": dest, "license": license_str,
                    "attribution": f"Recorded by {rec.get('recordedBy', 'unknown')}; "
                                    f"Pl@ntNet observations dataset, GBIF occurrence {rec.get('key')}",
                    "source_url": f"https://www.gbif.org/occurrence/{rec.get('key')}",
                })
                saved += 1
    print(f"    -> saved {saved} image(s)")
    return saved


# ---------------------------------------------------------------
# Main
# ---------------------------------------------------------------

def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    for species in SPECIES:
        print(f"\n=== {species} ===")
        folder = os.path.join(OUT_DIR, safe_name(species))
        os.makedirs(folder, exist_ok=True)
        fetch_inaturalist(species, PER_SOURCE_LIMIT, folder)
        time.sleep(REQUEST_DELAY)
        fetch_plantnet_via_gbif(species, PER_SOURCE_LIMIT, folder)
        time.sleep(REQUEST_DELAY)

    manifest_path = os.path.join(OUT_DIR, "manifest.csv")
    with open(manifest_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f, fieldnames=["species", "source", "file", "license", "attribution", "source_url"]
        )
        writer.writeheader()
        writer.writerows(manifest_rows)

    print(f"\nDone. {len(manifest_rows)} image(s) saved under ./{OUT_DIR}/")
    print(f"Provenance/licensing log written to {manifest_path}")
    print("Keep manifest.csv -- cite it as your seed-data source in Chapter 4.")


if __name__ == "__main__":
    main()