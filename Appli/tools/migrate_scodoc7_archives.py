# -*- mode: python -*-
# -*- coding: utf-8 -*-

import glob
import os
import shutil
import sys

from app.models import Departement
from app.models.formsemestre import FormSemestre
from app.models.etudiants import Identite


def migrate_scodoc7_dept_archives(dept_name=""):
    if dept_name:
        depts = Departement.query.filter_by(acronym=dept_name)
    else:
        depts = Departement.query
    for dept in depts:
        print(f"Migrating {dept.acronym} archives...")
        # SemsArchiver
        #   /opt/scodoc-data/archives/<dept>/<scodoc7id> -> formsemestre_id
        migrate_sem_archives(dept)

        # EtudsArchiver:
        migrate_docetuds(dept)

        # ApoCSVArchiver:
        #   /opt/scodoc-data/archives/apo_csv/<dept>/ -> apo_csv/<dept_id>/
        migrate_apo_csv(dept)


def migrate_sem_archives(dept):
    "/opt/scodoc-data/archives/<dept>/<scodoc7id> -> formsemestre_id"
    n = 0
    n_moves = 0
    for sem in FormSemestre.query.filter_by(dept_id=dept.id):
        n += 1
        arch_dir7 = f"/opt/scodoc-data/archives/{dept.acronym}/{sem.scodoc7_id}"
        arch_dir9 = f"/opt/scodoc-data/archives/{dept.id}/{sem.id}"
        if os.path.exists(arch_dir7):
            n_moves += 1
            if not os.path.exists(arch_dir9):
                # print(f"renaming {arch_dir7} to {arch_dir9}")
                shutil.move(arch_dir7, arch_dir9)
            else:
                # print(f"merging {arch_dir7} with {arch_dir9}")
                for arch in glob.glob(f"{arch_dir7}/*"):
                    # print(f"\tmoving {arch}")
                    shutil.move(arch, arch_dir9)
    # print(f"moved {n_moves}/{n} sems")


def migrate_docetuds(dept):
    "/opt/scodoc-data/archives/docetuds/<dept>/<scodoc7_id>/ -> etudid"
    n = 0
    n_moves = 0
    for etud in Identite.query.filter_by(dept_id=dept.id):
        n += 1
        arch_dir7 = (
            f"/opt/scodoc-data/archives/docetuds/{dept.acronym}/{etud.scodoc7_id}"
        )
        arch_dir9 = f"/opt/scodoc-data/archives/docetuds/{dept.id}/{etud.id}"
        if os.path.exists(arch_dir7):
            n_moves += 1
            if not os.path.exists(arch_dir9):
                # print(f"renaming {arch_dir7} to {arch_dir9}")
                shutil.move(arch_dir7, arch_dir9)
            else:
                # print(f"merging {arch_dir7} with {arch_dir9}")
                for arch in glob.glob(f"{arch_dir7}/*"):
                    # print(f"\tmoving {arch}")
                    shutil.move(arch, arch_dir9)
    # print(f"moved {n_moves}/{n} etuds")


def migrate_apo_csv(dept):
    "/opt/scodoc-data/archives/apo_csv/<dept>/ -> .../apo_csv/<dept_id>/"
    arch_dir7 = f"/opt/scodoc-data/archives/apo_csv/{dept.acronym}"
    arch_dir7_upper = f"/opt/scodoc-data/archives/apo_csv/{dept.acronym.upper()}"
    arch_dir9 = f"/opt/scodoc-data/archives/apo_csv/{dept.id}"
    if os.path.exists(arch_dir7):
        if os.path.exists(arch_dir9):
            print(
                f"Warning: {arch_dir9} exist ! not moving {arch_dir7}", file=sys.stderr
            )
        else:
            shutil.move(arch_dir7, arch_dir9)
    elif os.path.exists(arch_dir7_upper):
        if os.path.exists(arch_dir9):
            print(
                f"Warning: {arch_dir9} exist ! not moving {arch_dir7_upper}",
                file=sys.stderr,
            )
        else:
            shutil.move(arch_dir7_upper, arch_dir9)
