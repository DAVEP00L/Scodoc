// Affiche et met a jour la liste des UE partageant le meme code

$().ready(function () {
    update_ue_validations();
    update_ue_list();
    $("#tf_ue_id").bind("change", update_ue_list);
    $("#tf_ue_id").bind("change", update_ue_validations);
});


function update_ue_list() {
    var ue_id = $("#tf_ue_id")[0].value;
    if (ue_id) {
        var query = "ue_sharing_code?ue_id=" + ue_id;
        $.get(query, '', function (data) {
            $("#ue_list_code").html(data);
        });
    }
}

function update_ue_validations() {
    var etudid = $("#tf_etudid")[0].value;
    var ue_id = $("#tf_ue_id")[0].value;
    var formsemestre_id = $("#tf_formsemestre_id")[0].value;
    if (ue_id) {
        var query = SCO_URL + "/Notes/get_etud_ue_cap_html?ue_id=" + ue_id + "&etudid=" + etudid + "&formsemestre_id=" + formsemestre_id;
        $.get(query, '', function (data) {
            $("#ue_list_etud_validations").html(data);
        });
    }
}