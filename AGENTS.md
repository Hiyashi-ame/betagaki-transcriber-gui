# Codex保守ガイド

## 目的と変更の単位

Python/Tkinterの日本語m4a文字起こしGUIをWindows/macOSで維持する。
Issueの受入条件を確認し、1課題につき1ブランチ・1PRで修正する。
依存関係更新時は公式API仕様とPython対応版を確認し、READMEも更新する。

## 守ること

- APIキー、実音声、文字起こし結果、個人データをコミット・Issue・ログ・スクリーンショットに含めない。
- APIキーをユーザーにチャットで送らせない。実API試験は明示的な許可と権利のある試験音声があるときのみ。
- 通常テストはAPIモックと一時領域に生成する人工音声で行う。実音声をfixtureにしない。
- Tkinter操作はメインスレッド。ffmpeg/API処理はワーカー。
- 出力の上書き防止、partial保存、一時音声掃除を維持する。
- SDKの生の例外文字列やレスポンスを画面・ログに出さない。
- `.gitignore`と`scripts/check_publication.py`の許可リストは新しいソースを追加するときに両方更新する。

## 検証

```bash
python -m unittest discover -s tests -v
python scripts/check_publication.py
```

GUI変更時は手動操作の結果をPRに記録する。実行できないOSの確認を済んだと書かない。
公開チェックは秘密文字列の完全検出を保証しない。差分・追跡対象・履歴を確認する。

## 引継ぎ

`docs/issues/`の原稿はGitHub Issueに転記できる独立したタスク。
各Issueの背景・対象・受入条件を完了させ、変更点・検証・残課題をPRに記載する。
