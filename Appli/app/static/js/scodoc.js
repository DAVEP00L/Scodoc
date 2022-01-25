// JS for all ScoDoc pages (using jQuery UI)


$(function () {
    // Autocomplete recherche etudiants par nom
    $("#in-expnom").autocomplete(
        {
            delay: 300, // wait 300ms before suggestions
            minLength: 2, // min nb of chars before suggest
            position: { collision: 'flip' }, // automatic menu position up/down
            source: "search_etud_by_name",
            select: function (event, ui) {
                $("#in-expnom").val(ui.item.value);
                $("#form-chercheetud").submit();
            }
        });

    // Date picker
    $(".datepicker").datepicker({
        showOn: 'button',
        buttonImage: '/ScoDoc/static/icons/calendar_img.png',
        buttonImageOnly: true,
        dateFormat: 'dd/mm/yy',
        duration: 'fast',
    });
    $('.datepicker').datepicker('option', $.extend({ showMonthAfterYear: false },
        $.datepicker.regional['fr']));

    /* Barre menu */
    var sco_menu_position = { my: "left top", at: "left bottom" };
    $("#sco_menu").menu({
        position: sco_menu_position,
        blur: function () {
            $(this).menu("option", "position", sco_menu_position);
        },
        focus: function (e, ui) {
            if ($("#sco_menu").get(0) !== $(ui).get(0).item.parent().get(0)) {
                $(this).menu("option", "position", { my: "left top", at: "right top" });
            }
        }
    }).mouseleave(function (x, y) {
        $("#sco_menu").menu('collapseAll');
    });

    $("#sco_menu > li > a > span").switchClass("ui-icon-carat-1-e", "ui-icon-carat-1-s");

    /* Les menus isoles dropdown */
    $(".sco_dropdown_menu").menu({
        position: sco_menu_position
    }).mouseleave(function (x, y) {
        $(".sco_dropdown_menu").menu('collapseAll');
    }
    );
    $(".sco_dropdown_menu > li > a > span").switchClass("ui-icon-carat-1-e", "ui-icon-carat-1-s");

});


// Affiche un message transitoire
function sco_message(msg, color) {
    if (color === undefined) {
        color = "green";
    }
    $('#sco_msg').html(msg).show();
    if (color) {
        $('#sco_msg').css('color', color);
    }
    setTimeout(
        function () {
            $('#sco_msg').fadeOut(
                'slow',
                function () {
                    $('#sco_msg').html('');
                }
            );
        },
        2000 // <-- duree affichage en milliseconds  
    );
}


function get_query_args() {
    var s = window.location.search; // eg "?x=1&y=2"
    var vars = {};
    s.replace(
        /[?&]+([^=&]+)=?([^&]*)?/gi, // regexp
        function (m, key, value) { // callback
            vars[key] = value !== undefined ? value : '';
        }
    );
    return vars;
}


// Tables (gen_tables)
$(function () {
    $('table.gt_table').DataTable({
        "paging": false,
        "searching": false,
        "info": false,
        /* "autoWidth" : false, */
        "fixedHeader": {
            "header": true,
            "footer": true
        },
        "orderCellsTop": true, // cellules ligne 1 pour tri 
        "aaSorting": [], // Prevent initial sorting
    });
});


// Show tags (readonly)
function readOnlyTags(nodes) {
    // nodes are textareas, hide them and create a span showing tags
    for (var i = 0; i < nodes.length; i++) {
        var node = $(nodes[i]);
        node.hide();
        var tags = nodes[i].value.split(',');
        node.after('<span class="ro_tags"><span class="ro_tag">' + tags.join('</span><span class="ro_tag">') + '</span></span>');
    }
}
