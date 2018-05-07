import requests
import redis
from linebot.models import TextSendMessage
from linebot import (LineBotApi, WebhookParser)


# 登録するJob(function)をここに書いていく
r = redis.from_url("redis://localhost:6379")
CHANNEL_ACCESS_TOKEN = '6IqIN2H9tUAvD4QFUzwlm6DGfV+TMQ3aavxSrkY0JMo/XxlNXVcf5CRFvnI9CDVUdqYGx70RyzJtWYspCZJBej2SQsxL7BjWWsZPtVdr7B9Fm992S8Pr75ElIdXAaz4OFVnQLKvkacIHMtrWVI6E3wdB04t89/1O/w1cDnyilFU='
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)


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



