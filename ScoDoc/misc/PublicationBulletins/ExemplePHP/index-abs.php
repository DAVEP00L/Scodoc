<?php

// Code contribué par Yann Leboulanger (Université Paris 10), Juin 2013
// Modifié par D.SOUDIERE avec le concours de Catherine Hatinguais

// Publication des notes vers les étudiants
// Gestion des absences: affichage et gestion des billets d'absences.
// Les étudiants signales les absences à venir ou passées et justifient en ligne puis physiquement.

//  L'étudiant est authenfié via le CAS 
// Le bulletin, les absences est récupéré en format XML en interrogeant ScoDoc
// Les billets sont envoyés à Scodoc et sont gérés par le secrétariat ou autre et validé.
// Il faut cocher la case "publier le bulletin sur le portail étudiants" dans le semestre 
//  ainsi que Gestion de "billets" d'absence dans les paramètres
// Pour qu'une évaluation soit visible il faut régler celle ci avec la case "Visible sur bulletins" 
//  et "Prise en compte immédiate" ou bien que toutes cases soient remplies.
// Il faut créer un utilisateur ScoDoc n'ayant que des droits de lecture.
//
// A adapter à vos besoins locaux.
// penser à mettre les fichiers css et js et les icons utilisés

// L authentification CAS et donc LDAP est fait par apache 
// cf /etc/apache2/site-enable/newdi

// il faut le paquet : php5-ldap


function convertir_utf8($texte){
$retour=htmlentities($texte,ENT_NOQUOTES,'UTF-8');
return ($retour);
}


// Définition de la fonction d'encodage des headers
function http_build_headers( $headers ) {

       $headers_brut = '';

       foreach( $headers as $nom => $valeur ) {
               $headers_brut .= $nom . ': ' . $valeur . "\r\n";
       }

       return $headers_brut;
}


function get_EtudAbs_page($nip, $dept,$beg_date)
{
	global $user_agent;
    global $sco_user;
	global $sco_pw;
	global $sco_url;
   $end_date=date("Y-m-d");  
    $donnees = array(
        'format' => 'xml',
        'code_nip' => $nip,
        '__ac_name' => $sco_user,
        '__ac_password' => $sco_pw,
        'beg_date' => $beg_date,
        'end_date' => $end_date);

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
    $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Absences/XMLgetAbsEtud', false, $contexte );

    return ($retour);
}


function get_BilletAbs_list($nip, $dept)
{
	global $user_agent;
    global $sco_user;
	global $sco_pw;
	global $sco_url;
    $donnees = array(
        'format' => 'xml',
        'code_nip' => $nip,
        '__ac_name' => $sco_user,
        '__ac_password' => $sco_pw,
);

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
    $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Absences/XMLgetBilletsEtud', false, $contexte );

    return ($retour);
}


function Get_EtudAbs_billet($nip, $dept,$begin,$end,$description)
{
	global $user_agent;
    global $sco_user;
	global $sco_pw;
	global $sco_url;
   $end_date=date("Y-m-d"); 
$justified="0";
    $donnees = array(
        'format' => 'xml',
        'code_nip' => $nip,
        '__ac_name' => $sco_user,
        '__ac_password' => $sco_pw,
        'description' =>$description,
        'justified' =>$justified,
        'begin' => $begin,
        'end' => $end);
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
    $retour = file_get_contents( $sco_url . $dept . '/Scolarite/Absences/AddBilletAbsence', false, $contexte );

    return ($retour);
}


function get_EtudInfos_page($nip, $dept)
{
	global $user_agent;
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
	global $user_agent;
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
	global $user_agent;
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
        echo '>' . convertir_utf8($xml->formsemestre['titre_num']) . '</option>
';
    }
    echo '</select>
<input type="submit" value="Valider">
</form>';
}

function print_semestre($xml_data, $sem, $dept, $show_moy=False)
{
    global $etudid;
    global $nip;
        global $sco_user;
	global $sco_pw;
    	global $sco_url;
    $xml = simplexml_load_string($xml_data);
    $etudid= $xml->etudiant['etudid'];
    
        if (!$show_moy) {
    echo '<p><span style="color: red;">Les informations contenues dans ce tableau sont
        provisoires. L&apos;&eacute;tat n&apos;a pas valeur de bulletin de notes.</span>';}

    echo '<span style="color: red;"><br>Il vous appartient de contacter vos enseignants
        ou votre département en cas de désaccord.</span></p>';
        
    echo '<h3>' . $xml->etudiant['sexe'] . ' ' . $xml->etudiant['prenom'] . ' ' . $xml->etudiant['nom'] . '</h3>';
    //echo '<br/>';
    $retour = get_semestre_info($sem, $dept);
    $xml2 = simplexml_load_string($retour);
    $debut=date("Y-m-d",strtotime($xml2->formsemestre['dateord']));
    
    echo '<b>'.convertir_utf8($xml2->formsemestre['titre_num']).'</b><br>';
    if (!$show_moy) {        echo "vous avez à ce jour ".convertir_utf8($xml->absences['nbabs'])." demi-journées d'absences dont ".convertir_utf8($xml->absences['nbabsjust']).' justifiées';}
       echo '
<br/>
<br/>
';
    echo '<table class="notes_bulletin" style="background-color: background-color: rgb(255,255,240);">
<tr>
  <td class="note_bold">UE</td>
  <td class="note_bold">Code Module</td>
    <td class="note_bold">Module</td>
  <td class="note_bold">Evaluation</td>
  <td class="note_bold">Note/20</td>
    <td class="note_bold">(Min/Max)</td>
  <td class="note_bold">Coef</td>
</tr>
';
    if ($show_moy) {
        echo '<tr class="gt_hl notes_bulletin_row_gen" ><td  class="titre" colspan="4" >Moyenne générale:</td><td  class="note">' . $xml->note['value'] . '</td><td class="max">('.$xml->note['min'].'/'.$xml->note['max'].')</td><td  class="coef"></td></tr>';
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
  <td></td>
';

        if ($show_moy) {
            echo '  <td>' . $ue->note['value'] . '</td><td class="max">('.$ue->note['min'].'/'.$ue->note['max'].')</td>
';
        }
        else {
            echo '  <td></td>
                    <td></td>
';
        }

echo '  <td>' . $coef . '</td>
</tr>';
        foreach ($ue->module as $mod) {
            echo '<tr class="notes_bulletin_row_mod">
  <td></td>
  <td>' . $mod['code'] . '</td>
   <td>' . convertir_utf8($mod['titre']) . '</td>
  <td></td>
';

            if ($show_moy) {
            echo '  <td>' . $mod->note['value'] . '</td><td class="max">('.$mod->note['min'].'/'.$mod->note['max'].')</td>
';
            }
            else {
                echo '  <td></td><td></td>
';
            }

            echo '  <td>' . $mod['coefficient'] . '</td>
</tr>';
       
            if (!$show_moy) {
                foreach ($mod->evaluation as $eval) {
                    echo '<tr class="notes_bulletin_row_eval">
  <td></td>
  <td></td>
    <td></td>
  <td class="bull_nom_eval">' . convertir_utf8($eval['description']) . '</td>
  <td class="note">' . $eval->note['value'] . '</td><td class="max">('.$eval->note['min'].'/'.$eval->note['max'].')</td>
  <td class="max">(' . $eval['coefficient'] . ')</td>
</tr>';
                } 
            }
        }
    }
    echo '</table>
<br/>
';
$code=$xml->decision['code'];

$date_fin=$xml->decision['date_fin'];
echo $date_fin;

    if ($show_moy) {
        echo "Situation sous réserve de validation par le jury : <br>".convertir_utf8($xml->situation);
    }
    else{if($code!=""){echo "Situation sous réserve de validation par le jury : <br>". convertir_utf8($xml->situation);}}
  
    
    if (!$show_moy) {    
echo ' 
<a href="#" id="toggler">
<h3>Cliquez ici pour afficher/masquer la liste des absences du semestre: </h3></a>';

   $retourabs = get_EtudAbs_page($nip, $dept,$debut);
   $xmlabs = simplexml_load_string($retourabs);
   

   
    echo '   
    <div id="toggle" style="display:none;">
    <table class="notes_bulletin" style="background-color: background-color: rgb(255,255,240);">

<tr> 
  <td class="note_bold">Du </td>
  <td class="note_bold">Au </td>
    <td class="note_bold">Justifiée</td>
  <td class="note_bold">Motif</td>
</tr>';   

foreach ($xmlabs->abs as $abs) {
   if($abs['justified']=="True"){$just="Oui";}else{$just="Non";}
   if(intval(date("H", strtotime($abs['begin'])))<12){$debmatin="matin";}else{$debmatin="apr&eacute;s midi";}
    if(intval(date("H", strtotime($abs['end'])))<12){$endmatin="matin";}else{$endmatin="apr&eacute;s midi";}
  echo "<tr><td>". date("d-m-Y H:i:s", strtotime($abs['begin'])) . ' '.$debmatin.'</td><td> ' .  date("d-m-Y H:i:s", strtotime($abs['end'])) .' '.$endmatin. '</td><td> ' . $just. '</td><td> ' . convertir_utf8($abs['description']) ."</td></tr>";
}
    echo '</table>
</div>';

echo '
<FORM method=post action=index.php>';

echo ' 
<h3> Déclaration des motifs d&apos;absences:</h3>';

    echo '
<TABLE BORDER=0>

<TR>
	<TD>Date et heure de début:</TD><TD> 
	<INPUT type="text" name="begin" size="10" value="" class="datepicker"/>
	</TD><TD>     
    <SELECT name="begtime" size="1" value="08:00">
<OPTION>08:00
<OPTION>08:30
<OPTION selected>08:00
<OPTION>09:00
<OPTION>09:30
<OPTION>10:00
<OPTION>10:30
<OPTION>11:00
<OPTION>11:30
<OPTION>12:00
<OPTION>12:30
<OPTION>13:00
<OPTION>13:30
<OPTION>14:00
<OPTION>14:30
<OPTION>15:00
<OPTION>15:30
<OPTION>16:00
<OPTION>16:30
<OPTION>17:00
<OPTION>17:30
<OPTION>18:00
<OPTION>18:30
<OPTION>19:00
<OPTION>19:30
</SELECT>
</TD></TR>
<TR> 
    <TD>Date et heure de fin:</TD><TD> 
	<INPUT type="text" name="end" size="10" value="" class="datepicker"/>
	</TD>
    <TD>     
    <SELECT name="endtime" size="1" value="18:00">
<OPTION>08:00
<OPTION>08:30
<OPTION selected>18:00
<OPTION>09:00
<OPTION>09:30
<OPTION>10:00
<OPTION>10:30
<OPTION>11:00
<OPTION>11:30
<OPTION>12:00
<OPTION>12:30
<OPTION>13:00
<OPTION>13:30
<OPTION>14:00
<OPTION>14:30
<OPTION>15:00
<OPTION>15:30
<OPTION>16:00
<OPTION>16:30
<OPTION>17:00
<OPTION>17:30
<OPTION>18:00
<OPTION>18:30
<OPTION>19:00
<OPTION>19:30
</SELECT>
</TD>
</TR>

</TABLE>

	Motif:
    
    <TABLE><br><TR>
	<TEXTAREA rows="3"  type="text" name="description"  cols="60"/></TEXTAREA>
	
</TR><br>
<span style="color: red;">Veuillez indiquer les matières et enseignants concernés (pour les absences de courte durée).<br> Apportez par ailleurs le num&eacute;ro du billet affiché dans le tableau ci après ainsi que vos justificatifs éventuels au secrétariat du département.</span>
<TR>
	<TD COLSPAN=1>
	<INPUT type="submit" value="Envoyer">
	</TD>
</TR>
</TABLE>';



if (isset($_POST["begin"]) and isset($_POST["end"])  and isset($_POST["begtime"]) and isset($_POST["endtime"]) and isset($_POST["description"]) and $_POST["end"]>=$_POST["begin"]){
$date1 = new DateTime($_POST["begin"]);
$date1->setTime(intval(substr($_POST["begtime"],0,2)), intval(substr($_POST["begtime"],-2)));

$date2 = new DateTime($_POST["end"]);
$date2->setTime(intval(substr($_POST["endtime"],0,2)), intval(substr($_POST["endtime"],-2)));
Get_EtudAbs_billet($nip, $dept,$date1->format('Y-m-d H:i:s') , $date2->format('Y-m-d H:i:s')  , $_POST["description"]);}

echo ' 
<h3> Billets d&apos;absences d&eacute;pos&eacute;s: </h3>';
   $retourbillets = get_BilletAbs_list($nip, $dept);
   $xmlbillets = simplexml_load_string($retourbillets);
   
    echo '<table class="notes_bulletin" style="background-color: background-color: rgb(255,255,240);">
<tr>
<td class="note_bold">Billet </td>
  <td class="note_bold">Du </td>
  <td class="note_bold">Au </td>
  <td class="note_bold">Motif</td>
    <td class="note_bold">Situation</td>
</tr>';   

foreach ($xmlbillets->row as $billet) {
  echo "<tr><td>". $billet->billet_id['value'] . '</td><td>'. convertir_utf8($billet->abs_begin_str['value']). '</td><td> ' .  convertir_utf8($billet->abs_end_str['value']) . '</td><td> ' .  convertir_utf8($billet->description['value']) .'</td><td> ' .  convertir_utf8($billet->etat_str['value']) ."</td></tr>
";
}

echo '  </table>
</FORM>'; 


}}




function get_dept($nip)
{
	global $sco_url;
    $dept = file_get_contents( $sco_url . 'get_etud_dept?code_nip=' . $nip);
    return ($dept);
}


// function pour la recuperation des infos ldap
function search_results($info) {
  foreach ($info as $inf) {
    if (is_array($inf)) {
      foreach ($inf as $key => $in) {
        if ((count($inf[$key]) - 1) > 0) {
          if (is_array($in)) {
            unset($inf[$key]["count"]);
          }
          $results[$key] = $inf[$key];
        }
      }
    }
  }
  $results["dn"] = explode(',', $info[0]["dn"]);
  return $results;
}


// Programme principal


echo '<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<title>Bulletin de notes</title>
<meta http-equiv="Content-Type" content="text/html; charset=iso-8859-1" />
<meta http-equiv="Content-Style-Type" content="text/css" />
<link href="css/scodoc.css" rel="stylesheet" type="text/css" />
<link type="text/css" rel="stylesheet" href="libjs/jquery-ui/css/custom-theme/jquery-ui-1.7.2.custom.css" />
<script language="javascript" type="text/javascript" src="js/bulletin.js"></script>
<script language="javascript" type="text/javascript" src="jQuery/jquery.js"></script>
<script language="javascript" type="text/javascript" src="jQuery/jquery-migrate-1.2.0.min.js"></script>
<script language="javascript" type="text/javascript" src="libjs/jquery-ui/js/jquery-ui-1.7.2.custom.min.js"></script>
<script language="javascript" type="text/javascript" src="libjs/jquery-ui/js/jquery-ui-i18n.js"></script>
 <script language="javascript" type="text/javascript">
           $(function() {
		$(".datepicker").datepicker({
                      showOn: "button", 
                      buttonImage: "icons/calendar_img.png", 
                      buttonImageOnly: true,
                      dateFormat: "yy-mm-dd",   
                      duration : "fast",                   
                  });
                $(".datepicker").datepicker("option", $.extend({showMonthAfterYear: false},
				$.datepicker.regional["fr"]));
    });
        </script>';

echo "<script type='text/javascript'>
/* <![CDATA[ */ 
/*
|-----------------------------------------------------------------------
|  jQuery Toggle Script by Matt - skyminds.net
|-----------------------------------------------------------------------
|
| Affiche/cache le contenu d'un bloc une fois qu'un lien est cliqué.
|
*/
 
// On attend que la page soit chargée 
jQuery(document).ready(function()
{
   // On cache la zone de texte
   jQuery('#toggle').hide();
   // toggle() lorsque le lien avec l'ID #toggler est cliqué
   jQuery('a#toggler').click(function()
  {
      jQuery('#toggle').toggle(400);
      return false;
   });
});
/* ]]> */ 
</script>
<style>
#toggle{height:auto; background:#eee; border:1px solid #900; margin:1em;text-align:center}
#toggle p{text-align:center;padding:0}
</style>
        
</head>
<body>
";


$user = $_SERVER['PHP_AUTH_USER'];
//echo 'USER: '.$user."\n"."<br>";

//$user = "ei121713";
//echo "On triche USER = ".$user."\n"."<br>";

$ds = ldap_connect("ldap://ldap");
if ($ds) {
	$r = ldap_bind($ds);
	$sr = ldap_search($ds, "ou=people,dc=univ-lehavre,dc=fr", "(&(objectClass=ulhEtudiant)(uid=$user))");
	$info = ldap_get_entries($ds, $sr);
 
	//echo $info["count"]." IS Search Result(s) for \"".$user."\"\n";
	$results = search_results($info);
	// si pas de reponse de l a nnuaire, ce n est pas un etudiant
	if ($info["count"] == 0 ) {
		echo '<html>
		<head>
			<title>getEtud</title>
		</head>
		<body>
			<h1>Service de consultation des notes</h1>
			<div>
			Il faut &ecirc;tre etudiant de l&apos;IUT pour acc&eacute;der &agrave; ses notes.
			</div>
		</body>
		</html>';
	} else {
		foreach ($results as $key => $result) {
			if ($key == 'supannetuid' ) {
				//echo " *  ".$key." : \n";
    				if (is_array($result)){
					foreach($result as $res){
						//echo "    ".$res."\n";
					}
				}
				//echo "<br>";
				$nip=$res;
			}
		}
	}
	ldap_close($ds);
}
// Login information of a scodoc user that can access notes
$sco_user = 'lecturenotes';
$sco_pw = 'XXXXXXX';
$sco_url = 'https://scodoc.XXXXX.fr/ScoDoc/';

$user_agent = 'Mozilla/5.0 (Windows; U; Windows NT 5.1; fr; rv:1.8.1) Gecko/20061010 Firefox/2.0';

echo '<form action="index.php" method="post">';
if ($nip) {
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
}

echo '</form>';


echo  '
          </body>
</html>';


?>
