# 最初にインサイダーとマスターを決めるかいなか。
# room['insider_order'] = [random.choice(members) for i in range(rounds)]
# print((room['insider_order']))
# room['master_order'] = [random.choice(get_list_without_insider(members, room['insider_order'][i])) for i in range(rounds)]
# rooms_dict[room_id] = room
# json.dump(rooms_dict, open('rooms.json', 'w'), indent=2)
# insider = room['insider_order'][0]
# master = room['master_order'][0]
# members.remove(insider)

import sched
import time


s = sched.scheduler(time.time, time.sleep)
def print_time(a='default'):
    print("From print_time", time.time(), a)

def print_some_times():
    print(time.time())
    s.enter(10, 1, print_time)
    s.enter(5, 2, print_time, argument=('positional',))
    s.enter(5, 1, print_time, kwargs={'a': 'keyword'})
    s.run()
    print(time.time())

print_some_times()