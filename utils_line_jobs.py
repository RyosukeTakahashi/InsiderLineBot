from linebot.models import TextSendMessage
from constants import line_bot_api, r

# 登録するJob(function)をここに書いていく


def set_reminders(timestamp, timings, members):

    for timing in timings:
        end_timestamp = timing + timestamp
        r.zadd('timer', f'{180-timing}', end_timestamp)
        print("set added to redis")

    print(r.zrange('timer', 0, -1, withscores=True))
    timings_str = [str(timing) for timing in timings]
    line_bot_api.multicast(
        members,
        TextSendMessage(text=f"timer has been set. It will reminder you in{','.join(timings_str)}s")
    )

