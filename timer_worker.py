import time
import asyncio
from linebot.models import TextSendMessage
from constants import line_bot_api, r
import json


async def timer(delay):
    while True:
        now = time.time()
        for name, end_timestamp in r.zrange("timer", 0, -1, withscores=True):
            diff = end_timestamp - now
            print(name)
            with open('rooms.json', 'r') as room_json:
                rooms_dict = json.load(room_json)
                answered = rooms_dict["1"]["rounds_info"][-1]["answered"]

            if answered is True:
                print("removing since it was answered")
                r.zrem("timer", name)

            if diff <= 0 and answered is False:
                # message_id, sender_id, text = name.decode().split(':')
                line_bot_api.push_message(
                    "U0a028f903127e2178bd789b4b4046ba7",
                    TextSendMessage(text=f'残りは{name.decode()}秒です。\n now {int(now)}')
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
        loop.run_until_complete(timer(2))
    finally:
        print("closing loop")
        loop.close()
