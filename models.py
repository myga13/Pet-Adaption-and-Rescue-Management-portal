from extensions import db
from datetime import datetime
from sqlalchemy import Enum as SAEnum
import enum



from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from extensions import db
# models.py

from extensions import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime
class AdoptionList(db.Model):
    __tablename__ = "adoption_list"   # must match your MySQL table name

    id = db.Column(db.Integer, primary_key=True)

    # ⚠️ This MUST be a ForeignKey to PetDetails
    pet_id = db.Column(
        db.Integer,
        db.ForeignKey("pets_details.pet_id"),  # <-- match PetDetails.__tablename__
        nullable=False,
        unique=True
    )

    status = db.Column(
        db.String(20),          # or db.Enum("pending", "completed", name="adoption_status")
        nullable=False,
        default="pending"
    )

    created_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow
    )

    updated_at = db.Column(
        db.DateTime,
        nullable=False,
        default=datetime.utcnow,
        onupdate=datetime.utcnow
    )

    # ORM relationship to PetDetails
    pet = db.relationship(
        "PetDetails",
        backref=db.backref("adoption_entry", uselist=False)
    )
    status = db.Column(db.String(20), default="pending")


class PetAdoptionRequest(db.Model):
    __tablename__ = "pet_adoption_requests"

    request_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pet_id = db.Column(db.Integer, nullable=False)          # or db.ForeignKey('pets_details.pet_id')
    requester_id = db.Column(db.Integer, nullable=False)    # user id (from g.user.user_id)
    request_status = db.Column(db.String(20), default='pending', nullable=False)
    requested_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

class Admin(db.Model):
    __tablename__ = "admins"

    id = db.Column(db.Integer, primary_key=True)

    # PERSONAL
    full_name = db.Column(db.String(120), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    phone = db.Column(db.String(20), nullable=False)
    address = db.Column(db.Text, nullable=False)
    city = db.Column(db.String(80), nullable=False)
    state = db.Column(db.String(80), nullable=False)
    current_location = db.Column(db.String(255))

    profile_image = db.Column(db.String(255))

    # ROLE / EXPERIENCE
    admin_role = db.Column(db.String(80), nullable=False)
    experience_years = db.Column(db.Integer)
    past_experience = db.Column(db.Text)

    # NGO
    ngo_name = db.Column(db.String(120))
    ngo_designation = db.Column(db.String(120))
    ngo_years = db.Column(db.Integer)

    # ID PROOF
    id_proof_type = db.Column(db.String(50), nullable=False)
    id_proof_number = db.Column(db.String(80), nullable=False)
    id_proof_file = db.Column(db.String(255))

    # EMERGENCY
    emergency_name = db.Column(db.String(120))
    emergency_relation = db.Column(db.String(80))
    emergency_phone = db.Column(db.String(20))
    emergency_phone_alt = db.Column(db.String(20))

    # SOCIAL
    linkedin = db.Column(db.String(255))
    instagram = db.Column(db.String(255))

    # AUTH
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # SIMPLE STATUS (optional)
    is_active = db.Column(db.Boolean, default=True)

    # ---- helpers ----
    def set_password(self, password: str):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)

# ----------------------------
# Enums
# ----------------------------
class GenderEnum(enum.Enum):
    male = "male"
    female = "female"

# ----------------------------
# UserDetails (single user model)
# ----------------------------
class UserDetails(db.Model):
    __tablename__ = "webapp_userdetails"

    user_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    user_name = db.Column(db.String(100), nullable=False)
    user_img = db.Column(db.String(255), nullable=True)
    user_bio = db.Column(db.Text, nullable=True)
    password = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), nullable=True)
    city = db.Column(db.String(100), nullable=True)
    state = db.Column(db.String(100), nullable=True)
    country = db.Column(db.String(100), nullable=True)
    address = db.Column(db.String(255), nullable=True)
    email = db.Column(db.String(150), unique=True, nullable=False)
    pincode = db.Column(db.String(10), nullable=True) 

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    pets = db.relationship(
        "PetDetails",
        back_populates="owner",
        cascade="all, delete-orphan",
        lazy="select",
    )

    def __repr__(self):
        return f"<UserDetails {self.user_id} {self.user_name}>"

# ----------------------------
# PetDetails
# ----------------------------
class PetDetails(db.Model):
    __tablename__ = "pets_details"

    pet_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    pet_name = db.Column(db.String(100), nullable=False)

    pet_owner_id = db.Column(
        db.Integer,
        db.ForeignKey("webapp_userdetails.user_id", ondelete="CASCADE"),
        nullable=False,
    )

    pet_img = db.Column(db.String(255), nullable=True)
    pet_age = db.Column(db.String(10), nullable=True)
    pet_licence_id = db.Column(db.String(100), nullable=True)
    pet_type = db.Column(db.String(50), nullable=True)
    pet_breed = db.Column(db.String(50), nullable=True)
    pet_colour = db.Column(db.String(50), nullable=True)
    pet_male_female = db.Column(SAEnum(GenderEnum), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = db.relationship("UserDetails", back_populates="pets", lazy="joined")

    def __repr__(self):
        return f"<PetDetails {self.pet_id} {self.pet_name}>"
    
# ----------------------------
# ContactMessage
# ----------------------------

class ContactMessage(db.Model):
    __tablename__ = "contact_messages"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    email = db.Column(db.String(120), nullable=False)
    phone = db.Column(db.String(30))  # optional
    subject = db.Column(db.String(200), nullable=False)
    message = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    status = db.Column(db.String(20), default="new", nullable=False)

# ----------------------------
# FoundPetReport
# ----------------------------

class FoundPetReport(db.Model):
    __tablename__ = "found_pet_reports"

    id = db.Column(db.Integer, primary_key=True)

    # Pet info
    pet_type = db.Column(db.String(50), nullable=True)
    found_location = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    date_found = db.Column(db.Date, nullable=True)

    pet_condition = db.Column(db.Text, nullable=True)  # renamed from "condition"

    pet_img = db.Column(db.String(255), nullable=True)

    # Finder details
    finder_name = db.Column(db.String(120), nullable=False)
    finder_phone = db.Column(db.String(30), nullable=False)
    finder_whatsapp = db.Column(db.String(30), nullable=True)
    finder_email = db.Column(db.String(120), nullable=False)
    finder_notes = db.Column(db.Text, nullable=True)
    
    status = db.Column(db.String(20), nullable=False, default="pending")
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)


# ----------------------------
# FoundPetReport
# ----------------------------
class LostPetReport(db.Model):
    __tablename__ = "lost_pet_reports"

    id = db.Column(db.Integer, primary_key=True)

    pet_name = db.Column(db.String(120), nullable=False)
    pet_type = db.Column(db.String(50))
    description = db.Column(db.Text)

    last_seen_location = db.Column(db.String(255), nullable=False)
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)
    date_lost = db.Column(db.Date)

    owner_name = db.Column(db.String(120), nullable=False)
    owner_phone = db.Column(db.String(50), nullable=False)
    owner_whatsapp = db.Column(db.String(50))
    owner_email = db.Column(db.String(120), nullable=False)
    owner_address = db.Column(db.String(255))
    reward_info = db.Column(db.String(255))

    pet_img_face = db.Column(db.String(255))
    pet_img_full = db.Column(db.String(255))
    pet_img_marks = db.Column(db.String(255))

    status = db.Column(db.String(50), default="pending", nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

from datetime import datetime
from extensions import db


class ChatRoom(db.Model):
    __tablename__ = "chat_rooms"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    is_private = db.Column(db.Boolean, default=False)
    created_by = db.Column(db.Integer, db.ForeignKey("admin.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


class ChatRoomMember(db.Model):
    __tablename__ = "chat_room_members"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("chat_rooms.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("user_details.user_id"), nullable=False)


class ChatMessage(db.Model):
    __tablename__ = "chat_messages"

    id = db.Column(db.Integer, primary_key=True)
    room_id = db.Column(db.Integer, db.ForeignKey("chat_rooms.id"), nullable=False)
    sender_id = db.Column(db.Integer, db.ForeignKey("user_details.user_id"), nullable=False)
    content = db.Column(db.Text, nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)


from datetime import datetime
from extensions import db

class PetRequest(db.Model):
    __tablename__ = 'pet_requests'

    id = db.Column(db.Integer, primary_key=True)

    report_id = db.Column(
        db.Integer,
        db.ForeignKey('found_pet_reports.id'),
        nullable=False
    )

    user_id = db.Column(db.Integer, nullable=False)
    user_name = db.Column(db.String(120))
    user_email = db.Column(db.String(120))

    message = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    status = db.Column(db.String(20), default='pending')

    # ✅ relationship
    report = db.relationship('FoundPetReport', backref='requests')

from datetime import datetime
from extensions import db

class Notification(db.Model):
    __tablename__ = "notifications"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(db.Integer, nullable=False)
    title = db.Column(db.String(120), nullable=False)
    message = db.Column(db.Text, nullable=False)

    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
