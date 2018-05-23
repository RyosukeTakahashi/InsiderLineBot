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
func_mode = "production"

# debugging_tool = 'line-simulator'
debugging_tool = 'phone'

insider_guess_correct_point = 5
insider_guess_wrong_penalty = 5
insider_uncaught_score = 5
insider_caught_penalty = 5


if func_mode == "one_phone_dev":
    reminder_timings_setting = [2, 4]
    # reminder_timings_setting = [2, 32, 62]
    insider_guess_remind_interval = 10
    time_limit_when_word_guess_failed = 30

if func_mode == "multi_phone_dev":
    reminder_timings_setting = [2, 32, 62]
    insider_guess_remind_interval = 10
    time_limit_when_word_guess_failed = 30

if func_mode == "testing":
    reminder_timings_setting = [2, 92, 152, 182]
    insider_guess_remind_interval = 30
    time_limit_when_word_guess_failed = 30

if func_mode == "production":
    reminder_timings_setting = [2, 62, 122, 152, 182]
    insider_guess_remind_interval = 30
    time_limit_when_word_guess_failed = 30


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
    1: "https://i.imgur.com/Vt9aSgX.png",
    2: "https://i.imgur.com/fuE11V9.png",
    3: "https://i.imgur.com/PIV2ets.png",
    4: "https://i.imgur.com/dNXrlko.png",
    5: "https://i.imgur.com/vNiPXWz.png",
    6: "https://i.imgur.com/EuUiEV8.png",
    7: "https://i.imgur.com/t6wyq70.png",
    8: "https://i.imgur.com/iw3fRhT.png",
    9: "https://i.imgur.com/LCGM2TQ.png",
    10: "https://i.imgur.com/fuAxQyD.png",
}

rule = '''
ルール説明:

このゲームでは、プレイヤーは、各ラウンドで以下に別れます。

マスター：１人
インサイダー：１人、
庶民：それ以外

マスター＆インサイダーは、お題（一般的な名詞）を知っています。

各ラウンドで、3つのステップを実行します。

Step1:
庶民はマスターに質問をしながら、お題を当てにいきます。
なお、マスターは「はい」「いいえ」「わからない」しか答えられません。
ここで制限時間内にお題を当てられなかったら、全員負けです。

Step2:
実はプレーヤーの中に、庶民のフリをしながら、周りの誘導を試みた”インサイダー”がいます。
そのインサイダーが誰か議論します。

Step3:
インサイダーの容疑者を多数決で決めます。
庶民がインサイダーを当てたら、庶民の勝ち。
当てられなければ、インサイダーの勝ちです。
'''