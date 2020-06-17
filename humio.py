from core import plugin, model
from plugins.humio.models import trigger

class _humio(plugin._plugin):
    version = 1.5

    def install(self):
        # Register models
        model.registerModel("humio","_humio","_trigger","plugins.humio.models.trigger")
        model.registerModel("humioIngest","_humioIngest","_trigger","plugins.humio.models.action")
        model.registerModel("humioSearch","_humioSearch","_action","plugins.humio.models.action")
        model.registerModel("humioDashboard","_humioDashboard","_action","plugins.humio.models.action")
        return True

    def uninstall(self):
        # deregister models
        model.deregisterModel("humio","_humio","_trigger","plugins.humio.models.trigger")
        model.deregisterModel("humioIngest","_humioIngest","_action","plugins.humio.models.action")
        model.deregisterModel("humioSearch","_humioSearch","_action","plugins.humio.models.action")
        model.deregisterModel("humioDashboard","_humioDashboard","_action","plugins.humio.models.action")
        return True

    def upgrade(self,LatestPluginVersion):
        #Added Humio Dashboard Action
        if self.version < 1.5:
            model.registerModel("humioDashboard","_humioDashboard","_action","plugins.humio.models.action")

        #Added HumioSearch Action
        if self.version < 1.5:
            model.registerModel("humioSearch","_humioSearch","_action","plugins.humio.models.action")

        #Added Humio Ingest Action
        if self.version < 1.2:
            model.registerModel("humioIngest","_humioIngest","_action","plugins.humio.models.action")
        return True
