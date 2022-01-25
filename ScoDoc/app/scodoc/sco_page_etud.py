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

"""ScoDoc ficheEtud

   Fiche description d'un étudiant et de son parcours

"""
from flask import url_for, g, request
from flask_login import current_user

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc import html_sco_header
from app.scodoc import htmlutils
from app.scodoc import sco_archives_etud
from app.scodoc import sco_bac
from app.scodoc import sco_codes_parcours
from app.scodoc import sco_formsemestre
from app.scodoc import sco_formsemestre_status
from app.scodoc import sco_groups
from app.scodoc import sco_parcours_dut
from app.scodoc import sco_permissions_check
from app.scodoc import sco_photos
from app.scodoc import sco_users
from app.scodoc import sco_report
from app.scodoc import sco_etud
from app.scodoc.sco_bulletins import etud_descr_situation_semestre
from app.scodoc.sco_exceptions import ScoValueError
from app.scodoc.sco_formsemestre_validation import formsemestre_recap_parcours_table
from app.scodoc.sco_permissions import Permission


def _menuScolarite(authuser, sem, etudid):
    """HTML pour menu "scolarite" pour un etudiant dans un semestre.
    Le contenu du menu depend des droits de l'utilisateur et de l'état de l'étudiant.
    """
    locked = not sem["etat"]
    if locked:
        lockicon = scu.icontag("lock32_img", title="verrouillé", border="0")
        return lockicon  # no menu
    if not authuser.has_permission(
        Permission.ScoEtudInscrit
    ) and not authuser.has_permission(Permission.ScoEtudChangeGroups):
        return ""  # no menu
    ins = sem["ins"]
    args = {"etudid": etudid, "formsemestre_id": ins["formsemestre_id"]}

    if ins["etat"] != "D":
        dem_title = "Démission"
        dem_url = "scolar.formDem"
    else:
        dem_title = "Annuler la démission"
        dem_url = "scolar.doCancelDem"

    # Note: seul un etudiant inscrit (I) peut devenir défaillant.
    if ins["etat"] != sco_codes_parcours.DEF:
        def_title = "Déclarer défaillance"
        def_url = "scolar.formDef"
    elif ins["etat"] == sco_codes_parcours.DEF:
        def_title = "Annuler la défaillance"
        def_url = "scolar.doCancelDef"
    def_enabled = (
        (ins["etat"] != "D")
        and authuser.has_permission(Permission.ScoEtudInscrit)
        and not locked
    )
    items = [
        {
            "title": dem_title,
            "endpoint": dem_url,
            "args": args,
            "enabled": authuser.has_permission(Permission.ScoEtudInscrit)
            and not locked,
        },
        {
            "title": "Validation du semestre (jury)",
            "endpoint": "notes.formsemestre_validation_etud_form",
            "args": args,
            "enabled": authuser.has_permission(Permission.ScoEtudInscrit)
            and not locked,
        },
        {
            "title": def_title,
            "endpoint": def_url,
            "args": args,
            "enabled": def_enabled,
        },
        {
            "title": "Inscrire à un module optionnel (ou au sport)",
            "endpoint": "notes.formsemestre_inscription_option",
            "args": args,
            "enabled": authuser.has_permission(Permission.ScoEtudInscrit)
            and not locked,
        },
        {
            "title": "Désinscrire (en cas d'erreur)",
            "endpoint": "notes.formsemestre_desinscription",
            "args": args,
            "enabled": authuser.has_permission(Permission.ScoEtudInscrit)
            and not locked,
        },
        {
            "title": "Inscrire à un autre semestre",
            "endpoint": "notes.formsemestre_inscription_with_modules_form",
            "args": {"etudid": etudid},
            "enabled": authuser.has_permission(Permission.ScoEtudInscrit),
        },
        {
            "title": "Enregistrer un semestre effectué ailleurs",
            "endpoint": "notes.formsemestre_ext_create_form",
            "args": args,
            "enabled": authuser.has_permission(Permission.ScoImplement),
        },
    ]

    return htmlutils.make_menu(
        "Scolarité", items, css_class="direction_etud", alone=True
    )


def ficheEtud(etudid=None):
    "fiche d'informations sur un etudiant"
    authuser = current_user
    cnx = ndb.GetDBConnexion()
    if etudid:
        try:  # pour les bookmarks avec d'anciens ids...
            etudid = int(etudid)
        except ValueError:
            raise ScoValueError("id invalide !")
        # la sidebar est differente s'il y a ou pas un etudid
        # voir html_sidebar.sidebar()
        g.etudid = etudid
    args = sco_etud.make_etud_args(etudid=etudid)
    etuds = sco_etud.etudident_list(cnx, args)
    if not etuds:
        log("ficheEtud: etudid=%s request.args=%s" % (etudid, request.args))
        raise ScoValueError("Etudiant inexistant !")
    etud = etuds[0]
    etudid = etud["etudid"]
    sco_etud.fill_etuds_info([etud])
    #
    info = etud
    info["ScoURL"] = scu.ScoURL()
    info["authuser"] = authuser
    info["info_naissance"] = info["date_naissance"]
    if info["lieu_naissance"]:
        info["info_naissance"] += " à " + info["lieu_naissance"]
    if info["dept_naissance"]:
        info["info_naissance"] += " (%s)" % info["dept_naissance"]
    info["etudfoto"] = sco_photos.etud_photo_html(etud)
    if (
        (not info["domicile"])
        and (not info["codepostaldomicile"])
        and (not info["villedomicile"])
    ):
        info["domicile"] = "<em>inconnue</em>"
    if info["paysdomicile"]:
        pays = sco_etud.format_pays(info["paysdomicile"])
        if pays:
            info["paysdomicile"] = "(%s)" % pays
        else:
            info["paysdomicile"] = ""
    if info["telephone"] or info["telephonemobile"]:
        info["telephones"] = "<br/>%s &nbsp;&nbsp; %s" % (
            info["telephonestr"],
            info["telephonemobilestr"],
        )
    else:
        info["telephones"] = ""
    # e-mail:
    if info["email_default"]:
        info["emaillink"] = ", ".join(
            [
                '<a class="stdlink" href="mailto:%s">%s</a>' % (m, m)
                for m in [etud["email"], etud["emailperso"]]
                if m
            ]
        )
    else:
        info["emaillink"] = "<em>(pas d'adresse e-mail)</em>"
    # champs dependant des permissions
    if authuser.has_permission(Permission.ScoEtudChangeAdr):
        info["modifadresse"] = (
            '<a class="stdlink" href="formChangeCoordonnees?etudid=%s">modifier adresse</a>'
            % etudid
        )
    else:
        info["modifadresse"] = ""

    # Groupes:
    sco_groups.etud_add_group_infos(info, info["cursem"])

    # Parcours de l'étudiant
    if info["sems"]:
        info["last_formsemestre_id"] = info["sems"][0]["formsemestre_id"]
    else:
        info["last_formsemestre_id"] = ""
    sem_info = {}
    for sem in info["sems"]:
        if sem["ins"]["etat"] != "I":
            descr, _ = etud_descr_situation_semestre(
                etudid,
                sem["formsemestre_id"],
                info["ne"],
                show_date_inscr=False,
            )
            grlink = '<span class="fontred">%s</span>' % descr["situation"]
        else:
            group = sco_groups.get_etud_main_group(etudid, sem)
            if group["partition_name"]:
                gr_name = group["group_name"]
            else:
                gr_name = "tous"
            grlink = (
                '<a class="discretelink" href="groups_view?group_ids=%s" title="Liste du groupe">groupe %s</a>'
                % (group["group_id"], gr_name)
            )
        # infos ajoutées au semestre dans le parcours (groupe, menu)
        menu = _menuScolarite(authuser, sem, etudid)
        if menu:
            sem_info[sem["formsemestre_id"]] = (
                "<table><tr><td>" + grlink + "</td><td>" + menu + "</td></tr></table>"
            )
        else:
            sem_info[sem["formsemestre_id"]] = grlink

    if info["sems"]:
        Se = sco_parcours_dut.SituationEtudParcours(etud, info["last_formsemestre_id"])
        info["liste_inscriptions"] = formsemestre_recap_parcours_table(
            Se,
            etudid,
            with_links=False,
            sem_info=sem_info,
            with_all_columns=False,
            a_url="Notes/",
        )
        info[
            "link_bul_pdf"
        ] = f"""<span class="link_bul_pdf"><a class="stdlink" href="{
            url_for("notes.etud_bulletins_pdf", scodoc_dept=g.scodoc_dept, etudid=etudid)
            }">tous les bulletins</a></span>"""
        if authuser.has_permission(Permission.ScoEtudInscrit):
            info[
                "link_inscrire_ailleurs"
            ] = f"""<span class="link_bul_pdf"><a class="stdlink" href="{
                url_for("notes.formsemestre_inscription_with_modules_form", scodoc_dept=g.scodoc_dept, etudid=etudid)
                }">inscrire à un autre semestre</a></span>"""
        else:
            info["link_inscrire_ailleurs"] = ""
    else:
        # non inscrit
        l = ["<p><b>Etudiant%s non inscrit%s" % (info["ne"], info["ne"])]
        if authuser.has_permission(Permission.ScoEtudInscrit):
            l.append(
                '<a href="%s/Notes/formsemestre_inscription_with_modules_form?etudid=%s">inscrire</a></li>'
                % (scu.ScoURL(), etudid)
            )
        l.append("</b></b>")
        info["liste_inscriptions"] = "\n".join(l)
        info["link_bul_pdf"] = ""
        info["link_inscrire_ailleurs"] = ""

    # Liste des annotations
    alist = []
    annos = sco_etud.etud_annotations_list(cnx, args={"etudid": etudid})
    for a in annos:
        if not sco_permissions_check.can_suppress_annotation(a["id"]):
            a["dellink"] = ""
        else:
            a[
                "dellink"
            ] = '<td class="annodel"><a href="doSuppressAnnotation?etudid=%s&annotation_id=%s">%s</a></td>' % (
                etudid,
                a["id"],
                scu.icontag(
                    "delete_img",
                    border="0",
                    alt="suppress",
                    title="Supprimer cette annotation",
                ),
            )
        author = sco_users.user_info(a["author"])
        alist.append(
            f"""<tr><td><span class="annodate">Le {a['date']} par {author['prenomnom']} : 
            </span><span class="annoc">{a['comment']}</span></td>{a['dellink']}</tr>
            """
        )
    info["liste_annotations"] = "\n".join(alist)
    # fiche admission
    has_adm_notes = (
        info["math"] or info["physique"] or info["anglais"] or info["francais"]
    )
    has_bac_info = (
        info["bac"]
        or info["specialite"]
        or info["annee_bac"]
        or info["rapporteur"]
        or info["commentaire"]
        or info["classement"]
        or info["type_admission"]
    )
    if has_bac_info or has_adm_notes:
        adm_tmpl = """<!-- Donnees admission -->
<div class="fichetitre">Informations admission</div>
"""
        if has_adm_notes:
            adm_tmpl += """
<table>
<tr><th>Bac</th><th>Année</th><th>Rg</th>
<th>Math</th><th>Physique</th><th>Anglais</th><th>Français</th></tr>
<tr>
<td>%(bac)s (%(specialite)s)</td>
<td>%(annee_bac)s </td>
<td>%(classement)s</td>
<td>%(math)s</td><td>%(physique)s</td><td>%(anglais)s</td><td>%(francais)s</td>
</tr>
</table>
"""
        adm_tmpl += """
<div>Bac %(bac)s (%(specialite)s) obtenu en %(annee_bac)s </div>
<div class="ilycee">%(ilycee)s</div>"""
        if info["type_admission"] or info["classement"]:
            adm_tmpl += """<div class="vadmission">"""
        if info["type_admission"]:
            adm_tmpl += """<span>Voie d'admission: <span class="etud_type_admission">%(type_admission)s</span></span> """
        if info["classement"]:
            adm_tmpl += """<span>Rang admission: <span class="etud_type_admission">%(classement)s</span></span>"""
        if info["type_admission"] or info["classement"]:
            adm_tmpl += "</div>"
        if info["rap"]:
            adm_tmpl += """<div class="note_rapporteur">%(rap)s</div>"""
        adm_tmpl += """</div>"""
    else:
        adm_tmpl = ""  # pas de boite "info admission"
    info["adm_data"] = adm_tmpl % info

    # Fichiers archivés:
    info["fichiers_archive_htm"] = (
        '<div class="fichetitre">Fichiers associés</div>'
        + sco_archives_etud.etud_list_archives_html(etudid)
    )

    # Devenir de l'étudiant:
    has_debouche = True
    if sco_permissions_check.can_edit_suivi():
        suivi_readonly = "0"
        link_add_suivi = """<li class="adddebouche">
            <a id="adddebouchelink" class="stdlink" href="#">ajouter une ligne</a>
            </li>"""
    else:
        suivi_readonly = "1"
        link_add_suivi = ""
    if has_debouche:
        info[
            "debouche_html"
        ] = """<div id="fichedebouche" data-readonly="%s" data-etudid="%s">
        <span class="debouche_tit">Devenir:</span>
        <div><form>
        <ul class="listdebouches">
        %s
        </ul>
        </form></div>
        </div>""" % (
            suivi_readonly,
            info["etudid"],
            link_add_suivi,
        )
    else:
        info["debouche_html"] = ""  # pas de boite "devenir"
    #
    if info["liste_annotations"]:
        info["tit_anno"] = '<div class="fichetitre">Annotations</div>'
    else:
        info["tit_anno"] = ""
    # Inscriptions
    # if info["sems"]:  # XXX rcl unused ? à voir
    #     rcl = (
    #         """(<a href="%(ScoURL)s/Notes/formsemestre_validation_etud_form?check=1&etudid=%(etudid)s&formsemestre_id=%(last_formsemestre_id)s&desturl=ficheEtud?etudid=%(etudid)s">récapitulatif parcours</a>)"""
    #         % info
    #     )
    # else:
    #     rcl = ""
    info[
        "inscriptions_mkup"
    ] = """<div class="ficheinscriptions" id="ficheinscriptions">
<div class="fichetitre">Parcours</div>%s
%s %s
</div>""" % (
        info["liste_inscriptions"],
        info["link_bul_pdf"],
        info["link_inscrire_ailleurs"],
    )

    #
    if info["groupes"].strip():
        info["groupes_row"] = (
            '<tr><td class="fichetitre2">Groupe :</td><td>%(groupes)s</td></tr>' % info
        )
    else:
        info["groupes_row"] = ""
    info["menus_etud"] = menus_etud(etudid)
    tmpl = """<div class="menus_etud">%(menus_etud)s</div>
<div class="ficheEtud" id="ficheEtud"><table>
<tr><td>
<h2>%(nomprenom)s (%(inscription)s)</h2>

<span>%(emaillink)s</span> 
</td><td class="photocell">
<a href="etud_photo_orig_page?etudid=%(etudid)s">%(etudfoto)s</a>
</td></tr></table>

<div class="fichesituation">
<div class="fichetablesitu">
<table>
<tr><td class="fichetitre2">Situation :</td><td>%(situation)s</td></tr>
%(groupes_row)s
<tr><td class="fichetitre2">Né%(ne)s le :</td><td>%(info_naissance)s</td></tr>
</table>


<!-- Adresse -->
<div class="ficheadresse" id="ficheadresse">
<table><tr>
<td class="fichetitre2">Adresse :</td><td> %(domicile)s %(codepostaldomicile)s %(villedomicile)s %(paysdomicile)s
%(modifadresse)s
%(telephones)s
</td></tr></table>
</div>
</div>
</div>

%(inscriptions_mkup)s

<div class="ficheadmission">
%(adm_data)s

%(fichiers_archive_htm)s
</div>

%(debouche_html)s

<div class="ficheannotations">
%(tit_anno)s
<table id="etudannotations">%(liste_annotations)s</table>

<form action="doAddAnnotation" method="GET" class="noprint">
<input type="hidden" name="etudid" value="%(etudid)s">
<b>Ajouter une annotation sur %(nomprenom)s: </b>
<table><tr>
<tr><td><textarea name="comment" rows="4" cols="50" value=""></textarea>
<br/><font size=-1>
<i>Ces annotations sont lisibles par tous les enseignants et le secrétariat.</i>
<br/>
<i>L'annotation commençant par "PE:" est un avis de poursuite d'études.</i>
</font>
</td></tr>
<tr><td>
 <input type="hidden" name="author" width=12 value="%(authuser)s">
<input type="submit" value="Ajouter annotation"></td></tr>
</table>
</form>
</div>

<div class="code_nip">code NIP: %(code_nip)s</div>

</div>
        """
    header = html_sco_header.sco_header(
        page_title="Fiche étudiant %(prenom)s %(nom)s" % info,
        cssstyles=["libjs/jQuery-tagEditor/jquery.tag-editor.css"],
        javascripts=[
            "libjs/jinplace-1.2.1.min.js",
            "js/ue_list.js",
            "libjs/jQuery-tagEditor/jquery.tag-editor.min.js",
            "libjs/jQuery-tagEditor/jquery.caret.min.js",
            "js/recap_parcours.js",
            "js/etud_debouche.js",
        ],
    )
    return header + tmpl % info + html_sco_header.sco_footer()


def menus_etud(etudid):
    """Menu etudiant (operations sur l'etudiant)"""
    authuser = current_user

    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]

    menuEtud = [
        {
            "title": etud["nomprenom"],
            "endpoint": "scolar.ficheEtud",
            "args": {"etudid": etud["etudid"]},
            "enabled": True,
            "helpmsg": "Fiche étudiant",
        },
        {
            "title": "Changer la photo",
            "endpoint": "scolar.formChangePhoto",
            "args": {"etudid": etud["etudid"]},
            "enabled": authuser.has_permission(Permission.ScoEtudChangeAdr),
        },
        {
            "title": "Changer les données identité/admission",
            "endpoint": "scolar.etudident_edit_form",
            "args": {"etudid": etud["etudid"]},
            "enabled": authuser.has_permission(Permission.ScoEtudInscrit),
        },
        {
            "title": "Supprimer cet étudiant...",
            "endpoint": "scolar.etudident_delete",
            "args": {"etudid": etud["etudid"]},
            "enabled": authuser.has_permission(Permission.ScoEtudInscrit),
        },
        {
            "title": "Voir le journal...",
            "endpoint": "scolar.showEtudLog",
            "args": {"etudid": etud["etudid"]},
            "enabled": True,
        },
    ]

    return htmlutils.make_menu("Etudiant", menuEtud, alone=True)


def etud_info_html(etudid, with_photo="1", debug=False):
    """An HTML div with basic information and links about this etud.
    Used for popups information windows.
    """
    formsemestre_id = sco_formsemestre_status.retreive_formsemestre_from_request()
    with_photo = int(with_photo)
    etud = sco_etud.get_etud_info(filled=True)[0]
    photo_html = sco_photos.etud_photo_html(etud, title="fiche de " + etud["nom"])
    # experimental: may be too slow to be here
    etud["codeparcours"], etud["decisions_jury"] = sco_report.get_codeparcoursetud(
        etud, prefix="S", separator=", "
    )

    bac = sco_bac.Baccalaureat(etud["bac"], etud["specialite"])
    etud["bac_abbrev"] = bac.abbrev()
    H = (
        """<div class="etud_info_div">
    <div class="eid_left">
     <div class="eid_nom"><div>%(nomprenom)s</div></div>
     <div class="eid_info eid_bac">Bac: <span class="eid_bac">%(bac_abbrev)s</span></div>
     <div class="eid_info eid_parcours">%(codeparcours)s</div>
    """
        % etud
    )

    # Informations sur l'etudiant dans le semestre courant:
    sem = None
    if formsemestre_id:  # un semestre est spécifié par la page
        sem = sco_formsemestre.get_formsemestre(formsemestre_id)
    elif etud["cursem"]:  # le semestre "en cours" pour l'étudiant
        sem = etud["cursem"]
    if sem:
        groups = sco_groups.get_etud_groups(etudid, sem)
        grc = sco_groups.listgroups_abbrev(groups)
        H += '<div class="eid_info">En <b>S%d</b>: %s</div>' % (sem["semestre_id"], grc)
    H += "</div>"  # fin partie gauche (eid_left)
    if with_photo:
        H += '<span class="eid_right">' + photo_html + "</span>"

    H += "</div>"
    if debug:
        return (
            html_sco_header.standard_html_header()
            + H
            + html_sco_header.standard_html_footer()
        )
    else:
        return H
