# Git Folder Dashboard

[工具合集](../../README.md) · [English](../README.md) | 中文

本地运行的多仓库 Git 管理面板。选择一个父目录，扫描其一级子目录中的 Git 仓库，通过浏览器查看仓库状态、文件改动并执行常用 Git 操作。

![Git Folder Dashboard 预览](preview.gif)

## 目录

- [功能概览](#功能概览)
- [环境要求](#环境要求)
- [快速开始](#快速开始)
- [配置](#配置)
- [工作区快照](#工作区快照)
- [行为与限制](#行为与限制)
- [打包](#打包)
- [项目结构](#项目结构)
- [API 参考](#api-参考)

## 功能概览

- 扫描同级仓库，展示分支、ahead/behind 和工作区状态。
- 查看已暂存、未暂存文件的 diff，以及未跟踪文件的内容。
- 执行 fetch、pull、push、commit 和分支切换。
- 暂存、撤回暂存、丢弃、删除或本地忽略文件，支持批量操作。
- 通过 ZIP 快照导出和导入工作区改动，支持二进制文件。
- 切换中英文和明暗主题。
- 挂载到 URL 子路径，并可选启用 HTTP Basic 登录验证。

例如，扫描 `~/Code` 会识别以下 `project-a` 和 `project-b`，并将 `notes` 列为非 Git 目录：

```text
~/Code/
├── project-a/.git/
├── project-b/.git/
└── notes/
```

## 环境要求

- Python 3，且 `PATH` 中可以找到 Git。
- [requirements.txt](../requirements.txt) 中的 Python 依赖：Flask、Werkzeug 和 PyInstaller。PyInstaller 仅用于打包。
- 可选文件夹选择器：后端机器需有 `tkinter` 和图形桌面。Ubuntu 通过 `python3-tk` 提供 `tkinter`；也可以直接手动输入路径。

代码原先面向 Python 3.6 / Ubuntu 18.04 兼容，旧环境对应的依赖组合为 Flask 2.0.3 与 Werkzeug 2.0.3。当前 requirements 文件**未锁定版本**，不能假定其解析出的最新依赖仍支持 Python 3.6。

## 快速开始

在 `misc-tools` 根目录执行：

```bash
cd git-folder-dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py --default-path ~/Code
```

Windows 使用 `.venv\Scripts\activate` 激活环境。本文后续命令均在 `git-folder-dashboard` 目录中执行。

若浏览器没有自动打开，访问 `http://127.0.0.1:8765/`。扫描父目录后选择仓库，查看改动，再执行所需操作。页面中的路径均指向后端机器的文件系统。

## 配置

通过命令行参数配置，无需 `.env` 文件。

| 参数 | 说明 | 默认值 |
| --- | --- | --- |
| `--host` | 监听地址 | `127.0.0.1` |
| `--port` | 监听端口 | `8765` |
| `--default-path` | 页面初始工作区路径 | 空 |
| `--base-path` | URL 前缀，例如 `/git` | 域名根路径 |
| `--authorize USERNAME:PASSWORD` | 启用 HTTP Basic 登录验证 | 关闭 |
| `--no-browser [true/false]` | 禁止自动打开浏览器；单独使用时为 `true` | `false` |
| `--export REPO` | 导出工作区快照后退出 | 关闭 |
| `--import REPO SNAPSHOT` | 导入快照后退出；必须同时指定 `--force` | 关闭 |
| `--output FILE`、`-o FILE` | 快照导出位置 | 当前目录下带时间戳的 ZIP |
| `--force` | 允许覆盖导出文件，或确认导入快照 | 关闭 |

保留历史别名 `--defaut-path` 和 `--no-brower`。完整命令行说明可通过 `python app.py --help` 查看。

```bash
# 自定义端口和工作区，禁止自动打开浏览器
python app.py --port 8080 --default-path ~/Code --no-browser

# 挂载到 /git/，并要求登录
python app.py --base-path /git --authorize admin:change-me
```

第二个示例的地址为 `http://127.0.0.1:8765/git/`。使用反向代理时需保留配置的 URL 前缀。需要接受其他机器的连接时，再添加 `--host 0.0.0.0`。

登录验证覆盖页面、静态资源和 API。密码可以包含 `:`，用户名不可以。Basic 验证本身不加密凭据，命令行参数也可能被本机其他进程查看；对外提供服务时应通过 HTTPS 访问。

## 工作区快照

无需启动 Web 服务即可导出和导入改动：

```bash
python app.py --export /path/to/repo
python app.py --export /path/to/repo --output /tmp/repo-snapshot.zip
python app.py --import /path/to/repo /tmp/repo-snapshot.zip --force
```

仓库参数可以是工作区根目录或其中的子目录；非 Git 目录和裸仓库会被拒绝。覆盖已有导出文件需要 `--force`。

快照包含 `manifest.json` 和 `files/*`，记录修改、新增、删除及未跟踪文件。清单保存相对路径、变更类型、来源范围和文件内容的位置。Web 界面使用相同的快照格式。

导入会直接覆盖、创建和删除快照中列出的工作区文件，支持二进制和嵌套文件，但不会精确恢复 Git index 的暂存布局。快照只保存改动，不包含仓库历史，也不是完整仓库备份。

## 行为与限制

- 只扫描所选目录的一级子目录，不递归扫描，也不将所选目录本身作为扫描结果。
- 仓库 ID 和扫描结果仅保存在内存中，后端重启后需要重新扫描。
- **提交前会执行 `git add .`**，因此会包含仓库中所有可暂存改动，而非仅提交之前已暂存的文件。
- 仓库级丢弃依次执行 `git reset --hard HEAD` 和 `git clean -fd`，会移除已跟踪文件的改动，以及未跟踪文件和目录。
- 忽略操作写入 `.git/info/exclude`，不会修改共享的 `.gitignore`。
- 登录验证默认关闭，不提供按用户划分的仓库权限。
- 远程操作使用后端机器已有的 Git 凭据和配置。

## 打包

安装依赖后，在本项目目录构建独立可执行文件。

Linux/macOS：

```bash
pyinstaller --onefile --name git-folder-dashboard --add-data "static:static" app.py
```

Windows：

```bat
pyinstaller --onefile --name git-folder-dashboard --add-data "static;static" app.py
```

产物为 `dist/git-folder-dashboard`，Windows 带 `.exe` 后缀。目标机器仍需可以使用 Git。

```bash
./dist/git-folder-dashboard --port 8080 --default-path ~/Code --base-path /git --no-browser
```

## 项目结构

| 路径 | 职责 |
| --- | --- |
| [app.py](../app.py) | 调用 CLI 的薄入口 |
| [scripts/cli.py](../scripts/cli.py) | 参数解析，分发 Web 或快照命令 |
| [scripts/webapp.py](../scripts/webapp.py) | 组装并启动 Flask 应用 |
| [scripts/routes.py](../scripts/routes.py) | 路由、参数校验、仓库扫描与响应编排 |
| [scripts/runtime.py](../scripts/runtime.py) | 运行配置、登录验证、URL 前缀与浏览器打开 |
| [scripts/git_service.py](../scripts/git_service.py) | Git 执行、状态解析、预览与文件操作 |
| [scripts/snapshot_service.py](../scripts/snapshot_service.py) | 工作区快照导出与导入 |
| [scripts/repo_store.py](../scripts/repo_store.py) | 内存中的仓库 ID、路径和状态 |
| [scripts/http_utils.py](../scripts/http_utils.py) | JSON 请求响应与下载辅助 |
| [static/](../static/) | 原生 HTML、CSS 和 JavaScript 界面 |

请求链路为 `浏览器 → 路由 → Git/快照服务 → 刷新仓库状态 → JSON → 界面`。阅读代码时先看 CLI 和路由，再查看对应操作的服务模块。

## API 参考

以下路径均相对于 `--base-path`。仓库 ID 来自扫描或列表响应，重新扫描后会变化。

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/config` | 运行配置 |
| POST | `/api/select-folder` | 打开后端机器的文件夹选择器 |
| POST | `/api/scan` | 扫描父目录 |
| GET | `/api/repos` | 已扫描仓库列表 |
| POST | `/api/repos/refresh-all` | 刷新全部已扫描仓库 |
| POST | `/api/repos/{id}/refresh` | 刷新单个仓库 |
| POST | `/api/repos/{id}/fetch` | 获取远程更新 |
| POST | `/api/repos/{id}/pull` | 拉取 |
| POST | `/api/repos/{id}/push` | 推送 |
| POST | `/api/repos/{id}/push-origin-main` | 将本地 main 分支推送到 origin |
| POST | `/api/repos/{id}/open` | 在后端机器上打开仓库目录 |
| POST | `/api/repos/{id}/commit` | 暂存所有可暂存改动并提交 |
| POST | `/api/repos/{id}/checkout` | 切换分支 |
| POST | `/api/repos/{id}/discard` | 丢弃仓库改动 |
| POST | `/api/repos/{id}/files/preview` | 查看 diff 或文件 |
| POST | `/api/repos/{id}/files/action` | 单文件操作 |
| POST | `/api/repos/{id}/files/bulk-action` | 批量文件操作 |
| POST | `/api/repos/{id}/export-state` | 下载快照 ZIP |
| POST | `/api/repos/{id}/import-state` | 上传并应用快照 ZIP |

仓库状态值包括 `clean`、`dirty`、`ahead`、`behind`、`diverged`、`no_remote` 和 `error`。请求体与响应字段见 [scripts/routes.py](../scripts/routes.py)。
