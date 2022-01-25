
// JS Ajax code for SignaleAbsenceGrSemestre
// Contributed by YLB

function ajaxFunction(mod, etudid, dat) {
	var ajaxRequest;  // The variable that makes Ajax possible!

	try {
		// Opera 8.0+, Firefox, Safari
		ajaxRequest = new XMLHttpRequest();
	} catch (e) {
		// Internet Explorer Browsers
		try {
			ajaxRequest = new ActiveXObject("Msxml2.XMLHTTP");
		} catch (e) {
			try {
				ajaxRequest = new ActiveXObject("Microsoft.XMLHTTP");
			} catch (e) {
				// Something went wrong
				alert("Your browser broke!");
				return false;
			}
		}
	}
	// Create a function that will receive data sent from the server
	ajaxRequest.onreadystatechange = function () {
		if (ajaxRequest.readyState == 4 && ajaxRequest.status == 200) {
			document.getElementById("AjaxDiv").innerHTML = ajaxRequest.responseText;
		}
	}
	ajaxRequest.open("POST", SCO_URL + "/Absences/doSignaleAbsenceGrSemestre", true);
	ajaxRequest.setRequestHeader("Content-type", "application/x-www-form-urlencoded");
	var oSelectOne = $("#abs_form")[0].elements["moduleimpl_id"];
	var index = oSelectOne.selectedIndex;
	var modul_id = oSelectOne.options[index].value;
	if (mod == 'add') {
		ajaxRequest.send("reply=0&moduleimpl_id=" + modul_id + "&abslist:list=" + etudid + ":" + dat);
	}
	if (mod == 'remove') {
		ajaxRequest.send("reply=0&moduleimpl_id=" + modul_id + "&etudids=" + etudid + "&dates=" + dat);
	}
}

// -----
function change_moduleimpl(url) {
	document.location = url + '&moduleimpl_id=' + document.getElementById('moduleimpl_id').value;
}
