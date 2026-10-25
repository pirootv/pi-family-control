# Raspberry Pi ファミリー制御

## 構成
- `site/`: Netlifyで公開する管理サイト
- `netlify/functions/api.js`: ログイン、設定、Gist API、使用履歴API
- `raspberry-pi/pi_guard.py`: Raspberry Pi OS Desktop用のTkinter制限画面

## 重要な注意
管理サイトからのロック/解除、曜日別時間帯、日使用上限、今日の延長、使用履歴に加えて、Piのロック画面から管理パスワードを入力して5/15/30/60/120/180分の一時解除ができます。一時解除期限はGistに保存され、期限後に通常の制限へ戻ります。旧形式の平文パスワードは正しく入力された際にPBKDF2形式へ自動移行します。新しい設定はPBKDF2で保存します。Tkinterの全画面表示だけではOSショートカット等による回避を完全には防げません。家族用の補助機能であり、強固なペアレンタルコントロールではありません。ネット接続断時は安全側としてロックします。使用履歴は動作中のエージェントが報告できた時間だけです。

## Gist
Gist ID: `5c56ef1a0541a164158faef9d54d1b0d`
ファイル名が正確に `config.json` であることを確認してください。指定Gistの現在の初期JSONを使用できます。GistをSecretにすることを推奨します。管理パスワードはPBKDF2ハッシュで保存します。

## Netlifyへの配置
1. ZIPを展開し、フォルダ内のファイルをGitHubリポジトリにpushします。
2. Netlifyで「Add new site」→「Import an existing project」からリポジトリを選択します。
3. `netlify.toml` を使うため、publish directoryは `site`、functions directoryは `netlify/functions`。Build commandは空欄でOKです。
4. Netlify Site configuration → Environment variablesに以下を設定:
   - `GITHUB_TOKEN`: Gistの読み書きができるGitHubトークン（fine-grained tokenの場合はGistsの読み書き権限）
   - `GIST_ID`: `5c56ef1a0541a164158faef9d54d1b0d`
   - `SESSION_SECRET`: 32バイト以上のランダムな秘密値
   - `DEVICE_TOKEN`: ラズパイ用のランダムな秘密値
5. 例: `openssl rand -hex 32` でランダム値を作れます。環境変数設定後に再デプロイします。
6. 公開サイトを開き、10文字以上の初回管理パスワードを設定します。GitHubトークンをサイトのJSに書かないでください。

## Raspberry Pi 5 / Raspberry Pi OS Desktop
ターミナルで:
```bash
sudo apt update
sudo apt install -y python3-tk
mkdir -p ~/pi-family-control
```
`raspberry-pi/pi_guard.py` を `~/pi-family-control/pi_guard.py` にコピーします。環境変数ファイルを作ります:
```bash
sudo install -m 600 /dev/null /etc/pi-family-control.env
sudo nano /etc/pi-family-control.env
```
以下を入力し、URLとトークンを置き換えます:
```bash
PI_CONTROL_URL=https://YOUR-SITE-NAME.netlify.app
PI_DEVICE_TOKEN=NetlifyのDEVICE_TOKENと同じ値
```
手動起動:
```bash
set -a
source /etc/pi-family-control.env
set +a
python3 ~/pi-family-control/pi_guard.py
```
デスクトップの自動起動を設定:
```bash
mkdir -p ~/.config/autostart
nano ~/.config/autostart/pi-family-control.desktop
```
以下を入力。`YOUR_USER` は実際のLinuxユーザー名に変更:
```ini
[Desktop Entry]
Type=Application
Name=Pi Family Control
Exec=sh -lc 'set -a; . /etc/pi-family-control.env; set +a; python3 /home/YOUR_USER/pi-family-control/pi_guard.py'
Terminal=false
X-GNOME-Autostart-enabled=true
```
再起動前に、サイト側で時間割を無効・上限無制限にして接続テストしてください。

## テスト
1. 初回パスワード設定
2. サイトの「今すぐロック」→ 10〜20秒待つ → Piに全画面表示
3. サイトの「ロック解除」→ 10〜20秒待つ → Pi画面が消える
4. 短い時間帯や使用上限を設定してテスト
5. テスト終了後に本来の設定へ戻す

## トラブルシューティング
- 500エラー: Netlify環境変数、Gist ID、トークン権限、`config.json`を確認
- Gist API 403: Netlifyの`GITHUB_TOKEN`が期限切れでないこと、対象Gistへの読み書き権限があることを確認して再デプロイ
- 401 device: PiとNetlifyのDEVICE_TOKEN一致を確認
- Tkinterエラー: `sudo apt install python3-tk`
- Piがロック状態: サイト設定、ネット接続、日時、タイムゾーンを確認
