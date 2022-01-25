/* -*- mode: javascript -*-
 *
 * Selection semaine sur calendrier Absences
 *
 * E. Viennet, Oct 2006
 */

var WEEKDAYCOLOR = "#EEEEEE";
var WEEKENDCOLOR = "#99CC99";
var DAYHIGHLIGHT = "red";
var CURRENTWEEKCOLOR = "yellow";

// get all tr elements from this class
// (no getElementBuClassName)
function getTRweek( week ) { 
  var tablecal = document.getElementById('maincalendar');
  var all = tablecal.getElementsByTagName('tr');
  var res = [] ;
  for(var i=0; i < all.length; i++) {
    if (all[i].className == week)
      res[res.length] = all[i];
  }
  return res;
}

var HIGHLIGHTEDCELLS = [];

function deselectweeks() {
  
  for(var i=0; i < HIGHLIGHTEDCELLS.length; i++) {
    var row = rows[i];
    if (row) {
      if (row.className.match('currentweek')) {
	row.style.backgroundColor = CURRENTWEEKCOLOR;
      } else {
	row.style.backgroundColor = WEEKDAYCOLOR;
      }
      rows[i] = null;
    }
  }
}

// highlight 5 days
function highlightweek(el) {
  deselectweeks();
  var week = el.className;
  if ((week == 'wkend') || (week.substring(0,2) != 'wk')) {
    return; /* does not hightlight weekends */
  }
  rows = getTRweek(week);
  for (var i=0; i < rows.length; i++) {
    var row = rows[i];
    row.style.backgroundColor = DAYHIGHLIGHT;
    HIGHLIGHTEDCELLS[HIGHLIGHTEDCELLS.length] = row;
  }
}

// click on a day
function wclick(el) {
  monday = el.className;
  form = document.getElementById('formw');
  form.datelundi.value = monday.substr(2).replace(/_/g,'/').split(' ')[0];
  form.submit();
}
