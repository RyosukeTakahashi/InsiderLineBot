import unittest
# import app
import json
import random
import sched
import time


class TestLineBot(unittest.TestCase):

    def test_get_room_count(self):
        rooms_json = json.load(open('rooms.json'))
        print(f'room count is {len(rooms_json.keys())}')


    def test_sched(self):
        scheduler = sched.scheduler(time.time, time.sleep)
        scheduler.enter(2, 1, print, ('2sec',))
        scheduler.enter(4, 1, print, ('2sec',))





