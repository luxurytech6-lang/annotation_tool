"""
Tier 2 of the species-suggestion cascade: an online plant-ID lookup,
used only when the local reference library (tier 1) has no confident
match -- e.g. cold start, or a species that hasn't been labeled yet.

This tier can only ever suggest a species name (scientific/common).
It has no knowledge of Urhobo names or medicinal use -- that stays
entirely with the labeller's own field/community knowledge.

Fails soft: any missing API key, network error, or bad response
returns None so the caller falls through to tier 3 (manual entry)
rather than blocking the labeller.
"""

import requests

PLANTNET_URL = "https://my-api.plantnet.org/v2/identify/{project}"


def lookup_species(image_path, api_key, project="all", timeout=8):
    if not api_key:
        return None

    try:
        with open(image_path, "rb") as f:
            files = [("images", (image_path, f, "image/jpeg"))]
            data = {"organs": ["leaf"]}
            resp = requests.post(
                PLANTNET_URL.format(project=project),
                files=files,
                data=data,
                params={"api-key": api_key},
                timeout=timeout,
            )
        if resp.status_code != 200:
            return None

        payload = resp.json()
        results = payload.get("results", [])
        if not results:
            return None

        top = results[0]
        species = top.get("species", {})
        common_names = species.get("commonNames", [])
        return {
            "scientific_name": species.get("scientificNameWithoutAuthor", ""),
            "common_name": common_names[0] if common_names else species.get("scientificNameWithoutAuthor", ""),
            "score": top.get("score", 0.0),
        }
    except Exception as exc:
        print(f"[plantnet] lookup failed: {exc}")
        return None
