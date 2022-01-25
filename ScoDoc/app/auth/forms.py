# -*- coding: UTF-8 -*

"""Formulaires authentification

TODO: à revoir complètement pour reprendre ZScoUsers et les pages d'authentification
"""

from flask_wtf import FlaskForm
from wtforms import StringField, PasswordField, BooleanField, SubmitField
from wtforms.validators import ValidationError, DataRequired, Email, EqualTo
from app.auth.models import User, is_valid_password


_ = lambda x: x  # sans babel
_l = _


class LoginForm(FlaskForm):
    user_name = StringField(_l("Nom d'utilisateur"), validators=[DataRequired()])
    password = PasswordField(_l("Mot de passe"), validators=[DataRequired()])
    remember_me = BooleanField(_l("mémoriser la connexion"))
    submit = SubmitField(_l("Suivant"))


class UserCreationForm(FlaskForm):
    user_name = StringField(_l("Nom d'utilisateur"), validators=[DataRequired()])
    email = StringField(_l("Email"), validators=[DataRequired(), Email()])
    password = PasswordField(_l("Mot de passe"), validators=[DataRequired()])
    password2 = PasswordField(
        _l("Répéter"), validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField(_l("Inscrire"))

    def validate_user_name(self, user_name):
        user = User.query.filter_by(user_name=user_name.data).first()
        if user is not None:
            raise ValidationError(_("Please use a different user_name."))

    def validate_email(self, email):
        user = User.query.filter_by(email=email.data).first()
        if user is not None:
            raise ValidationError(_("Please use a different email address."))


class ResetPasswordRequestForm(FlaskForm):
    email = StringField(
        _l("Adresse email associée à votre compte ScoDoc:"),
        validators=[DataRequired(), Email()],
    )
    submit = SubmitField(_l("Envoyer"))


class ResetPasswordForm(FlaskForm):
    password = PasswordField(_l("Mot de passe"), validators=[DataRequired()])
    password2 = PasswordField(
        _l("Répéter"), validators=[DataRequired(), EqualTo("password")]
    )
    submit = SubmitField(_l("Valider ce mot de passe"))

    def validate_password(self, password):
        if not is_valid_password(password.data):
            raise ValidationError(f"Mot de passe trop simple, recommencez")


class DeactivateUserForm(FlaskForm):
    submit = SubmitField("Modifier l'utilisateur")
    cancel = SubmitField(label="Annuler", render_kw={"formnovalidate": True})
