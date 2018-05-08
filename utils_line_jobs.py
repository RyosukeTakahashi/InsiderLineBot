import requests
import redis
from linebot.models import TextSendMessage
from linebot import (LineBotApi)
import os
import json


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


CHANNEL_ACCESS_TOKEN = '6IqIN2H9tUAvD4QFUzwlm6DGfV+TMQ3aavxSrkY0JMo/XxlNXVcf5CRFvnI9CDVUdqYGx70RyzJtWYspCZJBej2SQsxL7BjWWsZPtVdr7B9Fm992S8Pr75ElIdXAaz4OFVnQLKvkacIHMtrWVI6E3wdB04t89/1O/w1cDnyilFU='
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
# 登録するJob(function)をここに書いていく


def count_words_at_url(url):
    resp = requests.get(url)
    return len(resp.text.split())


def set_timer(timestamp):
    end_timestamp = timestamp + 5
    r.zadd('timer', "hello"+str(timestamp), end_timestamp)
    print("added to redis")
    print(r.zrange('timer', 0, -1, withscores=True))
    line_bot_api.push_message(
        "U0a028f903127e2178bd789b4b4046ba7",
        TextSendMessage(text="time started")
    )



