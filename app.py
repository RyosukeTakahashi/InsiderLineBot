from __future__ import unicode_literals
from cloudant import Cloudant
import os
import sys
from dotenv import load_dotenv
import atexit
import pprint
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

        # print("showing event")
        # pprint.pprint(event)
        # print("")

        if isinstance(event, MessageEvent):

            if isinstance(event.message, TextMessage):

                text = event.message.text

                if text == 's':

                    line_bot_api.reply_message(
                        event.reply_token,
                        get_participation_button()
                    )

                if text == '参加する':
                    print("参加表明がありました。")
                    print(event.source.user_id)

                if text == "rm":
                    get_richmenu()

                if text == "delete rm":
                    rmm = RichMenuManager(CHANNEL_ACCESS_TOKEN)
                    rmm.remove_all()

                post_text_to_db(event)

        if isinstance(event, PostbackEvent):

            data_str = event.postback.data
            data_dict = dict(urlparse.parse_qsl(data_str))
            try:
                next = data_dict['next']
            except:
                next = ''

            if next == 'get-participation':
                room_id = data_dict['room_id']
                print("次の参加表明者を待っています")
                rooms_dict = json.load(open('rooms.json', 'r'))
                rooms_dict[room_id]['members'].append(event.source.user_id)
                json.dump(rooms_dict, open('rooms.json', 'w'), indent=2)

            if next == 'close':
                room_id = data_dict['room_id']
                rooms_dict = json.load(open('rooms.json', 'r'))
                members = rooms_dict[room_id]['members']
                for member in members:
                    line_bot_api.push_message(
                        member,
                        TextSendMessage(text=f"ゲームID{room_id}に参加します")
                    )

            post_postback_to_db(event)

    return 'OK'


#######################################

# Below are templates functions

def get_participation_button():

    rooms_json = open('rooms.json', 'r')
    rooms_dict = json.load(rooms_json)

    rooms_dict.pop('1', None)  # only while testing

    room_count = get_room_count(rooms_dict)
    new_room_id = room_count + 1

    rooms_dict[str(new_room_id)] = {
        "members": [
            "U0a028f903127e2178bd789b4b4046ba7"
        ],
        "total_rounds": 6,
        "rounds_ended": [],
        "insider_order": [
            "U0a028f903127e2178bd789b4b4046ba7"
        ],
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

def choose_master():
    pass


# get template function end

###############################################

# Below are api using function


def get_geocode(address):
    params = {
        'address': 'つくば市 ' + address,
        'key': GEOCODING_APIKEY
    }
    s = requests.Session()
    r = s.get(GEOCODING_ENDPOINT, params=params)
    json_res = r.json()
    location = json_res['results'][0]['geometry']['location']

    location_str = str(location['lat']) + ',' + str(location['lng'])

    return location_str


def get_places_by_nearby_search(budget, transportation, location_geometry):
    radius = ''
    print(transportation)
    if transportation == '徒歩':
        radius = '700'
    elif transportation == '自転車':
        radius = '2000'
    elif transportation == '車':
        radius = '8000'

    params = {
        'key': PLACES_APIKEY,
        'keyword': 'レストラン OR カフェ OR 定食 OR バー',
        'location': location_geometry,
        'radius': radius,
        # 'maxprice': budget,
        # 'minprice': str(int(budget) - 1),
        'opennow': 'true',
        'rankby': 'prominence',
        'language': 'ja'
    }
    s = requests.Session()

    r = s.get(PLACES_NEARBYSEARCH_ENDPOINT, params=params)
    r.encoding = r.apparent_encoding
    json_result = r.json()
    # pprint.pprint(json_result)
    with open('place.json', mode='w', encoding='utf-8') as f:
        f.write(json.dumps(json_result, sort_keys=True, ensure_ascii=False, indent=2))
        print(json.dumps(json_result, sort_keys=True, ensure_ascii=False, indent=2))  # .encode('utf-8'))

    return json_result


def get_place_detail(place_id):
    params = {
        'key': PLACES_APIKEY,
        'placeid': place_id,
        'language': 'ja'
    }

    s = requests.Session()
    r = s.get(PLACES_DETAIL_ENDPOINT, params=params)
    json_result = r.json()

    return json_result


def get_place_photo_url(photo_ref):
    params = {
        'key': PLACES_APIKEY,
        'photoreference': photo_ref,
        'maxwidth': '400'
    }
    url = PLACES_PHOTO_ENDPOINT + '?' + urlparse.urlencode(params)

    return url


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
def get_richmenu():

    rmm = RichMenuManager(CHANNEL_ACCESS_TOKEN)

    rm_name_and_id = get_rm_name_and_id(rmm)
    menu_name_to_get = "Menu1"

    if menu_name_to_get in rm_name_and_id.keys():
        richmenu_id = rm_name_and_id[menu_name_to_get]
        print("found {}".format(menu_name_to_get))

    else:
        rm = RichMenu(name="Menu1", chat_bar_text="問い合わせカテゴリー", selected=True)
        rm.add_area(0, 0, 1250, 843, "message", "住所変更")
        rm.add_area(1250, 0, 1250, 843, "uri", "http://www.city.tsukuba.lg.jp/index.html")
        rm.add_area(0, 843, 1250, 843, "postback", "data1=from_richmenu&data2=as_postback")
        rm.add_area(1250, 843, 1250, 843, "postback", ["data3=from_richmenu_with&data4=message_text", "ポストバックのメッセージ"])

        # Register
        res = rmm.register(rm, "./menu_images/4x2.png")
        richmenu_id = res["richMenuId"]
        print("Registered as " + richmenu_id)

    # Apply to user
    user_id = "U0a028f903127e2178bd789b4b4046ba7"
    rmm.apply(user_id, richmenu_id)

    # Check
    res = rmm.get_applied_menu(user_id)
    print(user_id  + ":" + res["richMenuId"])


def get_richmenu2():

    rmm = RichMenuManager(CHANNEL_ACCESS_TOKEN)

    rm_name_and_id = get_rm_name_and_id(rmm)
    menu_name_to_get = "Menu2"

    if menu_name_to_get in rm_name_and_id.keys():
        richmenu_id = rm_name_and_id[menu_name_to_get]
        print("found {}".format(menu_name_to_get))

    else:
        rm = RichMenu(name=menu_name_to_get, chat_bar_text="住所変更", size_full=False)
        rm.add_area(0, 0, 625, 421, "message", "転出")
        rm.add_area(625, 0, 625, 421, "message", "転入（国内）")
        rm.add_area(1875, 422, 625, 421, "message", "戻る")
        rm.add_area(1250, 422, 625, 421, "message", "delete richmenu")

        # Register
        res = rmm.register(rm, "./menu_images/4x2.png")
        richmenu_id = res["richMenuId"]
        print("Registered as " + richmenu_id)

    # Apply to user
    user_id = "U0a028f903127e2178bd789b4b4046ba7"
    rmm.apply(user_id, richmenu_id)


def get_rm_name_and_id(rmm):

    rm_list = rmm.get_list()['richmenus']
    rm_name_and_id = {}
    rm_name_list = [rm['name'] for rm in rm_list]
    rm_richMenuId_list = [rm['richMenuId'] for rm in rm_list]

    for name, richMenuId in zip(rm_name_list, rm_richMenuId_list):
        rm_name_and_id[name] = richMenuId

    return rm_name_and_id

#####################################

# below are you utility functions
#####################################


def get_room_count(rooms_json):
    return len(rooms_json.keys())

def get_postback_data_dict(data):
    return dict(urlparse.parse_qsl(data))


#####################################
if __name__ == "__main__":
    # arg_parser = ArgumentParser(
    #     usage='Usage: python ' + __file__ + ' [--port <port>] [--help]'
    # )
    # arg_parser.add_argument('-p', '--port', default=port, help='port')
    # arg_parser.add_argument('-d', '--debug', default=False, help='debug')
    # options = arg_parser.parse_args()

    app.run(debug=True, port=port, host='0.0.0.0')
