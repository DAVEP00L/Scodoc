if(typeof(bsn)=="undefined")_b=bsn={};if(typeof(_b.Autosuggest)=="undefined")_b.Autosuggest={};else alert("Autosuggest is already set!");_b.AutoSuggest=function(b,c){if(!document.getElementById)return 0;this.fld=_b.DOM.gE(b);if(!this.fld)return 0;this.sInp="";this.nInpC=0;this.aSug=[];this.iHigh=0;this.oP=c?c:{};var k,def={minchars:1,meth:"get",varname:"input",className:"autosuggest",timeout:2500,delay:500,offsety:-5,shownoresults:true,noresults:"No results!",maxheight:250,cache:true,maxentries:25};for(k in def){if(typeof(this.oP[k])!=typeof(def[k]))this.oP[k]=def[k]}var p=this;this.fld.onkeypress=function(a){return p.onKeyPress(a)};this.fld.onkeyup=function(a){return p.onKeyUp(a)};this.fld.setAttribute("autocomplete","off")};_b.AutoSuggest.prototype.onKeyPress=function(a){var b=(window.event)?window.event.keyCode:a.keyCode;var c=13;var d=9;var e=27;var f=1;switch(b){case c:this.setHighlightedValue();f=0;return false;break;case e:this.clearSuggestions();break}return f};_b.AutoSuggest.prototype.onKeyUp=function(a){var b=(window.event)?window.event.keyCode:a.keyCode;var c=38;var d=40;var e=1;switch(b){case c:this.changeHighlight(b);e=0;break;case d:this.changeHighlight(b);e=0;break;default:this.getSuggestions(this.fld.value)}return e};_b.AutoSuggest.prototype.getSuggestions=function(a){if(a==this.sInp)return 0;_b.DOM.remE(this.idAs);this.sInp=a;if(a.length<this.oP.minchars){this.aSug=[];this.nInpC=a.length;return 0}var b=this.nInpC;this.nInpC=a.length?a.length:0;var l=this.aSug.length;if(this.nInpC>b&&l&&l<this.oP.maxentries&&this.oP.cache){var c=[];for(var i=0;i<l;i++){if(this.aSug[i].value.substr(0,a.length).toLowerCase()==a.toLowerCase())c.push(this.aSug[i])}this.aSug=c;this.createList(this.aSug);return false}else{var d=this;var e=this.sInp;clearTimeout(this.ajID);this.ajID=setTimeout(function(){d.doAjaxRequest(e)},this.oP.delay)}return false};_b.AutoSuggest.prototype.doAjaxRequest=function(b){if(b!=this.fld.value)return false;var c=this;if(typeof(this.oP.script)=="function")var d=this.oP.script(encodeURIComponent(this.sInp));else var d=this.oP.script+this.oP.varname+"="+encodeURIComponent(this.sInp);if(!d)return false;var e=this.oP.meth;var b=this.sInp;var f=function(a){c.setSuggestions(a,b)};var g=function(a){alert("AJAX error: "+a)};var h=new _b.Ajax();h.makeRequest(d,e,f,g)};_b.AutoSuggest.prototype.setSuggestions=function(a,b){if(b!=this.fld.value)return false;this.aSug=[];if(this.oP.json){var c=eval('('+a.responseText+')');for(var i=0;i<c.results.length;i++){this.aSug.push({'id':c.results[i].id,'value':c.results[i].value,'info':c.results[i].info})}}else{var d=a.responseXML;var e=d.getElementsByTagName('results')[0].childNodes;for(var i=0;i<e.length;i++){if(e[i].hasChildNodes())this.aSug.push({'id':e[i].getAttribute('id'),'value':e[i].childNodes[0].nodeValue,'info':e[i].getAttribute('info')})}}this.idAs="as_"+this.fld.id;this.createList(this.aSug)};_b.AutoSuggest.prototype.createList=function(b){var c=this;_b.DOM.remE(this.idAs);this.killTimeout();if(b.length==0&&!this.oP.shownoresults)return false;var d=_b.DOM.cE("div",{id:this.idAs,className:this.oP.className});var e=_b.DOM.cE("div",{className:"as_corner"});var f=_b.DOM.cE("div",{className:"as_bar"});var g=_b.DOM.cE("div",{className:"as_header"});g.appendChild(e);g.appendChild(f);d.appendChild(g);var h=_b.DOM.cE("ul",{id:"as_ul"});for(var i=0;i<b.length;i++){var j=b[i].value;var k=j.toLowerCase().indexOf(this.sInp.toLowerCase());var l=j.substring(0,k)+"<em>"+j.substring(k,k+this.sInp.length)+"</em>"+j.substring(k+this.sInp.length);var m=_b.DOM.cE("span",{},l,true);if(b[i].info!=""){var n=_b.DOM.cE("br",{});m.appendChild(n);var o=_b.DOM.cE("small",{},b[i].info);m.appendChild(o)}var a=_b.DOM.cE("a",{href:"#"});var p=_b.DOM.cE("span",{className:"tl"}," ");var q=_b.DOM.cE("span",{className:"tr"}," ");a.appendChild(p);a.appendChild(q);a.appendChild(m);a.name=i+1;a.onclick=function(){c.setHighlightedValue();return false};a.onmouseover=function(){c.setHighlight(this.name)};var r=_b.DOM.cE("li",{},a);h.appendChild(r)}if(b.length==0&&this.oP.shownoresults){var r=_b.DOM.cE("li",{className:"as_warning"},this.oP.noresults);h.appendChild(r)}d.appendChild(h);var s=_b.DOM.cE("div",{className:"as_corner"});var t=_b.DOM.cE("div",{className:"as_bar"});var u=_b.DOM.cE("div",{className:"as_footer"});u.appendChild(s);u.appendChild(t);d.appendChild(u);var v=_b.DOM.getPos(this.fld);d.style.left=v.x+"px";d.style.top=(v.y+this.fld.offsetHeight+this.oP.offsety)+"px";d.style.width=this.fld.offsetWidth+"px";d.onmouseover=function(){c.killTimeout()};d.onmouseout=function(){c.resetTimeout()};document.getElementsByTagName("body")[0].appendChild(d);this.iHigh=0;var c=this;this.toID=setTimeout(function(){c.clearSuggestions()},this.oP.timeout)};_b.AutoSuggest.prototype.changeHighlight=function(a){var b=_b.DOM.gE("as_ul");if(!b)return false;var n;if(a==40)n=this.iHigh+1;else if(a==38)n=this.iHigh-1;if(n>b.childNodes.length)n=b.childNodes.length;if(n<1)n=1;this.setHighlight(n)};_b.AutoSuggest.prototype.setHighlight=function(n){var a=_b.DOM.gE("as_ul");if(!a)return false;if(this.iHigh>0)this.clearHighlight();this.iHigh=Number(n);a.childNodes[this.iHigh-1].className="as_highlight";this.killTimeout()};_b.AutoSuggest.prototype.clearHighlight=function(){var a=_b.DOM.gE("as_ul");if(!a)return false;if(this.iHigh>0){a.childNodes[this.iHigh-1].className="";this.iHigh=0}};_b.AutoSuggest.prototype.setHighlightedValue=function(){if(this.iHigh){this.sInp=this.fld.value=this.aSug[this.iHigh-1].value;this.fld.focus();if(this.fld.selectionStart)this.fld.setSelectionRange(this.sInp.length,this.sInp.length);this.clearSuggestions();if(typeof(this.oP.callback)=="function")this.oP.callback(this.aSug[this.iHigh-1])}};_b.AutoSuggest.prototype.killTimeout=function(){clearTimeout(this.toID)};_b.AutoSuggest.prototype.resetTimeout=function(){clearTimeout(this.toID);var a=this;this.toID=setTimeout(function(){a.clearSuggestions()},1000)};_b.AutoSuggest.prototype.clearSuggestions=function(){this.killTimeout();var a=_b.DOM.gE(this.idAs);var b=this;if(a){var c=new _b.Fader(a,1,0,250,function(){_b.DOM.remE(b.idAs)})}};if(typeof(_b.Ajax)=="undefined")_b.Ajax={};_b.Ajax=function(){this.req={};this.isIE=false};_b.Ajax.prototype.makeRequest=function(a,b,c,d){if(b!="POST")b="GET";this.onComplete=c;this.onError=d;var e=this;if(window.XMLHttpRequest){this.req=new XMLHttpRequest();this.req.onreadystatechange=function(){e.processReqChange()};this.req.open("GET",a,true);this.req.send(null)}else if(window.ActiveXObject){this.req=new ActiveXObject("Microsoft.XMLHTTP");if(this.req){this.req.onreadystatechange=function(){e.processReqChange()};this.req.open(b,a,true);this.req.send()}}};_b.Ajax.prototype.processReqChange=function(){if(this.req.readyState==4){if(this.req.status==200){this.onComplete(this.req)}else{this.onError(this.req.status)}}};if(typeof(_b.DOM)=="undefined")_b.DOM={};_b.DOM.cE=function(b,c,d,e){var f=document.createElement(b);if(!f)return 0;for(var a in c)f[a]=c[a];var t=typeof(d);if(t=="string"&&!e)f.appendChild(document.createTextNode(d));else if(t=="string"&&e)f.innerHTML=d;else if(t=="object")f.appendChild(d);return f};_b.DOM.gE=function(e){var t=typeof(e);if(t=="undefined")return 0;else if(t=="string"){var a=document.getElementById(e);if(!a)return 0;else if(typeof(a.appendChild)!="undefined")return a;else return 0}else if(typeof(e.appendChild)!="undefined")return e;else return 0};_b.DOM.remE=function(a){var e=this.gE(a);if(!e)return 0;else if(e.parentNode.removeChild(e))return true;else return 0};_b.DOM.getPos=function(e){var e=this.gE(e);var a=e;var b=0;if(a.offsetParent){while(a.offsetParent){b+=a.offsetLeft;a=a.offsetParent}}else if(a.x)b+=a.x;var a=e;var c=0;if(a.offsetParent){while(a.offsetParent){c+=a.offsetTop;a=a.offsetParent}}else if(a.y)c+=a.y;return{x:b,y:c}};if(typeof(_b.Fader)=="undefined")_b.Fader={};_b.Fader=function(a,b,c,d,e){if(!a)return 0;this.e=a;this.from=b;this.to=c;this.cb=e;this.nDur=d;this.nInt=50;this.nTime=0;var p=this;this.nID=setInterval(function(){p._fade()},this.nInt)};_b.Fader.prototype._fade=function(){this.nTime+=this.nInt;var a=Math.round(this._tween(this.nTime,this.from,this.to,this.nDur)*100);var b=a/100;if(this.e.filters){try{this.e.filters.item("DXImageTransform.Microsoft.Alpha").opacity=a}catch(e){this.e.style.filter='progid:DXImageTransform.Microsoft.Alpha(opacity='+a+')'}}else{this.e.style.opacity=b}if(this.nTime==this.nDur){clearInterval(this.nID);if(this.cb!=undefined)this.cb()}};_b.Fader.prototype._tween=function(t,b,c,d){return b+((c-b)*(t/d))};