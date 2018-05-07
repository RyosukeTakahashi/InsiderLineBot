from rq import Queue
from worker import conn
import utils_line_jobs
import time

q = Queue(connection=conn)
result = q.enqueue(utils_line_jobs.set_timer, int(time.time()))

