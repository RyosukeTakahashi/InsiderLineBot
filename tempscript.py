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
import redis


r = redis.from_url("redis://localhost:6379")

r.flushall()

r.sadd('this key', 'hello you all'+str(time.time()))
name = r.smembers('this key')
print(name)

# r.zadd('my-key', 1.1, 'name1', 2.2, 'name2', name3=3.3, name4=4.4)
# r.zadd('timer', "hello2" + str(time.time()), time.time())
print(r.zrange('timer', 0, -1, withscores=True))
#
