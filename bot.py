from ConfigParser import ConfigParser
import logging
from Queue import Queue, Empty
import random
import re
import sys
import time

from BaseBot import BaseBot, act, weighted_choice

logging.basicConfig(filename='bot.log',level=logging.DEBUG)

class ClericBot(BaseBot):
    
    def __init__(self, config):
        super(ClericBot, self).__init__(config)

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
                "sleep": 25,
                "dig": 25,
                "search": 25,
                "climb": 25
            }            
            action = weighted_choice(possible)
        elif type_choice == "spell":
            possible = {
                act("cast", "create water", "dragonskin"): 10,
                act("cast", "create food"): 0,
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

    def on_response(self, response):
        if (re.search('You are a mite peckish', response) or
                re.search('You are hungry', response) or
                re.search('You are famished', response) or
                re.search('You are STARVING', response)):
            self.do_next(act("cast", "create food"), act("eat"))
        if (re.search('You are thirsty', response) or
                re.search('You are parched', response) or
                re.search('You are DYING of THIRST', response)):
            self.do_next(
                act("cast", "create water", "dragonskin"),
                act("drink"))
        
    def handle_create_water(self):
        self.command("cast \"create water\" dragonskin")
        
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
    
if __name__ == '__main__':
    try:
        config_file = sys.argv[1]
    except IndexError:
        config_file = "bot.config"
    config = ConfigParser()
    config.read(config_file)
    bot = ClericBot(config)
