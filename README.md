# jimiPlugin-humio

Unlock jimi’s potential  by adding the Humio plugin. Humio is an event log management solution but combined with jimi the possibilities are endless. 

Use jimi in combination with Humio to create powerful jimiFlows that respond to your data. For example:
* Target online systems for software deployment, 
* Create alerts when threshold are met ( can be done per host, per metric etc )
* Security event enrichment
* Event filtering
* Automaticaly respond to system failures and carry out automated actions

API details are required within jimi settings.json file

```
humio : {
  "host": "<host>",
  "port": <port>,
  "apiToken": "<apiToken>",
  "secure" : <true/false>, - Optional
  "ca" : "<CAPATH>", - Optional
  "requestTimeout": <TimeoutValue> - Optional
}
```
