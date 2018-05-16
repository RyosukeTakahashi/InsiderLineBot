import os
from dotenv import load_dotenv
import json
import sys
from linebot import LineBotApi, WebhookParser
from cloudant import Cloudant
import redis

# https://insider-bot.mybluemix.net/

# to change setting easily
# func_mode = "one_phone_dev"
# func_mode = "multi_phone_dev"
# func_mode = "testing"
func_mode= "production"

# debugging_tool = 'line-simulator'
debugging_tool = 'phone'

insider_guess_correct_point = 5
insider_guess_wrong_penalty = 0
insider_uncaught_score = 5
insider_caught_penalty = 5


if func_mode == "one_phone_dev":
    # reminder_timings_setting = [2, 4]
    reminder_timings_setting = [2, 32, 62]
    remind_interval = 5
    time_limit = 30

if func_mode == "multi_phone_dev":
    reminder_timings_setting = [2, 32, 62]
    remind_interval = 10
    time_limit = 30

if func_mode == "testing":
    reminder_timings_setting = [2, 92, 152, 182]
    remind_interval = 30
    time_limit = 30

if func_mode == "production":
    reminder_timings_setting = [2, 92, 152, 182]
    remind_interval = 10
    time_limit = 30


if os.path.isfile('.env') or os.path.isfile('env'):
    print('found .env. So it should be a local environment.')
    ENV = load_dotenv('.env')
    if ENV is None:
        ENV = load_dotenv('env')
else:
    print('Cannot find .env. So it should be on the cloud.')

CHANNEL_SECRET = os.getenv('CHANNEL_SECRET')
CHANNEL_ACCESS_TOKEN = os.getenv('CHANNEL_ACCESS_TOKEN')
DB_NAME = os.getenv('DB_NAME')
print(CHANNEL_SECRET)
parser = WebhookParser(CHANNEL_SECRET)

if CHANNEL_SECRET is None:
    print('Specify LINE_CHANNEL_SECRET as environment variable.')
    sys.exit(1)
if CHANNEL_ACCESS_TOKEN is None:
    print('Specify LINE_CHANNEL_ACCESS_TOKEN as environment variable.')
    sys.exit(1)

if debugging_tool == 'phone':
    line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN)
else:
    line_bot_api = LineBotApi(CHANNEL_ACCESS_TOKEN, "http://localhost:8080/bot")

cloundant_creds = {}

if 'VCAP_SERVICES' in os.environ:
    vcap = json.loads(os.getenv('VCAP_SERVICES'))
    print('Found VCAP_SERVICES')
    if 'cloudantNoSQLDB' in vcap:
        print("cloundantNoSQLDB is found")
        cloundant_creds = vcap['cloudantNoSQLDB'][0]['credentials']
        redis_creds = vcap['rediscloud'][0]['credentials']
        r = redis.Redis(
            host=redis_creds['hostname'],
            password=redis_creds['password'],
            port=redis_creds['port']
        )


elif os.path.isfile('vcap-services.json'):
    with open('vcap-services.json') as f:
        vcap = json.load(f)
        print('Found local VCAP_SERVICES')
        cloundant_creds = vcap['cloudantNoSQLDB'][0]['credentials']
        r = redis.from_url("redis://localhost:6379")

        print("created local redis connection")

user = cloundant_creds['username']
password = cloundant_creds['password']
url = 'https://' + cloundant_creds['host']
client = Cloudant(user, password, url=url, connect=True)
db = client.create_database(DB_NAME, throw_on_exists=False)
port = int(os.getenv('PORT', 8000))


round_img = {
    1: "https://i.imgur.com/MB1Q5c4.png",
    2: "https://i.imgur.com/RtwlJ5L.png",
    3: "https://i.imgur.com/Le2vruB.png",
    4: "https://i.imgur.com/Mn70yxs.png",
    5: "https://i.imgur.com/tBtEZyv.png",
}

rule = '''
ルール説明をします。

このゲームでは、プレイヤーは、各ラウンドで、

マスター：１人
インサイダー：１人、
庶民：それ以外

にランダムで別れます。
その際、マスターとインサイダーは、お題の単語をランダムで通知されます。

そして、以下の3つのステップを行います。

Step1:
庶民はマスターに質問をしながら、お題を当てにいきます。
お題は、一般的な名詞です。（椅子、テーブル、スマートフォン、野球、などなど）
なお、マスターは「はい」「いいえ」「わからない」しか答えることができないので、それを踏まえ質問しましょう。
ここでお題を当てられなかったら、全員が負けです。

Step2:
お題を正解できたとしても、実はプレーヤーの中に、お題を知りながらも、知らないをフリをしながら、
周りをお題に狡猾に誘導しようとした”インサイダー”がいます。
今度はをそのインサイダー見つけます。
インサイダーは、インサイダーが自分だと悟られないように、周りの議論を誘導しましょう。

Step3:
インサイダーと疑われる人を多数決で決めます。
庶民がインサイダーをが見つけられたら、庶民の勝ちです。
庶民がインサイダー以外を疑ってしまったら、インサイダーの勝ちです。

==================

プレイ人数：
4~8人

プレイ時間：
5ラウンドで30分程度。

操作：

1.
参加者が入ったルームで、「す」と入力し、参加ボタンを表示する 

2.
参加するを押す。参加者の参加受付が確認できたら、参加を締め切るを押す。

3.
あとは、アカウントから来る指示に従ってください。


'''