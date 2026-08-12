#!/usr/bin/env bash
# panel.sh - Web 面板 HTML 生成

write_panel() {
  install -d -o hy2-aio -g caddy -m 2750 "$WEB_DIR" "$WEB_DIR/downloads"
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
.top,.head,.toolbar{display:flex;justify-content:space-between;align-items:center;gap:14px}.top{align-items:flex-end}
h1{font-size:26px;margin:0}.muted,.label{color:#737780}.actions,.services{display:flex;gap:8px;flex-wrap:wrap}
.btn,.pill{border:1px solid #d9dce1;border-radius:11px;background:#fff;color:inherit;text-decoration:none;padding:9px 12px;cursor:pointer;font:inherit}
.btn.primary{background:#17191c;color:#fff;border-color:#17191c}.btn.bad{color:#b42318;border-color:#f0b8b2}
.btn:disabled{opacity:.55;cursor:wait}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-top:20px}
.card{background:#fff;border:1px solid #e3e5e8;border-radius:17px;padding:17px}
.value{font-size:21px;font-weight:760;margin-top:5px}.bar{height:8px;background:#eceef1;border-radius:8px;overflow:hidden;margin-top:13px}
.bar i{display:block;height:100%;background:#17191c}.ok{color:#137547;border-color:#b9dec9}.bad{color:#b42318;border-color:#f0b8b2}.card.disabled{opacity:.55}
.users{display:grid;grid-template-columns:repeat(2,1fr);gap:12px}.name{font-weight:750;font-size:17px}
.stats{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin:14px 0}.stat{background:#f5f6f8;border-radius:11px;padding:10px}.stat b{display:block}
h2{font-size:17px;margin:27px 0 12px}
.notice{display:none;margin-top:14px;padding:12px 36px 12px 14px;background:#fff8e8;border:1px solid #f0dfaf;border-radius:12px;position:relative}
.notice.show{display:block}
.notice-close{position:absolute;top:8px;right:8px;width:28px;height:28px;border:0;border-radius:8px;background:transparent;color:#8a7a3a;cursor:pointer;font:inherit;font-size:18px;line-height:1}
.notice-close:hover{background:#f3e7c0}
.error{display:none;margin-top:14px;padding:12px 14px;background:#fff0ef;color:#b42318;border-radius:12px}
.footer{margin-top:26px;color:#777b82;font-size:12px}
.add-box{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:12px 0 0;padding:12px;background:#fff;border:1px solid #e3e5e8;border-radius:14px}
.input{border:1px solid #d9dce1;border-radius:10px;padding:9px 12px;font:inherit;min-width:160px;background:#fff}
.note-row{display:flex;gap:8px;align-items:center;margin-bottom:12px;flex-wrap:wrap}
.note-row .input{flex:1;min-width:140px}
.toast{position:fixed;right:16px;bottom:16px;background:#17191c;color:#fff;padding:12px 16px;border-radius:12px;opacity:0;pointer-events:none;transition:opacity .2s;z-index:20;max-width:320px}
.toast.show{opacity:1}
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
      <button id="syncBtn" class="btn primary" type="button">立即同步</button>
      <a class="btn" href="users.csv">用户 CSV</a>
      <a class="btn" href="history.csv">历史记录</a>
    </div>
  </div>

  <div id="error" class="error"></div>
  <div id="notice" class="notice" role="note">
    <button id="noticeClose" class="notice-close" type="button" aria-label="关闭提示">×</button>
    套餐用量以「本月整机流量」为准（网卡本地计数，尽量对齐云厂商限制）；Clash 订阅流量条与此同步。用户卡片是 HY2 代理分摊参考，各用户之和通常小于整机（差额含系统/面板等非代理流量）。云厂商控制台仍是最终账单。速率模式只写入 Clash 订阅。
  </div>

  <div class="grid">
    <div class="card">
      <div class="label">本月整机（对齐云厂商套餐）</div><div id="traffic" class="value">--</div>
      <div id="remain" class="muted">--</div><div class="bar"><i id="trafficBar" style="width:0"></i></div>
    </div>
    <div class="card"><div class="label">CPU / 负载</div><div id="cpu" class="value">--</div><div id="load" class="muted">--</div></div>
    <div class="card"><div class="label">内存 / Swap</div><div id="memory" class="value">--</div><div id="swap" class="muted">--</div></div>
    <div class="card"><div class="label">磁盘 / 运行时间</div><div id="disk" class="value">--</div><div id="uptime" class="muted">--</div></div>
  </div>

  <h2>服务状态</h2><div id="services" class="services"></div>
  <h2>用户管理</h2>
  <div class="add-box">
    <input id="newUser" class="input" type="text" maxlength="32" placeholder="新用户名（字母数字_ -）" autocomplete="off">
    <button id="addBtn" class="btn primary" type="button">添加用户</button>
  </div>
  <div id="users" class="users" style="margin-top:12px"></div>
  <div class="footer">轻量模式：60 秒轮询 + 操作后即时刷新。Clash 显示整机套餐进度；用户卡片为 HY2 分摊参考。</div>
</div>
<div id="toast" class="toast"></div>

<script>
const $=id=>document.getElementById(id);
const bytes=value=>{let n=Number(value||0),i=0;const u=["B","KB","MB","GB","TB"];while(n>=1000&&i<u.length-1){n/=1000;i++}return n.toFixed(i<2?2:1)+" "+u[i]};
const duration=seconds=>{seconds=Math.max(0,Math.floor(Number(seconds)||0));return Math.floor(seconds/86400)+" 天 "+Math.floor(seconds%86400/3600)+" 小时"};
const VALID_NAME=/^[A-Za-z0-9_-]{1,32}$/;
let toastTimer=null;

function toast(message){
  const node=$("toast");
  node.textContent=message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>node.classList.remove("show"),2200);
}
function el(tag,attrs={},...kids){
  const node=document.createElement(tag);
  for(const [key,value] of Object.entries(attrs||{})){
    if(value==null)continue;
    if(key==="className")node.className=value;
    else if(key==="text")node.textContent=value;
    else if(key==="style"&&typeof value==="object")Object.assign(node.style,value);
    else if(key.startsWith("on")&&typeof value==="function")node[key]=value;
    else if(key in node)node[key]=value;
    else node.setAttribute(key,value);
  }
  for(const kid of kids){
    if(kid==null||kid===false)continue;
    node.append(kid.nodeType?kid:document.createTextNode(String(kid)));
  }
  return node;
}
function clearNode(node){while(node.firstChild)node.removeChild(node.firstChild)}

async function copyText(text,button){
  try{await navigator.clipboard.writeText(text)}catch(e){prompt("复制下面内容：",text)}
  const old=button.textContent;button.textContent="已复制";setTimeout(()=>button.textContent=old,1200);
}
async function apiPost(path,payload){
  const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload||{}),cache:"no-store"});
  const result=await response.json().catch(()=>({}));
  if(!response.ok||!result.ok)throw new Error(result.error||("HTTP "+response.status));
  return result;
}
async function copyCredential(username,kind,button){
  const old=button.textContent;button.disabled=true;
  try{
    const result=await apiPost("api/user/credentials",{username,kind});
    await copyText(result.value,button);
  }catch(error){toast("复制失败："+error.message);button.textContent=old}
  button.disabled=false;
}
async function saveNote(username,input,button){
  const note=String(input.value||"").trim();
  if(note.length>100){toast("备注最长 100 字符");return}
  const old=button.textContent;button.disabled=true;button.textContent="保存中…";
  try{
    await apiPost("api/user/note",{username,note});
    toast("备注已保存");
    await load();
  }catch(error){toast("保存失败："+error.message)}
  button.disabled=false;button.textContent=old;
}
async function toggleUser(username,disabled){
  if(!disabled&&!confirm("确认禁用 "+username+"？该用户将立即无法连接，数据保留。"))return;
  try{
    await apiPost(disabled?"api/user/enable":"api/user/disable",{username});
    toast(disabled?"已启用 "+username:"已禁用 "+username);
    await load();
  }catch(error){toast("操作失败："+error.message)}
}
async function removeUser(username){
  if(!confirm("确认删除用户 "+username+"？此操作不可恢复。"))return;
  try{
    await apiPost("api/user/remove",{username});
    toast("已删除 "+username);
    await load();
  }catch(error){toast("删除失败："+error.message)}
}
async function rotateUser(username){
  if(!confirm("确认轮换 "+username+" 的密码与订阅 token？旧订阅将失效。"))return;
  try{
    await apiPost("api/user/rotate",{username});
    toast("已轮换 "+username+" 的密钥");
    await load();
  }catch(error){toast("轮换失败："+error.message)}
}
async function addUser(){
  const input=$("newUser");
  const username=String(input.value||"").trim();
  if(!VALID_NAME.test(username)){toast("用户名仅允许字母、数字、下划线、短横线，长度 1-32");return}
  const btn=$("addBtn");btn.disabled=true;
  try{
    await apiPost("api/user/add",{username});
    input.value="";
    toast("已添加 "+username);
    await load();
  }catch(error){toast("添加失败："+error.message)}
  btn.disabled=false;
}
async function syncNow(){
  const btn=$("syncBtn"),old=btn.textContent;
  btn.disabled=true;btn.textContent="同步中…";
  try{
    await apiPost("api/sync",{});
    await load();
    toast("同步完成");
    btn.textContent="同步完成";
  }catch(error){
    btn.textContent="同步失败";
    toast("同步失败："+error.message);
  }
  setTimeout(()=>{btn.disabled=false;btn.textContent=old},1200);
}
function renderServices(services){
  const root=$("services");clearNode(root);
  Object.entries(services||{}).forEach(([name,status])=>{
    root.append(el("span",{className:"pill "+(status==="active"?"ok":"bad"),text:name+"："+status}));
  });
}
function renderUsers(users){
  const root=$("users");clearNode(root);
  (users||[]).forEach(user=>{
    const statusClass=user.disabled?"bad":(user.online?"ok":"muted");
    const statusText=user.disabled?"已禁用":(user.online?"在线客户端 "+user.online:"离线");
    const meta="HY2 代理分摊 · 速率模式："+(user.mode||"BBR 自动估速")+" · 最后活动："+user.last_active+" · 历史累计："+bytes(user.lifetime_total);
    const noteInput=el("input",{className:"input",type:"text",maxLength:100,value:user.note||"",placeholder:"设备备注（如 iPhone 13）"});
    const card=el("div",{className:"card"+(user.disabled?" disabled":"")},
      el("div",{className:"head"},
        el("span",{className:"name",text:user.username}),
        el("span",{className:statusClass,text:statusText})
      ),
      el("div",{className:"stats"},
        el("div",{className:"stat"},el("span",{className:"label",text:"HY2 月上传"}),el("b",{text:bytes(user.upload)})),
        el("div",{className:"stat"},el("span",{className:"label",text:"HY2 月下载"}),el("b",{text:bytes(user.download)})),
        el("div",{className:"stat"},el("span",{className:"label",text:"HY2 月合计"}),el("b",{text:bytes(user.total)}))
      ),
      el("div",{className:"muted",style:{marginBottom:"10px"},text:meta}),
      el("div",{className:"note-row"},
        noteInput,
        el("button",{className:"btn",type:"button",text:"保存备注",onclick:function(){saveNote(user.username,noteInput,this)}})
      ),
      el("div",{className:"actions"},
        el("button",{className:"btn primary",type:"button",text:"复制订阅",onclick:function(){copyCredential(user.username,"subscription",this)}}),
        el("button",{className:"btn",type:"button",text:"复制直链",onclick:function(){copyCredential(user.username,"direct",this)}}),
        el("button",{className:"btn",type:"button",text:"复制密码",onclick:function(){copyCredential(user.username,"password",this)}}),
        el("button",{className:"btn "+(user.disabled?"primary":"bad"),type:"button",text:user.disabled?"启用":"禁用",onclick:function(){toggleUser(user.username,!!user.disabled)}}),
        el("button",{className:"btn",type:"button",text:"轮换密钥",onclick:function(){rotateUser(user.username)}}),
        el("button",{className:"btn bad",type:"button",text:"删除",onclick:function(){removeUser(user.username)}})
      )
    );
    root.append(card);
  });
}
async function load(){
  try{
    const response=await fetch("data.json?t="+Date.now(),{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    const data=await response.json(),t=data.server.traffic;
    $("time").textContent="更新时间："+data.generated_at+" · "+data.server.ip+" · "+data.server.domain;
    $("traffic").textContent=bytes(t.used)+" / "+bytes(t.limit);
    $("remain").textContent="入站 "+bytes(t.rx)+" · 出站 "+bytes(t.tx)+" · 套餐剩余 "+bytes(t.remain)+" · "+Number(t.percent).toFixed(3)+"%";
    $("trafficBar").style.width=Math.min(100,Number(t.percent)||0)+"%";
    $("cpu").textContent=data.server.cpu+"%";$("load").textContent="负载 "+data.server.load.join(" / ");
    $("memory").textContent=data.server.memory.percent+"%";$("swap").textContent="Swap "+data.server.memory.swap_percent+"%";
    $("disk").textContent=data.server.disk.percent+"%";$("uptime").textContent="运行 "+duration(data.server.uptime);
    renderServices(data.server.services);
    renderUsers(data.users);
    $("error").style.display=data.errors.length?"block":"none";
    $("error").textContent=data.errors.join("；");
  }catch(error){
    $("error").style.display="block";
    $("error").textContent="读取失败："+error.message;
  }
}
$("syncBtn").onclick=syncNow;
$("addBtn").onclick=addUser;
$("newUser").addEventListener("keydown",event=>{if(event.key==="Enter")addUser()});
const NOTICE_KEY="hy2-aio-notice-dismissed-v2";
if(localStorage.getItem(NOTICE_KEY)!=="1")$("notice").classList.add("show");
$("noticeClose").onclick=()=>{
  $("notice").classList.remove("show");
  try{localStorage.setItem(NOTICE_KEY,"1")}catch(e){}
};
load();
setInterval(load,60000);
</script>
</body>
</html>
HTML

  chown -R hy2-aio:caddy "$WEB_DIR"
  find "$WEB_DIR" -type d -exec chmod 2750 {} \;
  find "$WEB_DIR" -type f -exec chmod 0640 {} \;
}
