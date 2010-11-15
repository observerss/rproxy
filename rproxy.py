from twisted.internet import epollreactor
epollreactor.install()

from twisted.internet import protocol,reactor,ssl
from twisted.protocols.basic import LineReceiver

from twisted.application.service import Application
from twisted.application import internet,app

from twisted.web import http,server
from twisted.web.proxy import Resource,ProxyClientFactory,ProxyClient,ReverseProxyResource
from twisted.web.server import NOT_DONE_YET
from pickle import load,dump
import StringIO,gzip,zlib
import os,sys
from mako.template import Template

PATH = "/var/www/rproxy"
sys.path.append(PATH)
from rpconfig import RPConfig

WEBCONFIG = True
DEBUG = False
CONFPATH = PATH + "/rproxy.cfg"
DOMAIN = "rproxy.org"
PORT = 8484

class MyProxyClient(ProxyClient):
    def __init__(self, *args, **kwargs):
        self._buffer = ''
        self.encoding = ''
        self.ctype = ''
        self.reencode = True
        self.replace = False
        ProxyClient.__init__(self,*args,**kwargs)

    def handleHeader(self, key, value):
        value = self.factory.rp.get_aliasheader(self.factory.host,value) 
        if DEBUG:
            print key,value
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
            ProxyClient.handleHeader(self, key, value)
 
    def handleEndHeaders(self):
        #let handleResponseEnd do this
        pass 

    def handleResponsePart(self, buffer):
        if self.replace:
            self._buffer += buffer
        else:
            ProxyClient.handleResponsePart(self,buffer)

    def handleResponseEnd(self):
        if self.replace:
            if self.encoding == 'gzip':
                try:
                    buffer1 = StringIO.StringIO(self._buffer)
                    gzipper = gzip.GzipFile(fileobj=buffer1)
                    html = gzipper.read()
                except Exception as what:
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
                ProxyClient.handleHeader(self,"Content-Encoding","gzip")
            ProxyClient.handleHeader(self, "Content-Length", len(self._buffer))
            ProxyClient.handleEndHeaders(self)
            ProxyClient.handleResponsePart(self,self._buffer)
        else:
            if self.encoding:
                ProxyClient.handleHeader(self,"Content-Encoding",self.encoding)
            ProxyClient.handleEndHeaders(self)
        ProxyClient.handleResponseEnd(self) 

class MyProxyClientFactory(ProxyClientFactory):
    protocol = MyProxyClient
    def __init__(self, *args, **kwargs):
        self.host = ''
        self.realhost = ''
        self.rp = None
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
            print self.realhost,self.port,self.scheme
            print request.method
            print request.uri
            print request.clientproto
            print request.getAllHeaders()
            print request.content.read()
        clientFactory.host = self.host
        clientFactory.realhost = self.realhost
        clientFactory.rp = self.rp
        if self.scheme == 'https':
            self.reactor.connectSSL(self.realhost,self.port,clientFactory,ssl.ClientContextFactory())
        else:
            self.reactor.connectTCP(self.realhost,self.port,clientFactory)
        return NOT_DONE_YET

    def page_index(self):
            html = Template(open("index.html").read()).render(cfgs=self.rp.cfgs,domain=DOMAIN)
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
            html = Template(open("edit.html").read()).render(cfg=cfg)
            return html
        elif request.uri.startswith("/edit"):
            if request.method == "GET":
                alias = request.uri.split("=")[-1]
                cfg = self.rp.get_config(alias)
                html = Template(open("edit.html").read()).render(cfg=cfg)
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
            if os.path.exists(request.uri[1:]):
                if request.uri[1:].endswith('css'):
                    request.setHeader('content-type', 'text/css')
                elif request.uri[1:].endswith('jpg'):
                    request.setHeader('content-type', 'image/jpeg')
                else:
                    request.setHeader('content-type', 'text/plain')
                return open(request.uri[1:]).read()
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


