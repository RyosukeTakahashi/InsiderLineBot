from __future__ import unicode_literals

import collections
import copy
import json
import urllib.parse as urlparse
# noinspection PyUnresolvedReferences
import cf_deployment_tracker
import time
import random

from apscheduler.schedulers.background import BackgroundScheduler

from worker import r
from utils_line_jobs import set_reminders
from rq import Queue
from flask import Flask, request, abort, render_template
from linebot.exceptions import (InvalidSignatureError)
# noinspection PyUnresolvedReferences
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage, ConfirmTemplate,
    PostbackEvent, JoinEvent, TemplateSendMessage, CarouselTemplate, CarouselColumn,
    ButtonsTemplate, PostbackTemplateAction, MessageTemplateAction, URITemplateAction
)
from constants import (
    line_bot_api, db, client, parser, port, func_mode, reminder_timings_setting, sleep_time,
    insider_caught_penalty, insider_uncaught_score, insider_guess_correct_point, insider_guess_wrong_penalty
)

# todo 画像を入れて、区切りを見えやすくする。


app = Flask(__name__)


@app.route('/')
def home():
    return render_template('index.html')


@app.route("/line/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']

    # get request body as text
    body = request.get_data(as_text=True)
    app.logger.info("Request body: " + body)

    # parse webhook body
    events = []
    try:
        events = parser.parse(body, signature)
    except InvalidSignatureError:
        abort(400)

    for event in events:

        if isinstance(event, MessageEvent):

            if isinstance(event.message, TextMessage):

                text = event.message.text

                if text in ['s', 'す']:
                    new_room_id = add_room_info_to_json_and_return_room_id()
                    line_bot_api.reply_message(
                        event.reply_token,
                        [TextSendMessage(text="このアカウントを友達登録をしてから、以下の参加ボタンを押してください。"),
                         get_participation_button(new_room_id)]
                    )

                if text in ['t', 'た']:
                    sample_timer(event)

                if text in ['m', 'main']:
                    with open('rooms.json', 'r') as room_json:
                        rooms_dict = json.load(room_json)
                    room = rooms_dict["1"]
                    single_turn_main(room, "1", event)

                if text in ['c', 'か']:
                    change_answer_state_to_true(event)

                if text in ['f', 'ふ']:
                    change_answer_state_to_false(event)

                post_text_to_db(event)

        if isinstance(event, PostbackEvent):

            data_str = event.postback.data
            data_dict = dict(urlparse.parse_qsl(data_str))
            # you can only use postback event for after button action because of below
            room_id = data_dict['room_id']
            with open('rooms.json', 'r') as room_json:
                rooms_dict = json.load(room_json)

            room = rooms_dict[room_id]
            try:
                next_action = data_dict['next_action']
            except KeyError:
                next_action = ''

            if next_action == 'get-participation':
                room['members'].append({'user_id': event.source.user_id, "score": 0, "display_name": "hoge"})
                print(room)
                with open('rooms.json', 'w') as room_json:
                    json.dump(rooms_dict, room_json, indent=2)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f'参加受付:{line_bot_api.get_profile(event.source.user_id).display_name}')
                )

            if next_action == 'close':
                close_participation(event, room, room_id, rooms_dict)

            if next_action == 'start':
                single_turn_main(room, room_id, event)

            if next_action == 'answered':
                room['rounds_info'][-1]["answered"] = True
                rooms_dict[room_id] = room
                with open('rooms.json', 'w') as room_json:
                    json.dump(rooms_dict, room_json, indent=2)

                start_timestamp = int(data_dict["start_timestamp"])
                single_turn_guess_insider(room, room_id, start_timestamp)

            if next_action == 'word_guess_time_up':
                single_turn_guess_insider_when_time_is_up(room, room_id)

            if "insider_guess" in data_dict and "last_guess" not in data_dict:
                current_round = room['rounds_info'][-1]
                accept_vote(current_round, data_dict, event, rooms_dict)

                if len(current_round["insider_guess"]) >= len(get_room_members(room)):
                    members = get_room_members(room)
                    # noinspection PyArgumentList
                    c = collections.Counter(current_round['insider_guess'][:len(members)])
                    vote_result_sorted = c.most_common()
                    has_same_rate, guessed_insiders = has_same_rate_first_place(vote_result_sorted)
                    most_guessed_insider = vote_result_sorted[0][0]

                    if has_same_rate:
                        insider_guess_tournament(room, room_id, members, guessed_insiders)
                    else:
                        result_of_guess_message(room, current_round, most_guessed_insider)
                        if current_round == room["total_rounds"]:
                            line_bot_api.multicast(
                                members,
                                TextSendMessage(text=f"{current_round}ラウンドが終わりました。ゲームを終了します。")
                            )
                        else:
                            single_round_intro(members, room, room_id, rooms_dict)

            if "last_guess" in data_dict:
                members = get_room_members(room)
                current_round = room['rounds_info'][-1]
                last_guessed_insider = data_dict["insider_guess"]
                result_of_guess_message(room, current_round, last_guessed_insider)

                if current_round == room["total_rounds"]:
                    line_bot_api.multicast(
                        members,
                        TextSendMessage(text=f"{current_round}ラウンドが終わりました。ゲームを終了します。")
                    )
                else:
                    single_round_intro(members, room, room_id, rooms_dict)

            post_postback_to_db(event)

    return 'OK'


def accept_vote(current_round, data_dict, event, rooms_dict):
    guessed_insider = data_dict["insider_guess"]
    already_voteds = current_round["commons_who_already_voted"]
    if event.source.user_id not in already_voteds or func_mode == "one_phone_dev":
        current_round["insider_guess"].append(guessed_insider)
        already_voteds.append(event.source.user_id)
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text="投票を受け付けました。"),
             TextSendMessage(text=f"{len(already_voteds)}人が投票済みです。")]
        )

    elif event.source.user_id in already_voteds:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="あなたは投票済みです。")
        )
    with open('rooms.json', 'w') as room_json:
        json.dump(rooms_dict, room_json, indent=2)


def close_participation(event, room, room_id, rooms_dict):
    if func_mode is not "one_phone_dev":
        members = list(set(get_room_members(room)))  # if in dev, there would be many same IDs.
    else:
        members = get_room_members(room)
        line_bot_api.push_message(
            "U0a028f903127e2178bd789b4b4046ba7",
            TextSendMessage(text=f"this is {func_mode} mode")
        )
    if len(members) < 4:
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=f"最低でも4人必要です。5~8人がおすすめです。"),
             TextSendMessage(text=f"上の参加ボタンをあと{4-len(members)}人以上に押してもらってから、もう一度「参加を締め切るボタン」を押してください。」")]
        )
    else:
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=f"皆様の役割を個人メッセージでお送りしました。これ以降は、そちらをご参考ください。")]
        )
        rounds = int(room['total_rounds'])
        line_bot_api.multicast(
            members,
            [TextSendMessage(text=f"ゲームID{room_id}に参加します"),
             TextSendMessage(text=f"全部で{rounds}ラウンドです。")]
        )
        single_round_intro(members, room, room_id, rooms_dict)


def add_room_info_to_json_and_return_room_id():
    with open('rooms.json', 'r') as room_json:
        rooms_dict = json.load(room_json)

    if func_mode is not "production":
        rooms_dict.pop('1', None)  # only while testing to prevent number of rooms from increasing.
    room_count = get_room_count(rooms_dict)
    new_room_id = room_count + 1

    with open('words.txt', 'r') as f:
        whole_words_list = f.readlines()
    picked_words = [word.replace('\n', "") for word in random.sample(whole_words_list, 5)]
    rooms_dict[str(new_room_id)] = {
        'members': [],
        "total_rounds": 5,
        "rounds_info": [],
        "words": picked_words
    }
    with open('rooms.json', 'w') as room_json:
        json.dump(rooms_dict, room_json, indent=2)

    return new_room_id


def single_round_intro(members, room, room_id, rooms_dict):
    members_copy = copy.deepcopy(members)
    insider = random.choice(members_copy)
    members_copy.remove(insider)
    master = random.choice(members_copy)
    members_copy.remove(master)
    commons = members_copy
    room['rounds_info'].append({
        'insider': insider,
        'master': master,
        'answered': False,
        'insider_guess': [],
        'commons_who_already_voted': []
    })
    rooms_dict[room_id] = room
    with open('rooms.json', 'w') as room_json:
        json.dump(rooms_dict, room_json, indent=2)

    nth_round = len(room['rounds_info'])
    word = room["words"][nth_round - 1]
    line_bot_api.multicast(
        members,
        [TextSendMessage(text=f"それでは、第{nth_round}ラウンドを開始します。")]
    )

    line_bot_api.multicast(
        commons,
        [TextSendMessage(text='あなたの役割は庶民です。'),
         TextSendMessage(text=f'お題を当てるためにマスターに質問をしていきましょう。'),
         TextSendMessage(text='なお、「はい」「いいえ」「わからない」でマスターが答えられる質問にしましょう'),
         TextSendMessage(text='それでは、マスターからの指示を待ちましょう')]

    )
    line_bot_api.push_message(
        insider,
        [TextSendMessage(text='インサイダーはあなたです。'),
         TextSendMessage(text=f'お題は"{word}"です。（お題はあなたとマスター以外には送られていません。）'),
         TextSendMessage(text='庶民のふりをしつつ、庶民を裏で操り、お題を当てさせてあげましょう。'),
         TextSendMessage(text='それでは、マスターからの指示を待ちましょう')]

    )
    line_bot_api.push_message(
        master,
        [TextSendMessage(text='マスターはあなたです。マスターであることを皆に伝えてください。'),
         TextSendMessage(text=f'お題は"{word}"です。（お題はあなたとインサイダー以外には送られていません。）'),
         TextSendMessage(text=f'お題に関しての庶民からの質問に「はい」「いいえ」「わからない」の３択で答えていきましょう。'),
         TextSendMessage(text=f'お題の"{word}"を当てられたら「正解です」と答え、「正解が出ました」ボタンを押しましょう'),
         get_start_button(room_id, len(room['rounds_info']))]
    )


def single_turn_main(room, room_id, event):
    members = get_room_members(room)
    round_info = room['rounds_info']
    master = round_info[-1]['master']
    nth_round = len(round_info)
    line_bot_api.multicast(get_room_members(room),
                           [TextSendMessage(text=f'第{nth_round}ラウンドをスタートしました'),
                            TextSendMessage(text='各自の役割を遂行してください。')]
                           )

    start_timestamp = int(str(event.timestamp)[:10])

    line_bot_api.push_message(
        master,
        get_end_button(room_id, nth_round, start_timestamp)
    )

    reminder_timings = reminder_timings_setting
    q = Queue(connection=r)
    guessing_time = 182
    guessed_object = "word"
    q.enqueue(set_reminders, start_timestamp, reminder_timings, members, room_id, master, guessing_time, guessed_object)

    line_bot_api.multicast(
        members,
        TextSendMessage(text=f"それでは制限時間内にお題を予測してください。正解が出たらマスターは「正解が出ました」ボタンを押してください。 ")
    )


def single_turn_guess_insider(room, room_id, start_timestamp):
    time_left = int(time.time()) - start_timestamp
    line_bot_api.multicast(
        get_room_members(room),
        [TextSendMessage(text='お題の正解が出たようです。'),
         TextSendMessage(text=f'それではインサイダーは誰だったか、議論しましょう。{time_left}秒議論したので、残り時間は{time_left}秒です。')]
    )

    round_info = room['rounds_info']
    master = round_info[-1]['master']
    guessing_time = time_left
    reminder_timings = list(range(2, guessing_time, 30))
    reminder_timings.append(guessing_time)
    guessed_object = "insider"

    # 残っていたタイマーを消す。複数のグループがやっていたらやばいかも？さらにグループIDでしぼれがいいか。
    set_list = r.zrange("timer", 0, -1, withscores=True)
    for i, value_score in enumerate(set_list):
        end_timestamp = value_score[1]
        if end_timestamp < time.time():
            r.zrem("timer", value_score[0])

    print("printing zrange")
    print(r.zrange('timer', 0, -1, withscores=True))

    q = Queue(connection=r)
    q.enqueue(set_reminders, int(time.time()), reminder_timings, get_room_members(room),
              room_id, master, guessing_time, guessed_object)

    # start_vote_of_insider(room, room_id)


def single_turn_guess_insider_when_time_is_up(room, room_id):
    line_bot_api.multicast(
        get_room_members(room),
        [TextSendMessage(text='インサイダーは世論を操るのに失敗しました。'),
         TextSendMessage(text=f'ですが参考までに、インサイダーは誰だったか、議論しましょう。残り時間は{sleep_time}秒です。')]
    )

    # scheduler = BackgroundScheduler()
    scheduler_starttime = time.time()
    scheduler.add_job(lambda: timer_for_insider_guess(scheduler_starttime, room, room_id),
                      'interval', seconds=30, id='timer')

    # time.sleep(sleep_time)  # APScheduler?試すべき
    # start_vote_of_insider(room, room_id)


def timer_for_insider_guess(scheduler_starttime, room, room_id):
    diff = int(time.time() - scheduler_starttime)
    time_limit = 90
    if diff >= time_limit:

        scheduler.remove_job('timer')
        start_vote_of_insider(room, room_id)
    if diff < time_limit:
        line_bot_api.multicast(
            get_room_members(room),
            [TextSendMessage(text=f'残り{time_limit - diff}秒')]
        )

    print(diff)


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


def has_same_rate_first_place(vote_result_sorted):
    biggest_vote_count = vote_result_sorted[0][1]
    vote_dict = {}
    for word, count in vote_result_sorted:
        if count in vote_dict.keys():
            vote_dict[count].append(word)
        else:
            vote_dict[count] = [word]

    has_same_rate = False
    guessed_insiders = vote_dict[biggest_vote_count]
    if len(guessed_insiders) > 1:
        has_same_rate = True
    return has_same_rate, guessed_insiders


def insider_guess_tournament(room, room_id, members, guessed_insiders):
    master = room['rounds_info'][-1]['master']
    print("printing guessed insiders")
    print(guessed_insiders)
    guessed_insiders_str = ', '.join([get_display_name(guessed_insider) for guessed_insider in guessed_insiders])
    line_bot_api.multicast(
        members,
        [TextSendMessage(text="投票の結果、同率一位がいました。"),
         TextSendMessage(text=f"{guessed_insiders_str} が最もインサイダーの疑惑がかけられています。"),
         TextSendMessage(text="マスターが議論をして、最終インサイダー予想をしてください。"),
         TextSendMessage(text="マスターに投票ボタンを送りました。")]
    )

    line_bot_api.push_message(
        master,
        get_guess_insider_carousel(room_id, get_members_without_master(room), True)
    )


def result_of_guess_message(room, current_round, most_guessed_insider):
    real_insider = current_round['insider']

    if real_insider == most_guessed_insider:
        guess_result_message = "庶民がインサイダーを当てることに成功しました。"
        calculate_score_when_insider_guess_was_correct(real_insider, room)
    else:
        guess_result_message = "インサイダーが狡猾にも庶民を騙すことに成功しました。"
        calculate_score_when_insider_guess_was_wrong(real_insider, room)

    scores_text_list = [f'{get_display_name(user_info["user_id"])}: {user_info["score"]}' for user_info in room["members"]]
    scores_text = '\n'.join(scores_text_list)

    line_bot_api.multicast(
        get_room_members(room),
        [TextSendMessage(text=f"インサイダーとして疑われたのは、"),
         TextSendMessage(text=f"{line_bot_api.get_profile(most_guessed_insider).display_name} です"),
         TextSendMessage(text=f"実際のインサイダーは{line_bot_api.get_profile(real_insider).display_name} でした。"),
         TextSendMessage(text=f"{guess_result_message}"),
         TextSendMessage(text=f"現在のスコアです。\n\n{scores_text}")
         ]
    )


def calculate_score_when_insider_guess_was_wrong(real_insider, room):
    for member_info in room["members"]:
        if member_info["user_id"] == real_insider:
            member_info["score"] += insider_uncaught_score
        else:  # commons
            member_info["score"] -= insider_guess_wrong_penalty


def calculate_score_when_insider_guess_was_correct(real_insider, room):
    for member_info in room["members"]:
        if member_info["user_id"] == real_insider:
            member_info["score"] -= insider_caught_penalty
        else:  # commons
            member_info["score"] += insider_guess_correct_point


#######################################

# Below are templates functions


def get_participation_button(new_room_id):
    buttons_template_message = TemplateSendMessage(
        alt_text='インサイダーゲームを開始します。参加者はボタンを押してください。',
        template=ButtonsTemplate(
            title='インサイダーを開始します',
            text='参加者はボタンを押してください。',
            actions=[
                PostbackTemplateAction(
                    label='参加する',
                    text='参加する',
                    data=urlparse.urlencode({
                        'room_id': new_room_id,
                        'next_action': 'get-participation'
                    })
                ),
                PostbackTemplateAction(
                    label='参加を締め切る',
                    text='参加を締め切る',
                    data=urlparse.urlencode(
                        {
                            'room_id': new_room_id,
                            'next_action': 'close'
                        }
                    )
                )
            ]
        )
    )

    return buttons_template_message


def get_start_button(room_id, nth_round):
    buttons_template_message = TemplateSendMessage(
        alt_text='Buttons template',
        template=ButtonsTemplate(
            # thumbnail_image_url='https://example.com/image.jpg',
            title='各自が役割を確認できたらスタートを押してください',
            text='このボタンはマスターのあなたにしか見えていません',
            actions=[
                PostbackTemplateAction(
                    label='スタート',
                    text=f'第{nth_round}ラウンドをスタート',
                    data=f'room_id={room_id}&next_action=start'
                )
            ]
        )
    )

    return buttons_template_message


def get_end_button(room_id, nth_round, start_timestamp):
    buttons_template_message = TemplateSendMessage(
        alt_text='Buttons template',
        template=ButtonsTemplate(
            # thumbnail_image_url='https://example.com/image.jpg',
            title='正解が出たら押してください',
            text='このボタンはマスターのあなたにしか見えていません',
            actions=[
                PostbackTemplateAction(
                    label='正解が出ました',
                    text=f'第{nth_round}ラウンドの正解が出ました',
                    data=f'room_id={room_id}&start_timestamp={start_timestamp}&next_action=answered'
                )
            ]
        )
    )

    return buttons_template_message


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


# def get_guess_insider_button(room_id, members, nth_round):
#     actions = [get_display_name_postback_template_action(user_id, room_id) for user_id in members]
#
#     buttons_template_message = TemplateSendMessage(
#         alt_text='Buttons template',
#         template=ButtonsTemplate(
#             # thumbnail_image_url='https://example.com/image.jpg',
#             title='インサイダーを予測してください',
#             text='お選びください',
#             actions=actions
#         )
#     )
#
#     return buttons_template_message
#
#
# def get_display_name_postback_template_action(user_id, room_id):
#     display_name = line_bot_api.get_profile(user_id).display_name
#     return PostbackTemplateAction(
#         label=display_name,
#         text=display_name,
#         data=f'room_id={room_id}&insider_guess={user_id}'
#     )


# get template function end

###############################################

# Below are api using function


def post_text_to_db(event):
    data_to_send = {
        "text": event.message.text,
        "text_id": event.message.id,
        "user_id": event.source.user_id,
        "type": event.type,
        "timestamp": event.timestamp
    }

    if client:
        db.create_document(data_to_send)
        print('data added to db')
        return 'done'

    else:
        print('No database')


def post_postback_to_db(event):
    data_to_send = {
        "postback_data": event.postback.data,
        "user_id": event.source.user_id,
        "type": event.type,
        "timestamp": event.timestamp
    }

    if client:
        db.create_document(data_to_send)
        print('data added to db')
        return 'done'

    else:
        print('No database')


# api using function end.

#####################################

# below are richmenu function
#####################################


#####################################

# below are you utility functions
#####################################

def change_answer_state_to_false(event):
    with open('rooms.json', 'r') as room_json:
        rooms_dict = json.load(room_json)
        rooms_dict["1"]["rounds_info"][-1]["answered"] = False
    with open('rooms.json', 'w') as room_json:
        json.dump(rooms_dict, room_json, indent=2)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="changing answer state to false")
    )


def change_answer_state_to_true(event):
    with open('rooms.json', 'r') as room_json:
        rooms_dict = json.load(room_json)
        rooms_dict["1"]["rounds_info"][-1]["answered"] = True
    with open('rooms.json', 'w') as room_json:
        json.dump(rooms_dict, room_json, indent=2)
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text="changing answer state to true")
    )


def sample_timer(event):
    timestamp = int(str(event.timestamp)[:10])
    line_bot_api.reply_message(
        event.reply_token,
        TextSendMessage(text=f"直前のメッセージ受け付け時のタイムスタンプ：{timestamp}")
    )
    q = Queue(connection=r)
    members = ['U0a028f903127e2178bd789b4b4046ba7', 'U0a028f903127e2178bd789b4b4046ba7']
    q.enqueue(set_reminders, timestamp, [3, 6, 9], members, "1")
    print('queing reminders')


def get_room_count(rooms_json):
    return len(rooms_json.keys())


def get_postback_data_dict(data):
    return dict(urlparse.parse_qsl(data))


def get_list_without_insider(members, insider):
    members.remove(insider)
    return members


def get_display_name(user_id):
    print(f'user_id is {user_id}')
    return line_bot_api.get_profile(user_id).display_name


def get_room_members(room: dict):
    return list([member_info['user_id'] for member_info in room['members']])
    # return room['members']


#####################################


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.start()
    app.run(debug=True, port=port, host='0.0.0.0')
