import ctypes

# ✅ 放这里（最早执行）
try:
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except:
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except:
        pass

import os
import shutil
import subprocess
import sys
import threading
import queue
import tkinter as tk
from tkinter import messagebox
from urllib.request import urlopen
from io import BytesIO

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Please install pillow: pip install pillow")
    sys.exit(1)

import imageio_ffmpeg
import numpy as np
import re
from funasr import AutoModel


STATIONS = {
    "101.7": {
        "name": "上海动感101",
        "freq": "FM101.7",
        "url": "https://lhttp-hw.qtfm.cn/live/274/64k.mp3",
        "logo": "http://pic.qingting.fm/2014/0909/20140909123511693.jpg",
    },
    "103.7": {
        "name": "上海流行音乐 LoveRadio",
        "freq": "FM103.7",
        "url": "https://lhttp-hw.qtfm.cn/live/273/64k.mp3",
        "logo": "http://pic.qtfm.cn/2014/0909/20140909125130474.jpg",
    },
    "93.4": {
        "name": "上海新闻广播",
        "freq": "FM93.4",
        "url": "https://lhttp-hw.qtfm.cn/live/270/64k.mp3",
        "logo": "http://pic.qtfm.cn/2015/0202/20150202170847551.jpg",
    },
    "97.7": {
        "name": "第一财经广播",
        "freq": "FM97.7",
        "url": "https://lhttp-hw.qtfm.cn/live/276/64k.mp3",
        "logo": "http://pic.qtfm.cn/sso/48/1641438475219_mv9SoJP78.jpeg",
    },
    "105.7": {
        "name": "上海交通广播",
        "freq": "FM105.7",
        "url": "https://lhttp-hw.qtfm.cn/live/266/64k.mp3",
        "logo": "http://pic.qtfm.cn/sso/48/1641437453117_JxQnTn1vv.jpeg",
    },
}

class RadioApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("收音机控制台")
        self.root.geometry("1500x950")
        self.root.minsize(1300, 820)

        meipass = getattr(sys, "_MEIPASS", None)
        if meipass and os.path.isfile(os.path.join(meipass, "ffplay.exe")):
            self.ffplay_path = os.path.join(meipass, "ffplay.exe")
        else:
            self.ffplay_path = shutil.which("ffplay")
            if not self.ffplay_path:
                try:
                    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
                    self.ffplay_path = ffmpeg_exe.replace("\\ffmpeg", "\\ffplay").replace("/ffmpeg", "/ffplay")
                    if not os.path.isfile(self.ffplay_path):
                        self.ffplay_path = ffmpeg_exe
                except Exception:
                    self.ffplay_path = None

        if not self.ffplay_path:
            messagebox.showerror("错误", "没有找到 ffplay。请先安装 ffmpeg，并确保 ffplay 在 PATH 中。")
            root.destroy()
            return

        self.process: subprocess.Popen | None = None
        self.current_station_id: str | None = None
        self.current_logo_tk = None
        self.logo_redraw_job = None
        self.logo_ready = False
        self.logo_cache: dict[str, ImageTk.PhotoImage] = {}
        self.is_muted = False
        self.play_anim_job = None
        self._play_anim_idx = 0

        # ASR
        self.asr_model = None
        self.asr_thread: threading.Thread | None = None
        self.asr_q: queue.Queue = queue.Queue()
        self.asr_proc: subprocess.Popen | None = None
        self.asr_run_id = 0
        self.asr_running = False
        self.transcript_lines: list[str] = []
        self.asr_ready = False
        
        self.build_ui()
        self.bind_keys()

        self.current_station_id = "101.7"
        self.name_var.set(STATIONS["101.7"]["name"])
        self.freq_var.set(STATIONS["101.7"]["freq"])
        self.root.title(f"📻 {STATIONS['101.7']['name']} {STATIONS['101.7']['freq']}")
        self.status_var.set(f"正在播放：{STATIONS['101.7']['name']} {STATIONS['101.7']['freq']}")

        for sid, btn in self.station_buttons.items():
            if sid == "101.7":
                btn.configure(bg="#2d5cff")
            else:
                btn.configure(bg="#252935")

        self.root.after(100, self.play_current)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def on_logo_frame_configure(self, event) -> None:
        # 过滤掉初始化阶段那些很小的假尺寸
        if event.width < 200 or event.height < 150:
            return

        # 第一次拿到靠谱尺寸时，标记 ready
        self.logo_ready = True

        # 防抖，避免窗口布局过程里反复重绘
        if self.logo_redraw_job is not None:
            self.root.after_cancel(self.logo_redraw_job)

        self.logo_redraw_job = self.root.after(60, self.redraw_current_logo)


    def redraw_current_logo(self) -> None:
        self.logo_redraw_job = None
        if not self.current_station_id:
            return
        station = STATIONS[self.current_station_id]
        self.load_logo(station["logo"])

    def build_ui(self) -> None:
        self.root.configure(bg="#101216")

        outer = tk.Frame(self.root, bg="#101216")
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        left = tk.Frame(outer, bg="#171a21", width=270)
        left.pack(side="left", fill="y")
        left.pack_propagate(False)

        right = tk.Frame(outer, bg="#101216")
        right.pack(side="right", fill="both", expand=True, padx=(16, 0))

        title = tk.Label(
            left,
            text="📻 频道列表",
            fg="white",
            bg="#171a21",
            font=("Microsoft YaHei UI", 18, "bold"),
            anchor="w",
        )
        title.pack(fill="x", padx=14, pady=(14, 10))

        self.station_buttons: dict[str, tk.Button] = {}
        for station_id in STATIONS:
            station = STATIONS[station_id]
            text = f"{station['name']}\n{station['freq']}"
            btn = tk.Button(
                left,
                text=text,
                justify="left",
                anchor="w",
                wraplength=236,
                fg="white",
                bg="#252935",
                activeforeground="white",
                activebackground="#2d5cff",
                relief="flat",
                bd=0,
                padx=12,
                pady=12,
                font=("Microsoft YaHei UI", 12),
                command=lambda sid=station_id: self.select_station(sid, auto_play=True),
            )
            btn.pack(fill="x", padx=12, pady=8)
            self.station_buttons[station_id] = btn

        tips = tk.Label(
            left,
            text="快捷键\n↑↓ = 切换电台\n空格 = 播放/停止\nM = 静音\nQ = 退出",
            fg="#b8c0d0",
            bg="#171a21",
            justify="left",
            font=("Microsoft YaHei UI", 11),
        )
        tips.pack(side="bottom", anchor="w", padx=14, pady=16)

        header = tk.Frame(right, bg="#101216")
        header.pack(fill="x")

        self.name_var = tk.StringVar(value="未选择频道")
        self.freq_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="已停止")
        self.time_var = tk.StringVar(value="")

        header_left = tk.Frame(header, bg="#101216")
        header_left.pack(side="left", fill="both", expand=True)

        header_right = tk.Frame(header, bg="#101216")
        header_right.pack(side="right")

        self.clock_label = tk.Label(
            header_right,
            textvariable=self.time_var,
            fg="#7a8599",
            bg="#101216",
            font=("Consolas", 20, "bold"),
            anchor="e",
        )
        self.clock_label.pack()

        self._update_clock()

        self.name_label = tk.Label(
            header_left,
            textvariable=self.name_var,
            fg="white",
            bg="#101216",
            font=("Microsoft YaHei UI", 24, "bold"),
            anchor="w",
        )
        self.name_label.pack(fill="x", pady=(0, 6))

        self.freq_label = tk.Label(
            header_left,
            textvariable=self.freq_var,
            fg="#86a7ff",
            bg="#101216",
            font=("Consolas", 18, "bold"),
            anchor="w",
        )
        self.freq_label.pack(fill="x")

        self.status_label = tk.Label(
            header_left,
            textvariable=self.status_var,
            fg="#cdd5e0",
            bg="#101216",
            font=("Microsoft YaHei UI", 12),
            anchor="w",
            padx=2,
            pady=2,
        )
        self.status_label.pack(fill="x", pady=(8, 0))

        transcript_frame = tk.Frame(right, bg="#0f1117")
        transcript_frame.pack(fill="x", pady=(8, 0))

        self.transcript_text = tk.Text(
            transcript_frame,
            height=7,
            fg="#b8c0d0",
            bg="#0f1117",
            font=("Microsoft YaHei UI", 12),
            wrap="word",
            relief="flat",
            state="disabled",
            padx=4,
            pady=4,
            borderwidth=0,
            highlightthickness=0,
        )
        self.transcript_text.pack(fill="x")

        self.logo_frame = tk.Frame(right, bg="#0f1117", height=360, highlightthickness=1, highlightbackground="#2a3142")
        self.logo_frame.pack(fill="both", expand=True, pady=16)
        self.logo_frame.pack_propagate(False)
        self.logo_frame.bind("<Configure>", self.on_logo_frame_configure)

        self.logo_label = tk.Label(
            self.logo_frame,
            text="暂无 Logo",
            fg="#d7deeb",
            bg="#0f1117",
            font=("Microsoft YaHei UI", 18),
        )
        self.logo_label.pack(fill="both", expand=True)

        controls = tk.Frame(right, bg="#101216")
        controls.pack(fill="x")

        self.play_btn = tk.Button(
            controls,
            text="▶ 播放",
            command=self.play_current,
            bg="#2d5cff",
            fg="white",
            activebackground="#416dff",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.play_btn.pack(side="left")

        self.stop_btn = tk.Button(
            controls,
            text="■ 停止",
            command=self.stop_playback,
            bg="#303646",
            fg="white",
            activebackground="#40495e",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=18,
            pady=10,
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self.stop_btn.pack(side="left", padx=10)

        self.mute_btn = tk.Button(
            controls,
            text="🔊 静音",
            command=self.toggle_mute,
            bg="#303646",
            fg="white",
            activebackground="#40495e",
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=14,
            pady=10,
            font=("Microsoft YaHei UI", 11, "bold"),
        )
        self.mute_btn.pack(side="left", padx=(10, 0))

    def bind_keys(self) -> None:
        self.root.bind("1", lambda _: self.select_station("101.7", auto_play=True))
        self.root.bind("2", lambda _: self.select_station("103.7", auto_play=True))
        self.root.bind("<space>", lambda _: self.toggle_play())
        self.root.bind("<Up>", lambda _: self.cycle_station(-1))
        self.root.bind("<Down>", lambda _: self.cycle_station(1))
        self.root.bind("q", lambda _: self.on_close())
        self.root.bind("Q", lambda _: self.on_close())
        self.root.bind("m", lambda _: self.toggle_mute())
        self.root.bind("M", lambda _: self.toggle_mute())

        # 阻止空格传播到子控件
        for widget in (self.play_btn, self.stop_btn):
            widget.bind("<space>", lambda e: "break")

    def select_station(self, station_id: str, auto_play: bool) -> None:
        if station_id not in STATIONS:
            return

        self.current_station_id = station_id
        station = STATIONS[station_id]

        self.name_var.set(station["name"])
        self.freq_var.set(station["freq"])
        self.root.title(f"📻 {station['name']} {station['freq']}")

        for sid, btn in self.station_buttons.items():
            if sid == station_id:
                btn.configure(bg="#2d5cff")
            else:
                btn.configure(bg="#252935")

        # 只有在 logo 区域尺寸真正准备好后才加载
        if self.logo_ready:
            self.load_logo(station["logo"])

        if auto_play:
            self.play_current()
        else:
            self.status_var.set("已选择，未播放")

    def load_logo(self, logo_source: str) -> None:
        # 取缓存（仅取原始尺寸版本，不依赖 frame 大小）
        if logo_source in self.logo_cache:
            image = self.logo_cache[logo_source]
        else:
            try:
                if logo_source.startswith(("http://", "https://")):
                    with urlopen(logo_source, timeout=10) as resp:
                        raw = resp.read()
                    image = Image.open(BytesIO(raw))
                else:
                    image = Image.open(logo_source)
                self.logo_cache[logo_source] = image
            except Exception as e:
                self.logo_label.configure(
                    image="",
                    text=f"Logo 加载失败\n{e}",
                    fg="#ffb4b4",
                )
                return

        frame_w = self.logo_frame.winfo_width()
        frame_h = self.logo_frame.winfo_height()
        if frame_w < 200 or frame_h < 150:
            return

        # 用缓存的图片对象来绘制（每次重新缩放以适配当前窗口大小）
        image = self.logo_cache[logo_source].copy()
        image.thumbnail((frame_w - 40, frame_h - 40))

        bg = Image.new("RGB", (frame_w, frame_h), "#0f1117")
        x = (frame_w - image.width) // 2
        y = (frame_h - image.height) // 2
        bg.paste(image, (x, y))

        self.current_logo_tk = ImageTk.PhotoImage(bg)
        self.logo_label.configure(image=self.current_logo_tk, text="")

    def play_current(self) -> None:
        if not self.current_station_id:
            return

        station = STATIONS[self.current_station_id]
        self.stop_playback()

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        vol = 0 if self.is_muted else 100

        try:
            self.process = subprocess.Popen(
                [
                    self.ffplay_path,
                    "-nodisp",
                    "-loglevel",
                    "quiet",
                    "-volume",
                    str(vol),
                    station["url"],
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self._play_anim_idx = 0
            self.status_var.set(f"🔊 正在播放：{station['name']} {station['freq']}")
            self._play_anim_tick()
            self._start_asr(station["url"])
        except Exception as e:
            self.process = None
            self.status_var.set(f"启动失败：{e}")
            messagebox.showerror("播放失败", str(e))

    def stop_playback(self) -> None:
        if self.play_anim_job:
            self.root.after_cancel(self.play_anim_job)
            self.play_anim_job = None
        self._stop_asr()
        if not self.process:
            self.status_var.set("已停止")
            return

        try:
            if self.process.poll() is None:
                if self.process.stdin:
                    try:
                        self.process.stdin.write(b"q")
                        self.process.stdin.flush()
                    except Exception:
                        pass
                self.process.terminate()
                try:
                    self.process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    self.process.kill()
        finally:
            self.process = None
            self.status_var.set("已停止")

    def toggle_play(self) -> None:
        if self.process and self.process.poll() is None:
            self.stop_playback()
        else:
            self.play_current()

    def toggle_mute(self) -> None:
        self.is_muted = not self.is_muted
        self.mute_btn.configure(text="🔇 已静音" if self.is_muted else "🔊 静音")
        if self.process and self.process.poll() is None:
            self.play_current()

    def cycle_station(self, direction: int) -> None:
        """切换到上一个或下一个电台。direction: 1=下一个, -1=上一个"""
        station_ids = list(STATIONS.keys())
        if not self.current_station_id or self.current_station_id not in station_ids:
            next_id = station_ids[0]
        else:
            idx = station_ids.index(self.current_station_id)
            next_idx = (idx + direction) % len(station_ids)
            next_id = station_ids[next_idx]
        self.select_station(next_id, auto_play=True)

    def _update_clock(self) -> None:
        from datetime import datetime
        self.time_var.set(datetime.now().strftime("%H:%M:%S"))
        self.root.after(1000, self._update_clock)

    def _play_anim_tick(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        icons = ["🔊", "🔉", "🔈"]
        station = STATIONS[self.current_station_id]
        self.status_var.set(f"{icons[self._play_anim_idx]} 正在播放：{station['name']} {station['freq']}")
        self._play_anim_idx = (self._play_anim_idx + 1) % len(icons)
        self.play_anim_job = self.root.after(600, self._play_anim_tick)

    def _start_asr(self, url: str) -> None:
        """启动 ASR 后台线程，用独立的 FFmpeg 拉流做转写"""
        if self.asr_thread and self.asr_thread.is_alive():
            return
        self.asr_run_id += 1
        run_id = self.asr_run_id
        self.asr_running = True
        self.asr_ready = False
        local_q: queue.Queue = queue.Queue()
        self.asr_q = local_q
        # 仅首次加载模型时显示“ASR 加载中...”
        self.transcript_lines.clear()
        if self.asr_model is None:
            self._render_transcript(current_line="ASR 加载中...")
        else:
            self._render_transcript()
        self.asr_thread = threading.Thread(
            target=self._asr_loop,
            args=(url, local_q, run_id),
            daemon=True,
        )
        self.asr_thread.start()
        self.root.after(500, self._poll_asr)

    def _asr_loop(self, url: str, local_q: queue.Queue, run_id: int) -> None:
        """后台线程：FFmpeg 拉流 -> 积累音频 -> FunASR 推理 -> 结果放入队列"""
        ffmpeg_path = re.sub(r"[Ff][Ff]play(\.exe)?$", lambda m: "ffmpeg" + (m.group(1) or ""), self.ffplay_path, count=0, flags=re.IGNORECASE)

        # 懒加载模型
        if self.asr_model is None:
            try:
                self.asr_model = AutoModel(
                    model="iic/SenseVoiceSmall",
                    device="cpu",
                    disable_update=True,
                )
                local_q.put(("status", "ASR 已就绪（CPU）"))
                self.asr_ready = True
            except Exception:
                local_q.put(("status", "ASR 初始化失败"))
                return
        proc = subprocess.Popen(
            [
                ffmpeg_path,
                "-v", "quiet",
                "-i", url,
                "-ar", "16000", "-ac", "1", "-f", "s16le", "-"
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        self.asr_proc = proc

        buf = b""
        chunk_size = 16000 * 2  # 1 second (16kHz, s16le, mono)
        while self.asr_running and run_id == self.asr_run_id:
            try:
                data = proc.stdout.read(chunk_size)
                if not data:
                    break
                buf += data
                if len(buf) >= chunk_size * 2:  # 积累够2秒再处理
                    audio = np.frombuffer(buf[:chunk_size * 2], dtype=np.int16).astype(np.float32) / 32768.0
                    buf = buf[chunk_size * 2:]  # 完全丢弃已处理的，不重叠
                    try:
                        result = self.asr_model.generate(audio, return_raw_text=True, disable_pbar=True)
                        text = result[0].get("text", "") if result else ""
                        # 跳过日/韩/粤标签片段
                        if any(tag in text for tag in ("<|ja|>", "<|ko|>", "<|yue|>")):
                            continue
                        # 跳过含日韩字符比例高的片段
                        ja_chars = sum(1 for c in text if '\u3040' <= c <= '\u309f' or '\u30a0' <= c <= '\u30ff')
                        ko_chars = sum(1 for c in text if '\uac00' <= c <= '\ud7af' or '\u1100' <= c <= '\u11ff')
                        if len(text) > 0 and (ja_chars + ko_chars) / len(text) > 0.3:
                            continue
                        # 去掉语言标签，保留中文和英文内容
                        text = text.replace("<|zh|>", "").replace("<|en|>", "")
                        text = re.sub(r"<\|[^|]+\|>", "", text).strip()
                        if text:
                            local_q.put(("text", text))
                    except Exception:
                        pass
            except Exception:
                break
        try:
            proc.terminate()
            proc.wait(timeout=1)
        except Exception:
            try:
                proc.kill()
            except Exception:
                pass
        finally:
            if self.asr_proc is proc:
                self.asr_proc = None

    def _render_transcript(self, current_line: str = "") -> None:
        """固定渲染7行：普通滚动文本，不做行语义绑定与高亮。"""
        if self.transcript_lines:
            display_lines = list(self.transcript_lines[-7:])
        elif current_line:
            display_lines = [current_line]
        else:
            display_lines = []

        display_lines += [""] * (7 - len(display_lines))

        self.transcript_text.config(state="normal")
        self.transcript_text.delete("1.0", "end")
        for line in display_lines:
            self.transcript_text.insert("end", line + "\n")
        self.transcript_text.see("1.0")
        self.transcript_text.config(state="disabled")

    def _poll_asr(self) -> None:
        """主线程轮询 ASR 结果，保持7行滚动显示"""
        try:
            while True:
                kind, text = self.asr_q.get_nowait()
                if kind == "status":
                    # 状态仅在尚未出现转写文本前占位显示
                    if not self.transcript_lines:
                        self._render_transcript(current_line=text)
                    continue
                if self.transcript_lines and text == self.transcript_lines[-1]:
                    continue
                self.transcript_lines.append(text)
                if len(self.transcript_lines) > 20:
                    self.transcript_lines.pop(0)
                self._render_transcript()
        except queue.Empty:
            pass
        if self.asr_running and self.asr_thread and self.asr_thread.is_alive():
            self.root.after(500, self._poll_asr)

    def _stop_asr(self) -> None:
        self.asr_run_id += 1
        self.asr_running = False
        self.asr_ready = False
        proc = self.asr_proc
        self.asr_proc = None
        if proc and proc.poll() is None:
            try:
                proc.terminate()
            except Exception:
                pass
        self.asr_thread = None
        self.transcript_lines.clear()
        self._render_transcript()

    def on_close(self) -> None:
        self.stop_playback()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    
    # ✅ 控制缩放（可调）
    root.tk.call('tk', 'scaling', 2.0)

    app = RadioApp(root)
    if app.ffplay_path:
        root.mainloop()


if __name__ == "__main__":
    main()