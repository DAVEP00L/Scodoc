# Simple benchmark
# mesure temps execution NotesTable

import time

from flask import g
from flask_login import login_user

from config import RunningConfig as BenchConfig
import app
from app import db, create_app
from app import clear_scodoc_cache
from app.auth.models import get_super_admin
from app.scodoc import notesdb as ndb
from app.scodoc import notes_table


def setup_generator(dept: str):
    # Setup
    apptest = create_app(BenchConfig)
    # Run tests:
    with apptest.test_client() as client:
        with apptest.app_context():
            with apptest.test_request_context():
                # Clear application cache:
                print("clearing cache...")
                clear_scodoc_cache()
                # initialize scodoc "g":
                g.stored_get_formsemestre = {}
                # Loge l'utilisateur super-admin
                admin_user = get_super_admin()
                login_user(admin_user)
                app.set_sco_dept(dept)  # set db connection
                yield client
                ndb.close_db_connection()
                # Teardown:
                db.session.commit()
                db.session.remove()


def bench_notes_table(dept: str, formsemestre_ids: list[int]) -> float:
    for client in setup_generator(dept):
        tot_time = 0.0
        for formsemestre_id in formsemestre_ids:
            print(f"building sem {formsemestre_id}...")
            t0 = time.time()
            nt = notes_table.NotesTable(formsemestre_id)
            tot_time += time.time() - t0
        print(f"Total time: {tot_time}")
    return tot_time
