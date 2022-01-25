
$(function () {
    $("div#export_help").accordion({
        heightStyle: "content",
        collapsible: true,
        active: false,
    });
});

// Affichage des listes par type
// routine de traitement d'évènement javascript à associé au lien
// présents dans le tableau effectifs
// -> filtre la liste étudiant sur critère de classe
// -> surligne le cas sélectionné

function display(r, c, row, col) {
    if ((row != r) && (row != '*')) return 'none';
    if ((col != c) && (col != '*')) return 'none';
    return '';
}

function show_tag(all_rows, all_cols, tag) {
    // Filtrer tous les étudiants
    all_rows.split(',').forEach(function (r) {
        all_cols.split(',').forEach(function (c) {
            etudiants = r + c.substring(1);
            $(etudiants).css("display", "none");
        })
    })
    // sauf le tag
    $('.' + tag).css('display', '');
}

function show_filtres(effectifs, filtre_row, filtre_col) {
    $("#compte").html(effectifs);
    if ((filtre_row == '') && (filtre_col == '')) {
        $("#sans_filtre").css("display", "");
        $("#filtre_row").css("display", "none");
        $("#filtre_col").css("display", "none");
    } else {
        $("#sans_filtre").css("display", "none");
        if (filtre_row == '') {
            $("#filtre_row").css("display", "none");
            $("#filtre_col").css("display", "");
            $("#filtre_col").html("Filtre sur code étape: " + filtre_col);
        } else if (filtre_col == '') {
            $("#filtre_row").css("display", "");
            $("#filtre_col").css("display", "none");
            $("#filtre_row").html("Filtre sur semestre: " + filtre_row);
        } else {
            $("#filtre_row").css("display", "");
            $("#filtre_col").css("display", "");
            $("#filtre_row").html("Filtre sur semestre: " + filtre_row);
            $("#filtre_col").html("Filtre sur code étape: " + filtre_col);
        }
    }
}

function doFiltrage(all_rows, all_cols, row, col, effectifs, filtre_row, filtre_col) {
    show_filtres(effectifs, filtre_row, filtre_col)
    all_rows.split(',').forEach(function (r) {
        all_cols.split(',').forEach(function (c) {
            etudiants = r + c.substring(1);
            $(etudiants).css("display", display(r, c, row, col));
        });
    });

    $('.repartition td').css("background-color", "");
    $('.repartition th').css("background-color", "");

    if (row == '*' && col == '*') {     // Aucun filtre
    } else if (row == '*') {            // filtrage sur 1 colonne
        $(col).css("background-color", "lightblue");
    } else if (col == '*') {            // Filtrage sur 1 ligne
        $(row + '>td').css("background-color", "lightblue");
        $(row + '>th').css("background-color", "lightblue");
    } else {                            // filtrage sur 1 case
        $(row + '>td' + col).css("background-color", "lightblue");
    }

    // Modifie le titre de la section pour indiquer la sélection:
    // elt est le lien cliqué
    // var td_class = elt.parentNode.className.trim();
    // if (td_class) {
    //     var titre_col = $("table.repartition th.")[0].textContent.trim();
    //     if (titre_col) {
    //         $("h4#effectifs").html("Liste des étudiants de " + titre_col);
    //     }
    // }
}
