//
// Diagramme "radar" montrant les notes d'un étudiant
//
// ScoDoc, (c) E. Viennet 2012
//
// Ce code utilise d3.js



var WIDTH = 460; // taille du canvas SVG
var HEIGHT = WIDTH;
var CX = WIDTH/2; // coordonnees centre du cercle
var CY = HEIGHT/2; 
var RR = 0.4*WIDTH; // Rayon du cercle exterieur

/* Emplacements des marques (polygones et axe gradué) */
var R_TICS = [ 8, 10, 20 ]; /* [6, 8, 10, 12, 14, 16, 18, 20]; */
var R_AXIS_TICS = [4, 6, 8, 10, 12, 14, 16, 18, 20];
var NB_TICS = R_TICS.length;


        draw_radar(notes); 


function draw_radar(notes) {
    /* Calcul coordonnées des éléments */
    var nmod = notes.length;
    var angle = 2*Math.PI/nmod;

    for (var i=0; i<notes.length; i++) {
        var d = notes[i];
        var cx = Math.sin(i*angle);
        var cy = - Math.cos(i*angle);
        d["x_v"] = CX + RR * d.note/20 * cx;
        d["y_v"] = CY + RR * d.note/20 * cy;
        d["x_moy"] = CX + RR * d.moy/20 * cx;
        d["y_moy"] = CY + RR * d.moy/20 * cy;
        d["x_20"] = CX + RR * cx;
        d["y_20"] = CY + RR * cy;
        d["x_label"] = CX + (RR + 25) * cx - 10
        d["y_label"] = CY + (RR + 25) * cy + 10;
        d["tics"] = [];
        // Coords des tics sur chaque axe
        for (var j=0; j < NB_TICS; j++) {
            var r = R_TICS[j]/20 * RR;
            d["tics"][j] = { "x" : CX + r * cx, "y" : CY + r * cy };        
        }
    }

    var notes_circ = notes.slice(0);
    notes_circ.push(notes[0])
    var notes_circ_valid = notes_circ.filter( function(e,i,a) { return e.note != 'NA' && e.note != '-'; } );
    var notes_valid = notes.filter( function(e,i,a) { return e.note != 'NA' && e.note != '-'; } )

    /* Crée l'élément SVG */
    g = d3.select("#radar_bulletin").append("svg")
        .attr("class", "radar")
        .attr("width", WIDTH)
        .attr("height", HEIGHT);

    /* Centre */
    g.append( "circle" ).attr("cy", CY)
        .attr("cx", CX)
        .attr("r", 2)
        .attr("class", "radar_center_mark");

    /* Lignes "tics" */
    for (var j=0; j < NB_TICS; j++) {
        var ligne_tics = d3.svg.line() 
            .x(function(d) { return d["tics"][j]["x"]; })
            .y(function(d) { return d["tics"][j]["y"]; });
        g.append( "svg:path" )
            .attr("class", "radar_disk_tic")
            .attr("id", "radar_disk_tic_" +  R_TICS[j])
            .attr("d", ligne_tics(notes_circ));
    }

    /* Lignes radiales pour chaque module */
    g.selectAll("radar_rad")
        .data(notes)
        .enter().append("line")
        .attr("x1", CX)
        .attr("y1", CY)
        .attr("x2", function(d) { return d["x_20"]; })
        .attr("y2", function(d) { return d["y_20"]; })
        .attr("class", "radarrad");


    /* Lignes entre notes */
    var ligne = d3.svg.line() 
        .x(function(d) { return d["x_v"]; })
        .y(function(d) { return d["y_v"]; });

    g.append( "svg:path" )
        .attr("class", "radarnoteslines")
        .attr("d", ligne(notes_circ_valid));

    var ligne_moy = d3.svg.line() 
        .x(function(d) { return d["x_moy"]; })
        .y(function(d) { return d["y_moy"]; })

    g.append( "svg:path" )
        .attr("class", "radarmoylines")
        .attr("d", ligne_moy(notes_circ_valid));

    /* Points (notes) */
    g.selectAll("circle1")
        .data(notes_valid)
        .enter().append("circle")
        .attr("cx", function(d) { return d["x_v"]; })
        .attr("cy", function(d) { return d["y_v"]; })
        .attr("r", function(x, i) { return 3; } )
        .style("stroke-width", 1)
        .style("stroke", "black")
        .style("fill", "blue")
        .on("mouseover", function(d) {
	        var rwidth = 290;
	        var x = d["x_v"];
	        if (x + rwidth + 12 > WIDTH) {
	            x = WIDTH - rwidth - 12;
	        }
	        var r = g.append("rect")
	            .attr('class','radartip')
	            .attr("x", x + 5)
                .attr("y", d["y_v"] + 5 );
	        
	        var txt = g.append("text").text("Note: " +  d.note + "/20, moyenne promo: " + d.moy + "/20")
	            .attr('class','radartip')
	            .attr("x", x + 5 + 5)
                .attr("y", d["y_v"] + 5 + 16 );
	        r.attr("width", rwidth).attr("height", 20);
        })
        .on("mouseout", function(d){
            d3.selectAll(".radartip").remove()
        });

    /* Valeurs des notes */
    g.selectAll("notes_labels")
        .data(notes_valid)
        .enter().append("text")
        .text(function(d) { return d["note"]; })
        .attr("x", function(d) { 
            return d["x_v"]; 
        })
        .attr("y", function(d) { 
            if (d["y_v"] > CY)
                return d["y_v"] + 16;
            else
                return d["y_v"] - 8;
        })
        .attr("class", "note_label");

    /* Petits points sur les poyennes */
    g.selectAll("circle2")
        .data(notes_valid)
        .enter().append("circle")
        .attr("cx", function(d) { return d["x_moy"]; })
        .attr("cy", function(d) { return d["y_moy"]; })
        .attr("r", function(x, i) { return 2; } )
        .style("stroke-width", 0)
        .style("stroke", "black")
        .style("fill", "rgb(20,90,50)");

    /* Valeurs sur axe */
    g.selectAll("textaxis")
        .data( R_AXIS_TICS )
        .enter().append("text")
        .text(String)
        .attr("x", CX - 10)
        .attr("y", function(x, i) { return CY - x*RR/20 + 6; })
        .attr("class", "textaxis");

    /* Noms des modules */
    g.selectAll("text_modules")
        .data(notes)
        .enter().append("text")
        .text( function(d) { return d['code']; } )
        .attr("x", function(d) { return d['x_label']; } )
        .attr("y", function(d) { return d['y_label']; })
        .attr("dx", 0)
        .attr("dy", 0);
}