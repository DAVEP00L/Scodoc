# -*- mode: python -*-
# -*- coding: utf-8 -*-


"""Simple form generator/validator

   E. Viennet 2005 - 2008

   v 1.3 (python3)
"""
import html


def TrivialFormulator(
    form_url,
    values,
    formdescription=(),
    initvalues={},
    method="post",
    enctype=None,
    submitlabel="OK",
    name=None,
    formid="tf",
    cssclass="",
    cancelbutton=None,
    submitbutton=True,
    submitbuttonattributes=[],
    top_buttons=False,  # place buttons at top of form
    bottom_buttons=True,  # buttons after form
    html_foot_markup="",
    readonly=False,
    is_submitted=False,
):
    """
    form_url : URL for this form
    initvalues : dict giving default values
    values : dict with all HTML form variables (may start empty)
    is_submitted:  handle form as if already submitted

    Returns (status, HTML form, values)
         status = 0 (html to display),
                  1 (ok, validated values in "values")
                  -1 cancel (if cancelbutton specified)
         HTML form: html string (form to insert in your web page)
         values: None or, when the form is submitted and correctly filled,
                 a dictionnary with the requeted values.
    formdescription: sequence [ (field, description), ... ]
        where description is a dict with following (optional) keys:
          default    : default value for this field ('')
          title      : text titre (default to field name)
          allow_null : if true, field can be left empty (default true)
          type       : 'string', 'int', 'float' (default to string), 'list' (only for hidden)
          readonly   : default False. if True, no form element, display current value.
          convert_numbers: covert int and float values (from string)
          allowed_values : list of possible values (default: any value)
          validator : function validating the field (called with (value,field)).
          min_value : minimum value (for floats and ints)
          max_value : maximum value (for floats and ints)
          explanation: text string to display next the input widget
          title_buble: help bubble on field title (needs bubble.js or equivalent)
          comment : comment, showed under input widget
          withcheckbox: if true, place a checkbox at the left of the input
                        elem. Checked items will be returned in 'tf-checked'
          attributes: a liste of strings to put in the HTML form element
          template: HTML template for element
          HTML elements:
             input_type : 'text', 'textarea', 'password',
                          'radio', 'menu', 'checkbox',
                          'hidden', 'separator', 'file', 'date', 'boolcheckbox',
                          'text_suggest'
                         (default text)
             size : text field width
             rows, cols: textarea geometry
             labels : labels for radio or menu lists (associated to allowed_values)
             vertical: for checkbox; if true, vertical layout
             disabled_items: for checkbox, dict such that disabled_items[i] true if disabled checkbox
          To use text_suggest elements, one must:
            - specify options in text_suggest_options (a dict)
            - HTML page must load JS AutoSuggest.js and CSS autosuggest_inquisitor.css
            - bodyOnLoad must call JS function init_tf_form(formid)
    """
    method = method.lower()
    if method == "get":
        enctype = None
    t = TF(
        form_url,
        values,
        formdescription,
        initvalues,
        method,
        enctype,
        submitlabel,
        name,
        formid,
        cssclass,
        cancelbutton=cancelbutton,
        submitbutton=submitbutton,
        submitbuttonattributes=submitbuttonattributes,
        top_buttons=top_buttons,
        bottom_buttons=bottom_buttons,
        html_foot_markup=html_foot_markup,
        readonly=readonly,
        is_submitted=is_submitted,
    )
    form = t.getform()
    if t.canceled():
        res = -1
    elif t.submitted() and t.result:
        res = 1
    else:
        res = 0
    return res, form, t.result


class TF(object):
    def __init__(
        self,
        form_url,
        values,
        formdescription=[],
        initvalues={},
        method="POST",
        enctype=None,
        submitlabel="OK",
        name=None,
        formid="tf",
        cssclass="",
        cancelbutton=None,
        submitbutton=True,
        submitbuttonattributes=[],
        top_buttons=False,  # place buttons at top of form
        bottom_buttons=True,  # buttons after form
        html_foot_markup="",  # html snippet put at the end, just after the table
        readonly=False,
        is_submitted=False,
    ):
        self.form_url = form_url
        self.values = values.copy()
        self.formdescription = list(formdescription)
        self.initvalues = initvalues
        self.method = method
        self.enctype = enctype
        self.submitlabel = submitlabel
        if name:
            self.name = name
        else:
            self.name = formid  # 'tf'
        self.formid = formid
        self.cssclass = cssclass
        self.cancelbutton = cancelbutton
        self.submitbutton = submitbutton
        self.submitbuttonattributes = submitbuttonattributes
        self.top_buttons = top_buttons
        self.bottom_buttons = bottom_buttons
        self.html_foot_markup = html_foot_markup
        self.readonly = readonly
        self.result = None
        self.is_submitted = is_submitted
        if readonly:
            self.top_buttons = self.bottom_buttons = False
            self.cssclass += " readonly"

    def submitted(self):
        "true if form has been submitted"
        if self.is_submitted:
            return True
        return self.values.get("%s_submitted" % self.formid, False)

    def canceled(self):
        "true if form has been canceled"
        return self.values.get("%s_cancel" % self.formid, False)

    def getform(self):
        "return HTML form"
        R = []
        msg = None
        self.setdefaultvalues()
        if self.submitted() and not self.readonly:
            msg = self.checkvalues()
        # display error message
        R.append(tf_error_message(msg))
        # form or view
        if self.readonly:
            R = R + self._ReadOnlyVersion(self.formdescription)
        else:
            R = R + self._GenForm()
        #
        return "\n".join(R)

    __str__ = getform
    __repr__ = getform

    def setdefaultvalues(self):
        "set default values and convert numbers to strings"
        for (field, descr) in self.formdescription:
            # special case for boolcheckbox
            if descr.get("input_type", None) == "boolcheckbox" and self.submitted():
                if field not in self.values:
                    self.values[field] = 0
                else:
                    self.values[field] = 1
            if field not in self.values:
                if "default" in descr:  # first: default in form description
                    self.values[field] = descr["default"]
                else:  # then: use initvalues dict
                    self.values[field] = self.initvalues.get(field, "")
                if self.values[field] == None:
                    self.values[field] = ""

            # convert numbers, except ids
            if field.endswith("id") and self.values[field]:
                # enforce integer ids:
                try:
                    self.values[field] = int(self.values[field])
                except ValueError:
                    pass
            elif isinstance(self.values[field], (int, float)):
                self.values[field] = str(self.values[field])
        #
        if "tf-checked" not in self.values:
            if self.submitted():
                # si rien n'est coché, tf-checked n'existe plus dans la reponse
                self.values["tf-checked"] = []
            else:
                self.values["tf-checked"] = self.initvalues.get("tf-checked", [])
        self.values["tf-checked"] = [str(x) for x in self.values["tf-checked"]]

    def checkvalues(self):
        "check values. Store .result and returns msg"
        ok = 1
        msg = []
        for (field, descr) in self.formdescription:
            val = self.values[field]
            # do not check "unckecked" items
            if descr.get("withcheckbox", False):
                if not field in self.values["tf-checked"]:
                    continue
            # null values
            allow_null = descr.get("allow_null", True)
            if not allow_null:
                if val == "" or val == None:
                    msg.append(
                        "Le champ '%s' doit être renseigné" % descr.get("title", field)
                    )
                    ok = 0
            # type
            typ = descr.get("type", "string")
            if val != "" and val != None:
                # check only non-null values
                if typ[:3] == "int":
                    try:
                        val = int(val)
                        self.values[field] = val
                    except:
                        msg.append(
                            "La valeur du champ '%s' doit être un nombre entier" % field
                        )
                        ok = 0
                elif typ == "float" or typ == "real":
                    self.values[field] = self.values[field].replace(",", ".")
                    try:
                        val = float(val.replace(",", "."))  # allow ,
                        self.values[field] = val
                    except:
                        msg.append(
                            "La valeur du champ '%s' doit être un nombre" % field
                        )
                        ok = 0
                if typ[:3] == "int" or typ == "float" or typ == "real":
                    if "min_value" in descr and val < descr["min_value"]:
                        msg.append(
                            "La valeur (%d) du champ '%s' est trop petite (min=%s)"
                            % (val, field, descr["min_value"])
                        )
                        ok = 0

                    if "max_value" in descr and val > descr["max_value"]:
                        msg.append(
                            "La valeur (%s) du champ '%s' est trop grande (max=%s)"
                            % (val, field, descr["max_value"])
                        )
                        ok = 0

            # allowed values
            if "allowed_values" in descr:
                if descr.get("input_type", None) == "checkbox":
                    # for checkboxes, val is a list
                    for v in val:
                        if not v in descr["allowed_values"]:
                            msg.append(
                                "valeur invalide (%s) pour le champ '%s'" % (val, field)
                            )
                            ok = 0
                elif descr.get("input_type", None) == "boolcheckbox":
                    pass
                elif not val in descr["allowed_values"]:
                    msg.append("valeur invalide (%s) pour le champ '%s'" % (val, field))
                    ok = 0
            if "validator" in descr:
                if not descr["validator"](val, field):
                    msg.append("valeur invalide (%s) pour le champ '%s'" % (val, field))
                    ok = 0
            # boolean checkbox
            if descr.get("input_type", None) == "boolcheckbox":
                if int(val):
                    self.values[field] = True
                else:
                    self.values[field] = False
                # open('/tmp/toto','a').write('checkvalues: val=%s (%s) values[%s] = %s\n' % (val, type(val), field, self.values[field]))
            if descr.get("convert_numbers", False):
                if typ[:3] == "int":
                    self.values[field] = int(self.values[field])
                elif typ == "float" or typ == "real":
                    self.values[field] = float(self.values[field].replace(",", "."))
        if ok:
            self.result = self.values
        else:
            self.result = None
        return msg

    def _GenForm(self, method="", enctype=None, form_url=""):
        values = self.values
        add_no_enter_js = False  # add JS function to prevent 'enter' -> submit
        # form template

        # default template for each input element
        itemtemplate = """<tr%(item_dom_attr)s>
        <td class="tf-fieldlabel">%(label)s</td><td class="tf-field">%(elem)s</td>
        </tr>
        """
        hiddenitemtemplate = "%(elem)s"
        separatortemplate = '<tr%(item_dom_attr)s><td colspan="2">%(label)s</td></tr>'
        # ---- build form
        buttons_markup = ""
        if self.submitbutton:
            buttons_markup += (
                '<input type="submit" name="%s_submit" id="%s_submit" value="%s" %s/>'
                % (
                    self.formid,
                    self.formid,
                    self.submitlabel,
                    " ".join(self.submitbuttonattributes),
                )
            )
        if self.cancelbutton:
            buttons_markup += (
                ' <input type="submit" name="%s_cancel" id="%s_cancel" value="%s"/>'
                % (self.formid, self.formid, self.cancelbutton)
            )

        R = []
        suggest_js = []
        if self.enctype is None:
            if self.method == "post":
                enctype = "multipart/form-data"
            else:
                enctype = "application/x-www-form-urlencoded"
        if self.cssclass:
            klass = ' class="%s"' % self.cssclass
        else:
            klass = ""
        name = self.name
        R.append(
            '<form action="%s" method="%s" id="%s" enctype="%s" name="%s" %s>'
            % (self.form_url, self.method, self.formid, enctype, name, klass)
        )
        R.append('<input type="hidden" name="%s_submitted" value="1"/>' % self.formid)
        if self.top_buttons:
            R.append(buttons_markup + "<p></p>")
        R.append('<table class="tf">')
        idx = 0
        for idx in range(len(self.formdescription)):
            (field, descr) = self.formdescription[idx]
            if descr.get("readonly", False):
                R.append(self._ReadOnlyElement(field, descr))
                continue
            wid = self.name + "_" + field
            size = descr.get("size", 12)
            rows = descr.get("rows", 5)
            cols = descr.get("cols", 60)
            title = descr.get("title", field.capitalize())
            title_bubble = descr.get("title_bubble", None)
            withcheckbox = descr.get("withcheckbox", False)
            input_type = descr.get("input_type", "text")
            item_dom_id = descr.get("dom_id", "")
            if item_dom_id:
                item_dom_attr = ' id="%s"' % item_dom_id
            else:
                item_dom_attr = ""
            # choix du template
            etempl = descr.get("template", None)
            if etempl is None:
                if input_type == "hidden":
                    etempl = hiddenitemtemplate
                elif input_type == "separator":
                    etempl = separatortemplate
                    R.append(etempl % {"label": title, "item_dom_attr": item_dom_attr})
                    continue
                else:
                    etempl = itemtemplate
            lab = []
            lem = []
            if withcheckbox and input_type != "hidden":
                if field in values["tf-checked"]:
                    checked = 'checked="checked"'
                else:
                    checked = ""
                lab.append(
                    '<input type="checkbox" name="%s:list" value="%s" onclick="tf_enable_elem(this)" %s/>'
                    % ("tf-checked", field, checked)
                )
            if title_bubble:
                lab.append(
                    '<a class="discretelink" href="" title="%s">%s</a>'
                    % (title_bubble, title)
                )
            else:
                lab.append(title)
            #
            attribs = " ".join(descr.get("attributes", []))
            if (
                withcheckbox and not checked
            ) or not descr.get(  # desactive les element non coches:
                "enabled", True
            ):
                attribs += ' disabled="true"'
            #
            if input_type == "text":
                lem.append(
                    '<input type="text" name="%s" size="%d" id="%s" %s'
                    % (field, size, wid, attribs)
                )
                if descr.get("return_focus_next", False):  # and nextitemname:
                    # JS code to focus on next element on 'enter' key
                    # ceci ne marche que pour desactiver enter sous IE (pas Firefox)
                    # lem.append('''onKeyDown="if(event.keyCode==13){
                    # event.cancelBubble = true; event.returnValue = false;}"''')
                    lem.append('onkeypress="return enter_focus_next(this, event);"')
                    add_no_enter_js = True
                #                    lem.append('onchange="document.%s.%s.focus()"'%(name,nextitemname))
                #                    lem.append('onblur="document.%s.%s.focus()"'%(name,nextitemname))
                lem.append(('value="%(' + field + ')s" />') % values)
            elif input_type == "password":
                lem.append(
                    '<input type="password" name="%s" id="%s" size="%d" %s'
                    % (field, wid, size, attribs)
                )
                lem.append(('value="%(' + field + ')s" />') % values)
            elif input_type == "radio":
                labels = descr.get("labels", descr["allowed_values"])
                for i in range(len(labels)):
                    if descr["allowed_values"][i] == values[field]:
                        checked = 'checked="checked"'
                    else:
                        checked = ""
                    lem.append(
                        '<input type="radio" name="%s" value="%s" %s %s>%s</input>'
                        % (
                            field,
                            descr["allowed_values"][i],
                            checked,
                            attribs,
                            labels[i],
                        )
                    )
            elif input_type == "menu":
                lem.append('<select name="%s" id="%s" %s>' % (field, wid, attribs))
                labels = descr.get("labels", descr["allowed_values"])
                for i in range(len(labels)):
                    if str(descr["allowed_values"][i]) == str(values[field]):
                        selected = "selected"
                    else:
                        selected = ""
                    lem.append(
                        '<option value="%s" %s>%s</option>'
                        % (descr["allowed_values"][i], selected, labels[i])
                    )
                lem.append("</select>")
            elif input_type == "checkbox" or input_type == "boolcheckbox":
                if input_type == "checkbox":
                    labels = descr.get("labels", descr["allowed_values"])
                else:  # boolcheckbox
                    labels = [""]
                    descr["allowed_values"] = ["0", "1"]
                vertical = descr.get("vertical", False)
                disabled_items = descr.get("disabled_items", {})
                if vertical:
                    lem.append("<table>")
                for i in range(len(labels)):
                    if input_type == "checkbox":
                        # from app.scodoc.sco_utils import log # debug only
                        # log('checkbox: values[%s] = "%s"' % (field,repr(values[field]) ))
                        # log("descr['allowed_values'][%s] = '%s'" % (i, repr(descr['allowed_values'][i])))
                        if (
                            values[field]
                            and descr["allowed_values"][i] in values[field]
                        ):
                            checked = 'checked="checked"'
                        else:
                            checked = ""
                    else:  # boolcheckbox
                        # open('/tmp/toto','a').write('GenForm: values[%s] = %s (%s)\n' % (field, values[field], type(values[field])))
                        if values[field] == "True":
                            v = True
                        elif values[field] == "False":
                            v = False
                        else:
                            try:
                                v = int(values[field])
                            except:
                                v = False
                        if v:
                            checked = 'checked="checked"'
                        else:
                            checked = ""
                    if vertical:
                        lem.append("<tr><td>")
                    if disabled_items.get(i, False):
                        disab = 'disabled="1"'
                        ilab = (
                            '<span class="tf-label-disabled">'
                            + labels[i]
                            + "</span> <em>(non modifiable)</em>"
                        )
                    else:
                        disab = ""
                        ilab = "<span>" + labels[i] + "</span>"
                    lem.append(
                        '<input type="checkbox" name="%s:list" value="%s" %s %s %s>%s</input>'
                        % (
                            field,
                            descr["allowed_values"][i],
                            attribs,
                            disab,
                            checked,
                            ilab,
                        )
                    )
                    if vertical:
                        lem.append("</tr></td>")
                if vertical:
                    lem.append("</table>")
            elif input_type == "textarea":
                lem.append(
                    '<textarea name="%s" id="%s" rows="%d" cols="%d" %s>%s</textarea>'
                    % (field, wid, rows, cols, attribs, values[field])
                )
            elif input_type == "hidden":
                if descr.get("type", "") == "list":
                    for v in values[field]:
                        lem.append(
                            '<input type="hidden" name="%s:list" value="%s" %s />'
                            % (field, v, attribs)
                        )
                else:
                    lem.append(
                        '<input type="hidden" name="%s" id="%s" value="%s" %s />'
                        % (field, wid, values[field], attribs)
                    )
            elif input_type == "separator":
                pass
            elif input_type == "file":
                lem.append(
                    '<input type="file" name="%s" size="%s" value="%s" %s/>'
                    % (field, size, values[field], attribs)
                )
            elif input_type == "date":  # JavaScript widget for date input
                lem.append(
                    '<input type="text" name="%s" size="10" value="%s" class="datepicker"/>'
                    % (field, values[field])
                )
            elif input_type == "text_suggest":
                lem.append(
                    '<input type="text" name="%s" id="%s" size="%d" %s'
                    % (field, field, size, attribs)
                )
                lem.append(('value="%(' + field + ')s" />') % values)
                suggest_js.append(
                    f"""var {field}_opts = {dict2js(descr.get("text_suggest_options", {}))};
var {field}_as = new bsn.AutoSuggest('{field}', {field}_opts);
"""
                )
            else:
                raise ValueError("unkown input_type for form (%s)!" % input_type)
            explanation = descr.get("explanation", "")
            if explanation:
                lem.append('<span class="tf-explanation">%s</span>' % explanation)
            comment = descr.get("comment", "")
            if comment:
                lem.append('<br/><span class="tf-comment">%s</span>' % comment)
            R.append(
                etempl
                % {
                    "label": "\n".join(lab),
                    "elem": "\n".join(lem),
                    "item_dom_attr": item_dom_attr,
                }
            )
        R.append("</table>")

        R.append(self.html_foot_markup)

        if self.bottom_buttons:
            R.append("<br/>" + buttons_markup)

        if add_no_enter_js:
            R.append(
                """<script type="text/javascript">
            function enter_focus_next (elem, event) {
        var cod = event.keyCode ? event.keyCode : event.which ? event.which : event.charCode;
        var enter = false;
        if (event.keyCode == 13)
            enter = true;
        if (event.which == 13)
            enter = true;
        if (event.charCode == 13)
            enter = true;
        if (enter) {
            var focused = false;
            var i;
            for (i = 0; i < elem.form.elements.length; i++)
                if (elem == elem.form.elements[i])
                    break;
            i = i + 1;
            while (i < elem.form.elements.length) {
                if ((elem.form.elements[i].type == "text") 
                    && (!(elem.form.elements[i].disabled))
                    && ($(elem.form.elements[i]).is(':visible')))
                {
                    elem.form.elements[i].focus();
                    focused = true;
                    break;
                }
                i = i + 1;
            }
            if (!focused) {
                elem.blur();
            }
            return false;
        } 
        else
            return true;
    }</script>
            """
            )  # enter_focus_next, ne focus que les champs text
        if suggest_js:
            # nota: formid is currently ignored
            # => only one form with text_suggest field on a page.
            R.append(
                """<script type="text/javascript">
            function init_tf_form(formid) {                
                %s
            }
            </script>"""
                % "\n".join(suggest_js)
            )
        # Javascript common to all forms:
        R.append(
            """<script type="text/javascript">
    // controle par la checkbox
    function tf_enable_elem(checkbox) {
      var oid = checkbox.value;
      if (oid) {
         var elem = document.getElementById(oid);
         if (elem) {
             if (checkbox.checked) {
                 elem.disabled = false;
             } else {
                 elem.disabled = true;
             }
         }
      }
    }

    // Selections etendues avec shift (use jquery.field)
    $('input[name="tf-checked:list"]').createCheckboxRange();
        </script>"""
        )
        R.append("</form>")
        return R

    def _ReadOnlyElement(self, field, descr):
        "Generate HTML for an element, read-only"
        R = []
        title = descr.get("title", field.capitalize())
        input_type = descr.get("input_type", "text")
        klass = descr.get("cssclass", "")
        klass = " " + klass
        if input_type == "hidden":
            return ""

        R.append('<tr class="tf-ro-tr%s">' % klass)

        if input_type == "separator":  # separator
            R.append('<td colspan="2">%s' % title)
        else:
            R.append('<td class="tf-ro-fieldlabel%s">' % klass)
            R.append("%s</td>" % title)
            R.append('<td class="tf-ro-field%s">' % klass)

        if input_type == "text" or input_type == "text_suggest":
            R.append(("%(" + field + ")s") % self.values)
        elif input_type in ("radio", "menu", "checkbox", "boolcheckbox"):
            if input_type == "boolcheckbox":
                labels = descr.get(
                    "labels", descr.get("allowed_values", ["oui", "non"])
                )
                _val = self.values[field]
                if isinstance(_val, bool):
                    bool_val = 1 if _val else 0
                elif _val == "False":
                    bool_val = 0
                elif _val:
                    bool_val = 1
                else:
                    bool_val = 0
                R.append(labels[bool_val])
                if bool_val:
                    R.append('<input type="hidden" name="%s" value="1"/>' % field)
            else:
                labels = descr.get("labels", descr["allowed_values"])
                for i in range(len(labels)):
                    if str(descr["allowed_values"][i]) == str(self.values[field]):
                        R.append('<span class="tf-ro-value">%s</span>' % labels[i])
        elif input_type == "textarea":
            R.append(
                '<div class="tf-ro-textarea">%s</div>' % html.escape(self.values[field])
            )
        elif input_type == "separator" or input_type == "hidden":
            pass
        elif input_type == "file":
            R.append("'%s'" % self.values[field])
        else:
            raise ValueError("unkown input_type for form (%s)!" % input_type)

        explanation = descr.get("explanation", "")
        if explanation:
            R.append('<span class="tf-explanation">%s</span>' % explanation)

        R.append("</td></tr>")

        return "\n".join(R)

    def _ReadOnlyVersion(self, formdescription):
        "Generate HTML for read-only view of the form"
        R = ['<table class="tf-ro">']
        for (field, descr) in formdescription:
            R.append(self._ReadOnlyElement(field, descr))
        R.append("</table>")
        return R


def dict2js(d):
    """convert Python dict to JS code"""
    r = []
    for k in d:
        v = d[k]
        if isinstance(v, bool):
            if v:
                v = "true"
            else:
                v = "false"
        elif isinstance(v, str):  # ne marchera pas en python2
            v = '"' + v + '"'

        r.append("%s: %s" % (k, v))
    return "{" + ",\n".join(r) + "}"


def tf_error_message(msg):
    """html for form error message"""
    if not msg:
        return ""
    if isinstance(msg, str):
        msg = [msg]
    return (
        '<ul class="tf-msg"><li class="tf-msg error-message">%s</li></ul>'
        % '</li><li class="tf-msg tf-msg error-message">'.join(msg)
    )
