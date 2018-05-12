from linebot.models import TextSendMessage
from constants import line_bot_api, r
import json

# 登録するJob(function)をここに書いていく


def set_reminders(start_timestamp, timings, members, room_id, master, guessing_time, guessed_object):

    value_dict = {
        "time_left": 0,
        "members": members,
        "room_id": room_id,
        "master": master,
        "guessed_object": guessed_object

    }
    print(timings)
    print(type(timings))
    # reminder_timings_setting = timings = [3, 93, 153, 183]
    for timing in timings:
        end_timestamp = timing + start_timestamp
        value_dict["time_left"] = guessing_time-timing
        value_json = json.dumps(value_dict)

        r.zadd('timer', value_json, end_timestamp)
        print("set added to redis")

    print(r.zrange('timer', 0, -1, withscores=True))


#