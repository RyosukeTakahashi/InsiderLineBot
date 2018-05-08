import os
import redis
from rq import Worker, Queue, Connection
import json

listen = ['high', 'default', 'low']

# redis_url = os.getenv('REDISTOGO_URL', 'redis://localhost:6379')
# conn = redis.from_url(redis_url)


if 'VCAP_SERVICES' in os.environ:
    vcap = json.loads(os.getenv('VCAP_SERVICES'))
    print('Found VCAP_SERVICES')
    if 'rediscloud' in vcap:
        creds = vcap['rediscloud'][0]['credentials']


elif os.path.isfile('vcap-services.json'):
    with open('vcap-services.json') as f:
        vcap = json.load(f)
        print('Found local VCAP_SERVICES')
        creds = vcap['rediscloud'][0]['credentials']

# else:
#     r = redis.from_url("redis://localhost:6379")

r = redis.Redis(
    host=creds['hostname'],
    password=creds['password'],
    port=creds['port']
)


if __name__ == '__main__':
    with Connection(r):
        worker = Worker(map(Queue, listen))
        worker.work()

