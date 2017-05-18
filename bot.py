from ConfigParser import ConfigParser
import logging
from Queue import Queue, Empty
import random
import re
import sys
import time

from BaseBot import BaseBot, act, weighted_choice

class ClericBot(BaseBot):
    
    def __init__(self, config):
        super(ClericBot, self).__init__(config)

    def on_no_action(self):
        if self.following:
            self.do(act("look", self.target))
        action_type = [
            "spell",
            "action" 
        ]
        if self.follow == None:
            action_type.append("move")
        type_choice = random.choice(action_type)
        if type_choice == "move":
            possible = [
                "look"
            ]
            action = random.choice(possible)
        elif type_choice == "action":
            possible = {
                "sleep": 25,
                "dig": 25,
                "search": 25,
                "climb": 25
            }            
            action = weighted_choice(possible)
        elif type_choice == "spell":
            possible = {
                act("cast", "create spring"): 5,
                act("cast", "armor"): 5,
                act("cast", "bless"): 5,
                act("cast", "cure light"): 5,
                act("cast", "cure serious"): 5,
                act("cast", "cure critical"): 5,
                act("cast", "cure poison"): 5,
                act("cast", "remove hex", "self"): 5,
                act("cast", "remove curse", "self"): 5,
                act("cast", "detect invis"): 5,
                act("cast", "detect evil"): 5,
                act("cast", "detect magic"): 5,
                act("cast", "detect poison", "dragonskin"): 5,
                act("cast", "know alignment", "self"): 5,
                act("cast", "refresh"): 5,
                act("cast", "protection"): 5,
                act("cast", "detect hidden"): 5,
                act("cast", "float"): 5,
                act("cast", "fly"): 5,
                act("cast", "summon", "dog"): 5,
                act("cast", "identify", "dragonskin"): 5,
                act("cast", "minor invocation"): 5,
                act("cast", "locate object", "club"): 5,
                act("create_symbol"): 5
            }
            action = weighted_choice(possible)
        self.do_now("dwell", action)

    def on_response(self, response):
        if (re.search('You are a mite peckish', response) or
                re.search('You are hungry', response) or
                re.search('You are famished', response) or
                re.search('You are STARVING', response)):
            self.do_now(act("cast", "create food"), act("eat"))
        if (re.search('You are thirsty', response) or
                re.search('You are parched', response) or
                re.search('You are DYING of THIRST', response)):
            self.do_now(
                act("cast", "create water", "dragonskin"),
                act("drink"))
        if re.search('You do not see that here', response):
            self.follow = None
        
    def on_tell(self, name, tell):
        if re.match("follow", tell):
            self.follow = name
            self.command("tell %s Let's go! Tell me 'unfollow' to dismiss me." % name)
            self.command('follow %s' % name)
        elif re.match("unfollow", tell) and name == self.follow:
            self.follow = None
            self.command("tell %s Until next time, %s!" % (name, name))
            self.command("follow self")
        else:
            self.command("tell %s Back at ya, cutie!" % name)

    def handle_create_water(self):
        self.command("cast \"create water\" dragonskin")
        
    def handle_create_symbol(self):
        self.command("cast \"create symbol\"")
        self.command("drop symbol")
        
    def handle_drink(self):
        self.command("drink dragonskin")
        
    def handle_create_food(self):
        self.command("cast \"create food\"")
        
    def handle_eat(self):
        self.command("eat mushroom")
        
    def handle_parse_look(self):
        try:
            if self.place:
                self.do("random_exit")
            else:
                self.do("parse_look")
        except AttributeError:
            self.do("parse_look")

    def handle_dig(self):
        self.command("dig")
    
    def handle_search(self):
        self.command("search")
    
    def handle_climb(self):
        self.command("climb")
    
    def handle_look(self, target):
        self.command("look %s" % target)
        self.look_target = target
    
if __name__ == '__main__':
    try:
        config_file = sys.argv[1]
    except IndexError:
        config_file = "bot.config"
    config = ConfigParser()
    config.read(config_file)
    log_file = config.get("logging", "log_file")
    logging.basicConfig(filename=log_file,level=logging.DEBUG)
    bot = ClericBot(config)
