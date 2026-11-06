# notebook_auto_start.py — WorkBuddy 电脑上跑的自动启动脚本（v0.2，2026-11-06）
# 改动：不再每 30 分钟轮询。改成单次检查 + 时间戳保护，省积分。
# 用法（在 Windows 电脑上）：
#   pip install playwright
#   playwright install chromium
#   python notebook_auto_start.py            # 正常跑：没到时间就直接退出，不花功夫
#   python notebook_auto_start.py --force    # 不管时间戳，强制检查一次（测试用）
# 第一次跑之前，先用同一个浏览器手动登录一次魔搭，完成短信验证，
# 登录态保存在 ./ms_profile/ 里，后面脚本复用，不用每次都登录。
# 注意：登录态过期、或页面要求重新验证时，脚本会停下来写日志，不会猜验证码。
#
# 时间间隔说明：页面上查到 CPU 实例单次最多跑 4 小时，所以默认间隔是 3.5 小时，
# 也就是上次确认它活着之后过了 3.5 小时才再检查一次。
# 如果你坚持按 10 小时算，把下面的 MIN_INTERVAL_SECONDS 改成 9.5 * 3600，
# 但注意：4 小时一到实例就会停，10 小时才检查的话中间会断 6 小时。

import os
import sys
import time
import datetime
import logging

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "auto_start.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("notebook_auto_start")

NOTEBOOK_URL = "https://www.modelscope.cn/my/mynotebook"
PROFILE_DIR = os.path.join(os.path.dirname(__file__), "ms_profile")
LAST_RUN_FILE = os.path.join(os.path.dirname(__file__), "last_activation.txt")
MAX_RETRIES = 3

# 上次确认实例活着之后，隔多久才再检查一次（秒）。默认 3.5 小时。
MIN_INTERVAL_SECONDS = 3.5 * 3600

def read_last_activation():
    try:
        with open(LAST_RUN_FILE, "r", encoding="utf-8") as f:
            return datetime.datetime.fromisoformat(f.read().strip())
    except Exception:
        return None

def write_last_activation(now):
    with open(LAST_RUN_FILE, "w", encoding="utf-8") as f:
        f.write(now.isoformat())

def main():
    now = datetime.datetime.now()
    force = "--force" in sys.argv
    last = read_last_activation()
    if last and not force:
        elapsed = (now - last).total_seconds()
        if elapsed < MIN_INTERVAL_SECONDS:
            log.info(f"跳过：上次确认活着是 {last}，才过了 {elapsed/3600:.1f} 小时，不到 {MIN_INTERVAL_SECONDS/3600:.1f} 小时，不检查。")
            return
    else:
        if force:
            log.info("强制检查（--force），忽略时间戳。")
        else:
            log.info("第一次跑，没有上次的时间戳，直接检查。")

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("缺少 playwright，先跑: pip install playwright && playwright install chromium")
        return

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"]
        )
        page = ctx.new_page()
        page.goto(NOTEBOOK_URL, timeout=60000)
        page.wait_for_timeout(5000)

        # 需要登录：页面出现登录字样或跳到登录页，停下等人工
        if "登录" in page.content() and "我的Notebook" not in page.content():
            log.warning("需要重新登录魔搭，请在电脑上手动登录一次（短信验证一次），再跑脚本。")
            ctx.close()
            return

        # 读状态：页面上有“已停止”和“运行中”两种
        text = page.content()
        if "运行中" in text:
            log.info("实例运行中，什么都不做。")
            write_last_activation(now)  # 这次确认它活着，更新时间戳
            ctx.close()
            return

        # 已停止：点 CPU 环境的启动按钮，重试 3 次
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # 启动按钮文案以页面实际为准，这里按通用写法找
                btn = page.get_by_role("button", name="启动").first
                btn.click(timeout=10000)
                log.info(f"第 {attempt} 次点了启动，等实例起来…")
                page.wait_for_timeout(180000)  # 等 3 分钟
                if "运行中" in page.content():
                    log.info("启动成功，实例运行中。")
                    write_last_activation(datetime.datetime.now())
                    ctx.close()
                    return
                log.warning(f"第 {attempt} 次点完还没变运行中，重试。")
            except Exception as e:
                log.warning(f"第 {attempt} 次启动失败：{e}")
                page.wait_for_timeout(300000)  # 隔 5 分钟再试

        log.error("启动 3 次都失败，请人工看一眼 Notebook 页面。")
        ctx.close()

if __name__ == "__main__":
    main()
# 用法（在云电脑 Windows 上）：
#   pip install playwright
#   playwright install chromium
#   python notebook_auto_start.py
# 第一次跑之前，先用同一个浏览器手动登录一次魔搭，完成短信验证，
# 登录态保存在 ./ms_profile/ 里，后面脚本复用，不用每次都登录。
# 注意：登录态过期、或页面要求重新验证时，脚本会停下来写日志，不会猜验证码。

import os
import time
import datetime
import logging

LOG_DIR = os.path.join(os.path.dirname(__file__), "logs")
os.makedirs(LOG_DIR, exist_ok=True)
logging.basicConfig(
    filename=os.path.join(LOG_DIR, "auto_start.log"),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("notebook_auto_start")

NOTEBOOK_URL = "https://www.modelscope.cn/my/mynotebook"
PROFILE_DIR = os.path.join(os.path.dirname(__file__), "ms_profile")
MAX_RETRIES = 3

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        log.error("缺少 playwright，先跑: pip install playwright && playwright install chromium")
        return

    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(
            PROFILE_DIR, headless=False, args=["--start-maximized"]
        )
        page = ctx.new_page()
        page.goto(NOTEBOOK_URL, timeout=60000)
        page.wait_for_timeout(5000)

        # 需要登录：页面出现登录字样或跳到登录页，停下等人工
        if "登录" in page.content() and "我的Notebook" not in page.content():
            log.warning("需要重新登录魔搭，请在云电脑上手动登录一次（短信验证一次），再跑脚本。")
            ctx.close()
            return

        # 读状态：页面上有“已停止”和“运行中”两种
        text = page.content()
        if "运行中" in text:
            log.info("实例运行中，什么都不做。")
            ctx.close()
            return

        # 已停止：点 CPU 环境的启动按钮，重试 3 次
        for attempt in range(1, MAX_RETRIES + 1):
            try:
                # 启动按钮文案以页面实际为准，这里按通用写法找
                btn = page.get_by_role("button", name="启动").first
                btn.click(timeout=10000)
                log.info(f"第 {attempt} 次点了启动，等实例起来…")
                page.wait_for_timeout(180000)  # 等 3 分钟
                if "运行中" in page.content():
                    log.info("启动成功，实例运行中。")
                    ctx.close()
                    return
                log.warning(f"第 {attempt} 次点完还没变运行中，重试。")
            except Exception as e:
                log.warning(f"第 {attempt} 次启动失败：{e}")
                page.wait_for_timeout(300000)  # 隔 5 分钟再试

        log.error("启动 3 次都失败，请人工看一眼 Notebook 页面。")
        ctx.close()

if __name__ == "__main__":
    main()
