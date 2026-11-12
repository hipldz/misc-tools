# Git Folder Dashboard

[English](../README.md) | 中文

在本地管理一个父目录下的多个 Git 仓库。工作区概览负责找出需要处理的项目，仓库详情集中展示文件、差异和提交操作。

## 界面与状态

- 本地修改与远端 ahead / behind 独立展示，不再用一个状态覆盖其他信息。
- 打开仓库、从编辑器切回窗口时检查本地状态；当前仓库可见时每 10 秒检查一次。
- 打开工作区时先检查所有仓库的本地状态，再限流抓取远端，逐仓库更新结果。
- 每个仓库分别记录本地检查时间和成功抓取时间。远端失败会保留旧结果并明确标记。
- 后台任务显示完成数、失败项目和详细输出，支持单独重试。
- 提交严格使用暂存区；“暂存全部并提交”是单独的明确操作。
- 提交草稿会保留；提交失败、仓库操作失败和路径错误各自在对应区域显示。
- 支持中英文、明暗主题、移动布局、文件差异、快照导入导出。
- 前端资源全部在本地，无 CDN，无需 Node 构建即可运行或打包。

## 启动

系统需要安装 Git 并加入 `PATH`。本轮开发与 Windows 打包使用 Python 3.12 验证。源码保持 Python 3.6 语法；旧环境可使用 `requirements-legacy.txt` 固定依赖，本轮未实测旧解释器运行。

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt
.\.venv\Scripts\python.exe app.py --default-path D:\Workspace\Git
```

默认访问 `http://127.0.0.1:8765`。Linux/macOS 把虚拟环境解释器路径改成 `.venv/bin/python`。

```powershell
# 每五分钟后台抓取整个工作区，并使用可选代理
python app.py --default-path D:\Workspace\Git --sync-interval 300 --git-proxy http://127.0.0.1:7890

# 子路径部署与登录
python app.py --base-path /git --authorize admin:change-me --no-browser
```

| 参数 | 默认值 | 作用 |
| --- | --- | --- |
| `--host` | `127.0.0.1` | 监听地址 |
| `--port` | `8765` | 端口 |
| `--default-path` | 空 | 默认工作区父目录 |
| `--sync-interval` | `0` | 全工作区定时抓取秒数，`0` 关闭 |
| `--fetch-workers` | `3` | 检查与抓取并发数，范围 1–8 |
| `--git-proxy` | 空 | Git HTTP 代理 |
| `--base-path` | 空 | 例如 `/git` 的 URL 前缀 |
| `--authorize` | 关闭 | `用户名:密码` 形式的 Basic Auth |
| `--no-browser` | `false` | 不自动打开浏览器，可传 `true/false` |

保留 `--defaut-path`、`--no-brower` 旧别名。全工作区定期抓取由启动参数控制。首次加载、手动抓取不受定时开关影响。Fetch 更新远端引用，不执行 pull 或修改工作区；拉取采用 `--ff-only`。

目录选择器在服务端机器打开。Windows 使用系统原生目录对话框，不依赖 Tk；Linux/macOS 使用 Tk。远程或无桌面环境请直接输入服务端路径；Linux 可能需要安装 `python3-tk`。EXE 也需要系统 Git。对外部署 Basic Auth 时应配置 HTTPS，默认只监听本机。

## Windows 单文件打包

```powershell
# 创建虚拟环境后执行；使用清华镜像准备构建依赖
.\.venv\Scripts\python.exe scripts/build.py --install-dependencies

# 已安装依赖时
.\.venv\Scripts\python.exe scripts/build.py
```

也提供 `scripts/build.ps1` 便捷入口。构建先执行后端回归测试，然后根据 `packaging/git-folder-dashboard.spec` 打出单文件 EXE，自动包含 `static/` 与 `templates/`。

```text
dist/
  git-folder-dashboard.exe
  git-folder-dashboard-2.0.0-windows-amd64.zip
  SHA256SUMS.txt
```

构建中间文件放在 `build/pyinstaller/`，浏览器截图放在 `build/verification/`，这些目录均不提交。EXE 可从任意工作目录启动，无需旁放源码或静态资源。旧 Python 环境只作为源码运行目标，打包请使用现代 Python。

## 命令行快照

```powershell
python app.py --export ./ --output ./changes.zip
python app.py --import ./ ./changes.zip --force
```

快照记录改动文件的最终工作区内容，支持新增、修改、删除和二进制文件；不保存整个仓库，也不重建暂存区。导入只应用清单记录的文件，可能覆盖当前修改，必须明确确认。导出覆盖已有文件需要 `--force`。

## 目录约定

应用代码在 `git_dashboard/`，Git、快照、工作区和后台任务分别在 `services/`。前端按 `templates/`、`static/css/`、`static/js/`、`static/icons/` 放置；`scripts/` 只放工程脚本，`packaging/` 只放打包配置，`tests/` 放临时仓库回归验证，`docs/` 放文档。

[工程结构与接口](architecture.md) · [开发和发布验证](development.md)

扫描只覆盖第一层子目录，支持 `.git` 为文件的 worktree。服务端工作区与任务在内存中，重启后重新发现；浏览器保存偏好和提交草稿。同一个服务实例连接的浏览器共享一个工作区。
