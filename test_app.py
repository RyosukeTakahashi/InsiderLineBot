import unittest
# import app
import json
import random
import sched
import time
import os
from apscheduler.schedulers.background import BackgroundScheduler

import app


class TestLineBot(unittest.TestCase):

    def test_insider_guess_reminder(self):
        scheduler = BackgroundScheduler()
        scheduler.start()

        app.insider_guess_reminder(27, scheduler)
        print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

        try:
            # This is here to simulate application activity (which keeps the main thread alive).
            while True:
                time.sleep(2)
        except (KeyboardInterrupt, SystemExit):
            # Not strictly necessary if daemonic mode is enabled but should be done if possible
            scheduler.shutdown()


    def test_get_room_count(self):
        rooms_json = json.load(open('rooms.json'))
        print(f'room count is {len(rooms_json.keys())}')

    def test_sched(self):
        scheduler = sched.scheduler(time.time, time.sleep)
        scheduler.enter(2, 1, print, ('2sec',))
        scheduler.enter(4, 1, print, ('2sec',))

    def test_check_multi_first_place(self):
        import collections
        s = 'government of the people, by the people, for the people.'

        s_remove = s.replace(',', '').replace('.', '')

        word_list = s_remove.split()

        c = collections.Counter(word_list)

        biggest_vote_count = c.most_common()[0][1]
        dict = {}

        for word, count in c.most_common():
            if count in dict.keys():
                dict[count].append(word)
            else:
                dict[count] = [word]
        print(len(dict[biggest_vote_count]))

    def test_init_json(self):

        rooms_dict = {"1":{}}
        with open('words.txt', 'r') as f:
            whole_words_list = f.readlines()
        picked_words = [word.replace('\n', "") for word in random.sample(whole_words_list, 5)]
        rooms_dict["1"] = \
            {
                "members": {
                    "user1": {
                        "score": 0,
                        "display_name": "fdsadfsa"
                    },
                    "user2": {
                        "score": 0,
                        "display_name": "fdsadfsa"
                    }
                },
                "total_rounds": 5,
                "rounds_info": [],
                "words": picked_words
            }

        print(rooms_dict)
        print(list(rooms_dict["1"]["members"].keys()))
        with open('rooms.json', 'w') as room_json:
            json.dump(rooms_dict, room_json, indent=2)
