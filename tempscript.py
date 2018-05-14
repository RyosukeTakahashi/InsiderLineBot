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