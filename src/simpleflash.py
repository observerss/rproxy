from bitstring import BitString,pack
import zlib
from StringIO import StringIO
import re
# this simple content replacer is written according to the flash specification:
# @ http://www.adobe.com/devnet/swf.html

class SimpleFlash:
    def __init__(self,filestr):
        try:
            self.data = filestr
            b = BitString(bytes=filestr[:8])
            self.signature = b.read('bytes:3') #FWS/SWS
            self.version = b.read('uint:8')
            self.filelength = b.read('uintle:32')
            self.sizelen = self.xmin = self.xmax = self.ymin = self.ymax = 0
            self.framerate = self.framecount = 0
            self.tags = []
            #print self.signature,self.version,self.filelength
            if self.signature=='CWS':
                data = zlib.decompress(filestr[8:])
                self.parse(data)
            else:
                self.parse(filestr[8:])
            self.parsed = True
        except Exception as what:
            print what
            self.parsed = False


    def replace(self,pat1,pat2):
        if self.parsed:
            for i in range(len(self.tags)):
                self.tags[i][1] = self.tags[i][1].replace(pat1,pat2)
            return self.get_swf()
        else:
            return self.data

    def parse(self,data):
        totalbits = len(data)*8
        b = BitString(bytes=data)
        self.sizelen = b.read('uint:5')
        if self.sizelen>0:
            self.xmin = b.read('uint:%d'%self.sizelen)
            self.xmax = b.read('uint:%d'%self.sizelen)
            self.ymin = b.read('uint:%d'%self.sizelen)
            self.ymax = b.read('uint:%d'%self.sizelen)
            taillen = (self.sizelen*4+5)%8 != 0 and 8-(self.sizelen*4+5)%8 or 0
        else:
            self.xmin=self.xmax=self.ymin=self.ymax=0
            taillen = 3
        b.read('uint:%d'%taillen)
        self.framerate = b.read('uint:16')
        self.framecount = b.read('uintle:16')
        #print self.sizelen,self.xmin,self.xmax,self.ymin,self.ymax
        #print self.framerate,self.framecount
        while b.pos<totalbits:
            tagcl = b.read('uintle:16')
            tagcode = (tagcl>>6)
            taglen = tagcl&0x3f
            if taglen == 0x3f:
                taglen = b.read('intle:32')
            tagdata = b.read('bytes:%d'%taglen)
            self.tags.append( [tagcode,tagdata] )
            #print tagcode,taglen

    def get_swf(self):
        if not self.parsed:
            return ''
        b = BitString(bytes='')
        b.append('uint:5=%d'%self.sizelen)
        if self.sizelen>0:
            b.append('uint:%d=%d'%(self.sizelen,self.xmin))
            b.append('uint:%d=%d'%(self.sizelen,self.xmax))
            b.append('uint:%d=%d'%(self.sizelen,self.ymin))
            b.append('uint:%d=%d'%(self.sizelen,self.ymax))
            taillen = (self.sizelen*4+5)%8 != 0 and 8-(self.sizelen*4+5)%8 or 0
        else:
            taillen = 3
        b.append('uint:%d=0'%taillen)
        b.append('uint:16=%d'%self.framerate)
        b.append('uintle:16=%d'%self.framecount)
        for tagcode,tagdata in self.tags:
            taglen = len(tagdata)
            if taglen >= 0x3f:
                b.append('uintle:16=%d'%((tagcode<<6)|0x3f))
                b.append('intle:32=%d'%len(tagdata))
            else:
                b.append('uintle:16=%d'%((tagcode<<6)|taglen))
            b.append(BitString(bytes=tagdata))
        data = b.tobytes()
        self.filelength = len(data)
        if self.signature == 'CWS':
            data = zlib.compress(data)
        b = BitString(bytes='')
        b.append(BitString(bytes=self.signature))
        b.append(BitString('uint:8=%d'%self.version))
        b.append(BitString('uintle:32=%d'%self.filelength))
        header = b.tobytes()
        return header + data
        

if __name__ == "__main__":
    sf = SimpleFlash(open("test.swf","rb").read())
    open("out.swf","wb").write(sf.replace("youtube.com","yt.rproxy.org"))
