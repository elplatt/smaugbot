from ConfigParser import ConfigParser
import logging
from Queue import Queue, Empty
import random
import re
import select
import sys
from telnetlib import Telnet
from threading import Thread
import thread
import time
import traceback

username_prompt = "By what name are you known (or \"new\" to create a new character): "
password_prompt = "Password: "
splash1_re = re.compile("\[Press Enter\]")
splash2_re = re.compile("Press \[ENTER\]")
main_prompt = "> "
main_prompt_re = re.compile("<(\d+)/(\d+)hp (\d+)/(\d+)m (\d+)/(\d+)mv ([0-9,]+)to level>")
exit_re = re.compile("Exits: (.*)")
location_re = re.compile("([^\n\r]+)\n\r(.+?)\n\rExits: ([^\n\r]*)\n?\r?(.*)", re.DOTALL)

class BaseBot(object):
    
    def __init__(self, config):
        
        self.config = config
        self.place = None
        self.flavor = None
        self.exits = None
        self.objects = None
        self.follow = None
        self.sleep = False
        
        # Begin process to read keyboard input
        logging.debug("Starting keyboard_daemon")
        self.input_q = Queue()
        self.keyboard_d = Thread(target=keyboard_daemon, args=(self.input_q,))
        self.keyboard_d.daemon = True
        self.keyboard_d.start()
        
        # Connect to server
        host = self.config.get("host", "host")
        port = self.config.getint("host", "port")
        logging.debug("Connecting to %s:%d" % (host, port))
        try:
            self.tn = Telnet(host, port)
            self.recent = ""
        except EOFError:
            logging.debug("Remote host disconnected")
            sys.exit()
        except:
            logging.debug("  Caught exception: " + str(sys.exc_info()))
            sys.exit()
    
        # Begin process to read and display server output
        logging.debug("Starting output_daemon")
        self.output_q = Queue()
        self.output_d = Thread(target=output_daemon, args=(self.tn, self.output_q))
        self.output_d.daemon = True
        self.output_d.start()
        
        # Begin process to write input to server
        logging.debug("Starting input_daemon")
        self.input_d = Thread(target=input_daemon, args=(self.tn, self.input_q))
        self.input_d.daemon = True
        self.input_d.start()
        
        logging.debug("Starting action_loop()")
        self.action_deque = ["username"]
        self.last_action = None
        self.response_q = Queue()
        self.parse_responses = False
        try:
            self.action_loop()
        except KeyboardInterrupt:
            # Probably caugt an exception in a worker thread
            # Usually happens when connection is closed by manual quit
            logging.debug("Caught exception: %s" % traceback.format_exc())
            try:
                while True:
                    sys.stdout.write(self.output_q.get(False))
            except Empty:
                pass
            sys.exit()
        except:
            logging.debug("Caught exception: %s" % traceback.format_exc())
            self.tn.write("quit\n")
            sys.exit()
    
    def action_loop(self):
        while True:
            self.update_output()
            self.process_responses()
            try:
                item = self.action_deque.pop()
                if not isinstance(item, basestring):
                    action = item[0]
                    args = item[1:]
                else:
                    action = item
                    args = []
                if action != self.last_action:
                    logging.debug("New action: %s" % action)
                    self.last_action = action
                handler = getattr(self, "handle_%s" % action)
                handler(*args)
            except IndexError:
                logging.debug("  No action to handle")
                self.on_no_action()
            time.sleep(0)

    def on_no_action(self):
        self.do_now("dwell", "random_exit")


    def on_tell(self, name, tell):
        self.command("tell %s Back at ya, cutie!" % name)

    def handle_username(self):
        if self.recent.endswith(username_prompt):
            self.do("password")
            self.clear_output()
            self.command(self.config.get("account", "username"))
        else:
            self.do("username")
    
    def handle_password(self):
        if self.recent.endswith(password_prompt):
            self.do("splash1")
            self.clear_output()
            self.silent_command(self.config.get("account", "password"))
        else:
            self.do("password")
    
    def handle_splash1(self):
        if re.search(splash1_re, self.recent):
            self.do("splash2")
            self.clear_output()
            self.command("")
        else:
            self.do("splash1")

    def handle_splash2(self):
        if re.search(splash2_re, self.recent):
            self.clear_output()
            self.command("")
            self.parse_responses = True
        else:
            self.do("splash2")

    def handle_look(self, target=None):
        if target:
            self.command("look %s" % target)
            self.look_target = target
        else:
            self.command('look')
    
    def handle_random_exit(self):
        if not self.place:
            self.do("look", "random_exit")
            return
        if self.exits[0] == "none":
            logger.debug("No exits")
        else:
            exit_choice = random.choice(self.exits)
            if exit_choice[0] == "[":
                exit_choice = exit_choice[1:-1]
                self.command("open %s" % exit_choice)
            self.place = None
            self.flavor = None
            self.exits = None
            self.objects = None
            self.command(exit_choice)
        
    def handle_dwell(self, t=None):
        self.dwell_start = time.time()
        if t:
            self.do(act("dwell_wait", t))
        else:
            self.do("dwell_wait")
        
    def handle_dwell_wait(self, t=None):
        now = time.time()
        if t:
            to_dwell = t
        else:
            to_dwell = self.config.getint("timing", "dwell")
        if now - self.dwell_start <= to_dwell:
            self.do_now(act("dwell_wait", to_dwell))
            time.sleep(1)
    
    def handle_sleep(self):
        self.sleep = True
        self.command("sleep")
        self.do(
            act("dwell_wait", self.config.getint("timing", "sleep_wait")),
            act("wake"))
        
    def handle_wake(self):
        self.sleep = False
        self.command("wake")
    
    def handle_cast(self, spell, target=None):
        if target:
            self.command("cast \"%s\" \"%s\"" % (spell, target))
        else:
            self.command("cast \"%s\"" % spell)

    def do(self, *args):
        '''Add actions to action queue.'''
        for arg in args:
            self.action_deque.insert(0, arg)
        
    def do_now(self, *args):
        '''Add actions to front of action queue.'''
        for arg in reversed(args):
            self.action_deque.append(arg)

    def update_output(self):
        try:
            while True:
                chunk = self.output_q.get(False)
                self.recent += chunk
                sys.stdout.write(chunk)
                sys.stdout.flush()
                if self.parse_responses:
                    next_start = 0
                    matches = re.finditer(main_prompt_re, self.recent)
                    if matches:
                        for m in matches:
                            g = m.groups()
                            self.hp = int(g[0])
                            self.hp_total = int(g[1])
                            self.mana = int(g[2])
                            self.mana_total = int(g[3])
                            self.move = int(g[4])
                            self.move_total = int(g[5])
                            self.to_level = int(g[6].replace(",", ""))
                            logging.debug("hp: %d/%d" % (self.hp, self.hp_total))
                            logging.debug("mana: %d/%d" % (self.mana, self.mana_total))
                            logging.debug("move: %d/%d" % (self.move, self.move_total))
                            logging.debug("to level: %d" % (self.to_level))
                            response = self.recent[next_start:m.start()]
                            self.response_q.put(response.strip())
                            next_start = m.end()
                        self.recent = self.recent[next_start:]
        except Empty:
            pass
        
    def clear_output(self):
        s = self.recent
        self.recent = ""
        return s
        
    def process_responses(self):
        try:
            while True:
                response = self.response_q.get(False)
                logging.debug(response)
                m = re.search(location_re, response)
                if m:
                    place, flavor, exits, objects = m.groups()
                    self.place = place
                    self.flavor = flavor
                    self.exits = exits.strip().split(" ")
                    self.objects = objects.strip().split("\n\r")
                    logging.debug(self.place)
                    logging.debug(self.exits)
                    logging.debug(self.objects)
                m = re.search("(\w+) tells you \'(.+)\'", response)
                if m:
                    name, tell = m.groups()
                    if tell != "Back at ya, cutie!":
                        self.on_tell(name, tell)
                self.on_response(response)
        except Empty:
            pass
    
    def command(self, c):
        logging.debug("command: %s" % c)
        self.input_q.put(c + "\n")
        sys.stdout.write(c + "\n")
        time.sleep(self.config.getint("timing", "command_wait"))

    def silent_command(self, c):
        self.input_q.put(c + "\n")

def act(action, *args):
    return tuple([action] + list(args))

def act_args(a):
    if not isinstance(a, basestring):
        action = a[0]
        args = a[1:]
    else:
        action = a
        args = []
    return action, args

def keyboard_daemon(keyboard_q):
    try:
        while True:
            select.select([sys.stdin], [], [])
            line = sys.stdin.readline()
            keyboard_q.put(line)
    except KeyboardInterrupt:
        thread.interrupt_main()
        
def output_daemon(tn, output_q):
    try:
        while True:
            chunk = tn.read_some()
            if chunk == '':
                thread.interrupt_main()
                return
            output_q.put(chunk)
    except KeyboardInterrupt:
        thread.interrupt_main()
    except EOFError:
        thread.interrupt_main()

def input_daemon(tn, input_q):
    try:
        while True:
            data = input_q.get()
            tn.write(data)
    except KeyboardInterrupt:
        thread.interrupt_main()

def weighted_choice(choices):
    total = float(sum(choices.values()))
    x = random.random()
    sofar = 0.0
    for choice, p in choices.iteritems():
        sofar += float(p) / total
        if sofar >= x:
            return choice
    return choice
