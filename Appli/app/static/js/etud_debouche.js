// Cadre "debouchés" sur fiche etudiant
// affichage et saisie des informations sur l'avenir de l'étudiant.

// console.log('etud_debouche.js loaded');

$(function () {
    display_itemsuivis(false);
});


function display_itemsuivis(active) {
    var etudid = $('div#fichedebouche').data("etudid");
    var readonly = $('div#fichedebouche').data('readonly'); // present ro interface

    if (!readonly) {
        $('#adddebouchelink').off("click").click(function (e) {
            e.preventDefault();
            $.post(SCO_URL + "/itemsuivi_create", { etudid: etudid, format: 'json' }).done(item_insert_new);

            return false;
        });
    }
    // add existing items
    $.get(SCO_URL + "/itemsuivi_list_etud", { etudid: etudid, format: 'json' }, function (L) {
        for (var i in L) {
            item_insert(L[i]['itemsuivi_id'], L[i]['item_date'], L[i]['situation'], L[i]['tags'], readonly);
        }
    });

    $("div#fichedebouche").accordion({
        heightStyle: "content",
        collapsible: true,
        active: active,
    });
}

function item_insert_new(it) {
    item_insert(it.itemsuivi_id, it.item_date, it.situation, '', false);
}

function item_insert(itemsuivi_id, item_date, situation, tags, readonly) {
    if (item_date === undefined)
        item_date = Date2DMY(new Date());
    if (situation === undefined)
        situation = '';
    if (tags === undefined)
        tags = '';

    var nodes = item_nodes(itemsuivi_id, item_date, situation, tags, readonly);
    // insert just before last li:
    if ($('ul.listdebouches li.adddebouche').length > 0) {
        $('ul.listdebouches').children(':last').before(nodes);
    } else {
        // mode readonly, pas de li "ajouter"
        $('ul.listdebouches').append(nodes);
    }
};

function item_nodes(itemsuivi_id, item_date, situation, tags, readonly) {
    // console.log('item_nodes: itemsuivi_id=' + itemsuivi_id);
    var sel_mois = 'Situation à la date du <input type="text" class="itemsuividatepicker" size="10" value="' + item_date + '"/><span class="itemsuivi_suppress" onclick="itemsuivi_suppress(\'' + itemsuivi_id + '\')"><img width="10" height="9" border="0" title="" alt="supprimer cet item" src="/ScoDoc/static/icons/delete_small_img.png"/></span>';

    var h = sel_mois;
    // situation
    h += '<div class="itemsituation editable" data-type="textarea" data-url="itemsuivi_set_situation" data-placeholder="<em>décrire situation...</em>" data-object="' + itemsuivi_id + '">' + situation + '</div>';
    // tags:
    h += '<div class="itemsuivi_tag_edit"><textarea class="itemsuivi_tag_editor">' + tags + '</textarea></div>';

    var nodes = $($.parseHTML('<li class="itemsuivi">' + h + '</li>'));
    var dp = nodes.find('.itemsuividatepicker');
    dp.blur(function (e) {
        var date = this.value;
        // console.log('selected text: ' + date);
        $.post(SCO_URL + "/itemsuivi_set_date", { item_date: date, itemsuivi_id: itemsuivi_id });
    });
    dp.datepicker({
        onSelect: function (date, instance) {
            // console.log('selected: ' + date + 'for itemsuivi_id ' + itemsuivi_id);
            $.post(SCO_URL + "/itemsuivi_set_date", { item_date: date, itemsuivi_id: itemsuivi_id });
        },
        showOn: 'button',
        buttonImage: '/ScoDoc/static/icons/calendar_img.png',
        buttonImageOnly: true,
        dateFormat: 'dd/mm/yy',
        duration: 'fast',
        disabled: readonly
    });
    dp.datepicker('option', $.extend({ showMonthAfterYear: false },
        $.datepicker.regional['fr']));

    if (readonly) {
        // show tags read-only
        readOnlyTags(nodes.find('.itemsuivi_tag_editor'));
    }
    else {
        // bind tag editor
        nodes.find('.itemsuivi_tag_editor').tagEditor({
            initialTags: '',
            placeholder: 'Tags...',
            onChange: function (field, editor, tags) {
                $.post('itemsuivi_tag_set',
                    {
                        itemsuivi_id: itemsuivi_id,
                        taglist: tags.join()
                    });
            },
            autocomplete: {
                delay: 200, // ms before suggest
                position: { collision: 'flip' }, // automatic menu position up/down
                source: "itemsuivi_tag_search"
            },
        });

        // bind inplace editor
        nodes.find('div.itemsituation').jinplace();
    }

    return nodes;
};

function Date2DMY(date) {
    var year = date.getFullYear();

    var month = (1 + date.getMonth()).toString();
    month = month.length > 1 ? month : '0' + month;

    var day = date.getDate().toString();
    day = day.length > 1 ? day : '0' + day;

    return day + '/' + month + '/' + year;
}

function itemsuivi_suppress(itemsuivi_id) {
    $.post(SCO_URL + "/itemsuivi_suppress", { itemsuivi_id: itemsuivi_id });
    // Clear items and rebuild:
    $("ul.listdebouches li.itemsuivi").remove();
    display_itemsuivis(0);
}
