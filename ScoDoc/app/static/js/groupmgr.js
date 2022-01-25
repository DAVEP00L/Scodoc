/* -*- mode: javascript -*-
 *
 * ScoDoc: Affectation des groupes de TD
 * re-ecriture utilisant jQuery de l'ancien code
 */


/* --- Globals ---- */
var EtudColors = ["#E8EEF7", "#ffffff"]; // [ "#E8EEF7", "#E0ECFF", "#E5E6BE", "#F3EAE2", "#E3EAE1" ];
var EtudColorsIdx = 0;
var NbEtuds = 0;
var ETUDS = new Object(); // { etudid : etud }
var ETUD_GROUP = new Object(); // { etudid : group_id }
var groups_unsaved = false;

var groups = new Object(); // Liste des groupes

function loadGroupes() {
    $("#gmsg")[0].innerHTML = 'Chargement des groupes en cours...';
    var partition_id = document.formGroup.partition_id.value;

    $.get(SCO_URL + '/XMLgetGroupsInPartition', { partition_id: partition_id })
        .done(
            function (data) {
                var nodes = data.getElementsByTagName('group');
                if (nodes) {
                    var nbgroups = nodes.length;
                    // put last group at first (etudiants sans groupes)
                    if (nodes.length > 1 && nodes[nbgroups - 1].attributes.getNamedItem("group_id").value == '_none_') {
                        populateGroup(nodes[nodes.length - 1]);
                        nbgroups -= 1;
                    }
                    // then standard groups
                    for (var i = 0; i < nbgroups; i++) {
                        populateGroup(nodes[i]);
                    }
                }
                $("#gmsg")[0].innerHTML = '';
                updateginfo();
            }
        )
}

function populateGroup(node) {
    var group_id = node.attributes.getNamedItem("group_id").value;
    var group_name = node.attributes.getNamedItem("group_name").value;

    // CREE LA BOITE POUR CE GROUPE
    if (group_id) {
        var gbox = new CGroupBox(group_id, group_name);
        var etuds = node.getElementsByTagName('etud');
        var x = '';
        gbox.sorting = false; // disable to speedup
        EtudColorsIdx = 0; // repart de la premiere couleur
        for (var j = 0; j < etuds.length; j++) {
            var nom = etuds[j].attributes.getNamedItem("nom").value;
            var prenom = etuds[j].attributes.getNamedItem("prenom").value;
            var sexe = etuds[j].attributes.getNamedItem("sexe").value;
            var etudid = etuds[j].attributes.getNamedItem("etudid").value;
            var origin = etuds[j].attributes.getNamedItem("origin").value;
            var etud = new CDraggableEtud(nom, prenom, sexe, origin, etudid);
            gbox.createEtudInGroup(etud, group_id);
        }
        gbox.sorting = true;
        gbox.updateTitle(); // sort 
    }
}


/* --- Boite pour un groupe --- */

var groupBoxes = new Object(); // assoc group_id : groupBox
var groupsToDelete = new Object(); // list of group_id to be supressed

var CGroupBox = function (group_id, group_name) {
    group_id = $.trim(group_id);
    var regex = /^\w+$/;
    if (!regex.test(group_id)) {
        alert("Id de groupe invalide");
        return;
    }
    if (group_id in groups) {
        alert("Le groupe " + group_id + " existe déjà !");
        return;
    }
    groups[group_id] = 1;
    this.group_id = group_id;
    this.group_name = group_name;
    this.etuds = new Object();
    this.nbetuds = 0;
    this.isNew = false; // true for newly user-created groups
    this.sorting = true; // false to disable sorting

    this.groupBox = document.createElement("div");
    this.groupBox.className = "simpleDropPanel";
    this.groupBox.id = group_id;
    var titleDiv = document.createElement("div");
    titleDiv.className = "groupTitle0";
    titleDiv.appendChild(this.groupTitle());
    this.groupBox.appendChild(titleDiv);
    var gdiv = document.getElementById('groups');
    gdiv.appendChild(this.groupBox);
    this.updateTitle();
    $(this.groupBox).droppable(
        {
            accept: ".box",
            activeClass: "activatedPanel",
            drop: function (event, ui) {
                // alert("drop on " + this.group_name);
                var etudid = ui.draggable[0].id;
                var etud = ETUDS[etudid];
                var newGroupName = this.id;
                var oldGroupName = ETUD_GROUP[etudid];
                $(groupBoxes[newGroupName].groupBox).append(ui.draggable)
                ui.draggable[0].style.left = ""; // fix style (?)
                ui.draggable[0].style.top = "";
                etud.changeGroup(oldGroupName, newGroupName);
                etud.htmlElement.style.fontStyle = 'italic'; // italic pour les etudiants deplaces                
            }
        });
    /* On peut s'amuser a deplacer tout un groupe (visuellement: pas droppable) */
    $(this.groupBox).draggable({
        cursor: 'move',
        containment: '#groups'
    });

    groupBoxes[group_id] = this; // register
    updateginfo();
}

$.extend(CGroupBox.prototype, {
    // menu for group title
    groupTitle: function () {
        var menuSpan = document.createElement("span");
        menuSpan.className = "barrenav";
        var h = "<table><tr><td><ul class=\"nav\"><li onmouseover=\"MenuDisplay(this)\" onmouseout=\"MenuHide(this)\"><a href=\"#\" class=\"menu custommenu\"><span id=\"titleSpan" + this.group_id + "\" class=\"groupTitle\">menu</span></a><ul>";
        if (this.group_id != '_none_') {
            h += "<li><a href=\"#\" onClick=\"suppressGroup('" + this.group_id + "');\">Supprimer</a></li>";
            h += "<li><a href=\"#\" onClick=\"renameGroup('" + this.group_id + "');\">Renommer</a></li>";
        }
        h += "</ul></li></ul></td></tr></table>";
        menuSpan.innerHTML = h;
        return menuSpan;
    },
    // add etud to group, attach to DOM 
    createEtudInGroup: function (etud) {
        this.addEtudToGroup(etud);
        this.groupBox.appendChild(etud.htmlElement);
    },
    // add existing etud to group (does not affect DOM)
    addEtudToGroup: function (etud) {
        etud.group_id = this.group_id;
        this.etuds[etud.etudid] = etud;
        this.nbetuds++;
        ETUD_GROUP[etud.etudid] = this.group_id;
        this.updateTitle();
    },
    // remove etud
    removeEtud: function (etud) {
        delete this.etuds[etud.etudid];
        this.nbetuds--;
        this.updateTitle();
    },
    // Update counter display
    updateTitle: function () {
        var tclass = '';
        if (this.isNew) {
            tclass = ' class="newgroup"'
        }
        var titleSpan = document.getElementById('titleSpan' + this.group_id);
        if (this.group_id != '_none_')
            titleSpan.innerHTML = '<span' + tclass + '>Groupe ' + this.group_name + ' (' + this.nbetuds + ')</span>';
        else
            titleSpan.innerHTML = '<span' + tclass + '>Etudiants sans groupe' + ' (' + this.nbetuds + ')</span>';
        this.sortList(); // maintient toujours la liste triee
    },
    // Tri de la boite par nom
    sortList: function () {
        if (!this.sorting)
            return;
        var newRows = new Array();
        for (var i = 1; i < this.groupBox.childNodes.length; i++) { // 1 car div titre
            newRows[i - 1] = this.groupBox.childNodes[i];
        }
        var sortfn = function (a, b) {
            // recupere les noms qui sont dans un span
            var nom_a = a.childNodes[1].childNodes[0].nodeValue;
            var nom_b = b.childNodes[1].childNodes[0].nodeValue;
            // console.log( 'comp( %s, %s )', nom_a, nom_b );
            if (nom_a == nom_b)
                return 0;
            if (nom_a < nom_b)
                return -1;
            return 1;
        };
        newRows.sort(sortfn);
        for (var i = 0; i < newRows.length; i++) {
            this.groupBox.appendChild(newRows[i]);
            newRows[i].style.backgroundColor = EtudColors[EtudColorsIdx];
            EtudColorsIdx = (EtudColorsIdx + 1) % EtudColors.length;
        }
    }
});


function suppressGroup(group_id) {
    // 1- associate all members to group _none_
    if (!groupBoxes['_none_']) {
        // create group _none_
        var gbox = new CGroupBox('_none_', 'Etudiants sans groupe');
    }
    var dst_group_id = groupBoxes['_none_'].group_id;
    var src_box_etuds = groupBoxes[group_id].etuds;
    for (var etudid in src_box_etuds) {
        var etud = src_box_etuds[etudid];
        etud.changeGroup(group_id, dst_group_id);
        groupBoxes['_none_'].groupBox.appendChild(etud.htmlElement);
    }
    groupBoxes['_none_'].updateTitle();
    // 2- add group to list of groups to be removed (unless it's a new group)
    if (!groupBoxes[group_id].isNew)
        groupsToDelete[group_id] = true;
    // 3- delete objects and remove from DOM
    var div = document.getElementById(group_id);
    div.remove();
    delete groupBoxes[group_id];
    groups_unsaved = true;
    updateginfo();
}


function renameGroup(group_id) {
    // 1-- save modifications
    if (groups_unsaved) {
        alert("Enregistrez ou annulez vos changement avant !");
    } else {
        // 2- form rename
        document.location = 'group_rename?group_id=' + group_id;
    }
}

var createdGroupId = 0;
function newGroupId() {
    var gid;
    do {
        gid = 'NG' + createdGroupId.toString();
        createdGroupId += 1;
    } while (gid in groupBoxes);
    return gid;
}

// Creation d'un groupe
function createGroup() {
    var group_name = document.formGroup.groupName.value.trim();
    if (!group_name) {
        alert("Nom de groupe vide !");
        return false;
    }
    // check name:
    for (var group_id in groupBoxes) {
        if (group_id != 'extend') {
            if (groupBoxes[group_id].group_name == group_name) {
                alert("Nom de groupe déja existant !");
                return false;
            }
        }
    }
    var group_id = newGroupId();
    groups_unsaved = true;
    var gbox = new CGroupBox(group_id, group_name);
    gbox.isNew = true;
    gbox.updateTitle();
    return true;
}

/* --- Etudiant draggable --- */
var CDraggableEtud = function (nom, prenom, sexe, origin, etudid) {
    this.type = 'Custom';
    this.name = etudid;
    this.etudid = etudid;
    this.nom = nom;
    this.prenom = prenom;
    this.sexe = sexe;
    this.origin = origin;
    this.createNode();
    ETUDS[etudid] = this;
    NbEtuds++;
}

$.extend(CDraggableEtud.prototype, {
    repr: function () {
        return this.sexe + ' ' + this.prenom + ' <span class="nom">' + this.nom + '</span> ' + '<b>' + this.origin + '</b>';
    },
    createNode: function () {
        // Create DOM element for student
        var e = document.createElement("div");
        this.htmlElement = e;
        e.className = "box";
        e.id = this.etudid;
        // e.style.backgroundColor = EtudColors[EtudColorsIdx];
        // EtudColorsIdx = (EtudColorsIdx + 1) % EtudColors.length;
        //var txtNode = document.createTextNode( this.repr() );
        //e.appendChild(txtNode);
        e.innerHTML = this.repr();
        // declare as draggable
        $(e).draggable({
            cursor: 'move',
            stack: '#groups div',
            containment: '#groups',
            revert: 'invalid'
        });
    },
    endDrag: function () {
        var el = this.htmlElement;
        var p = el.parentNode;
        // alert("endDrag: [" + this.name +"] " + p.id );
        this.changeGroup(this.group_id, p.id);
        this.htmlElement.style.fontStyle = 'italic'; // italic pour les etudiants deplaces
    },
    // Move a student from a group to another
    changeGroup: function (oldGroupName, newGroupName) {
        if (oldGroupName == newGroupName) {
            // drop on original group, just sort
            groupBoxes[oldGroupName].updateTitle();
            return;
        }
        var oldGroupBox = null;
        if (oldGroupName) {
            oldGroupBox = groupBoxes[oldGroupName];
        }
        var newGroupBox = groupBoxes[newGroupName];
        newGroupBox.addEtudToGroup(this);
        if (oldGroupBox)
            oldGroupBox.removeEtud(this);
        groups_unsaved = true;
        updatesavedinfo();
    }
});


/* --- Upload du resultat --- */
function processResponse(value) {
    location.reload(); // necessaire pour reinitialiser les id des groupes créés
}

function handleError(msg) {
    alert('Error: ' + msg);
    console.log('Error: ' + msg);
}

function submitGroups() {
    var url = SCO_URL + '/setGroups';
    // build post request body: groupname \n etudid; ...
    var groupsLists = '';
    var groupsToCreate = '';
    for (var group_id in groupBoxes) {
        if (group_id != 'extend') { // je ne sais pas ce dont il s'agit ???
            if (group_id != '_none_') { // ne renvoie pas le groupe des sans-groupes
                groupBox = groupBoxes[group_id];
                if (groupBox.isNew) {
                    groupsToCreate += groupBox.group_name + ';';
                    for (var etudid in groupBox.etuds) {
                        if (etudid != 'extend')
                            groupsToCreate += etudid + ';';
                    }
                    groupsToCreate += '\n';
                    groupBox.isNew = false; // is no more new !
                } else {
                    groupsLists += group_id + ';';
                    for (var etudid in groupBox.etuds) {
                        if (etudid != 'extend')
                            groupsLists += etudid + ';';
                    }
                    groupsLists += '\n';
                }
            }
        }
    }
    var todel = '';
    for (var group_id in groupsToDelete) {
        todel += group_id + ';';
    }
    groupsToDelete = new Object(); // empty
    var partition_id = document.formGroup.partition_id.value;
    // Send to server
    $.get(url, {
        groupsLists: groupsLists, // encodeURIComponent
        partition_id: partition_id,
        groupsToDelete: todel,
        groupsToCreate: groupsToCreate
    })
        .done(function (data) {
            processResponse(data);
        })
        .fail(function () {
            handleError("Erreur lors de l'enregistrement de groupes");
        });
}

// Move to another partition (specified by menu)
function GotoAnother() {
    if (groups_unsaved) {
        alert("Enregistrez ou annulez vos changement avant !");
    } else
        document.location = SCO_URL + '/affect_groups?partition_id=' + document.formGroup.other_partition_id.value;
}


// Boite information haut de page 
function updateginfo() {
    var g = document.getElementById('ginfo');
    var group_names = new Array();
    for (var group_id in groupBoxes) {
        if ((group_id != 'extend') && (groupBoxes[group_id].group_name)) {
            group_names.push(groupBoxes[group_id].group_name);
        }
    }
    g.innerHTML = '<b>Groupes définis: ' + group_names.join(', ') + '<br/>'
        + "Nombre d'etudiants: " + NbEtuds + '</b>';

    updatesavedinfo();
}

// Boite indiquant si modifications non enregistrees ou non
function updatesavedinfo() {
    var g = document.getElementById('savedinfo');
    if (groups_unsaved) {
        g.innerHTML = 'modifications non enregistrées';
        g.style.visibility = 'visible';
    } else {
        g.innerHTML = '';
        g.style.visibility = 'hidden';
    }
    return true;
}


$(function () {
    loadGroupes();
});

/* debug:

var g = new CGroupBox('G0', 'Toto');

*/