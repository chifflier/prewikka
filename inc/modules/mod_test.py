import sys
from templates.modules.mod_test import Form

class Display:
    def __init__(self, query):
        self.query = query

    def __str__(self):
        ret = ""
        ret += "<p>foo: %s</p>\n" % self.query["foo"]
        ret += "<p>bar: %s</p>\n" % self.query["bar"]
        return ret


class Fetch:
    def __init__(self, query):
        self.query = query

    def __str__(self):
        form = Form.Form()
        form.setFixedField("mod", "test")
        form.setFixedField("section", "display")
        form.setInteractiveField("display.foo", "foo")
        form.setInteractiveField("display.bar", "bar")
        return str(form)



class Empty:
    def __init__(self, query):
        pass

    def __str__(self):
        return ""


def load(module):
    module.setName("Test")
    module.registerSection("fetch", Fetch, default=True)
    module.registerSection("display", Display, parent="fetch")
    module.registerSection("empty", Empty)
