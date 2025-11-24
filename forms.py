# forms.py
from flask_wtf import FlaskForm
from wtforms import (
    StringField,
    TextAreaField,
    PasswordField,
    IntegerField,
    SelectField,
    BooleanField,
    SubmitField,
)
from wtforms.validators import (
    DataRequired,
    Email,
    Length,
    Optional,
    EqualTo,
    NumberRange,
)
from flask_wtf.file import FileField, FileAllowed

from models import GenderEnum

ALLOWED_IMAGE_EXT = ["jpg", "jpeg", "png", "gif"]


class RegisterForm(FlaskForm):
    user_name = StringField(
        "Username",
        validators=[DataRequired(), Length(min=2, max=100)],
    )
    user_bio = TextAreaField(
        "Bio",
        validators=[Optional(), Length(max=500)],
    )
    phone_number = StringField(
        "Phone Number",
        validators=[Optional(), Length(max=20)],
    )
    city = StringField("City", validators=[Optional(), Length(max=100)])
    state = StringField("State", validators=[Optional(), Length(max=100)])
    country = StringField("Country", validators=[Optional(), Length(max=100)])
    address = StringField("Address", validators=[Optional(), Length(max=255)])

    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=150)],
    )

    password = PasswordField(
        "Password",
        validators=[DataRequired(), Length(min=6)],
    )
    confirm_password = PasswordField(
        "Confirm Password",
        validators=[
            DataRequired(),
            EqualTo("password", message="Passwords must match"),
        ],
    )

    # ✅ This matches register.html and edit_user.html
    user_img = FileField(
        "Profile Image",
        validators=[Optional(), FileAllowed(ALLOWED_IMAGE_EXT)],
    )

    submit = SubmitField("Register")


class LoginForm(FlaskForm):
    # EMAIL-BASED LOGIN
    email = StringField(
        "Email",
        validators=[DataRequired(), Email(), Length(max=150)],
    )
    password = PasswordField(
        "Password",
        validators=[DataRequired()],
    )
    remember = BooleanField("Remember me")
    submit = SubmitField("Login")


class PetForm(FlaskForm):
    pet_name = StringField(
        "Pet Name",
        validators=[DataRequired(), Length(min=1, max=100)],
    )
    pet_owner_id = IntegerField(
        "Owner ID",
        validators=[DataRequired(), NumberRange(min=1)],
    )

    pet_age = IntegerField(
        "Pet Age",
        validators=[Optional(), NumberRange(min=0)],
    )
    pet_licence_id = StringField(
        "Licence ID",
        validators=[Optional(), Length(max=100)],
    )
    pet_type = StringField(
        "Pet Type",
        validators=[Optional(), Length(max=50)],
    )
    pet_colour = StringField(
        "Colour",
        validators=[Optional(), Length(max=50)],
    )

    pet_male_female = SelectField(
        "Gender",
        choices=[
            (GenderEnum.male.value, "Male"),
            (GenderEnum.female.value, "Female"),
        ],
        validators=[DataRequired()],
    )

    pet_img = FileField(
        "Pet Image",
        validators=[Optional(), FileAllowed(ALLOWED_IMAGE_EXT)],
    )

    submit = SubmitField("Save")
