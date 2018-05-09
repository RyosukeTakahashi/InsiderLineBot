from linebot.models import TextSendMessage
from constants import line_bot_api, r
import json

# 登録するJob(function)をここに書いていく


def set_reminders(timestamp, timings, members, room_id):

    value_dict = {
        "time_left": 0,
        "members": members,
        "room_id": room_id
    }

    for timing in timings:
        end_timestamp = timing + timestamp
        value_dict["time_left"] = 183-timing
        value_json = json.dumps(value_dict)

        r.zadd('timer', value_json, end_timestamp)
        print("set added to redis")

    print(r.zrange('timer', 0, -1, withscores=True))
    line_bot_api.multicast(
        members,
        TextSendMessage(text=f"それでは制限時間内にお題を予測してください。正解が出たらマスターは「正解が出ました」ボタンを押してください。 ")
    )
