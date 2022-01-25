// Affiche carte google map des lycees

var ScoMarkerIcons = {};

$().ready(function(){
    $('#lyc_map_canvas').gmap(
	{ 'center': '48.955741,2.34141', 
	  'zoom' : 8,
	  'mapTypeId': google.maps.MapTypeId.ROADMAP
	}).bind('init', function(event, map) {
	    for (var i =0; i < lycees_coords.length; i++) {
		var lycee = lycees_coords[i];
		var nb = lycee['number'];
		var icon;
		if (nb in ScoMarkerIcons) {
		    icon = ScoMarkerIcons[nb];
		} else {
		    icon = new google.maps.MarkerImage( 'https://chart.apis.google.com/chart?chst=d_map_pin_letter&chld=' + nb + '|FF0000|000000' );
		    ScoMarkerIcons[nb] = icon; // cache
		}
		$('#lyc_map_canvas').gmap(
		    'addMarker', 
		    {'position': lycee['position'], 'bounds': true, 'nomlycee' : lycee['name'], 'icon' : icon } 
		).click(
		    function() {
			$('#lyc_map_canvas').gmap('openInfoWindow', {'content': this.nomlycee}, this);
		    }
		);
	    }
	});
});



