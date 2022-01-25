// Gestion formulaire UE externes

function toggle_new_ue_form(state) {
    // active/desactive le formulaire "nouvelle UE"
    var text_color;
    if (state) {
        text_color = 'rgb(180,160,160)';
    } else {
        text_color = 'rgb(0,0,0)';
    }

    $("#tf_extue_titre td:eq(1) input").prop( "disabled", state );
    $("#tf_extue_titre td:eq(1) input").css('color', text_color)

    $("#tf_extue_acronyme td:eq(1) input").prop( "disabled", state );
    $("#tf_extue_acronyme td:eq(1) input").css('color', text_color)

    $("#tf_extue_ects td:eq(1) input").prop( "disabled", state );
    $("#tf_extue_ects td:eq(1) input").css('color', text_color)
}


function update_external_ue_form() {
    var state = (tf.existing_ue.value != "")
    toggle_new_ue_form(state);
}




