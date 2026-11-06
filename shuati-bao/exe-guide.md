# 刷题宝 exe 使用说明（v0.6 最终版）

## exe 在哪

`dist/刷题宝.exe`（Windows 程序，单文件）。

## 怎么用（Win7 / 10 / 11 主机）

1. 把整个 `mvp-v06` 文件夹拷到主机上。
2. 双击 `dist/刷题宝.exe`。
3. 启动后自动打开浏览器到本机地址 `http://127.0.0.1:8765/`；控制台窗口会打印本机地址、局域网地址和停止方法。
4. 局域网其他电脑用浏览器打开 `http://<主机IP>:8765/`；XP 机打开 `http://<主机IP>:8765/lite`。
5. 停止：关掉 exe 的控制台窗口即可（按 Ctrl+C 也可以）。
6. 数据库和题库存在 exe 旁边的 `data/` 文件夹里（`data/shuati.db` + `data/assets/` + `data/backups/`）；搬家时整个文件夹一起拷走。

## 不用装 Python

exe 是单文件程序，主机不用装 Python。后台“运维备份”照常用（一键备份、每天自动备份、恢复）。

## 怎么重新打包（在 Windows 主机上）

1. 主机装 Python 3.8 以上（勾选 Add Python to PATH）。
2. 双击 `build_exe.bat`，按提示等它装完 PyInstaller 并打包。
3. 打包完成会生成新的 `dist/刷题宝.exe`。

## 重要限制（实话）

- **XP 不能跑这个 exe**：PyInstaller 打出的 exe 要求 Win7 以上。XP 机继续走网页版 `/lite`，不要在 XP 上跑 exe。
- **Windows exe 本身未在真实 Windows 主机上跑过**：本机是 Linux 环境，已验证 exe 是有效 PE 文件，并在 wine 下实际跑起来服务过（根页/Lite/showcase 均 200、登录与练题都通，见 `验收记录-v0.6.md` 的 exe 验证一节）。拿到 Windows 主机后，请先双击验证一次：能打开浏览器、能登录（演示账号 `minjing` / `123456`）、能练一题。
- 不要同时开 exe 和 `start.bat`（会抢 8765 端口，二选一）。
- 首次启动 Windows 防火墙可能弹窗，点“允许访问”，否则局域网其他电脑连不上。端口是 8765（TCP）。
- 演示账号 `admin` / `jiaoguan` / `minjing` / `minjing2`，密码都是 `123456`，**上线前务必改掉**。
