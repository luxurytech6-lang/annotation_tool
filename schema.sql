-- Topic 3: Ethno-botanical Image Annotation Tool
-- SQLite schema

PRAGMA foreign_keys = ON;

-- Species reference table.
-- Species can be added on the fly during annotation (manual entry / override),
-- so this is NOT a hardcoded fixed list -- it grows as labellers work.
CREATE TABLE IF NOT EXISTS plants (
    species_id      INTEGER PRIMARY KEY AUTOINCREMENT,
    common_name     TEXT NOT NULL,
    urhobo_name     TEXT,
    scientific_name TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(common_name)
);

-- Medicinal use categories.
-- Seeded with a fixed starter list (see seed_data.py) but new categories
-- can be added by an admin/labeller -- not locked forever, just not
-- free-typed per annotation (keeps export data clean, avoids
-- "Fever" vs "fever" vs "high fever" duplicates).
CREATE TABLE IF NOT EXISTS use_categories (
    category_id INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE
);

-- One row per uploaded/annotated image.
CREATE TABLE IF NOT EXISTS images (
    image_id              INTEGER PRIMARY KEY AUTOINCREMENT,
    filename              TEXT NOT NULL,
    species_id            INTEGER,
    suggested_species_id  INTEGER,
    suggestion_score      REAL,
    image_type            TEXT CHECK (image_type IN ('leaf', 'bark', 'flower', 'whole_plant')),
    labeller              TEXT,
    date_annotated        DATETIME,
    date_uploaded         DATETIME DEFAULT CURRENT_TIMESTAMP,
    status                TEXT DEFAULT 'pending' CHECK (status IN ('pending', 'annotated')),
    FOREIGN KEY (species_id) REFERENCES plants(species_id),
    FOREIGN KEY (suggested_species_id) REFERENCES plants(species_id)
);

-- Many-to-many: one row per (image, use category) tag, each carrying
-- its own qualitative effectiveness rating.
CREATE TABLE IF NOT EXISTS image_use_tags (
    tag_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    image_id              INTEGER NOT NULL,
    category_id           INTEGER NOT NULL,
    effectiveness_rating  TEXT NOT NULL CHECK (effectiveness_rating IN ('None', 'Low', 'Medium', 'High')),
    FOREIGN KEY (image_id) REFERENCES images(image_id) ON DELETE CASCADE,
    FOREIGN KEY (category_id) REFERENCES use_categories(category_id),
    UNIQUE(image_id, category_id)
);

-- Cached CNN embeddings for the similarity-suggestion feature.
-- Kept in its own table (not bolted onto `images`) so the core schema
-- stays exactly as designed, and this can be rebuilt/cleared independently
-- if the feature-extractor model ever changes.
CREATE TABLE IF NOT EXISTS image_embeddings (
    image_id   INTEGER PRIMARY KEY,
    embedding  BLOB NOT NULL,
    FOREIGN KEY (image_id) REFERENCES images(image_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_images_species ON images(species_id);
CREATE INDEX IF NOT EXISTS idx_tags_image ON image_use_tags(image_id);
