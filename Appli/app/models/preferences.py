# -*- coding: UTF-8 -*

"""Model : preferences
"""
from app import db, log
from app.scodoc import bonus_sport
from app.scodoc.sco_exceptions import ScoValueError


class ScoPreference(db.Model):
    """ScoDoc preferences (par département)"""

    __tablename__ = "sco_prefs"
    id = db.Column(db.Integer, primary_key=True)
    pref_id = db.synonym("id")

    dept_id = db.Column(db.Integer, db.ForeignKey("departement.id"))

    name = db.Column(db.String(128), nullable=False, index=True)
    value = db.Column(db.Text())
    formsemestre_id = db.Column(db.Integer, db.ForeignKey("notes_formsemestre.id"))


class ScoDocSiteConfig(db.Model):
    """Config. d'un site
    Nouveau en ScoDoc 9: va regrouper les paramètres qui dans les versions
    antérieures étaient dans scodoc_config.py
    """

    __tablename__ = "scodoc_site_config"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False, index=True)
    value = db.Column(db.Text())

    BONUS_SPORT = "bonus_sport_func_name"
    NAMES = {
        BONUS_SPORT: str,
        "always_require_ine": bool,
        "SCOLAR_FONT": str,
        "SCOLAR_FONT_SIZE": str,
        "SCOLAR_FONT_SIZE_FOOT": str,
        "INSTITUTION_NAME": str,
        "INSTITUTION_ADDRESS": str,
        "INSTITUTION_CITY": str,
        "DEFAULT_PDF_FOOTER_TEMPLATE": str,
    }

    def __init__(self, name, value):
        self.name = name
        self.value = value

    def __repr__(self):
        return f"<{self.__class__.__name__}('{self.name}', '{self.value}')>"

    def get_dict(self) -> dict:
        "Returns all data as a dict name = value"
        return {
            c.name: self.NAMES.get(c.name, lambda x: x)(c.value)
            for c in ScoDocSiteConfig.query.all()
        }

    @classmethod
    def set_bonus_sport_func(cls, func_name):
        """Record bonus_sport config.
        If func_name not defined, raise NameError
        """
        if func_name not in cls.get_bonus_sport_func_names():
            raise NameError("invalid function name for bonus_sport")
        c = ScoDocSiteConfig.query.filter_by(name=cls.BONUS_SPORT).first()
        if c:
            log("setting to " + func_name)
            c.value = func_name
        else:
            c = ScoDocSiteConfig(cls.BONUS_SPORT, func_name)
        db.session.add(c)
        db.session.commit()

    @classmethod
    def get_bonus_sport_func_name(cls):
        """Get configured bonus function name, or None if None."""
        f = cls.get_bonus_sport_func_from_name()
        if f is None:
            return ""
        else:
            return f.__name__

    @classmethod
    def get_bonus_sport_func(cls):
        """Get configured bonus function, or None if None."""
        return cls.get_bonus_sport_func_from_name()

    @classmethod
    def get_bonus_sport_func_from_name(cls, func_name=None):
        """returns bonus func with specified name.
        If name not specified, return the configured function.
        None if no bonus function configured.
        Raises ScoValueError if func_name not found in module bonus_sport.
        """
        if func_name is None:
            c = ScoDocSiteConfig.query.filter_by(name=cls.BONUS_SPORT).first()
            if c is None:
                return None
            func_name = c.value
        if func_name == "":  # pas de bonus défini
            return None
        try:
            return getattr(bonus_sport, func_name)
        except AttributeError:
            raise ScoValueError(
                f"""Fonction de calcul maison inexistante: {func_name}. 
                (contacter votre administrateur local)."""
            )

    @classmethod
    def get_bonus_sport_func_names(cls):
        """List available functions names
        (starting with empty string to represent "no bonus function").
        """
        return [""] + sorted(
            [
                getattr(bonus_sport, name).__name__
                for name in dir(bonus_sport)
                if name.startswith("bonus_")
            ]
        )
