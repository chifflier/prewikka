import sys
import os, os.path

import Config
import Log
import Prelude
import Interface

class Core:
    def __init__(self):
        self.content_modules = { }
        self._content_module_names = [ ]
        self._config = Config.Config()
        self.interface = Interface.Interface(self, self._config.get("interface", { }))
        self.log = Log.Log()
        self._initModules()
        self._initPrelude()

##     def _initModules(self):
##         sys.path.append("inc/modules")
##         #names = [ "mod_alert", "mod_test", "mod_log_stderr" ]
##         names = [ "mod_alert", "mod_log_stderr" ]
##         for name in names:
##             module = __import__(name)
##             module.load(self, self._config.modules.get(name, { }))

    def _initModules(self):
        print >> sys.stderr, "###", os.getcwd()
        sys.path.append(".")
        base_dir = "inc/modules/"
        files = os.listdir(base_dir)
        for file in files:
            if os.path.isdir(base_dir + file):
                name = os.path.basename(file)
                if os.path.isfile(base_dir + file + "/" + name + ".py"):
                    print >> sys.stderr, "try to import module", (base_dir + file + "/" + name)
                    module = __import__(base_dir + file + "/" + name)
                    print >> sys.stderr, "load module", name
                    module.load(self, self._config.modules.get(name, {}))
        
    def _initPrelude(self):
        self.prelude = Prelude.Prelude(self._config["prelude"])
        
    def process(self, query, response):
        if query.has_key("action"):
            action = query["action"]
            del query["action"]
        else:
            action = None
        
        view = self.interface.process(action, query)
        response.write(view)
