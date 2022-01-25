

function _partition_set_attr(partition_id, attr_name, attr_value) {
    $.post(SCO_URL + '/partition_set_attr',
        {
            'partition_id': partition_id,
            'attr': attr_name,
            'value': attr_value
        },
        function (result) {
            sco_message(result);
        });
    return;
}

// Met à jour bul_show_rank lorsque checkbox modifiees:
function update_rk(e) {
    var partition_id = $(e).attr('data-partition_id');
    var v;
    if (e.checked)
        v = '1';
    else
        v = '0';
    _partition_set_attr(partition_id, 'bul_show_rank', v);
}


function update_show_in_list(e) {
    var partition_id = $(e).attr('data-partition_id');
    var v;
    if (e.checked)
        v = '1';
    else
        v = '0';

    _partition_set_attr(partition_id, 'show_in_lists', v);
}

