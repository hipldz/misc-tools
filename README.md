# misc-tools

日常开发、语音输入和视频制作工具合集。各子项目独立安装、配置和运行，具体说明见对应 README。

## 项目导航

| 项目 | 用途 | 运行环境 | 文档 |
| --- | --- | --- | --- |
| [git-folder-dashboard](git-folder-dashboard/) | 扫描父目录下的 Git 仓库，统一查看改动、执行 Git 操作和导入导出工作区快照 | Python、Git；浏览器界面 | [中文](git-folder-dashboard/doc/README.zh-CN.md) · [English](git-folder-dashboard/README.md) |
| [html-edge-tts-video](html-edge-tts-video/) | 用 HTML 场景和旁白生成带字幕的视频，提供 Studio 编辑界面 | Python 3.11、项目管理的 Chromium Headless Shell 和 FFmpeg | [使用说明](html-edge-tts-video/README.md) |
| [qwen-asr-input](qwen-asr-input/) | 按住 `Ctrl+Win` 说话，松开后将 Qwen ASR 识别结果粘贴到原输入位置 | Ubuntu X11、Python 3.11+、麦克风、DashScope API Key | [使用说明](qwen-asr-input/README.md) |

## 如何开始

1. 选择需要的工具，进入对应子目录。
2. 按子项目 README 安装依赖，并准备所需的系统组件或凭据。
3. 从快速开始示例运行，再按需配置后台运行、反向代理或工程接入。

本仓库没有统一安装或启动命令。各 Python 子项目应分别使用虚拟环境安装依赖。

## 常用入口

以下命令均在对应子项目目录中执行，且假定已完成该项目的安装和配置：

| 项目 | 入口 | 默认地址或输出 |
| --- | --- | --- |
| Git Folder Dashboard | `python app.py` | `http://127.0.0.1:8765/` |
| HTML TTS Video | `python main.py studio` | `http://127.0.0.1:8765/` |
| Qwen ASR Input | `./qwen-asr-input run` | 将最终识别文本粘贴到录音前的输入位置 |

Git 面板和视频 Studio 的前台命令默认都使用 `8765` 端口，同时运行时请用 `--port` 为其中一个指定其他端口。视频工具的 `studio.sh` 后台脚本使用不同的默认端口和路径，详见其 README。

## 目录结构

```text
misc-tools/
├── README.md                 # 项目索引与公共说明
├── git-folder-dashboard/     # 多仓库 Git 面板
├── html-edge-tts-video/       # HTML 场景、TTS 与视频 Studio
└── qwen-asr-input/            # Linux 按键语音输入
```

各工具的生成文件和本地配置由子项目自行管理，例如虚拟环境、API 配置、语音录音和视频输出。文件位置、支持范围和使用限制均以对应 README 为准。
