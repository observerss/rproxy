#!/usr/bin/env python
import re
from hashlib import md5

class RPConfig:
    def __init__(self,path,domain="rproxy.org"):
        self.path = path
        self.domain = domain
        self.cfgs = []
        self.cfgdict = {}
        self.externs = []
        self.read_config()

    def add_alias(self,target,alias,html,javascript,css,flash,extern,sslonhttp):
        key = alias+"."+self.domain
        value = (target,alias,html,javascript,css,flash,extern,sslonhttp)
        self.cfgdict[key]=value
        cfgs = []
        for x in self.cfgs:
            if x[1] != alias:
                cfgs.append(x)
        cfgs.append( value )
        self.cfgs = cfgs
        if (extern == "Y") and (key not in self.externs):
            self.externs.append(key)
        self.save()

    def del_alias(self,alias):
        key = alias+"."+self.domain
        if self.cfgdict.has_key(key):
            self.cfgdict.pop(key)
        cfgs = []
        for x in self.cfgs:
            if x[1] != alias:
                cfgs.append(x)
        self.cfgs = cfgs
        if key in self.externs:
            self.externs.remove(key)
        self.save()

    def get_config(self,alias):
        key = alias+"."+self.domain
        return self.cfgdict[key]

    def striphost(self,host):
        return '.'.join( host.split('.')[-3:] )

    def get_realhost(self,host):
        shost = self.striphost(host)
        port = 80
        scheme = ''
        if self.cfgdict.has_key(shost):
            target,alias,html,javascript,css,flash,extern,sslonhttp = self.cfgdict[shost]
            if ':' in target:
                port = int(target[target.find[':']+1:])
            if sslonhttp == "Y":
                scheme = 'http'
            realhost = host.replace(shost,target)
            return realhost,port,scheme
        return host,port,scheme

    def get_aliasheader(self,host,value):
        shost = self.striphost(host)
        if self.cfgdict.has_key(shost):
            target = self.cfgdict[shost][0]
            return value.replace(target,shost)
        return value

    def get_realheader(self,host,value):
        shost = self.striphost(host)
        if self.cfgdict.has_key(shost):
            return value.replace(shost,self.cfgdict[shost][0])
        return value

    def process(self,host,ctype,data):
        '''replace url if necaessary'''
        host = self.striphost(host)
        # replace global settings
        for ext in self.externs:
            if host!=ext:
                data = self._process(ext,ctype,data)
        # replace local settings
        data = self._process(host,ctype,data)
        # some spefic repl for facebook,twitter,etc
        data = self.__process(host,ctype,data)
        return data

    def _process(self,host,ctype,data):
        if self.cfgdict.has_key(host):
            target,alias,html,css,js,flash,extern,sslonhttp = self.cfgdict[host]
            if (ctype.startswith("text/html") and html == "Y") or \
                    (ctype.startswith("text/css") and css == "Y") or \
                    ("javascript" in ctype and js == "Y") or \
                    ("text" in ctype):
                    #(ctype.startswith("application/x-shockwave-flash") and flash == "Y"):
                data = data.replace(target,host)
        return data

    def __process(self,host,ctype,data):
        if self.cfgdict.has_key(host):
            target,alias,html,css,js,flash,extern,sslonhttp = self.cfgdict[host]
            if target == "facebook.com" and "javascript" in ctype:
                data = data.replace(r"'\/\/www.'+e+'.com\/ajax\/ua_callback.php'",
                    r"'\/\/%s\/ajax\/ua_callback.php'"%host )
            if target == "twitter.com":
                data = data.replace("document.domain = 'twitter.com';",  r"")
            if target == "twimg.com" and "javascript" in ctype:
                data = re.sub(r"document\.domain\s*=\s*('|\")twitter\.com('|\")\s*;?", r"", data)
        return data

    def save(self):
        self.write_config()

    def read_config(self):
        cfgs = open(self.path).readlines()
        for cfg in cfgs:
            cfg = self.format_config(cfg)
            if cfg:
                try:
                    target,alias,html,css,js,flash,extern,sslonhttp = cfg.split()
                    args = self.format_check(target,alias,html,css,js,flash,extern,sslonhttp)
                    self.cfgs.append( args )
                    self.cfgdict[alias+"."+self.domain] = args
                    if extern == "Y":
                        self.externs.append( alias+"."+self.domain )
                except:
                    pass

    def write_config(self):
        cfgpath = open(self.path,"w")
        docs = '''# This is the config file for rproxy
# Each line is a rproxy entry, represents target,alias,html,css,js,flash,global,sslonhttp
# the format is as follows:
# TARGET ALIAS Y/N Y/N Y/N Y/N Y/N Y/N
# e.g: 
# www.google.com gg Y Y Y Y Y N
# obmem.com ob Y Y Y Y N N
'''
        cfgpath.write(docs)
        for cfg in self.cfgs:
            cfgpath.write("%s %s %s %s %s %s %s %s\n"%cfg)
        
    def format_config(self,line):
        #remove comment
        line = re.sub(r'#.*','',line)
        #strip
        line = line.strip()
        return line

    def format_check(self,target,alias,html,css,js,flash,extern,sslonhttp):
        html = html.upper() in ["Y","N"] and html.upper() or "N"
        css = css.upper() in ["Y","N"] and css.upper() or "N"
        js = js.upper() in ["Y","N"] and js.upper() or "N"
        flash = flash.upper() in ["Y","N"] and flash.upper() or "N"
        extern = extern.upper() in ["Y","N"] and extern.upper() or "N"
        sslonhttp = sslonhttp.upper() in ["Y","N"] and sslonhttp.upper() or "N"
        return (target,alias,html,css,js,flash,extern,sslonhttp)

if __name__ == "__main__":
    rpconf = RPConfig("rproxy.cfg")
    rpconf.add_alias("playsc.com","playsc","Y","Y","Y","Y","Y","N")
    rpconf.del_alias("playsc")
