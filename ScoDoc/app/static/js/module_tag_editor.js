// Edition tags sur modules


$(function() {
    $('.module_tag_editor').tagEditor({
        initialTags: '',
        placeholder: 'Tags du module ...',
	forceLowercase: false,
        onChange: function(field, editor, tags) {
            $.post('module_tag_set', 
                   {
                       module_id: field.data("module_id"),
                       taglist: tags.join()
                   });
        },
        autocomplete: {
            delay: 200, // ms before suggest
            position: { collision: 'flip' }, // automatic menu position up/down
            source: "module_tag_search"
        },
    });

    // version readonly
    readOnlyTags($('.module_tag_editor_ro'));

    
    $('.sco_tag_checkbox').click(function() {
        if( $(this).is(':checked')) {
            $(".sco_tag_edit").show();
        } else {
            $(".sco_tag_edit").hide();
        }
    }); 

});
