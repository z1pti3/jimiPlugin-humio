import urllib
from datetime import datetime, timedelta
import socket,sys,json,requests
from pathlib import Path
from functools import reduce
import operator

from core import settings, logging, helpers, auth, cache, db
from core.models import action, conduct

from plugins.humio.includes import humio

humioSettings = settings.config["humio"]

class _humioSearch(action._action):
    searchQuery = str()
    searchRepository = str()
    searchStart = str()
    searchEnd = str()
    searchLive = bool()
    humioOverrideSettings = bool()
    humioJob = str()
    humioHost = str()
    humioPort = int()
    humioAPIToken = str()
    humioTimeout = int()

    def run(self,data,persistentData,actionResult):
        searchQuery = helpers.evalString(self.searchQuery,{"data" : data})
        searchRepository = helpers.evalString(self.searchRepository,{"data" : data})
        searchStart = helpers.evalString(self.searchStart,{"data" : data})
        searchEnd = helpers.evalString(self.searchEnd,{"data" : data})

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

        if not self.searchLive:
            kwargs = { }
            # Skipping any undefined search values
            if searchQuery:
                kwargs["searchQuery"] = searchQuery
            if searchStart:
                kwargs["searchStart"] = searchStart
            kwargs["searchLive"] = self.searchLive
            if searchEnd:
                kwargs["searchEnd"] = searchEnd
            createJobResult = h.createJob(searchRepository,**kwargs)
            if createJobResult[0] == 200:
                humioJob = createJobResult[1]
                wait = True
                pollResult = h.pollJob(searchRepository,humioJob,wait)
                if pollResult[0] == 200 and "events" in pollResult[1]:
                    actionResult["events"] = pollResult[1]["events"]
            actionResult["rc"] = 0
            actionResult["result"] = True
            return actionResult
        else:
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
                    actionResult["events"] = pollResult[1]["events"]
                    actionResult["humio"] = {"searchQuery" : str(self.searchQuery), "searchRepository" : str(self.searchRepository)}
                    actionResult["rc"] = 0
                    actionResult["result"] = True
                else:
                    logging.debug("Humio poll failed, result={0}, class={1}".format(pollResult,self.parse(True)),6)
                    self.humioJob = ""
                    self.update(["humioJob"])
                    actionResult["rc"] = -1
                    actionResult["result"] = False

    def setAttribute(self,attr,value,sessionData=None):
        if attr == "searchQuery":
            if db.fieldACLAccess(sessionData,self.acl,attr,accessType="write"):
                self.humioJob = ""
                self.searchQuery = value
                return True
            return False
        if attr == "humioAPIToken" and not value.startswith("ENC "):
            if db.fieldACLAccess(sessionData,self.acl,attr,accessType="write"):
                self.humioAPIToken = "ENC {0}".format(auth.getENCFromPassword(value))
                return True
            return False
        return super(_humioSearch, self).setAttribute(attr,value,sessionData=sessionData)


class _humioIngest(action._action):
    humio_ingest_token = str()
    humio_repo = str()
    field = list()
    custom_data = dict()
    custom_time = bool()
    time_field = str()
    flatten_field = str()

    def run(self,data,persistentData,actionResult):
        if not hasattr(self,"plain_humioAPIToken"):
            self.plain_humio_ingest_token = auth.getPasswordFromENC(self.humio_ingest_token)

        # Get data dict
        if len(self.custom_data) > 0:
            dataToSend = helpers.evalDict(self.custom_data,{"data" : data})
        else:
            if len(self.field) > 0:
                dataToSend = helpers.getDictValue(self.field[0],{"data" : data})
            else:
                dataToSend = data

        # Apply flatten
        if self.flatten_field:
            for key,value in data[self.flatten_field].items():
                dataToSend[key] = value
            del dataToSend[self.flatten_field]

        # Send events
        if type(dataToSend) is list:
            events = []
            for entry in dataToSend:
                events.append(self.buildEvents(entry))
            if not self.shippingHandlerBulk(events):
                actionResult["result"] = False
                actionResult["rc"] = 1
                return actionResult
        elif type(dataToSend) is dict:
            if not self.shippingHandler(dataToSend):
                actionResult["result"] = False
                actionResult["rc"] = 2
                return actionResult

        actionResult["result"] = True
        actionResult["rc"] = 0
        return actionResult

        
    def shippingHandler(self,entry):
        if self.custom_time:
            timing = entry[self.time_field]
        else:
            timing = datetime.now().timestamp()
        if self.humio_repo != "":
            self.shipHumio(entry,timing)

    def buildEvents(self,event):
        if self.custom_time:
            timing = event[self.time_field]
        else:
            timing = datetime.now().timestamp()
        return { "timestamp": timing * 1000, "attributes" : event }

    def shipHumio(self,event,timing):
        api_url = "https://{}:443/api/v1/dataspaces/{}/ingest".format(humioSettings["host"],self.humio_repo)
        headers = {"Authorization":"Bearer {}".format(self.plain_humio_ingest_token),"Content-Type":"application/json","Accept":"application/json"}
        data = [{
                    "tags" : {},
                    "events": [ { "timestamp": timing * 1000, "attributes" : event } ]
                }]
        if "ca" in humioSettings:
            r=requests.post(api_url,headers=headers,data=json.dumps(data),verify=Path(humioSettings["ca"]))
        else:
            r=requests.post(api_url,headers=headers,data=json.dumps(data))
        if r.status_code != 200:
            print(r.status_code)
            return False
        return True

    def shippingHandlerBulk(self,events):
        api_url = "https://{}:443/api/v1/dataspaces/{}/ingest".format(humioSettings["host"],self.humio_repo)
        headers = {"Authorization":"Bearer {}".format(self.plain_humio_ingest_token),"Content-Type":"application/json","Accept":"application/json"}
        data = [{
                    "tags" : {},
                    "events": events
                }]
        if "ca" in humioSettings:
            r=requests.post(api_url,headers=headers,data=json.dumps(data),verify=Path(humioSettings["ca"]))
        else:
            r=requests.post(api_url,headers=headers,data=json.dumps(data))
        if r.status_code != 200:
            print(r.status_code)
            return False
        return True

    def getFromDict(self, dataDict, mapList):
        return reduce(operator.getitem, mapList, dataDict)

    def setAttribute(self,attr,value,sessionData=None):
        if attr == "humio_ingest_token" and not value.startswith("ENC "):
            if db.fieldACLAccess(sessionData,self.acl,attr,accessType="write"):
                self.humio_ingest_token = "ENC {0}".format(auth.getENCFromPassword(value))
                return True
            return False
        return super(_humioIngest, self).setAttribute(attr,value,sessionData=sessionData)
