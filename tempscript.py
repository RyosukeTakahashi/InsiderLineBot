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
import json

room_json = open('room.json', 'r')


json.load()
json.dump()



