<?php

 
include("phpToPDF.php");
$billet=utf8_decode($_GET['billet']);
$nom=utf8_decode($_GET['nom']);
$prenom=utf8_decode($_GET['prenom']);
$semestre=utf8_decode($_GET['semestre']);
$groupe=utf8_decode($_GET['groupe']);
$sexe=utf8_decode($_GET['sexe']);
$motif=utf8_decode($_GET['motif']);
$debut=utf8_decode($_GET['debut']);
$fin=utf8_decode($_GET['fin']);
$finsemestre=date("d-m-Y",strtotime(($_GET['finsemestre'])));
$debutsemestre=date("d-m-Y",strtotime(($_GET['debutsemestre'])));

$trait="_____________________________________________________________________________";			
$etudiant = "Etudiant : ".$sexe." ".$prenom." ".$nom;
$numbillet="Billet d'absence: ".$billet;
$dates="Absence du  : ".$debut." au ".$fin;
$texte3="";

$largeur=200;
$esp=5;
$deb= 25;
$PDF = new phpToPDF();
$PDF->AddPage();


$PDF->SetFont('Arial','B',16);

$fill = 1;
$PDF->SetFillColor(224,228,200);
$PDF->SetTextColor(0,0,0);

$PDF->Text(20,15,"$semestre");
$PDF->SetXY(20,20);
$PDF->MultiCell(180,5,"(du $debutsemestre au $finsemestre)",0,'C',0);


$PDF->SetXY(20,30);
$PDF->SetFont('Arial','',10);
$PDF->MultiCell(180,5,"Formulaire à compléter par l'étudiant. \n A faire signer par les enseignants et à déposer au secrétariat sans attendre avec les justificatifs s'il y a lieu.",0,'C',0); 
$PDF->SetFont('Arial','B',12);

$PDF->Text(15,40,"$trait");
$PDF->Text(20,50,"$etudiant");
$PDF->Text(100,55,"Groupe (TD/TP): $groupe");
$PDF->Text(20,55,"$numbillet",0,0,'L');
$PDF->Text(15,60,"$trait");
$PDF->SetFont('Arial','',11);
$PDF->Text(20,70,"$dates");

$PDF->Text(20,75,"Justificatif apporté: Oui   Non");
$PDF->SetFont('Arial','B',11);
$PDF->Text(20,80,"Motif: ");
$PDF->SetFont('Arial','',10);
$PDF->SetXY(20,82);
$PDF->MultiCell(180,5,"$motif",1,'L',0); 
$PDF->SetXY(20,122);

// Définition des propriétés du tableau.
$larccel=38;
$larccel2=55;
//$R=151;$G=190;$B=13;
$R=224;$G=228;$B=216;

$proprietesTableau = array(
	'TB_ALIGN' => 'L',
	'L_MARGIN' => 1,
	'BRD_COLOR' => array(0,0,0),
	'BRD_SIZE' => '0.5',
	);
 
// Definition des proprietes du header du tableau.	
$proprieteHeader = array(
	'T_COLOR' => array(0,0,0),
	'T_SIZE' => 10,
	'T_FONT' => 'Arial',
	'T_ALIGN' => 'C',
	'V_ALIGN' => 'T',
	'T_TYPE' => 'B',
	'LN_SIZE' => 7,
	'BG_COLOR_COL0' => array($R, $G, $B),
	'BG_COLOR' => array($R, $G, $B),
	'BRD_COLOR' => array(0,0,0),
	'BRD_SIZE' => 0.2,
	'BRD_TYPE' => '1',
	'BRD_TYPE_NEW_PAGE' => '',
	);

// Contenu du header du tableau.	
$contenuHeader = array(
	$larccel, $larccel, $larccel2, $larccel2, 
	"Matiere","Enseignant","Emargement Enseignant","Observations"
	);

    // Contenu du tableau.	
$contenuTableau = array(
	"", "", "","", 
    "",	"", "", "",
    "",	"", "", "",    
    "",	"", "", "",
    "", "",	"","", 
    "", "", "",	"",
    0, 0, 0, "",
	); 
// Definition des propriétés du reste du contenu du tableau.	
$proprieteContenu = array(
	'T_COLOR' => array(0,0,0),
	'T_SIZE' => 10,
	'T_FONT' => 'Arial',
	'T_ALIGN_COL0' => 'L',
	'T_ALIGN' => 'R',
	'V_ALIGN' => 'M',
	'T_TYPE' => '',
	'LN_SIZE' => 6,
	'BG_COLOR_COL0' => array($R, $G, $B),
	'BG_COLOR' => array(255,255,255),
	'BRD_COLOR' => array(0,0,0),
	'BRD_SIZE' => 0.2,
	'BRD_TYPE' => '1',
	'BRD_TYPE_NEW_PAGE' => '',
	);


$PDF->drawTableau($PDF, $proprietesTableau, $proprieteHeader, $contenuHeader, $proprieteContenu, $contenuTableau);
$PDF->Text(15,180,"Indiquez ci-dessous les Devoirs surveillés, contrôles TP, interrogations écrites concernés:");
$PDF->SetXY(20,182);
$PDF->drawTableau($PDF, $proprietesTableau, $proprieteHeader, $contenuHeader, $proprieteContenu, $contenuTableau);
$PDF->SetXY(20,235);
$PDF->SetFont('Arial','I',10);
$PDF->MultiCell(180,3,'Je déclare avoir fait, ou faire expressément, le nécessaire pour rattraper tous les cours cités ci-dessus, tant au niveau des documents distribués, du déroulement des séances de travail et d’éventuelles évaluations. 
La recevabilité de l’absence sera appréciée par l’équipe de direction.',0,'L',0);
$PDF->SetFont('Arial','B',11);
$PDF->SetFillColor(224,228,216);
$PDF->SetXY(20,260);
$PDF->MultiCell(180,5,"Partie réservée à l'administration:
Absence justifiée : Oui   Non             Autorisé à rattraper les contrôles:  Oui   Non",1,'C',1); 
$PDF->Text(15,250,"Signature du Directeur des études:");
$PDF->Text(125,250,"Signature de l'étudiant:");
$PDF->Text(80,290,"Imprimé le ".date("d/n/Y à H:i"));


$PDF->Ln();
$PDF->Output();
$PDF->Output($nom.".pdf", "D");


?>
<p>&nbsp;</p>
