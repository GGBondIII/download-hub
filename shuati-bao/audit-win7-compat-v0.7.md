# 刷题宝 v0.7 — Win7 兼容性审核报告（从头复核）

审核时间：2026-11-06。起因：用户在真实 Win7 电脑上试了 v0.6，网页版和 exe 都装不上；另报 zip 解压缩损坏。
审核方法：不信旧结论，全部重查——zip 逐项校验、exe 的 PE 头与内嵌 Python 版本实测、启动脚本逐行读、对照 Python / PyInstaller 官方文档。

## 结论先说

v0.6 在 Win7 上失败是**两个独立的真问题**，不是用户操作问题：

1. **zip 解压缩损坏是真的**：压缩包数据本身没坏（CRC 全过），但 15 个中文文件名没有置 UTF-8 标志，Win7 自带解压按 GBK 解码，其中 4 个文件名含非法 GBK 字节序列，解压直接失败。
2. **exe 在 Win7 上装不上是真的**：exe 内嵌的是 Python 3.12，官方不支持 Win7（Python 3.8 是最后一个官方支持 Win7 的版本）。v0.6 文档里写的“exe 要求 Win7 以上”与“装 Python 3.8 以上”都是错的。

网页版装不上也是这两个问题叠加：zip 解不开就什么都没有；就算解开了，start.bat 也要求主机预装 Python，而 Win7 主机上一般没有 Python。

## 问题 1：zip 解压缩损坏（根因：文件名编码）

- 证据 1：`unzip -t` 全部通过，`testzip()` 为空——压缩数据本身完好，文件没有在传输中损坏。
- 证据 2：27 个条目里 15 个中文文件名，`flag_bits` 的 UTF-8 标志位（bit 11）全部为 0，文件名以原始 UTF-8 字节存放。
- 证据 3：把这些原始字节按 GBK 解码（Win7 自带解压对无 UTF-8 标志的文件名就是这么做的），4 个条目直接解码失败：
  - `示例题库-边检通用样题20道.xlsx`（字节 0xa3 非法）
  - `示例题库-Word导入示例3道.docx`（字节 0x93 非法）
  - `设计检查表-HIG.md`（字节 0xae 非法）
  - `刷题宝.spec`（字节 0xa2 非法）
- 其余中文文件名能解出 GBK，但全是乱码。Win7 自带解压遇到非法字节序列会直接报错“解压缩损坏”并中止，不是只乱码文件名。
- 修复（v0.7）：压缩包内全部改成英文文件名（`import-templates/`、`product-intro.md`、`acceptance-v0.x.md`、`design-checklist-HIG.md`、`exe-guide.md`、`shuatibao.spec` 等），并用脚本校验——只要还有一个非 ASCII 文件名，打包就失败。`dist/` 仍不进 zip（exe 另附）。

## 问题 2：exe 在 Win7 上装不上（根因：内嵌 Python 3.12）

- 证据 1：PE 实测——`刷题宝.exe` 是 PE32+ x86-64 控制台程序，内嵌 `python312.dll`（字符串表可查）。
- 证据 2：Python 官方文档（docs.python.org，using/windows）：“Python 3.12 supports Windows 8.1 and newer. If you require Windows 7 support, please install Python 3.8.”另有多处确认：Python 3.8 是最后一个官方支持 Win7 的版本，3.9 及以上安装程序会在 Win7 上直接拒绝。
- 证据 3：PyInstaller 官方文档（5.0）：“To support Windows 8.0 and 7 you must build with Python 3.8 or older.”PyInstaller 6.x 的 README 也只说“should work on Windows 7 or newer, but we only officially support Windows 8+”——真正卡住 Win7 的是内嵌的 Python 3.12，不是打包器本身。
- 修复（v0.7）：新增 Win7 专用版 `dist/刷题宝-Win7.exe`，用 **Python 3.8.10 + PyInstaller 5.13.2** 打包（copyparty 等项目给 Win7 打包就是这个组合）。通用版 `dist/刷题宝.exe`（Python 3.12）保留，只给 Win10/11 用。两个版本功能完全相同。
- 代码侧已验证：`server.py` 无 3.9+ 语法与标准库用法（`ast.parse(feature_version=(3,8))` 通过；无 `match/case`、`X | Y` 注解、`removeprefix`、`zoneinfo`、`datetime.UTC`），Python 3.8 能直接跑。

## 问题 3：网页版在 Win7 裸机上没有可行的启动路径

- `start.bat` 要求主机预装 Python，Win7 主机一般没有；没装时只打印一行提示，用户只能看到“装不上”。
- `start.bat` / `build_exe.bat` 是无 BOM 的 UTF-8 编码，又以 `chcp 65001` 开头：Win7 的 cmd 默认 GBK，读无 BOM 的 UTF-8 批处理会乱码，而 `chcp 65001` 在 Win7 下还会扰乱批处理解析（已知坑）。
- 修复（v0.7）：两个 bat 全部改写为 GBK 编码、去掉 `chcp 65001`、用 CRLF 换行；`start.bat` 没检测到 Python 时明确告诉用户“直接双击 exe，不用装 Python”，并区分 Win7 / Win10-11 的 exe；`build_exe.bat` 锁定 Python 3.8 + PyInstaller 5.13.2 打 Win7 版，并注明通用版的打法。

## 问题 4：文档里的兼容性说法多处是错的（已一并修正）

- “exe 要求 Win7 以上”——错。v0.6 的 exe 要求 Win8.1 以上；Win7 只能用 v0.7 的专用版；XP 任何 exe 都不能跑。
- “主机装 Python 3.8 以上”——对 Win7 是错的。Win7 只能装 Python 3.8，3.9 及以上装不上。
- `build_exe.bat` 原来让用户装“Python 3.8 以上”再 `pip install pyinstaller`（最新 6.x）——在 Win7 主机上照做会原样复现这个坏 exe。已改成锁定版本。
- `README.md` 与 `product-intro.md` 的启动方式、系统对照表、待验证清单已按“Win7 专用 exe / Win10-11 通用 exe / XP 只走 Lite”重写。

## 其他复核项（没发现问题的）

- 网页本身：现代版目标浏览器是 Chrome/Edge（Win7 上 Chrome ≤109 可用），Lite 版面向 IE8/Chrome 49/XP，与设计一致；静态资源零 CDN、零外部字体，离线可用。
- 服务端：`ThreadingHTTPServer` + SQLite WAL，设计按 150 并发、300 峰值预留；150 并发仍只做过本机模拟，未做真实局域网实机压测（见待验证）。
- 导入框架：Excel/Word 用标准库 `zipfile + xml` 手写解析，运行时零依赖；模板文件内容未变，只改了文件名。

## v0.7 改了什么（清单）

- 新增 `dist/刷题宝-Win7.exe`（Python 3.8.10 + PyInstaller 5.13.2）；保留 `dist/刷题宝.exe`（Python 3.12，Win10/11 用）。
- 压缩包全英文文件名，打包脚本强制校验（见 `build-v07-zip.py`）。
- `start.bat`、`build_exe.bat` 改 GBK 编码，去 `chcp 65001`；没装 Python 时指引用户用 exe。
- `server.py` 版本号升到 v0.7；功能与 v0.6 完全相同。
- `README.md`、`product-intro.md`、`exe-guide.md` 按正确口径重写；新增本报告与 `acceptance-v0.7.md`。
- v0.6 原样保留在 `mvp-v06/`，可回滚。

## 仍需真实环境验证（v0.7 也没做到，不要当作已验证）

- Win7 专用 exe 在真实 Win7 SP1 64 位机上双击（本机只在 wine 下验过）。
- 通用版 exe 在真实 Win10/11 机上双击。
- 真实局域网多机访问、联邦共享两台真机、150 并发实机压测、真实 XP 机开 Lite 页。
- 浏览器实测动效手感与系统减弱动效开关切换。
- 若用户的 Win7 是 32 位：两个 exe 都是 64 位，都不能用，需另打 32 位版（请告知）。
