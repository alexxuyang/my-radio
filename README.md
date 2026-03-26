# My Radio

上海电台收音机，支持 5 个频道、快捷键、静音。

![界面截图](https://raw.githubusercontent.com/alexxuyang/my-radio/main/resources/screen.png)

## 电台

| 频率 | 名称 |
|------|------|
| FM101.7 | 上海动感101 |
| FM103.7 | 上海流行音乐 LoveRadio |
| FM93.4 | 上海新闻广播 |
| FM97.7 | 第一财经广播 |
| FM105.7 | 上海交通广播 |

## 依赖

- **Python 3.10+**
- **FFmpeg**（包含 ffplay）

  必须确保 `ffplay` 可用，程序会按以下顺序查找：

  1. `PATH` 中的 `ffplay`
  2. `C:\Users\<用户名>\AppData\Local\Microsoft\WinGet\Packages\...\ffplay.exe`（WinGet 安装的 Gyan.FFmpeg）
  3. `C:\Program Files\ffmpeg\bin\ffplay.exe`
  4. `C:\ffmpeg\bin\ffplay.exe`

  将 FFmpeg 加入 PATH 后最省事：
  ```
  控制面板 → 系统 → 环境变量 → 编辑 PATH → 添加 FFmpeg bin 目录
  ```

## 安装运行

```bash
# 安装依赖
uv sync

# 运行
uv run python main.py
```

## 快捷键

| 按键 | 功能 |
|------|------|
| ↑ / ↓ | 切换上/下一个电台 |
| 空格 | 播放 / 停止 |
| M | 静音 / 取消静音 |
| Q | 退出 |

## 下载

直接下载 exe 运行，无需安装任何东西：

- **[my-radio-with-ffmpeg-1.0.0.exe](https://github.com/alexxuyang/my-radio/releases/download/1.0.0/my-radio-with-ffmpeg-1.0.0.exe)** — 带 FFmpeg，推荐下载 (291MB)
- **[my-radio-1.0.0.exe](https://github.com/alexxuyang/my-radio/releases/download/1.0.0/my-radio-1.0.0.exe)** — 不带 FFmpeg，需系统已安装 FFmpeg (47MB)

## 打包

**带 FFmpeg：**
```bash
uv run pyinstaller --noconfirm --clean --onefile --windowed --add-binary "ffmpeg\\bin;." --name my-radio main.py
```

**不带 FFmpeg：**
```bash
uv run pyinstaller --noconfirm --clean --onefile --windowed --name my-radio main.py
```
