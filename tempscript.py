# 最初にインサイダーとマスターを決めるかいなか。
# room['insider_order'] = [random.choice(members) for i in range(rounds)]
# print((room['insider_order']))
# room['master_order'] = [random.choice(get_list_without_insider(members, room['insider_order'][i])) for i in range(rounds)]
# rooms_dict[room_id] = room
# json.dump(rooms_dict, open('rooms.json', 'w'), indent=2)
# insider = room['insider_order'][0]
# master = room['master_order'][0]
# members.remove(insider)

# import sched
# import time
# import json
# import redis
# import random
# from pytz import utc
#
# from apscheduler.schedulers.background import BackgroundScheduler
# from apscheduler.schedulers.background import BlockingScheduler
# import time
# # sched = BackgroundScheduler()
# sched = BlockingScheduler()
#
#
# def timed_job():
#     with open('test.txt', 'w') as f:
#         f.write(f'{time.time()}')
#
#     print('this job is run every 1 sec')
#
#
# sched.add_job(timed_job, 'interval', seconds=1)
# sched.start()


from datetime import datetime
import time
import os

from apscheduler.schedulers.background import BackgroundScheduler


def tick(scheduler_starttime):
    diff = time.time() - scheduler_starttime
    if diff > 3:
        job_id = scheduler.get_jobs()[0]
        print(job_id)
        scheduler.remove_job('timer')
    print(diff)


if __name__ == '__main__':
    scheduler = BackgroundScheduler()
    scheduler_starttime = time.time()
    scheduler.add_job(lambda: tick(scheduler_starttime), 'interval', seconds=1, id='timer')
    scheduler.start()
    print('Press Ctrl+{0} to exit'.format('Break' if os.name == 'nt' else 'C'))

    try:
        # This is here to simulate application activity (which keeps the main thread alive).
        while True:
            time.sleep(2)
    except (KeyboardInterrupt, SystemExit):
        # Not strictly necessary if daemonic mode is enabled but should be done if possible
        scheduler.shutdown()