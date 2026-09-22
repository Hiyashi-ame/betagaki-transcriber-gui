# 新規GitHubリポジトリへの公開

## 決定済み

- 新規リポジトリとして準備する
- MIT Licenseを採用する
- 候補名：`betagaki-transcriber-gui`

## 公開時に確定する情報

- 所有者（個人アカウントまたは組織）
- 正式なリポジトリ名
- 公開タイミング：非公開で両OSの操作確認を行うか、公開準備版として公開するか

2026-09-22に公開リポジトリを作成しました。
公開先：https://github.com/Hiyashi-ame/betagaki-transcriber-gui
GitHub Issueは未作成です。以下の初回登録手順は新規公開時の参考として残しています。
Issue原稿は`docs/issues/`にあります。

## アップロード前

1. このフォルダだけを新規リポジトリにする。親のChatGPTプロジェクトや添付を登録しない。
2. 音声・キー・結果はリポジトリ外で管理する。
3. READMEのテストと公開チェックを実行する。
4. `docs/issues/02-platform-smoke-tests.md`を実施する。未実施で公開する場合はREADMEの公開準備版表記を残す。
5. 差分を目視確認する。自動チェックは任意の個人情報まで判定できない。

## 初回登録

このREADMEのあるリポジトリ用フォルダの中で実行する。

```bash
git init -b main
python scripts/check_publication.py
git add README.md LICENSE .gitignore .gitattributes requirements.txt transcribe_betagaki_gui.py start_gui_windows.bat start_gui_mac.command AGENTS.md tests scripts docs .github
git update-index --chmod=+x start_gui_mac.command
git diff --cached --stat
git diff --cached
python scripts/check_publication.py
git commit -m "Prepare transcription GUI for publication"
python scripts/check_publication.py
```

GitHubで確認済みの所有者・名前・公開範囲の空リポジトリを作成する。
そのURLを`git remote add origin`に指定し、`git push -u origin main`で登録する。
GitHub側でREADMEを自動生成せず、空のリポジトリを使う。

## 公開後

- Actionsの結果を確認し、検証状況を更新する。
- `docs/issues/`の原稿をタイトル・本文としてIssue化する。重複があれば追加しない。
- Codexに対象リポジトリとIssueを指定し、AGENTS.mdの手順で保守する。
- topic候補：`python`, `tkinter`, `transcription`, `speech-to-text`, `openai-api`
- PRごとにテストと公開チェックを実施する。

機密データを検出した場合はpushを止め、追跡対象と履歴から除く。
`.gitignore`は既存履歴を削除しない。公開済みの実キーはまず失効・再発行する。
