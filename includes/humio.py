import requests
import json
import time
from pathlib import Path

class jobPollException(Exception):
    def __init__(self,objId,objName,jobID):
        self.id = objId
        self.name = objName
        self.jobID = jobID
        
    def __str__(self):
        return "Error: Humio job could not be polled. id='{0}', name='{1}', job='{2}'".format(self.id,self.name,self.jobID)

class jobCreateException(Exception):
    def __init__(self,objId,objName,query):
        self.id = objId
        self.name = objName
        self.query = query
        
    def __str__(self):
        return "Error: Humio job could not be created. id='{0}', name='{1}', query='{2}'".format(self.id,self.name,self.query)

class humioClass():
    host = str()
    port = int()
    apiToken = str()
    apiURI = "/api/v1/"

    def __init__(self,host,port,apiToken,secure=False,ca=None,requestTimeout=30):
        self.host = host
        self.port = port
        self.apiToken = apiToken
        self.secure = secure
        self.requestTimeout = requestTimeout
        if ca:
            self.ca = Path(ca)
        else:
            self.ca = None

        self.buildHeaders()

    def buildHeaders(self):
        httpScheme = "http"
        if self.secure:
            httpScheme = "https"
        self.url = "{0}://{1}:{2}{3}".format(httpScheme,self.host,self.port,self.apiURI)
        self.headers = {
            "Authorization" : "{0} {1}".format("Bearer",self.apiToken),
            "Content-Type" : "application/json",
            "Accept" : "application/json"
        }

    def createJob(self,searchRepository,searchQuery="",searchStart="1h",searchLive=False,searchEnd=None):
        postData = { "queryString" : searchQuery, "start" : searchStart, "isLive" : searchLive }
        if searchEnd:
            postData["end"] = searchEnd
        postData = json.dumps(postData)
        try:
            if self.ca:
                response = requests.post("{0}repositories/{1}/queryjobs".format(self.url,searchRepository),headers=self.headers,data=postData,verify=self.ca,timeout=self.requestTimeout)
            else:
                response = requests.post("{0}repositories/{1}/queryjobs".format(self.url,searchRepository),headers=self.headers,data=postData,timeout=self.requestTimeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return 0, "Connection Timeout"

        if response.status_code == 200:
            return response.status_code, json.loads(response.text)["id"]
        else:
            return response.status_code, response.text

    def pollJob(self,searchRepository,jobID,wait=False):
        while True:
            try:
                if self.ca:
                    response = requests.get("{0}repositories/{1}/queryjobs/{2}".format(self.url,searchRepository,jobID),headers=self.headers,verify=self.ca,timeout=self.requestTimeout)
                else:
                    response = requests.get("{0}repositories/{1}/queryjobs/{2}".format(self.url,searchRepository,jobID),headers=self.headers,timeout=self.requestTimeout)
            except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
                return 0, "Connection Timeout"

            if response.status_code == 200:
                if not wait or json.loads(response.text)["done"]:
                    return response.status_code, json.loads(response.text)
            else:
                return response.status_code, response.text
            time.sleep(0.1)

    def deleteJob(self,searchRepository,jobID):
        try:
            if self.ca:
                response = requests.delete("{0}repositories/{1}/queryjobs/{2}".format(self.url,searchRepository,jobID),headers=self.headers,verify=self.ca,timeout=self.requestTimeout)
            else:
                response = requests.delete("{0}repositories/{1}/queryjobs/{2}".format(self.url,searchRepository,jobID),headers=self.headers,timeout=self.requestTimeout)
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            return 0, "Connection Timeout"

        if response.status_code != 200:
            return response.status_code, response.text
        else:
            return response.status_code

