# -*- mode: python -*-
# -*- coding: utf-8 -*-

SCOVERSION = "9.0.67"

SCONAME = "ScoDoc"

SCONEWS = """
<h4>Année 2021</h4>
<ul>
<li>ScoDoc 9: nouvelle architecture logicielle (Flask/Python3/Debian 11)</li>
<li>Version mobile (en test)</li>
<li>Évaluations de type "deuxième session"</li>
<li>Gestion du genre neutre (pas d'affichage de la civilité)</li>
<li>Diverses corrections (PV de jurys, ...)</li>
<li>Modernisation du code Python</li>
</ul>
<h4>Année 2020</h4>
<ul>
<li>Corrections d'erreurs, améliorations saisie absences et affichage bulletins</li>
<li>Nouveau site <a href="https://scodoc.org" target="_blank" rel="noopener noreferrer">scodoc.org</a> pour la documentation</li>
<li>Enregistrement de semestres extérieurs</li>
<li>Améliorations PV de Jury</li>
<li>Contributions J.-M. Place: aide au diagnostic problèmes export Apogée
</li>
</ul>
<h4>Année 2019</h4>
<ul>
<li>Support Linux Debian 10</li>
<li>Petites améliorations: import groupes, droits de suppression notes pour vacataires, etc.</li>
<li>Exports listes pour Moodle</li>
<li>Fonction facilitant l'envoi de données pour l'assistance technique</li>
</ul>
<h4>Année 2018</h4>
<ul>
<li>Affichage date finalisation inscription Apogée</li>
<li>Co-responsables de semestres</li>
<li>Amélioration page d'accueil département</li>
<li>Corrections diverses et petites améliorations</li>
<li>Avis de poursuites d'études plus robustes et configurables</li>
</ul>
<h4>Année 2017</h4>
<ul>
<li>Bonus/Malus sur les moyennes d'UE</li>
<li>Enregistrement des informations sur le devenir de l'étudiant</li>
<li>Export global des résultats d'un département (utile pour les rapports d'évaluation)</li>
<li>Compatibilité Linux Debian 9, et modernisation de certains composants</li>
<li>Génération des avis de poursuite d'études</li>
<li>Toilettage page liste programme pédagogiques</li>
<li>Amélioration exports résultats vers Apogée</li>
<li>Amélioration calcul des ECTS</li>
<li>Possibilité d'utilisation des adresses mail personnelles des étudiant</li>
<li>Corrections diverses</li>
</ul>

<h4>Année 2016</h4>
<ul>
<li>Import des données d'admissions depuis fichiers APB ou autres</li>
<li>Nouveau formulaire saisie des notes</li>
<li>Export des résultats vers Apogée pour un ensemble de semestre</li>
<li>Enregistrement du classement lors de l'admission</li>
<li>Modification du calcul des coefficients des UE capitalisées</li>
</ul>

<h4>Année 2015</h4>
<ul>
<li>Exports fichiers Apogée</li>
<li>Recherche étudiants sur plusieurs départements</li>
<li>Corrections diverses</li>
</ul>


<h4>Année 2014</h4>
<ul>
<li>Nouvelle interface pour listes groupes, photos, feuilles d'émargement.</li>
</ul>
<h4>Année 2013</h4>
<ul>
<li>Modernisation de nombreux composants logiciels (ScoDoc 7)</li>
<li>Saisie des absences par matières</li>
</ul>
<h4>Année 2012</h4>
<ul>
<li>Table lycées d'origine avec carte google</li>
<li>Amélioration des PV de jury (logos, ...)</li>
<li>Accélération du code de calcul des semestres</li>
<li>Changement documentation en ligne (nouveau site web)</li>
</ul>


<h4>Année 2011</h4>
<ul>
<li>Amélioration de la présentation des bulletins de notes, et possibilité de définir de nouveaux formats</li>
<li>Possibilité de modifier les moyennes d'UE via un "bonus" (sport/culture)</li>
<li>Ajout parcours spécifique pour UCAC (Cameroun)</li>
<li>Possibilité d'indiquer des mentions sur les PV</li>
<li>Evaluations de "rattrapage"</li>
<li>Support pour installation en Linux Debian "Squeeze"</li>
<li>Corrections diverses</li>
</ul>


<h4>Novembre 2010</h4>
<ul>
<li>Possibilité d'indiquer des évaluations avec publication immédiate des notes (même si incomplètes)</li>
</ul>

<h4>Octobre 2010</h4>
<ul>
<li>Nouvelle API JSON</li>
<li>Possibilité d'associer 2 étapes Apogée au même semestre</li>
<li>Table "poursuite études"</li>
<li>Possibilité d'envoyer un mail auto aux étudiants absentéistes<li>
</ul>

<h4>Août 2010</h4>
<ul>
<li>Définitions de parcours (DUT, LP, ...) avec prise en compte des spécificités (par ex., certaines barres d'UE différentes en LP)</li>
</ul>

<h4>Avril - Juin 2010</h4>
<ul>
<li>Formules utilisateur pour le calcul des moyennes d'UE</li>
<li>Nouveau système de notification des absences par mail</li>
<li>Affichage optionnel des valeurs mini et maxi des moyennes sur les bulletins</li>
<li>Nouveau code de décision jury semestre: "RAT" : en attente de rattrapage</li>
</ul>

<h4>Janvier 2010</h4>
<ul>
<li>Nouveau menu "Groupes" pour faciliter la prise en main</li>
<li>Possibilité de définir des règles ad hoc de calcul des moyennes de modules (formules)</li>
<li>Possibilité d'inclure des images (logos) dans les bulletins PDF</li>
<li>Bandeau "provisoire" sur les bulletins en cours de semestre</li>
<li>Possibilite de valider (capitaliser) une UE passee hors ScoDoc</li>
<li>Amelioration de l'édition des programmes (formations)</li>
<li>Nombreuses améliorations mineures</li>
</ul>

<h4>Novembre 2009</h4>
<ul>
<li>Gestion des partitions et groupes en nombres quelconques</li>
<li>Nouvelle gestion des photos</li>
<lI>Imports d'étudiants excel incrémentaux</li>
<li>Optimisations et petites améliorations</li>
</ul>

<h4>Septembre 2009</h4>
<ul>
<li>Traitement de "billets d'absences" (saisis par les étudiants sur le portail)</li>
</ul>

<h4>Juin 2009</h4>
<ul>
<li>Nouveau système plus flexibles de gestion des préférences (ou "paramètres")</li>
<li>Possiblité d'associer une nouvelle version de programme à un semestre</li>
<li>Corrections et améliorations diverses</h4>
</ul>

<h4>Juillet 2008: version 6.0</h4>
<ul>
<li>Installeur automatisé pour Linux</li>
<li>Amélioration ergonomie (barre menu pages semestres)</li>
<li>Refonte fiche étudiant (parcours)</li>
<li>Archivage des documents (PV)</li>
<li>Nouvel affichage des notes des évaluations</li>
<li>Nombreuses corrections et améliorations</li>
</ul>

<h4>Juin 2008</h4>
<ul>
<li>Rangs sur les bulletins</li>
</ul>

<h4>Février 2008</h4>
<ul>
<li>Statistiques et suivis de cohortes (chiffres et graphes)</li>
<li>Nombreuses petites corrections suites aux jurys de janvier</li>
</ul>

<h4>Janvier 2008</h4>
<ul>
<li>Personnalisation des régles de calculs notes d'option (sport, culture)</li>
<li>Edition de PV de jury individuel</li>
</ul>

<h4>Novembre 2007</h4>
<ul>
<li>Vérification des absences aux évaluations</li>
<li>Import des photos depuis portail, trombinoscopes en PDF</li>
</ul>

<h4>Septembre 2007</h4>
<ul>
<li>Importation des etudiants depuis étapes Apogée</li>
<li>Inscription de groupes à des modules (options ou parcours)</li>
<li>Listes de étapes Apogée (importées du portail)</li>
</ul>

<h4>Juillet 2007</h4>
<ul>
<li>Import utilisateurs depuis Excel</li>
<li>Nouvelle gestion des passage d'un semestre à l'autre</li>
</ul>

<h4>Juin 2007: version 5.0</h4>
<ul>
<li>Suivi des parcours et règles de décision des jurys DUT</li>
<li>Capitalisation des UEs</li>
<li>Edition des PV de jurys et courriers aux étudiants</li>
<li>Feuilles (excel) pour préparation jurys</li>
<li>Nombreuses petites améliorations</li>
</ul>

<h4>Avril 2007</h4>
<ul>
<li>Paramètres de mise en page des bulletins en PDF</li>
</ul>

<h4>Février 2007</h4>

<ul>
<li>Possibilité de ne <em>pas</em> publier les bulletins sur le portail</li>
<li>Gestion des notes "en attente" (publication d'évaluations sans correction de toutes les copies)</li>
<li>Amélioration formulaire saisie absences, saisie absences par semestre.</li>
</ul>

<h4>Janvier 2007</h4>
<ul>
<li>Possibilité d'initialiser les notes manquantes d'une évaluation</li>
<li>Recupération des codes NIP depuis Apogée</li>
<li>Gestion des compensations inter-semestre DUT (en cours de développement)</li>
<li>Export trombinoscope en archive zip</li>
</ul>

<h4>Octobre 2006</h4>
<ul>
<li>Réorganisation des pages d'accueil</li>
<li>Ajout des "nouvelles" (dernières opérations), avec flux RSS</li>
<li>Import/Export XML des formations, duplication d'une formation (versions)</li>
<li>Bulletins toujours sur une seule feuille (passage à ReportLab 2.0)</li>
<li>Suppression d'un utilisateur</il>
</ul>
<h4>Septembre 2006</h4>
<ul>
<li>Page pour suppression des groupes.</li>
<li>Amélioration gestion des utilisateurs</li>
<li>"Verrouillage" des semestres</li>
<li>Liste d'enseignants (chargés de TD) associés à un module (et pouvant saisir des notes)</li>
<li>Noms de types de groupes (TD, TP, ...) modifiables</li>
<li>Tableau rudimentaire donnant la répartition des bacs dans un semestre</li>
<li>Amélioration mise en page des listes au format excel</li>
<li>Annulation des démissions</li>
</ul>

<h4>Juillet 2006</h4>
<ul>
<li>Dialogue permettant au directeur des études de modifier
les options d'un semestre</li>
<li>Option pour ne pas afficher les UE validées sur les bulletins</li>
</ul>

<h4>30 juin 2006</h4>
<ul>
<li>Option pour ne pas afficher les décisions sur les bulletins</li>
<li>Génération feuilles pour préparation jury</li>
<li>Gestion des modules optionnels</li>
<li>Prise en compte note "activités culturelles ou sportives"</li>
<li>Amélioration tableau de bord semestre</li>
<li>Import listes étudiants depuis Excel (avec code Apogée)</li>
</ul>

<h4>12 juin 2006</h4>
<ul>
<li>Formulaire dynamique d'affectation aux groupes</li>
<li>Tri des tableaux (listes, récapitulatif)</li>
<li>Export XML des infos sur un etudiant et des groupes</li>
</ul>

<h4>12 mai 2006</h4>
<ul>
<li>Possibilité de suppression d'un semestre</li>
<li>Export XML du tableau recapitulatif des notes du semestre</li>
<li>Possibilité de supression d'une formation complète</li>
</ul>

<h4>24 avril 2006</h4>
<ul>
<li>Export bulletins en XML (expérimental)</li>
<li>Flag "gestion_absence" sur les semestres de formation</li>
</ul>

<h4>4 mars 2006</h4>
<ul>
<li>Formulaire d'inscription au semestre suivant.</li>
<li>Format "nombre" dans les feuilles excel exportées.</li>
</ul>

<h4>23 février 2006</h4>
<ul>
<li>Décisions jury sur bulletins.</li>
</ul>

<h4>17 janvier 2006</h4>
<ul>
<li>Ajout et édition d'appréciations sur les bulletins.</li>
</ul>
<h4>12 janvier 2006</h4>
<ul>
<li>Envoi des bulletins en PDF par mail aux étudiants.</li>
</ul>

<h4>6 janvier 2006</h4>
<ul>
<li>Affichage des ex-aequos.</li>
<li>Classeurs bulletins PDF en différentes versions.</li>
<li>Corrigé gestion des notes des démissionnaires.</li>
</ul>

<h4>1er janvier 2006</h4>
<ul>
<li>Import du projet dans Subversion / LIPN.</li>
<li>Lecture des feuilles de notes Excel.</li>
</ul>

<h4>31 décembre 2005</h4>
<ul>
<li>Listes générées au format Excel au lieu de CSV.</li>
<li>Bug fix (création/saisie evals).</li>
</ul>

<h4>29 décembre 2005</h4>
<ul>
<li>Affichage des moyennes de chaque groupe dans tableau de bord module.
</ul>

<h4>26 décembre 2005</h4>
<ul>
<li>Révision inscription/édition <em>individuelle</em> d'étudiants.</li>
<li>Amélioration fiche étudiant (cosmétique, liste formations, actions).</li>
<li>Listings notes d'évaluations anonymes (utilité douteuse ?).</li>
<li>Amélioration formulaire saisie notes ('enter' -> champ suivant).</li>
</ul>

<h4>24 décembre 2005</h4>
<ul>
<li>Génération de bulletins PDF
</li>
<li>Suppression de notes (permet donc de supprimer une évaluation)
</li>
<li>Bulletins en versions courtes (seulement moyennes de chaque module), longues
(toutes les notes) et intermédiaire (moyenne de chaque module plus notes dans les évaluations sélectionnées).
</li>
<li>Notes moyennes sous les barres en rouge dans le tableau récapitulatif (seuil=10 sur la moyenne générale, et 8 sur chaque UE).
</li>
<li>Colonne "groupe de TD" dans le tableau récapitulatif des notes.
</ul>
"""
