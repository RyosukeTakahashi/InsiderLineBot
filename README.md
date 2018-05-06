# タイトル

## 入力

## 出力


## 実装手段候補
- Heroku and Redis Queue
    - https://qiita.com/matsulib/items/d3ce4876f58d478406e9
    - https://github.com/matsulib/line-bot-timer
- [Celery](http://docs.celeryproject.org/en/latest/getting-started/first-steps-with-celery.html#running-the-celery-worker-server) with Heroku?
- Azure Function
    - https://qiita.com/yorifuji/items/7f892564958cf464a812
    - https://qiita.com/hat22/items/f7b2aec5211951dd7622
    - https://github.com/yokawasa/azure-functions-python-samples
    - https://www.buildinsider.net/pr/microsoft/azure/solution02
    - http://pierre3.hatenablog.com/entry/2017/09/29/165544




## 環境
Anaconda python3

候補

## 準備

`pip install -r requirements.txt`

あと適宜足りなかったら pip でインストール


### 環境変数の設定

#### IBM Cloudのアカウントを作成ログイン

[login url](https://idaas.iam.ibm.com/idaas/mtfim/sps/authsvc?PolicyId=urn:ibm:security:authentication:asf:basicldapuser)

#### リソースを設定
- python環境
    - create resource -> cloud foundry app -> python
- nosql db
    - catalog -> cloudant nosql db -> launch -> create database
- dbとのconnection作成
    - (your app overview) -> create connection

#### .envの準備
.env.sampleを.envにリネームし編集する。その際、各種APIを以下から取得

- API各種
    - https://developers.line.me/console/
    - https://developers.google.com/places/web-service/?hl=ja
    - https://developers.google.com/maps/documentation/geocoding/get-api-key?hl=ja
- Cloudant NoSQL DBに作ったdbの名前にする
    - DB_NAMEに設定する

#### ibm cloudに環境変数の設定をする

[cloudfoundry/cli download](https://github.com/cloudfoundry/cli/releases)

```bash
python generate_shell_script_for_set-env.py
sh set-env.sh
```
を実行すると、先程編集した.envを元に環境変数が設定できる。

### vcap-local.jsonの準備
- ibm_cloud(dashboard) -> Cloudant NoSQL DB -> show credentials　をみてコピペ

```json
{
 "services": ここに追記
}
```

### .gitignore を忘れない。

## 実行方法

ngrokを使う場合,
Win:`ngrok.exe http 8000`
Mac:`./ngrok http 8000`
webhook url をLineダッシュボードで設定して、
- https://xxxxxxxx.ngrok.io/line/callback

`python app.py`

## IBM Cloud へのPush

最初からGithubからのCIを設定した方がいい。
デフォルト設定でToolchainを作り、Git部分をGithubに変える(Existing repositoryを使う設定)。
Deploymentをトラックする設定にする。
SlackによるDeploy通知も作る。

## その他必要なこと。

- LINE Messaging APIを使うための諸準備。ググるべし。
    - 新規Botの場合、
        - Webhook使用
        - グループトーク機能On
        - 自動挨拶Offを忘れずに
- Google Place API, Google Map Geocoding APIを使うための準備。
    - Google Developer Consoleからプロジェクト作ったり、API有効化したり。

## 理解するのに必要であろう知識やスキル
- PCの基礎
- Python (+ Flask)
- エディタをそれなりに使える
- Webアプリケーションの基礎知識
    - post, get, port, html, css
        - 少しでいい。
- API, JSONの概念と、それを利用するスキル
- Git, Github, Continuous Integration の概念
- Bluemix(IBM Cloud), PaaSの概念。マニュアル読みながら使う。
- NoSQLの概念