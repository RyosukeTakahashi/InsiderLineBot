from __future__ import unicode_literals
import collections
import copy
import json
import urllib.parse as urlparse
# noinspection PyUnresolvedReferences
import cf_deployment_tracker
import time
import random

import datetime
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
    ButtonsTemplate, PostbackTemplateAction, MessageTemplateAction, URITemplateAction,
    FollowEvent)
from constants import (
    line_bot_api, db, client, parser, port, func_mode, reminder_timings_setting,
    insider_caught_penalty, insider_uncaught_score, insider_guess_correct_point, insider_guess_wrong_penalty,
    insider_guess_remind_interval, time_limit_when_word_guess_failed, rule,
    round_img)

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
        if isinstance(event, FollowEvent):
            line_bot_api.reply_message(
                event.reply_token,
                [TextSendMessage(text="インサイダー風ゲームBot友だちとなって頂きありがとうございます！\n"),
                 TextSendMessage(text="一緒にゲームをするメンバーがいるルームで、'す'を入力するとスタートできます！"),
                 TextSendMessage(text="'る'を入力するとルールが表示されます！")]
            )

        if isinstance(event, JoinEvent):
            line_bot_api.reply_message(
                event.reply_token,
                [TextSendMessage(text="インサイダー風ゲームBotを招待していただきありがとうございます！\n"),
                 TextSendMessage(text="'す'を入力するとスタート、'る'を入力するとルールが表示されます！")]
            )

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

                if text in ['r', 'rule', 'ルール', 'る', '説明', 'ル']:
                    line_bot_api.reply_message(
                        event.reply_token,
                        [TextSendMessage(text=rule)]
                    )

                post_text_to_db(event)

        if isinstance(event, PostbackEvent):

            data_str = event.postback.data
            data_dict = dict(urlparse.parse_qsl(data_str))
            room_id = data_dict['room_id']

            with open('rooms.json', 'r') as room_json:
                rooms_dict = json.load(room_json)

            room = rooms_dict[room_id]
            current_round_count = len(room["rounds_info"])
            nth_round_in_data_dict = -1
            if "nth_round" in data_dict.keys():
                nth_round_in_data_dict = int(data_dict["nth_round"])

            latest_button = True
            if nth_round_in_data_dict != current_round_count:
                latest_button = False

            try:
                next_action = data_dict['next_action']
            except KeyError:
                next_action = ''

            if next_action == 'get-participation':
                display_name = get_display_name(event.source.user_id)
                new_user = event.source.user_id
                if new_user not in get_room_members(room) or func_mode == "one_phone_dev":
                    room['members'].append({
                        'user_id': event.source.user_id,
                        "score": 0,
                        "display_name": display_name
                    })
                    with open('rooms.json', 'w') as room_json:
                        json.dump(rooms_dict, room_json, indent=2)
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f'参加受付:{display_name}')
                    )
                else:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text=f'{display_name}は参加済みです。')
                    )

            if next_action == 'close':
                close_participation(event, room, room_id, rooms_dict)

            if next_action == 'start':
                if room["rounds_info"][-1]["started"] is False:
                    single_turn_main(room, room_id, event)
                    room["rounds_info"][-1]["started"] = True
                    with open('rooms.json', 'w') as room_json:
                        json.dump(rooms_dict, room_json, indent=2)
                else:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="開始済みです")
                    )

            if next_action == 'answered' and latest_button:
                if room['rounds_info'][-1]["answered"] is False:
                    room['rounds_info'][-1]["answered"] = True
                    rooms_dict[room_id] = room
                    real_insider = room['rounds_info'][-1]["insider"]
                    calculate_score_when_insider_guess_was_correct(real_insider, room)
                    with open('rooms.json', 'w') as room_json:
                        json.dump(rooms_dict, room_json, indent=2)

                    start_timestamp = int(data_dict["start_timestamp"])
                    single_turn_guess_insider(room, room_id, start_timestamp)
                else:
                    line_bot_api.reply_message(
                        event.reply_token,
                        TextSendMessage(text="既に正解が出てます。")
                    )

            if next_action == 'word_guess_time_up':
                real_insider = room['rounds_info'][-1]["insider"]
                calculate_score_when_word_guess_timed_up(real_insider, room)
                single_turn_guess_insider_when_time_is_up(room, room_id)

            if "insider_guess" in data_dict and "last_guess" not in data_dict:
                current_round = room['rounds_info'][-1]
                accept_vote(current_round, data_dict, event, rooms_dict, room)
                members = get_room_members(room)
                if len(current_round["insider_guess"]) >= len(members):
                    # noinspection PyArgumentList
                    c = collections.Counter(current_round['insider_guess'][:len(members)])
                    vote_result_sorted = c.most_common()
                    has_same_rate, guessed_insiders = has_same_rate_first_place(vote_result_sorted)
                    most_guessed_insider = vote_result_sorted[0][0]

                    if has_same_rate:
                        insider_guess_tournament(room, room_id, members, guessed_insiders)
                    else:
                        result_of_guess_message(room, current_round, most_guessed_insider)
                        if len(room['rounds_info']) == room["total_rounds"]:
                            line_bot_api.multicast(
                                members,
                                TextSendMessage(text=f"{room['total_rounds']}ラウンドが終わりました。ゲームを終了します。")
                            )
                        else:
                            # single_round_intro(members, room, room_id, rooms_dict)
                            run_date = datetime.datetime.now() + datetime.timedelta(seconds=6)

                            scheduler.add_job(single_round_intro, 'date', run_date=run_date,
                                              args=[members, room, room_id, rooms_dict])

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


def accept_vote(current_round, data_dict, event, rooms_dict, room):
    guessed_insider = data_dict["insider_guess"]
    already_voteds = current_round["commons_who_already_voted"]
    user_id = event.source.user_id
    if user_id not in already_voteds or func_mode == "one_phone_dev":
        current_round["insider_guess"].append(guessed_insider)
        already_voteds.append(user_id)
        display_names_who_voted = \
            [get_display_name_from_json(user_id_who_voted, room) for user_id_who_voted in already_voteds]
        who_voted_str = '\n'.join(display_names_who_voted)
        line_bot_api.reply_message(
            event.reply_token,
            [TextSendMessage(text=f"投票済みの方：\n{who_voted_str}")]
        )

    elif event.source.user_id in already_voteds:
        line_bot_api.reply_message(
            event.reply_token,
            TextSendMessage(text="あなたは投票済みです。")
        )
    with open('rooms.json', 'w') as room_json:
        json.dump(rooms_dict, room_json, indent=2)


def close_participation(event, room, room_id, rooms_dict):
    print(room)
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

    # if func_mode is not "production":
    #     rooms_dict.pop('1', None)  # only while testing to prevent number of rooms from increasing.
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
        'started': False,
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
        [ImageSendMessage(original_content_url=round_img[nth_round], preview_image_url=round_img[nth_round])]
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

    guessing_time = time_left
    reminder_timings = list(range(2, guessing_time, 30))
    reminder_timings.append(guessing_time)

    add_job_insider_guess_reminder(time_left, room, room_id)


def add_job_insider_guess_reminder(insider_guess_time_limit, room, room_id):

    if func_mode == "one_phone_dev":
        insider_guess_remind_timings = list(range(0, 13, insider_guess_remind_interval))
    else:
        insider_guess_remind_timings = list(range(0, insider_guess_time_limit, insider_guess_remind_interval))
    insider_guess_remind_timings.append(insider_guess_time_limit)
    if insider_guess_time_limit > 30:
        insider_guess_remind_timings.insert(1, 15)
    print("")
    print(insider_guess_remind_timings)
    now = datetime.datetime.now()
    members = get_room_members(room)
    remind_dts = [{
        "dt": now + datetime.timedelta(seconds=insider_guess_time_limit - remind_timing),
        "remind_timing": remind_timing
    } for remind_timing in insider_guess_remind_timings]

    for remind_dt in remind_dts:
        scheduler.add_job(send_insider_guess_reminder, 'date', run_date=remind_dt["dt"],
                          args=[remind_dt["remind_timing"], members, room, room_id])
    print(scheduler.print_jobs())


def send_insider_guess_reminder(text, members, room, room_id):
    line_bot_api.multicast(
        members,
        TextSendMessage(text=f'インサイダー予想時間：残り{text}秒')
    )
    if text == 0:
        start_vote_of_insider(room, room_id)
        pass


def single_turn_guess_insider_when_time_is_up(room, room_id):
    line_bot_api.multicast(
        get_room_members(room),
        [TextSendMessage(text='インサイダーは世論を操るのに失敗しました。'),
         TextSendMessage(text=f'ですが参考までに、インサイダーは誰だったか、議論しましょう。残り時間は\n{time_limit_when_word_guess_failed}秒です。')]
    )
    time_lefts = [0, 15, 30]
    remind_dts = [{
        "dt": datetime.datetime.now() + datetime.timedelta(seconds=time_limit_when_word_guess_failed - time_left),
        "time_left": time_left
    } for time_left in time_lefts]

    members = get_room_members(room)
    for remind_dt in remind_dts:
        scheduler.add_job(send_insider_guess_reminder, 'date', run_date=remind_dt["dt"],
                          args=[remind_dt["time_left"], members, room, room_id])
    print(scheduler.print_jobs())


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
        guess_result_message = "庶民がインサイダーを見事当てました。"
        calculate_score_when_insider_guess_was_correct(real_insider, room)
    else:
        guess_result_message = "インサイダーが狡猾にも庶民を騙すことに成功しました。"
        calculate_score_when_insider_guess_was_wrong(real_insider, room)

    scores_text_list = \
        [f'{get_display_name(user_info["user_id"])}: {user_info["score"]}' for user_info in room["members"]]
    scores_text = '\n'.join(scores_text_list)

    line_bot_api.multicast(
        get_room_members(room),
        [TextSendMessage(text=f"インサイダー（容疑）：{get_display_name_from_json(most_guessed_insider, room)}\n"
                              f"インサイダー（実際）：{get_display_name_from_json(real_insider, room)}"),
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


def calculate_score_when_word_guess_was_correct(real_insider, room):
    for member_info in room["members"]:
        if member_info["user_id"] == real_insider:
            member_info["score"] += 10
        else:  # commons
            member_info["score"] += 5


def calculate_score_when_word_guess_timed_up(real_insider, room):
    for member_info in room["members"]:
        if member_info["user_id"] == real_insider:
            member_info["score"] -= 10
        else:  # commons
            member_info["score"] -= 5

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
                    label='参加する(要:友達追加)',
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

    data = urlparse.urlencode({
        'room_id': room_id,
        'start_timestamp': start_timestamp,
        'nth_round': nth_round,
        'next_action': "answered"
    })

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
                    data=data
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
        print('text data added to db')
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
        print('postback data added to db')
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

def get_room_count(rooms_json):
    return len(rooms_json.keys())


def get_postback_data_dict(data):
    return dict(urlparse.parse_qsl(data))


def get_list_without_insider(members, insider):
    members.remove(insider)
    return members


def get_display_name(user_id):
    return line_bot_api.get_profile(user_id).display_name


def get_display_name_from_json(user_id, room):
    display_name = [member["display_name"] for member in room["members"] if member["user_id"] == user_id][0]
    return display_name


def get_room_members(room: dict):
    return list([member_info['user_id'] for member_info in room['members']])
    # return room['members']


#####################################


if __name__ == "__main__":
    scheduler = BackgroundScheduler()
    scheduler.start()
    app.run(debug=True, port=port, host='0.0.0.0')
