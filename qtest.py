from rq import Queue
from worker import conn

q = Queue(connection=conn)
result = q.enqueue(count_words_at_url, 'http://heroku.com')