import os
import shutil
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox
from urllib.request import urlopen
from io import BytesIO

try:
    from PIL import Image, ImageTk
except ImportError:
    print("Please install pillow: pip install pillow")
    sys.exit(1)


STATIONS = {
    "101": {
        "name": "上海动感101",
        "freq": "FM101.7",
        "url": "https://lhttp-hw.qtfm.cn/live/274/64k.mp3",
        # 你也可以换成本地文件路径，比如 r"D:\\radio\\101.png"
        "logo": "http://pic.qingting.fm/2014/0909/20140909123511693.jpg",
    },
    "103": {
        "name": "上海流行音乐 LoveRadio",
        "freq": "FM103.7",
        "url": "https://lhttp-hw.qtfm.cn/live/273/64k.mp3",
        # 你可以换成你自己找到的更清晰 logo
        "logo": "http://pic.qtfm.cn/2014/0909/20140909125130474.jpg",
    },
}


class RadioApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("收音机控制台")
        self.root.geometry("980x620")
        self.root.minsize(900, 560)

        self.ffplay_path = shutil.which("ffplay") or r"C:\Users\alex\AppData\Local\Microsoft\WinGet\Packages\Gyan.FFmpeg_Microsoft.Winget.Source_8wekyb3d8bbwe\ffmpeg-8.1-full_build\bin\ffplay.exe"
        if not self.ffplay_path:
            messagebox.showerror("错误", "没有找到 ffplay。请先安装 ffmpeg，并确保 ffplay 在 PATH 中。")
            root.destroy()
            return

        self.process: subprocess.Popen | None = None
        self.current_station_id: str | None = None
        self.current_logo_tk = None

        self.build_ui()
        self.bind_keys()
        self.select_station("101", auto_play=False)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def build_ui(self) -> None:
        self.root.configure(bg="#101216")

        outer = tk.Frame(self.root, bg="#101216")
        outer.pack(fill="both", expand=True, padx=16, pady=16)

        left = tk.Frame(outer, bg="#171a21", width=250)
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
        for station_id in ("101", "103"):
            station = STATIONS[station_id]
            text = f"{station_id}  {station['name']}\n{station['freq']}"
            btn = tk.Button(
                left,
                text=text,
                justify="left",
                anchor="w",
                wraplength=210,
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
            text="快捷键\n1 = 101\n2 = 103\n空格 = 播放/停止\nQ = 退出",
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

        self.name_label = tk.Label(
            header,
            textvariable=self.name_var,
            fg="white",
            bg="#101216",
            font=("Microsoft YaHei UI", 24, "bold"),
            anchor="w",
        )
        self.name_label.pack(fill="x", pady=(0, 6))

        self.freq_label = tk.Label(
            header,
            textvariable=self.freq_var,
            fg="#86a7ff",
            bg="#101216",
            font=("Consolas", 18, "bold"),
            anchor="w",
        )
        self.freq_label.pack(fill="x")

        self.status_label = tk.Label(
            header,
            textvariable=self.status_var,
            fg="#cdd5e0",
            bg="#101216",
            font=("Microsoft YaHei UI", 12),
            anchor="w",
        )
        self.status_label.pack(fill="x", pady=(8, 0))

        self.logo_frame = tk.Frame(right, bg="#0f1117", height=360, highlightthickness=1, highlightbackground="#2a3142")
        self.logo_frame.pack(fill="both", expand=True, pady=16)
        self.logo_frame.pack_propagate(False)

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

        self.info_label = tk.Label(
            controls,
            text="底层播放器：ffplay",
            fg="#94a0b8",
            bg="#101216",
            font=("Microsoft YaHei UI", 11),
        )
        self.info_label.pack(side="right")

    def bind_keys(self) -> None:
        self.root.bind("1", lambda e: self.select_station("101", auto_play=True))
        self.root.bind("2", lambda e: self.select_station("103", auto_play=True))
        self.root.bind("<space>", lambda e: self.toggle_play())
        self.root.bind("q", lambda e: self.on_close())
        self.root.bind("Q", lambda e: self.on_close())

    def select_station(self, station_id: str, auto_play: bool) -> None:
        if station_id not in STATIONS:
            return

        self.current_station_id = station_id
        station = STATIONS[station_id]

        self.name_var.set(station["name"])
        self.freq_var.set(station["freq"])
        self.root.title(f"📻 {station['name']} {station['freq']}")
        self.load_logo(station["logo"])

        for sid, btn in self.station_buttons.items():
            if sid == station_id:
                btn.configure(bg="#2d5cff")
            else:
                btn.configure(bg="#252935")

        if auto_play:
            self.play_current()
        else:
            self.status_var.set("已选择，未播放")

    def load_logo(self, logo_source: str) -> None:
        try:
            if logo_source.startswith(("http://", "https://")):
                with urlopen(logo_source, timeout=10) as resp:
                    raw = resp.read()
                image = Image.open(BytesIO(raw))
            else:
                image = Image.open(logo_source)

            image = image.convert("RGB")

            frame_w = max(self.logo_frame.winfo_width(), 600)
            frame_h = max(self.logo_frame.winfo_height(), 300)
            image.thumbnail((frame_w - 30, frame_h - 30))

            bg = Image.new("RGB", (frame_w, frame_h), "#0f1117")
            x = (frame_w - image.width) // 2
            y = (frame_h - image.height) // 2
            bg.paste(image, (x, y))

            self.current_logo_tk = ImageTk.PhotoImage(bg)
            self.logo_label.configure(image=self.current_logo_tk, text="")
        except Exception as e:
            self.current_logo_tk = None
            self.logo_label.configure(
                image="",
                text=f"Logo 加载失败\n{e}",
                fg="#ffb4b4",
            )

    def play_current(self) -> None:
        if not self.current_station_id:
            return

        station = STATIONS[self.current_station_id]
        self.stop_playback()

        creationflags = 0
        if os.name == "nt":
            creationflags = subprocess.CREATE_NO_WINDOW

        try:
            self.process = subprocess.Popen(
                [
                    self.ffplay_path,
                    "-nodisp",
                    "-autoexit",
                    "-loglevel",
                    "quiet",
                    station["url"],
                ],
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=creationflags,
            )
            self.status_var.set(f"正在播放：{station['name']} {station['freq']}")
        except Exception as e:
            self.process = None
            self.status_var.set(f"启动失败：{e}")
            messagebox.showerror("播放失败", str(e))

    def stop_playback(self) -> None:
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

    def on_close(self) -> None:
        self.stop_playback()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    app = RadioApp(root)
    if app.ffplay_path:
        root.mainloop()


if __name__ == "__main__":
    main()