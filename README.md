# IP Webcam Recorder

AndroidのIP Webcamが配信する映像と音声をPythonからFFmpegへ渡し、1時間単位のMKV（H.264/AAC）としてNFSに保存します。Pythonの外部パッケージは不要です。

## 準備

1. AndroidでIP Webcamの音声配信を有効にしてサーバーを起動します。端末の省電力設定も確認してください。
2. カメラのWeb画面で映像・音声のURLを確認します。初期値は `/video` と `/audio.wav` ですが、アプリの設定・バージョンに合わせて変更してください。
3. Docker EngineとComposeプラグインが動作するLinuxホストを用意します。DockerホストからカメラとNFSサーバーへ接続できる必要があります。
4. NFSv4のエクスポート先ディレクトリを事前作成し、Dockerホストからのアクセスと、`PUID:PGID`（初期値1000:1000）による書き込みを許可します。root squashを無効化する必要はありません。`NFS_EXPORT`にはNFSv4クライアントから見えるエクスポートパスを指定します。

WindowsのDocker DesktopではLinux VMからNFSへ到達できることが必要です。環境によってNFSマウントが利用できないため、常時録画はLinuxホストを推奨します。

## 起動

```sh
cp .env.example .env
# .envを編集してカメラURLとNFS接続先を設定
docker compose up -d --build
docker compose logs -f recorder
```

PowerShellで設定ファイルをコピーする場合は `Copy-Item .env.example .env` を使います。

停止は `docker compose down` です。通常の停止時はFFmpegへSIGINTを送り、ファイルを閉じるまで最大20秒待ちます。

NFSの設定を変更した場合、既存のDockerボリュームには反映されません。録画を停止して `docker compose down -v` を実行した後に起動し直してください。このコマンドはDockerのNFSボリューム定義を削除します。NFS上の録画ファイルは残ります。

## 設定

| 環境変数 | 初期値・用途 |
| --- | --- |
| VIDEO_URL | 必須。映像ストリームのURL |
| AUDIO_URL | 必須。音声ストリームのURL |
| NFS_SERVER | 必須。NFSサーバーのIPアドレス |
| NFS_EXPORT | 必須。NFSv4のエクスポートパス |
| PUID / PGID | 1000 / 1000。録画プロセスのUID/GID |
| TZ | Asia/Tokyo。ファイル名・ログのタイムゾーン |
| SEGMENT_SECONDS | 3600。分割秒数 |
| HTTP_TIMEOUT_SECONDS | 30。HTTP読み取りタイムアウト |
| RETRY_SECONDS | 10。切断・エラー後の再試行間隔 |
| MIN_FREE_MB | 1024。FFmpeg開始前に必要な空き容量（MiB） |

`.env`には認証情報を含められるため、アクセス権を制限してください。認証が必要な場合は `http://user:password@host:8080/video` の形式でURLに指定できます。特殊文字はURLエンコードしてください。FFmpegの生ログにはURLが含まれる可能性があるため出力を抑制し、Python側で終了コードと再試行を記録します。認証方式によってはURLへの埋め込みに対応しない場合があります。

## 録画の仕様

- 録画開始から約3600秒ごとに分割します。毎時00分に揃える動作ではありません。映像のフレームや音声パケットにより境界にわずかな誤差が生じます。
- ファイル名は `2026-10-21_12-34-56_<起動ごとのID>.mkv` 形式です。再接続時も別IDを付け、同名による上書きを避けます。
- 分割位置にキーフレームを作るため映像を再エンコードします。CPU使用量は解像度・FPSに依存します。
- 独立した映像・音声の入力に受信時刻を付け、音声の非同期リサンプリングで時刻のずれを補正します。端末やネットワーク由来の固定遅延まで完全に補正するものではありません。
- 映像と音声の両方を必須にしています。接続切断・FFmpeg終了時は両方を接続し直します。再接続までの欠落分は復元できず、最後のファイルは1時間未満になる場合があります。
- NFSはDockerが起動前にマウントするため、マウント失敗時にホストの通常ディレクトリへ録画することはありません。NFSサーバー不通時は `hard` マウントのI/Oが待機し、停止にも時間がかかることがあります。
- 録画はNFSへ直接書き込みます。ローカルへの一時保存・後送機能はありません。空き容量はFFmpeg起動前に確認しますが、録画中に満杯になれば書き込みエラーになります。自動削除は行わないため容量監視・保存期間管理は別途必要です。
- MKVは異常終了時の影響を抑えやすい形式ですが、強制停止・NFS障害時の最後のファイルについて完全性は保証できません。

FFmpegの分割オプションは[公式ドキュメント](https://ffmpeg.org/ffmpeg-formats.html#segment_002c-stream_005fsegment_002c-ssegment)に従っています。

## Dockerを使わずに起動

Python 3.10以降とFFmpeg（libx264/AAC対応）をインストールし、NFSをOS側でマウントします。`VIDEO_URL`、`AUDIO_URL`、`OUTPUT_DIR`などを環境変数に設定して `python recorder.py` を実行します。この場合 `.env` は自動読み込みしません。Linuxでの運用を想定しています。

## 確認

```sh
python -m unittest discover -s tests -v
docker compose --env-file .env.example config --quiet
```

実際のFFmpegで5秒のテスト映像・音声を2秒ごとの3ファイルに分割し、コーデックと長さを検証できます（カメラ・NFS不要）。

```sh
docker build -t ipwebcam-recorder:local .
docker run --rm -e PYTHONPATH=/app -v "${PWD}/tests:/tests:ro" ipwebcam-recorder:local python /tests/smoke_ffmpeg.py
```

実機確認では `SEGMENT_SECONDS=60` で数分動かし、NFS上に複数のファイルができ、映像・音声が再生できることを確認後に3600へ戻します。カメラの一時停止後に再接続されることも確認してください。
