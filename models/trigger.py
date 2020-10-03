import urllib
from datetime import datetime, timedelta

from plugins.humio.includes import humio

from core.models import trigger

from core import settings, logging, auth, db

from system.models import trigger as systemTrigger

humioSettings = settings.config["humio"]

class _humio(trigger._trigger):
    humioJob = str()
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

        if not self.humioJob:
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