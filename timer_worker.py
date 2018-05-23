import time
import asyncio
from linebot.models import (
    TextSendMessage, ButtonsTemplate,
    TemplateSendMessage, PostbackTemplateAction, CarouselColumn, CarouselTemplate
)
from constants import line_bot_api, r
import json
import copy


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
                current_round_count = len(rooms_dict[room_id]["rounds_info"])

            print(f'\nroom_id{room_id} time_left:{time_left}')
            print(f'i:{i}, set_list_len:{len(r.zrange("timer", 0, -1, withscores=True))}')
            print(f'answered: {answered}')
            print(f'guessed_object: {guessed_object}')
            print(f'diff:{diff}')

            if guessed_object == "insider":
                guessed_object_jpn = "インサイダー推理"
            elif guessed_object == "word":
                guessed_object_jpn = "お題あて"

            if answered is True and guessed_object == "word":
                print("removing since it was answered")
                r.zrem("timer", value_score[0])

            if (diff <= 0 and answered is False) or (diff <= 0 and guessed_object == "insider"):
                # message_id, sender_id, text = name.decode().split(':')
                print(end_timestamp)
                line_bot_api.multicast(
                    members,
                    TextSendMessage(text=f'{guessed_object_jpn}の残り時間、{time_left}秒です。')
                )
                r.zrem("timer", value_score[0])
                print("removed one")
                print(f'z range length :{len(r.zrange("timer", 0, -1, withscores=True))}\n')

                if len(r.zrange("timer", 0, -1, withscores=True)) == 0 or time_left == 0:
                    if guessed_object == "word":
                        line_bot_api.multicast(
                            members,
                            [TextSendMessage(text=f'お題あての時間が切れました。'),
                             TextSendMessage(text='マスターはまず答えを言ってください。次に表示されている確認ボタンを押してください。')]
                        )

                        line_bot_api.push_message(
                            master,
                            [get_confirm_button_moving_to_insider_guess(room_id, current_round_count)]
                        )

            else:
                print("breaking from 'for'\n")
                break
        await asyncio.sleep(delay)  # indent position is important


def get_confirm_button_moving_to_insider_guess(room_id, current_round_count):

    confirm_template_message = TemplateSendMessage(
        alt_text='確認ボタンが表示されています。',
        template=ButtonsTemplate(
            title='確認',
            text='インサイダーの予想に移ります。',
            actions=[
                PostbackTemplateAction(
                    label='確認',
                    text='確認',
                    data=f'room_id={room_id}&nth_round={current_round_count}&next_action=word_guess_time_up'
                )
            ]
        )
    )
    return confirm_template_message


def start_vote_of_insider(room, room_id):
    members_without_master = get_members_without_master(room)
    line_bot_api.multicast(
        get_room_members(room),
        [TextSendMessage(text='時間切れです。すぐに以下のボタンからインサイダーと思う人を投票してください。全員の票が集まったら、結果を発表します。'),
         get_guess_insider_carousel(room_id, members_without_master, False)]
    )


def get_members_without_master(room):
    master = room['rounds_info'][-1]['master']
    copy_of_members = copy.deepcopy(get_room_members(room))
    print(copy_of_members)
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


def get_room_members(room: dict):
    return list([member_info['user_id'] for member_info in room['members']])
    # return room['members']


if __name__ == '__main__':

    r.flushall()
    print("redis flushed")
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(timer(2))
    finally:
        print("loop closing")
        loop.close()
