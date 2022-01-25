/* -*- mode: javascript -*-
 */

function getMouseXY(e) // works on IE6,FF,Moz,Opera7
{ 
  if (!e) e = window.event; // works on IE, but not NS (we rely on NS passing us the event)

  if (e)
  { 
    if (e.pageY)
    { // this doesn't work on IE6!! (works on FF,Moz,Opera7)
      mousey = e.pageY;
      algor = '[e.pageX]';
      if (e.clientX || e.clientY) algor += ' [e.clientX] '
    }
    else if (e.clientY)
    { // works on IE6,FF,Moz,Opera7
if ( document.documentElement && document.documentElement.scrollTop )	
	{
      mousey = e.clientY + document.documentElement.scrollTop;
	}
	
	else
	{
      mousey = e.clientY + document.body.scrollTop;
	}
      algor = '[e.clientX]';
      if (e.pageX || e.pageY) algor += ' [e.pageX] '
    }
  }
}

var menu_firefox_flicker = false ;


var mousey = 0

function MenuDisplay(l_element)
	{
	getMouseXY()
	if ( ! menu_firefox_flicker )
		{
		l_element.childNodes[1].style.display = 'block' ;
		if ( mousey > 600 )
			{
			l_element.childNodes[1].style.left = '0px' ;
			l_element.childNodes[1].style.display = 'block' ;
			l_element.childNodes[1].style.top = - l_element.childNodes[1].offsetHeight + 'px' ;
			}
		}
	else if ( mousey > 600 )
		{
		l_element.childNodes[1].style.top = - l_element.childNodes[1].offsetHeight + 'px' ;
		}
	}
	
function MenuHide(l_element)
	{
	if ( ! menu_firefox_flicker )
		{
		l_element.childNodes[1].style.display = 'none'
		}
	}
