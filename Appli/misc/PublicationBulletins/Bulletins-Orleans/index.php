<?php
// https://trac.lipn.univ-paris13.fr/projects/scodoc/wiki/ScoDocAPI
// La publication des notes suppose que l'option "Semestres => Menu Semestre => Modifier le semestre => Publication" soit cochée.

// Code contribué par Yann Leboulanger (Université Paris 10), Juin 2013
// et modifié par  Pascal Legrand <pascal.legrand@univ-orleans.fr> (Nov 2017)
//
// Exemple publication des bulletins de notes vers les étudiants
// L'étudiant est authenfié via le CAS 
// Le bulletin est récupéré en format XML en interrogeant ScoDoc
// 
// Il faut créer un utilisateur ScoDoc n'ayant que des droits de lecture.
//
// A adapter à  vos besoins locaux.

include_once 'CAS.php';
// *********************************************** CONFIGURATION ***************************************************
phpCAS::client(CAS_VERSION_2_0,'URL_CAS',443,'');
phpCAS::setNoCasServerValidation();
phpCAS::forceAuthentication();

$nip = phpCAS::getUser();

// Login information of a scodoc user that can access notes
$sco_user = 'USER';
$sco_pw = 'PASS';
$sco_url = 'https://SERVEUR/ScoDoc/';

// URL où sont stockées les photos, si celle-ci diffère de "$sco_url". 
// Cette valeur est concaténée avec la valeur de "etudiant['photo_url']". (/ScoDoc/static/photos/.....)
$photo_url = 'https://SERVEUR/ScoDoc/';
// *********************************************** CONFIGURATION ***************************************************

// ************************************************* FONCTIONS *****************************************************
// Définition de la fonction d'encodage des headers
function http_build_headers( $headers ) {
         $headers_brut = '';
         foreach( $headers as $nom => $valeur ) {
                $headers_brut .= $nom . ': ' . $valeur . "\r\n";
         }
         return $headers_brut;
}

// Récupération du département
function get_dept($nip) {
	     global $sco_url;
         $dept = file_get_contents( $sco_url . 'get_etud_dept?code_nip=' . $nip);
         return ($dept);
}

function get_EtudInfos_page($nip, $dept) {
// Récupération des informations concernant l'étudiant.
// Nécessite une authentification avec sco_user et sco_pw - Il est possible de choisir le format XML ou JSON.
// etud_info
// Paramètres: etudid ou code_nip ou code_ine
// Résultat: informations sur cet étudiant et les semestres dans lesquels il est (ou a été) inscrit.
// Exemple: etud_info?format=json&etudid=12345
         global $sco_user;
	     global $sco_pw;
         global $sco_url;
         $donnees = array('format' => 'xml', 'code_nip' => $nip, '__ac_name' => $sco_user, '__ac_password' => $sco_pw);
    // Création du contenu brut de la requête
         $contenu = http_build_query($donnees);
    // Définition des headers
         $headers = http_build_headers(array('Content-Type' => 'application/x-www-form-urlencoded', 'Content-Length' => strlen( $contenu)));
     // Définition du contexte
         $options = array('http' => array('method' => 'POST', 'content' => $contenu, 'header' => $headers));
    // Création du contexte
         $contexte = stream_context_create($options);
    // Envoi du formulaire POST
         $retour = file_get_contents($sco_url . $dept . '/Scolarite/Notes/etud_info', false, $contexte);
         return ($retour);
}

function get_all_semestres($xml_data)
// Tous les semestres suivis par l'étudiant
{
         $data = array();
         $xml = simplexml_load_string($xml_data);
         foreach ($xml->insemestre as $s) {
                 $sem = (array) $s['formsemestre_id'];
                 $data[] = $sem[0];
         }
         return $data;
}

function get_current_semestre($xml_data)
// Semestre courrant suivi par l'étudiant
{
         $xml = simplexml_load_string($xml_data);
         foreach ($xml->insemestre as $s) {
                 if ($s['current'] == 1)
                    $sem = (array) $s['formsemestre_id'];
                    return ($sem[0]);
         }
}

function get_semestre_info($sem, $dept) {
// Renvoi les informations détaillées d'un semestre
// Ne nécessite pas d'authentification avec sco_user et sco_pw - Il est possible de choisir le format XML ou JSON.
// formsemestre_list
// Paramètres (tous optionnels): formsemestre_id, formation_id, etape_apo
// Résultat: liste des semestres correspondant.
// Exemple: formsemestre_list?format=xml&etape_apo=V1RT 
         global $sco_pw;
         global $sco_user;
         global $sco_url;
         $donnees = array('format' => 'xml', 'formsemestre_id' => $sem, '__ac_name' => $sco_user, '__ac_password' => $sco_pw);
    // Création du contenu brut de la requête
         $contenu = http_build_query( $donnees );
    // Définition des headers
         $headers = http_build_headers( array('Content-Type' => 'application/x-www-form-urlencoded', 'Content-Length' => strlen( $contenu) ) );
     // Définition du contexte
         $options = array( 'http' => array('method' => 'POST', 'content' => $contenu, 'header' => $headers ) );
    // Création du contexte
         $contexte = stream_context_create($options);
    // Envoi du formulaire POST
         $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Notes/formsemestre_list', false, $contexte );
/*
         echo '<div class="code"><img src="images/code.jpg"><br />';
         echo '<b>get_semestre_info : </b>';
         echo '<pre>' . htmlentities($retour) . '</pre>';
         echo '</div>';
*/
         return ($retour);
}

function print_semestres_list($sems, $dept, $sem) {
// Affiche le nom (titre_num) de tous les semestres suivis par l'étudiant dans un formulaire
         echo ' <form action="index.php" method="post">' . "\n";
         echo '  <fieldset>' . "\n";
         echo '   <legend>Liste des semestres</legend>' . "\n";
         echo '   <p><label for="sem">Semestre sélectionné: </label>' . "\n";
         echo '    <select name="sem" id="sem">' . "\n";
         for ($i=0; $i < count($sems); $i++) {
              $s = $sems[$i];
              $retour = get_semestre_info($s, $dept);
              $xml = simplexml_load_string($retour);
              echo '     <option value="' . $s . '"';
              if ($s == $sem) {
                   echo ' selected';
              }
              echo '>' . htmlentities($xml->formsemestre['titre_num']) . '</option>' . "\n";
         }
         echo '    </select>' . "\n";
         echo '    <br /><input type="radio" name="notes_moy" id="notes_moy_1" value="notes" required ';    if (isset($_POST['notes_moy']) && $_POST['notes_moy']=='notes')    echo 'checked="checked"'; echo '/><label for="notes_moy_1">Notes</label>' . "\n";
         echo '    <br /><input type="radio" name="notes_moy" id="notes_moy_2" value="moyennes" required '; if (isset($_POST['notes_moy']) && $_POST['notes_moy']=='moyennes') echo 'checked="checked"'; echo '/><label for="notes_moy_2">Moyennes</label>' . "\n";
         echo '    <p><input class="submit" type="submit" name="submit" value="Valider" />' . "\n";
         echo '  </fieldset>' . "\n";
         echo ' </form>' . "\n";
}

function get_bulletinetud_page($nip, $sem, $dept) {
// formsemestre_bulletinetud
// Paramètres: formsemestre_id, etudid, format (xml ou json), version (short, selectedevalsou long)
// Résultat: bulletin de notes
// Exemple: ici au format JSON, pour une version courte (version=short) 
         global $sco_user;
         global $sco_pw;
         global $sco_url;
         $donnees = array('format' => 'xml', 'code_nip' => $nip, 'formsemestre_id' => $sem, 'version' => 'long', '__ac_name' => $sco_user, '__ac_password' => $sco_pw );
    // Création du contenu brut de la requête
         $contenu = http_build_query( $donnees );
    // Définition des headers
         $headers = http_build_headers( array('Content-Type' => 'application/x-www-form-urlencoded', 'Content-Length' => strlen( $contenu) ) );
     // Définition du contexte
         $options = array( 'http' => array('method' => 'POST', 'content' => $contenu, 'header' => $headers ) );
    // Création du contexte
         $contexte = stream_context_create($options);
    // Envoi du formulaire POST
         $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Notes/formsemestre_bulletinetud', false, $contexte );
         return ($retour);
}

function print_semestre($xml_data, $sem, $dept, $show_moy) {
         global $photo_url;
         $xml = simplexml_load_string($xml_data);
         echo ' <h2><img src="' . $photo_url . $xml->etudiant['photo_url'] . '"> ' . $xml->etudiant['sexe'] . ' ' . $xml->etudiant['prenom'] . ' ' . $xml->etudiant['nom'] . '</h2>' . "\n" . ' <br />' . "\n";
         $retour = get_semestre_info($sem, $dept);
         $xml2 = simplexml_load_string($retour);
         $publie= $xml2->formsemestre['bul_hide_xml'];
         if (isset($xml->absences)) {
              (isset($xml->absences['nbabs'])) ? $nbabs = $xml->absences['nbabs']: $nbabs = 0;
              (isset($xml->absences['nbabsjust'])) ? $nbabsjust = $xml->absences['nbabsjust']: $nbabsjust = 0;
              echo ' <span class="info">Vous avez à  ce jour<span class="nbabs"> ' . $nbabs . ' </span>demi-journée(s) d\'absences, dont<span class="nbabsjust"> ' . $nbabsjust . ' </span>justifiée(s) </span><br />' . "\n";
         }
         else {
              echo ' <span class="info"><img src="images/info.png"> Les absences ne sont pas saisies. <img src="images/info.png"></span><br />' . "\n";
         }
         echo ' <h2>' . htmlentities($xml2->formsemestre['titre_num']) . '</h2>' . "\n";
         if ($publie == 1) {
              echo '<span class="alert"><img src="images/info.png"> Publication des notes non activée sur ScoDoc pour ce semestre <img src="images/info.png"></span><br />' . "\n";
         }
         else {
              echo ' <br />' . "\n";
              echo ' <div class="bulletin">' . "\n";
              echo '  <table cellspacing="0" cellpadding="0">' . "\n";
              echo '   <tr>' . "\n";
              echo '    <td class="titre">UE</td>' . "\n";
              echo '    <td class="titre">Module</td>' . "\n";
              echo '    <td class="titre">Evaluation</td>' . "\n";
              echo '    <td class="titre">Note/20</td>' . "\n";
              echo '    <td class="titre">Coef</td>' . "\n";
              echo '   </tr>' . "\n";
              if ($show_moy) {
                   echo '   <tr>' . "\n";
                   echo '    <td class="titre" colspan="3">Moyenne générale:</td>' . "\n";
                   echo '    <td class="titre">' . $xml->note['value'] . '</td>' . "\n";
                   echo '    <td class="titre"></td>' . "\n";
                   echo '   </tr>' . "\n";
              }
              foreach ($xml->ue as $ue) {
                   $coef = 0;
                   foreach ($ue->module as $mod) {
		     $coef += (float) $mod['coefficient'];
		   }
                  echo '   <tr>' . "\n";
                  echo '    <td class="ue">' . $ue['acronyme'] . ' <br /> ' . htmlentities($ue['titre']) . '</td>' . "\n";
                  echo '    <td class="titre_vide"></td>' . "\n";
                  echo '    <td class="titre_vide"></td>' . "\n";
                  if ($show_moy) {
                       echo '    <td class="moyennes_bold">' . $ue->note['value'] . '</td>' . "\n";
                  }
                  else {
                       echo '   <td class="titre_vide"></td>' . "\n";
                  }
                  echo '    <td class="coef_ue">' . $coef . '</td>   </tr>' . "\n";
                  foreach ($ue->module as $mod) {
                       echo '   <tr>' . "\n";
                       echo '    <td class="ue_vide"></td>' . "\n";
                       echo '    <td class="module">' . htmlentities($mod['titre']) . '</td>' . "\n";
                       echo '    <td class="evaluation_vide"></td>' . "\n";
                       if ($show_moy) {
                            echo '    <td class="moyennes">' . $mod->note['value'] . '</td>' . "\n";
                       }
                       else {
                            echo '    <td class="note_vide"></td>' . "\n";
                       }
                       echo '    <td class="coef">' . $mod['coefficient'] . '</td>' . "\n";
                       echo '   </tr>' . "\n";
                       if (!$show_moy) {
                            foreach ($mod->evaluation as $eval) {
                                 echo '   <tr>' . "\n";
                                 echo '    <td class="ue_vide"></td>' . "\n";
                                 echo '    <td class="module_vide"></td>' . "\n";
                                 echo '    <td class="evaluation">' . htmlentities($eval['description']) . '</td>' . "\n";
                                 echo '    <td class="note">' . $eval->note['value'] . '</td>' . "\n";
                                 echo '    <td class="coef_vide"></td>' . "\n";
                                 echo '   </tr>' . "\n";
                            } 
                       }
                  }
              }
              echo '  </table>' . "\n";
              echo ' </div>' . "\n";
              echo ' <br />' . "\n";
              if ($show_moy) {
                   echo $xml->situation . "\n";
              }
         }
}
// ************************************************* FONCTIONS *****************************************************

// **************************************************  HTML    *****************************************************
echo'<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Strict//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-strict.dtd">
<html xmlns="http://www.w3.org/1999/xhtml" xml:lang="fr" lang="fr">
 <head>
  <title>Bulletins de notes</title>
  <meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
  <meta http-equiv="Content-Style-Type" content="text/css" />
  <link href="style.css" rel="stylesheet" type="text/css" />
 </head>
<body>
';

$dept = get_dept($nip);
if ($dept) {
     $etud_info = get_EtudInfos_page($nip, $dept);
     $sems = get_all_semestres($etud_info);
     $sem_current = get_current_semestre($etud_info);
//   (Condition) ? <Condition=True>:<Condition=False>
     (isset($_POST['sem'])) ? $sem = $_POST['sem']:$sem = $sem_current;
     print_semestres_list($sems, $dept, $sem);
     (!isset($_POST['notes_moy'])) ? $_POST['notes_moy']='notes':'';
     echo ' <br /><span class="info">Affichage des ' . ucfirst($_POST['notes_moy']) . '</span>' . "\n";;
     $bulletin_page = get_bulletinetud_page($nip, $sem, $dept);
     ($_POST['notes_moy'] == 'notes') ? print_semestre($bulletin_page, $sem, $dept, False):print_semestre($bulletin_page, $sem, $dept, True);
//   ($sem == $sem_current) ? print_semestre($bulletin_page, $sem, $dept, False):print_semestre($bulletin_page, $sem, $dept, True);
}
else {
     echo '<span class=alert><img src="images/info.png"> Numéro étudiant inconnu : ' . $nip . ' - Contactez votre Chef de département <img src="images/info.png"></span><br />' . "\n";
}
$erreur=0;    // Tout est OK
/*
echo '<div class="code"><img src="images/code.jpg"><br />';
echo '<b>get_etud_info : </b>';
echo '<pre>' . htmlentities($etud_info) . '</pre>';
echo '<b>sems : </b>';
echo '<pre>' . print_r($sems) . '</pre>';
echo '<b>sem_current : </b>';
echo '<pre>' . htmlentities($sem_current) . '</pre>';
echo '<b>get_bulletinetud_page : </b>';
echo '<pre>' . htmlentities($bulletin_page) . '</pre>';
echo '</div>';
*/
echo '</body>' . "\n";
echo '</html>' . "\n";
// **************************************************  HTML    *****************************************************
?>
