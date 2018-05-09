from __future__ import unicode_literals
import copy
import json
import urllib.parse as urlparse
import cf_deployment_tracker
import time
import random
from worker import r
from utils_line_jobs import set_reminders
from rq import Queue
from flask import Flask, request, abort, render_template
from linebot.exceptions import (InvalidSignatureError)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage, ConfirmTemplate,
    PostbackEvent, JoinEvent, TemplateSendMessage, CarouselTemplate, CarouselColumn,
    ButtonsTemplate, PostbackTemplateAction, MessageTemplateAction, URITemplateAction
)
from constants import line_bot_api, db, client, parser, port, func_mode, reminder_timings_setting, sleep_time

# todo インサイダー決選投票
# todo インサイダー議論でsleepのところを非同期にする

cf_deployment_tracker.track()

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
                        get_participation_button(new_room_id)
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
                next = data_dict['next']
            except:
                next = ''

            if next == 'get-participation':
                room['members'].append(event.source.user_id)
                with open('rooms.json', 'w') as room_json:
                    json.dump(rooms_dict, room_json, indent=2)
                line_bot_api.reply_message(
                    event.reply_token,
                    TextSendMessage(text=f'参加受付:{line_bot_api.get_profile(event.source.user_id).display_name}')
                )

            if next == 'close':
                if func_mode is not "dev":
                    members = list(set(room["members"]))  # if in dev, there would be many same IDs.
                else:
                    members = room['members']

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

            if next == 'start':
                single_turn_main(room, room_id, event)

            if next == 'answered':
                room['rounds_info'][-1]["answered"] = True
                rooms_dict[room_id] = room
                with open('rooms.json', 'w') as room_json:
                    json.dump(rooms_dict, room_json, indent=2)

                start_timestamp = int(data_dict["start_timestamp"])
                single_turn_guess_insider(room, room_id, start_timestamp)

            if next == 'word_guess_time_up':
                single_turn_guess_insider_when_time_is_up(room, room_id)

            if "insider_guess" in data_dict:
                guessed_insider = data_dict["insider_guess"]
                room['rounds_info'][-1]["insider_guess"].append(guessed_insider)
                with open('rooms.json', 'w') as room_json:
                    json.dump(rooms_dict, room_json, indent=2)

                if len(room['rounds_info'][-1]["insider_guess"]) >= len(room['members']):
                    members = room['members']
                    result_of_guess_message(members, room, room_id)
                    time.sleep(2)
                    single_round_intro(members, room, room_id, rooms_dict)

            post_postback_to_db(event)

    return 'OK'


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
        "members": [],
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
    members = room['members']
    round_info = room['rounds_info']
    master = round_info[-1]['master']
    nth_round = len(round_info)
    line_bot_api.multicast(room['members'],
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
    q.enqueue(set_reminders, start_timestamp, reminder_timings, members, room_id)


def single_turn_guess_insider(room, room_id, start_timestamp):
    time_left = int(time.time()) - start_timestamp
    line_bot_api.multicast(
        room['members'],
        [TextSendMessage(text='お題の正解が出たようです。'),
         TextSendMessage(text=f'それではインサイダーは誰だったか、議論しましょう。{time_left}秒議論したので、残り時間は{time_left}秒です。')]
    )
    if func_mode == "dev":
        time.sleep(2)
    else:
        time.sleep(time_left)

    start_vote_of_insider(room, room_id)


def single_turn_guess_insider_when_time_is_up(room, room_id):
    line_bot_api.multicast(
        room['members'],
        [TextSendMessage(text='インサイダーは世論を操るのに失敗しました。'),
         TextSendMessage(text=f'ですが参考までに、インサイダーは誰だったか、議論しましょう。残り時間は{180}秒です。')]
    )
    if func_mode is not "production":
        time.sleep(sleep_time)
    else:
        time.sleep(180)

    start_vote_of_insider(room, room_id)


def start_vote_of_insider(room, room_id):
    master = room['rounds_info'][-1]['master']
    copy_of_members = copy.deepcopy(room['members'])
    copy_of_members.remove(master)
    members_without_master = copy_of_members
    print(members_without_master)
    line_bot_api.multicast(
        room['members'],
        [TextSendMessage(text='時間切れです。すぐに以下のボタンからインサイダーと思う人を投票してください。全員の票が集まったら、結果を発表します。'),
         get_guess_insider_carousel(room_id, members_without_master)]
    )


def result_of_guess_message(members, room, room_id):
    import collections
    c = collections.Counter(room['members'][:len(members)])
    most_guessed_insider = c.most_common()[0][0]
    real_insider = room['rounds_info'][-1]['insider']
    if real_insider == most_guessed_insider:
        guess_result_message = "庶民がインサイダーを当てることに成功しました。"
    else:
        guess_result_message = "インサイダーが狡猾にも庶民を騙すことに成功しました。"
    line_bot_api.multicast(
        members,
        [TextSendMessage(text=f"ゲームID{room_id}のインサイダーとして疑われたのは、"),
         TextSendMessage(text=f"{line_bot_api.get_profile(most_guessed_insider).display_name} です"),
         TextSendMessage(text=f"実際のインサイダーは{line_bot_api.get_profile(real_insider).display_name} でした。"),
         TextSendMessage(text=f"{guess_result_message}"),
         ]
    )


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
                        'next': 'get-participation'
                    })
                ),
                PostbackTemplateAction(
                    label='参加を締め切る',
                    text='参加を締め切る',
                    data=urlparse.urlencode(
                        {
                            'room_id': new_room_id,
                            'next': 'close'
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
                    data=f'room_id={room_id}&next=start'
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
                    data=f'room_id={room_id}&start_timestamp={start_timestamp}&next=answered'
                )
            ]
        )
    )

    return buttons_template_message


def get_guess_insider_carousel(room_id, members):
    columns = [get_display_name_carousel_column(user_id, room_id) for user_id in members]
    carousel_template_message = TemplateSendMessage(
        alt_text='Buttons template',
        template=CarouselTemplate(
            columns=columns
        )
    )

    return carousel_template_message


def get_display_name_carousel_column(user_id, room_id):
    display_name = line_bot_api.get_profile(user_id).display_name

    return CarouselColumn(
        title=display_name,
        text=display_name,
        actions=[
            PostbackTemplateAction(
                label=display_name,
                text=display_name,
                data=f'room_id={room_id}&insider_guess={user_id}'
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


#####################################
if __name__ == "__main__":
    app.run(debug=True, port=port, host='0.0.0.0')
