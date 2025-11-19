from flask_wtf import FlaskForm
from flask_wtf.file import FileField, FileAllowed

from wtforms import (
    StringField, TextAreaField, FileField, IntegerField,
    PasswordField, SubmitField, SelectField
)

from wtforms.validators import (
    DataRequired, Optional, Length, NumberRange
)

# Allowed image types
ALLOWED_IMAGES = {"jpg", "jpeg", "png", "gif"}
from wtforms import BooleanField
from wtforms.validators import InputRequired

class LoginForm(FlaskForm):
    user_name = StringField("Username", validators=[DataRequired(), Length(max=100)])
    password = PasswordField("Password", validators=[DataRequired()])
    remember = BooleanField("Remember me")   # optional — we will implement simple session-based "remember"
    submit = SubmitField("Login")

# -------------------------------
# User Registration Form
# -------------------------------
class RegisterForm(FlaskForm):
    user_name = StringField("Name", validators=[DataRequired(), Length(max=100)])
    user_img = FileField("Photo", validators=[
        Optional(),
        FileAllowed(list(ALLOWED_IMAGES), "Only images allowed (jpg, png, gif).")
    ])
    user_bio = TextAreaField("Bio", validators=[Optional()])
    password = PasswordField("Password", validators=[DataRequired()])
    phone_number = StringField("Phone", validators=[Optional(), Length(max=20)])
    city = StringField("City", validators=[Optional()])
    state = StringField("State", validators=[Optional()])
    country = StringField("Country", validators=[Optional()])
    address = StringField("Address", validators=[Optional()])
   
    
    submit = SubmitField("Register")


# -------------------------------
# Pet Form
# -------------------------------
class PetForm(FlaskForm):
    pet_name = StringField("Pet Name", validators=[DataRequired(), Length(max=100)])
    pet_owner_id = IntegerField("Owner ID", validators=[DataRequired(), NumberRange(min=1)])

    pet_img = FileField("Pet Image", validators=[
        Optional(),
        FileAllowed(list(ALLOWED_IMAGES), "Only images allowed (jpg, png, gif).")
    ])

    pet_age = IntegerField("Age", validators=[Optional(), NumberRange(min=0)])
    pet_licence_id = StringField("Licence ID", validators=[Optional(), Length(max=100)])
    pet_type = StringField("Type", validators=[Optional(), Length(max=50)])
    pet_colour = StringField("Colour", validators=[Optional(), Length(max=50)])

    pet_male_female = SelectField(
        "Gender",
        choices=[("male", "Male"), ("female", "Female")],
        validators=[DataRequired()]
    )

    submit = SubmitField("Save Pet")
