import time,heapq

class Cache:
    def __init__(self,memorylimit=64*1024*1024,maxobjectsize=1024*1024,duration=60*60):
        self.data = dict()
        self.keyheap = []

        self.uppermem = memorylimit
        self.upperitem = maxobjectsize
        self.duration = duration
        self.size = 0

    def remove(self,key):
        try:
            size = self.data[key][0]
            del self.data[key]
            self.size -= size
            return True
        except:
            return False

    def set(self,key,value,duration=None):
        if not duration:
            duration = self.duration
        #keep limits
        newsize = len(value)
        if newsize > self.upperitem:
            return
        while (self.size+newsize)>self.uppermem:
            oldestkey = heapq.heappop(self.keyheap)[1]
            self.remove(oldestkey)
        #set dict
        self.data[key] = (newsize,int(time.time()),duration,value)
        self.size += newsize
        heapq.heappush(self.keyheap,(int(time.time())+duration,key))

    def check_duration(self):
        if not len(self.keyheap):
            return
        timestamp,key = heapq.heappop(self.keyheap)
        while timestamp<int(time.time()):
            self.remove(key)
            if not len(self.keyheap):
                return
            timestamp,key = heapq.heappop(self.keyheap)
        heapq.heappush(self.keyheap,(timestamp,key))

    def get(self,key):
        self.check_duration()
        if key in self.data.keys():
            return self.data[key][-1]
        else:
            return ''

if __name__ == "__main__":
    mycache = Cache()
    mycache.set('b','b3',3)
    mycache.set('c','c2',2)
    mycache.set('d','d1',1)
    print mycache.get('b')
    print mycache.get('c')
    print mycache.get('d')
    time.sleep(1)
    print mycache.get('b')
    print mycache.get('c')
    print mycache.get('d')
    time.sleep(1)
    print mycache.get('b')
    print mycache.get('c')
    print mycache.get('d')
    time.sleep(1)
    print mycache.get('b')
    print mycache.get('c')
    print mycache.get('d')
