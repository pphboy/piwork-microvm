# Public endpoints only. Capture diagnostics even when an external request fails.
import datetime,json,socket,urllib.error,urllib.request
out={'utc':datetime.datetime.now(datetime.timezone.utc).isoformat()}
try:out['dns']=bool(socket.getaddrinfo('example.com',443))
except Exception as error:out['dns']=False;out['dnsError']=str(error)
for name,url in [('https','https://example.com'),('unauthenticatedAIAPI','https://api.openai.com/v1/models')]:
 try:out[name]=urllib.request.urlopen(url,timeout=20).status
 except urllib.error.HTTPError as error:out[name]=error.code
 except Exception as error:out[name]=str(error)
print(json.dumps(out))
