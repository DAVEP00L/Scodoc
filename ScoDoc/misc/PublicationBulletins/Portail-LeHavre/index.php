<?php
// On démarre la session
session_start ();
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
// penser à mettre les fichiers css et js

// L authentification CAS et donc LDAP est fait par apache 
// cf /etc/apache2/site-enable/newdi

// il faut le paquet : php5-ldap


function convertir_utf8($texte){
$retour=htmlentities($texte,ENT_NOQUOTES,'UTF-8');
return ($retour);
}
function retire_accents($str, $charset='utf-8')
{
    $str = htmlentities($str, ENT_NOQUOTES, $charset);
    
    $str = preg_replace('#&([A-za-z])(?:acute|cedil|circ|grave|orn|ring|slash|th|tilde|uml);#', '\1', $str);
    $str = preg_replace('#&([A-za-z]{2})(?:lig);#', '\1', $str); // pour les ligatures e.g. '&oelig;'
    $str = preg_replace('#&[^;]+;#', '', $str); // supprime les autres caractères
    
    return $str;
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
//echo $sco_url . $dept . '/Scolarite/Absences/XMLgetBilletsEtud'.
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
        if ($s['current'] == 1){
            $sem = (array) $s['formsemestre_id'];
            return ($sem[0]);}    
            else{$sem = "";
            return ($sem);}
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
<a href="./deconnexion.php">Déconnexion</a>
</form>';
}

function print_semestre($xml_data, $sem, $dept, $show_moy=False)
{
    global $etudid;
    global $nip;
        global $sco_user;
	global $sco_pw;
    	global $sco_url;
        $modules=array();
        $codesmodules=array();
        $i=0;
          if($sem==""){echo '<h2> Il n&apos;y a pas de semestre courant</h2>';} else{   
    $xml = simplexml_load_string($xml_data);
    $etudid= $xml->etudiant['etudid'];

        $retour = get_semestre_info($sem, $dept);
    $xml2 = simplexml_load_string($retour);
    $debut=date("Y-m-d",strtotime($xml2->formsemestre['dateord']));
    $finsemestre=$xml2->formsemestre['date_fin_iso'];
    $fin=strtotime($finsemestre)+3000000;
    $day=strtotime(date("d-m-Y"));
     $publie= $xml2->formsemestre['bul_hide_xml'];
     
 // teste la publication et affiche un message si non publié
 // $showmoy teste si on est avant date de fin du semestre
 // si la date du jour dépasse de 45 jours la date de fin de semestre on affiche les moyennes
 // sinon pas encore

     $sexe=$xml->etudiant['sexe']; 
     $prenom=$xml->etudiant['prenom']; 
     $nom=$xml->etudiant['nom'];
     $semestre=$xml2->formsemestre['titre_num']; 
     
        if ($publie=="0") {    
        if (!$show_moy) {
    echo '<p><center><div class="attention"><span style="color: red;">Les informations contenues dans ces tableaux sont
        provisoires. L&apos;&eacute;tat n&apos;a pas valeur de bulletin de notes.</span>';}

    echo '<span style="color: red;"><br>Il vous appartient de contacter vos enseignants
        ou votre département en cas de désaccord.</span></div></center></p>';
      
    echo '<center><h3>' . convertir_utf8($sexe). ' ' . convertir_utf8($prenom). ' ' . convertir_utf8($nom). '</h3>';
    //echo '<br/>';

    echo '<b>'.convertir_utf8($semestre).'</b><br>';
    if (!$show_moy) {        echo "vous avez à ce jour ".convertir_utf8($xml->absences['nbabs'])." demi-journées d'absences dont ".convertir_utf8($xml->absences['nbabsjust']).' justifiées';}
    
       echo '
';
    echo ' <HR noshade size="5" width="100%" align="left" style="color: blue;">
    </center>  <a href="#" id="toggler"><center><H3><img src="imgs/livre.png" alt="-" title="" height="20" width="20" border="0" /> Cliquez ici pour afficher/masquer le bulletin de notes </H3></center></a>
        <div id="toggle" style="display:none;">

    <table class="notes_bulletin" style="background-color: background-color: rgb(255,255,240);">
<tr>
  <td class="note_bold">UE</td>
  <td class="note_bold">Code Module</td>
    <td class="note_bold">Module</td>
  <td class="note_bold"><a href="#" id="toggler4">Evaluation</a></td>
  <td class="note_bold">Note</td>
    <td class="note_bold">(Min/Max)</td>
  <td class="note_bold">Coef</td>
</tr>
';
    if ($show_moy and $fin<=$day) {
        echo '<tr class="gt_hl notes_bulletin_row_gen" ><td  class="titre" colspan="4" >Moyenne générale:</td><td  class="note">' . $xml->note['value'] . '/20</td><td class="max">('.$xml->note['min'].'/'.$xml->note['max'].')</td><td  class="coef"></td></tr>';
    }
    foreach ($xml->ue as $ue) {
        $coef = 0;
        foreach ($ue->module as $mod) {
        $i=$i+1;
            $coef = $coef + strval($mod['coefficient']);
            $modules[$i]=retire_accents($mod['titre'],'UTF-8');
            $codesmodules[$i]=retire_accents($mod['code'],'UTF-8');
        }
        echo '<tr class="notes_bulletin_row_ue">
  <td class="note_bold"><span onclick="toggle_vis_ue(this);" class="toggle_ue"><img src="imgs/minus_img.png" alt="-" title="" height="13" width="13" border="0" /></span>' . $ue['acronyme'] . '</td>
  <td></td>
  <td></td>
  <td></td>
';

        if ($show_moy and $fin<=$day) {
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


            echo '  <td>' . $mod->note['value'] . '</td><td class="max">('.$mod->note['min'].'/'.$mod->note['max'].')</td>
';


            echo '  <td>' . $mod['coefficient'] . '</td>
</tr>';
       
             if (!$show_moy or $fin>$day ){
                foreach ($mod->evaluation as $eval) {
                if (is_numeric(strval($eval->note['value']))) {
                $note_eval=round((strval($eval->note['value']))/20*strval($eval['note_max_origin']),2);}
                else{$note_eval=$eval->note['value'];}
                
                    echo '<tr class="toggle4" >
  <td></td>
  <td></td>
    <td></td>
  <td class="bull_nom_eval">' . convertir_utf8($eval['description']) . '</td>
  <td class="note">' . $note_eval . ' / '.strval($eval['note_max_origin']).'</td><td class="max"></td>
  <td class="max">(' . $eval['coefficient'] . ')</td>
</tr>';
                } 
            }
        }
    }
    echo '</table>
';
$code=$xml->decision['code'];

// Affichage décision seulement aprés 45 jours de la fin du semestre
    if ($show_moy and $fin<$day ) {
        echo "<br>".convertir_utf8($xml->situation);
    }
    else{if($code!=""  and $fin<$day){echo "<br>". convertir_utf8($xml->situation);}}
  
    
    if (!$show_moy) {    
echo '</div>
 <p> <HR noshade size="5" width="100%" align="left" style="color: blue;">
<center><span style="color: blue;"> <h3>Gestion des absences</h3></span>
<div class="attention">Les régles de gestion peuvent actuellement dépendre des départements. <span style="text-decoration: underline;">La déclaration en ligne ne suffit pas.</span> </div>


<a href="#" id="toggler1">
<h4><img src="imgs/Voir_abs.png" alt="-" title="" height="30" width="30" border="0" /> Cliquez ici pour afficher/masquer la liste des absences du semestre   </h4></a></center>';

   $retourabs = get_EtudAbs_page($nip, $dept,$debut);
   $xmlabs = simplexml_load_string($retourabs);
   

   
    echo '   
    <div id="toggle1" style="display:none;">
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
   $retourbillets = get_BilletAbs_list($nip, $dept);
if($retourbillets!=''){
echo '    <a href="#" id="toggler2"><center><H4> <img src="imgs/modifier_texte.png" alt="-" title="" height="30" width="30" border="0" /> Déclaration d&apos;un billet d&apos;absences</H4></center></a>
        <div class="news" id="toggle2" style="display:none;">
<FORM method=post action=index.php>';


echo '<span style="color: red;"><center>Imprimez par ailleurs le billet en cliquant sur  son identifiant dans le dans le tableau ci apr&egrave;s et <span style="text-decoration: underline;">d&eacute;posez le ainsi que vos justificatifs &eacute;ventuels au secr&eacute;tariat du d&eacute;partement</span>.
<br><i>En cas d&apos;absence &agrave; un ou plusieurs contr&ocirc;les, l&apos;&eacute;tudiant(e) doit obligatoirement remplir le justificatif et fournir les documents correspondants<br> (Rappel: toute absence à une évaluation, non justifiée dans les délais, est sanctionnée par un z&eacute;ro d&eacute;finitif)</i></center></br>  </span>';
    echo '
<TABLE BORDER=0>
<TR>
<TD><span style="color: red;" style="text-decoration: underline;"> <b>Vérifiez bien les dates et heures avant validation</b></span></TD></TR>
<TR>
	<TD>Date et heure de début:</TD><TD> 
	<INPUT type="text" name="begin" size="10" value="'.date("d-m-Y").'" class="datepicker"/>
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
	<INPUT type="text" name="end" size="10" value="'.date("d-m-Y").'" class="datepicker"/>
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
<TR>
	<TD>GROUPE (TD/TP):</TD><TD> <INPUT rows="1"  type="text" name="groupe"  size="10" value=""/></INPUT></TD>
</TABLE>

	Motif (à compléter avec ou sans justificatif):
    
    <TABLE ><br><TR>
	<TEXTAREA rows="4"  type="text" name="description"  cols="100"/> </TEXTAREA> </TR></TABLE>
    

   <TABLE >
    <tr style="color: red;"><td>Cocher ci-dessous les matières concernées par le billet</td><td>Cocher ci-dessous les contrôles concernés</td></tr>';
    
$matcoche=array();
$dscoche=array();
  for($i=1;$i<sizeof($modules);$i++){ 
  $matcoche[$i]=0;
  $dscoche[$i]=0;
  }
  
  for($i=1;$i<=sizeof($modules);$i++){ echo "<tr><td><input type='checkbox' name='mat".$i."' value=1>".$modules[$i]."<td><input type='checkbox' name='ds".$i."' value=1>".$modules[$i]."</td></tr>";
  }
echo '	</TABLE><TABLE><TR>	<TD COLSPAN=1>
	<INPUT type="submit" name="submit" value="Envoyer" >
	</TD>
</TR>
</TABLE></div>';




if (isset($_POST['submit']) && $_POST['submit'] == "Envoyer"){
$description=$_POST["description"];

$date1 = new DateTime($_POST["begin"]);
$date1->setTime(intval(substr($_POST["begtime"],0,2)), intval(substr($_POST["begtime"],-2)))+1;

$date2 = new DateTime($_POST["end"]);
$date2->setTime(intval(substr($_POST["endtime"],0,2)), intval(substr($_POST["endtime"],-2))-31);

if(!$description){$description="Motif: ".$description."  - Matières: " ;}
  for($i=1;$i<sizeof($modules);$i++){if (isset($_POST["mat".$i]))
  {$description=$description." ".$codesmodules[$i];}}

 if(substr($description,-12)=="- Matières: "){$description=substr($description,0,-12);} 
$description=$description."   - Contrôles: " ;
  for($i=1;$i<sizeof($modules);$i++)
  {if (isset($_POST["ds".$i])){$description=$description." ".$codesmodules[$i];}
  }
  if(substr($description,-13)=="- Contrôles: "){$description=substr($description,0,-13);}  
  $description=$description." (billet déposé le ".date("d/n/Y à H:i").")";
  $description=utf8_encode($description);

$date1=convertir_utf8(date_format($date1, 'Y-m-d H:i:s'));
$date2=convertir_utf8(date_format($date2, 'Y-m-d H:i:s'));
echo '</FORM>'; 

  Get_EtudAbs_billet($nip, $dept,$date1 , $date2  , $description);
 }

// pour tester le renvoi des variables
 //print_r($_POST); 

echo '

     <a href="#" id="toggler3" ><center><img src="imgs/Voir_abs.png" alt="-" title="" height="30" width="30" border="0" /> Cliquez ici pour afficher/masquer les billets d&apos;absences d&eacute;pos&eacute;s </center></a>
        <div id="toggle3" style="display:none;">';

   $xmlbillets = simplexml_load_string($retourbillets);
   
    echo '    <table class="notes_bulletin" style="background-color: background-color: rgb(255,255,240);">
<tr>
<td class="note_bold">Billet </td>
  <td class="note_bold">Du </td>
  <td class="note_bold">Au </td>
  <td class="note_bold">Motif</td>
    <td class="note_bold">Situation</td>
</tr>';   

foreach ($xmlbillets->row as $billets) {
$billet=$billets->billet_id['value'];
$motif=$billets->description['value'];
$begbillet=$billets->abs_begin_str['value'];
$endbillet=$billets->abs_end_str['value'];
if (isset($_POST["groupe"])){$groupe=$_POST["groupe"];}else{$groupe=".............";}
  
  echo "<tr><td><img src='icons/pdficon16x20_img.png' alt='-' title='' height='15' width='15' border='0' /><a href='PDF_Billet.php?billet=".$billet."&sexe=".$sexe."&nom=".$nom."&prenom=".$prenom."&semestre=".$semestre."&groupe=".$groupe."&debutsemestre=".$debut."&finsemestre=".$finsemestre."&motif=".$motif."&debut=".$begbillet."&fin=".$endbillet."' target='_blank'>". $billet . "</a></td><td>". convertir_utf8($begbillet). '</td><td> ' .  convertir_utf8($endbillet) . '</td><td> ' .  convertir_utf8($motif) .'</td><td> ' .  convertir_utf8($billets->etat_str['value']) ."</td></tr>
";
}

echo '  </table></div>
'; 
}

}}
else
{echo '<h2> Votre d&eacute;partement n&apos;a pas autoris&eacute; l&apos;affichage des informations de ce semestre</h2>';}

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
// $nip="20121713";

echo '<html xmlns="http://www.w3.org/1999/xhtml">
<head>
<title>Portail Webnotes</title>
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
                      dateFormat: "dd-mm-yy",   
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
    jQuery('#toggle1').hide();
    jQuery('#toggle2').hide();
    jQuery('#toggle3').hide();
    jQuery('#toggle4').show();
     
   // toggle() lorsque le lien avec l'ID #toggler est cliqué
   jQuery('a#toggler').click(function()
  {
      jQuery('#toggle').toggle(400);
      return false;
   });
      jQuery('a#toggler1').click(function()
  {
      jQuery('#toggle1').toggle(400);
      return false;
   });
      jQuery('a#toggler2').click(function()
  {
      jQuery('#toggle2').toggle(400);
      return false;
   });
         jQuery('a#toggler3').click(function()
  {
      jQuery('#toggle3').toggle(400);
      return false;
   });
            jQuery('a#toggler4').click(function()
  {
      jQuery('.toggle4').toggle(400);
      return false;
   });
});
/* ]]> */ 
</script>
<style>
#toggle{height:auto; background:#eee; border:1px solid #900; margin:1em;text-align:center}
#toggle p{text-align:center;padding:0}
tr.toggle{height:auto; background:#eee; border:1px solid #900; margin:1em;text-align:center}
tr.toggle p{text-align:center;padding:0}
</style>
        
</head>
<body>
";

//$user = $_SERVER['PHP_AUTH_USER'];
//echo 'USER: '.$user."\n"."<br>";

//$user = "ei121713";
//echo "On triche USER = ".$user."\n"."<br>";
/*
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
			<H1>Service de consultation des notes</H1>
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
}*/
// Login information of a scodoc user that can access notes
$sco_user = 'lecturenotes';
$sco_pw = 'lecture2014';
//$sco_url = 'https://test1-scodoc.iut.univ-lehavre.fr/ScoDoc/';
$nip="20121713";
$sco_url = 'https://scodoc-demo.iut.univ-lehavre.fr/ScoDoc/';
//$sco_url = 'https://scodoc.univ-lehavre.fr/ScoDoc/'; 
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
  if($sem==""){echo '<h2> Il n&apos;y a pas de semestre en cours - Choisissez éventuellement dans la liste.</h2>';} else{       
    $retour = get_bulletinetud_page($nip, $sem, $dept);
    if ($sem == $sem_current) {
        print_semestre($retour, $sem, $dept, False);
    }
    else {
        print_semestre($retour, $sem, $dept, True);
    }
    $erreur=0;    // Tout est OK
}}
else {
    echo "Numéro étudiant inconnu : " . $nip . ". Contactez votre Chef de département.";

}}

echo '</form>';


echo  '
          </body>
</html>';


?>