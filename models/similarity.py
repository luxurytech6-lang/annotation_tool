"""
Tier 1 of the species-suggestion cascade: compare a new image's visual
"fingerprint" against every image already confirmed in the local
reference library (image_embeddings table), using MobileNetV2 purely
as a pretrained FEATURE EXTRACTOR (not a classifier -- its final
classification layer is stripped off). No training happens here; the
reference library simply grows every time a labeller confirms an
annotation.

Heavy imports (torch / torchvision) are done lazily inside functions so
the rest of the app (upload, browse, export, admin) works even before
those packages are installed -- this module fails soft, not hard.
"""

import io
import pickle

import numpy as np

_model = None
_transform = None


def _load_model():
    """Lazily load MobileNetV2 with its classifier head removed."""
    global _model, _transform
    if _model is not None:
        return _model, _transform

    import torch
    from torchvision import models, transforms

    weights = models.MobileNet_V2_Weights.IMAGENET1K_V1
    net = models.mobilenet_v2(weights=weights)
    net.classifier = torch.nn.Identity()  # strip classification head -> raw 1280-d features
    net.eval()

    _model = net
    _transform = transforms.Compose(
        [
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
        ]
    )
    return _model, _transform


def is_available():
    """Check if the embedding model can be loaded (torch/torchvision installed)."""
    try:
        _load_model()
        return True
    except Exception:
        return False


def extract_embedding(image_path):
    """
    Turn an image into a 1280-dim L2-normalized feature vector.
    Returns None if torch/torchvision aren't installed or the image
    can't be read -- callers must handle that gracefully (fall through
    to tier 2 / manual entry).
    """
    try:
        import torch
        from PIL import Image

        model, transform = _load_model()
        img = Image.open(image_path).convert("RGB")
        tensor = transform(img).unsqueeze(0)
        with torch.no_grad():
            vec = model(tensor).squeeze(0).numpy()
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.astype(np.float32)
    except Exception as exc:
        print(f"[similarity] extract_embedding failed: {exc}")
        return None


def embedding_to_blob(vec):
    return pickle.dumps(vec)


def blob_to_embedding(blob):
    return pickle.loads(blob)


def save_embedding(db, image_id, vec):
    db.execute(
        "INSERT OR REPLACE INTO image_embeddings (image_id, embedding) VALUES (?, ?)",
        (image_id, embedding_to_blob(vec)),
    )
    db.commit()


def suggest_species(db, image_path, threshold=0.75):
    """
    Compare a new image against every embedding in the local reference
    library. Returns (species_id, score) for the best match if the
    library is non-empty, regardless of threshold -- callers decide
    what counts as "confident enough" using the returned score.
    Returns None if the library is empty (cold start) or the model
    isn't available.
    """
    new_vec = extract_embedding(image_path)
    if new_vec is None:
        return None

    rows = db.execute(
        """
        SELECT e.embedding, i.species_id
        FROM image_embeddings e
        JOIN images i ON i.image_id = e.image_id
        WHERE i.species_id IS NOT NULL
        """
    ).fetchall()

    if not rows:
        return None  # cold start -- nothing to compare against yet

    best_species_id = None
    best_score = -1.0
    for row in rows:
        try:
            ref_vec = blob_to_embedding(row["embedding"])
        except Exception:
            continue
        score = float(np.dot(new_vec, ref_vec))  # both L2-normalized -> dot == cosine similarity
        if score > best_score:
            best_score = score
            best_species_id = row["species_id"]

    if best_species_id is None:
        return None
    return best_species_id, best_score
