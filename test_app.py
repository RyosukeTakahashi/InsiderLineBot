import unittest
import app
import json


class TestLineBot(unittest.TestCase):

    def test_get_room_count(self):
        rooms_json = json.load(open('rooms.json'))
        print(f'room count is {len(rooms_json.keys())}')
