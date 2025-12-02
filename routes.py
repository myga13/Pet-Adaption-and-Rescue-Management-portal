from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    request,
    flash,
    current_app,
    send_from_directory,
    session,
    g,
    abort,
    jsonify,
)
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse, urljoin
from functools import wraps
from flask_wtf.csrf import generate_csrf

import os
from time import time
from datetime import datetime, timedelta
import traceback
import random
import string
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

from extensions import db
from models import (
    UserDetails,
    PetDetails,
    GenderEnum,
    Admin,
    PetAdoptionRequest,
    AdoptionList,
    ContactMessage,
    FoundPetReport,
    LostPetReport,
)
from models import LostPetReport 
from forms import RegisterForm, PetForm, LoginForm

bp = Blueprint("main", __name__)

ALLOWED_EXT = {"jpg", "jpeg", "png", "gif"}


# ============================
#  AUTH DECORATORS & HELPERS
# ============================


def login_required(view):
    """For normal user login."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "user_id" not in session:
            flash("Please log in to access this page.", "warning")
            return redirect(url_for("main.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view

def admin_login_required(view):
    """For admin-only routes."""
    @wraps(view)
    def wrapped_view(*args, **kwargs):
        if "admin_id" not in session:
            flash("Please log in as admin to access this page.", "warning")
            return redirect(url_for("main.admin_login", next=request.path))
        return view(*args, **kwargs)
    return wrapped_view


def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXT


def is_safe_url(target):
    host_url = urlparse(request.host_url)
    redirect_url = urlparse(urljoin(request.host_url, target))
    return (
        redirect_url.scheme in ("http", "https")
        and host_url.netloc == redirect_url.netloc
    )


@bp.before_app_request
def load_logged_in_user():
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        g.user = UserDetails.query.get(user_id)

    admin_id = session.get("admin_id")
    if admin_id is None:
        g.admin = None
    else:
        g.admin = Admin.query.get(admin_id)



# ============================
#  ADOPTION NOTIFICATION INJECTION
# ============================

@bp.context_processor
def inject_adoption_notifications():
    """
    Inject into all templates:
      - pending_adoption_count    (pending requests for pets you own)
      - pending_adoption_requests (full rows)
      - my_adoption_updates       (your own requests accepted/rejected)
    """
    if getattr(g, "user", None) is None:
        return dict(
            pending_adoption_count=0,
            pending_adoption_requests=[],
            my_adoption_updates=[],
        )

    user_id = g.user.user_id

    # 1) Requests for pets YOU own (owner side, pending only)
    owner_requests = (
        db.session.query(
            PetAdoptionRequest.request_id,
            PetAdoptionRequest.pet_id,
            PetAdoptionRequest.requester_id,
            PetAdoptionRequest.request_status,
            PetAdoptionRequest.requested_at,
            PetDetails.pet_name,
        )
        .join(PetDetails, PetDetails.pet_id == PetAdoptionRequest.pet_id)
        .join(AdoptionList, AdoptionList.pet_id == PetAdoptionRequest.pet_id)
        .filter(
            PetDetails.pet_owner_id == user_id,
            PetAdoptionRequest.request_status == "pending",
            AdoptionList.status == "pending",  # only if pet is still open for adoption
        )
        .all()
    )

    # 2) Your own adoption requests that were accepted or rejected (requester side)
    my_updates = (
        db.session.query(
            PetAdoptionRequest.request_id,
            PetAdoptionRequest.pet_id,
            PetAdoptionRequest.request_status,
            PetAdoptionRequest.requested_at,
            PetDetails.pet_name,
        )
        .join(PetDetails, PetDetails.pet_id == PetAdoptionRequest.pet_id)
        .filter(
            PetAdoptionRequest.requester_id == user_id,
            PetAdoptionRequest.request_status.in_(["accepted", "rejected"]),
        )
        .order_by(PetAdoptionRequest.requested_at.desc())
        .limit(10)
        .all()
    )

    return dict(
        pending_adoption_count=len(owner_requests),
        pending_adoption_requests=owner_requests,
        my_adoption_updates=my_updates,
    )


# ============================
#  ADOPTION: SEND FOR ADOPTION
# ============================

@bp.route("/pets/<int:pet_id>/send-for-adoption", methods=["POST"])
@login_required
def send_for_adoption(pet_id):
    pet = PetDetails.query.get_or_404(pet_id)

    # Only owner can send this pet for adoption
    if not g.user or g.user.user_id != pet.pet_owner_id:
        flash("You are not allowed to send this pet for adoption.", "danger")
        return redirect(url_for("main.my_pets"))

    adoption = AdoptionList.query.filter_by(pet_id=pet_id).first()

    try:
        if adoption:
            if adoption.status == "pending":
                flash("This pet is already open for adoption.", "info")
            else:
                adoption.status = "pending"
                db.session.commit()
                flash("Pet re-opened for adoption.", "success")
        else:
            new_entry = AdoptionList(pet_id=pet_id, status="pending")
            db.session.add(new_entry)
            db.session.commit()
            flash("Pet sent for adoption.", "success")
    except Exception as e:
        db.session.rollback()
        current_app.logger.exception(f"Error in send_for_adoption: {e}")
        flash("Error sending pet for adoption.", "danger")

    return redirect(url_for("main.my_pets"))


# ============================
#  ADOPTION REQUEST ROUTE (USER → OWNER)
# ============================

@bp.route("/adoption/request/<int:pet_id>", methods=["POST"])
@login_required
def request_adoption(pet_id):
    try:
        user = g.user
        if user is None:
            flash("Please sign in to request adoption.", "warning")
            return redirect(url_for("main.login"))

        requester_id = user.user_id
        pet = PetDetails.query.get_or_404(pet_id)

        # 1) Owner cannot request own pet
        if pet.pet_owner_id == requester_id:
            flash("You already own this pet.", "info")
            return redirect(url_for("main.adoption_pets"))

        # 2) Check adoption_list: must be pending
        adoption = AdoptionList.query.filter_by(pet_id=pet_id).first()
        if not adoption or adoption.status != "pending":
            flash("This pet is not available for adoption.", "warning")
            return redirect(url_for("main.adoption_pets"))

        # 3) Avoid duplicate pending requests
        existing = PetAdoptionRequest.query.filter_by(
            pet_id=pet_id,
            requester_id=requester_id,
            request_status="pending",
        ).first()

        if existing:
            flash("You already have a pending request for this pet.", "info")
            return redirect(url_for("main.adoption_pets"))

        # 4) Create adoption request
        new_request = PetAdoptionRequest(
            pet_id=pet_id,
            requester_id=requester_id,
            request_status="pending",
        )
        db.session.add(new_request)
        db.session.commit()

        flash("Adoption request sent to the owner!", "success")
        return redirect(url_for("main.adoption_pets"))

    except Exception as e:
        current_app.logger.exception(f"Error in request_adoption: {e}")
        db.session.rollback()
        flash("Something went wrong while sending your request.", "danger")
        return redirect(url_for("main.adoption_pets"))


# ============================
#  ADOPTION ACCEPT / REJECT
# ============================

@bp.route("/adoption/accept/<int:request_id>", methods=["POST"])
@login_required
def accept_adoption(request_id):
    user = getattr(g, "user", None)
    if user is None:
        flash("Please sign in to perform this action.", "warning")
        return redirect(url_for("main.login"))

    req = PetAdoptionRequest.query.get_or_404(request_id)
    pet = PetDetails.query.get_or_404(req.pet_id)

    # Only owner can accept
    if pet.pet_owner_id != user.user_id:
        flash("You are not the owner of this pet.", "danger")
        return redirect(url_for("main.view_pet", pet_id=pet.pet_id))

    if req.request_status != "pending":
        flash(f"Request is already {req.request_status}.", "info")
        return redirect(url_for("main.view_pet", pet_id=pet.pet_id))

    try:
        # 1) Accept this request
        req.request_status = "accepted"

        # 2) Transfer pet owner
        pet.pet_owner_id = req.requester_id

        # 3) Reject all other pending requests for this pet
        PetAdoptionRequest.query.filter(
            PetAdoptionRequest.pet_id == pet.pet_id,
            PetAdoptionRequest.request_id != req.request_id,
            PetAdoptionRequest.request_status == "pending",
        ).update({PetAdoptionRequest.request_status: "rejected"})

        # 4) Mark adoption_list as completed
        adoption = AdoptionList.query.filter_by(pet_id=pet.pet_id).first()
        if adoption:
            adoption.status = "completed"

        db.session.commit()
        flash("Adoption accepted. Ownership transferred.", "success")
    except Exception as e:
        current_app.logger.exception(f"Error in accept_adoption: {e}")
        db.session.rollback()
        flash("Error while accepting request.", "danger")

    return redirect(url_for("main.view_pet", pet_id=pet.pet_id))


@bp.route("/adoption/reject/<int:request_id>", methods=["POST"])
@login_required
def reject_adoption(request_id):
    """Owner rejects a single adoption request; other requests remain."""
    user = getattr(g, "user", None)
    if user is None:
        flash("Please sign in to perform this action.", "warning")
        return redirect(url_for("main.login"))

    req = PetAdoptionRequest.query.get_or_404(request_id)
    pet = PetDetails.query.get_or_404(req.pet_id)

    if pet.pet_owner_id != user.user_id:
        flash("You are not the owner of this pet.", "danger")
        return redirect(url_for("main.view_pet", pet_id=pet.pet_id))

    if req.request_status != "pending":
        flash(f"Request is already {req.request_status}.", "info")
        return redirect(url_for("main.view_pet", pet_id=pet.pet_id))

    try:
        req.request_status = "rejected"
        db.session.commit()
        flash("Adoption request rejected.", "info")
    except Exception as e:
        current_app.logger.exception(f"Error in reject_adoption: {e}")
        db.session.rollback()
        flash("Error while rejecting request.", "danger")

    return redirect(url_for("main.view_pet", pet_id=pet.pet_id))


# ============================
#  EMAIL / OTP CONFIG
# ============================

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587
SENDER_EMAIL = "pawcarengo@gmail.com"
SENDER_PASSWORD = "bhqravwitybfnspi"  # app password


def send_otp_email(to_email: str, otp: str):
    recipient_email = to_email
    subject = "PawCare Admin Login OTP"
    body = f"""
    Dear Sir/Madam,

    Your PawCare admin login OTP is: {otp}.

    This OTP is valid for a short time. Do not share it with anyone.

    Thank you,
    PawCare Team
    """

    if not recipient_email or not SENDER_EMAIL or not subject:
        print("Missing required fields for OTP email")
        return

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()
        print("OTP email sent successfully.")
    except Exception as e:
        print(f"Failed to send OTP email: {e}")


def send_admin_code_email(to_email: str, code: str):
    recipient_email = to_email
    subject = "PawCare Admin Registration Code"
    body = f"""
    Dear Sir/Madam,

    Thank you for registering as a PawCare admin.

    Your unique admin registration verification code is: {code}

    Please enter this code on the registration form to complete creation
    of your admin account.

    Thank you,
    PawCare Team
    """

    if not recipient_email or not SENDER_EMAIL or not subject:
        print("Missing required fields for admin code email")
        return

    msg = MIMEMultipart()
    msg["From"] = SENDER_EMAIL
    msg["To"] = recipient_email
    msg["Subject"] = subject
    msg.attach(MIMEText(body, "plain"))

    try:
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(SENDER_EMAIL, SENDER_PASSWORD)
        server.sendmail(SENDER_EMAIL, recipient_email, msg.as_string())
        server.quit()
        print("Admin code email sent successfully.")
    except Exception as e:
        print(f"Failed to send admin code email: {e}")


# ============================
#  ADMIN EMAIL VERIFICATION API (SEND CODE)
# ============================

@bp.route("/admin/send-email-code", methods=["POST"])
def send_email_verification_code():
    """
    AJAX endpoint:
    Expects JSON: { "email": "user@example.com" }
    Stores code in session["admin_email_verification"].
    """
    data = request.get_json(silent=True) or {}
    email = (data.get("email") or "").strip()

    if not email:
        return jsonify({"success": False, "message": "Email is required."}), 400

    # optionally block if email already registered
    if Admin.query.filter_by(email=email).first():
        return jsonify({
            "success": False,
            "message": "An admin with this email already exists."
        }), 400

    code = f"{random.randint(0, 999999):06d}"

    session["admin_email_verification"] = {
        "email": email,
        "code": code,
        "created_at": int(time())
    }

    try:
        send_admin_code_email(email, code)
    except Exception as e:
        current_app.logger.exception("Error sending admin verification code email")
        return jsonify({"success": False, "message": "Could not send verification email."}), 500

    return jsonify({"success": True})


# ============================
#  ADMIN REGISTRATION / LOGIN
# ============================

@bp.route("/admin/register", methods=["GET", "POST"])
def admin_register():
    if request.method == "POST":
        pwd = request.form.get("password")
        cpwd = request.form.get("confirm_password")

        if not pwd or pwd != cpwd:
            flash("Passwords do not match.", "danger")
            return render_template("admin_register.html")

        email = (request.form.get("email") or "").strip()
        if Admin.query.filter_by(email=email).first():
            flash("An admin with this email already exists.", "warning")
            return render_template("admin_register.html")

        # ===== EMAIL VERIFICATION CHECK =====
        input_code = (request.form.get("email_verification_code") or "").strip()
        ver_data = session.get("admin_email_verification")

        if not ver_data:
            flash("Please verify your email by clicking 'Send Code' and entering the code sent to your inbox.", "danger")
            return render_template("admin_register.html")

        stored_email = ver_data.get("email")
        stored_code = ver_data.get("code")
        created_at = ver_data.get("created_at", 0)

        # expire after 10 minutes
        now_ts = int(time())
        if now_ts - int(created_at) > 600:
            session.pop("admin_email_verification", None)
            flash("Verification code has expired. Please request a new code.", "danger")
            return render_template("admin_register.html")

        if email != stored_email:
            flash("The email address does not match the one that was verified. Please resend the code.", "danger")
            return render_template("admin_register.html")

        if not input_code or input_code != stored_code:
            flash("Invalid verification code. Please check your email and try again.", "danger")
            return render_template("admin_register.html")

        # If we reach here, email is verified
        session.pop("admin_email_verification", None)

        admin = Admin(
            full_name=request.form.get("full_name"),
            age=request.form.get("age"),
            email=email,
            phone=request.form.get("phone"),
            address=request.form.get("address"),
            city=request.form.get("city"),
            state=request.form.get("state"),
            current_location=request.form.get("current_location"),
            admin_role=request.form.get("admin_role"),
            experience_years=request.form.get("experience_years") or None,
            past_experience=request.form.get("past_experience"),
            ngo_name=request.form.get("ngo_name"),
            ngo_designation=request.form.get("ngo_designation"),
            ngo_years=request.form.get("ngo_years") or None,
            id_proof_type=request.form.get("id_proof_type"),
            id_proof_number=request.form.get("id_proof_number"),
            emergency_name=request.form.get("emergency_name"),
            emergency_relation=request.form.get("emergency_relation"),
            emergency_phone=request.form.get("emergency_phone"),
            emergency_phone_alt=request.form.get("emergency_phone_alt"),
            linkedin=request.form.get("linkedin"),
            instagram=request.form.get("instagram"),
        )

        admin.set_password(pwd)

        admin_profile_dir = current_app.config.get(
            "ADMIN_PROFILE_UPLOADS",
            os.path.join(current_app.root_path, "media", "admin_profiles"),
        )
        admin_id_dir = current_app.config.get(
            "ADMIN_ID_UPLOADS",
            os.path.join(current_app.root_path, "media", "admin_ids"),
        )
        os.makedirs(admin_profile_dir, exist_ok=True)
        os.makedirs(admin_id_dir, exist_ok=True)

        profile_image = request.files.get("profile_image")
        if profile_image and profile_image.filename:
            filename = secure_filename(profile_image.filename)
            filepath = os.path.join(admin_profile_dir, filename)
            profile_image.save(filepath)
            admin.profile_image = filename

        id_proof_file = request.files.get("id_proof_file")
        if id_proof_file and id_proof_file.filename:
            filename = secure_filename(id_proof_file.filename)
            filepath = os.path.join(admin_id_dir, filename)
            id_proof_file.save(filepath)
            admin.id_proof_file = filename

        db.session.add(admin)
        try:
            db.session.commit()
            flash("Admin registered successfully! You can now login.", "success")
            return redirect(url_for("main.admin_login"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error registering admin")
            flash(f"Error registering admin: {e}", "danger")

    return render_template("admin_register.html")


@bp.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip()
        password = request.form.get("password")

        admin = Admin.query.filter_by(email=email).first()
        if not admin or not admin.check_password(password):
            flash("Invalid email or password.", "danger")
            return render_template("admin_login.html")

        if not admin.is_active:
            flash("Your admin account is deactivated. Contact super admin.", "warning")
            return render_template("admin_login.html")

        otp = f"{random.randint(100000, 999999)}"
        session["admin_otp"] = otp
        session["admin_otp_email"] = admin.email
        session["name"] = admin.full_name
        session["admin_otp_expires"] = (
            datetime.utcnow() + timedelta(minutes=10)
        ).isoformat()

        send_otp_email(admin.email, otp)

        flash("OTP sent to your admin email. Please verify.", "info")
        return redirect(url_for("main.admin_verify_otp"))

    return render_template("admin_login.html")


@bp.route("/admin/verify-otp", methods=["GET", "POST"])
def admin_verify_otp():
    otp_stored = session.get("admin_otp")
    email = session.get("admin_otp_email")
    expires_raw = session.get("admin_otp_expires")

    if not otp_stored or not email or not expires_raw:
        flash("OTP session expired or invalid. Please login again.", "warning")
        return redirect(url_for("main.admin_login"))

    try:
        expires_at = datetime.fromisoformat(expires_raw)
        if datetime.utcnow() > expires_at:
            session.pop("admin_otp", None)
            session.pop("admin_otp_email", None)
            session.pop("admin_otp_expires", None)
            flash("OTP expired. Please login again.", "warning")
            return redirect(url_for("main.admin_login"))
    except Exception:
        flash("Invalid OTP session. Please login again.", "warning")
        return redirect(url_for("main.admin_login"))

    if request.method == "POST":
        user_otp = (request.form.get("otp") or "").strip()
        if user_otp == otp_stored:
            admin = Admin.query.filter_by(email=email).first()
            if not admin:
                flash("Admin account not found.", "danger")
                return redirect(url_for("main.admin_login"))

            session.pop("admin_otp", None)
            session.pop("admin_otp_email", None)
            session.pop("admin_otp_expires", None)

            session["admin_id"] = admin.id
            flash("Admin login successful.", "success")
            return redirect(url_for("main.admin_dashboard"))
        else:
            flash("Incorrect OTP. Please try again.", "danger")

    return render_template("admin_verify_otp.html", email=email)


@bp.route("/admin/dashboard")
@admin_login_required
def admin_dashboard():
    # load reports
    found_reports = FoundPetReport.query.order_by(FoundPetReport.created_at.desc()).all()
    lost_reports = LostPetReport.query.order_by(LostPetReport.created_at.desc()).all()

    # derive img filename if g.admin exists and has profile image
    img_filename = None
    if getattr(g, "admin", None) and getattr(g.admin, "profile_image", None):
        img_filename = f"admin_profiles/{g.admin.profile_image}"
    csrf_token_value = generate_csrf()
    return render_template(
        "admin_dashboard.html",
        found_reports=found_reports,
        lost_reports=lost_reports,
        img_filename=img_filename,
        csrf_token_value=csrf_token_value
    )

# ============================
#  HOME / INDEX (user)
# ============================

@bp.route("/")
def index():
    return render_template("index.html")


@bp.route('/about')
def about():
    return render_template('about.html')


@bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        name = request.form.get('name')
        email = request.form.get('email')
        phone = request.form.get('phone')
        subject = request.form.get('subject')
        message = request.form.get('message')

        if not all([name, email, subject, message]):
            flash('Please fill all required fields.', 'danger')
            return redirect(url_for('main.contact'))

        try:
            contact_msg = ContactMessage(
                name=name.strip(),
                email=email.strip(),
                phone=(phone or "").strip(),
                subject=subject.strip(),
                message=message.strip(),
            )
            db.session.add(contact_msg)
            db.session.commit()
            flash('Thank you for reaching out. We will get back to you soon!', 'success')
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error saving contact message")
            flash('Something went wrong while submitting your message.', 'danger')

        return redirect(url_for('main.contact'))

    return render_template('contact.html')


# ============================
#  USER REGISTER / LOGIN / LOGOUT
# ============================

@bp.route("/register/", methods=["GET", "POST"])
def register():
    form = RegisterForm()
    if form.validate_on_submit():
        file = request.files.get("user_img")
        filename = None

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
            email=form.email.data.strip(),
        )

        db.session.add(new_user)
        try:
            db.session.commit()
            flash("User registered!", "success")
            return redirect(url_for("main.index"))
        except Exception as e:
            db.session.rollback()
            if filename:
                try:
                    os.remove(
                        os.path.join(
                            current_app.config.get("USER_IMAGE_UPLOADS"),
                            os.path.basename(filename),
                        )
                    )
                except Exception:
                    pass
            current_app.logger.exception("Error creating user")
            flash(f"Error registering user: {e}", "danger")

    return render_template("register.html", form=form)


@bp.route("/login", methods=["GET", "POST"])
def login():
    form = LoginForm()
    requested_next = (
        request.args.get("next")
        or request.form.get("next")
        or url_for("main.index")
    )

    if form.validate_on_submit():
        email = (form.email.data or "").strip()
        password = form.password.data

        user = UserDetails.query.filter_by(email=email).first()

        if user and check_password_hash(user.password, password):
            session.clear()
            session["user_id"] = user.user_id

            session.permanent = bool(
                getattr(form, "remember", None) and form.remember.data
            )

            if requested_next and is_safe_url(requested_next):
                return redirect(requested_next)
            return redirect(url_for("main.index"))
        else:
            flash("Invalid email or password.", "danger")

    return render_template("login.html", form=form, next=requested_next)


@bp.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for("main.index"))


# ============================
#  USER LIST / EDIT PROFILE
# ============================

@bp.route("/users/")
@login_required
def user_list():
    try:
        page = request.args.get("page", 1, type=int)
        per_page = current_app.config.get("USERS_PER_PAGE", 12)

        pagination = UserDetails.query.order_by(
            UserDetails.user_id.desc()
        ).paginate(page=page, per_page=per_page, error_out=False)
        users = pagination.items

        return render_template(
            "user_list.html",
            users=users,
            pagination=pagination,
        )
    except Exception:
        current_app.logger.exception("Error loading user list")
        if current_app.debug:
            raise
        return render_template("500.html"), 500


@bp.route("/user/edit/<int:user_id>", methods=["GET", "POST"])
@login_required
def edit_user(user_id):
    if not g.user:
        flash("Please sign in to edit your profile.", "warning")
        return redirect(url_for("main.login", next=request.path))

    if g.user.user_id != user_id:
        flash("You are not authorized to edit that profile.", "danger")
        return redirect(url_for("main.user_list"))

    user = UserDetails.query.get_or_404(user_id)
    form = RegisterForm(obj=user)

    if form.validate_on_submit():
        upload_dir = None
        try:
            if "get_user_uploads" in globals():
                upload_dir = get_user_uploads()
        except Exception:
            upload_dir = None

        if not upload_dir:
            media_root = current_app.config.get("MEDIA_ROOT") or os.path.join(
                current_app.root_path, "media"
            )
            upload_dir = current_app.config.get("USER_IMAGE_UPLOADS") or os.path.join(
                media_root, "user_images"
            )
        try:
            os.makedirs(upload_dir, exist_ok=True)
        except Exception:
            current_app.logger.exception(
                "Could not create upload directory: %s", upload_dir
            )

        if request.form.get("remove_image"):
            if user.user_img:
                try:
                    old_path = os.path.join(
                        upload_dir, os.path.basename(user.user_img)
                    )
                    if os.path.exists(old_path):
                        os.remove(old_path)
                except Exception:
                    current_app.logger.exception(
                        "Failed to remove old user image for user %s",
                        user.user_id,
                    )
            user.user_img = None

        file = request.files.get("user_img")
        if file and getattr(file, "filename", None):
            fname = secure_filename(file.filename)
            if fname and allowed_file(fname):
                uniq_name = f"{int(time())}_{fname}"
                save_path = os.path.join(upload_dir, uniq_name)
                try:
                    file.save(save_path)
                except Exception:
                    current_app.logger.exception(
                        "Failed to save uploaded file for user %s", user.user_id
                    )
                    flash("Failed to save uploaded image.", "danger")
                    return render_template(
                        "edit_user.html", form=form, user=user
                    )

                if user.user_img:
                    try:
                        old_path = os.path.join(
                            upload_dir, os.path.basename(user.user_img)
                        )
                        if os.path.exists(old_path):
                            os.remove(old_path)
                    except Exception:
                        current_app.logger.exception(
                            "Failed to cleanup previous avatar for user %s",
                            user.user_id,
                        )

                user.user_img = f"user_images/{uniq_name}"
            else:
                flash(
                    "Invalid image type (allowed: jpg, jpeg, png, gif).",
                    "danger",
                )
                return render_template(
                    "edit_user.html", form=form, user=user
                )

        try:
            user.user_name = (
                form.user_name.data.strip()
                if form.user_name.data
                else user.user_name
            )
            user.user_bio = form.user_bio.data
            user.phone_number = form.phone_number.data
            user.city = form.city.data
            user.state = form.state.data
            user.country = form.country.data
            user.address = form.address.data

            if form.email.data:
                user.email = form.email.data.strip()

            if form.password.data and form.password.data.strip():
                user.password = generate_password_hash(
                    form.password.data.strip()
                )

            db.session.add(user)
            db.session.commit()
            flash("Profile updated successfully.", "success")
            return redirect(url_for("main.user_list"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception(
                "Error updating profile for user %s", user.user_id
            )
            flash(f"Error updating profile: {e}", "danger")
            return render_template("edit_user.html", form=form, user=user)

    return render_template("edit_user.html", form=form, user=user)


# ============================
#  MEDIA
# ============================

@bp.route("/media/<path:filename>")
def media(filename):
    return send_from_directory(current_app.config["MEDIA_ROOT"], filename)


# ============================
#  PET CRUD
# ============================

@bp.route("/pets")
@login_required
def pets_list():
    try:
        pets = PetDetails.query.order_by(PetDetails.pet_id.desc()).all()
        return render_template("pets_list.html", pets=pets)
    except Exception:
        current_app.logger.exception("Error in pets_list route")
        try:
            log_path = current_app.config.get(
                "LOG_FILE",
                os.path.join(current_app.root_path, "error.log"),
            )
            with open(log_path, "a", encoding="utf-8") as f:
                f.write(
                    f"\n\n[{datetime.utcnow().isoformat()}] Exception in /pets\n"
                )
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
        pet_owner_id = form.pet_owner_id.data
        owner = UserDetails.query.get(pet_owner_id)
        if not owner:
            flash("Owner ID not found.", "danger")
            return render_template("add_pet.html", form=form)

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

        pet_male_female_raw = form.pet_male_female.data
        pet_male_female = (
            GenderEnum(pet_male_female_raw) if pet_male_female_raw else None
        )

        pet = PetDetails(
            pet_name=form.pet_name.data.strip(),
            pet_owner_id=pet_owner_id,
            pet_img=filename,
            pet_age=form.pet_age.data,
            pet_licence_id=(
                form.pet_licence_id.data.strip()
                if form.pet_licence_id.data
                else None
            ),
            pet_type=(
                form.pet_type.data.strip()
                if form.pet_type.data
                else None
            ),
            pet_colour=(
                form.pet_colour.data.strip()
                if form.pet_colour.data
                else None
            ),
            pet_male_female=pet_male_female,
        )

        db.session.add(pet)
        try:
            db.session.commit()
            flash("Pet added successfully.", "success")
            return redirect(url_for("main.pets_list"))
        except Exception as e:
            db.session.rollback()
            if filename:
                try:
                    os.remove(
                        os.path.join(
                            current_app.config.get("USER_IMAGE_UPLOADS"),
                            os.path.basename(filename),
                        )
                    )
                except Exception:
                    pass
            current_app.logger.exception("Error adding pet")
            flash(f"Error adding pet: {e}", "danger")

    return render_template("add_pet.html", form=form)


@bp.route("/profile")
def profile():
    return render_template("profile_dashboard.html")


@bp.route("/user/profile")
def user_profile():
    return render_template("something.html")


@bp.route("/pets/<int:pet_id>")
@login_required
def view_pet(pet_id):
    pet = PetDetails.query.get_or_404(pet_id)

    pending_requests = []
    user = getattr(g, "user", None)

    # Only load adoption requests if logged-in user is the owner
    if user is not None and user.user_id == pet.pet_owner_id:
        pending_requests = PetAdoptionRequest.query.filter_by(
            pet_id=pet_id,
            request_status="pending",
        ).all()

    return render_template(
        "view_pet.html",
        pet=pet,
        pending_requests=pending_requests,
    )


@bp.route("/pets/edit/<int:pet_id>", methods=["GET", "POST"])
@login_required
def edit_pet(pet_id):
    pet = PetDetails.query.get_or_404(pet_id)
    form = PetForm(obj=pet)

    if form.validate_on_submit():
        pet_owner_id = form.pet_owner_id.data
        owner = UserDetails.query.get(pet_owner_id)
        if not owner:
            flash("Owner ID not found.", "danger")
            return render_template("edit_pet.html", form=form, pet=pet)

        pet.pet_name = form.pet_name.data.strip()
        pet.pet_owner_id = pet_owner_id
        pet.pet_age = form.pet_age.data
        pet.pet_licence_id = (
            form.pet_licence_id.data.strip()
            if form.pet_licence_id.data
            else None
        )
        pet.pet_type = (
            form.pet_type.data.strip() if form.pet_type.data else None
        )
        pet.pet_colour = (
            form.pet_colour.data.strip()
            if form.pet_colour.data
            else None
        )

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

                if pet.pet_img:
                    try:
                        os.remove(
                            os.path.join(
                                upload_dir, os.path.basename(pet.pet_img)
                            )
                        )
                    except Exception:
                        pass

                pet.pet_img = f"user_images/{uniq}"

        pet_male_female_raw = form.pet_male_female.data
        pet.pet_male_female = (
            GenderEnum(pet_male_female_raw) if pet_male_female_raw else None
        )

        try:
            db.session.commit()
            flash("Pet updated successfully.", "success")
            return redirect(url_for("main.my_pets"))
        except Exception as e:
            db.session.rollback()
            current_app.logger.exception("Error updating pet")
            flash(f"Error updating pet: {e}", "danger")

    form.pet_male_female.data = (
        pet.pet_male_female.value if pet.pet_male_female else None
    )
    return render_template("edit_pet.html", form=form, pet=pet)


@bp.route("/pets/delete/<int:pet_id>", methods=["POST"])
@login_required
def delete_pet(pet_id):
    pet = PetDetails.query.get_or_404(pet_id)
    try:
        if pet.pet_img:
            try:
                upload_dir = current_app.config.get("USER_IMAGE_UPLOADS")
                os.remove(
                    os.path.join(upload_dir, os.path.basename(pet.pet_img))
                )
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


# ============================
#  MY PETS / ADOPTION PETS
# ============================

@bp.route("/mypets")
@login_required
def my_pets():
    if not g.user:
        flash("Please sign in.", "warning")
        return redirect(url_for("main.login"))

    pets = (
        PetDetails.query
        .filter_by(pet_owner_id=g.user.user_id)
        .order_by(PetDetails.pet_id.desc())
        .all()
    )
    return render_template("mypets.html", pets=pets)


@bp.route("/adoptions")
@login_required
def adoption_pets():
    if not g.user:
        flash("Please sign in.", "warning")
        return redirect(url_for("main.login"))

    pets = (
        db.session.query(PetDetails)
        .join(AdoptionList, AdoptionList.pet_id == PetDetails.pet_id)
        .filter(
            PetDetails.pet_owner_id != g.user.user_id,
            AdoptionList.status == "pending",
        )
        .order_by(PetDetails.pet_id.desc())
        .all()
    )
    return render_template("adoption_pets.html", pets=pets)


# ============================
#  report PETS (FOUND)
# ============================
@bp.route("/report-found-pet", methods=["GET", "POST"])
def report_found_pet():
    if request.method == "POST":
        pet_type = request.form.get("pet_type")
        found_location = request.form.get("found_location")
        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        date_found_str = request.form.get("date_found")
        pet_condition = request.form.get("condition")

        finder_name = request.form.get("finder_name")
        finder_phone = request.form.get("finder_phone")
        finder_whatsapp = request.form.get("finder_whatsapp")
        finder_email = request.form.get("finder_email")
        finder_notes = request.form.get("finder_notes")

        # Basic required validation
        if not all([found_location, finder_name, finder_phone, finder_email]):
            flash("Please fill all required contact and location fields.", "danger")
            return redirect(url_for("main.report_found_pet"))

        # Parse date_found
        date_found = None
        if date_found_str:
            try:
                date_found = datetime.strptime(date_found_str, "%Y-%m-%d").date()
            except ValueError:
                pass  # keep None if invalid

        # Handle image upload (optional)
        pet_img_filename = None
        file = request.files.get("pet_img")

        if file and getattr(file, "filename", None):
            filename_raw = secure_filename(file.filename)
            if filename_raw:
                upload_dir = current_app.config["FOUND_PET_UPLOADS"]
                os.makedirs(upload_dir, exist_ok=True)
                save_path = os.path.join(upload_dir, filename_raw)
                file.save(save_path)

                # This is what you store in DB, relative to MEDIA_ROOT
                pet_img_filename = f"found_pets/{filename_raw}"

        # Convert lat/lng to float
        lat_val = float(latitude) if latitude else None
        lng_val = float(longitude) if longitude else None

        report = FoundPetReport(
            pet_type=pet_type,
            found_location=found_location,
            latitude=lat_val,
            longitude=lng_val,
            date_found=date_found,
            pet_condition=pet_condition,
            pet_img=pet_img_filename,  # << field name in model
            finder_name=finder_name,
            finder_phone=finder_phone,
            finder_whatsapp=finder_whatsapp,
            finder_email=finder_email,
            finder_notes=finder_notes,
            status="pending",
        )

        db.session.add(report)
        try:
            db.session.commit()
            flash("Found pet report submitted successfully. Thank you!", "success")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error saving found pet report")
            flash("Error saving your report. Please try again.", "danger")

        return redirect(url_for("main.report_found_pet"))

    return render_template("report_found_pet.html")



# ============================
#  LOST PET REPORT
# ============================

def save_lost_pet_image(field_name: str):
    """Helper: save an uploaded image for lost pet; returns stored path or None."""
    file = request.files.get(field_name)
    if not file or not getattr(file, "filename", None):
        return None

    filename_raw = secure_filename(file.filename)
    if not filename_raw:
        return None

    upload_dir = current_app.config.get(
        "LOST_PET_UPLOADS",
        os.path.join(current_app.root_path, "media", "lost_pets"),
    )
    os.makedirs(upload_dir, exist_ok=True)

    uniq_name = f"{int(time())}_{filename_raw}"
    save_path = os.path.join(upload_dir, uniq_name)
    file.save(save_path)

    return f"lost_pets/{uniq_name}"


@bp.route("/report-lost-pet", methods=["GET", "POST"])
def report_lost_pet():
    if request.method == "POST":
        # ---------- FORM DATA ----------
        pet_name = request.form.get("pet_name")
        pet_type = request.form.get("pet_type")
        description = request.form.get("description")  # marks/colour/etc.

        # From HTML: name="last_seen"
        last_seen_location = request.form.get("last_seen")

        latitude = request.form.get("latitude")
        longitude = request.form.get("longitude")
        date_lost_str = request.form.get("date_lost")

        owner_name = request.form.get("owner_name")
        owner_phone = request.form.get("owner_phone")
        owner_whatsapp = request.form.get("owner_whatsapp")
        owner_email = request.form.get("owner_email")
        owner_address = request.form.get("owner_address")
        reward_info = request.form.get("reward_info")

        # ---------- BASIC VALIDATION ----------
        if not all([pet_name, last_seen_location, owner_name, owner_phone, owner_email]):
            flash("Please fill all required fields for lost pet report.", "danger")
            return redirect(url_for("main.report_lost_pet"))

        # ---------- DATE PARSE ----------
        date_lost = None
        if date_lost_str:
            try:
                date_lost = datetime.strptime(date_lost_str, "%Y-%m-%d").date()
            except ValueError:
                # keep None if invalid
                pass

        # ---------- IMAGE UPLOADS (3 photos) ----------
        upload_dir = current_app.config.get(
            "LOST_PET_UPLOADS",
            os.path.join(current_app.root_path, "media", "lost_pets"),
        )
        os.makedirs(upload_dir, exist_ok=True)

        def save_optional_image(field_name: str) -> str | None:
            """
            Save an optional image file from request.files[field_name].
            Returns a relative path (e.g. 'lost_pets/filename.jpg') or None.
            """
            file = request.files.get(field_name)
            if not file or not getattr(file, "filename", ""):
                return None

            filename_raw = secure_filename(file.filename)
            if not filename_raw:
                return None

            save_path = os.path.join(upload_dir, filename_raw)
            file.save(save_path)

            # What we store in DB – relative to media root
            return f"lost_pets/{filename_raw}"

        pet_img_face = save_optional_image("pet_img_face")
        pet_img_full = save_optional_image("pet_img_full")
        pet_img_marks = save_optional_image("pet_img_marks")

        # ---------- COORDINATES ----------
        lat_val = float(latitude) if latitude else None
        lng_val = float(longitude) if longitude else None

        # ---------- CREATE MODEL INSTANCE ----------
        # Make sure your LostPetReport model has these fields:
        #   pet_name, pet_type, description, last_seen_location,
        #   latitude, longitude, date_lost,
        #   owner_name, owner_phone, owner_whatsapp, owner_email,
        #   owner_address, reward_info,
        #   pet_img_face, pet_img_full, pet_img_marks, status
        report = LostPetReport(
            pet_name=pet_name,
            pet_type=pet_type,
            description=description,
            last_seen_location=last_seen_location,
            latitude=lat_val,
            longitude=lng_val,
            date_lost=date_lost,
            owner_name=owner_name,
            owner_phone=owner_phone,
            owner_whatsapp=owner_whatsapp,
            owner_email=owner_email,
            owner_address=owner_address,
            reward_info=reward_info,
            pet_img_face=pet_img_face,
            pet_img_full=pet_img_full,
            pet_img_marks=pet_img_marks,
            status="pending",
        )

        # ---------- SAVE TO DB ----------
        db.session.add(report)
        try:
            db.session.commit()
            flash("Lost pet report submitted successfully.", "success")
        except Exception:
            db.session.rollback()
            current_app.logger.exception("Error saving lost pet report")
            flash("Error saving your report. Please try again.", "danger")

        return redirect(url_for("main.report_lost_pet"))

    # GET request – just render the form
    return render_template("report_lost_pet.html")

# ============================
#  LOST PET STATUS UPDATE (ADMIN)
# ============================
@bp.route('/admin/lost-pet/<int:report_id>/status', methods=['POST'])
@admin_login_required
def update_lost_pet_status(report_id):
    """
    Admin-only AJAX or form endpoint to set lost-pet report status to 'accepted' or 'rejected'.
    Accepts JSON { status: 'accepted' } or form-encoded status=accepted.
    Returns JSON.
    """
    # Ensure g.admin exists (double-check)
    if not getattr(g, "admin", None):
        abort(403)

    # Accept JSON or form data
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        new_status = (payload.get("status") or "").strip().lower()
    else:
        new_status = (request.form.get("status") or "").strip().lower()

    if new_status not in ("accepted", "rejected"):
        return jsonify({"ok": False, "error": "invalid status"}), 400

    report = LostPetReport.query.get_or_404(report_id)

    # normalize statuses in DB as lowercase (optional); here we set lower-case values
    # If you want to keep titlecase, change below to 'Accepted'/'Rejected'
    current_status = (report.status or "").strip().lower()
    if current_status == new_status:
        return jsonify({"ok": True, "status": current_status})

    try:
        report.status = new_status
        db.session.add(report)
        db.session.commit()
        return jsonify({"ok": True, "status": new_status})
    except SQLAlchemyError:
        current_app.logger.exception("Failed to update lost pet status for id %s", report_id)
        db.session.rollback()
        return jsonify({"ok": False, "error": "db error"}), 500

@bp.route('/admin/found-pet/<int:report_id>/status', methods=['POST'])
@admin_login_required
def update_found_pet_status(report_id):
    if not getattr(g, "admin", None):
        abort(403)

    # JSON or form
    if request.is_json:
        payload = request.get_json(silent=True) or {}
        new_status = (payload.get("status") or "").strip().lower()
    else:
        new_status = (request.form.get("status") or "").strip().lower()

    if new_status not in ("accepted", "rejected"):
        return jsonify({"ok": False, "error": "invalid status"}), 400

    report = FoundPetReport.query.get_or_404(report_id)

    try:
        report.status = new_status
        db.session.commit()
        return jsonify({"ok": True, "status": new_status})
    except Exception:
        db.session.rollback()
        return jsonify({"ok": False, "error": "db error"}), 500
    


@bp.route("/found-reports")
def found_reports():
    # show only accepted/verified found reports if you prefer:
    found_reports = FoundPetReport.query.filter_by(status='accepted') \
                   .order_by(FoundPetReport.created_at.desc()).all()
    return render_template("found_reports.html", found_reports=found_reports)


@bp.route('/lost-reports')
def lost_reports():
    # only show reports that admin accepted
    found_reports = FoundPetReport.query.filter_by(status='accepted').order_by(FoundPetReport.created_at.desc()).all()
    lost_reports = LostPetReport.query.filter_by(status='accepted').order_by(LostPetReport.created_at.desc()).all()
    return render_template("lost_reports.html", found_reports=found_reports, lost_reports=lost_reports)
