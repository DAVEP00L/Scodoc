# -*- mode: python -*-
# -*- coding: utf-8 -*-

import inspect
import logging
import pdb
import time

import psycopg2
import sqlalchemy
from sqlalchemy import func

from flask import current_app
from app import db
from app.auth.models import User, get_super_admin
import app
from app import clear_scodoc_cache
from app import models
from app.models import APO_CODE_STR_LEN, SHORT_STR_LEN, GROUPNAME_STR_LEN
from app.scodoc import notesdb as ndb


def truncate_field(table_name, field, max_len):
    "renvoie une fonction de troncation"

    def troncator(value):
        "Si la chaine est trop longue pour la nouvelle base, émet un warning et tronque"
        if value and len(value) > max_len:
            logging.warning(
                "Chaine trop longue tronquée: %s.%s=%s", table_name, field, value
            )
            return value[:max_len]
        return value

    return troncator


# Attributs dont le nom change entre les bases ScoDoc 7 et 9:
# (None indique que l'attribut est supprimé, "nouveau_nom" qu'il change de nom)
ATTRIBUTES_MAPPING = {
    "admissions": {
        "debouche": None,
    },
    "adresse": {
        "entreprise_id": None,
    },
    "etud_annotations": {
        "zope_authenticated_user": "author",
        "zope_remote_addr": None,
    },
    "identite": {
        "foto": None,
    },
    "notes_formsemestre": {
        "etape_apo2": None,  # => suppressed
        "etape_apo3": None,
        "etape_apo4": None,
        # préférences, plus dans formsemestre:
        # (inutilisés depuis ScoDoc 6 environ)
        "bul_show_decision": None,
        "bul_show_uevalid": None,
        "nomgroupetd": None,
        "nomgroupetp": None,
        "nomgroupeta": None,
        "gestion_absence": None,
        "bul_show_codemodules": None,
        "bul_show_rangs": None,
        "bul_show_ue_rangs": None,
        "bul_show_mod_rangs": None,
    },
    "partition": {
        "compute_ranks": None,
    },
    "notes_appreciations": {
        "zope_authenticated_user": "author",
        "zope_remote_addr": None,
    },
    "scolog": {
        "remote_addr": None,
        "remote_host": None,
    },
}

# Attributs à transformer pour passer de ScoDoc 7 à 9
# la fonction est appliquée au nouvel attribut
ATTRIBUTES_TRANSFORM = {
    "notes_formsemestre": {
        # la modalité CP est devenue CPRO
        "modalite": lambda x: x if x != "CP" else "CPRO",
        "bul_bgcolor": truncate_field(
            "notes_formsemestre", "bul_bgcolor", SHORT_STR_LEN
        ),
    },
    # tronque les codes trop longs pour être honnêtes...
    "notes_formations": {
        "formation_code": truncate_field(
            "notes_formations", "formation_code", SHORT_STR_LEN
        ),
        "code_specialite": truncate_field(
            "notes_formations", "code_specialite", SHORT_STR_LEN
        ),
    },
    "notes_ue": {
        "ue_code": truncate_field("notes_ue", "ue_code", SHORT_STR_LEN),
        "code_apogee": truncate_field("notes_ue", "code_apogee", APO_CODE_STR_LEN),
    },
    "notes_modules": {
        "code_apogee": truncate_field("notes_modules", "code_apogee", APO_CODE_STR_LEN),
    },
    "notes_formsemestre_etapes": {
        "etape_apo": truncate_field(
            "notes_formsemestre_etapes", "etape_apo", APO_CODE_STR_LEN
        ),
    },
    "notes_form_modalites": {
        "modalite": truncate_field("notes_form_modalites", "modalite", SHORT_STR_LEN),
    },
    "notes_formsemestre_inscription": {
        "etape": truncate_field(
            "notes_formsemestre_inscription", "etape", APO_CODE_STR_LEN
        ),
    },
    "partition": {
        "partition_name": truncate_field("partition", "partition_name", SHORT_STR_LEN),
    },
    "group_descr": {
        "group_name": truncate_field("group_descr", "group_name", GROUPNAME_STR_LEN),
    },
    "scolar_autorisation_inscription": {
        "formation_code": truncate_field(
            "scolar_autorisation_inscription", "formation_code", SHORT_STR_LEN
        ),
    },
}


def setup_log(dept_acronym: str):
    """log to console (stderr) and /opt/scodoc-data/log/migration79.log"""
    log_formatter = logging.Formatter(
        "%(asctime)s %(levelname)s (" + dept_acronym + ")  %(message)s"
    )
    # Log to file:
    logger = logging.getLogger()
    file_handler = logging.FileHandler("/opt/scodoc-data/log/migration79.log")
    file_handler.setFormatter(log_formatter)
    logger.addHandler(file_handler)
    # Log to stderr:
    console_handler = logging.StreamHandler()  # stderr
    console_handler.setFormatter(log_formatter)
    logger.addHandler(console_handler)
    # Caution:
    logger.setLevel(logging.DEBUG)


def import_scodoc7_dept(dept_id: str, dept_db_uri=None):
    """Importe un département ScoDoc7 dans ScoDoc >= 8.1
    (base de donnée unique)

    Args:
        dept_id: acronyme du département ("RT")
        dept_db_uri: URI de la base ScoDoc7eg "postgresql:///SCORT"
        si None, utilise postgresql:///SCO{dept_id}
    """
    dept = models.Departement.query.filter_by(acronym=dept_id).first()
    if dept:
        raise ValueError(f"le département {dept_id} existe déjà !")
    if dept_db_uri is None:
        dept_db_uri = f"postgresql:///SCO{dept_id}"
    setup_log(dept_id)
    logging.info(f"connecting to database {dept_db_uri}")
    cnx = psycopg2.connect(dept_db_uri)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    # Create dept:
    dept = models.Departement(acronym=dept_id, description="migré de ScoDoc7")
    db.session.add(dept)
    db.session.commit()
    #
    id_from_scodoc7 = {}  # { scodoc7id (str) : scodoc8 id (int)}
    # Utilisateur de rattachement par défaut:
    default_user = get_super_admin()
    #
    t0 = time.time()
    for (table, id_name) in SCO7_TABLES_ORDONNEES:
        logging.info(f"{dept.acronym}: converting {table}...")
        klass = get_class_for_table(table)
        t1 = time.time()
        n = convert_table(dept, cursor, id_from_scodoc7, klass, id_name, default_user)
        logging.info(f"     inserted {n} objects in {time.time()-t1:3.2f}s.")

    logging.info(f"All table imported in {time.time()-t0:3.2f}s")
    logging.info(f"clearing app caches...")
    clear_scodoc_cache()
    logging.info(f"Done.")
    logging.warning(f"Un redémarrage du serveur postgresql est conseillé.")


def get_class_for_table(table):
    """Return ScoDoc orm class for the given SQL table: search in our models"""
    for name in dir(models):
        item = getattr(models, name)
        if inspect.isclass(item):
            if issubclass(item, db.Model):
                if item.__tablename__ == table:
                    return item
        try:  # pour les db.Table qui ne sont pas des classes (isclass est faux !)
            if item.name == table:
                return item
        except:
            pass
    raise ValueError(f"No model for table {table}")


def get_boolean_columns(klass):
    "return list of names of boolean attributes in this (ScoDoc 9) model"
    boolean_columns = []
    column_names = sqlalchemy.inspect(klass).columns.keys()
    for column_name in column_names:
        column = getattr(klass, column_name)
        if isinstance(column.expression.type, sqlalchemy.sql.sqltypes.Boolean):
            boolean_columns.append(column_name)
    return boolean_columns


def get_table_max_id(klass):
    "return max id in this Table (or -1 if no id)"
    if not id in sqlalchemy.inspect(klass).columns.keys():
        return -1
    sql_table = str(klass.description)
    cnx = db.engine.connect()
    r = cnx.execute("SELECT max(id) FROM " + sql_table)
    r.fetchone()
    if r:
        return r[0]
    else:  # empty table
        return 0


def update_table_sequence(table_name):
    """After filling the table, we need to update the serial
    so that the next insertions will use new ids
    """
    with db.engine.connect() as cnx:
        cnx.execute(
            f"""SELECT 
        setval('{table_name}_id_seq', 
            (SELECT MAX(id) FROM {table_name}))
        """
        )


def convert_table(
    dept, cursor, id_from_scodoc7: dict, klass=None, id_name=None, default_user=None
):
    "converti les élements d'une table scodoc7"
    # Est-ce une Table ou un Model dans l'ORM ?
    if isinstance(klass, sqlalchemy.sql.schema.Table):
        is_table = True
        current_id = get_table_max_id(klass)
        has_id = current_id != -1
        table_name = str(klass.description)
        boolean_columns = []
    else:
        is_table = False
        has_id = True
        table_name = klass.__tablename__
        # Colonnes booléennes (valeurs à convertir depuis int)
        boolean_columns = get_boolean_columns(klass)
        # Part de l'id le plus haut actuellement présent
        # (évidemment, nous sommes les seuls connectés à la base destination !)
        current_id = db.session.query(func.max(klass.id)).first()
        if (current_id is None) or (current_id[0] is None):
            current_id = 0
        else:
            current_id = current_id[0]
    cnx = db.engine.connect()
    # mapping: login (scodoc7) : user id (scodoc8)
    login2id = {u.user_name: u.id for u in User.query}

    # les tables ont le même nom dans les deux versions de ScoDoc:
    cursor.execute(f"SELECT * FROM {table_name}")
    objects = cursor.dictfetchall()

    n = 0
    for obj in objects:
        current_id += 1
        convert_object(
            current_id,
            dept,
            obj,
            has_id,
            id_from_scodoc7,
            klass,
            is_table,
            id_name,
            boolean_columns,
            login2id,
            default_user,
            cnx,
        )
        # commit progressif pour ne pas consommer trop de mémoire:
        n += 1
        if (not n % 1000) and cnx:
            db.session.commit()

    if cnx:
        cnx.close()

    db.session.commit()  # écrit la table
    if has_id:
        update_table_sequence(table_name)
    return len(objects)


def convert_object(
    new_id,
    dept,
    obj: dict,
    has_id: bool = True,
    id_from_scodoc7: dict = None,
    klass=None,
    is_table: bool = False,
    id_name=None,
    boolean_columns=None,
    login2id=None,
    default_user=None,
    cnx=None,  # cnx à la base destination
):
    # Supprime l'id ScoDoc7 (eg "formsemestre_id") qui deviendra "id"
    if id_name:
        old_id = obj[id_name]
        del obj[id_name]
        if hasattr(klass, "scodoc7_id"):
            obj["scodoc7_id"] = old_id
    else:
        old_id = None  # tables ScoDoc7 sans id
    if is_table:
        table_name = str(klass.description)
    else:
        table_name = klass.__tablename__
    # Les champs contant des id utilisateurs:
    # chaine login en ScoDoc7, uid numérique en ScoDoc 8+
    USER_REFS = {"responsable_id", "ens_id", "uid"}
    if not is_table:
        # Supprime les attributs obsoletes (très anciennes versions de ScoDoc):
        attributs = ATTRIBUTES_MAPPING.get(table_name, {})
        # renomme ou supprime les attributs
        for k in attributs.keys() & obj.keys():
            v = attributs[k]
            if v is not None:
                obj[v] = obj[k]
            del obj[k]
        # transforme les valeurs: obj[k] = transform(obj[k])
        for k in ATTRIBUTES_TRANSFORM.get(table_name, {}):
            obj[k] = ATTRIBUTES_TRANSFORM[table_name][k](obj[k])
    # map les ids (foreign keys)
    for k in obj:
        if (k.endswith("id") or k == "object") and k not in USER_REFS | {
            "semestre_id",
            "sem_id",
            "scodoc7_id",
        }:
            old_ref = obj[k]
            if old_ref is not None:
                if isinstance(old_ref, str):
                    old_ref = old_ref.strip()
                elif k == "entreprise_id":  # id numérique spécial
                    old_ref = f"entreprises.{old_ref}"
                elif k == "entreprise_corresp_id":
                    old_ref = f"entreprise_correspondant.{old_ref}"

                if old_ref == "NULL" or not old_ref:  # buggy old entries
                    new_ref = None
                elif old_ref in id_from_scodoc7:
                    new_ref = id_from_scodoc7[old_ref]
                elif (not is_table) and table_name in {
                    "scolog",
                    "etud_annotations",
                    "notes_notes_log",
                    "scolar_news",
                    "absences",
                    "absences_notifications",
                    "itemsuivi",  # etudid n'était pas une clé
                    "adresse",  # etudid n'était pas une clé
                    "admissions",  # idem
                    "scolar_events",
                }:
                    # tables avec "fausses" clés
                    # (l'object référencé a pu disparaitre)
                    new_ref = None
                elif is_table and table_name in {
                    "notes_semset_formsemestre",
                }:
                    # pour anciennes installs où des relations n'avait pas été déclarées clés étrangères
                    # eg: notes_semset_formsemestre.semset_id n'était pas une clé
                    # Dans ce cas, mieux vaut supprimer la relation si l'un des objets n'existe pas
                    return
                else:
                    raise ValueError(f"no new id for {table_name}.{k}='{obj[k]}' !")
                obj[k] = new_ref
    # Remape les utilisateur: user.id
    # S'il n'existe pas, rattache à l'admin
    for k in USER_REFS & obj.keys():
        login_scodoc7 = obj[k]
        uid = login2id.get(login_scodoc7)
        if not uid:
            uid = default_user.id
            warning_user_dont_exist(
                login_scodoc7,
                f"non existent user: {login_scodoc7}: giving {table_name}({old_id}) to admin",
            )
            # raise ValueError(f"non existent user: {login_scodoc7}")
        obj[k] = uid
    # Converti les booléens
    for k in boolean_columns:
        if k in obj:
            obj[k] = bool(obj[k])

    # Ajoute le département si besoin:
    if hasattr(klass, "dept_id"):
        obj["dept_id"] = dept.id

    # Fixe l'id (ainsi nous évitons d'avoir à commit() après chaque entrée)
    if has_id:
        obj["id"] = new_id

    if is_table:
        statement = sqlalchemy.insert(klass).values(**obj)
        _ = cnx.execute(statement)
    else:
        new_obj = klass(**obj)  # ORM object
        db.session.add(new_obj)
        # insert_object(cnx, table_name, obj)

    # Stocke l'id pour les références (foreign keys):
    if id_name and has_id:
        if isinstance(old_id, int):
            # les id int étaient utilisés pour les "entreprises"
            old_id = table_name + "." + str(old_id)
        id_from_scodoc7[old_id] = new_id


MISSING_USERS = set()  # login ScoDoc7 référencés mais non existants...


def warning_user_dont_exist(login_scodoc7, msg):
    if login_scodoc7 not in MISSING_USERS:
        return
    MISSING_USERS.add(login_scodoc7)
    logging.warning(msg)


def insert_object(cnx, table_name: str, vals: dict) -> str:
    """insert tuple in db
    version manuelle => ne semble pas plus rapide
    """
    cols = list(vals.keys())
    colnames = ",".join(cols)
    fmt = ",".join(["%%(%s)s" % col for col in cols])
    cnx.execute("insert into %s (%s) values (%s)" % (table_name, colnames, fmt), vals)


# tables ordonnées topologiquement pour les clés étrangères:
# g = nx.read_adjlist("misc/model-scodoc7.csv", create_using=nx.DiGraph,delimiter=";")
# L = list(reversed(list(nx.topological_sort(g))))
SCO7_TABLES_ORDONNEES = [
    # (table SQL, nom de l'id scodoc7)
    ("notes_formations", "formation_id"),
    ("notes_ue", "ue_id"),
    ("notes_matieres", "matiere_id"),
    ("notes_formsemestre", "formsemestre_id"),
    ("notes_modules", "module_id"),
    ("notes_moduleimpl", "moduleimpl_id"),
    (
        "notes_modules_enseignants",
        "modules_enseignants_id",
    ),  # (relation) avait un id modules_enseignants_id
    ("partition", "partition_id"),
    ("identite", "etudid"),
    ("entreprises", "entreprise_id"),
    ("notes_evaluation", "evaluation_id"),
    ("group_descr", "group_id"),
    ("group_membership", "group_membership_id"),  # (relation, qui avait un id)
    ("notes_semset", "semset_id"),
    ("notes_tags", "tag_id"),
    ("itemsuivi", "itemsuivi_id"),
    ("itemsuivi_tags", "tag_id"),
    ("adresse", "adresse_id"),
    ("admissions", "adm_id"),
    ("absences", ""),
    ("scolar_news", "news_id"),
    ("scolog", ""),
    ("etud_annotations", "id"),
    ("billet_absence", "billet_id"),
    ("entreprise_correspondant", "entreprise_corresp_id"),
    ("entreprise_contact", "entreprise_contact_id"),
    ("absences_notifications", ""),
    # ("notes_form_modalites", "form_modalite_id"), : déjà initialisées
    ("notes_appreciations", "id"),
    ("scolar_autorisation_inscription", "autorisation_inscription_id"),
    ("scolar_formsemestre_validation", "formsemestre_validation_id"),
    ("scolar_events", "event_id"),
    ("notes_notes_log", "id"),
    ("notes_notes", ""),
    ("notes_moduleimpl_inscription", "moduleimpl_inscription_id"),
    ("notes_formsemestre_inscription", "formsemestre_inscription_id"),
    ("notes_formsemestre_custommenu", "custommenu_id"),
    (
        "notes_formsemestre_ue_computation_expr",
        "notes_formsemestre_ue_computation_expr_id",
    ),
    ("notes_formsemestre_uecoef", "formsemestre_uecoef_id"),
    ("notes_semset_formsemestre", ""),  # (relation)
    ("notes_formsemestre_etapes", ""),
    ("notes_formsemestre_responsables", ""),  # (relation)
    ("notes_modules_tags", ""),
    ("itemsuivi_tags_assoc", ""),  # (relation)
    ("sco_prefs", "pref_id"),
]

"""
from tools.import_scodoc7_dept import *
import_scodoc7_dept( "RT", "SCORT" )
"""
