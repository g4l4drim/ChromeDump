from tornado.websocket import websocket_connect
from tornado.ioloop import IOLoop
from tornado import gen
import subprocess # gestion des sous-processs / suivis du processus chromium
import logging
import os
import sys # lancement de chromium comme subrpocess
import json
import requests
import asyncio
import time
import base64, binascii
import mimetypes #file type management
from datetime import datetime
import argparse


def timestamp():
    #return int(round(time.time() * 1000))
    return datetime.utcnow().isoformat(sep=' ', timespec='milliseconds')

def filett():
    return datetime.utcnow().strftime("%Y-%m-%d_%H-%M-%S_%f")


def is_base64(s):
    try:
        base64.b64decode(s,validate=True)
        return True
    except binascii.Error:
        return False

class Dumplog():
    def __init__(self,savedir):
        self.savedir=savedir
        logging.basicConfig(filename=savedir+"/dumpweb.log",
                filemode='a', 
                level=logging.DEBUG,
                format='%(asctime)s %(levelname)-8s %(message)s',
                datefmt='%Y-%m-%d %H:%M:%S')
        logging.getLogger().addHandler(logging.StreamHandler(sys.stdout))
        self.httplogreq=savedir+"/httplogreq.json"
        self.httplogres=savedir+"/httplogres.json"
        self.urllist=savedir+"/urls.txt"
        self.jsconsolelog=savedir+"/consolelog.txt"
        self.jslog=savedir+"/jslog.json"
        self.otherlog=savedir+"/other.json"

    def info(self, msg, *args):
        logging.info(msg, *args)

    def debug(self, msg, *args):
        logging.debug(msg, *args)

    def httpreq(self, req):
        self.__appendfile(self.httplogreq, req)

    def httpres(self, res):
        self.__appendfile(self.httplogres, res)

    def url(self, url):
        self.__appendfile(self.urllist,url+"\n")

    def js(self, log):
        self.__appendfile(self.jslog, log+"\n")
        
    def jsconsole(self, log):
        self.__appendfile(self.jsconsolelog, log)

    def other(self, log):
        self.__appendfile(self.otherlog, log)

    def __appendfile(self,filename,content):
        with open(filename,"a") as fd:
            fd.write(content)
            fd.close()


class Dumpfiles():
    def __init__(self, savedir):
        self.savedir=savedir
        self.screenshotdir=savedir+"/screenshots"
        os.mkdir(self.screenshotdir)
        self.dldir=savedir+"/downloads"
        os.mkdir(self.dldir)
        self.filedir=savedir+"/files"
        os.mkdir(self.filedir)
        self.jsdir=savedir+"/js"
        os.mkdir(self.jsdir)

    def sc(self, scname, scbytes):
        """save screenshot"""
        self.__cwfile(self.screenshotdir+"/"+scname,"wb",scbytes)

    def js(self,jsname,jscode):
        """save javascript code"""
        self.__cwfile(self.jsdir+"/"+jsname, "w", jscode)

    def wasm(self, wasmname, bytecode):
        self.__cwfile(self.jsdir+"/"+wasmname, "wb", bytecode)

    def rawfile(self,filename, rawdata):
        """save bytes in file"""
        self.__cwfile(self.filedir+"/"+filename, "wb", rawdata)

    def file(self,filename,strdata):
        """save strings in file"""
        self.__cwfile(self.filedir+"/"+filename, "w", strdata)

    def __cwfile(self, filename, mode, data):
        with open(filename, mode) as fd:
            fd.write(data)
            fd.close()

class Browser():
    def __init__(self,host, port, savedir):
        self.browser_host=host
        self.browser_port=port
        self.browser_host_port="{}:{}".format(host,port)
        self.tab_dict=dict()
        self.ioloop = IOLoop.instance()
        self.result_dir=savedir
        self.dumpfile=Dumpfiles(savedir)
        self.dumplog=Dumplog(savedir)
        self.callback={
            "new_tab": self.new_tab,
            "close_tab": self.close_ws
        }
        tab_list_requests=requests.get("http://{}/json".format(self.browser_host_port))
        if tab_list_requests.ok:
            for tab in tab_list_requests.json():
                self.dumplog.info(tab["id"])
                self.new_tab(tab["id"])
                self.tab_dict[tab["id"]].connect()
        self.ioloop.start()
       

    def new_tab(self,target_id):
        if not target_id in self.tab_dict.keys():
            self.dumplog.info(target_id)
            self.tab_dict[target_id] = TabHandler(self.browser_host_port, target_id, self.callback, self.result_dir, self.dumplog, self.dumpfile)

    def close_ws(self, target_id):
        del self.tab_dict[target_id]
        if len(self.tab_dict) == 0:
            time.sleep(5)
            self.ioloop.stop()

    def create_tab(self):
        pass

    def open_url(tab_id):
        pass

    def close_tab(tab_id):
        pass

class TabHandler():
    id=1
    
    def __init__(self,browser_host_port, target_id, callback, result_dir,dumplog,dumpfile):
        self.browser_host_port=browser_host_port
        self.target_id=target_id
        self.dldir= result_dir+"/downloads"
        self.dumplog=dumplog
        self.dumpfile=dumpfile
        self.target_ws_url="ws://{}/devtools/page/{}".format(browser_host_port,target_id)
        self.ws_message_list=list()
        self.callback=callback
        self.sourceindex={}
        self.bodyindex={}
        self.ws=None
        self.connect()

        
    
    @gen.coroutine
    def connect(self):
        
        self.dumplog.info("new tab launched, trying to connect")
        try:
            self.dumplog.info(self.target_ws_url)
            self.ws = yield websocket_connect(self.target_ws_url)
        except Exception:
            self.dumplog.info("tab connection refused")
        else:
            self.dumplog.info("connected")
            #self.ws.on_connection_closed=self.callback["close_tab"](self.target_id)
            params_list = [
                {"id":1,"method":"Page.enable"},
                {"id":2, "method": "Network.enable",
                    "params":{}}, # {"maxPostDataSize": 65536}},
                {"id":3,"method":"Debugger.enable"},
                    #"params":{}},
                {"id":4,"method":"Debugger.setSkipAllPauses",
                    "params":{"skip":True}},
                {"id":5,"method":"Target.setDiscoverTargets",
                    "params":{"discover":True}},
                {"id":6,"method":"Target.setAutoAttach","params":
                    {"autoAttach":True,"waitForDebuggerOnStart":True,"flatten":True}},
                {"id":7,"method":"Browser.setDownloadBehavior",
                    "params":{"behavior":"allow","downloadPath":self.dldir}},
                {"id":8,"method":"Console.enable"},
                    #"params":{}},
                {"id":9,"method":"Page.startScreencast",
                    "params":{
                        "format":"png",
                        "quality":50,
                        "maxWidth":1024,
                        "maxHeight":1024,
                        "everyNthFrame":1
                        }},
                {"id":10,"method":"Runtime.enable"},
                {"id":11,"method":"Runtime.runIfWaitingForDebugger"}#,
                    #"params":{}},
            ]
            id=11
            for message in params_list:
                self.write_message(message)
                self.run()

    @gen.coroutine
    def write_message(self, message):
        message_str=json.dumps(message)
        self.ws_message_list.append(message)
        self.ws.write_message(message_str)

    @gen.coroutine
    def run(self):
        while True:
            msg = yield self.ws.read_message()
            if msg is None:
                self.ws = None
                self.write_logs()
                self.callback["close_tab"](self.target_id)
                self.dumplog.info("tab close")
                break
            else:
                msg=json.loads(msg)
                #msg["eventtime"]=timestamp()
                #print(msg)
                if "method" in msg.keys():
                    method=msg["method"]
                    self.dumplog.debug("method="+method)
                    params=msg["params"]
                    if method=="Target.targetCreated":
                        target_info=params["targetInfo"]
                        if target_info["type"] == "page":
                            self.callback["new_tab"](target_info["targetId"])
                    elif method=="Network.dataReceived":
                        if params["dataLength"] > 0:
                            requestid=params["requestId"]
                            self.write_message(message={"id":self.id,"method":"Network.getResponseBody","params":{"requestId":requestid}})
                            self.bodyindex[self.id]=requestid
                            self.id= self.id+1
                    elif method=="Debugger.scriptParsed":
                            scriptid=params["scriptId"]
                            self.write_message(message={"id":self.id,"method":"Debugger.getScriptSource","params":{"scriptId":scriptid}})
                            self.sourceindex[self.id]=scriptid
                            self.id= self.id+1
                    elif method=="Page.screencastFrame":
                        sessionId=params["sessionId"]
                        self.write_message(message={"id":self.id,"method":"Page.screencastFrameAck","params":{"sessionId":sessionId}})
                        self.id= self.id+1
                self.ws_message_list.append(msg)
                    

    def write_logs(self):
        self.dumplog.debug("%s messages to save" % len(self.ws_message_list))
        scripts={}
        bodies={}
        for msg in self.ws_message_list:
            if "method" in msg.keys() and "params" in msg.keys():
                method=msg["method"]
                #print("method="+method)
                params=msg["params"]
                if method =="Debugger.scriptParsed":
                    self.dumplog.js(json.dumps(params,indent=2))
                    scripts[params["scriptId"]]=params
                elif method =="Console.messageAdded":
                    self.dumplog.jsconsole(json.dumps(params,indent=2))
                elif method =="Network.requestWillBeSent":
                    url=msg["params"]["request"]["url"]
                    self.dumplog.url(url)
                    self.dumplog.httpreq(json.dumps(params,indent=2))
                elif method =="Network.responseReceived":
                    self.dumplog.httpres(json.dumps(params,indent=2))
                    bodies[params["requestId"]]=params
                elif method =="Page.screencastFrame":
                    filename="%s_%s.png" % (params["sessionId"],params["metadata"]["timestamp"])
                    self.dumpfile.sc(filename, base64.b64decode(params["data"]))
            elif "result" in msg.keys():
                rid=msg["id"]
                result=msg["result"]
                if "scriptSource" in result.keys():
                    #print(scripts)
                    filename="_error_"
                    if rid in self.sourceindex.keys():
                        filename=scripts[self.sourceindex[rid]]["hash"]
                    else:
                        filename="%s" % self.sourceindex[rid]
                    if "bytecode" in result.keys():
                        self.dumpfile.wasm(filename+".wasm",base64.b64decode(result["bytecode"]))
                    else:
                        self.dumpfile.js(filename+".js",result["scriptSource"])
                elif "body" in result.keys():
                    body=result["body"]            
                    filename="__error__"
                    orphaned=True
                    if rid in self.bodyindex.keys():
                        orphaned=False
                        filename="%s" % self.bodyindex[rid]
                    else:
                        filename="%s" % rid
                    if orphaned:
                        self.dumpfile.file(filename,body)
                    else:
                        response=bodies[self.bodyindex[rid]]["response"]
                        self.dumplog.debug(response["mimeType"])
                        extension=mimetypes.guess_extension(response["mimeType"])
                        self.dumplog.debug(extension)
                        if extension == None :
                            extension=""
                        filename=filename+extension
                        if result["base64Encoded"]:
                            print("base64 body:"+filename)
                            body=base64.b64decode(body)
                            self.dumpfile.rawfile(filename,body)
                        else:
                            self.dumpfile.file(filename,body)
            else:
                self.dumplog.other(json.dumps(msg,indent=2))
        self.dumplog.info("done saving")

if __name__ == "__main__":
    
    parser= argparse.ArgumentParser(description='ChromeDump - CDP Based JavaScript dumper') 
    
    parser.add_argument('-u','--url', dest='url_list', type=str, nargs='+',help='urls to open')
    parser.add_argument('-z','--zip', dest='compress', type=bool, nargs='?',help='create a zip archive (based on linux zip command)',default=True)
    parser.add_argument('-p','--password', dest='password', type=str, nargs='?',help='password for the zip archive', default='infected')
    parser.add_argument('--remote-debugging-port', dest='cdp_port', type=str, nargs='?', help='CDP port to connect to', default='9222')
    parser.add_argument('--remote-debuging-ip',dest='cdp_ip',type=str,nargs='?',help='CDP target ip',default='127.0.0.1')
    parser.add_argument('--chromeargs', dest='chrome_args', type=str, nargs='+', help='arguments passed to the chrome/chromium binary',default=[])
    parser.add_argument('--no-profile', dest='chrome_noprofile', type=bool,nargs='?',help="do not generate a new profile, use the existing one",default=False)
    parser.add_argument('-b','--chrome-binary', dest='chrome_bin', type=str, nargs='?', help='Chrome/Chromium binary to use', default="chromium")    
    
    dumptime=time.strftime("%Y-%m-%d_%H-%M-%S")
    parser.add_argument('-d', dest='savedir', type=str, nargs='?', help='directory location to store dumped data',default=("dump_%s" % dumptime))

    
    args = parser.parse_args()
    print(args)
    os.mkdir(args.savedir)
    profiledir=args.savedir+"/profile"
    os.mkdir(profiledir)
    chromeargs=[args.chrome_bin,"--remote-debugging-port="+args.cdp_port]
    if not args.chrome_noprofile:
        chromeargs=chromeargs+["--user-data-dir="+profiledir]
    chromeargs=chromeargs+args.chrome_args
    chromium= subprocess.Popen([args.chrome_bin,"--remote-debugging-port="+args.cdp_port,"--user-data-dir="+profiledir],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    #wait for CDP log line
    chromeout= chromium.stderr.readline().decode()
    while "DevTools listening on" not in chromeout:
        chromeout= chromium.stderr.readline().decode()
    time.sleep(1)
    client = Browser(args.cdp_ip,args.cdp_port,args.savedir)
    if args.compress:
        tar= subprocess.Popen(["zip","-e","-P {}" % args.password,"-r",args.savedir+".zip",args.savedir])
        tar.wait()
        #remove dir
        cleandir = subprocess.Popen(["rm","-rf",args.savedir])
        cleandir.wait()

