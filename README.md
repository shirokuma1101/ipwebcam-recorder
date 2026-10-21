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
| FILENAME_PREFIX | 省略時は空。ファイル名の先頭に付けるカメラ名（例: ipcam01）。半角英数字・`_`・`-`のみ使用可能 |
| SEGMENT_SECONDS | 3600。時計に合わせた分割間隔（秒）。3600なら毎時00分、60なら毎分00秒 |
| HTTP_TIMEOUT_SECONDS | 30。HTTP読み取りタイムアウト |
| RETRY_SECONDS | 10。切断・エラー後の再試行間隔 |
| MIN_FREE_MB | 1024。FFmpeg開始前に必要な空き容量（MiB） |

`.env`には認証情報を含められるため、アクセス権を制限してください。認証が必要な場合は `http://user:password@host:8080/video` の形式でURLに指定できます。特殊文字はURLエンコードしてください。FFmpegの生ログにはURLが含まれる可能性があるため出力を抑制し、Python側で終了コードと再試行を記録します。認証方式によってはURLへの埋め込みに対応しない場合があります。

## 録画の仕様

- `TZ`で指定したタイムゾーンの時計に合わせ、初期設定では毎時00分に分割します。例: 12:34に起動すると最初は12:34〜13:00、以降は13:00〜14:00、14:00〜15:00となります。再接続後も次の毎時00分で分割します。ホストの時刻を正しく同期してください。
- 分割は境界後のキーフレームで行います。1秒ごとにキーフレームを作成しているため、正常なリアルタイム入力では境界に約1秒以内と処理・入出力の遅延が加わる場合があります。ファイル名は実際のファイル作成時刻です。
- `.env`で `FILENAME_PREFIX=ipcam01` を設定すると、ファイル名は `ipcam01_2026-09-17_04-00-04_<起動ごとのID>.mkv` 形式になります。Prefixと日時の間の `_` は自動で追加します。省略・空文字の場合は日時から始まります。再接続時も別IDを付け、同名による上書きを避けます。設定変更後は `docker compose up -d --build` で反映してください。
- 時計の境界付近で分割できるよう映像を再エンコードし、低遅延設定を使用します。CPU使用量・ファイルサイズは解像度・FPSに依存します。
- 映像には受信時刻を付け、音声にはサンプル数に基づく連続した時刻を使用します。音声のHTTP受信間隔の揺れを理由に無音を挿入したり音声を削除したりしません。独立した映像・音声入力の固定遅延や長時間のクロック差は自動補正しません。
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

実際のFFmpegで5秒のテスト映像・音声を時計の2秒境界で分割し、コーデック・長さ・音声の連続性を検証できます（カメラ・NFS不要）。音声入力のタイムスタンプを意図的に揺らし、復号後の音声に無音区間がないことを確認します。開始時刻により最初と最後の長さ・ファイル数が変わります。

```sh
docker build -t ipwebcam-recorder:local .
docker run --rm -e PYTHONPATH=/app -v "${PWD}/tests:/tests:ro" ipwebcam-recorder:local python /tests/smoke_ffmpeg.py
```

実機確認では `SEGMENT_SECONDS=60` で数分動かし、NFS上に複数のファイルができ、映像・音声が再生できることを確認後に3600へ戻します。カメラの一時停止後に再接続されることも確認してください。
