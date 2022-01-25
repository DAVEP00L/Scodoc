<?php

// Code contribué par Yann Leboulanger (Université Paris 10), Juin 2013
// 
// Exemple publication des bulletins de notes vers les étudiants
//  L'étudiant est authenfié via le CAS 
// Le bulletin est récupéré en format XML en interrogeant ScoDoc
// 
// Il faut créer un utilisateur ScoDoc n'ayant que des droits de lecture.
//
// A adapter à vos besoins locaux.

include_once 'CAS.php';

phpCAS::setDebug();
phpCAS::client(CAS_VERSION_2_0,'URL_CAS',443,'');
phpCAS::setNoCasServerValidation();
phpCAS::forceAuthentication();

$nip = phpCAS::getUser();

// Login information of a scodoc user that can access notes
$sco_user = 'USER';
$sco_pw = 'PASS';
$sco_url = 'https://SERVEUR/ScoDoc/';

$user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; fr; rv:1.8.1) Gecko/20061010 Firefox/2.0';

// Définition de la fonction d'encodage des headers
function http_build_headers( $headers ) {

       $headers_brut = '';

       foreach( $headers as $nom => $valeur ) {
               $headers_brut .= $nom . ': ' . $valeur . "\r\n";
       }

       return $headers_brut;
}

function get_EtudInfos_page($nip, $dept)
{
	global $sco_user;
	global $sco_pw;
	global $sco_url;
    $donnees = array(
        'code_nip' => $nip,
        '__ac_name' => $sco_user,
        '__ac_password' => $sco_pw );

    // Création du contenu brut de la requête
    $contenu = http_build_query( $donnees );

    // Définition des headers
    $headers = http_build_headers( array(
    'Content-Type' => 'application/x-www-form-urlencoded',
    'Content-Length' => strlen( $contenu) ) );

     // Définition du contexte
     $options = array( 'http' => array( 'user_agent' => $user_agent,
     'method' => 'POST',
     'content' => $contenu,
     'header' => $headers ) );

    // Création du contexte
    $contexte = stream_context_create($options);

    // Envoi du formulaire POST
    $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Notes/XMLgetEtudInfos', false, $contexte );

    return ($retour);
}

function get_bulletinetud_page($nip, $sem, $dept) {
	global $sco_user;
	global $sco_pw;
	global $sco_url;
    $donnees = array(
        'format' => 'xml',
        'code_nip' => $nip,
        'formsemestre_id' => $sem,
        'version' => 'selectedevals',
        '__ac_name' => $sco_user,
        '__ac_password' => $sco_pw );

    // Création du contenu brut de la requête
    $contenu = http_build_query( $donnees );

    // Définition des headers
    $headers = http_build_headers( array(
    'Content-Type' => 'application/x-www-form-urlencoded',
    'Content-Length' => strlen( $contenu) ) );

     // Définition du contexte
     $options = array( 'http' => array( 'user_agent' => $user_agent,
     'method' => 'POST',
     'content' => $contenu,
     'header' => $headers ) );

    // Création du contexte
    $contexte = stream_context_create($options);

    // Envoi du formulaire POST
    $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Notes/formsemestre_bulletinetud', false, $contexte );

    return ($retour);
}

function get_semestre_info($sem, $dept)
{
	global $sco_user;
	global $sco_pw;
	global $sco_url;
    $donnees = array(
        'formsemestre_id' => $sem,
        '__ac_name' => $sco_user,
        '__ac_password' => $sco_pw );

    // Création du contenu brut de la requête
    $contenu = http_build_query( $donnees );

    // Définition des headers
    $headers = http_build_headers( array(
    'Content-Type' => 'application/x-www-form-urlencoded',
    'Content-Length' => strlen( $contenu) ) );

     // Définition du contexte
     $options = array( 'http' => array( 'user_agent' => $user_agent,
     'method' => 'POST',
     'content' => $contenu,
     'header' => $headers ) );

    // Création du contexte
    $contexte = stream_context_create($options);

    // Envoi du formulaire POST
    $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Notes/XMLgetFormsemestres', false, $contexte );

    return ($retour);
}

function get_all_semestres($xml_data)
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
{
    $xml = simplexml_load_string($xml_data);
    foreach ($xml->insemestre as $s) {
        if ($s['current'] == 1)
            $sem = (array) $s['formsemestre_id'];
            return ($sem[0]);
    }
}

function print_semestres_list($sems, $dept, $sem)
{
    echo 'Semestre : <select name="sem">';
    for ($i=0; $i < count($sems); $i++) {
        $s = $sems[$i];
        $retour = get_semestre_info($s, $dept);
    	$xml = simplexml_load_string($retour);
        echo '<option value="' . $s . '"';
        if ($s == $sem) {
            echo ' selected';
        }
        echo '>' . $xml->formsemestre['titre_num'] . '</option>
';
    }
    echo '</select>
<input type="submit" value="Valider">
</form>';
}

function print_semestre($xml_data, $sem, $dept, $show_moy=False)
{
    $xml = simplexml_load_string($xml_data);
    echo '<h2>' . $xml->etudiant['sexe'] . ' ' . $xml->etudiant['prenom'] . ' ' . $xml->etudiant['nom'] . '</h2>';
    echo '<br/>
';
    $retour = get_semestre_info($sem, $dept);
    $xml2 = simplexml_load_string($retour);
    echo $xml2->formsemestre['titre_num'];
    echo '
<br/>
<br/>
';
    echo '<table class="notes_bulletin" style="background-color: background-color: rgb(255,255,240);">
<tr>
  <td class="note_bold">UE</td>
  <td class="note_bold">Module</td>
  <td class="note_bold">Evaluation</td>
  <td class="note_bold">Note/20</td>
  <td class="note_bold">Coef</td>
</tr>
';
    if ($show_moy) {
        echo '<tr class="gt_hl notes_bulletin_row_gen" ><td  class="titre" colspan="3" >Moyenne générale:</td><td  class="note">' . $xml->note['value'] . '</td><td  class="coef"></td></tr>';
    }
    foreach ($xml->ue as $ue) {
        $coef = 0;
        foreach ($ue->module as $mod) {
            $coef += $mod['coefficient'];
        }
        echo '<tr class="notes_bulletin_row_ue">
  <td class="note_bold"><span onclick="toggle_vis_ue(this);" class="toggle_ue"><img src="imgs/minus_img.png" alt="-" title="" height="13" width="13" border="0" /></span>' . $ue['acronyme'] . '</td>
  <td></td>
  <td></td>
';

        if ($show_moy) {
            echo '  <td>' . $ue->note['value'] . '</td>
';
        }
        else {
            echo '  <td></td>
';
        }

echo '  <td>' . $coef . '</td>
</tr>';
        foreach ($ue->module as $mod) {
            echo '<tr class="notes_bulletin_row_mod">
  <td></td>
  <td>' . $mod['code'] . '</td>
  <td></td>
';

            if ($show_moy) {
                echo '  <td>' . $mod->note['value'] . '</td>
';
            }
            else {
                echo '  <td></td>
';
            }

            echo '  <td>' . $mod['coefficient'] . '</td>
</tr>';
       
            if (!$show_moy) {
                foreach ($mod->evaluation as $eval) {
                    echo '<tr class="notes_bulletin_row_eval">
  <td></td>
  <td></td>
  <td class="bull_nom_eval">' . $eval['description'] . '</td>
  <td class="note">' . $eval->note['value'] . '</td>
  <td></td>
</tr>';
                } 
            }
        }
    }
    echo '</table>
<br/>
';
    if ($show_moy) {
        echo $xml->situation;
    }
}

function get_dept($nip)
{
	global $sco_url;
    $dept = file_get_contents( $sco_url . 'get_etud_dept?code_nip=' . $nip);
    return ($dept);
}



echo '<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<title>Bulletin de notes</title>
<meta http-equiv="Content-Type" content="text/html; charset=utf-8" />
<meta http-equiv="Content-Style-Type" content="text/css" />
<link href="css/scodoc.css" rel="stylesheet" type="text/css" />
<script language="javascript" type="text/javascript" src="js/bulletin.js"></script>
</head>
<body>
';

echo '<form action="index.php" method="post">';

$dept = get_dept($nip);
if ($dept) {
    $retour = get_EtudInfos_page($nip, $dept);
    $sems = get_all_semestres($retour);
    $sem_current = get_current_semestre($retour);
    if (isset($_POST["sem"])) {
        $sem = $_POST["sem"];
    }
    else {
        $sem = $sem_current;
    }
    print_semestres_list($sems, $dept, $sem);
    $retour = get_bulletinetud_page($nip, $sem, $dept);
    if ($sem == $sem_current) {
        print_semestre($retour, $sem, $dept, False);
    }
    else {
        print_semestre($retour, $sem, $dept, True);
    }
    $erreur=0;    // Tout est OK
}
else {
    echo "Numéro étudiant inconnu : " . $nip . ". Contactez votre Chef de département.";
}

echo '</form>';

echo '</body>
</html>';
?>
