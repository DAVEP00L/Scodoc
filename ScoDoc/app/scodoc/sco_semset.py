# -*- mode: python -*-
# -*- coding: utf-8 -*-

##############################################################################
#
# Gestion scolarite IUT
#
# Copyright (c) 1999 - 2021 Emmanuel Viennet.  All rights reserved.
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
#
#   Emmanuel Viennet      emmanuel.viennet@viennet.net
#
##############################################################################

"""Gestion des ensembles de semestres:

class SemSet:  un ensemble de semestres d'un département, à exporter ves Apogée. En principe de la meme annee scolaire.
 
 SemSet.annees_scolaires() : les annees scolaires. e.g. [ 2015, 2016 ], ou le plus souvent, une seule: [2016]
 SemSet.list_etapes(): listes des étapes apogee et vdi des semestres (instances de ApoEtapeVDI)

 SemSet.add(sem): ajoute un semestre à l'ensemble


sem_set_list()

"""

import flask
from flask import g

from app.scodoc import html_sco_header
from app.scodoc import sco_cache
from app.scodoc import sco_etape_apogee
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_portal_apogee
from app.scodoc import sco_preferences
from app.scodoc.gen_tables import GenTable
from app import log
from app.scodoc.sco_etape_bilan import EtapeBilan
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_vdi import ApoEtapeVDI
import app.scodoc.notesdb as ndb
import app.scodoc.sco_utils as scu


_semset_editor = ndb.EditableTable(
    "notes_semset",
    "semset_id",
    ("semset_id", "title", "annee_scolaire", "sem_id"),
    filter_dept=True,
)

semset_create = _semset_editor.create
semset_edit = _semset_editor.edit
semset_list = _semset_editor.list
semset_delete = _semset_editor.delete


class SemSet(dict):
    def __init__(self, semset_id=None, title="", annee_scolaire="", sem_id=""):
        """Load and init, or, if semset_id is not specified, create"""
        if not annee_scolaire and not semset_id:
            # on autorise annee_scolaire null si sem_id pour pouvoir lire les anciens semsets
            # mal construits...
            raise ScoValueError("Année scolaire invalide !")
        self.semset_id = semset_id
        self["semset_id"] = semset_id
        self.sems = []
        self.formsemestre_ids = []
        cnx = ndb.GetDBConnexion()
        if semset_id:  # read existing set
            L = semset_list(cnx, args={"semset_id": semset_id})
            if not L:
                raise ValueError("invalid semset_id %s" % semset_id)
            self["title"] = L[0]["title"]
            self["annee_scolaire"] = L[0]["annee_scolaire"]
            self["sem_id"] = L[0]["sem_id"]
            r = ndb.SimpleDictFetch(
                "SELECT formsemestre_id FROM notes_semset_formsemestre WHERE semset_id = %(semset_id)s",
                {"semset_id": semset_id},
            )
            if r:
                self.formsemestre_ids = {x["formsemestre_id"] for x in r}  # a set
        else:  # create a new empty set
            self.semset_id = semset_create(
                cnx,
                {"title": title, "annee_scolaire": annee_scolaire, "sem_id": sem_id},
            )
            log("created new semset_id=%s" % self.semset_id)
        self.load_sems()
        # analyse des semestres pour construire le bilan par semestre et par étape
        self.bilan = EtapeBilan()
        for sem in self.sems:
            self.bilan.add_sem(sem)

    def delete(self):
        """delete"""
        cnx = ndb.GetDBConnexion()
        semset_delete(cnx, self.semset_id)

    def edit(self, args):
        cnx = ndb.GetDBConnexion()
        semset_edit(cnx, args)

    def load_sems(self):
        """Load formsemestres"""
        self.sems = []
        for formsemestre_id in self.formsemestre_ids:
            self.sems.append(sco_formsemestre.get_formsemestre(formsemestre_id))

        if self.sems:
            self["date_debut"] = min([sem["date_debut_iso"] for sem in self.sems])
            self["date_fin"] = max([sem["date_fin_iso"] for sem in self.sems])
        else:
            self["date_debut"] = ""
            self["date_fin"] = ""

        self["etapes"] = self.list_etapes()
        self["semtitles"] = [sem["titre_num"] for sem in self.sems]

        # Construction du ou des lien(s) vers le semestre
        pattern = '<a class="stdlink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titreannee)s</a>'
        self["semlinks"] = [(pattern % sem) for sem in self.sems]
        self["semtitles_str"] = "<br/>".join(self["semlinks"])

    def fill_formsemestres(self):
        for sem in self.sems:
            sco_formsemestre_status.fill_formsemestre(sem)
            ets = sco_etape_apogee.apo_get_sem_etapes(sem)
            sem["etapes_apo_str"] = sco_formsemestre.etapes_apo_str(sorted(list(ets)))

    def add(self, formsemestre_id):
        # check
        if formsemestre_id in self.formsemestre_ids:
            return  # already there
        if formsemestre_id not in [
            sem["formsemestre_id"] for sem in self.list_possible_sems()
        ]:
            raise ValueError(
                "can't add %s to set %s: incompatible sem_id"
                % (formsemestre_id, self.semset_id)
            )

        ndb.SimpleQuery(
            """INSERT INTO notes_semset_formsemestre 
            (formsemestre_id, semset_id) 
            VALUES (%(formsemestre_id)s, %(semset_id)s)
            """,
            {
                "formsemestre_id": formsemestre_id,
                "semset_id": self.semset_id,
            },
        )
        self.load_sems()  # update our list

    def remove(self, formsemestre_id):
        ndb.SimpleQuery(
            """DELETE FROM notes_semset_formsemestre
            WHERE semset_id=%(semset_id)s 
            AND formsemestre_id=%(formsemestre_id)s
            """,
            {"formsemestre_id": formsemestre_id, "semset_id": self.semset_id},
        )
        self.load_sems()  # update our list

    def annees_scolaires(self):
        """Les annees scolaires. e.g. [ 2015, 2016 ], ou le plus souvent, une seule: [2016]
        L'année scolaire est l'année de début du semestre (2015 pour 2015-2016)
        """
        annees = list(set([int(s["annee_debut"]) for s in self.sems]))
        annees.sort()
        return annees

    def list_etapes(self):
        """Listes triée des étapes Apogée des semestres (instances de ApoEtapeVDI).
        Chaque étape apparait une seule fois, dans sa forme la plus générale.
        Si on a [ 'V1RT', 'V1RT!111' ], le résultat sera [ 'V1RT' ]
        Si on a [ 'V1RT!111', 'V1RT!112' ], le résultat sera [ 'V1RT!111', 'V1RT!112' ]
        """
        D = {}  # { etape : { versions vdi } }
        for s in self.sems:
            for et in s["etapes"]:
                if et:
                    if et.etape in D:
                        D[et.etape].add(et.vdi)
                    else:
                        D[et.etape] = {et.vdi}
        # enlève les versions excédentaires:
        for etape in D:
            if "" in D[etape]:
                D[etape] = [""]
        # forme liste triée d'instances:
        etapes = []
        for etape in D:
            for vdi in D[etape]:
                etapes.append(ApoEtapeVDI(etape=etape, vdi=vdi))
        etapes.sort()
        return etapes

    def list_possible_sems(self):
        """List sems that can be added to this set"""
        sems = sco_formsemestre.do_formsemestre_list()
        # remove sems already here:
        sems = [
            sem for sem in sems if sem["formsemestre_id"] not in self.formsemestre_ids
        ]
        # filter annee, sem_id:
        # Remplacement du filtre de proposition des semestres potentiels
        # au lieu de la parité (sem 1 et 3 / sem 2 et 4) on filtre sur la date de
        # debut du semestre: ceci permet d'ajouter les semestres décalés
        if self["annee_scolaire"]:
            sems = [
                sem
                for sem in sems
                if sco_formsemestre.sem_in_semestre_scolaire(
                    sem,
                    year=self["annee_scolaire"],
                    saison=self["sem_id"],
                )
            ]
        return sems

    def load_etuds(self):
        self["etuds_without_nip"] = set()  # etudids
        self["jury_ok"] = True
        for sem in self.sems:
            nt = sco_cache.NotesTableCache.get(sem["formsemestre_id"])
            sem["etuds"] = list(nt.identdict.values())
            sem["nips"] = {e["code_nip"] for e in sem["etuds"] if e["code_nip"]}
            sem["etuds_without_nip"] = {
                e["etudid"] for e in sem["etuds"] if not e["code_nip"]
            }
            self["etuds_without_nip"] |= sem["etuds_without_nip"]
            sem["jury_ok"] = nt.all_etuds_have_sem_decisions()
            self["jury_ok"] &= sem["jury_ok"]

    def html_descr(self):
        """Short HTML description"""
        H = [
            """<span class="box_title">Ensemble de semestres %(title)s</span>""" % self
        ]
        if self["annee_scolaire"]:
            H.append("<p>Année scolaire: %(annee_scolaire)s</p>" % self)
        else:
            H.append(
                "<p>Année(s) scolaire(s) présentes: %s"
                % ", ".join([str(x) for x in self.annees_scolaires()])
            )
            if len(self.annees_scolaires()) > 1:
                H.append(
                    ' <span class="redboldtext">(attention, plusieurs années !)</span>'
                )
            H.append("</p>")
        if self["sem_id"]:
            H.append(
                "<p>Période: %(sem_id)s (<em>1: septembre, 2: janvier</em>)</p>" % self
            )
        H.append(
            "<p>Etapes: <tt>%s</tt></p>"
            % sco_formsemestre.etapes_apo_str(self.list_etapes())
        )
        H.append("""<h4>Semestres de l'ensemble:</h4><ul class="semset_listsems">""")

        for sem in self.sems:
            H.append(
                '<li><a class="stdlink" href="formsemestre_status?formsemestre_id=%(formsemestre_id)s">%(titre_num)s</a> %(mois_debut)s - %(mois_fin)s'
                % sem
            )
            H.append(
                ' <a class="stdlink" href="do_semset_remove_sem?semset_id=%s&formsemestre_id=%s">(retirer)</a>'
                % (self["semset_id"], sem["formsemestre_id"])
            )
            H.append(
                "<br/>Etapes: <tt>%(etapes_apo_str)s</tt>, %(nbinscrits)s inscrits"
                % sem
            )
            H.append("<br/>Elément Apogée année: ")
            if sem["elt_annee_apo"]:
                H.append("<tt>%(elt_annee_apo)s</tt>" % sem)
            else:
                H.append('<span style="color: red;">manquant</span>')

            H.append("<br/>Elément Apogée semestre: ")
            if sem["elt_sem_apo"]:
                H.append("<tt>%(elt_sem_apo)s</tt>" % sem)
            else:
                H.append('<span style="color: red;">manquant</span>')

            H.append("</br><em>vérifier les semestres antécédents !</em>")
            H.append("</li>")

        return "\n".join(H)

    def html_form_sems(self):
        """HTML form to manage sems"""
        H = []
        possible_sems = self.list_possible_sems()
        if possible_sems:
            menu_sem = """<select name="formsemestre_id">
            <option value="" selected>(semestre)</option>"""
            for sem in possible_sems:
                menu_sem += (
                    """<option value="%(formsemestre_id)s">%(titreannee)s</option>\n"""
                    % sem
                )
            menu_sem += """</select>"""
            H.append(
                '<form action="do_semset_add_sem" method="post">Ajouter un semestre:'
            )
            H.append(menu_sem)
            H.append(
                '<input type="hidden" name="semset_id" value="%s"/>' % self.semset_id
            )
            H.append('<input type="submit" value="Ajouter"/>')
            H.append("</form>")
        else:
            H.append("<em>pas de semestres à ajouter</em>")
        return "\n".join(H)

    def html_diagnostic(self):
        """Affichage de la partie Effectifs et Liste des étudiants
        (actif seulement si un portail est configuré)
        """
        if sco_portal_apogee.has_portal():
            return self.bilan.html_diagnostic()
        else:
            return ""


def get_semsets_list():
    """Liste de tous les semsets
    Trié par date_debut, le plus récent d'abord
    """
    cnx = ndb.GetDBConnexion()
    L = []
    for s in semset_list(cnx):
        L.append(SemSet(semset_id=s["semset_id"]))
    L.sort(key=lambda s: s["date_debut"], reverse=True)
    return L


def do_semset_create(title="", annee_scolaire=None, sem_id=None):
    """Create new setset"""
    log(
        "do_semset_create(title=%s, annee_scolaire=%s, sem_id=%s)"
        % (title, annee_scolaire, sem_id)
    )
    SemSet(title=title, annee_scolaire=annee_scolaire, sem_id=sem_id)
    return flask.redirect("semset_page")


def do_semset_delete(semset_id, dialog_confirmed=False):
    """Delete a semset"""
    if not semset_id:
        raise ScoValueError("empty semset_id")
    s = SemSet(semset_id=semset_id)
    if not dialog_confirmed:
        return scu.confirm_dialog(
            "<h2>Suppression de l'ensemble %(title)s ?</h2>" % s,
            dest_url="",
            parameters={"semset_id": semset_id},
            cancel_url="semset_page",
        )
    s.delete()
    return flask.redirect("semset_page")


def edit_semset_set_title(id=None, value=None):
    """Change title of semset"""
    title = value.strip()
    if not id:
        raise ScoValueError("empty semset_id")
    SemSet(semset_id=id)
    cnx = ndb.GetDBConnexion()
    semset_edit(cnx, {"semset_id": id, "title": title})
    return title


def do_semset_add_sem(semset_id, formsemestre_id):
    """Add a sem to a semset"""
    if not semset_id:
        raise ScoValueError("empty semset_id")
    s = SemSet(semset_id=semset_id)
    # check for valid formsemestre_id
    _ = sco_formsemestre.get_formsemestre(formsemestre_id)  # raise exc

    s.add(formsemestre_id)

    return flask.redirect("apo_semset_maq_status?semset_id=%s" % semset_id)


def do_semset_remove_sem(semset_id, formsemestre_id):
    """Add a sem to a semset"""
    if not semset_id:
        raise ScoValueError("empty semset_id")
    s = SemSet(semset_id)

    s.remove(formsemestre_id)

    return flask.redirect("apo_semset_maq_status?semset_id=%s" % semset_id)


# ----------------------------------------


def semset_page(format="html"):
    """Page avec liste semsets:
    Table avec : date_debut date_fin titre liste des semestres
    """
    semsets = get_semsets_list()
    for s in semsets:
        s["suppress"] = scu.icontag(
            "delete_small_img", border="0", alt="supprimer", title="Supprimer"
        )
        s["_suppress_target"] = "do_semset_delete?semset_id=%s" % (s["semset_id"])
        s["export_link"] = "Export Apogée"
        s["_export_link_target"] = "apo_semset_maq_status?semset_id=%s" % s.semset_id
        s["_export_link_link_class"] = "stdlink"
        # Le lien associé au nom de semestre redirigeait vers le semset
        # (remplacé par n liens vers chacun des semestres)
        # s['_semtitles_str_target'] = s['_export_link_target']
        # Experimental:
        s[
            "_title_td_attrs"
        ] = 'class="inplace_edit" data-url="edit_semset_set_title" id="%s"' % (
            s["semset_id"]
        )

    tab = GenTable(
        rows=semsets,
        titles={
            "annee_scolaire": "Année scolaire",
            "sem_id": "P",
            "date_debut": "Début",
            "date_fin": "Fin",
            "title": "Titre",
            "export_link": "",
            "semtitles_str": "semestres",
        },
        columns_ids=[
            "suppress",
            "annee_scolaire",
            "sem_id",
            "date_debut",
            "date_fin",
            "title",
            "export_link",
            "semtitles_str",
        ],
        html_sortable=True,
        html_class="table_leftalign",
        filename="semsets",
        preferences=sco_preferences.SemPreferences(),
    )
    if format != "html":
        return tab.make_page(format=format)

    page_title = "Ensembles de semestres"
    H = [
        html_sco_header.sco_header(
            page_title=page_title,
            init_qtip=True,
            javascripts=["libjs/jinplace-1.2.1.min.js"],
        ),
        """<script>$(function() {
           $('.inplace_edit').jinplace();
           });
           </script>""",
        "<h2>%s</h2>" % page_title,
    ]
    H.append(tab.html())

    annee_courante = int(scu.AnneeScolaire())
    menu_annee = "\n".join(
        [
            '<option value="%s">%s</option>' % (i, i)
            for i in range(2014, annee_courante + 1)
        ]
    )

    H.append(
        """
    <div style="margin-top:20px;">
    <h4>Création nouvel ensemble</h4>
    <form method="POST" action="do_semset_create">
    <select name="annee_scolaire">
    <option value="" selected>(année scolaire)</option>"""
    )
    H.append(menu_annee)
    H.append(
        """</select>
    <select name="sem_id">
    <option value="1">1re période (S1, S3)</option>
    <option value="2">2de période (S2, S4)</option>
    <option value="0">non semestrialisée (LP, ...)</option>
    </select>
    <input type="text" name="title" size="32"/>
    <input type="submit" value="Créer"/>
    </form></div>
    """
    )

    H.append(
        """
    <div>
    <h4>Autres opérations:</h4>
    <ul>
    <li><a class="stdlink" href="scodoc_table_results">
    Table des résultats de tous les semestres
    </a></li>
    <li><a class="stdlink" href="apo_compare_csv_form">
    Comparaison de deux maquettes Apogée
    </a></li>
    </ul>
    </div>
    """
    )

    return "\n".join(H) + html_sco_header.sco_footer()
