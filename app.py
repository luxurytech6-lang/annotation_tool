import csv
import io
import json
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for,
    flash, session, send_from_directory, Response, current_app
)
from werkzeug.utils import secure_filename

from config import Config
import db as db_module
from models import similarity, plantnet


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
    db_module.init_app(app)
    register_routes(app)
    return app


def allowed_file(filename):
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in current_app.config["ALLOWED_EXTENSIONS"]
    )


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get("is_admin"):
            flash("Admin access required.", "error")
            return redirect(url_for("admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


def register_routes(app):

    @app.route("/")
    def index():
        return render_template("landing.html")

    # ---------------------------------------------------------------
    # Upload  (Tier 1 + Tier 2 species suggestion runs right after save)
    # ---------------------------------------------------------------
    @app.route("/upload", methods=["GET", "POST"])
    def upload():
        db = db_module.get_db()

        if request.method == "POST":
            labeller = request.form.get("labeller", "").strip()
            file = request.files.get("image")

            if not file or file.filename == "":
                flash("Choose an image file first.", "error")
                return redirect(url_for("upload"))
            if not allowed_file(file.filename):
                flash("Only JPG or PNG images are supported.", "error")
                return redirect(url_for("upload"))

            filename = secure_filename(file.filename)
            timestamp = datetime.now().strftime("%Y%m%d%H%M%S%f")
            stored_name = f"{timestamp}_{filename}"
            filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], stored_name)
            file.save(filepath)

            cur = db.execute(
                "INSERT INTO images (filename, labeller, status) VALUES (?, ?, 'pending')",
                (stored_name, labeller or None),
            )
            db.commit()
            image_id = cur.lastrowid

            # Tier 1: local reference library match
            suggestion = similarity.suggest_species(
                db, filepath, threshold=current_app.config["SIMILARITY_THRESHOLD"]
            )
            if suggestion is not None:
                species_id, score = suggestion
                db.execute(
                    "UPDATE images SET suggested_species_id = ?, suggestion_score = ? WHERE image_id = ?",
                    (species_id, score, image_id),
                )
                db.commit()

            # Also cache this image's own embedding immediately so the
            # library is ready to compare future uploads against once
            # this one gets annotated (embedding gets linked to a
            # confirmed species_id at save-time in the annotate route).
            vec = similarity.extract_embedding(filepath)
            if vec is not None:
                similarity.save_embedding(db, image_id, vec)

            return redirect(url_for("annotate", image_id=image_id))

        recent = db.execute(
            "SELECT * FROM images ORDER BY date_uploaded DESC LIMIT 6"
        ).fetchall()
        return render_template("upload.html", recent=recent)

    # ---------------------------------------------------------------
    # Annotate
    # ---------------------------------------------------------------
    @app.route("/annotate/<int:image_id>", methods=["GET", "POST"])
    def annotate(image_id):
        db = db_module.get_db()
        image = db.execute("SELECT * FROM images WHERE image_id = ?", (image_id,)).fetchone()
        if image is None:
            flash("Image not found.", "error")
            return redirect(url_for("upload"))

        if request.method == "POST":
            species_choice = request.form.get("species_choice", "").strip()
            new_species_name = request.form.get("new_species_name", "").strip()
            urhobo_name = request.form.get("urhobo_name", "").strip()
            scientific_name = request.form.get("scientific_name", "").strip()
            image_type = request.form.get("image_type", "").strip()
            labeller = request.form.get("labeller", "").strip()

            category_ids = request.form.getlist("category_id[]")
            ratings = request.form.getlist("effectiveness_rating[]")

            if not image_type:
                flash("Select an image type.", "error")
                return redirect(url_for("annotate", image_id=image_id))

            # Resolve species: either an existing plant, or create a new one
            if species_choice == "__new__":
                if not new_species_name:
                    flash("Enter a species name.", "error")
                    return redirect(url_for("annotate", image_id=image_id))
                existing = db.execute(
                    "SELECT species_id FROM plants WHERE common_name = ?", (new_species_name,)
                ).fetchone()
                if existing:
                    species_id = existing["species_id"]
                else:
                    cur = db.execute(
                        "INSERT INTO plants (common_name, urhobo_name, scientific_name) VALUES (?, ?, ?)",
                        (new_species_name, urhobo_name or None, scientific_name or None),
                    )
                    species_id = cur.lastrowid
            else:
                species_id = int(species_choice)
                if urhobo_name:
                    db.execute(
                        "UPDATE plants SET urhobo_name = ? WHERE species_id = ?",
                        (urhobo_name, species_id),
                    )

            db.execute(
                """
                UPDATE images
                SET species_id = ?, image_type = ?, labeller = ?, status = 'annotated',
                    date_annotated = CURRENT_TIMESTAMP
                WHERE image_id = ?
                """,
                (species_id, image_type, labeller or image["labeller"], image_id),
            )

            # Replace use-tags for this image
            db.execute("DELETE FROM image_use_tags WHERE image_id = ?", (image_id,))
            for cat_id, rating in zip(category_ids, ratings):
                if not cat_id:
                    continue
                db.execute(
                    """
                    INSERT INTO image_use_tags (image_id, category_id, effectiveness_rating)
                    VALUES (?, ?, ?)
                    """,
                    (image_id, int(cat_id), rating),
                )

            db.commit()
            flash("Annotation saved.", "success")
            return redirect(url_for("browse"))

        # GET: run tier 2 fallback here if tier 1 gave nothing / low confidence,
        # so the suggestion is fresh when the labeller opens the form.
        suggestion_label = None
        suggestion_source = None
        if image["suggested_species_id"] and (image["suggestion_score"] or 0) >= current_app.config["SIMILARITY_THRESHOLD"]:
            sp = db.execute(
                "SELECT common_name FROM plants WHERE species_id = ?", (image["suggested_species_id"],)
            ).fetchone()
            if sp:
                suggestion_label = sp["common_name"]
                suggestion_source = "local"
        else:
            filepath = os.path.join(current_app.config["UPLOAD_FOLDER"], image["filename"])
            api_result = plantnet.lookup_species(
                filepath,
                current_app.config["PLANTNET_API_KEY"],
                current_app.config["PLANTNET_PROJECT"],
            )
            if api_result:
                suggestion_label = api_result["common_name"] or api_result["scientific_name"]
                suggestion_source = "api"

        plants = db.execute("SELECT * FROM plants ORDER BY common_name").fetchall()
        categories = db.execute("SELECT * FROM use_categories ORDER BY name").fetchall()
        existing_tags = db.execute(
            "SELECT * FROM image_use_tags WHERE image_id = ?", (image_id,)
        ).fetchall()

        return render_template(
            "annotate.html",
            image=image,
            plants=plants,
            categories=categories,
            existing_tags=existing_tags,
            suggestion_label=suggestion_label,
            suggestion_source=suggestion_source,
            ratings=["None", "Low", "Medium", "High"],
        )

    # ---------------------------------------------------------------
    # Browse / review
    # ---------------------------------------------------------------
    @app.route("/browse")
    def browse():
        db = db_module.get_db()
        species_filter = request.args.get("species_id", "")
        status_filter = request.args.get("status", "")
        search = request.args.get("q", "").strip()

        query = """
            SELECT i.*, p.common_name, p.urhobo_name
            FROM images i
            LEFT JOIN plants p ON p.species_id = i.species_id
            WHERE 1=1
        """
        params = []
        if species_filter:
            query += " AND i.species_id = ?"
            params.append(species_filter)
        if status_filter:
            query += " AND i.status = ?"
            params.append(status_filter)
        if search:
            query += " AND (p.common_name LIKE ? OR p.urhobo_name LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])
        query += " ORDER BY i.date_uploaded DESC LIMIT 60"

        images = db.execute(query, params).fetchall()
        plants = db.execute("SELECT * FROM plants ORDER BY common_name").fetchall()

        return render_template("browse.html", images=images, plants=plants,
                                species_filter=species_filter, status_filter=status_filter, search=search)

    # ---------------------------------------------------------------
    # Admin: passcode gate
    # ---------------------------------------------------------------
    @app.route("/admin/login", methods=["GET", "POST"])
    def admin_login():
        if request.method == "POST":
            passcode = request.form.get("passcode", "")
            if passcode == current_app.config["ADMIN_PASSCODE"]:
                session["is_admin"] = True
                flash("Admin panel unlocked.", "success")
                return redirect(request.args.get("next") or url_for("admin_manage"))
            flash("Incorrect passcode.", "error")
        return render_template("admin_login.html")

    @app.route("/admin/logout")
    def admin_logout():
        session.pop("is_admin", None)
        return redirect(url_for("upload"))

    # ---------------------------------------------------------------
    # Admin: manage categories + flagged review
    # ---------------------------------------------------------------
    @app.route("/admin/manage", methods=["GET", "POST"])
    @admin_required
    def admin_manage():
        db = db_module.get_db()

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            if name:
                db.execute("INSERT OR IGNORE INTO use_categories (name) VALUES (?)", (name,))
                db.commit()
                flash(f'Added category "{name}".', "success")
            return redirect(url_for("admin_manage"))

        categories = db.execute("SELECT * FROM use_categories ORDER BY name").fetchall()
        flagged = db.execute(
            """
            SELECT * FROM images
            WHERE status = 'pending'
               OR suggested_species_id IS NULL
               OR suggestion_score < ?
            ORDER BY date_uploaded DESC LIMIT 30
            """,
            (current_app.config["SIMILARITY_THRESHOLD"],),
        ).fetchall()

        return render_template("admin_manage.html", categories=categories, flagged=flagged)

    @app.route("/admin/categories/<int:category_id>/delete", methods=["POST"])
    @admin_required
    def admin_delete_category(category_id):
        db = db_module.get_db()
        db.execute("DELETE FROM use_categories WHERE category_id = ?", (category_id,))
        db.commit()
        flash("Category removed.", "success")
        return redirect(url_for("admin_manage"))

    # ---------------------------------------------------------------
    # Admin: export
    # ---------------------------------------------------------------
    def _export_rows(db):
        return db.execute(
            """
            SELECT
                i.image_id, i.filename, p.common_name AS species, p.urhobo_name,
                p.scientific_name, i.image_type, c.name AS use_category,
                t.effectiveness_rating, i.labeller, i.date_annotated
            FROM images i
            JOIN plants p ON p.species_id = i.species_id
            JOIN image_use_tags t ON t.image_id = i.image_id
            JOIN use_categories c ON c.category_id = t.category_id
            WHERE i.status = 'annotated'
            ORDER BY i.image_id
            """
        ).fetchall()

    @app.route("/admin/export")
    @admin_required
    def admin_export():
        db = db_module.get_db()
        total_images = db.execute("SELECT COUNT(*) c FROM images").fetchone()["c"]
        annotated = db.execute("SELECT COUNT(*) c FROM images WHERE status='annotated'").fetchone()["c"]
        species_count = db.execute("SELECT COUNT(*) c FROM plants").fetchone()["c"]
        preview = _export_rows(db)[:10]
        return render_template(
            "admin_export.html",
            total_images=total_images, annotated=annotated,
            species_count=species_count, preview=preview,
        )

    @app.route("/admin/export/csv")
    @admin_required
    def admin_export_csv():
        db = db_module.get_db()
        rows = _export_rows(db)
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(rows[0].keys() if rows else
                         ["image_id", "filename", "species", "urhobo_name", "scientific_name",
                          "image_type", "use_category", "effectiveness_rating", "labeller", "date_annotated"])
        for r in rows:
            writer.writerow([r[k] for k in r.keys()])
        return Response(
            buf.getvalue(), mimetype="text/csv",
            headers={"Content-Disposition": "attachment; filename=annotations.csv"},
        )

    @app.route("/admin/export/json")
    @admin_required
    def admin_export_json():
        db = db_module.get_db()
        rows = [dict(r) for r in _export_rows(db)]
        return Response(
            json.dumps(rows, indent=2, default=str), mimetype="application/json",
            headers={"Content-Disposition": "attachment; filename=annotations.json"},
        )


app = create_app()

if __name__ == "__main__":
    app.run(debug=True)