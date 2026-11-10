# 飞书机器人（摸鱼仔AI助手）— ECS 部署包

代码：`feishu_bot.py`，366 行完整版（标准库 only，无第三方依赖）。
监听 0.0.0.0:18080，两个接口：`POST /feishu/events`、`GET /health`。

## 部署（在 ECS 上）

```bash
mkdir -p /data/agents/feishu-bot
cp feishu_bot.py /data/agents/feishu-bot/
cp .env.example /data/agents/feishu-bot/.env   # 然后填真实值
cd /data/agents/feishu-bot
nohup python3 feishu_bot.py > bot.log 2>&1 &
curl http://127.0.0.1:18080/health
```

也可以用 systemd（见 `feishu-bot.service`，复制到 `/etc/systemd/system/` 后
`systemctl enable --now feishu-bot`）。

## 必填的环境变量（.env，不进仓库）

- `FEISHU_APP_ID` / `FEISHU_APP_SECRET`：飞书开放平台“摸鱼仔AI助手”应用的凭证
- `FEISHU_VERIFY_TOKEN`：飞书事件订阅的验证 token（可空）
- `OPENROUTER_API_KEY`：OpenRouter 免费模型 Key（网关不在本机时走直连兜底）
- `GATEWAY_URL`：本地免费模型网关地址，默认 `http://127.0.0.1:18900/v1`
  （ECS 上目前没有网关，留空默认值即可，机器人会走 OpenRouter 直连）
- `PORT`：默认 18080
- `DEFAULT_MODEL`：默认 `nvidia/nemotron-3-ultra-550b-a55b:free`

## 注意

- 没有填 `FEISHU_APP_ID` / `FEISHU_APP_SECRET` 时程序会直接退出，
  这是故意设计的：没凭证不能假装在跑。
- 机器人只问一句答一句，不会主动定时推送；敏感内容（密码、验证码、
  证件、支付信息）会直接拒绝，不发给外部模型。
- 飞书侧事件订阅地址：`http://<公网IP>:18080/feishu/events`
