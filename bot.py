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

logging.basicConfig(filename='bot.log',level=logging.DEBUG)

config = ConfigParser()
config.read("bot.config")

username_prompt = "By what name are you known (or \"new\" to create a new character): "
password_prompt = "Password: "
splash1_re = re.compile("\[Press Enter\]")
splash2_re = re.compile("Press \[ENTER\]")
main_prompt = "> "
main_prompt_re = re.compile("<\d+[^>]+>")
exit_re = re.compile("Exits: (.*)")
location_re = re.compile("([^\n\r]+)\n\r(.+?)\n\rExits: ([^\n\r]*)\n?\r?(.*)", re.DOTALL)

class Bot(object):
    
    def __init__(self, config):
        
        self.config = config
        
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
        self.action_stack = ["username"]
        self.last_action = None
        self.response_q = Queue()
        self.parse_responses = False
        try:
            self.action_loop()
        except:
            logging.debug("Caught exception: %s" % str(sys.exc_info()))
            self.tn.write("quit\n")
            sys.exit()
    
    def action_loop(self):
        while True:
            self.update_output()
            self.process_responses()
            try:
                item = self.action_stack.pop()
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

    def do(self, action, *args):
        if len(args) > 0:
            item = tuple([action] + list(args))
            self.action_stack.append(item)
        else:
            self.action_stack.append(action)
        
    def do_next(self, *args):
        for arg in reversed(args):
            self.action_stack.append(arg)

    def on_no_action(self):
        action_type = [
            "move",
            "spell",
            "action"
        ]
        type_choice = random.choice(action_type)
        if type_choice == "move":
            possible = [
                "look"
            ]
            action = random.choice(possible)
        elif type_choice == "action":
            possible = {
                "drink": 25,
                "eat": 25,
                "sleep": 25,
                "dig": 10,
                "search": 10,
                "climb": 5
            }            
            action = weighted_choice(possible)
        elif type_choice == "spell":
            possible = {
                act("cast", "create water", "waterskin"): 10,
                act("cast", "create food"): 20,
                act("cast", "armor"): 5,
                act("cast", "bless"): 5,
                act("cast", "cure light"): 5,
                act("cast", "cure serious"): 5,
                act("cast", "cure critical"): 5,
                act("cast", "cure poison"): 5,
                act("cast", "detect invis"): 5,
                act("cast", "detect evil"): 5,
                act("cast", "detect magic"): 5,
                act("cast", "refresh"): 5,
                act("cast", "protection"): 5,
                act("cast", "detect hidden"): 5,
                act("cast", "float"): 5,
                act("cast", "summon", "dog"): 5
            }
            action = weighted_choice(possible)
        self.do_next("dwell", action)

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

    def handle_look(self):
        self.command("look")
        self.do("parse_look")
        
    def handle_create_water(self):
        self.command("cast \"create water\" waterskin")
        
    def handle_drink(self):
        self.command("drink waterskin")
        
    def handle_create_food(self):
        self.command("cast \"create food\"")
        
    def handle_eat(self):
        self.command("eat mushroom")
        
    def handle_parse_look(self):
        if self.place:
            self.do("random_exit")
        else:
            self.do("parse_look")

    def handle_random_exit(self):
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
            self.do(act("dwell_wait", to_dwell))
            time.sleep(1)
    
    def handle_sleep(self):
        self.command("sleep")
        self.do("wake")
        self.do("dwell_wait", self.config.getint("timing", "sleep_wait"))
        
    def handle_wake(self):
        self.command("wake")
    
    def handle_cast(self, spell, target=None):
        if target:
            self.command("cast \"%s\" \"%s\"" % (spell, target))
        else:
            self.command("cast \"%s\"" % spell)

    def handle_dig(self):
        self.command("dig")
    
    def handle_search(self):
        self.command("search")
    
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
            output_q.put(tn.read_some())
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

if __name__ == '__main__':
    config = ConfigParser()
    config.read("bot.config")
    bot = Bot(config)
