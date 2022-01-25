// Affiche et met a jour la liste des UE partageant le meme code

$().ready(function () {
    update_ue_list();
    $("#tf_ue_code").bind("keyup", update_ue_list);
});


function update_ue_list() {
    var ue_id = $("#tf_ue_id")[0].value;
    var ue_code = $("#tf_ue_code")[0].value;
    var query = SCO_URL + "/Notes/ue_sharing_code?ue_code=" + ue_code + "&hide_ue_id=" + ue_id + "&ue_id=" + ue_id;
    $.get(query, '', function (data) {
        $("#ue_list_code").html(data);
    });
}
