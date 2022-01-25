// Affichage bulletin de notes
// (uses jQuery)


// Change visibility of UE details (les <tr> de classe "notes_bulletin_row_mod" suivant)
// La table a la structure suivante:
//  <tr class="notes_bulletin_row_ue"><td><span class="toggle_ue">+/-</span>...</td>...</tr>
//  <tr class="notes_bulletin_row_mod">...</tr>
//  <tr class="notes_bulletin_row_eval">...</tr>
//
// On change la visi de tous les <tr> jusqu'au notes_bulletin_row_ue suivant.
//
function toggle_vis_ue(e, new_state) { 
    // e is the span containg the clicked +/- icon
    var tr = e.parentNode.parentNode;
    if (new_state == undefined) {
	// current state: use alt attribute of current image
	if (e.childNodes[0].alt == '+') {
            new_state=false;
	} else {
            new_state=true;
	}
    } 
    // find next tr in siblings
    var tr = tr.nextSibling;
    //while ((tr != null) && sibl.tagName == 'TR') {
    var current = true;
    while ((tr != null) && current) {
	if ((tr.nodeType==1) && (tr.tagName == 'TR')) {
	    for (var i=0; i < tr.classList.length; i++) {
		if (tr.classList[i] == 'notes_bulletin_row_ue') 
		    current = false;
 	    }
	    if (current) {
		if (new_state) {
		    tr.style.display = 'none';
		} else {
		    tr.style.display = 'table-row';
		}
	    }
        }
        tr = tr.nextSibling;	
    }
    if (new_state) {
	e.innerHTML = '<img width="13" height="13" border="0" title="" alt="+" src="icons/plus_img.png"/>';
    } else {
	e.innerHTML = '<img width="13" height="13" border="0" title="" alt="-" src="icons/minus_img.png"/>';
    }
}

