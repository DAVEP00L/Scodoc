// Affichage progressif du trombinoscope html

$().ready(function () {
    var spans = $(".unloaded_img");
    for (var i = 0; i < spans.length; i++) {
        var sp = spans[i];
        var etudid = sp.id;
        $(sp).load(SCO_URL + '/etud_photo_html?etudid=' + etudid);
    }
});


// L'URL pour recharger l'état courant de la page (groupes et tab selectionnes)
// (ne fonctionne que pour les requetes GET: manipule la query string)

function groups_view_url() {
    var url = $.url();
    delete url.param()['group_ids']; // retire anciens groupes de l'URL
    delete url.param()['curtab']; // retire ancien tab actif
    if (CURRENT_TAB_HASH) {
        url.param()['curtab'] = CURRENT_TAB_HASH;
    }
    delete url.param()['formsemestre_id'];
    url.param()['formsemestre_id'] = $("#group_selector")[0].formsemestre_id.value;

    var selected_groups = $("#group_selector select").val();
    url.param()['group_ids'] = selected_groups;    // remplace par groupes selectionnes

    return url;
}

// Selectionne tous les etudiants et recharge la page:
function select_tous() {
    var url = groups_view_url();
    var default_group_id = $("#group_selector")[0].default_group_id.value;
    delete url.param()['group_ids'];
    url.param()['group_ids'] = [default_group_id];

    var query_string = $.param(url.param(), traditional = true);
    window.location = url.attr('base') + url.attr('path') + '?' + query_string;
}

// L'URL pour l'état courant de la page:
function get_current_url() {
    var url = groups_view_url();
    var query_string = $.param(url.param(), traditional = true);
    return url.attr('base') + url.attr('path') + '?' + query_string;
}

// Recharge la page en changeant les groupes selectionnés et en conservant le tab actif:
function submit_group_selector() {
    window.location = get_current_url();
}

function show_current_tab() {
    $('.nav-tabs [href="#' + CURRENT_TAB_HASH + '"]').tab('show');
}

var CURRENT_TAB_HASH = $.url().param()['curtab'];

$().ready(function () {
    $('.nav-tabs a').on('shown.bs.tab', function (e) {
        CURRENT_TAB_HASH = e.target.hash.slice(1); // sans le #
    });

    show_current_tab();
});

function change_list_options() {
    var url = groups_view_url();
    var selected_options = $("#group_list_options").val();
    var options = ["with_paiement", "with_archives", "with_annotations", "with_codes"];
    for (var i = 0; i < options.length; i++) {
        var option = options[i];
        delete url.param()[option];
        if ($.inArray(option, selected_options) >= 0) {
            url.param()[option] = 1;
        }
    }
    var query_string = $.param(url.param(), traditional = true);
    window.location = url.attr('base') + url.attr('path') + '?' + query_string;
}

// Menu choix groupe:
function toggle_visible_etuds() {
    //
    $(".etud_elem").hide();
    var qargs = "";
    $("#group_ids_sel option:selected").each(function (index, opt) {
        var group_id = opt.value;
        $(".group-" + group_id).show();
        qargs += "&group_ids=" + group_id;
    });
    // Update url saisie tableur:
    var input_eval = $("#formnotes_evaluation_id");
    if (input_eval.length > 0) {
        var evaluation_id = input_eval[0].value;
        $("#menu_saisie_tableur a").attr("href", "saisie_notes_tableur?evaluation_id=" + evaluation_id + qargs);
        // lien feuille excel:
        $("#lnk_feuille_saisie").attr("href", "feuille_saisie_notes?evaluation_id=" + evaluation_id + qargs);
    }
}

$().ready(function () {
    $('#group_ids_sel').multiselect(
        {
            includeSelectAllOption: false,
            nonSelectedText: 'choisir...',
            // buttonContainer: '<div id="group_ids_sel_container"/>',
            onChange: function (element, checked) {
                if (checked == true) {
                    var default_group_id = $(".default_group")[0].value;

                    if (element.hasClass("default_group")) {
                        // click sur groupe "tous"
                        // deselectionne les autres
                        $("#group_ids_sel option:selected").each(function (index, opt) {
                            if (opt.value != default_group_id) {
                                $("#group_ids_sel").multiselect('deselect', opt.value);
                            }
                        });

                    } else {
                        // click sur un autre item
                        // si le groupe "tous" est selectionne et que l'on coche un autre, le deselectionner
                        var default_is_selected = false;
                        $("#group_ids_sel option:selected").each(function (index, opt) {
                            if (opt.value == default_group_id) {
                                default_is_selected = true;
                                return false;
                            }
                        });
                        if (default_is_selected) {
                            $("#group_ids_sel").multiselect('deselect', default_group_id);
                        }
                    }
                }

                toggle_visible_etuds();
                // referme le menu apres chaque choix:
                $("#group_selector .btn-group").removeClass('open');

                if ($("#group_ids_sel").hasClass("submit_on_change")) {
                    submit_group_selector();
                }
            }
        }
    );

    // initial setup
    toggle_visible_etuds();
});

// Trombinoscope
$().ready(function () {

    var elems = $(".trombi-photo");
    for (var i = 0; i < elems.length; i++) {
        $(elems[i]).qtip(
            {
                content: {
                    ajax: {
                        url: SCO_URL + "/etud_info_html?with_photo=0&etudid=" + get_etudid_from_elem(elems[i])
                    },
                    text: "Loading..."
                },
                position: {
                    at: "right",
                    my: "left top"
                },
                style: {
                    classes: 'qtip-etud'
                },
                // utile pour debugguer le css: 
                // hide: { event: 'unfocus' }
            }
        );
    }
});
