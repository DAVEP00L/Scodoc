// Export table tous les resultats

// Menu choix parcours:
$(function() {
    $('#parcours_sel').multiselect(
	{
	    includeSelectAllOption: true,
	    nonSelectedText:'Choisir le(s) parcours...',
	    selectAllValue: '',
	    numberDisplayed: 3,
	}
    );
});

