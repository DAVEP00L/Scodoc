// Formulaire saisie des notes

$().ready(function () {

    $("#formnotes .note").bind("blur", valid_note);

    $("#formnotes input").bind("paste", paste_text);

});

function is_valid_note(v) {
    if (!v)
        return true;

    var note_min = parseFloat($("#eval_note_min").text());
    var note_max = parseFloat($("#eval_note_max").text());

    if (!v.match("^-?[0-9.]*$")) {
        return (v == "ABS") || (v == "EXC") || (v == "SUPR") || (v == "ATT") || (v == "DEM");
    } else {
        var x = parseFloat(v);
        return (x >= note_min) && (x <= note_max);
    }
}

function valid_note(e) {
    var v = this.value.trim().toUpperCase().replace(",", ".");
    if (is_valid_note(v)) {
        if (v && (v != $(this).attr('data-last-saved-value'))) {
            this.className = "note_valid_new";
            var etudid = $(this).attr('data-etudid');
            save_note(this, v, etudid);
        }
    } else {
        /* Saisie invalide */
        this.className = "note_invalid";
    }
}

function save_note(elem, v, etudid) {
    var evaluation_id = $("#formnotes_evaluation_id").attr("value");
    var formsemestre_id = $("#formnotes_formsemestre_id").attr("value");
    $('#sco_msg').html("en cours...").show();
    $.post(SCO_URL + '/Notes/save_note',
        {
            'etudid': etudid,
            'evaluation_id': evaluation_id,
            'value': v,
            'comment': $("#formnotes_comment").attr("value")
        },
        function (result) {
            sco_message("enregistré");
            elem.className = "note_saved";
            if (result['nbchanged'] > 0) {
                // il y avait une decision de jury ?
                if (result.existing_decisions[0] == etudid) {
                    if (v != $(elem).attr('data-orig-value')) {
                        $("#jurylink_" + etudid).html('<a href="formsemestre_validation_etud_form?formsemestre_id=' + formsemestre_id + '&etudid=' + etudid + '">mettre à jour décision de jury</a>');
                    } else {
                        $("#jurylink_" + etudid).html('');
                    }
                }
                // mise a jour menu historique
                if (result['history_menu']) {
                    $("#hist_" + etudid).html(result['history_menu']);
                }
            }
            $(elem).attr('data-last-saved-value', v)
        }
    );
}

function change_history(e) {
    var opt = e.selectedOptions[0];
    var val = $(opt).attr("data-note");
    var etudid = $(e).attr('data-etudid');
    // le input associé a ce menu:
    var input_elem = e.parentElement.parentElement.parentElement.childNodes[0];
    input_elem.value = val;
    save_note(input_elem, val, etudid);
}

// Contribution S.L.: copier/coller des notes


function paste_text(e) {
    var event = e.originalEvent;
    event.stopPropagation();
    event.preventDefault();
    var clipb = e.originalEvent.clipboardData;
    var data = clipb.getData('Text');
    var list = data.split(/\r\n|\r|\n|\t| /g);
    var currentInput = event.currentTarget;

    for (var i = 0; i < list.length; i++) {
        currentInput.value = list[i];
        var evt = document.createEvent("HTMLEvents");
        evt.initEvent("blur", false, true);
        currentInput.dispatchEvent(evt);
        var sibbling = currentInput.parentElement.parentElement.nextElementSibling;
        while (sibbling && sibbling.style.display == "none") {
            sibbling = sibbling.nextElementSibling;
        }
        if (sibbling) {
            currentInput = sibbling.querySelector("input");
            if (!currentInput) {
                return;
            }
        } else {
            return;
        }
    }
}
