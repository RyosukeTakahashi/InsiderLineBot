from __future__ import unicode_literals
from cloudant import Cloudant
import os
import sys
from dotenv import load_dotenv
import atexit
import random
import time
import datetime
import sched
import re
import json
import requests
import urllib.parse as urlparse
import cf_deployment_tracker
from flask import Flask, request, abort, render_template, jsonify
from linebot import (LineBotApi, WebhookParser)
from linebot.exceptions import (InvalidSignatureError)
from linebot.models import (
    MessageEvent, TextMessage, TextSendMessage, ImageSendMessage, LocationMessage, ConfirmTemplate,
    PostbackEvent, JoinEvent, TemplateSendMessage, CarouselTemplate, CarouselColumn,
    ButtonsTemplate, PostbackTemplateAction, MessageTemplateAction, URITemplateAction
)
from richmenu import RichMenu, RichMenuManager

cf_deployment_tracker.track()

if os.path.isfile('.env') or os.path.isfile('env'):
    print('found .env. So it should be a local environment.')
    ENV = load_dotenv('.env')
    if ENV is None:
        ENV = load_dotenv('env')
else:
    print('Cannot find .env. So it should be on the cloud.')

CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
PLACES_APIKEY = os.getenv('PLACES_APIKEY')
GEOCODING_APIKEY = os.getenv('GEOCODING_APIKEY')
DB_NAME = os.getenv('DB_NAME')

CHATBOT_ENDPOINT = 'https://chatbot-api.userlocal.jp/api/chat'
SIMPLE_WIKIPEDIA_API = 'http://wikipedia.simpleapi.net/api'
PLACES_TEXTSEARCH_ENDPOINT = 'https://maps.googleapis.com/maps/api/place/textsearch/json'
PLACES_NEARBYSEARCH_ENDPOINT = 'https://maps.googleapis.com/maps/api/place/nearbysearch/json'
PLACES_DETAIL_ENDPOINT = 'https://maps.googleapis.com/maps/api/place/details/json'
PLACES_PHOTO_ENDPOINT = 'https://maps.googleapis.com/maps/api/place/photo'
GEOCODING_ENDPOINT = 'https://maps.googleapis.com/maps/api/geocode/json'

if CHANNEL_SECRET is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if CHANNEL_ACCESS_TOKEN is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

parser = WebhookParser(CHANNEL_SECRET)
line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)

if 'VCAP_SERVICES' in os.environ:
    vcap = json.loads(os.getenv('VCAP_SERVICES'))
    print('Found VCAP_SERVICES')
    if 'cloudantNoSQLDB' in vcap:
        creds = vcap['cloudantNoSQLDB'][0]['credentials']

elif os.path.isfile('vcap-local.json'):
    with open('vcap-local.json') as f:
        vcap = json.load(f)
        print('Found local VCAP_SERVICES')
        creds = vcap['services']['cloudantNoSQLDB'][0]['credentials']

user = creds['username']
password = creds['password']
url = 'https://' + creds['host']
client = Cloudant(user, password, url=url, connect=True)
db = client.create_database(DB_NAME, throw_on_exists=False)

app = Flask(__name__)

port = int(os.getenv('PORT', 8000))
# 8080 on bluemix
print("port is {}".format(port))


@app.route('/')
def home():
    return render_template('index.html')


@app.route('/api/visitors', methods=['POST'])
def put_visitor():
    user = request.json['name']
    if client:
        data = {'name': user}
        db.create_document(data)
        return 'Hello %s! I added you to the database.' % user
    else:
        print('No database')
        return 'Hello %s!' % user


@atexit.register
def shutdown():
    if client:
        client.disconnect()


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
                    line_bot_api.reply_message(
                        event.reply_token,
                        get_participation_button()
                    )

                if text == "rm":
                    get_richmenu()

                if text == "delete rm":
                    rmm = RichMenuManager(CHANNEL_ACCESS_TOKEN)
                    rmm.remove_all()

                post_text_to_db(event)

        if isinstance(event, PostbackEvent):

            data_str = event.postback.data
            data_dict = dict(urlparse.parse_qsl(data_str))
            # you can only use postbackevent for after button action because of below
            room_id = data_dict['room_id']
            room_json = open('rooms.json', 'r')
            rooms_dict = json.load(room_json)
            room = rooms_dict[room_id]
            room_json.close()
            try:
                next = data_dict['next']
            except:
                next = ''

            if next == 'get-participation':
                room['members'].append(event.source.user_id)
                json.dump(rooms_dict, open('rooms.json', 'w'), indent=2)

            if next == 'close':
                members = room['members']
                rounds = int(room['total_rounds'])
                line_bot_api.multicast(
                    members,
                    [TextSendMessage(text=f"ゲームID{room_id}に参加します"),
                     TextSendMessage(text=f"全部で{rounds}ラウンドです。")]
                )

                single_round_intro(members, room, room_id, rooms_dict)

            if next == 'start':
                round_info = room['rounds_info']
                now = datetime.datetime.now()

                master = round_info[-1]['master']
                nth_round = len(round_info)
                line_bot_api.multicast(room['members'],
                                       [TextSendMessage(text='スタートしました'),
                                        TextSendMessage(text='各自の役割を遂行してください。')]
                                       )
                # round_info[-1]['start_time'] = now.strftime('%Y/%m/%d %H/%M%s')
                # round_info[-1]['end_time'] = now + datetime.timedelta(seconds=5).strftime('%Y/%m/%d %H/%M%s')
                end_time = now + datetime.timedelta(seconds=5)


                line_bot_api.push_message(
                    master,
                    get_end_button(room_id, nth_round)
                )

                s = sched.scheduler(time.time, time.sleep)
                def send_remaining_time(passed_time):
                    line_bot_api.multicast(
                        members,
                        TextSendMessage(text=f'あと{300-passed_time}秒です。')
                    )
                def schedule_remind_time(remind_times):

                    for remind_time in remind_times:
                        s.enter(remind_times, 1, send_remaining_time, argument=remind_time)
                    s.run()
                    print(time.time())

                schedule_remind_time([3,6])

                line_bot_api.push_message(
                    master,
                    TextSendMessage(text="test")
                )


            post_postback_to_db(event)

    return 'OK'


def single_round_intro(members, room, room_id, rooms_dict):
    insider = random.choice(members)
    members.remove(insider)
    master = random.choice(members)
    members.remove(master)
    commons = members
    room['rounds_info'].append({
        'insider': insider,
        'master': master
    })
    rooms_dict[room_id] = room
    with open('rooms.json', 'w') as room_json:
        json.dump(rooms_dict, room_json, indent=2)

    nth_round = len(room['rounds_info'])
    word = room["words"][nth_round-1]
    line_bot_api.multicast(
        members,
        [TextSendMessage(text=f"それでは、第{nth_round}ラウンドを開始します。")]
    )


    line_bot_api.multicast(
        commons,
        [TextSendMessage(text='あなたは庶民です。'),
         TextSendMessage(text=f'お題を当てるためにマスターに質問をしていきましょう。'),
         TextSendMessage(text='なお、「はい」「いいえ」「わからない」でマスターが答えられる質問にしましょう'),
         TextSendMessage(text='それでは、マスターからの指示を待ちましょう')]

    )
    line_bot_api.push_message(
        insider,
        [TextSendMessage(text='インサイダーはあなたです。'),
         TextSendMessage(text=f'お題は"{word}"です。（お題はあなたとインサイダー以外には送られていません。）'),
         TextSendMessage(text='庶民のふりをしつつ、庶民を裏で操り、お題を当てさせてあげましょう。'),
         TextSendMessage(text='それでは、マスターからの指示を待ちましょう')]

    )
    line_bot_api.push_message(
        master,
        [TextSendMessage(text='マスターはあなたです。マスターであることを皆に伝えてください。'),
         TextSendMessage(text=f'お題は"{word}"です。（お題はあなたとマスター以外には送られていません。）'),
         TextSendMessage(text=f'お題に関しての庶民からの質問に「はい」「いいえ」「わからない」の３択で答えていきましょう。'),
         TextSendMessage(text=f'お題の"{word}"を当てられたら「正解です」と答え、「正解が出ました」ボタンを押しましょう'),
         get_start_button(room_id, len(room['rounds_info']))]
    )


#######################################

# Below are templates functions

def get_participation_button():
    rooms_json = open('rooms.json', 'r')
    rooms_dict = json.load(rooms_json)

    rooms_dict.pop('1', None)  # only while testing

    room_count = get_room_count(rooms_dict)
    new_room_id = room_count + 1

    rooms_dict[str(new_room_id)] = {
        "members": [],
        "total_rounds": 6,
        "rounds_ended": [],
        "insider_order": [],
        "master_order": [],
        "rounds_info": [],
        "words": [
            "ジェットコースター",
            "インク",
            "アイポッド",
            "メール",
            "ベルト",
            "紅茶"
        ]
    }
    json.dump(rooms_dict, open('rooms.json', 'w'), indent=2)

    data_dict = {'room_id': new_room_id,
                 'next': 'get-participation'}
    data = urlparse.urlencode(data_dict)

    buttons_template_message = TemplateSendMessage(
        alt_text='インサイダーゲームを開始します。参加者はボタンを押してください。',
        template=ButtonsTemplate(
            title='インサイダーを開始します',
            text='参加者はボタンを押してください。',
            actions=[
                PostbackTemplateAction(
                    label='参加する',
                    text='参加する',
                    data=data
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
                    text='スタート',
                    data=f'room_id={room_id}&next=start'
                )
            ]
        )
    )

    return buttons_template_message


def get_end_button(room_id, nth_round):
    buttons_template_message = TemplateSendMessage(
        alt_text='Buttons template',
        template=ButtonsTemplate(
            # thumbnail_image_url='https://example.com/image.jpg',
            title='正解が出たら押してください',
            text='このボタンはマスターのあなたにしか見えていません',
            actions=[
                PostbackTemplateAction(
                    label='正解が出ました',
                    text='正解が出ました',
                    data=f'room_id={room_id}&next=answered'
                )
            ]
        )
    )

    return buttons_template_message

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


def get_room_count(rooms_json):
    return len(rooms_json.keys())


def get_postback_data_dict(data):
    return dict(urlparse.parse_qsl(data))


def get_list_without_insider(members, insider):
    members.remove(insider)
    return members


#####################################
if __name__ == "__main__":
    # arg_parser = ArgumentParser(
    #     usage='Usage: python ' + __file__ + ' [--port <port>] [--help]'
    # )
    # arg_parser.add_argument('-p', '--port', default=port, help='port')
    # arg_parser.add_argument('-d', '--debug', default=False, help='debug')
    # options = arg_parser.parse_args()

    app.run(debug=True, port=port, host='0.0.0.0')
