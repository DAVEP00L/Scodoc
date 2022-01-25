// Affichage progressif du trombinoscope html

$().ready(function () {
    var spans = $(".unloaded_img");
    for (var i = 0; i < spans.size(); i++) {
        var sp = spans[i];
        var etudid = sp.id;
        $(sp).load(SCO_URL + "/etud_photo_html?etudid=" + etudid);
    }
});

