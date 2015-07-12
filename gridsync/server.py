# -*- coding: utf-8 -*-

import os
import sys
import time
import threading
import subprocess
import logging

try: # Hack to get around PyInstaller's Twisted hook
    del sys.modules['twisted.internet.reactor']
except KeyError:
    pass

from PyQt4.QtGui import QApplication
app = QApplication(sys.argv)
from qtreactor import pyqt4reactor
pyqt4reactor.install()

from twisted.internet.protocol import Protocol, Factory
from twisted.internet import reactor, task

from config import Config
from tahoe import Tahoe, bin_tahoe
#from watcher import Watcher
from systray import SystemTrayIcon


class ServerProtocol(Protocol):
    def dataReceived(self, data):
        logging.debug("Received command: " + str(data))
        self.factory.parent.handle_command(data)


class ServerFactory(Factory):
    protocol = ServerProtocol
    def __init__(self, parent):
        self.parent = parent


class Server():
    def __init__(self, args):
        self.args = args
        self.gateways = []
        self.sync_state = 0
        self.config = Config(self.args.config)

        logfile = os.path.join(self.config.config_dir, 'gridsync.log')
        logging.basicConfig(
                format='%(asctime)s %(message)s', 
                filename=logfile, 
                #filemode='w',
                level=logging.DEBUG)
        logging.info("Server initialized: " + str(args))
        if sys.platform == 'darwin': # Workaround for PyInstaller
            os.environ["PATH"] += os.pathsep + "/usr/local/bin" + os.pathsep \
                    + "/Applications/tahoe.app/bin" + os.pathsep \
                    + os.path.expanduser("~/Library/Python/2.7/bin") \
                    + os.pathsep + os.path.dirname(sys.executable) \
                    + '/Tahoe-LAFS/bin'
        logging.debug("$PATH is: " + os.getenv('PATH'))
        logging.info("Found bin/tahoe: " + bin_tahoe())

        try:
            self.settings = self.config.load()
        except IOError:
            self.settings = {}


        try:
            output = subprocess.check_output(["tahoe", "-V"])
            tahoe = output.split('\n')[0]
            logging.info("tahoe -V = " + tahoe)
        except Exception as e:
            logging.error('Error checking Tahoe-LAFS version: %s' % str(e))
            #sys.exit()

    def build_objects(self):
        logging.info("Building Tahoe objects...")
        logging.info(self.settings)
        for node, settings in self.settings.items():
            t = Tahoe(self, os.path.join(self.config.config_dir, node), settings)
            self.gateways.append(t)

    def handle_command(self, command):
        if command.lower().startswith('gridsync:'):
            logging.info('got gridsync uri')
        elif command == "stop" or command == "quit":
            self.stop()
        else:
            logging.info("Invalid command: " + command)

    def check_state(self):
        if self.sync_state:
            self.tray.start_animation()
        else:
            self.tray.stop_animation()

    def notify(self, title, message):
        self.tray.show_message(title, message)

    def start_gateways(self):
        logging.info("Starting gateway(s)...")
        logging.info(self.gateways)
        threads = [threading.Thread(target=o.start) for o in self.gateways]
        [t.start() for t in threads]
        [t.join() for t in threads]

    def first_run(self):
        from tutorial import Tutorial
        t = Tutorial(self)
        t.exec_()
        logging.debug("Got first run settings: ", self.settings)

        self.build_objects()
        self.start_gateways()

    def start(self):
        reactor.listenTCP(52045, ServerFactory(self), interface='localhost')
        if not self.settings:
            reactor.callLater(0, self.first_run)
        else:
            self.build_objects()
            print 'built objecs'
            reactor.callLater(0, self.start_gateways)
        self.tray = SystemTrayIcon(self)
        self.tray.show()
        loop = task.LoopingCall(self.check_state)
        loop.start(1.0)
        reactor.addSystemEventTrigger("before", "shutdown", self.stop)
        reactor.run()
        #sys.exit(app.exec_())

    def stop(self):
        #self.stop_watchers()
        #self.stop_gateways()
        self.config.save(self.settings)
        #sys.exit()
        
    def stop_gateways(self):
        threads = [threading.Thread(target=o.stop) for o in self.gateways]
        [t.start() for t in threads]
        [t.join() for t in threads]
        #reactor.stop()

