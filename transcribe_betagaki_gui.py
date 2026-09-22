"""Japanese plain transcription GUI. Credentials stay in memory; no API calls on import."""

from __future__ import annotations

import os
from pathlib import Path
import queue
import shutil
import subprocess
import tempfile
import threading

MODELS = ("gpt-4o-transcribe", "gpt-4o-mini-transcribe")
PROMPT = "日本語の音声を、要約せず、発言者名とタイムスタンプを付けずに文字起こししてください。"


class Cancelled(Exception):
    pass


class UserError(Exception):
    pass


def check_cancel(stop):
    if stop.is_set():
        raise Cancelled()


def collect_inputs(selected: Path, batch: bool) -> list[Path]:
    selected = selected.expanduser().absolute()
    if batch:
        folder = selected if selected.is_dir() else selected.parent
        if not folder.is_dir():
            raise UserError("入力フォルダがありません。")
        files = sorted((p for p in folder.iterdir()
                        if p.is_file() and p.suffix.lower() == ".m4a"),
                       key=lambda p: p.name.casefold())
    else:
        files = [selected] if selected.is_file() and selected.suffix.lower() == ".m4a" else []
    if not files:
        raise UserError("処理対象のm4aファイルがありません。")
    return files


def split_audio(source: Path, destination: Path, seconds: int, stop) -> list[Path]:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise UserError("ffmpegが見つかりません。READMEの導入手順を確認してください。")
    command = [ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error", "-n",
               "-i", str(source), "-map", "0:a:0", "-vn", "-ac", "1", "-ar", "16000",
               "-c:a", "libmp3lame", "-b:a", "64k", "-f", "segment",
               "-segment_time", str(seconds), "-reset_timestamps", "1",
               str(destination / "chunk_%06d.mp3")]
    check_cancel(stop)
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                               creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
    try:
        while process.poll() is None:
            if stop.wait(0.1):
                raise Cancelled()
        check_cancel(stop)
        if process.returncode:
            raise UserError("音声の分割に失敗しました。音声形式・空き容量・ffmpegを確認してください。")
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    chunks = sorted(destination.glob("chunk_*.mp3"))
    if not chunks or any(p.stat().st_size == 0 or p.stat().st_size >= 24_000_000 for p in chunks):
        raise UserError("分割音声が空、または大きすぎます。分割秒数を短くしてください。")
    return chunks


def transcribe_file(source: Path, client, model: str, seconds: int, stop, report) -> Path:
    """Reserve a fresh output directory so a retry never overwrites existing text."""
    check_cancel(stop)
    if model not in MODELS or not 30 <= seconds <= 600:
        raise UserError("モデルまたは分割秒数が不正です。")
    output = source.with_suffix("")
    try:
        output.mkdir(mode=0o700, exist_ok=False)
    except FileExistsError:
        raise UserError("同名の出力フォルダが既にあります。退避または入力名を変更してください。") from None
    partial = output / f"{source.stem}.partial.txt"
    final = output / f"{source.stem}.txt"
    # TemporaryDirectory deletes only this run's chunks, even on API failure or cancellation.
    with tempfile.TemporaryDirectory(prefix="_chunks_", dir=output) as directory:
        chunks = split_audio(source, Path(directory), seconds, stop)
        with partial.open("x", encoding="utf-8", newline="\n") as result:
            for index, chunk in enumerate(chunks, 1):
                check_cancel(stop)
                report(f"分割音声 {index}/{len(chunks)} を処理中")
                with chunk.open("rb") as audio:
                    response = client.audio.transcriptions.create(
                        model=model, file=audio, language="ja", prompt=PROMPT,
                        response_format="json")
                if not isinstance(response.text, str):
                    raise UserError("APIの応答形式を確認できませんでした。")
                result.write(response.text.strip() + "\n")
                result.flush()
                os.fsync(result.fileno())
                check_cancel(stop)
    # Exclusive create also works on file systems without hard link support.
    try:
        with final.open("x", encoding="utf-8", newline="\n") as target:
            target.write(partial.read_text(encoding="utf-8"))
            target.flush()
            os.fsync(target.fileno())
    except Exception:
        # Keep partial on any failure; do not remove a possibly pre-existing final.
        raise
    partial.unlink()
    return final


def safe_error(error: Exception) -> str:
    """Never render raw SDK/HTTP exceptions: they may contain private request data."""
    if isinstance(error, UserError):
        return str(error)
    if isinstance(error, PermissionError):
        return "読み書きの権限がありません。"
    status = getattr(error, "status_code", None)
    if status in (401, 403):
        return "APIキーまたはモデルの利用権限を確認してください。"
    if status == 429:
        return "APIの利用上限または残高を確認し、時間をおいて再実行してください。"
    if isinstance(status, int):
        return f"APIエラー（HTTP {status}）。設定・サービス状況を確認してください。"
    return "処理に失敗しました。接続・依存ライブラリ・音声・空き容量を確認してください。"


def create_client(key):
    from openai import OpenAI
    # Explicit destination prevents OPENAI_BASE_URL from redirecting credentials/audio.
    return OpenAI(api_key=key, base_url="https://api.openai.com/v1", timeout=120.0, max_retries=0)


def main():
    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    root = tk.Tk()
    root.title("ベタ起こし — m4a文字起こし")
    root.minsize(650, 440)
    frame = ttk.Frame(root, padding=20)
    frame.pack(fill="both", expand=True)
    frame.columnconfigure(1, weight=1)
    key = tk.StringVar()
    selected = tk.StringVar()
    batch = tk.BooleanVar()
    model = tk.StringVar(value=MODELS[0])
    seconds = tk.StringVar(value="120")
    status = tk.StringVar(value="m4aファイルを選択してください。")
    events = queue.Queue()
    stop = threading.Event()
    running = False
    widgets = []

    def choose():
        path = (filedialog.askdirectory() if batch.get() else
                filedialog.askopenfilename(filetypes=[("m4a音声", "*.m4a *.M4A")]))
        if path:
            selected.set(path)

    ttk.Label(frame, text="APIキー（保存しません）").grid(row=0, column=0, sticky="w", pady=7)
    entry = ttk.Entry(frame, textvariable=key, show="*")
    entry.grid(row=0, column=1, columnspan=2, sticky="ew")
    widgets.append(entry)
    check = ttk.Checkbutton(frame, text="フォルダ内のm4aを一括処理（サブフォルダを除く）",
                            variable=batch, command=lambda: selected.set(""))
    check.grid(row=1, column=0, columnspan=3, sticky="w", pady=7)
    widgets.append(check)
    path_entry = ttk.Entry(frame, textvariable=selected)
    path_entry.grid(row=2, column=0, columnspan=2, sticky="ew")
    choose_button = ttk.Button(frame, text="選択…", command=choose)
    choose_button.grid(row=2, column=2, padx=(8, 0))
    widgets.extend([path_entry, choose_button])
    ttk.Label(frame, text="モデル").grid(row=3, column=0, sticky="w", pady=10)
    models = ttk.Combobox(frame, textvariable=model, values=MODELS, state="readonly")
    models.grid(row=3, column=1, columnspan=2, sticky="ew")
    widgets.append(models)
    ttk.Label(frame, text="分割秒数（30〜600）").grid(row=4, column=0, sticky="w", pady=7)
    spin = ttk.Spinbox(frame, from_=30, to=600, textvariable=seconds)
    spin.grid(row=4, column=1, columnspan=2, sticky="ew")
    widgets.append(spin)
    ttk.Label(frame, text="音声をOpenAI APIへ送信します。API利用料が発生します。\n"
              "結果は音声と同じ場所の同名フォルダに保存します。\n"
              "既存フォルダは上書きしません。", wraplength=610).grid(
                  row=5, column=0, columnspan=3, sticky="w", pady=14)

    def work(files, api_key, chosen_model, duration):
        success = failures = 0
        try:
            with create_client(api_key) as client:
                api_key = ""
                for index, source in enumerate(files, 1):
                    check_cancel(stop)
                    events.put(("status", f"ファイル {index}/{len(files)}"))
                    try:
                        transcribe_file(source, client, chosen_model, duration, stop,
                                        lambda text: events.put(("status", f"ファイル {index}/{len(files)}：{text}")))
                        success += 1
                    except Cancelled:
                        raise
                    except Exception as error:
                        failures += 1
                        events.put(("error", f"ファイル {index}：{safe_error(error)}"))
                        # A credential/quota failure would affect the whole batch.
                        if getattr(error, "status_code", None) in (401, 403, 429):
                            break
            events.put(("status", f"処理終了：成功 {success} / 失敗 {failures} / 未処理 {len(files)-success-failures}"))
        except Cancelled:
            events.put(("status", f"停止しました（成功 {success} / 失敗 {failures}）。途中結果はpartial.txtに残ります。"))
        except Exception as error:
            events.put(("error", safe_error(error)))
            events.put(("status", "処理を終了しました。エラーを確認してください。"))
        finally:
            api_key = ""
            events.put(("done", ""))

    def start():
        nonlocal running
        try:
            api_key = key.get().strip() or os.environ.get("OPENAI_API_KEY", "").strip()
            if not api_key:
                raise UserError("APIキーを入力してください。")
            if not selected.get().strip():
                raise UserError("入力を選択してください。")
            duration = int(seconds.get())
            if not 30 <= duration <= 600:
                raise ValueError()
            files = collect_inputs(Path(selected.get()), batch.get())
            if not shutil.which("ffmpeg"):
                raise UserError("ffmpegが見つかりません。READMEを確認してください。")
        except ValueError:
            messagebox.showerror("設定を確認", "分割秒数は30〜600の整数で指定してください。")
            return
        except Exception as error:
            messagebox.showerror("設定を確認", safe_error(error))
            return
        if not messagebox.askokcancel("送信確認", f"{len(files)}件の音声をOpenAI APIへ送信します。\nAPI利用料が発生します。開始しますか？"):
            return
        running = True
        stop.clear()
        key.set("")
        error_log.configure(state="normal")
        error_log.delete("1.0", "end")
        error_log.configure(state="disabled")
        for widget in widgets:
            widget.configure(state="disabled")
        start_button.configure(state="disabled")
        cancel_button.configure(state="normal")
        threading.Thread(target=work, args=(files, api_key, model.get(), duration), daemon=False).start()

    def cancel():
        stop.set()
        status.set("停止待ちです。送信済みのAPI応答を待っています（最大約120秒）。")
        cancel_button.configure(state="disabled")

    start_button = ttk.Button(frame, text="文字起こし開始", command=start)
    start_button.grid(row=6, column=0, sticky="w")
    cancel_button = ttk.Button(frame, text="停止", command=cancel, state="disabled")
    cancel_button.grid(row=6, column=2)
    ttk.Label(frame, textvariable=status, wraplength=610).grid(row=7, column=0, columnspan=3, sticky="w", pady=12)
    error_log = tk.Text(frame, height=5, width=65, state="disabled", wrap="word")
    error_log.grid(row=8, column=0, columnspan=3, sticky="nsew")
    frame.rowconfigure(8, weight=1)

    def poll():
        nonlocal running
        try:
            while True:
                kind, text = events.get_nowait()
                if kind == "status":
                    status.set(text)
                elif kind == "error":
                    error_log.configure(state="normal")
                    error_log.insert("end", text + "\n")
                    error_log.configure(state="disabled")
                elif kind == "done":
                    running = False
                    for widget in widgets:
                        widget.configure(state="normal")
                    models.configure(state="readonly")
                    start_button.configure(state="normal")
                    cancel_button.configure(state="disabled")
        except queue.Empty:
            pass
        root.after(100, poll)

    def close():
        if running:
            cancel()
            messagebox.showinfo("停止待ち", "処理停止後にもう一度ウィンドウを閉じてください。")
        else:
            key.set("")
            root.destroy()

    root.protocol("WM_DELETE_WINDOW", close)
    poll()
    root.mainloop()


if __name__ == "__main__":
    main()
