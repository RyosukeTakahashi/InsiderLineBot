from rq import Worker, Queue, Connection
from constants import r

listen = ['high', 'default', 'low']

if __name__ == '__main__':
    with Connection(r):
        worker = Worker(map(Queue, listen))
        worker.work()
