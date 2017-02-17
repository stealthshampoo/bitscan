import os
import sys
import time
import signal
import bitscan
import threading
from twitchbot import TwitchBot

class State:
    def __init__(self):
        self.on = False
        self.ack = False

def main(argv):
    state = State()

    def signal_exit(signal, frame):
        state.on = False
        bot.quitirc("Bye.")
        while state.ack is False: None
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_exit)
    signal.signal(signal.SIGTERM, signal_exit)

    while 1:
        bot = TwitchBot()
        bot.setInfoFromConfig('bot.txt')
        bot.start()

        scan_thread = threading.Thread(target=bitscan.scan, args=(bot,state))
        
        state.on = True
        state.ack = False
        scan_thread.start()

        time.sleep(3600)
        state.on = False
        bot.quitirc("Bye.")
        while state.ack is False: None

        del scan_thread

if __name__ == '__main__':
    main(sys.argv)
