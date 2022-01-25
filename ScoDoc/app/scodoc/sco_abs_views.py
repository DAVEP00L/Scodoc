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

"""Pages HTML gestion absences
   (la plupart portées du DTML)
"""
import datetime

from flask import url_for, g, request

import app.scodoc.sco_utils as scu
from app.scodoc import notesdb as ndb
from app.scodoc.scolog import logdb
from app.scodoc.gen_tables import GenTable
from app.scodoc import html_sco_header
from app.scodoc import sco_abs
from app.scodoc import sco_cache
from app.scodoc import sco_etud
from app.scodoc import sco_find_etud
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_moduleimpl
from app.scodoc import sco_photos
from app.scodoc import sco_preferences
from app import log
from app.scodoc.sco_exceptions import ScoValueError


def doSignaleAbsence(
    datedebut,
    datefin,
    moduleimpl_id=None,
    demijournee=2,
    estjust=False,
    description=None,
    etudid=False,
):  # etudid implied
    """Signalement d'une absence.

    Args:
        datedebut: dd/mm/yyyy
        datefin: dd/mm/yyyy (non incluse)
        moduleimpl_id: module auquel imputer les absences
        demijournee: 2 si journée complète, 1 matin, 0 après-midi
        estjust: absence justifiée
        description: str
        etudid: etudiant concerné. Si non spécifié, cherche dans
        les paramètres de la requête courante.
    """
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    etudid = etud["etudid"]
    if not moduleimpl_id:
        moduleimpl_id = None
    description_abs = description
    dates = sco_abs.DateRangeISO(datedebut, datefin)
    nbadded = 0
    demijournee = int(demijournee)
    for jour in dates:
        if demijournee == 2:
            sco_abs.add_absence(
                etudid,
                jour,
                False,
                estjust,
                description_abs,
                moduleimpl_id,
            )
            sco_abs.add_absence(
                etudid,
                jour,
                True,
                estjust,
                description_abs,
                moduleimpl_id,
            )
            nbadded += 2
        else:
            sco_abs.add_absence(
                etudid,
                jour,
                demijournee,
                estjust,
                description_abs,
                moduleimpl_id,
            )
            nbadded += 1
    #
    if estjust:
        J = ""
    else:
        J = "NON "
    M = ""
    if moduleimpl_id and moduleimpl_id != "NULL":
        mod = sco_moduleimpl.moduleimpl_list(moduleimpl_id=moduleimpl_id)[0]
        formsemestre_id = mod["formsemestre_id"]
        nt = sco_cache.NotesTableCache.get(formsemestre_id)
        ues = nt.get_ues(etudid=etudid)
        for ue in ues:
            modimpls = nt.get_modimpls(ue_id=ue["ue_id"])
            for modimpl in modimpls:
                if modimpl["moduleimpl_id"] == moduleimpl_id:
                    M = "dans le module %s" % modimpl["module"]["code"]
    H = [
        html_sco_header.sco_header(
            page_title="Signalement d'une absence pour %(nomprenom)s" % etud,
        ),
        """<h2>Signalement d'absences</h2>""",
    ]
    if dates:
        H.append(
            """<p>Ajout de %d absences <b>%sjustifiées</b> du %s au %s %s</p>"""
            % (nbadded, J, datedebut, datefin, M)
        )
    else:
        H.append(
            """<p class="warning">Aucune date ouvrable entre le %s et le %s !</p>"""
            % (datedebut, datefin)
        )

    H.append(
        """<ul><li><a href="SignaleAbsenceEtud?etudid=%(etudid)s">Autre absence pour <b>%(nomprenom)s</b></a></li>
                    <li><a href="CalAbs?etudid=%(etudid)s">Calendrier de ses absences</a></li>
                </ul>
              <hr>"""
        % etud
    )
    H.append(sco_find_etud.form_search_etud())
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def SignaleAbsenceEtud():  # etudid implied
    """Formulaire individuel simple de signalement d'une absence"""
    # brute-force portage from very old dtml code ...
    etud = sco_etud.get_etud_info(filled=True)[0]
    etudid = etud["etudid"]
    disabled = False
    if not etud["cursem"]:
        require_module = sco_preferences.get_preference(
            "abs_require_module"
        )  # on utilise la pref globale car pas de sem courant
        if require_module:
            menu_module = """<div class="ue_warning">Pas inscrit dans un semestre courant, 
            et l'indication du module est requise. Donc pas de saisie d'absence possible !</div>"""
            disabled = True
        else:
            menu_module = ""
    else:
        formsemestre_id = etud["cursem"]["formsemestre_id"]
        require_module = sco_preferences.get_preference(
            "abs_require_module", formsemestre_id
        )
        nt = sco_cache.NotesTableCache.get(formsemestre_id)
        ues = nt.get_ues(etudid=etudid)
        if require_module:
            menu_module = """
            <script type="text/javascript">
            function form_enable_disable() {
                if ( $("select#sel_moduleimpl_id").val() == "" ) { 
                    $("#butsubmit").prop("disabled", true); 
                } else { 
                    $("#butsubmit").prop("disabled", false); 
                };
            }
            $(document).ready(function() {
                form_enable_disable();
            });
            </script>
            <p>Module: 
            <select id="sel_moduleimpl_id" name="moduleimpl_id"
            onChange="form_enable_disable();">"""
        else:
            menu_module = (
                """<p>Module: <select id="sel_moduleimpl_id" name="moduleimpl_id">"""
            )
        menu_module += """<option value="" selected>(Module)</option>"""

        for ue in ues:
            modimpls = nt.get_modimpls(ue_id=ue["ue_id"])
            for modimpl in modimpls:
                menu_module += (
                    """<option value="%(modimpl_id)s">%(modname)s</option>\n"""
                    % {
                        "modimpl_id": modimpl["moduleimpl_id"],
                        "modname": modimpl["module"]["code"],
                    }
                )
        menu_module += """</select></p>"""

    H = [
        html_sco_header.sco_header(
            page_title="Signalement d'une absence pour %(nomprenom)s" % etud,
        ),
        """<table><tr><td>
          <h2>Signalement d'une absence pour %(nomprenom)s</h2>
          </td><td>
          """
        % etud,
        """<a href="%s">"""
        % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etud["etudid"]),
        sco_photos.etud_photo_html(
            etudid=etudid,
            title="fiche de " + etud["nomprenom"],
        ),
        """</a></td></tr></table>""",
        """
<form action="doSignaleAbsence" method="get">
<input type="hidden" name="etudid" value="%(etudid)s">
<p>
<table><tr>
<td>Date début :  </td>
<td><input type="text" name="datedebut" size="10" class="datepicker"/> <em>j/m/a</em></td>
<td>&nbsp;&nbsp;&nbsp;Date fin (optionnelle):</td>
<td><input type="text" name="datefin" size="10" class="datepicker"/> <em>j/m/a</em></td>
</tr>
</table>
<br/>
<input type="radio" name="demijournee" value="2" checked>Journée(s)
&nbsp;<input type="radio" name="demijournee" value="1">Matin(s)
&nbsp;<input type="radio" name="demijournee" value="0">Après-midi

%(menu_module)s

<p>
<input type="checkbox" name="estjust"/>Absence justifiée.
<br/>
Raison: <input type="text" name="description" size="42"/> (optionnel)
</p>

<p>
<input id="butsubmit" type="submit" value="Envoyer" disable="%(disabled)s"/> 
<em>
 <p>Seuls les modules du semestre en cours apparaissent.</p>
 <p>Évitez de saisir une absence pour un module qui n'est pas en place à cette date.</p>
<p>Toutes les dates sont au format jour/mois/annee.</p>
</em>

</form> 
          """
        % {
            "etudid": etud["etudid"],
            "menu_module": menu_module,
            "disabled": "disabled" if disabled else "",
        },
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def doJustifAbsence(
    datedebut,
    datefin,
    demijournee,
    description=None,
    etudid=False,
):  # etudid implied
    """Justification d'une absence

    Args:
        datedebut: dd/mm/yyyy
        datefin: dd/mm/yyyy (non incluse)
        demijournee: 2 si journée complète, 1 matin, 0 après-midi
        estjust: absence justifiée
        description: str
        etudid: etudiant concerné. Si non spécifié, cherche dans les
        paramètres de la requête.
    """
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    etudid = etud["etudid"]
    description_abs = description
    dates = sco_abs.DateRangeISO(datedebut, datefin)
    nbadded = 0
    demijournee = int(demijournee)
    for jour in dates:
        if demijournee == 2:
            sco_abs.add_justif(
                etudid=etudid,
                jour=jour,
                matin=False,
                description=description_abs,
            )
            sco_abs.add_justif(
                etudid=etudid,
                jour=jour,
                matin=True,
                description=description_abs,
            )
            nbadded += 2
        else:
            sco_abs.add_justif(
                etudid=etudid,
                jour=jour,
                matin=demijournee,
                description=description_abs,
            )
            nbadded += 1
    #
    H = [
        html_sco_header.sco_header(
            page_title="Justification d'une absence pour %(nomprenom)s" % etud,
        ),
        """<h2>Justification d'absences</h2>""",
    ]
    if dates:
        H.append(
            """<p>Ajout de %d <b>justifications</b> du %s au %s</p>"""
            % (nbadded, datedebut, datefin)
        )
    else:
        H.append(
            """<p class="warning">Aucune date ouvrable entre le %s et le %s !</p>"""
            % (datedebut, datefin)
        )

    H.append(
        """<ul><li><a href="JustifAbsenceEtud?etudid=%(etudid)s">Autre justification pour <b>%(nomprenom)s</b></a></li>
<li><a href="SignaleAbsenceEtud?etudid=%(etudid)s">Signaler une absence</a></li>
<li><a href="CalAbs?etudid=%(etudid)s">Calendrier de ses absences</a></li>
<li><a href="ListeAbsEtud?etudid=%(etudid)s">Liste de ses absences</a></li>
</ul>
<hr>"""
        % etud
    )
    H.append(sco_find_etud.form_search_etud())
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def JustifAbsenceEtud():  # etudid implied
    """Formulaire individuel simple de justification d'une absence"""
    # brute-force portage from very old dtml code ...
    etud = sco_etud.get_etud_info(filled=True)[0]
    etudid = etud["etudid"]
    H = [
        html_sco_header.sco_header(
            page_title="Justification d'une absence pour %(nomprenom)s" % etud,
        ),
        """<table><tr><td>
          <h2>Justification d'une absence pour %(nomprenom)s</h2>
          </td><td>
          """
        % etud,
        """<a href="%s">"""
        % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
        sco_photos.etud_photo_html(
            etudid=etudid,
            title="fiche de " + etud["nomprenom"],
        ),
        """</a></td></tr></table>""",
        """
<form action="doJustifAbsence" method="get"> 
<input type="hidden" name="etudid" value="%(etudid)s">

<p>
<table><tr>
<td>Date d&eacute;but :  </td>
<td>
<input type="text" name="datedebut" size="10" class="datepicker"/>
</td>
<td>&nbsp;&nbsp;&nbsp;Date Fin (optionnel):</td>
<td><input type="text" name="datefin" size="10" class="datepicker"/></td>
</tr>
</table>
<br/>

<input type="radio" name="demijournee" value="2" checked>Journée(s)
&nbsp;<input type="radio" name="demijournee" value="1">Matin(s)
&nbsp;<input type="radio" name="demijournee" value="0">Apr&egrave;s midi

<br/><br/>
Raison: <input type="text" name="description" size="42"/> (optionnel)

<p>
<input type="submit" value="Envoyer"> 

</form> """
        % etud,
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def doAnnuleAbsence(datedebut, datefin, demijournee, etudid=False):  # etudid implied
    """Annulation des absences pour une demi journée"""
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    etudid = etud["etudid"]

    dates = sco_abs.DateRangeISO(datedebut, datefin)
    nbadded = 0
    demijournee = int(demijournee)
    for jour in dates:
        if demijournee == 2:
            sco_abs.annule_absence(etudid, jour, False)
            sco_abs.annule_absence(etudid, jour, True)
            nbadded += 2
        else:
            sco_abs.annule_absence(etudid, jour, demijournee)
            nbadded += 1
    #
    H = [
        html_sco_header.sco_header(
            page_title="Annulation d'une absence pour %(nomprenom)s" % etud,
        ),
        """<h2>Annulation d'absences pour %(nomprenom)s</h2>""" % etud,
    ]
    if dates:
        H.append(
            "<p>Annulation sur %d demi-journées du %s au %s"
            % (nbadded, datedebut, datefin)
        )
    else:
        H.append(
            """<p class="warning">Aucune date ouvrable entre le %s et le %s !</p>"""
            % (datedebut, datefin)
        )

    H.append(
        """<ul><li><a href="AnnuleAbsenceEtud?etudid=%(etudid)s">Annulation d'une
autre absence pour <b>%(nomprenom)s</b></a></li>
                    <li><a href="SignaleAbsenceEtud?etudid=%(etudid)s">Ajout d'une absence</a></li>
                    <li><a href="CalAbs?etudid=%(etudid)s">Calendrier de ses absences</a></li>
                </ul>
              <hr>"""
        % etud
    )
    H.append(sco_find_etud.form_search_etud())
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def AnnuleAbsenceEtud():  # etudid implied
    """Formulaire individuel simple d'annulation d'une absence"""
    # brute-force portage from very old dtml code ...
    etud = sco_etud.get_etud_info(filled=True)[0]
    etudid = etud["etudid"]

    H = [
        html_sco_header.sco_header(
            page_title="Annulation d'une absence pour %(nomprenom)s" % etud,
        ),
        """<table><tr><td>
          <h2><font color="#FF0000">Annulation</font> d'une absence pour %(nomprenom)s</h2>
          </td><td>
          """
        % etud,  #  "
        """<a href="%s">"""
        % url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
        sco_photos.etud_photo_html(
            etudid=etudid,
            title="fiche de " + etud["nomprenom"],
        ),
        """</a></td></tr></table>""",
        """<p>A n'utiliser que suite à une erreur de saisie ou lorsqu'il s'avère que l'étudiant était en fait présent. </p>
          <p><font color="#FF0000">Si plusieurs modules sont affectés, les absences seront toutes effacées. </font></p>
          """
        % etud,
        """<table frame="border" border="1"><tr><td>
<form action="doAnnuleAbsence" method="get"> 
<input type="hidden" name="etudid" value="%(etudid)s">
<p>
<table><tr>
<td>Date d&eacute;but :  </td>
<td>
<input type="text" name="datedebut" size="10" class="datepicker"/> <em>j/m/a</em>
</td>
<td>&nbsp;&nbsp;&nbsp;Date Fin (optionnel):</td>
<td>
<input type="text" name="datefin" size="10" class="datepicker"/> <em>j/m/a</em>
</td>
</tr>
</table>

<input type="radio" name="demijournee" value="2" checked>journ&eacute;e(s)
&nbsp;<input type="radio" name="demijournee" value="1">Matin(s)
&nbsp;<input type="radio" name="demijournee" value="0">Apr&egrave;s midi


<p>
<input type="submit" value="Supprimer les absences"> 
</form> 
</td></tr>

<tr><td>
<form action="doAnnuleJustif" method="get"> 
<input type="hidden" name="etudid" value="%(etudid)s">
<p>
<table><tr>
<td>Date d&eacute;but :  </td>
<td>
<input type="text" name="datedebut0" size="10" class="datepicker"/> <em>j/m/a</em>
</td>
<td>&nbsp;&nbsp;&nbsp;Date Fin (optionnel):</td>
<td>
<input type="text" name="datefin0" size="10" class="datepicker"/> <em>j/m/a</em>
</td>
</tr>
</table>
<p>

<input type="radio" name="demijournee" value="2" checked>journ&eacute;e(s)
&nbsp;<input type="radio" name="demijournee" value="1">Matin(s)
&nbsp;<input type="radio" name="demijournee" value="0">Apr&egrave;s midi


<p>
<input type="submit" value="Supprimer les justificatifs"> 
<i>(utiliser ceci en cas de justificatif erron&eacute; saisi ind&eacute;pendemment d'une absence)</i>
</form> 
</td></tr></table>"""
        % etud,
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def doAnnuleJustif(datedebut0, datefin0, demijournee):  # etudid implied
    """Annulation d'une justification"""
    etud = sco_etud.get_etud_info(filled=True)[0]
    etudid = etud["etudid"]
    dates = sco_abs.DateRangeISO(datedebut0, datefin0)
    nbadded = 0
    demijournee = int(demijournee)
    for jour in dates:
        # Attention: supprime matin et après-midi
        if demijournee == 2:
            sco_abs.annule_justif(etudid, jour, False)
            sco_abs.annule_justif(etudid, jour, True)
            nbadded += 2
        else:
            sco_abs.annule_justif(etudid, jour, demijournee)
            nbadded += 1
    #
    H = [
        html_sco_header.sco_header(
            page_title="Annulation d'une justification pour %(nomprenom)s" % etud,
        ),
        """<h2>Annulation de justifications pour %(nomprenom)s</h2>""" % etud,
    ]

    if dates:
        H.append(
            "<p>Annulation sur %d demi-journées du %s au %s"
            % (nbadded, datedebut0, datefin0)
        )
    else:
        H.append(
            """<p class="warning">Aucune date ouvrable entre le %s et le %s !</p>"""
            % (datedebut0, datefin0)
        )
    H.append(
        """<ul><li><a href="AnnuleAbsenceEtud?etudid=%(etudid)s">Annulation d'une
autre absence pour <b>%(nomprenom)s</b></a></li>
                    <li><a href="SignaleAbsenceEtud?etudid=%(etudid)s">Ajout d'une absence</a></li>
                    <li><a href="CalAbs?etudid=%(etudid)s">Calendrier de ses absences</a></li>
                </ul>
              <hr>"""
        % etud
    )
    H.append(sco_find_etud.form_search_etud())
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def AnnuleAbsencesDatesNoJust(etudid, dates, moduleimpl_id=None):
    """Supprime les absences non justifiées aux dates indiquées
    Ne supprime pas les justificatifs éventuels.
    Args:
        etudid: l'étudiant
        dates: liste de dates iso, eg [ "2000-01-15", "2000-01-16" ]
        moduleimpl_id: si spécifié, n'affecte que les absences de ce module

    Returns:
        None
    """
    # log('AnnuleAbsencesDatesNoJust: moduleimpl_id=%s' % moduleimpl_id)
    if not dates:
        return
    date0 = dates[0]
    if len(date0.split(":")) == 2:
        # am/pm is present
        for date in dates:
            jour, ampm = date.split(":")
            if ampm == "am":
                matin = 1
            elif ampm == "pm":
                matin = 0
            else:
                raise ValueError("invalid ampm !")
            sco_abs.annule_absence(etudid, jour, matin, moduleimpl_id)
        return
    cnx = ndb.GetDBConnexion()
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    # supr les absences non justifiees
    for date in dates:
        cursor.execute(
            """DELETE FROM absences 
            WHERE etudid=%(etudid)s and (not estjust) and jour=%(date)s and moduleimpl_id=%(moduleimpl_id)s
            """,
            vars(),
        )
        sco_abs.invalidate_abs_etud_date(etudid, date)
    # s'assure que les justificatifs ne sont pas "absents"
    for date in dates:
        cursor.execute(
            """UPDATE absences SET estabs=FALSE 
            WHERE etudid=%(etudid)s AND jour=%(date)s AND moduleimpl_id=%(moduleimpl_id)s
            """,
            vars(),
        )
    if dates:
        date0 = dates[0]
    else:
        date0 = None
    if len(dates) > 1:
        date1 = dates[1]
    else:
        date1 = None
    logdb(
        cnx,
        "AnnuleAbsencesDatesNoJust",
        etudid=etudid,
        msg="%s - %s - %s" % (date0, date1, moduleimpl_id),
    )
    cnx.commit()


def EtatAbsences():
    """Etat des absences: choix du groupe"""
    # crude portage from 1999 DTML
    H = [
        html_sco_header.sco_header(page_title="Etat des absences"),
        """<h2>État des absences pour un groupe</h2>
<form action="EtatAbsencesGr" method="GET">""",
        formChoixSemestreGroupe(),
        """<input type="submit" name="" value=" OK " width=100>

<table><tr><td>Date de début (j/m/a) : </td><td>

<input type="text" name="debut" size="10" value="01/09/%s" class="datepicker"/>

</td></tr><tr><td>Date de fin : </td><td>

<input type="text" name="fin" size="10" value="%s" class="datepicker"/>

</td></tr></table>
</form>"""
        % (scu.AnneeScolaire(), datetime.datetime.now().strftime("%d/%m/%Y")),
        html_sco_header.sco_footer(),
    ]
    return "\n".join(H)


def formChoixSemestreGroupe(all=False):
    """partie de formulaire pour le choix d'un semestre et d'un groupe.
    Si all, donne tous les semestres (même ceux verrouillés).
    """
    # XXX assez primitif, à ameliorer TOTALEMENT OBSOLETE !
    if all:
        sems = sco_formsemestre.do_formsemestre_list()
    else:
        sems = sco_formsemestre.do_formsemestre_list(args={"etat": "1"})
    if not sems:
        raise ScoValueError("aucun semestre !")
    H = ['<select  name="group_ids">']
    for sem in sems:
        for p in sco_groups.get_partitions_list(sem["formsemestre_id"]):
            for group in sco_groups.get_partition_groups(p):
                if group["group_name"]:
                    group_tit = "%s %s" % (p["partition_name"], group["group_name"])
                else:
                    group_tit = "tous"
                H.append(
                    '<option value="%s">%s: %s</option>'
                    % (group["group_id"], sem["titremois"], group_tit)
                )

    H.append("</select>")
    return "\n".join(H)


def CalAbs(etudid, sco_year=None):
    """Calendrier des absences d'un etudiant"""
    # crude portage from 1999 DTML
    etud = sco_etud.get_etud_info(filled=True, etudid=etudid)[0]
    etudid = etud["etudid"]
    anneescolaire = int(scu.AnneeScolaire(sco_year))
    datedebut = str(anneescolaire) + "-08-01"
    datefin = str(anneescolaire + 1) + "-07-31"
    nbabs = sco_abs.count_abs(etudid=etudid, debut=datedebut, fin=datefin)
    nbabsjust = sco_abs.count_abs_just(etudid=etudid, debut=datedebut, fin=datefin)
    events = []
    for a in sco_abs.list_abs_just(etudid=etudid, datedebut=datedebut):
        events.append(
            (str(a["jour"]), "a", "#F8B7B0", "", a["matin"], a["description"])
        )
    for a in sco_abs.list_abs_non_just(etudid=etudid, datedebut=datedebut):
        events.append(
            (str(a["jour"]), "A", "#EE0000", "", a["matin"], a["description"])
        )
    justifs_noabs = sco_abs.list_abs_justifs(
        etudid=etudid, datedebut=datedebut, only_no_abs=True
    )
    for a in justifs_noabs:
        events.append(
            (str(a["jour"]), "X", "#8EA2C6", "", a["matin"], a["description"])
        )
    CalHTML = sco_abs.YearTable(anneescolaire, events=events, halfday=1)

    #
    H = [
        html_sco_header.sco_header(
            page_title="Calendrier des absences de %(nomprenom)s" % etud,
            cssstyles=["css/calabs.css"],
        ),
        """<table><tr><td><h2>Absences de %(nomprenom)s (%(inscription)s)</h2><p>"""
        % etud,
        """<b><font color="#EE0000">A : absence NON justifiée</font><br/>
             <font color="#F8B7B0">a : absence justifiée</font><br/>
             <font color="#8EA2C6">X : justification sans absence</font><br/>
             %d absences sur l'année, dont %d justifiées (soit %d non justifiées)</b> <em>(%d justificatifs inutilisés)</em>
          </p>
           """
        % (nbabs, nbabsjust, nbabs - nbabsjust, len(justifs_noabs)),
        """</td>
<td><a href="%s">%s</a></td>
</tr>
</table>"""
        % (
            url_for("scolar.ficheEtud", scodoc_dept=g.scodoc_dept, etudid=etudid),
            sco_photos.etud_photo_html(
                etudid=etudid,
                title="fiche de " + etud["nomprenom"],
            ),
        ),
        CalHTML,
        """<form method="GET" action="CalAbs" name="f">""",
        """<input type="hidden" name="etudid" value="%s"/>""" % etudid,
        """Année scolaire %s-%s""" % (anneescolaire, anneescolaire + 1),
        """&nbsp;&nbsp;Changer année: <select name="sco_year" onchange="document.f.submit()">""",
    ]
    for y in range(anneescolaire, anneescolaire - 10, -1):
        H.append("""<option value="%s" """ % y)
        if y == anneescolaire:
            H.append("selected")
        H.append(""">%s</option>""" % y)
    H.append("""</select></form>""")
    H.append(html_sco_header.sco_footer())
    return "\n".join(H)


def ListeAbsEtud(
    etudid,
    with_evals=True,
    format="html",
    absjust_only=0,
    sco_year=None,
):
    """Liste des absences d'un étudiant sur l'année en cours
    En format 'html': page avec deux tableaux (non justifiées et justifiées).
    En format json, xml, xls ou pdf: l'un ou l'autre des table, suivant absjust_only.
    En format 'text': texte avec liste d'absences (pour mails).

    Args:
        etudid:
        with_evals: indique les evaluations aux dates d'absences
        absjust_only: si vrai, renvoie table absences justifiées
        sco_year: année scolaire à utiliser. Si non spécifier, utilie l'année en cours. e.g. "2005"
    """
    # si absjust_only, table absjust seule (export xls ou pdf)
    absjust_only = ndb.bool_or_str(absjust_only)
    datedebut = "%s-08-01" % scu.AnneeScolaire(sco_year=sco_year)

    etud = sco_etud.get_etud_info(etudid=etudid, filled=True)[0]

    # Liste des absences et titres colonnes tables:
    titles, columns_ids, absnonjust, absjust = _tables_abs_etud(
        etudid, datedebut, with_evals=with_evals, format=format
    )
    if request.base_url:
        base_url_nj = "%s?etudid=%s&absjust_only=0" % (request.base_url, etudid)
        base_url_j = "%s?etudid=%s&absjust_only=1" % (request.base_url, etudid)
    else:
        base_url_nj = base_url_j = ""
    tab_absnonjust = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=absnonjust,
        html_class="table_leftalign",
        table_id="tab_absnonjust",
        base_url=base_url_nj,
        filename="abs_" + scu.make_filename(etud["nomprenom"]),
        caption="Absences non justifiées de %(nomprenom)s" % etud,
        preferences=sco_preferences.SemPreferences(),
    )
    tab_absjust = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=absjust,
        html_class="table_leftalign",
        table_id="tab_absjust",
        base_url=base_url_j,
        filename="absjust_" + scu.make_filename(etud["nomprenom"]),
        caption="Absences justifiées de %(nomprenom)s" % etud,
        preferences=sco_preferences.SemPreferences(),
    )

    # Formats non HTML et demande d'une seule table:
    if format != "html" and format != "text":
        if absjust_only == 1:
            return tab_absjust.make_page(format=format)
        else:
            return tab_absnonjust.make_page(format=format)

    if format == "html":
        # Mise en forme HTML:
        H = []
        H.append(
            html_sco_header.sco_header(page_title="Absences de %s" % etud["nomprenom"])
        )
        H.append(
            """<h2>Absences de %s (à partir du %s)</h2>"""
            % (etud["nomprenom"], ndb.DateISOtoDMY(datedebut))
        )

        if len(absnonjust):
            H.append("<h3>%d absences non justifiées:</h3>" % len(absnonjust))
            H.append(tab_absnonjust.html())
        else:
            H.append("""<h3>Pas d'absences non justifiées</h3>""")

        if len(absjust):
            H.append("""<h3>%d absences justifiées:</h3>""" % len(absjust))
            H.append(tab_absjust.html())
        else:
            H.append("""<h3>Pas d'absences justifiées</h3>""")
        return "\n".join(H) + html_sco_header.sco_footer()

    elif format == "text":
        T = []
        if not len(absnonjust) and not len(absjust):
            T.append(
                """--- Pas d'absences enregistrées depuis le %s"""
                % ndb.DateISOtoDMY(datedebut)
            )
        else:
            T.append(
                """--- Absences enregistrées à partir du %s:"""
                % ndb.DateISOtoDMY(datedebut)
            )
            T.append("\n")
        if len(absnonjust):
            T.append("* %d absences non justifiées:" % len(absnonjust))
            T.append(tab_absnonjust.text())
        if len(absjust):
            T.append("* %d absences justifiées:" % len(absjust))
            T.append(tab_absjust.text())
        return "\n".join(T)
    else:
        raise ValueError("Invalid format !")


def _tables_abs_etud(
    etudid,
    datedebut,
    with_evals=True,
    format="html",
    absjust_only=0,
):
    """Tables des absences justifiees et non justifiees d'un étudiant
    sur l'année en cours
    """
    absjust = sco_abs.list_abs_just(etudid=etudid, datedebut=datedebut)
    absnonjust = sco_abs.list_abs_non_just(etudid=etudid, datedebut=datedebut)
    # examens ces jours là ?
    if with_evals:
        cnx = ndb.GetDBConnexion()
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        for a in absnonjust + absjust:
            cursor.execute(
                """SELECT eval.*
            FROM notes_evaluation eval, notes_moduleimpl_inscription mi, notes_moduleimpl m
            WHERE eval.jour = %(jour)s 
            and eval.moduleimpl_id = m.id
            and mi.moduleimpl_id = m.id 
            and mi.etudid = %(etudid)s
            """,
                {"jour": a["jour"].strftime("%Y-%m-%d"), "etudid": etudid},
            )
            a["evals"] = cursor.dictfetchall()
            cursor.execute(
                """SELECT mi.moduleimpl_id
            FROM  absences abs, notes_moduleimpl_inscription mi, notes_moduleimpl m
            WHERE abs.matin = %(matin)s
            and abs.jour = %(jour)s
            and abs.etudid = %(etudid)s
            and abs.moduleimpl_id = mi.moduleimpl_id
            and mi.moduleimpl_id = m.id
            and mi.etudid = %(etudid)s
            """,
                {
                    "matin": bool(a["matin"]),
                    "jour": a["jour"].strftime("%Y-%m-%d"),
                    "etudid": etudid,
                },
            )
            a["absent"] = cursor.dictfetchall()

    def matin(x):
        if x:
            return "matin"
        else:
            return "après-midi"

    def descr_exams(a):
        if "evals" not in a:
            return ""
        ex = []
        for ev in a["evals"]:
            mod = sco_moduleimpl.moduleimpl_withmodule_list(
                moduleimpl_id=ev["moduleimpl_id"]
            )[0]
            if format == "html":
                ex.append(
                    f"""<a href="{url_for('notes.moduleimpl_status', 
                        scodoc_dept=g.scodoc_dept, moduleimpl_id=mod["moduleimpl_id"])}
                        ">{mod["module"]["code"]}</a>"""
                )
            else:
                ex.append(mod["module"]["code"])
        if ex:
            return ", ".join(ex)
        return ""

    def descr_abs(a):
        ex = []
        for ev in a.get("absent", []):
            mod = sco_moduleimpl.moduleimpl_withmodule_list(
                moduleimpl_id=ev["moduleimpl_id"]
            )[0]
            if format == "html":
                ex.append(
                    f"""<a href="{url_for('notes.moduleimpl_status', 
                        scodoc_dept=g.scodoc_dept, moduleimpl_id=mod["moduleimpl_id"])}
                        ">{mod["module"]["code"]}</a>"""
                )
            else:
                ex.append(mod["module"]["code"])
        if ex:
            return ", ".join(ex)
        return ""

    # ajoute date formatée et évaluations
    for L in (absnonjust, absjust):
        for a in L:
            if with_evals:
                a["exams"] = descr_exams(a)
            a["datedmy"] = a["jour"].strftime("%d/%m/%Y")
            a["ampm"] = int(a["matin"])
            a["matin"] = matin(a["matin"])
            index = a["description"].find(")")
            if index != -1:
                a["motif"] = a["description"][1:index]
            else:
                a["motif"] = ""
            a["description"] = descr_abs(a) or ""

    # ajoute lien pour justifier
    if format == "html":
        for a in absnonjust:
            a["justlink"] = "<em>justifier</em>"
            a[
                "_justlink_target"
            ] = "doJustifAbsence?etudid=%s&datedebut=%s&datefin=%s&demijournee=%s" % (
                etudid,
                a["datedmy"],
                a["datedmy"],
                a["ampm"],
            )
    #
    titles = {
        "datedmy": "Date",
        "matin": "",
        "exams": "Examens ce jour",
        "justlink": "",
        "description": "Modules",
        "motif": "Motif",
    }
    columns_ids = ["datedmy", "matin"]
    if format in ("json", "xml"):
        columns_ids += ["jour", "ampm"]
    if with_evals:
        columns_ids.append("exams")

    columns_ids.append("description")
    columns_ids.append("motif")
    if format == "html":
        columns_ids.append("justlink")

    return titles, columns_ids, absnonjust, absjust
