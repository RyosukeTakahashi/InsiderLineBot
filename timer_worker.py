import time
import asyncio
from linebot.models import TextSendMessage, ButtonsTemplate, TemplateSendMessage, PostbackTemplateAction, CarouselColumn, CarouselTemplate
from constants import line_bot_api, r
import json
import copy


# 1 4sec
# i:0, set_list_len:4
# answered: True
# guessed_object: insider
# diff:-2.2144792079925537
# 1526104006.0
# removed one
# zrangelength :3
#
#
# 1 177sec
# i:1, set_list_len:3
# answered: True
# guessed_object: word
# diff:-0.2144792079925537
# removing since it was answered
# breaking from 'for'
#
#
# 1 0sec
# i:0, set_list_len:2
# answered: True
# guessed_object: insider
# diff:-0.5179698467254639
# 1526104010.0
# removed one
# zrangelength :1
#
#
# 1 174sec
# i:1, set_list_len:1
# answered: True
# guessed_object: word
# diff:0.48203015327453613
# removing since it was answered
# breaking from 'for'

#なるほど、word予想のところに入ってしまい、zrangeがなくなってしまってそれでなくなっている。



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
            print("type of time left")
            print(type(time_left))
            master = value_dict["master"]
            guessed_object = value_dict["guessed_object"]
            diff = end_timestamp - now
            with open('rooms.json', 'r') as room_json:
                rooms_dict = json.load(room_json)
                answered = rooms_dict[room_id]["rounds_info"][-1]["answered"]

            print(f'\nroom_id{room_id} time_left:{time_left}')
            print(f'i:{i}, set_list_len:{len(r.zrange("timer", 0, -1, withscores=True))}')
            print(f'answered: {answered}')
            print(f'guessed_object: {guessed_object}')
            print(f'diff:{diff}')

            if answered is True and guessed_object == "word":
                print("removing since it was answered")
                r.zrem("timer", value_score[0])

            if (diff <= 0 and answered is False) or (diff <= 0 and guessed_object == "insider"):
                # message_id, sender_id, text = name.decode().split(':')
                print(end_timestamp)
                line_bot_api.multicast(
                    members,
                    TextSendMessage(text=f'残り{time_left}秒です。')
                )
                r.zrem("timer", value_score[0])
                print("removed one")
                print(f'zrangelength :{len(r.zrange("timer", 0, -1, withscores=True))}\n')

                if len(r.zrange("timer", 0, -1, withscores=True)) == 0 or time_left == 0:
                    if guessed_object == "word":
                        line_bot_api.multicast(
                            members,
                            [TextSendMessage(text=f'お題あての時間が切れました。'),
                             TextSendMessage(text='マスターはまず答えを言ってください。次に表示されている確認ボタンを押してください。')]
                        )

                        line_bot_api.push_message(
                            master,
                            [get_confirm_button_moving_to_insider_guess(room_id)]
                        )
                    if guessed_object == "insider":
                        with open('rooms.json', 'r') as room_json:
                            rooms_dict = json.load(room_json)
                            room = rooms_dict[room_id]

                        start_vote_of_insider(room, room_id)

            else:
                print("breaking from 'for'\n")
                break
        await asyncio.sleep(delay)  # indent position is important


def get_confirm_button_moving_to_insider_guess(room_id):

    confirm_template_message = TemplateSendMessage(
        alt_text='確認ボタンが表示されています。',
        template=ButtonsTemplate(
            title='確認',
            text='インサイダーの予想に移ります。',
            actions=[
                PostbackTemplateAction(
                    label='確認',
                    text='確認',
                    data=f'room_id={room_id}&next_action=word_guess_time_up'
                )
            ]
        )
    )
    return confirm_template_message


def start_vote_of_insider(room, room_id):
    members_without_master = get_members_without_master(room)
    line_bot_api.multicast(
        room['members'],
        [TextSendMessage(text='時間切れです。すぐに以下のボタンからインサイダーと思う人を投票してください。全員の票が集まったら、結果を発表します。'),
         get_guess_insider_carousel(room_id, members_without_master, False)]
    )


def get_members_without_master(room):
    master = room['rounds_info'][-1]['master']
    copy_of_members = copy.deepcopy(room['members'])
    copy_of_members.remove(master)
    members_without_master = copy_of_members
    return members_without_master


def get_guess_insider_carousel(room_id, members, is_final_guess):
    columns = [get_display_name_carousel_column(user_id, room_id, is_final_guess) for user_id in members]
    carousel_template_message = TemplateSendMessage(
        alt_text='Buttons template',
        template=CarouselTemplate(
            columns=columns
        )
    )

    return carousel_template_message


def get_display_name_carousel_column(user_id, room_id, is_final_guess):
    display_name = line_bot_api.get_profile(user_id).display_name
    last_guess_text = ""
    if is_final_guess:
        last_guess_text = "&last_guess=true"
    return CarouselColumn(
        title="インサイダーを予想しましょう。",
        text=f'{display_name} さんでしょうか？',
        actions=[
            PostbackTemplateAction(
                label=display_name,
                text=f'投票：{display_name}',
                data=f'room_id={room_id}&insider_guess={user_id}{last_guess_text}'
            )
        ]
    )



if __name__ == '__main__':

    r.flushall()
    print("redis flushed")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(timer(2))
        print("one loop ended")
    finally:
        loop.close()
