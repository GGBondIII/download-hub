// worker.js — 魔搭 Notebook 保活 Worker v0.2（2026-11-06，诚实版）
// 部署目标：Cloudflare Workers 免费版（每天 10 万次请求，不绑卡）。
//
// 先说清它能做什么、不能做什么：
// - 能做：每 4 小时发一封提醒邮件到通知邮箱，附上 Notebook 手动启动链接；
//        提供一个状态页和一个“去启动”页；提供 /health 供外部定时器唤醒。
// - 不能做：点一下就自动启动 Notebook。免费魔搭实例没有 PAI 的 dsw 编号，
//   也没有公开的启动接口，Worker 调不到启动接口。v0.1 里写的
//   PAI StartInstance 那条路已经证实走不通，不要再用。
// - 真正的“点启动”现在由用户电脑上的 WorkBuddy 定时任务 + 脚本在做，
//   这个 Worker 是它的备份提醒和入口，不是替代品。
//
// 需要配的环境变量（在 Cloudflare 控制台里设，不要写进代码）：
// - NOTIFY_EMAIL：通知邮箱，例如 19986734357@163.com
// - RESEND_API_KEY：Resend 免费版 API Key（用来发邮件）。没有它就不发邮件，
//   只记日志。Resend 免费版要另外注册，见 DEPLOY-Cloudflare.md。
// - FROM_EMAIL：发件地址，Resend 要求发件域名已验证；
//   没验证域名之前可以用 Resend 自带的测试发件地址（只能发给注册邮箱）。

const NOTEBOOK_URL = "https://www.modelscope.cn/my/mynotebook";

export default {
  // 定时触发：wrangler.toml 里配 cron，每 4 小时跑一次。
  async scheduled(event, env, ctx) {
    ctx.waitUntil(sendReminder(env, "定时提醒"));
  },

  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    if (url.pathname === "/health") {
      return new Response(JSON.stringify({ ok: true, time: new Date().toISOString() }), {
        headers: { "content-type": "application/json" },
      });
    }
    if (url.pathname === "/start") {
      // 不是自动启动，是带说明的手动启动页，不骗人。
      return new Response(
        `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>启动 Notebook</title></head><body style="font-family:sans-serif;max-width:560px;margin:48px auto;padding:0 20px;">
        <h1>启动你的 Notebook</h1>
        <p>自动启动目前做不到，因为魔搭免费实例没有阿里云的启动编号。下面这个按钮打开魔搭页面，你再点一下“启动”就行，两步。</p>
        <p><a href="${NOTEBOOK_URL}" style="display:inline-block;padding:14px 28px;background:#0071e3;color:#fff;border-radius:999px;text-decoration:none;">打开 Notebook 页面去启动</a></p>
        <p style="color:#666">CPU 实例单次最多跑 4 小时，到时间会停。电脑上的 WorkBuddy 定时任务会帮你点启动，这个页面只是备用入口。</p>
        </body></html>`,
        { headers: { "content-type": "text/html; charset=utf-8" } }
      );
    }
    // 首页：状态页
    return new Response(
      `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>Notebook 保活</title></head><body style="font-family:sans-serif;max-width:560px;margin:48px auto;padding:0 20px;">
      <h1>Notebook 保活</h1>
      <p>状态：运行中。提醒邮件每 4 小时发一次到通知邮箱。</p>
      <p><a href="/start">去启动 Notebook</a> · <a href="${NOTEBOOK_URL}">直接打开魔搭页面</a></p>
      </body></html>`,
      { headers: { "content-type": "text/html; charset=utf-8" } }
    );
  },
};

async function sendReminder(env, reason) {
  if (!env.RESEND_API_KEY || !env.NOTIFY_EMAIL) {
    console.log("跳过发邮件：没配 RESEND_API_KEY 或 NOTIFY_EMAIL。");
    return;
  }
  const from = env.FROM_EMAIL || "Notebook 保活 <onboarding@resend.dev>";
  const res = await fetch("https://api.resend.com/emails", {
    method: "POST",
    headers: {
      Authorization: `Bearer ${env.RESEND_API_KEY}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify({
      from,
      to: [env.NOTIFY_EMAIL],
      subject: "Notebook 快到期了：点这里去启动",
      html: `<p>你的魔搭 Notebook 快到 4 小时上限了（或已经停了）。点下面去启动，两步就行：</p><p><a href="${NOTEBOOK_URL}">${NOTEBOOK_URL}</a></p><p>电脑上的 WorkBuddy 定时任务也会帮你点启动，这封是备用提醒。</p>`,
    }),
  });
  console.log(`提醒邮件（${reason}）发送结果：${res.status}`);
}
