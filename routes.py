# routes.py
from flask import (
    Blueprint, render_template, redirect, url_for, request, flash,
    current_app, send_from_directory, session, g
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse, urljoin
from functools import wraps

import os
from time import time
from datetime import datetime
import traceback

from extensions import db
from models import UserDetails, PetDetails, GenderEnum
from forms import RegisterForm, PetForm, LoginForm

from math import ceil
from flask import abort

bp = Blueprint("main", __name__)

ALLOWED_EXT = {"jpg", "jpeg", "png", "gif"}


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


# ----------------------------
# Authentication helpers
# ----------------------------
def login_required(view):
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = UserDetails.query.get(user_id)


def is_safe_url(target):
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return (redirect_url.scheme in ("http", "https") and host_url.netloc == redirect_url.netloc)


# ----------------------------
# Home / index
# ----------------------------
@bp.route("/")
def index():
    # you previously redirected to register — keep the same behaviour
    return redirect(url_for("main.register"))


# ----------------------------
# Register
# ----------------------------
@bp.route("/register/", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        file = request.files.get("user_img")
        filename = None

        # handle image upload
        if file and getattr(file, "filename", None):
            if allowed_file(file.filename):
                safe_name = secure_filename(file.filename)
                uniq_name = f"{int(time())}_{safe_name}"
                upload_dir = current_app.config.get("USER_IMAGE_UPLOADS")
                os.makedirs(upload_dir, exist_ok=True)
                file.save(os.path.join(upload_dir, uniq_name))
                filename = f"user_images/{uniq_name}"
            else:
                flash("Invalid file type", "danger")
                return render_template("register.html", form=form)

        # create user
        new_user = UserDetails(
            user_name=form.user_name.data.strip(),
            user_img=filename,
            user_bio=form.user_bio.data,
            password=generate_password_hash(form.password.data),
            phone_number=form.phone_number.data,
            city=form.city.data,
            state=form.state.data,
            country=form.country.data,
            address=form.address.data,
        )

        db.session.add(new_user)
        try:
            db.session.commit()
            flash("User registered!", "success")
            return redirect(url_for("main.user_list"))
        except Exception as e:
            db.session.rollback()
            # cleanup uploaded image if DB failed
            if filename:
                try:
                    os.remove(os.path.join(current_app.config.get("USER_IMAGE_UPLOADS"), os.path.basename(filename)))
                except Exception:
                    pass
            current_app.logger.exception("Error creating user")
            flash(f"Error registering user: {e}", "danger")

    return render_template("register.html", form=form)


# ----------------------------
# Login / Logout
# ----------------------------
@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    requested_next = request.args.get("next") or request.form.get("next") or url_for("main.index")

    if form.validate_on_submit():
        username = form.user_name.data.strip()
        password = form.password.data

        user = UserDetails.query.filter_by(user_name=username).first()
        if user and check_password_hash(user.password, password):
            session.clear()
            session["user_id"] = user.user_id
            session.permanent = bool(getattr(form, "remember", None) and form.remember.data)

            if requested_next and is_safe_url(requested_next):
                return redirect(requested_next)
            return redirect(url_for("main.index"))
        else:
            flash("Invalid username or password.", "danger")

    return render_template("login.html", form=form, next=requested_next)


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


# ----------------------------
# User list (protected)
# ----------------------------
@bp.route("/users/")
@login_required
def user_list():
    """
    Paginated user list. Querystring: ?page=<n>
    """
    try:
        # page param (1-indexed)
        page = request.args.get("page", 1, type=int)
        per_page = current_app.config.get("USERS_PER_PAGE", 12)  # default 12 per page

        # Using Flask-SQLAlchemy pagination
        pagination = UserDetails.query.order_by(UserDetails.user_id.desc()).paginate(
            page=page, per_page=per_page, error_out=False
        )
        users = pagination.items

        return render_template(
            "user_list.html",
            users=users,
            pagination=pagination
        )
    except Exception:
        current_app.logger.exception("Error loading user list")
        if current_app.debug:
            raise
        return render_template("500.html"), 500

@bp.route("/user/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    """
    Edit the currently logged-in user's profile.
    Only allows the owner to edit their own profile (no admin logic here).
    """
    # ensure user is logged in
    if not g.user:
        flash("Please sign in to edit your profile.", "warning")
        return redirect(url_for("main.login", next=request.path))

    # only allow editing your own profile
    if g.user.user_id != user_id:
        flash("You are not authorized to edit that profile.", "danger")
        return redirect(url_for("main.user_list"))

    # load the user from DB (fresh object)
    user = UserDetails.query.get_or_404(user_id)

    # prefer a dedicated Edit form if you have one; otherwise reuse RegisterForm
    form = RegisterForm(obj=user)

    if form.validate_on_submit():
        # --- helper: determine upload directory safely ---
        try:
            # use helper if available
            upload_dir = get_user_uploads() if "get_user_uploads" in globals() else None
        except Exception:
            upload_dir = None

        if not upload_dir:
            # fallback: MEDIA_ROOT/user_images or app-root/media/user_images
            media_root = current_app.config.get("MEDIA_ROOT") or os.path.join(current_app.root_path, "media")
            upload_dir = current_app.config.get("USER_IMAGE_UPLOADS") or os.path.join(media_root, "user_images")
        # ensure dir exists
        try:
            os.makedirs(upload_dir, exist_ok=True)
        except Exception:
            current_app.logger.exception("Could not create upload directory: %s", upload_dir)

        # --- handle "remove image" request from form (client sets remove_image hidden field) ---
        if request.form.get("remove_image"):
            if user.user_img:
                try:
                    old_path = os.path.join(upload_dir, os.path.basename(user.user_img))
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    current_app.logger.exception("Failed to remove old user image for user %s", user.user_id)
            user.user_img = None

        # --- handle new file upload ---
        file = request.files.get("user_img")
        if file and getattr(file, "filename", None):
            fname = secure_filename(file.filename)
            if fname and allowed_file(fname):
                uniq_name = f"{int(time())}_{fname}"
                save_path = os.path.join(upload_dir, uniq_name)
                try:
                    file.save(save_path)
                except Exception:
                    current_app.logger.exception("Failed to save uploaded file for user %s", user.user_id)
                    flash("Failed to save uploaded image.", "danger")
                    return render_template("edit_user.html", form=form, user=user)

                # delete old image if present
                if user.user_img:
                    try:
                        old_path = os.path.join(upload_dir, os.path.basename(user.user_img))
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    except Exception:
                        current_app.logger.exception("Failed to cleanup previous avatar for user %s", user.user_id)

                # store relative path (same pattern used elsewhere)
                user.user_img = f"user_images/{uniq_name}"
            else:
                flash("Invalid image type (allowed: jpg, jpeg, png, gif).", "danger")
                return render_template("edit_user.html", form=form, user=user)

        # --- update other fields ---
        try:
            user.user_name = form.user_name.data.strip() if form.user_name.data else user.user_name
            user.user_bio = form.user_bio.data
            user.phone_number = form.phone_number.data
            user.city = form.city.data
            user.state = form.state.data
            user.country = form.country.data
            user.address = form.address.data

            # Update password only if provided
            if form.password.data and form.password.data.strip():
                user.password = generate_password_hash(form.password.data.strip())

            db.session.add(user)
            db.session.commit()
            flash("Profile updated successfully.", "success")
            # redirect to profile or users list — choose what's appropriate
            return redirect(url_for("main.user_list"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error updating profile for user %s", user.user_id)
            flash(f"Error updating profile: {e}", "danger")
            return render_template("edit_user.html", form=form, user=user)

    # Pre-fill form (WTForms obj= already set above). Render the edit page.
    return render_template("edit_user.html", form=form, user=user)


# ----------------------------
# Serve uploaded media (public)
# ----------------------------
@bp.route("/media/<path:filename>")
def media(filename):
    # Serve files from MEDIA_ROOT. filename should be relative (e.g. "user_images/foo.png")
    return send_from_directory(current_app.config["MEDIA_ROOT"], filename)


# ----------------------------
# Pet CRUD
# ----------------------------

@bp.route("/pets")
@login_required
def pets_list():
    try:
        pets = PetDetails.query.order_by(PetDetails.pet_id.desc()).all()
        return render_template("pets_list.html", pets=pets)
    except Exception:
        current_app.logger.exception("Error in pets_list route")
        try:
            log_path = current_app.config.get("LOG_FILE", os.path.join(current_app.root_path, "error.log"))
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(f"\n\n[{datetime.utcnow().isoformat()}] Exception in /pets\n")
                traceback.print_exc(file=f)
        except Exception:
            pass
        if current_app.debug:
            raise
        return render_template("500.html"), 500


@bp.route("/pets/add", methods=["GET", "POST"])
@login_required
def add_pet():
    form = PetForm()
    if form.validate_on_submit():
        # validate owner exists
        pet_owner_id = form.pet_owner_id.data
        owner = UserDetails.query.get(pet_owner_id)
        if not owner:
            flash("Owner ID not found.", "danger")
            return render_template("add_pet.html", form=form)

        # image upload
        image_file = form.pet_img.data
        filename = None
        if image_file and getattr(image_file, "filename", None):
            filename_raw = secure_filename(image_file.filename)
            if filename_raw and allowed_file(filename_raw):
                upload_dir = current_app.config.get("USER_IMAGE_UPLOADS")
                os.makedirs(upload_dir, exist_ok=True)
                _, ext = os.path.splitext(filename_raw)
                uniq = f"pet_{int(time())}{ext}"
                save_path = os.path.join(upload_dir, uniq)
                image_file.save(save_path)
                filename = f"user_images/{uniq}"

        # convert gender to GenderEnum
        pet_male_female_raw = form.pet_male_female.data
        pet_male_female = GenderEnum(pet_male_female_raw) if pet_male_female_raw else None

        pet = PetDetails(
            pet_name=form.pet_name.data.strip(),
            pet_owner_id=pet_owner_id,
            pet_img=filename,
            pet_age=form.pet_age.data,
            pet_licence_id=form.pet_licence_id.data.strip() if form.pet_licence_id.data else None,
            pet_type=form.pet_type.data.strip() if form.pet_type.data else None,
            pet_colour=form.pet_colour.data.strip() if form.pet_colour.data else None,
            pet_male_female=pet_male_female
        )

        db.session.add(pet)
        try:
            db.session.commit()
            flash("Pet added successfully.", "success")
            return redirect(url_for("main.pets_list"))
        except Exception as e:
            db.session.rollback()
            # cleanup uploaded image if commit failed
            if filename:
                try:
                    os.remove(os.path.join(current_app.config.get("USER_IMAGE_UPLOADS"), os.path.basename(filename)))
                except Exception:
                    pass
            current_app.logger.exception("Error adding pet")
            flash(f"Error adding pet: {e}", "danger")

    return render_template("add_pet.html", form=form)


@bp.route("/pets/<int:pet_id>")
@login_required
def view_pet(pet_id):
    pet = PetDetails.query.get_or_404(pet_id)
    return render_template("view_pet.html", pet=pet)


@bp.route("/pets/edit/<int:pet_id>", methods=["GET", "POST"])
@login_required
def edit_pet(pet_id):
    pet = PetDetails.query.get_or_404(pet_id)
    form = PetForm(obj=pet)

    if form.validate_on_submit():
        # validate owner exists
        pet_owner_id = form.pet_owner_id.data
        owner = UserDetails.query.get(pet_owner_id)
        if not owner:
            flash("Owner ID not found.", "danger")
            return render_template("edit_pet.html", form=form, pet=pet)

        pet.pet_name = form.pet_name.data.strip()
        pet.pet_owner_id = pet_owner_id
        pet.pet_age = form.pet_age.data
        pet.pet_licence_id = form.pet_licence_id.data.strip() if form.pet_licence_id.data else None
        pet.pet_type = form.pet_type.data.strip() if form.pet_type.data else None
        pet.pet_colour = form.pet_colour.data.strip() if form.pet_colour.data else None

        # handle new image
        image_file = form.pet_img.data
        if image_file and getattr(image_file, "filename", None):
            filename_raw = secure_filename(image_file.filename)
            if filename_raw and allowed_file(filename_raw):
                upload_dir = current_app.config.get("USER_IMAGE_UPLOADS")
                os.makedirs(upload_dir, exist_ok=True)
                _, ext = os.path.splitext(filename_raw)
                uniq = f"pet_{int(time())}{ext}"
                save_path = os.path.join(upload_dir, uniq)
                image_file.save(save_path)

                # delete old image file if present
                if pet.pet_img:
                    try:
                        os.remove(os.path.join(upload_dir, os.path.basename(pet.pet_img)))
                    except Exception:
                        pass

                pet.pet_img = f"user_images/{uniq}"

        # convert gender string to enum
        pet_male_female_raw = form.pet_male_female.data
        pet.pet_male_female = GenderEnum(pet_male_female_raw) if pet_male_female_raw else None

        try:
            db.session.commit()
            flash("Pet updated successfully.", "success")
            return redirect(url_for("main.pets_list"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error updating pet")
            flash(f"Error updating pet: {e}", "danger")

    # Preselect the select field (WTForms expects string value)
    form.pet_male_female.data = pet.pet_male_female.value if pet.pet_male_female else None
    return render_template("edit_pet.html", form=form, pet=pet)


@bp.route("/pets/delete/<int:pet_id>", methods=["POST"])
@login_required
def delete_pet(pet_id):
    pet = PetDetails.query.get_or_404(pet_id)
    try:
        if pet.pet_img:
            try:
                upload_dir = current_app.config.get("USER_IMAGE_UPLOADS")
                os.remove(os.path.join(upload_dir, os.path.basename(pet.pet_img)))
            except Exception:
                pass

        db.session.delete(pet)
        db.session.commit()
        flash("Pet deleted.", "info")
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception("Error deleting pet")
        flash(f"Error deleting pet: {e}", "danger")

    return redirect(url_for("main.pets_list"))
