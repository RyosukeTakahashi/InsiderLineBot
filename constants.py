import os
from dotenv import load_dotenv
import json
import sys
from linebot import LineBotApi, WebhookParser
from cloudant import Cloudant
import redis

# https://insider-bot.mybluemix.net/

# to change setting easily
func_mode = "one_phone_dev"
# func_mode = "multi_phone_dev"
# func_mode = "testing"
# func_mode s= "production"

# debugging_tool = 'line-simulator'
debugging_tool = 'phone'


if func_mode == "one_phone_dev":
    reminder_timings_setting = [3, 6, 9]
    reminder_timings_setting = [2, 32, 62]
    sleep_time = 3

if func_mode == "multi_phone_dev":
    reminder_timings_setting = [3, 6, 9]
    sleep_time = 3

if func_mode == "testing":
    reminder_timings_setting = [2, 92, 152, 182]
    sleep_time = 90

if func_mode == "production":
    reminder_timings_setting = [2, 92, 152, 182]
    sleep_time = 90


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
        # redis_creds = vcap['rediscloud'][0]['credentials']
        # r = redis.Redis(
        #     host=redis_creds['hostname'],
        #     password=redis_creds['password'],
        #     port=redis_creds['port']
        # )

        print("created cloud redis connection")

user = cloundant_creds['username']
password = cloundant_creds['password']
url = 'https://' + cloundant_creds['host']
client = Cloudant(user, password, url=url, connect=True)
db = client.create_database(DB_NAME, throw_on_exists=False)
port = int(os.getenv('PORT', 8000))
