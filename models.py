from extensions import db
from datetime import datetime
from sqlalchemy import Enum as SAEnum
import enum

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
    pet_age = db.Column(db.Integer, nullable=True)
    pet_licence_id = db.Column(db.String(100), nullable=True)
    pet_type = db.Column(db.String(50), nullable=True)
    pet_colour = db.Column(db.String(50), nullable=True)
    pet_male_female = db.Column(SAEnum(GenderEnum), nullable=False)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    owner = db.relationship("UserDetails", back_populates="pets", lazy="joined")

    def __repr__(self):
        return f"<PetDetails {self.pet_id} {self.pet_name}>"
