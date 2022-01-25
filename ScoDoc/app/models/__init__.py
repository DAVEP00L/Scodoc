# -*- coding: UTF-8 -*

"""Modèles base de données ScoDoc
XXX version préliminaire ScoDoc8 #sco8 sans département
"""

CODE_STR_LEN = 16  # chaine pour les codes
SHORT_STR_LEN = 32  # courtes chaine, eg acronymes
APO_CODE_STR_LEN = 24  # nb de car max d'un code Apogée
GROUPNAME_STR_LEN = 64

from app.models.raw_sql_init import create_database_functions

from app.models.absences import Absence, AbsenceNotification, BilletAbsence

from app.models.departements import Departement

from app.models.entreprises import (
    Entreprise,
    EntrepriseCorrespondant,
    EntrepriseContact,
)
from app.models.etudiants import (
    Identite,
    Adresse,
    Admission,
    ItemSuivi,
    ItemSuiviTag,
    itemsuivi_tags_assoc,
    EtudAnnotation,
)
from app.models.events import Scolog, ScolarNews
from app.models.formations import (
    NotesFormation,
    NotesUE,
    NotesMatiere,
    NotesModule,
    NotesTag,
    notes_modules_tags,
)
from app.models.formsemestre import (
    FormSemestre,
    NotesFormsemestreEtape,
    NotesFormModalite,
    NotesFormsemestreUECoef,
    NotesFormsemestreUEComputationExpr,
    NotesFormsemestreCustomMenu,
    NotesFormsemestreInscription,
    notes_formsemestre_responsables,
    NotesModuleImpl,
    notes_modules_enseignants,
    NotesModuleImplInscription,
    NotesEvaluation,
    NotesSemSet,
    notes_semset_formsemestre,
)
from app.models.groups import Partition, GroupDescr, group_membership
from app.models.notes import (
    ScolarEvent,
    ScolarFormsemestreValidation,
    ScolarAutorisationInscription,
    NotesAppreciations,
    NotesNotes,
    NotesNotesLog,
)
from app.models.preferences import ScoPreference, ScoDocSiteConfig
