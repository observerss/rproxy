from twisted.internet import epollreactor
epollreactor.install()

from twisted.internet import protocol,reactor,ssl
from twisted.protocols.basic import LineReceiver

from twisted.application.service import Application
from twisted.application import internet,app

from twisted.web import http,server
from twisted.web.proxy import Resource,ProxyClientFactory,ProxyClient,ReverseProxyResource
from twisted.web.server import NOT_DONE_YET

from twisted.python import logfile
app.logfile.LogFile = logfile.DailyLogFile

from pickle import load,dump
import StringIO,gzip,zlib
import os,sys
from mako.template import Template
from hashlib import md5

PATH = "/var/www/rproxy"
#app.logfile.directory = PATH+"/logs"
sys.path.append(PATH+"/src")
from rpconfig import RPConfig
from caching import Cache

WEBCONFIG = True
DEBUG = False
CONFPATH = PATH + "/rproxy.cfg"
DOMAIN = "rproxy.org"
PORT = 8484
CACHE_MEMORYLIMIT = 64*1024*1024
CACHE_MAXOBJECT = 256*1024
CACHE_DURATION = 60*60*24
GLOBALCACHE = Cache(CACHE_MEMORYLIMIT,CACHE_MAXOBJECT,CACHE_DURATION)

class MyProxyClient(ProxyClient):
    def __init__(self, *args, **kwargs):
        self._buffer = []
        self.encoding = ''
        self.ctype = ''
        self.reencode = True
        self.replace = False
        self.headers_to_cache = {}
        ProxyClient.__init__(self,*args,**kwargs)

    def handleHeader(self, key, value):
        value = self.factory.rp.get_aliasheader(self.factory.host,value) 
        if DEBUG:
            pass
            #print key,value
        if key == "Content-Type" and (value.startswith("text") or \
                ("java" in value) or ("flash" in value)):
            self.replace = True
            self.ctype = value
        if key == "Content-Encoding":
            self.encoding = value
            return
        if key == "Content-Length":
            return
        else:
            self.headers_to_cache[key] = value
            ProxyClient.handleHeader(self, key, value)
 
    def handleResponsePart(self, buffer):
        #self._buffer += buffer
        self._buffer.append(buffer)
        if not self.replace:
            ProxyClient.handleResponsePart(self,buffer)

    def handleResponseEnd(self):
        self._buffer = ''.join(self._buffer)
        if self.replace: #if content replace is needed
            if self.encoding == 'gzip':
                try:
                    buffer1 = StringIO.StringIO(self._buffer)
                    gzipper = gzip.GzipFile(fileobj=buffer1)
                    html = gzipper.read()
                except Exception, what:
                    print self.factory.realhost,what
                    html = self._buffer
            elif self.encoding == 'deflate':
                try:
                    html = zlib.decompress(self._buffer)
                except zlib.error:
                    html = zlib.decompress(self._buffer, -zlib.MAX_WBITS)
            else:
                html = self._buffer
            self._buffer = self.factory.rp.process(self.factory.host,self.ctype,html)
            if self.reencode and ("flash" not in self.ctype):
                newbuffer = StringIO.StringIO()
                gzipper = gzip.GzipFile(fileobj=newbuffer,mode='wb')
                gzipper.write(self._buffer)
                gzipper.close()
                self._buffer = newbuffer.getvalue()
                self.headers_to_cache["Content-Encoding"]="gzip"
                ProxyClient.handleHeader(self,"Content-Encoding","gzip")
            self.headers_to_cache["Content-Length"]=len(self._buffer)
            ProxyClient.handleHeader(self, "Content-Length", len(self._buffer))
            ProxyClient.handleResponsePart(self,self._buffer)
        else:
            if self.encoding:
                self.headers_to_cache["Content-Encoding"]=self.encoding
                ProxyClient.handleHeader(self,"Content-Encoding",self.encoding)
            ProxyClient.handleEndHeaders(self)
            if len(self._buffer):
                self.factory.cache.set(self.factory.key,(self.headers_to_cache,self._buffer))
        ProxyClient.handleResponseEnd(self) 

class MyProxyClientFactory(ProxyClientFactory):
    protocol = MyProxyClient
    def __init__(self, *args, **kwargs):
        self.host = ''
        self.realhost = ''
        self.rp = None
        self.cache = None
        self.key = None
        ProxyClientFactory.__init__(self,*args,**kwargs)

    def buildProtocol(self, addr):
        p = self.protocol(self.command, self.rest, self.version,
                             self.headers, self.data, self.father)
        p.factory = self
        return p


class MyReverseProxyResource(Resource): 
    proxyClientFactoryClass = MyProxyClientFactory
    def __init__(self,reactor=reactor):
        Resource.__init__(self)
        self.rp = RPConfig(CONFPATH,domain=DOMAIN)
        self.cache = GLOBALCACHE
        self.reactor = reactor
        self.scheme = ''
        self.host = ''
        self.port = 80
        self.realhost = ''

    def getChild(self, path, request):
        """
        Create and return a proxy resource with the same proxy configuration
        as this one, except that its path also contains the segment given by
        C{path} at the end.
        """
        return MyReverseProxyResource(self.reactor)
    
    def render(self, request):
        """
        Render a request by forwarding it to the proxied server.
        """
        #robots
        if request.uri == "/robots.txt":
            return open(PATH+"/robots.txt").read()

        self.host = request.received_headers['host']
        if self.host == DOMAIN or \
            self.host == "www."+DOMAIN:
            return self.confpage(request)
        
        self.realhost,self.port,self.scheme = self.rp.get_realhost(self.host)
        # if no alias is found, confpage again
        if self.realhost == self.host:
            return self.confpage(request)

        if request.getHeader("x-forwarded-proto")=="https":
            if not self.scheme:
                self.port = 443
                self.scheme = 'https'

        for k,v in request.getAllHeaders().items():
            request.received_headers[k] = self.rp.get_realheader(self.host,v)

        request.received_headers['host'] = self.realhost
        request.content.seek(0, 0)
        clientFactory = self.proxyClientFactoryClass(
            request.method, request.uri, request.clientproto,
            request.getAllHeaders(), request.content.read(), request)
        if DEBUG:
            print self.realhost,self.port,self.scheme,request.method,request.uri
            #print request.clientproto
            #print request.getAllHeaders()
            #print request.content.read()
        clientFactory.host = self.host
        clientFactory.realhost = self.realhost
        clientFactory.rp = self.rp
        clientFactory.cache = self.cache

        #cached?
        key = md5(self.host+request.uri).hexdigest()
        if request.method == "GET":
            cacheddata = self.cache.get(key)
            if cacheddata:
                headers,data = cacheddata
                #request.setResponseCode(304,'(Not Modified)')
                request.setResponseCode(200,'OK')
                for k,v in headers.items():
                    request.setHeader(k,v)
                return data
        clientFactory.key = key

        if self.scheme == 'https':
            self.reactor.connectSSL(self.realhost,self.port,clientFactory,ssl.ClientContextFactory())
        else:
            self.reactor.connectTCP(self.realhost,self.port,clientFactory)
        return NOT_DONE_YET

    def page_index(self):
            html = Template(open(PATH+"/templates/index.html").read()).render(cfgs=self.rp.cfgs,domain=DOMAIN)
            return html

    def confpage(self,request):
        if not WEBCONFIG:
            return "web config is disabled."
        if request.uri == "/":
            return self.page_index()
        elif request.uri.startswith("/del"):
            alias = request.uri.split("=")[-1]
            self.rp.del_alias(alias)
            return self.page_index()
        elif request.uri.startswith("/add"):
            cfg = ['','','Y','Y','Y','Y','N','N']
            html = Template(open(PATH+"/templates/edit.html").read()).render(cfg=cfg)
            return html
        elif request.uri.startswith("/edit"):
            if request.method == "GET":
                alias = request.uri.split("=")[-1]
                cfg = self.rp.get_config(alias)
                html = Template(open(PATH+"/templates/edit.html").read()).render(cfg=cfg)
                return html
            elif request.method == "POST":
                args = request.args
                try:
                    target = args['target'][0]
                    alias = args['alias'][0]
                    html = args['html'][0].upper()
                    css = args['css'][0].upper()
                    js = args['js'][0].upper()
                    flash = args['flash'][0].upper()
                    extern = args['global'][0].upper()
                    sslonhttp = args['sslonhttp'][0].upper()
                    if alias:
                        self.rp.add_alias(target,alias,html,css,js,flash,extern,sslonhttp)
                except:
                    pass
                return self.page_index() 
        else:
            if os.path.exists(PATH+request.uri):
                if request.uri.endswith('css'):
                    request.setHeader('content-type', 'text/css')
                elif request.uri.endswith('jpg'):
                    request.setHeader('content-type', 'image/jpeg')
                else:
                    request.setHeader('content-type', 'text/plain')
                return open(PATH+request.uri).read()
            else:
                return "Not Found"
 
site = server.Site(MyReverseProxyResource())
#site = server.Site(ReverseProxyResource('www.google.com',80,''))
if DEBUG:
    reactor.listenTCP(PORT, site)
    reactor.run()
application = Application("RProxy")
appService = internet.TCPServer(PORT,site)
appService.setServiceParent(application)


