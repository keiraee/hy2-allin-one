#!/usr/bin/env bash
# panel.sh - Web 面板 HTML 生成

write_panel() {
  install -d -o root -g caddy -m 0750 "$WEB_DIR" "$WEB_DIR/downloads"
  cat > "$WEB_DIR/index.html" <<'HTML'
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>HY2 AIO Dashboard</title>
<style>
:root{font-family:Inter,ui-sans-serif,system-ui,-apple-system,"Segoe UI",sans-serif;color:#17191c;background:#f4f5f7}
*{box-sizing:border-box}body{margin:0}.wrap{max-width:1180px;margin:auto;padding:30px 16px 64px}
.top,.head{display:flex;justify-content:space-between;align-items:center;gap:14px}.top{align-items:flex-end}
h1{font-size:26px;margin:0}.muted,.label{color:#737780}.actions,.services{display:flex;gap:8px;flex-wrap:wrap}
.btn,.pill{border:1px solid #d9dce1;border-radius:11px;background:#fff;color:inherit;text-decoration:none;padding:9px 12px;cursor:pointer}
.btn.primary{background:#17191c;color:#fff;border-color:#17191c}.btn:disabled{opacity:.55;cursor:wait}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:20px}
.card{background:#fff;border:1px solid #e3e5e8;border-radius:17px;padding:17px;box-shadow:0 2px 12px #00000008}
.value{font-size:21px;font-weight:760;margin-top:5px}.bar{height:8px;background:#eceef1;border-radius:8px;overflow:hidden;margin-top:13px}
.bar i{display:block;height:100%;background:#17191c}.ok{color:#137547;border-color:#b9dec9}.bad{color:#b42318;border-color:#f0b8b2}.card.disabled{opacity:.55}
.users{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.name{font-weight:750;font-size:17px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}.stat{background:#f5f6f8;border-radius:11px;padding:10px}.stat b{display:block}
h2{font-size:17px;margin:27px 0 12px}.notice{margin-top:14px;padding:12px 14px;background:#fff8e8;border:1px solid #f0dfaf;border-radius:12px}
.error{display:none;margin-top:14px;padding:12px 14px;background:#fff0ef;color:#b42318;border-radius:12px}
.footer{margin-top:26px;color:#777b82;font-size:12px}
@media(max-width:850px){.grid{grid-template-columns:repeat(2,1fr)}.users{grid-template-columns:1fr}}
@media(max-width:540px){.grid{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}.stats{grid-template-columns:1fr}}
</style>
</head>
<body>
<div class="wrap">
  <div class="top">
    <div>
      <h1>HY2 AIO Dashboard</h1>
      <div id="time" class="muted">正在读取数据…</div>
    </div>
    <div class="actions">
      <button id="syncBtn" class="btn primary" onclick="syncNow()">立即同步</button>
      <a class="btn" href="users.csv">用户 CSV</a>
      <a class="btn" href="history.csv">历史记录</a>
    </div>
  </div>

  <div id="error" class="error"></div>
  <div class="notice">面板流量来自服务器网卡本地计数，适合日常观察；云厂商控制台和账单仍是最终计费依据。速率模式只写入 Clash 订阅，HY2 基础直链不包含带宽参数。</div>

  <div class="grid">
    <div class="card">
      <div class="label">本月整机流量</div><div id="traffic" class="value">--</div>
      <div id="remain" class="muted">--</div><div class="bar"><i id="trafficBar" style="width:0"></i></div>
    </div>
    <div class="card"><div class="label">CPU / 负载</div><div id="cpu" class="value">--</div><div id="load" class="muted">--</div></div>
    <div class="card"><div class="label">内存 / Swap</div><div id="memory" class="value">--</div><div id="swap" class="muted">--</div></div>
    <div class="card"><div class="label">磁盘 / 运行时间</div><div id="disk" class="value">--</div><div id="uptime" class="muted">--</div></div>
  </div>

  <h2>服务状态</h2><div id="services" class="services"></div>
  <h2>用户状态</h2><div id="users" class="users"></div>
  <div class="footer">数据每 60 秒采集，网页每 30 秒自动刷新。复制订阅/直链/密码需面板鉴权按需拉取。完整备份仅可通过 CLI（sudo hy2 backup）获取。</div>
</div>

<script>
const $=id=>document.getElementById(id);
const esc=value=>String(value).replace(/[&<>"']/g,ch=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#039;"}[ch]));
const bytes=value=>{let n=Number(value||0),i=0;const u=["B","KB","MB","GB","TB"];while(n>=1000&&i<u.length-1){n/=1000;i++}return n.toFixed(i<2?2:1)+" "+u[i]};
const duration=seconds=>{seconds=Math.max(0,Math.floor(Number(seconds)||0));return Math.floor(seconds/86400)+" 天 "+Math.floor(seconds%86400/3600)+" 小时"};
async function copyText(text,button){try{await navigator.clipboard.writeText(text)}catch(e){prompt("复制下面内容：",text)}const old=button.textContent;button.textContent="已复制";setTimeout(()=>button.textContent=old,1200)}
async function apiPost(path,payload){const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload),cache:"no-store"});const result=await response.json().catch(()=>({}));if(!response.ok||!result.ok)throw new Error(result.error||("HTTP "+response.status))}
async function copyCredential(username,kind,button){const old=button.textContent;button.disabled=true;try{const response=await fetch("api/user/credentials",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({username,kind}),cache:"no-store"});const result=await response.json().catch(()=>({}));if(!response.ok||!result.ok||!result.value)throw new Error(result.error||("HTTP "+response.status));await copyText(result.value,button)}catch(error){alert("复制失败："+error.message);button.textContent=old}button.disabled=false}
async function setNote(username,button){const note=prompt("设备备注（如 iPhone 13、笔记本，留空清除）："+(button.dataset.value?"当前："+button.dataset.value:""),button.dataset.value||"");if(note===null)return;const old=button.textContent;button.disabled=true;try{await apiPost("api/user/note",{username,note:note.trim()});await load()}catch(error){alert("设置备注失败："+error.message)}button.disabled=false;button.textContent=old}
async function toggleUser(username,button){const disabled=button.dataset.disabled==="1";if(!disabled&&!confirm("确认禁用 "+username+"？该用户将立即无法连接，数据保留。"))return;const old=button.textContent;button.disabled=true;try{await apiPost(disabled?"api/user/enable":"api/user/disable",{username});await load()}catch(error){alert("操作失败："+error.message)}button.disabled=false;button.textContent=old}
async function syncNow(){const btn=$("syncBtn"),old=btn.textContent;btn.disabled=true;btn.textContent="同步中…";try{const response=await fetch("api/sync",{method:"POST",cache:"no-store"});const result=await response.json().catch(()=>({}));if(!response.ok||!result.ok)throw new Error(result.error||("HTTP "+response.status));await load();btn.textContent="同步完成"}catch(error){btn.textContent="同步失败";alert("同步失败："+error.message)}setTimeout(()=>{btn.disabled=false;btn.textContent=old},1500)}
async function load(){
  try{
    const response=await fetch("data.json?t="+Date.now(),{cache:"no-store"});if(!response.ok)throw new Error("HTTP "+response.status);
    const data=await response.json(),t=data.server.traffic;
    $("time").textContent="更新时间："+data.generated_at+" · "+data.server.ip+" · "+data.server.domain;
    $("traffic").textContent=bytes(t.used)+" / "+bytes(t.limit);
    $("remain").textContent="接收 "+bytes(t.rx)+" · 发送 "+bytes(t.tx)+" · 剩余 "+bytes(t.remain)+" · "+Number(t.percent).toFixed(3)+"%";
    $("trafficBar").style.width=Math.min(100,Number(t.percent)||0)+"%";
    $("cpu").textContent=data.server.cpu+"%";$("load").textContent="负载 "+data.server.load.join(" / ");
    $("memory").textContent=data.server.memory.percent+"%";$("swap").textContent="Swap "+data.server.memory.swap_percent+"%";
    $("disk").textContent=data.server.disk.percent+"%";$("uptime").textContent="运行 "+duration(data.server.uptime);
    $("services").innerHTML=Object.entries(data.server.services).map(([name,status])=>`<span class="pill ${status==="active"?"ok":"bad"}">${esc(name)}：${esc(status)}</span>`).join("");
    $("users").innerHTML=data.users.map(user=>`<div class="card ${user.disabled?"disabled":""}"><div class="head"><span class="name">${esc(user.username)}</span><span class="${user.disabled?"bad":(user.online?"ok":"muted")}">${user.disabled?"已禁用":(user.online?"在线 "+user.online+" 台":"离线")}</span></div><div class="stats"><div class="stat"><span class="label">月上传</span><b>${bytes(user.upload)}</b></div><div class="stat"><span class="label">月下载</span><b>${bytes(user.download)}</b></div><div class="stat"><span class="label">月合计</span><b>${bytes(user.total)}</b></div></div><div class="muted" style="margin-bottom:12px">${user.note?`设备：${esc(user.note)} · `:""}速率模式：${esc(user.mode||"BBR 自动估速")} · 最后活动：${esc(user.last_active)} · 历史累计：${bytes(user.lifetime_total)}</div><div class="actions"><button class="btn primary" data-cred="${esc(user.username)}" data-kind="subscription">复制订阅</button><button class="btn" data-cred="${esc(user.username)}" data-kind="direct">复制基础直链</button><button class="btn" data-cred="${esc(user.username)}" data-kind="password">复制密码</button><button class="btn" data-note="${esc(user.username)}" data-value="${esc(user.note||"")}">备注</button><button class="btn ${user.disabled?"primary":"bad"}" data-toggle="${esc(user.username)}" data-disabled="${user.disabled?"1":"0"}">${user.disabled?"启用":"禁用"}</button></div></div>`).join("");
    document.querySelectorAll("[data-cred]").forEach(button=>{button.onclick=()=>copyCredential(button.dataset.cred,button.dataset.kind,button)});
    document.querySelectorAll("[data-note]").forEach(button=>{button.onclick=()=>setNote(button.dataset.note,button)});
    document.querySelectorAll("[data-toggle]").forEach(button=>{button.onclick=()=>toggleUser(button.dataset.toggle,button)});
    $("error").style.display=data.errors.length?"block":"none";$("error").textContent=data.errors.join("；");
  }catch(error){$("error").style.display="block";$("error").textContent="读取失败："+error.message}
}
load();setInterval(load,30000);
</script>
</body>
</html>
HTML

  chown -R root:caddy "$WEB_DIR"
  find "$WEB_DIR" -type d -exec chmod 0750 {} \;
  find "$WEB_DIR" -type f -exec chmod 0640 {} \;
}
