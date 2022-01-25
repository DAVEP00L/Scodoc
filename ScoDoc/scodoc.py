# -*- coding: UTF-8 -*


"""Application Flask: ScoDoc


"""

from pprint import pprint as pp
import re
import sys

import click
import flask
from flask.cli import with_appcontext
from flask.templating import render_template

from app import create_app, cli, db
from app import initialize_scodoc_database
from app import clear_scodoc_cache
from app import models

from app.auth.models import User, Role, UserRole
from app.models import ScoPreference
from app.scodoc.sco_permissions import Permission
from app.views import notes, scolar, absences
import tools

from config import RunningConfig

app = create_app(RunningConfig)
cli.register(app)


@app.shell_context_processor
def make_shell_context():
    from app.scodoc import notesdb as ndb
    from app.scodoc import sco_utils as scu
    from flask_login import login_user, logout_user, current_user
    import app as mapp  # le package app

    return {
        "db": db,
        "User": User,
        "Role": Role,
        "UserRole": UserRole,
        "Permission": Permission,
        "notes": notes,
        "scolar": scolar,
        "ndb": ndb,
        "scu": scu,
        "pp": pp,
        "flask": flask,
        "current_app": flask.current_app,
        "current_user": current_user,
        "login_user": login_user,
        "logout_user": logout_user,
        "ctx": app.test_request_context(),
        "models": models,
        "mapp": mapp,
    }


# ctx.push()
# login_user(admin)


@app.cli.command()
@click.option("--erase/--no-erase", default=False)
def sco_db_init(erase=False):  # sco-db-init
    """Initialize the database.
    Starts from an existing database and create all
    the necessary SQL tables and functions.
    """
    if not app.config.get("SCODOC_ADMIN_MAIL"):
        sys.stderr.write(
            """La variable SCODOC_ADMIN_MAIL n'est pas positionnée: vérifier votre .env"""
        )
        return 100
    initialize_scodoc_database(erase=erase)


@app.cli.command()
def user_db_clear():
    """Erase all users and roles from the database !"""
    click.echo("Erasing the users database !")
    _clear_users_db()


def _clear_users_db():
    """Erase (drop) all tables of users database !"""
    click.confirm(
        "This will erase all users and roles.\nAre you sure you want to continue?",
        abort=True,
    )
    db.reflect()
    try:
        db.session.query(UserRole).delete()
        db.session.query(User).delete()
        db.session.commit()
    except:
        db.session.rollback()
        raise


@app.cli.command()
@click.argument("username")
@click.argument("role")
@click.argument("dept")
@click.option("-n", "--nom", "nom")
@click.option("-p", "--prenom", "prenom")
def user_create(username, role, dept, nom=None, prenom=None):  # user-create
    "Create a new user"
    r = Role.get_named_role(role)
    if not r:
        sys.stderr.write("user_create: role {r} does not exists\n".format(r=role))
        return 1
    u = User.query.filter_by(user_name=username).first()
    if u:
        sys.stderr.write("user_create: user {u} already exists\n".format(u=u))
        return 2
    if dept == "@all":
        dept = None
    u = User(user_name=username, dept=dept, nom=nom, prenom=prenom)
    u.add_role(r, dept)
    db.session.add(u)
    db.session.commit()
    click.echo(
        "created user, login: {u.user_name}, with role {r} in dept. {dept}".format(
            u=u, r=r, dept=dept
        )
    )


@app.cli.command()
@click.argument("username")
@click.password_option()
def user_password(username, password=None):  # user-password
    "Set (or change) user's password"
    if not password:
        sys.stderr.write("user_password: missing password")
        return 1
    u = User.query.filter_by(user_name=username).first()
    if not u:
        sys.stderr.write(f"user_password: user {username} does not exists\n")
        return 1

    u.set_password(password)
    db.session.add(u)
    db.session.commit()
    click.echo(f"changed password for user {u}")


@app.cli.command()
@click.argument("rolename")
@click.argument("permissions", nargs=-1)
def create_role(rolename, permissions):  # create-role
    """Create a new role"""
    # Check rolename
    if not re.match(r"^[a-zA-Z0-9]+$", rolename):
        sys.stderr.write(f"create_role: invalid rolename {rolename}\n")
        return 1
    # Check permissions
    permission_list = []
    for permission_name in permissions:
        perm = Permission.get_by_name(permission_name)
        if not perm:
            sys.stderr.write(f"create_role: invalid permission name {perm}\n")
            sys.stderr.write(
                f"\tavailable permissions: {', '.join([ name for name in Permission.permission_by_name])}.\n"
            )
            return 1
        permission_list.append(perm)

    role = Role.query.filter_by(name=rolename).first()
    if role:
        sys.stderr.write(f"create_role: role {rolename} already exists\n")
        return 1

    role = Role(name=rolename)
    for perm in permission_list:
        role.add_permission(perm)
    db.session.add(role)
    db.session.commit()


@app.cli.command()
@click.argument("rolename")
@click.option("-a", "--add", "addpermissionname")
@click.option("-r", "--remove", "removepermissionname")
def edit_role(rolename, addpermissionname=None, removepermissionname=None):  # edit-role
    """Add [-a] and/or remove [-r] a permission to/from a role.
    In ScoDoc, permissions are not associated to users but to roles.
    Each user has a set of roles in each departement.

    Example: `flask edit-role -a ScoEditApo Ens`
    """
    if addpermissionname:
        perm_to_add = Permission.get_by_name(addpermissionname)
        if not perm_to_add:
            sys.stderr.write(
                f"edit_role: permission {addpermissionname} does not exists\n"
            )
            return 1
    else:
        perm_to_add = None
    if removepermissionname:
        perm_to_remove = Permission.get_by_name(removepermissionname)
        if not perm_to_remove:
            sys.stderr.write(
                f"edit_role: permission {removepermissionname} does not exists\n"
            )
            return 1
    else:
        perm_to_remove = None
    role = Role.query.filter_by(name=rolename).first()
    if not role:
        sys.stderr.write(f"edit_role: role {rolename} does not exists\n")
        return 1
    if perm_to_add:
        role.add_permission(perm_to_add)
        click.echo(f"adding permission {addpermissionname} to role {rolename}")
    if perm_to_remove:
        role.remove_permission(perm_to_remove)
        click.echo(f"removing permission {removepermissionname} from role {rolename}")
    if perm_to_add or perm_to_remove:
        db.session.add(role)
        db.session.commit()


@app.cli.command()
@click.argument("dept")
def delete_dept(dept):  # delete-dept
    """Delete existing departement"""
    from app.scodoc import notesdb as ndb
    from app.scodoc import sco_dept

    click.confirm(
        f"""Attention: Cela va effacer toutes les données du département {dept}
        (étudiants, notes, formations, etc)
        Voulez-vous vraiment continuer ?
        """,
        abort=True,
    )
    db.reflect()
    ndb.open_db_connection()
    d = models.Departement.query.filter_by(acronym=dept).first()
    if d is None:
        sys.stderr.write(f"Erreur: le departement {dept} n'existe pas !\n")
        return 2
    sco_dept.delete_dept(d.id)
    db.session.commit()
    return 0


@app.cli.command()
@click.argument("dept")
def create_dept(dept):  # create-dept
    "Create new departement"
    d = models.Departement(acronym=dept)
    p1 = ScoPreference(name="DeptName", value=dept, departement=d)
    db.session.add(p1)
    db.session.add(d)
    db.session.commit()
    return 0


@app.cli.command()
@click.argument("depts", nargs=-1)
def list_depts(depts=""):  # list-dept
    """If dept exists, print it, else nothing.
    Called without arguments, list all depts along with their ids.
    """
    for dept in models.Departement.query.order_by(models.Departement.id):
        if not depts or dept.acronym in depts:
            print(f"{dept.id}\t{dept.acronym}")


@app.cli.command()
@click.option(
    "-n",
    "--name",
    is_flag=True,
    help="show database name instead of connexion string (required for "
    "dropdb/createddb commands)",
)
def scodoc_database(name):  # list-dept
    """print the database connexion string"""
    uri = app.config["SQLALCHEMY_DATABASE_URI"]
    if name:
        print(uri.split("/")[-1])
    else:
        print(uri)


@app.cli.command()
@with_appcontext
def import_scodoc7_users():  # import-scodoc7-users
    """Import users defined in ScoDoc7 postgresql database into ScoDoc 9
    The old database SCOUSERS  must be alive and readable by the current user.
    This script is typically run as unix user "scodoc".
    The original SCOUSERS database is left unmodified.
    """
    messages = tools.import_scodoc7_user_db()
    click.echo("----")
    click.echo(f"import terminé: {len(messages)} warnings\n")
    click.echo("\n".join(messages) + "\n")


@app.cli.command()
@click.argument("dept")
@click.argument("dept_db_name")
@with_appcontext
def import_scodoc7_dept(dept: str, dept_db_name: str = ""):  # import-scodoc7-dept
    """Import département ScoDoc 7: dept: InfoComm, dept_db_name: SCOINFOCOMM"""
    dept_db_uri = f"postgresql:///{dept_db_name}"
    tools.import_scodoc7_dept(dept, dept_db_uri)


@app.cli.command()
@click.argument("dept", default="")
@with_appcontext
def migrate_scodoc7_dept_archives(dept: str):  # migrate-scodoc7-dept-archives
    """Post-migration: renomme les archives en fonction des id de ScoDoc 9"""
    tools.migrate_scodoc7_dept_archives(dept)


@app.cli.command()
@click.argument("formsemestre_id", type=click.INT)
@click.argument("xlsfile", type=click.File("rb"))
@click.argument("zipfile", type=click.File("rb"))
def photos_import_files(formsemestre_id: int, xlsfile: str, zipfile: str):
    import app as mapp
    from app.scodoc import sco_trombino, sco_photos
    from app.scodoc import notesdb as ndb
    from flask_login import login_user
    from app.auth.models import get_super_admin

    sem = mapp.models.formsemestre.FormSemestre.query.get(formsemestre_id)
    if not sem:
        sys.stderr.write("photos-import-files: numéro de semestre invalide\n")
        return 2

    with app.test_request_context():
        mapp.set_sco_dept(sem.departement.acronym)
        admin_user = get_super_admin()
        login_user(admin_user)

        def callback(etud, data, filename):
            sco_photos.store_photo(etud, data)

        (
            ignored_zipfiles,
            unmatched_files,
            stored_etud_filename,
        ) = sco_trombino.zip_excel_import_files(
            xlsfile=xlsfile,
            zipfile=zipfile,
            callback=callback,
            filename_title="fichier_photo",
        )
        print(
            render_template(
                "scolar/photos_import_files.txt",
                ignored_zipfiles=ignored_zipfiles,
                unmatched_files=unmatched_files,
                stored_etud_filename=stored_etud_filename,
            )
        )


@app.cli.command()
@with_appcontext
def clear_cache():  # clear-cache
    """Clear ScoDoc cache
    This cache (currently Redis) is persistent between invocation
    and it may be necessary to clear it during development or tests.
    """
    clear_scodoc_cache()
    click.echo("Redis caches flushed.")


def recursive_help(cmd, parent=None):
    ctx = click.core.Context(cmd, info_name=cmd.name, parent=parent)
    print(cmd.get_help(ctx))
    print()
    commands = getattr(cmd, "commands", {})
    for sub in commands.values():
        recursive_help(sub, ctx)


@app.cli.command()
def dumphelp():
    recursive_help(app.cli)


@app.cli.command()
@click.option("-h", "--host", default="127.0.0.1", help="The interface to bind to.")
@click.option("-p", "--port", default=5000, help="The port to bind to.")
@click.option(
    "--length",
    default=25,
    help="Number of functions to include in the profiler report.",
)
@click.option(
    "--profile-dir", default=None, help="Directory where profiler data files are saved."
)
def profile(host, port, length, profile_dir):
    """Start the application under the code profiler."""
    from werkzeug.middleware.profiler import ProfilerMiddleware
    from werkzeug.serving import run_simple

    app.wsgi_app = ProfilerMiddleware(
        app.wsgi_app, restrictions=[length], profile_dir=profile_dir
    )
    run_simple(
        host, port, app, use_debugger=False
    )  # use run_simple instead of app.run()
