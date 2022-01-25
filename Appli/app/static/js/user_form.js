
function refresh() {
    if ($("input[name='welcome:list']").is(":checked")) {
        $("input[name='reset_password:list']").closest("tr").css("display", "table-row")
        if ($("input[name='reset_password:list']").is(":checked")) {
            $("#tf_password").closest('tr').css("display", "none");
            $("#tf_password2").closest('tr').css("display", "none");
        } else {
            // Le mot de passe doit être saisi
            $("#tf_password").closest('tr').css("display", "table-row");
            $("#tf_password2").closest('tr').css("display", "table-row");
        }
    } else {
        // Le mot de passe doit être saisi
        $("input[name='reset_password:list']").closest("tr").css("display", "none")
        $("#tf_password").closest('tr').css("display", "table-row");
        $("#tf_password2").closest('tr').css("display", "table-row");
    }
}

$(function () {
    $("input[name='welcome:list']").click(function () {
        refresh();
    })
    $("input[name='reset_password:list']").click(function () {
        refresh();
    })
    refresh();
})

