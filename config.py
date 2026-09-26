import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    DATABASE = os.path.join(BASE_DIR, "database.db")
    UPLOAD_FOLDER = os.path.join(BASE_DIR, "static", "uploads")
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024  # 10MB

    
    # just a shared passcode that gates category/species management and export).
    ADMIN_PASSCODE = os.environ.get("ADMIN_PASSCODE", "changeme")

    # Tier 1: local reference-library similarity match (MobileNetV2 embeddings).
    SIMILARITY_THRESHOLD = float(os.environ.get("SIMILARITY_THRESHOLD", "0.75"))

    # Tier 2: online plant-ID fallback (optional -- app works fine without it,
    # falling straight through to manual entry). Get a free key at
    # https://my.plantnet.org/
    PLANTNET_API_KEY = os.environ.get("PLANTNET_API_KEY", "")
    PLANTNET_PROJECT = os.environ.get("PLANTNET_PROJECT", "all")
