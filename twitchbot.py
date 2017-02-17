'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''
The main library for running the Twitch bot. The TwitchBot class will be the bot
itself. The settings can be done manually or read from a config file. The
example config file shows some of the options. A simple implementation
of the bot would be:

   bot = TwitchBot()
   bot.setInfoFromConfig('config.txt')
   bot.start()

From there the bot will read the configuration from the config file and
do all the connections.

Use incoming() to receive text which will return an IRCMessage instance.

'''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''''

import re
import time
import json
import socket
import random
import datetime
import requests
import threading

# Class for parsing the IRC incoming messages.
# Not every message will be associated with every variable
class _IRCMessage:

    def __init__(self, text):
        self.message   = ''
        self.prefix    = ''

        self.username      = ''
        self.host      = ''
        self.serv      = ''
    
        self.IRCcmd    = ''
        self.IRCparams = []
        self.body      = ''

        self.command   = ''
        self.argument  = ''

        self.tag = None
        # End declarations

        if text.startswith(':'):
            if len(text.split(' ')) < 2:
                return
            
            self.message = text.partition(':')[2]
            self.prefix  = self.message.split()[0]

            if self.prefix.find('!') != -1 and self.prefix.find('@') != -1:
                self.username = self.prefix.split('!')[0]
                self.host = self.prefix.split('!')[1].split('@')[0]
                self.serv = self.prefix.split('!')[1].split('@')[0]

            self.IRCcmd = self.message.split()[1]
            
            self.IRCparams = []
            for token in self.message.split(' ')[2:]:
                if token.startswith(':'):
                    break
                self.IRCparams.append(token)

            if len(text.split(':')) > 2:
                self.body     = ':'.join(text.split(':')[2:])
                self.command  = self.body.split(' ')[0]
                if len(self.body.split(' ')) > 1:
                    self.argument = self.body.partition(' ')[2]

# This ends up being part of the _IRCMessage class
# Variable parts for Twitch's IRCv3 capabilities. 
class _IRCTag:

    def __init__(self, raw_text):
        self.tags = []
    
        # For PRIVMSG and related
        self.badges = []
        self.color = ''
        self.display_name = ''
        self.emotes= ''
        self.msg_id = '' 
        self.isMod = False
        self.isSub = False
        self.isTurbo = False
        self.room_id = 0
        self.user_id = 0
        self.user_type = ''
        self.isCheer = False
        self.bits = 0

        self.emote_sets = [] # For USERSTATE

        # For ROOMSTATE
        self.broadcaster_lang = ''
        self.r9k = False
        self.subs_only = False
        self.slow = 0
        
        # For USERNOTICE
        self.msg_param_months = 0
        self.system_msg = ''
        self.login = ''
        
        # For CLEARCHAT
        self.ban_duration = 0
        self.ban_reason = ''
        # End declarations

        text = raw_text[1:] # Remove leading @
        
        for token in text.split(';'):
            parts = token.split('=')
            if len(parts) >= 2:
                item = parts[0]
                value = parts[1]

                if item == 'badges': self.badges = value
                elif item == 'color': self.color = value
                elif item == 'display-name': self.display_name = value
                elif item == 'emotes': self.emotes = value
                elif item == 'id': self.msg_id = value
                elif item == 'mod': self.isMod = value == '1'
                elif item == 'subscriber': self.isSub = value == '1'
                elif item == 'turbo': self.isTurbo = value == '1'
                elif item == 'room-id': self.room_id = int(value)
                elif item == 'user-id': self.user_id = int(value)
                elif item == 'user-type': self.user_type = value
                elif item == 'bits':
                    self.isCheer = True
                    self.bits = int(value)
                elif item == 'emote-sets': self.emote_sets = value.split(',')
                elif item == 'broadcaster-lang': self.broadcaster_lang = value
                elif item == 'r9k': self.r9k = value == '1'
                elif item == 'subs-only': self.subs_only = value == '1'
                elif item == 'slow': self.slow = int(value)
                elif item == 'msg-param-months': self.msg_param_months = int(value)
                elif item == 'system-msg': self.system_msg = value
                elif item == 'login': self.login = value
                elif item == 'ban-duration': self.ban_duration = int(value)
                elif item == 'ban-reason': self.ban_reason = value

                self.tags.append(item)

# A timer that stores a time delay (minutes, seconds, hours) that can be checked
# Interfaced by _BotTimers, and controlled by TwitchBot
class _Timer:

    def __init__(self, ttype):
        self.rawDelay  = None # The amount of time delayed after initialization
        self.timerType = None # "sec" or "min" or "hr"

        self.time_d = None

        self.random = False
        self.randRange = ()

        self.loop = False

        self.active = False
        # End declarations
    
        if ttype not in ("sec", "min", "hr"):
            raise ValueError("type needs to be \"sec\", \"min\", or \"hr\"")
        self.timerType = ttype

    def setupDiscreteTimer(self, delay, loop):
        self.loop = loop
        self.rawDelay = delay
        self.random = False
        self.setDelay(delay)
        self.active = True

    def setupRandomTimer(self, rrange, loop):
        self.loop = loop
        self.rawDelay = 0
        self.random = True
        self.randRange = rrange
        if len(self.randRange) != 2:
            raise ValueError("Timer random range needs two specified values.")
        
        self.setDelay(0)
        self.active = True

    # If the loop is a randomly generated range, the raw delay is ignored.
    def setDelay(self, delay):
        if self.random:
            if len(self.randRange) != 2:
                raise ValueError("Timer random range needs two specified values.")
            if any([isinstance(x, int) for x in self.randRange]):
                raise ValueError("Random range must be two integer values.")
            delay = random.randint(self.randRange[0], self.randRange[1])

        now = datetime.datetime.now()
        if self.timerType == "sec":
            td = datetime.timedelta(seconds=delay)
            self.time_d = now + td
        elif self.timerType == "min":
            td = datetime.timedelta(minutes=delay)
            self.time_d = now + td
        elif self.timerType == "hr":
            td = datetime.timedelta(hours=delay)
            self.time_d = now + td
            
    def check(self):
        if not self.active:
            return False
        
        state = datetime.datetime.now() >= self.time_d

        if state:
            if self.loop:
                self.setDelay(self.rawDelay)
            else:
                self.active = False
                
        return state

# The main loop for bot timers. This will be run in a different thread to
# run in parallel with the main bot.
class _BotTimers:

    def __init__(self):
        self.timerList = []

        # These are accesed from outside to change
        self.initialized = False # Controls the main loop
        self.active = False      # Controls whether timer functions will run

        self.lock = None         # Locking thread for main loop function
    
        self.thread = threading.Thread(target=self.__loop, args=())
        self.lock = threading.Lock()
        self.initialized = True

    def begin(self):
        self.active = True
        self.thread.start()

    def __loop(self):
        while self.initialized:
            del_q = []
            self.lock.acquire(True)
            for entry in self.timerList:
                if entry['timer'].check() and self.active and not entry['paused']:
                    entry['callback'](entry['args'])
                if not entry['timer'].active:
                    del_q.append(entry)
            for e in del_q:
                self.timerList.remove(e)
            self.lock.release()
            time.sleep(1)
            
# General class for the IRC connection. Contains all join and messaging commands
class TwitchBot:
    __PRINT_OPT_MSG   = 0b00000001
    __PRINT_OPT_TAG   = 0b00000010
    __PRINT_OPT_JOIN  = 0b00000100
    __PRINT_OPT_SELF  = 0b00001000
    __PRINT_OPT_NONE  = 0b00010000
    __PRINT_OPT_MODE  = 0b00100000
    __PRINT_OPT_OTHER = 0b01000000
    __PRINT_OPT_STATE = 0b10000000
    __PRINT_OPT_ALL   = 0b11101111

    def __init__(self):
        self.__chat   = None    # Socket connection.
        self.__timers = None    # Timer loop
        self.__timercode = 0    # Timer count
        self.__printopts = 0b1100101  # Printing options

        self.server     = None
        self.channel    = None
        self.username   = None
        self.password   = None
    
        self.userlist = []    # All the users in the channel.
        self.modlist  = []    # All the elevated users, hop and higher.

        self.__variables = {}

        # Room states
        self.subs_on = False
        self.slow_on = False
        self.r9k_on  = False
        self.host_on = False
        self.emote_only_on = False
        self.msg_channel_suspended = False
        self.broadcaster_lang = ''
        # End declarations
        
        self.__chat = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.__timers = _BotTimers()

    def setInfoFromConfig(self, filename):
        try:
            with open(filename, 'r') as f:
                configLines = f.read().splitlines()
                configLines = list(configLines)
        except IOError:
            raise

        for line in configLines:
            if line.startswith('#'):
                continue
            
            tokens = line.strip().lower().split()
            [cname, eq, cvalue] = line.lower().partition('=')

            if len(tokens) < 1:
                continue

            if tokens[0] == 'declare':
                if len(tokens) < 3:
                    raise IndexError("\"declare\" must have following type, name, and value")

                type_d = {'boolean': bool,
                          'string': str,
                          'number': int}

                vartype = tokens[1]
                varname = tokens[2]

                if vartype not in type_d:
                    raise ValueError("Unknown var type \"%s\"." % vartype)
                if re.fullmatch('[a-z][\w_]+', varname) == None:
                    raise ValueError(("Variable \"%s\" must start with a letter "
                                      "and can contain only alphanumeric characters "
                                      "and underscores." % varname))
                if varname in self.__variables:
                    raise KeyError("Variable \"%s\" already declared." % varname)

                self.__variables[varname] = {}
                self.__variables[varname]['value'] = None
                self.__variables[varname]['type']  = type_d[vartype]
            elif cname.strip() == 'channel':
                channel = cvalue.strip()
                if not channel.startswith('#'):
                    raise ValueError("Channel name must start with \'#\' [%s]." % channel)
                self.channel = channel
            elif cname.strip() == 'username':
                username = cvalue.strip()
                self.username = username
            elif cname.strip() == 'password':
                password = cvalue.strip()
                if not password.startswith('oauth:'):
                    raise ValueError("Oauth must start with \"oauth:\" [%s]." % password)
                self.password = password
            elif re.fullmatch('(user|print)\.[a-z]+', cname.strip()) != None:
                namepath = cname.strip().split('.')
                option = cvalue.strip()
                self.__parseOptions(namepath, option)
            else:
                raise ValueError("Unknown option %s." % cname)

    # Parses the print.opt or user.var options
    def __parseOptions(self, namepath, value):
        if len(namepath) <= 1:
            raise IndexError("Missing variable name for \"%s\"." % '.'.join(namepath))

        if namepath[0] == 'user':
            varname = namepath[1]
            if varname not in self.__variables:
                raise KeyError("Variable \"%s\" not declared." % varname)
            if self.__variables[varname]['type'] == bool:
                if value not in ('true', 'false'):
                    raise TypeError("Variable \"%s\" not type boolean." % varname)
                self.__variables[varname]['value'] = value == 'true'
            elif self.__variables[varname]['type'] == str:
                self.__variables[varname]['value'] = value
            elif self.__variables[varname]['type'] == int:
                try:
                    self.__variables[varname]['value'] = int(value)
                except TypeError:
                    try:
                        self.__variables[varname]['value'] = float(value)
                        self.__variables[varname]['type'] = float
                    except TypeError:
                        raise TypeError("Variable \"%s\" not a valid number." % varname)
        elif namepath[0] == 'print':
            if value not in ('true', 'false'):
                raise TypeError("Print option \"%s\" not of type boolean" % namepath[2])
            opt = value == 'true'

            if namepath[1] == 'msg':
                self.setPrintOptions(msg=opt)
            elif namepath[1] == 'tag':
                self.setPrintOptions(tag=opt)
            elif namepath[1] == 'join':
                self.setPrintOptions(join=opt)
            elif namepath[1] == 'selfmsg':
                self.setPrintOptions(selfmsg=opt)
            elif namepath[1] == 'none':
                self.setPrintOptions(none=opt)
            elif namepath[1] == 'other':
                self.setPrintOptions(other=opt)
            elif namepath[1] == 'state':
                self.setPrintOptions(state=opt)
            elif namepath[1] == 'allmsg':
                self.setPrintOptions(allmsg=opt)

    # Sets what will be printed to stdout.
    def setPrintOptions(self, **kwargs):
        for key in kwargs:
            if not isinstance(kwargs[key], bool):
                raise TypeError('setPrintOptions takes only bool values.')
            
        def toggle(key, opt):
            if not kwargs[key] and self.__printopts & opt != 0:
                self.__printopts = self.__printopts ^ opt
            elif kwargs[key] and self.__printopts & opt == 0:
                self.__printopts = self.__printopts | opt
        
        if 'msg' in kwargs:
            toggle('msg', self.__PRINT_OPT_MSG)
        elif 'tag' in kwargs:
            toggle('tag', self.__PRINT_OPT_TAG)
        elif 'join' in kwargs:
            toggle('join', self.__PRINT_OPT_JOIN)
        elif 'selfmsg' in kwargs: 
            toggle('selfmsg', self.__PRINT_OPT_SELF)
        elif 'none' in kwargs:
            toggle('none', self.__PRINT_OPT_NONE)
        elif 'other' in kwargs:
            toggle('other', self.__PRINT_OPT_OTHER)
        elif 'state' in kwargs:
            toggle('state', self.__PRINT_OPT_STATE)
        elif 'allmsg' in kwargs:
            if kwargs['allmsg']:
                self.__printopts = self.__PRINT_OPT_ALL
            else:
                self.__printopts = self.__PRINT_OPT_NONE

    # Timer controls
    def initializeTimers(self):
        self.__timers = _BotTimers()
    def timersInitialized(self):
        return self.__timers is not None
    def startTimers(self):
        self.__timers.begin()
    def timersStarted(self):
        return self.__timers.active
    def pauseTimers(self):
        self.__timers.lock.acquire(True)
        self.__timers.active = False
        self.__timers.lock.release()
    def resumeTimers(self):
        self.__timers.lock.acquire(True)
        self.__timers.active = True
        self.__timers.lock.release()
    def killTimers(self):
        self.__timers.lock.acquire(True)
        self.__timers.initialized = False
        self.__timers.lock.release()
        self.__timers.lock.acquire(True) # Wait for thread to close
        self.__timers = None
    def addTimer(self, ttype, delay, callback,
                 args, rand=False, rrange=(), loop=False):

        t_entry = {}
        timer = _Timer(ttype)

        if rand:
            timer.setupRandomTimer(rrange, loop)
        else:
            timer.setupDiscreteTimer(delay, loop)

        t_entry['timer'] = timer
        t_entry['callback'] = callback
        t_entry['args'] = args
        t_entry['code'] = self.__timercode
        t_entry['paused'] = False

        # Lists are thread safe, and no existing data is modified
        self.__timers.timerList.append(t_entry)

        self.__timercode += 1
        return t_entry['code']
    def removeTimer(self, code):
        self.__timers.lock.acquire(True)
        for entry in self.__timers.timerList:
            if entry['code'] == code:
                entry['timer'].active = False
        self.__timers.lock.release()
    def pauseTimer(self, code):
        self.__timers.lock.acquire(True)
        for entry in self.__timers.timerList:
            if entry['code'] == code:
                entry['paused'] = True
        self.__timers.lock.release()
    def resumeTimer(self, code):
        self.__timers.lock.acquire(True)
        for entry in self.__timers.timerList:
            if entry['code'] == code:
                entry['paused'] = False
        self.__timers.lock.release()
    def timerExists(self, code):
        self.__timers.lock.acquire(True)
        for entry in self.__timers.timerList:
            if entry['code'] == code:
                self.__timers.lock.release()
                return True
        self.__timers.lock.release()
        return False

    def __request_chat_server(self, streamer):
        chaturl = 'https://tmi.twitch.tv'
        r = requests.get("%s/servers?channel=%s" % (chaturl, streamer))
        main = r.json()

        try:
            server = main['servers'][0].split(':')[0]
        except KeyError:
            server = 'irc.twitch.tv'
        except IndexError:
            server = 'irc.twitch.tv'

        return server
            
    def start(self):
        self.server = self.__request_chat_server(self.channel[1:])

        if any([x == None for x in (self.username, self.channel, self.password)]):
            raise ValueError("Username, channel, and password must be set.")

        print("Connecting to %s." % self.server)
        
        self.__connectServer(self.server)
        self.__authorize(self.password)
        self.__connectUsername(self.username)
        self.__connectUser(self.username, "Hello")
        self.__activateJoin()
        self.__activateTags()

        print("Bot username set as %s." % self.username)
        print("Joining channel %s." % self.channel)

        self.join(self.channel)

    # Internal connection initializations.
    def __connectServer(self, server):
        self.__chat.connect((server, 6667))
    def __connectUser(self, username, message):
        self.__chat.send(("USER %s botnick botnick :%s\r\n" % (username, message)).encode('utf-8'))
    def __connectUsername(self, username):
        self.__chat.send(("NICK %s\r\n" % username).encode('utf-8'))
    def __authorize(self, password):
        self.__chat.send(("PASS %s\r\n" % password).encode('utf-8'))
    def __activateJoin(self):
        self.__chat.send(("CAP REQ :twitch.tv/membership\r\n").encode('utf-8'))
    def __activateTags(self):
        self.__chat.send(("CAP REQ :twitch.tv/tags\r\n").encode('utf-8'))
    def join(self, channel):
        self.__chat.send(("JOIN %s\r\n" % channel).encode('utf-8'))
    def part(self, channel):
        self.__chat.send(("PART %s\r\n" % channel).encode('utf-8'))

    def __getText(self):
        return self.__chat.recv(2048).decode('utf-8')

    def __printText(self, irc, raw_text, msg_text):
        if self.__printopts & self.__PRINT_OPT_NONE != 0:
            return
 
        to_print = False
        
        if irc.IRCcmd == 'PRIVMSG':
            to_print = self.__printopts & self.__PRINT_OPT_MSG != 0
        else:
            if irc.IRCcmd in ['353', 'JOIN', 'PART', 'QUIT']:
                to_print = self.__printopts & self.__PRINT_OPT_JOIN != 0
            elif irc.IRCcmd == 'MODE':
                to_print = self.__printopts & self.__PRINT_OPT_MODE != 0
            elif irc.IRCcmd in ['ROOMSTATE', 'NOTICE']:
                to_print = self.__printopts & self.__PRINT_OPT_STATE != 0

            # Overrides any previous setup
            if self.__printopts & self.__PRINT_OPT_OTHER != 0:
                to_print = True

        if to_print:
            if self.__printopts & self.__PRINT_OPT_TAG != 0:
                try:
                    print(raw_text)
                except UnicodeDecodeError:
                    None
            else:
                try:
                    print(msg_text)
                except UnicodeDecodeError:
                    None

    # Formats and prepares an _IRCMessage instance to return.
    # Also updates the userlists if applicable.
    def incoming(self):
        text = self.__getText().strip()
 
        if text.find("PING") != -1:
            self.__chat.send(("PONG tmi.twitch.tv\r\n").encode('utf-8'))

        for line in text.split('\n'):
            tag_included = False
            
            if line.startswith('@'):
                tokens = line.partition(' ')
                msgtext = tokens[2]
                tag = tokens[0]
                tag_included = True
            else:
                msgtext = line
 
            message = _IRCMessage(msgtext)
            if message.IRCcmd == '353':
                self.__setUserList(message)
            elif message.IRCcmd == 'PART' or message.IRCcmd == 'QUIT':
                self.__removeUser(message.username)
            elif message.IRCcmd == 'JOIN':
                self.__appendUser(message.username)
            elif message.IRCcmd == 'MODE':
                self.__updateUser(message.IRCparams)

            if tag_included:
                message.tag = _IRCTag(tag)
            else:
                message.tag = _IRCTag('')

            if message.IRCcmd == 'NOTICE':
                self.__updateNotice(message.tag.msg_id)
            elif message.IRCcmd == 'ROOMSTATE':
                self.__updateRoomstate(message.tag)

            self.__printText(message, text, msgtext)

        # Only returns the last message for checking
        return message
    
    # Bot interaction commands.
    def msg(self, message):
        self.__chat.send(("PRIVMSG %s :%s\r\n" % (self.channel, message)).encode('utf-8'))
        if self.__printopts & self.__PRINT_OPT_SELF != 0:
            try:
                print("SELF: " + message)
            except UnicodeDecodeError:
                None
    def action(self, message):
        self.msg(".me %s" % message)
    def color(self, color):
        self.msg(".color %s" % color)
    def ignore(self, username):
        self.msg(".ignore %s" % username)
    def unignore(self, username):
        self.msg(".unignore %s" % username)
    def timeout(self, username, time):
        self.msg(".timeout %s %d" % (username, time))
    def purge(self, username):
        self.timeout(username, 1)
    def ban(self, username):
        self.msg(".ban %s" % username)
    def unban(self, username):
        self.msg(".unban %s" % username)
    def clear(self):
        self.msg(".clear")
    def slowon(self, time):
        self.msg(".slow %d" % time)
    def slowoff(self):
        self.msg(".slowoff")
    def subson(self):
        self.msg(".subscribers")
    def subsoff(self):
        self.msg(".subscribersoff")
    def r9kon(self):
        self.msg(".r9kbeta")
    def r9koff(self):
        self.msg(".r9kbetaoff")
    def emoteonlyon(self):
        self.msg(".emoteonly")
    def emoteonlyoff(self):
        self.msg(".emoteonlyoff")
    def quitirc(self, message):
        self.__chat.send(("QUIT :Quit %s\r\n" % message).encode('utf-8'))
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((self.server, 6667))
        self.__chat.shutdown(socket.SHUT_RDWR)
        self.__chat.close()

    # User variables
    def getUserVar(self, varname):
        if varname not in self.__variables:
            raise KeyError("Variable \"%s\" not found." % varname)
        return self.__variables[varname]['value']
    def setUserVar(self, varname, value):
        if varname not in self.__variables:
            raise KeyError("Variable \"%s\" not found." % varname)
        self.__variables[varname]['value'] = value
    def newUserVar(self, varname, value, vartype=None):
        if varname in self.__variables:
            raise KeyError("Variable \"%s\" already exists." % varname)
        if re.fullmatch('[a-z][\w_]+', varname) == None:
            raise ValueError(("Variable \"%s\" must start with a letter "
                              "and can contain only alphanumeric characters "
                              "and underscores." % varname))
        self.__variables[varname]['value'] = value
        self.__variables[varname]['type'] = vartype
    def delUserVar(self, varname):
        if varname not in self.__variables:
            raise KeyError("Variable \"%s\" not found." % varname)
        del self.__variables[varname]
    def getUserVarType(self, varname):
        if varname not in self.__variables:
            raise KeyError("Variable \"%s\" not found." % varname)
        return self.__variables[varname]['type']
    def setUserVarType(self, varname, vartype):
        if varname not in self.__variables:
            raise KeyError("Variable \"%s\" not found." % varname)
        self.__variables[varname]['type'] = vartype

    # Userlist commands
    def __appendUser(self, username):
        if len(username) < 1:
            return
        
        username = username.strip()
        
        if username[0] in ('%', '@', '&'):
            username = username[1:]
            if username not in self.modlist:
                self.modlist.append(username)

        if username not in self.userlist:
            self.userlist.append(username)

    def __removeUser(self, username):
        username = username.strip()
        
        if username in self.userlist:
            self.userlist.remove(username)
        if username in self.modlist:
            self.modlist.remove(username)

    def __updateUser(self, IRCparams):
        if len(IRCparams) < 3:
            return

        modeset = IRCparams[1]
        username    = IRCparams[2].strip()

        if modeset.startswith('+'):
            if 'o' in modeset or 'a' in modeset or 'h' in modeset:
                if username not in self.modlist:
                    self.modlist.append(username)
        elif modeset.startswith('-'):
            if 'o' in modeset or 'a' in modeset or 'h' in modeset:
                if username in self.modlist:
                    self.modlist.remove(username)

    def __setUserList(self, text):
        for username in text.body.split(' '):
            self.__appendUser(username)

    def __updateRoomstate(self, tag):
        for state in tag.tags:
            if state == 'broadcaster-lang':
                self.broadcaster_lang = tag.broadcaster_lang
            elif state == 'r9k':
                self.r9k_on = tag.r9k
            elif state == 'subs-only':
                self.subs_on = tag.subs_only
            elif state == 'slow':
                self.slow_on = tag.slow > 0

    def __updateNotice(self, msg_id):
        if msg_id == 'subs_on': self.subs_on = True
        elif msg_id == 'slow_on': self.slow_on = True
        elif msg_id == 'r9k_on': self.r9k_on = True
        elif msg_id == 'host_on': self.host_on = True
        elif msg_id == 'emote_only_on': self.emote_only_on = True
        elif msg_id == 'msg_channel_suspended': self.msg_channel_suspended = True

        elif msg_id == 'subs_off': self.subs_on = False
        elif msg_id == 'slow_off': self.slow_on = False
        elif msg_id == 'r9k_off': self.r9k_on = False
        elif msg_id == 'host_off': self.host_on = False
        elif msg_id == 'emote_only_off': self.emote_only_on = False
