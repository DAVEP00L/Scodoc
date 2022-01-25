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

""" Importation des étudiants à partir de fichiers CSV
"""

import collections
import io
import os
import re
import time
from datetime import date

from flask import g, url_for

import app.scodoc.sco_utils as scu
import app.scodoc.notesdb as ndb
from app import log
from app.scodoc.sco_excel import COLORS
from app.scodoc.sco_formsemestre_inscriptions import (
    do_formsemestre_inscription_with_modules,
)
from app.scodoc.gen_tables import GenTable
from app.scodoc.sco_exceptions import (
    AccessDenied,
    FormatError,
    ScoException,
    ScoValueError,
    ScoInvalidDateError,
    ScoLockedFormError,
    ScoGenError,
)
from app.scodoc import html_sco_header
from app.scodoc import sco_cache
from app.scodoc import sco_etud
from app.scodoc import sco_formsemestre
from app.scodoc import sco_groups
from app.scodoc import sco_excel
from app.scodoc import sco_groups_view
from app.scodoc import sco_news
from app.scodoc import sco_preferences

# format description (in tools/)
FORMAT_FILE = "format_import_etudiants.txt"

# Champs modifiables via "Import données admission"
ADMISSION_MODIFIABLE_FIELDS = (
    "code_nip",
    "code_ine",
    "date_naissance",
    "lieu_naissance",
    "bac",
    "specialite",
    "annee_bac",
    "math",
    "physique",
    "anglais",
    "francais",
    "type_admission",
    "boursier_prec",
    "qualite",
    "rapporteur",
    "score",
    "commentaire",
    "classement",
    "apb_groupe",
    "apb_classement_gr",
    "nomlycee",
    "villelycee",
    "codepostallycee",
    "codelycee",
    # Adresse:
    "email",
    "emailperso",
    "domicile",
    "codepostaldomicile",
    "villedomicile",
    "paysdomicile",
    "telephone",
    "telephonemobile",
    # Groupes
    "groupes",
)

# ----


def sco_import_format(with_codesemestre=True):
    "returns tuples (Attribut, Type, Table, AllowNulls, Description)"
    r = []
    for l in open(os.path.join(scu.SCO_TOOLS_DIR, FORMAT_FILE)):
        l = l.strip()
        if l and l[0] != "#":
            fs = l.split(";")
            if len(fs) < 5:
                # Bug: invalid format file (fatal)
                raise ScoException(
                    "file %s has invalid format (expected %d fields, got %d) (%s)"
                    % (FORMAT_FILE, 5, len(fs), l)
                )
            fieldname = (
                fs[0].strip().lower().split()[0]
            )  # titre attribut: normalize, 1er mot seulement (nom du champ en BD)
            typ, table, allow_nulls, description = [x.strip() for x in fs[1:5]]
            aliases = [x.strip() for x in fs[5:] if x.strip()]
            if fieldname not in aliases:
                aliases.insert(0, fieldname)  # prepend
            if with_codesemestre or fs[0] != "codesemestre":
                r.append((fieldname, typ, table, allow_nulls, description, aliases))
    return r


def sco_import_format_dict(with_codesemestre=True):
    """Attribut: { 'type': , 'table', 'allow_nulls' , 'description' }"""
    fmt = sco_import_format(with_codesemestre=with_codesemestre)
    R = collections.OrderedDict()
    for l in fmt:
        R[l[0]] = {
            "type": l[1],
            "table": l[2],
            "allow_nulls": l[3],
            "description": l[4],
            "aliases": l[5],
        }
    return R


def sco_import_generate_excel_sample(
    fmt,
    with_codesemestre=True,
    only_tables=None,
    with_groups=True,
    exclude_cols=[],
    extra_cols=[],
    group_ids=[],
):
    """Generates an excel document based on format fmt
    (format is the result of sco_import_format())
    If not None, only_tables can specify a list of sql table names
    (only columns from these tables will be generated)
    If group_ids, liste les etudiants de ces groupes
    """
    style = sco_excel.excel_make_style(bold=True)
    style_required = sco_excel.excel_make_style(bold=True, color=COLORS.RED)
    titles = []
    titlesStyles = []
    for l in fmt:
        name = l[0].lower()
        if (not with_codesemestre) and name == "codesemestre":
            continue  # pas de colonne codesemestre
        if only_tables is not None and l[2].lower() not in only_tables:
            continue  # table non demandée
        if name in exclude_cols:
            continue  # colonne exclue
        if int(l[3]):
            titlesStyles.append(style)
        else:
            titlesStyles.append(style_required)
        titles.append(name)
    if with_groups and "groupes" not in titles:
        titles.append("groupes")
        titlesStyles.append(style)
    titles += extra_cols
    titlesStyles += [style] * len(extra_cols)
    if group_ids:
        groups_infos = sco_groups_view.DisplayedGroupsInfos(group_ids)
        members = groups_infos.members
        log(
            "sco_import_generate_excel_sample: group_ids=%s  %d members"
            % (group_ids, len(members))
        )
        titles = ["etudid"] + titles
        titlesStyles = [style] + titlesStyles
        # rempli table avec données actuelles
        lines = []
        for i in members:
            etud = sco_etud.get_etud_info(etudid=i["etudid"], filled=True)[0]
            l = []
            for field in titles:
                if field == "groupes":
                    sco_groups.etud_add_group_infos(
                        etud, groups_infos.formsemestre, sep=";"
                    )
                    l.append(etud["partitionsgroupes"])
                else:
                    key = field.lower().split()[0]
                    l.append(etud.get(key, ""))
            lines.append(l)
    else:
        lines = [[]]  # empty content, titles only
    return sco_excel.excel_simple_table(
        titles=titles, titles_styles=titlesStyles, sheet_name="Etudiants", lines=lines
    )


def students_import_excel(
    csvfile,
    formsemestre_id=None,
    check_homonyms=True,
    require_ine=False,
    return_html=True,
):
    "import students from Excel file"
    diag = scolars_import_excel_file(
        csvfile,
        formsemestre_id=formsemestre_id,
        check_homonyms=check_homonyms,
        require_ine=require_ine,
        exclude_cols=["photo_filename"],
    )
    if return_html:
        if formsemestre_id:
            dest = url_for(
                "notes.formsemestre_status",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
            )
        else:
            dest = url_for("notes.index_html", scodoc_dept=g.scodoc_dept)
        H = [html_sco_header.sco_header(page_title="Import etudiants")]
        H.append("<ul>")
        for d in diag:
            H.append("<li>%s</li>" % d)
        H.append("</ul>")
        H.append("<p>Import terminé !</p>")
        H.append('<p><a class="stdlink" href="%s">Continuer</a></p>' % dest)
        return "\n".join(H) + html_sco_header.sco_footer()


def scolars_import_excel_file(
    datafile: io.BytesIO,
    formsemestre_id=None,
    check_homonyms=True,
    require_ine=False,
    exclude_cols=[],
):
    """Importe etudiants depuis fichier Excel
    et les inscrit dans le semestre indiqué (et à TOUS ses modules)
    """
    log("scolars_import_excel_file: formsemestre_id=%s" % formsemestre_id)
    cnx = ndb.GetDBConnexion(autocommit=False)
    cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
    annee_courante = time.localtime()[0]
    always_require_ine = sco_preferences.get_preference("always_require_ine")
    exceldata = datafile.read()
    if not exceldata:
        raise ScoValueError("Ficher excel vide ou invalide")
    diag, data = sco_excel.excel_bytes_to_list(exceldata)
    if not data:  # probably a bug
        raise ScoException("scolars_import_excel_file: empty file !")

    formsemestre_to_invalidate = set()
    # 1-  --- check title line
    titles = {}
    fmt = sco_import_format()
    for l in fmt:
        tit = l[0].lower().split()[0]  # titles in lowercase, and take 1st word
        if (
            (not formsemestre_id) or (tit != "codesemestre")
        ) and tit not in exclude_cols:
            titles[tit] = l[1:]  # title : (Type, Table, AllowNulls, Description)

    # log("titles=%s" % titles)
    # remove quotes, downcase and keep only 1st word
    try:
        fs = [scu.stripquotes(s).lower().split()[0] for s in data[0]]
    except:
        raise ScoValueError("Titres de colonnes invalides (ou vides ?)")
    # log("excel: fs='%s'\ndata=%s" % (str(fs), str(data)))

    # check columns titles
    if len(fs) != len(titles):
        missing = {}.fromkeys(list(titles.keys()))
        unknown = []
        for f in fs:
            if f in missing:
                del missing[f]
            else:
                unknown.append(f)
        raise ScoValueError(
            "Nombre de colonnes incorrect (devrait être %d, et non %d) <br/> (colonnes manquantes: %s, colonnes invalides: %s)"
            % (len(titles), len(fs), list(missing.keys()), unknown)
        )
    titleslist = []
    for t in fs:
        if t not in titles:
            raise ScoValueError('Colonne invalide: "%s"' % t)
        titleslist.append(t)  #
    # ok, same titles
    # Start inserting data, abort whole transaction in case of error
    created_etudids = []
    NbImportedHomonyms = 0
    GroupIdInferers = {}
    try:  # --- begin DB transaction
        linenum = 0
        for line in data[1:]:
            linenum += 1
            # Read fields, check and convert type
            values = {}
            fs = line
            # remove quotes
            for i in range(len(fs)):
                if fs[i] and (
                    (fs[i][0] == '"' and fs[i][-1] == '"')
                    or (fs[i][0] == "'" and fs[i][-1] == "'")
                ):
                    fs[i] = fs[i][1:-1]
            for i in range(len(fs)):
                val = fs[i].strip()
                typ, table, an, descr, aliases = tuple(titles[titleslist[i]])
                # log('field %s: %s %s %s %s'%(titleslist[i], table, typ, an, descr))
                if not val and not an:
                    raise ScoValueError(
                        "line %d: null value not allowed in column %s"
                        % (linenum, titleslist[i])
                    )
                if val == "":
                    val = None
                else:
                    if typ == "real":
                        val = val.replace(",", ".")  # si virgule a la française
                        try:
                            val = float(val)
                        except:
                            raise ScoValueError(
                                "valeur nombre reel invalide (%s) sur line %d, colonne %s"
                                % (val, linenum, titleslist[i])
                            )
                    elif typ == "integer":
                        try:
                            # on doit accepter des valeurs comme "2006.0"
                            val = val.replace(",", ".")  # si virgule a la française
                            val = float(val)
                            if val % 1.0 > 1e-4:
                                raise ValueError()
                            val = int(val)
                        except:
                            raise ScoValueError(
                                "valeur nombre entier invalide (%s) sur ligne %d, colonne %s"
                                % (val, linenum, titleslist[i])
                            )
                # xxx Ad-hoc checks (should be in format description)
                if titleslist[i].lower() == "sexe":
                    try:
                        val = sco_etud.input_civilite(val)
                    except:
                        raise ScoValueError(
                            "valeur invalide pour 'SEXE' (doit etre 'M', 'F', ou 'MME', 'H', 'X' ou vide, mais pas '%s') ligne %d, colonne %s"
                            % (val, linenum, titleslist[i])
                        )
                # Excel date conversion:
                if titleslist[i].lower() == "date_naissance":
                    if val:
                        try:
                            val = sco_excel.xldate_as_datetime(val)
                        except ValueError:
                            raise ScoValueError(
                                f"date invalide ({val}) sur ligne {linenum}, colonne {titleslist[i]}"
                            )
                # INE
                if (
                    titleslist[i].lower() == "code_ine"
                    and always_require_ine
                    and not val
                ):
                    raise ScoValueError(
                        "Code INE manquant sur ligne %d, colonne %s"
                        % (linenum, titleslist[i])
                    )

                # --
                values[titleslist[i]] = val
            skip = False
            is_new_ine = values["code_ine"] and _is_new_ine(cnx, values["code_ine"])
            if require_ine and not is_new_ine:
                log("skipping %s (code_ine=%s)" % (values["nom"], values["code_ine"]))
                skip = True

            if not skip:
                if values["code_ine"] and not is_new_ine:
                    raise ScoValueError("Code INE dupliqué (%s)" % values["code_ine"])
                # Check nom/prenom
                ok, NbHomonyms = sco_etud.check_nom_prenom(
                    cnx, nom=values["nom"], prenom=values["prenom"]
                )
                if not ok:
                    raise ScoValueError(
                        "nom ou prénom invalide sur la ligne %d" % (linenum)
                    )
                if NbHomonyms:
                    NbImportedHomonyms += 1
                # Insert in DB tables
                formsemestre_id_etud = _import_one_student(
                    cnx,
                    formsemestre_id,
                    values,
                    GroupIdInferers,
                    annee_courante,
                    created_etudids,
                    linenum,
                )

        # Verification proportion d'homonymes: si > 10%, abandonne
        log("scolars_import_excel_file: detected %d homonyms" % NbImportedHomonyms)
        if check_homonyms and NbImportedHomonyms > len(created_etudids) / 10:
            log("scolars_import_excel_file: too many homonyms")
            raise ScoValueError(
                "Il y a trop d'homonymes (%d étudiants)" % NbImportedHomonyms
            )
    except:
        cnx.rollback()
        log("scolars_import_excel_file: aborting transaction !")
        # Nota: db transaction is sometimes partly commited...
        # here we try to remove all created students
        cursor = cnx.cursor(cursor_factory=ndb.ScoDocCursor)
        for etudid in created_etudids:
            log("scolars_import_excel_file: deleting etudid=%s" % etudid)
            cursor.execute(
                "delete from notes_moduleimpl_inscription where etudid=%(etudid)s",
                {"etudid": etudid},
            )
            cursor.execute(
                "delete from notes_formsemestre_inscription where etudid=%(etudid)s",
                {"etudid": etudid},
            )
            cursor.execute(
                "delete from scolar_events where etudid=%(etudid)s", {"etudid": etudid}
            )
            cursor.execute(
                "delete from adresse where etudid=%(etudid)s", {"etudid": etudid}
            )
            cursor.execute(
                "delete from admissions where etudid=%(etudid)s", {"etudid": etudid}
            )
            cursor.execute(
                "delete from group_membership where etudid=%(etudid)s",
                {"etudid": etudid},
            )
            cursor.execute(
                "delete from identite where id=%(etudid)s", {"etudid": etudid}
            )
        cnx.commit()
        log("scolars_import_excel_file: re-raising exception")
        raise

    diag.append("Import et inscription de %s étudiants" % len(created_etudids))

    sco_news.add(
        typ=sco_news.NEWS_INSCR,
        text="Inscription de %d étudiants"  # peuvent avoir ete inscrits a des semestres differents
        % len(created_etudids),
        object=formsemestre_id,
    )

    log("scolars_import_excel_file: completing transaction")
    cnx.commit()

    # Invalide les caches des semestres dans lesquels on a inscrit des etudiants:
    for formsemestre_id in formsemestre_to_invalidate:
        sco_cache.invalidate_formsemestre(formsemestre_id=formsemestre_id)

    return diag


def students_import_admission(
    csvfile, type_admission="", formsemestre_id=None, return_html=True
):
    "import donnees admission from Excel file (v2016)"
    diag = scolars_import_admission(
        csvfile,
        formsemestre_id=formsemestre_id,
        type_admission=type_admission,
    )
    if return_html:
        H = [html_sco_header.sco_header(page_title="Import données admissions")]
        H.append("<p>Import terminé !</p>")
        H.append(
            '<p><a class="stdlink" href="%s">Continuer</a></p>'
            % url_for(
                "notes.formsemestre_status",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
            )
        )
        if diag:
            H.append("<p>Diagnostic: <ul><li>%s</li></ul></p>" % "</li><li>".join(diag))

        return "\n".join(H) + html_sco_header.sco_footer()


def _import_one_student(
    cnx,
    formsemestre_id,
    values,
    GroupIdInferers,
    annee_courante,
    created_etudids,
    linenum,
) -> int:
    """
    Import d'un étudiant et inscription dans le semestre.
    Return: id du semestre dans lequel il a été inscrit.
    """
    log(
        "scolars_import_excel_file: formsemestre_id=%s values=%s"
        % (formsemestre_id, str(values))
    )
    # Identite
    args = values.copy()
    etudid = sco_etud.identite_create(cnx, args)
    created_etudids.append(etudid)
    # Admissions
    args["etudid"] = etudid
    args["annee"] = annee_courante
    _ = sco_etud.admission_create(cnx, args)
    # Adresse
    args["typeadresse"] = "domicile"
    args["description"] = "(infos admission)"
    _ = sco_etud.adresse_create(cnx, args)
    # Inscription au semestre
    args["etat"] = "I"  # etat insc. semestre
    if formsemestre_id:
        args["formsemestre_id"] = formsemestre_id
    else:
        args["formsemestre_id"] = values["codesemestre"]
        formsemestre_id = values["codesemestre"]
    try:
        formsemestre_id = int(formsemestre_id)
    except ValueError as exc:
        raise ScoValueError(
            f"valeur invalide dans la colonne codesemestre, ligne {linenum+1}"
        ) from exc
    # recupere liste des groupes:
    if formsemestre_id not in GroupIdInferers:
        GroupIdInferers[formsemestre_id] = sco_groups.GroupIdInferer(formsemestre_id)
    gi = GroupIdInferers[formsemestre_id]
    if args["groupes"]:
        groupes = args["groupes"].split(";")
    else:
        groupes = []
    group_ids = [gi[group_name] for group_name in groupes]
    group_ids = list({}.fromkeys(group_ids).keys())  # uniq
    if None in group_ids:
        raise ScoValueError(
            "groupe invalide sur la ligne %d (groupe %s)" % (linenum, groupes)
        )

    do_formsemestre_inscription_with_modules(
        int(args["formsemestre_id"]),
        etudid,
        group_ids,
        etat="I",
        method="import_csv_file",
    )
    return args["formsemestre_id"]


def _is_new_ine(cnx, code_ine):
    "True if this code is not in DB"
    etuds = sco_etud.identite_list(cnx, {"code_ine": code_ine})
    return not etuds


# ------ Fonction ré-écrite en nov 2016 pour lire des fichiers sans etudid (fichiers APB)
def scolars_import_admission(datafile, formsemestre_id=None, type_admission=None):
    """Importe données admission depuis un fichier Excel quelconque
    par exemple ceux utilisés avec APB

    Cherche dans ce fichier les étudiants qui correspondent à des inscrits du
    semestre formsemestre_id.
    Le fichier n'a pas l'INE ni le NIP ni l'etudid, la correspondance se fait
    via les noms/prénoms qui doivent être égaux (la casse, les accents et caractères spéciaux
    étant ignorés).

    On tolère plusieurs variantes pour chaque nom de colonne (ici aussi, la casse, les espaces
    et les caractères spéciaux sont ignorés. Ainsi, la colonne "Prénom:" sera considéré comme "prenom".

    Le parametre type_admission remplace les valeurs vides (dans la base ET dans le fichier importé) du champ type_admission.
    Si une valeur existe ou est présente dans le fichier importé, ce paramètre est ignoré.

    TODO:
    - choix onglet du classeur
    """

    log("scolars_import_admission: formsemestre_id=%s" % formsemestre_id)
    members = sco_groups.get_group_members(
        sco_groups.get_default_group(formsemestre_id)
    )
    etuds_by_nomprenom = {}  # { nomprenom : etud }
    diag = []
    for m in members:
        np = (adm_normalize_string(m["nom"]), adm_normalize_string(m["prenom"]))
        if np in etuds_by_nomprenom:
            msg = "Attention: hononymie pour %s %s" % (m["nom"], m["prenom"])
            log(msg)
            diag.append(msg)
        etuds_by_nomprenom[np] = m

    exceldata = datafile.read()
    diag2, data = sco_excel.excel_bytes_to_list(exceldata)
    if not data:
        raise ScoException("scolars_import_admission: empty file !")
    diag += diag2
    cnx = ndb.GetDBConnexion()

    titles = data[0]
    # idx -> ('field', convertor)
    fields = adm_get_fields(titles, formsemestre_id)
    idx_nom = None
    idx_prenom = None
    for idx in fields:
        if fields[idx][0] == "nom":
            idx_nom = idx
        if fields[idx][0] == "prenom":
            idx_prenom = idx
    if (idx_nom is None) or (idx_prenom is None):
        log("fields indices=" + ", ".join([str(x) for x in fields]))
        log("fields titles =" + ", ".join([fields[x][0] for x in fields]))
        raise FormatError(
            "scolars_import_admission: colonnes nom et prenom requises",
            dest_url=url_for(
                "scolar.form_students_import_infos_admissions",
                scodoc_dept=g.scodoc_dept,
                formsemestre_id=formsemestre_id,
            ),
        )

    modifiable_fields = set(ADMISSION_MODIFIABLE_FIELDS)

    nline = 2  # la premiere ligne de donnees du fichier excel est 2
    n_import = 0
    for line in data[1:]:
        # Retrouve l'étudiant parmi ceux du semestre par (nom, prenom)
        nom = adm_normalize_string(line[idx_nom])
        prenom = adm_normalize_string(line[idx_prenom])
        if not (nom, prenom) in etuds_by_nomprenom:
            log(
                "unable to find %s %s among members" % (line[idx_nom], line[idx_prenom])
            )
        else:
            etud = etuds_by_nomprenom[(nom, prenom)]
            cur_adm = sco_etud.admission_list(cnx, args={"etudid": etud["etudid"]})[0]
            # peuple les champs presents dans le tableau
            args = {}
            for idx in fields:
                field_name, convertor = fields[idx]
                if field_name in modifiable_fields:
                    try:
                        val = convertor(line[idx])
                    except ValueError:
                        raise FormatError(
                            'scolars_import_admission: valeur invalide, ligne %d colonne %s: "%s"'
                            % (nline, field_name, line[idx]),
                            dest_url=url_for(
                                "scolar.form_students_import_infos_admissions",
                                scodoc_dept=g.scodoc_dept,
                                formsemestre_id=formsemestre_id,
                            ),
                        )
                    if val is not None:  # note: ne peut jamais supprimer une valeur
                        args[field_name] = val
            if args:
                args["etudid"] = etud["etudid"]
                args["adm_id"] = cur_adm["adm_id"]
                # Type admission: traitement particulier
                if not cur_adm["type_admission"] and not args.get("type_admission"):
                    args["type_admission"] = type_admission
                sco_etud.etudident_edit(cnx, args, disable_notify=True)
                adr = sco_etud.adresse_list(cnx, args={"etudid": etud["etudid"]})
                if adr:
                    args["adresse_id"] = adr[0]["adresse_id"]
                    sco_etud.adresse_edit(
                        cnx, args, disable_notify=True
                    )  # pas de notification ici
                else:
                    args["typeadresse"] = "domicile"
                    args["description"] = "(infos admission)"
                    adresse_id = sco_etud.adresse_create(cnx, args)
                # log('import_adm: %s' % args )
                # Change les groupes si nécessaire:
                if args["groupes"]:
                    gi = sco_groups.GroupIdInferer(formsemestre_id)
                    groupes = args["groupes"].split(";")
                    group_ids = [gi[group_name] for group_name in groupes]
                    group_ids = list({}.fromkeys(group_ids).keys())  # uniq
                    if None in group_ids:
                        raise ScoValueError(
                            "groupe invalide sur la ligne %d (groupe %s)"
                            % (nline, groupes)
                        )

                    for group_id in group_ids:
                        sco_groups.change_etud_group_in_partition(
                            args["etudid"], group_id
                        )
                #
                diag.append("import de %s" % (etud["nomprenom"]))
                n_import += 1
        nline += 1
    diag.append("%d lignes importées" % n_import)
    if n_import > 0:
        sco_cache.invalidate_formsemestre(formsemestre_id=formsemestre_id)
    return diag


_ADM_PATTERN = re.compile(r"[\W]+", re.UNICODE)  # supprime tout sauf alphanum


def adm_normalize_string(s):  # normalize unicode title
    return scu.suppress_accents(_ADM_PATTERN.sub("", s.strip().lower())).replace(
        "_", ""
    )


def adm_get_fields(titles, formsemestre_id):
    """Cherche les colonnes importables dans les titres (ligne 1) du fichier excel
    return: { idx : (field_name, convertor) }
    """
    # log('adm_get_fields: titles=%s' % titles)
    Fmt = sco_import_format_dict()
    fields = {}
    idx = 0
    for title in titles:
        title_n = adm_normalize_string(title)
        for k in Fmt:
            for v in Fmt[k]["aliases"]:
                if adm_normalize_string(v) == title_n:
                    typ = Fmt[k]["type"]
                    if typ == "real":
                        convertor = adm_convert_real
                    elif typ == "integer" or typ == "int":
                        convertor = adm_convert_int
                    else:
                        convertor = adm_convert_text
                    # doublons ?
                    if k in [x[0] for x in fields.values()]:
                        raise FormatError(
                            'scolars_import_admission: titre "%s" en double (ligne 1)'
                            % (title),
                            dest_url=url_for(
                                "scolar.form_students_import_infos_admissions_apb",
                                scodoc_dept=g.scodoc_dept,
                                formsemestre_id=formsemestre_id,
                            ),
                        )
                    fields[idx] = (k, convertor)
        idx += 1

    return fields


def adm_convert_text(v):
    if isinstance(v, float):
        return "{:g}".format(v)  # evite "1.0"
    return v


def adm_convert_int(v):
    if type(v) != int and not v:
        return None
    return int(float(v))  # accept "10.0"


def adm_convert_real(v):
    if type(v) != float and not v:
        return None
    return float(v)


def adm_table_description_format():
    """Table HTML (ou autre format) decrivant les donnees d'admissions importables"""
    Fmt = sco_import_format_dict(with_codesemestre=False)
    for k in Fmt:
        Fmt[k]["attribute"] = k
        Fmt[k]["aliases_str"] = ", ".join(Fmt[k]["aliases"])
        if not Fmt[k]["allow_nulls"]:
            Fmt[k]["required"] = "*"
        if k in ADMISSION_MODIFIABLE_FIELDS:
            Fmt[k]["writable"] = "oui"
        else:
            Fmt[k]["writable"] = "non"
    titles = {
        "attribute": "Attribut",
        "type": "Type",
        "required": "Requis",
        "writable": "Modifiable",
        "description": "Description",
        "aliases_str": "Titres (variantes)",
    }
    columns_ids = ("attribute", "type", "writable", "description", "aliases_str")

    tab = GenTable(
        titles=titles,
        columns_ids=columns_ids,
        rows=list(Fmt.values()),
        html_sortable=True,
        html_class="table_leftalign",
        preferences=sco_preferences.SemPreferences(),
    )
    return tab
