import urllib
import time
from datetime import datetime, timedelta

from plugins.humio.includes import humio

from core.models import trigger, webui

from core import settings, logging, auth, db

from system.models import trigger as systemTrigger

humioSettings = settings.config["humio"]

class _humio(trigger._trigger):
    humioJob = str()
    jobStartWaitTime = 10
    searchQuery = str()
    searchRepository = str()
    searchStart = str()
    searchEnd = str()
    searchLive = bool()
    onlyNew = bool()
    lastEventTimestamp = int()
    humioOverrideSettings = bool()
    humioJob = str()
    humioHost = str()
    humioPort = int()
    humioAPIToken = str()
    humioTimeout = int()

    class _properties(webui._properties):
        def generate(self,classObject):
            formData = []
            formData.append({"type" : "input", "schemaitem" : "_id", "textbox" : classObject._id})
            formData.append({"type" : "input", "schemaitem" : "name", "textbox" : classObject.name})
            formData.append({"type" : "checkbox", "schemaitem" : "humioOverrideSettings", "checked" : classObject.humioOverrideSettings, "tooltip" : "Select to use object defined humio host settings instead of global settings.json"})
            formData.append({"type" : "input", "schemaitem" : "humioTimeout", "textbox" : classObject.humioTimeout})
            formData.append({"type" : "input", "schemaitem" : "humioAPIToken", "textbox" : classObject.humioAPIToken})
            formData.append({"type" : "input", "schemaitem" : "humioPort", "textbox" : classObject.humioPort})
            formData.append({"type" : "input", "schemaitem" : "humioHost", "textbox" : classObject.humioHost})
            formData.append({"type" : "checkbox", "schemaitem" : "threaded", "checked" : classObject.threaded})
            formData.append({"type" : "input", "schemaitem" : "concurrency", "textbox" : classObject.concurrency})
            formData.append({"type" : "input", "schemaitem" : "clusterSet", "textbox" : classObject.clusterSet})
            formData.append({"type" : "input", "schemaitem" : "autoRestartCount", "textbox" : classObject.autoRestartCount, "tooltip" : "Defines the number of time to automatically re-attempt a trigger before marking it as failed"})
            formData.append({"type" : "checkbox", "schemaitem" : "enabled", "checked" : classObject.enabled})
            formData.append({"type" : "input", "schemaitem" : "schedule", "textbox" : classObject.schedule})
            formData.append({"type" : "input", "schemaitem" : "maxDuration", "textbox" : classObject.maxDuration})
            formData.append({"type" : "checkbox", "schemaitem" : "onlyNew", "checked" : classObject.onlyNew, "tooltip" : "When select only events with a timestamp greater than the last poll will be passed onto the jimi flow"})
            formData.append({"type" : "checkbox", "schemaitem" : "searchLive", "checked" : classObject.searchLive, "tooltip" : "Run a live search and cache the job for future polling - this reduces the overheads on humio when running the same search oftern"})
            formData.append({"type" : "input", "schemaitem" : "searchEnd", "textbox" : classObject.searchEnd})
            formData.append({"type" : "input", "schemaitem" : "searchStart", "textbox" : classObject.searchStart})
            formData.append({"type" : "input", "schemaitem" : "searchRepository", "textbox" : classObject.searchRepository})
            formData.append({"type" : "input", "schemaitem" : "searchQuery", "textbox" : classObject.searchQuery})
            formData.append({"type" : "json-input", "schemaitem" : "varDefinitions", "textbox" : classObject.varDefinitions})
            formData.append({"type" : "input", "schemaitem" : "logicString", "textbox" : classObject.logicString})
            formData.append({"type" : "checkbox", "schemaitem" : "log", "checked" : classObject.log})
            formData.append({"type" : "input", "schemaitem" : "comment", "textbox" : classObject.comment})
            return formData

    def check(self):

        if not self.humioOverrideSettings:
            if "ca" in humioSettings:
                h = humio.humioClass(humioSettings["host"],humioSettings["port"],humioSettings["apiToken"],humioSettings["secure"],humioSettings["ca"],humioSettings["requestTimeout"])
            else:
                h = humio.humioClass(humioSettings["host"],humioSettings["port"],humioSettings["apiToken"],humioSettings["secure"],requestTimeout=humioSettings["requestTimeout"])
        else:
            humioTimeout = 30
            if self.humioTimeout > 0:
                humioTimeout = self.humioTimeout
            if not hasattr(self,"plain_humioAPIToken"):
                self.plain_humioAPIToken = auth.getPasswordFromENC(self.humioAPIToken)
            if "ca" in humioSettings:
                h = humio.humioClass(self.humioHost,self.humioPort,self.plain_humioAPIToken,True,humioSettings["ca"],humioTimeout)
            else:
                h = humio.humioClass(self.humioHost,self.humioPort,self.plain_humioAPIToken,True,requestTimeout=humioTimeout)

        if "000000000001010000000000" in self._id:
            self.humioJob = ""

        if not self.humioJob or not self.searchLive:
            logging.debug("Humio No Existing Job Found, class={0}".format(self.parse(True)),10)
            kwargs = { }
            # Skipping any undefined search values
            if self.searchQuery:
                kwargs["searchQuery"] = self.searchQuery
            if self.searchStart:
                kwargs["searchStart"] = self.searchStart
            if self.searchLive:
                kwargs["searchLive"] = self.searchLive
            if self.searchEnd:
                kwargs["searchEnd"] = self.searchEnd
            createJobResult = h.createJob(self.searchRepository,**kwargs)
            if createJobResult[0] == 200:
                self.humioJob = createJobResult[1]
                self.update(["humioJob"])
                logging.debug("Humio Job Created, jobID={0}, class={1}".format(self.humioJob,self.parse(True)),8)
                time.sleep(self.jobStartWaitTime)
            else:
                systemTrigger.failedTrigger(None,"HumioJobCreateFailed","result={0}, class={1}".format(createJobResult,self.parse(True)))
                logging.debug("Humio Job Create Failed, result={0}, class={1}".format(createJobResult,self.parse(True)),5)

        if self.humioJob:
            logging.debug("Humio polling..., class={0}".format(self.parse(True)),15)
            wait = False
            if not self.searchLive:
                wait = True
            pollResult = h.pollJob(self.searchRepository,self.humioJob,wait)
            if pollResult[0] == 200 and "events" in pollResult[1]:
                if self.onlyNew:
                    events = []
                    if len(pollResult[1]["events"]) > 0:
                        for event in pollResult[1]["events"]:
                            if int(event["@timestamp"]) > self.lastEventTimestamp:
                                events.append(event)
                        self.lastEventTimestamp = int(pollResult[1]["events"][-1]["@timestamp"])/1000
                        self.update(["lastEventTimestamp"])
                    self.result["events"] = events
                else:
                    self.result["events"] = pollResult[1]["events"]
                self.result["plugin"]["humio"] = {"searchQuery" : str(self.searchQuery), "searchRepository" : str(self.searchRepository)}
            else:
                systemTrigger.failedTrigger(None,"HumioJobPollFailed","result={0}, class={1}".format(pollResult,self.parse(True)))
                logging.debug("Humio poll failed, result={0}, class={1}".format(pollResult,self.parse(True)),6)
                self.humioJob = ""
                self.update(["humioJob"])

    def setAttribute(self,attr,value,sessionData=None):
        if attr == "searchQuery":
            self.humioJob = ""
            self.update(['humioJob'])
        if attr == "humioAPIToken" and not value.startswith("ENC "):
            if db.fieldACLAccess(sessionData,self.acl,attr,accessType="write"):
                self.humioAPIToken = "ENC {0}".format(auth.getENCFromPassword(value))
                return True
            return False
        return super(_humio, self).setAttribute(attr,value,sessionData)