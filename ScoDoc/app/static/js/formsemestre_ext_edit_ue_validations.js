


function compute_moyenne() {
    var notes = $(".tf_field_note input").map( 
        function() {  return parseFloat($(this).val());  } 
    ).get();
    var coefs = $(".tf_field_coef input").map( 
        function() {  return parseFloat($(this).val());  } 
    ).get();
    var N = notes.length;
    var dp = 0.;
    var sum_coefs = 0.;
    for (var i=0; i < N; i++) {
        if (!(isNaN(notes[i]) || isNaN(coefs[i]))) {
            dp += notes[i] * coefs[i];
            sum_coefs += coefs[i];
        }
    }
    return dp / sum_coefs;    
}

// Callback select menu (UE code)
function enable_disable_fields_cb() {
    enable_disable_fields(this);
}
function enable_disable_fields(select_elt) {    
    // input fields controled by this menu
    var input_fields = $(select_elt).parent().parent().find('input');
    var disabled = false;
    if ($(select_elt).val() === "None") {
        disabled = true;
    }
    console.log('disabled=', disabled);
    input_fields.each( function () {
        var old_state = this.disabled;
        console.log("old_state=", old_state)
        if (old_state == disabled) {
            return; /* state unchanged */
        }
        var saved_value = $(this).data('saved-value');
        if (typeof saved_value == 'undefined') {
            saved_value = '';
        }
        var cur_value = $(this).val();
        // swap
        $(this).data('saved-value', cur_value);
        $(this).val(saved_value);
    });
    input_fields.prop('disabled', disabled);
}
function setup_text_fields() {
    $(".ueext_valid_select").each(
        function() {
            enable_disable_fields(this);
        }
    );
}

$().ready(function(){
    $(".tf_ext_edit_ue_validations").change(function (){
        $(".ext_sem_moy_val")[0].innerHTML=compute_moyenne();
    });
    $(".ueext_valid_select").change( enable_disable_fields_cb );

    setup_text_fields();
});
