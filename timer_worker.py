import time
import asyncio
import redis
from linebot.models import TextSendMessage
from linebot import (LineBotApi, WebhookParser)

r = redis.from_url("redis://localhost:6379")
CHANNEL_ACCESS_TOKEN = '6IqIN2H9tUAvD4QFUzwlm6DGfV+TMQ3aavxSrkY0JMo/XxlNXVcf5CRFvnI9CDVUdqYGx70RyzJtWYspCZJBej2SQsxL7BjWWsZPtVdr7B9Fm992S8Pr75ElIdXAaz4OFVnQLKvkacIHMtrWVI6E3wdB04t89/1O/w1cDnyilFU='
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)


async def timer(delay):
    while True:
        now = time.time()
        for name, end_timestamp in r.zrange("timer", 0, -1, withscores=True):
            diff = end_timestamp - now
            if diff <= 0:
                # message_id, sender_id, text = name.decode().split(':')
                line_bot_api.push_message(
                    "U0a028f903127e2178bd789b4b4046ba7",
                    TextSendMessage(text=f'timer ended {name}\n now {now}')
                )
                r.zrem("timer", name)
            else:
                break
        await asyncio.sleep(delay)


if __name__ == '__main__':

    r.flushall()
    print("redis flushed")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(timer(1))
    finally:
        loop.close()