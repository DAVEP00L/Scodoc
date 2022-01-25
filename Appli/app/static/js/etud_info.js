// Affiche popup avec info sur etudiant (pour les listes d'etudiants)
// affecte les elements de classe "etudinfo" portant l'id d'un etudiant
// utilise jQuery / qTip

function get_etudid_from_elem(e) {
    // renvoie l'etudid, obtenu a partir de l'id de l'element
    // qui est soit de la forme xxxx-etudid, soit tout simplement etudid
    var etudid = e.id.split("-")[1];
    if (etudid == undefined) {
        return e.id;
    } else {
        return etudid;
    }
}

$().ready(function () {

    var elems = $(".etudinfo");

    var q_args = get_query_args();
    var args_to_pass = new Set(
        ["formsemestre_id", "group_ids", "group_id", "partition_id",
            "moduleimpl_id", "evaluation_id"
        ]);
    var qs = "";
    for (var k in q_args) {
        if (args_to_pass.has(k)) {
            qs += '&' + k + '=' + q_args[k];
        }
    }
    for (var i = 0; i < elems.length; i++) {
        $(elems[i]).qtip({
            content: {
                ajax: {
                    url: SCO_URL + "/etud_info_html?etudid=" + get_etudid_from_elem(elems[i]) + qs,
                    type: "GET"
                    //success: function(data, status) {
                    //    this.set('content.text', data);
                    //    xxx called twice on each success ???
                    //    console.log(status);
                }
            },
            text: "Loading...",
            position: {
                at: "right bottom",
                my: "left top"
            },
            style: {
                classes: 'qtip-etud'
            },
            hide: {
                fixed: true,
                delay: 300
            }
            // utile pour debugguer le css: 
            // hide: { event: 'unfocus' }
        });
    }
});


