import time
import asyncio
from linebot.models import TextSendMessage, ButtonsTemplate, TemplateSendMessage, PostbackTemplateAction
from constants import line_bot_api, r
import json


async def timer(delay):
    while True:
        now = time.time()
        set_list = r.zrange("timer", 0, -1, withscores=True)
        for i, value_score in enumerate(set_list):
            end_timestamp = value_score[1]
            value_dict = json.loads(value_score[0].decode())
            room_id = value_dict["room_id"]
            members = value_dict["members"]
            time_left = value_dict["time_left"]
            print(f'{room_id} {time_left}sec')
            diff = end_timestamp - now
            print(f'i:{i}, set_list_len:{len(r.zrange("timer", 0, -1, withscores=True))}')
            with open('rooms.json', 'r') as room_json:
                rooms_dict = json.load(room_json)
                answered = rooms_dict[room_id]["rounds_info"][-1]["answered"]

            if answered is True:
                print("removing since it was answered")
                r.zrem("timer", value_score[0])

            if diff <= 0 and answered is False:
                # message_id, sender_id, text = name.decode().split(':')
                line_bot_api.multicast(
                    members,
                    TextSendMessage(text=f'残り{time_left}秒です。')
                )
                r.zrem("timer", value_score[0])
                print("removed one")
                print(len(r.zrange("timer", 0, -1, withscores=True)))

                if len(r.zrange("timer", 0, -1, withscores=True)) == 0:
                    line_bot_api.multicast(
                        members,
                        [TextSendMessage(text=f'お題あての時間が切れました。'),
                         TextSendMessage(text='マスターは答えを言ってください。'),
                         get_confirm_button_moving_to_insider_guess(room_id)]
                    )
            else:
                print("breaking from 'for'")
                break
        await asyncio.sleep(delay) # indent position is important


def get_confirm_button_moving_to_insider_guess(room_id):

    confirm_template_message = TemplateSendMessage(
        alt_text='Confirm template',
        template=ButtonsTemplate(
            title='確認',
            text='インサイダーの予想に移ります。',
            actions=[
                PostbackTemplateAction(
                    label='確認',
                    text='確認',
                    data=f'room_id={room_id}&next=word_guess_time_up'
                )
            ]
        )
    )
    return confirm_template_message


if __name__ == '__main__':

    r.flushall()
    print("redis flushed")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(timer(2))
        print("one loop ended")
    finally:
        loop.close()
