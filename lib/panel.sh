#!/usr/bin/env bash
# panel.sh - Web 面板 HTML 生成

write_panel() {
  install -d -o hy2-aio -g caddy -m 2750 "$WEB_DIR" "$WEB_DIR/downloads"
  log "写入面板：${WEB_DIR}/index.html"
  cat > "$WEB_DIR/index.html" <<'HTML'
<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>HY2 AIO</title>
<style>
:root{
  --bg:#f0f2f5;--panel:#fff;--line:#e5e7eb;--text:#111827;--muted:#6b7280;
  --accent:#0f172a;--ok:#047857;--bad:#b91c1c;--hover:#f8fafc;
  --drawer:320px;--radius:10px;
  font-family:"Segoe UI",ui-sans-serif,system-ui,-apple-system,sans-serif;
  color:var(--text);background:var(--bg);
}
*{box-sizing:border-box}body{margin:0;min-height:100vh}
a{color:inherit}
.shell{min-height:100vh;display:flex;flex-direction:column}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;
  padding:14px 20px;background:var(--panel);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30}
.brand{display:flex;flex-direction:column;gap:2px;min-width:0}
.brand h1{margin:0;font-size:18px;font-weight:700;letter-spacing:.02em}
.brand .sub{font-size:12px;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
.top-actions{display:flex;gap:8px;flex-shrink:0}
.btn{border:1px solid var(--line);border-radius:8px;background:var(--panel);color:inherit;
  padding:8px 12px;font:inherit;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px}
.btn:hover{background:var(--hover)}.btn:disabled{opacity:.55;cursor:wait}
.btn.primary{background:var(--accent);color:#fff;border-color:var(--accent)}
.btn.bad{color:var(--bad);border-color:#fecaca}
.btn.ghost{border-color:transparent;background:transparent}
.btn.ghost:hover{background:var(--hover)}
.main{flex:1;padding:20px;max-width:1100px;width:100%;margin:0 auto}
.metrics{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:18px}
.metric{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);padding:14px 16px}
.metric .label{font-size:12px;color:var(--muted)}.metric .value{font-size:20px;font-weight:700;margin-top:6px}
.metric .extra{font-size:12px;color:var(--muted);margin-top:4px}
.bar{height:6px;background:#eef0f3;border-radius:99px;overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;background:var(--accent)}
.section{margin-top:8px}
.section-h{display:flex;align-items:baseline;justify-content:space-between;gap:10px;margin:0 0 10px}
.section-h h2{margin:0;font-size:14px;font-weight:700;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}
.pills{display:flex;flex-wrap:wrap;gap:8px}
.pill{font-size:12px;padding:6px 10px;border-radius:999px;border:1px solid var(--line);background:var(--panel)}
.pill.ok{color:var(--ok);border-color:#a7f3d0;background:#ecfdf5}
.pill.bad{color:var(--bad);border-color:#fecaca;background:#fef2f2}
.pill.off{color:#92400e;border-color:#fde68a;background:#fffbeb}
.table-wrap{background:var(--panel);border:1px solid var(--line);border-radius:var(--radius);overflow:hidden}
table{width:100%;border-collapse:collapse}
th,td{padding:12px 14px;text-align:left;border-bottom:1px solid var(--line);font-size:14px;vertical-align:middle}
th{font-size:12px;color:var(--muted);font-weight:600;background:#fafbfc}
tr:last-child td{border-bottom:0}
tr:hover td{background:var(--hover)}
tr.disabled td{opacity:.55}
.user-cell{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap}
.user-name{font-weight:650}
.user-note{color:var(--muted);font-size:13px}
.status-cell{display:flex;flex-direction:column;gap:2px;align-items:flex-start}
.status-dot{display:inline-flex;align-items:center;gap:6px}
.status-dot::before{content:"";width:7px;height:7px;border-radius:50%;background:#d1d5db}
.status-dot.on::before{background:var(--ok)}.status-dot.off::before{background:#9ca3af}
.status-dot.ban::before{background:var(--bad)}
.status-active{font-size:12px;color:var(--muted)}
.ops{position:relative;text-align:right}
.menu-btn{width:34px;height:34px;border-radius:8px;border:1px solid transparent;background:transparent;
  cursor:pointer;font:inherit;font-size:18px;line-height:1;color:var(--muted)}
.menu-btn:hover,.menu-btn.open{background:var(--hover);border-color:var(--line);color:var(--text)}
.menu{display:none;position:fixed;min-width:168px;background:var(--panel);
  border:1px solid var(--line);border-radius:10px;box-shadow:0 12px 32px rgba(15,23,42,.12);padding:6px;z-index:45}
.menu.open{display:block}
.menu button{display:block;width:100%;text-align:left;border:0;background:transparent;padding:9px 10px;
  border-radius:7px;font:inherit;cursor:pointer;color:var(--text)}
.menu button:hover{background:var(--hover)}
.menu button.bad{color:var(--bad)}
.menu .sep{height:1px;background:var(--line);margin:5px 4px}
.notice,.error{display:none;margin:0 0 14px;padding:12px 14px;border-radius:var(--radius);font-size:13px;line-height:1.5}
.notice.show,.error.show{display:block}
.notice{background:#fffbeb;border:1px solid #fde68a;color:#92400e;position:relative;padding-right:36px}
.notice-close{position:absolute;top:6px;right:6px;width:28px;height:28px;border:0;border-radius:8px;
  background:transparent;cursor:pointer;font:inherit;color:#92400e}
.error{background:#fef2f2;border:1px solid #fecaca;color:var(--bad);position:relative;padding-right:36px}
.error .notice-close{color:var(--bad)}
.footer{margin-top:18px;font-size:12px;color:var(--muted)}
.scrim{display:none;position:fixed;inset:0;background:rgba(15,23,42,.35);z-index:50}
.scrim.open{display:block}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(var(--drawer),100%);background:var(--panel);
  border-left:1px solid var(--line);z-index:60;transform:translateX(100%);transition:transform .22s ease;
  display:flex;flex-direction:column;box-shadow:-12px 0 40px rgba(15,23,42,.12)}
.drawer.open{transform:translateX(0)}
.drawer-h{display:flex;align-items:center;justify-content:space-between;padding:16px 18px;border-bottom:1px solid var(--line)}
.drawer-h h2{margin:0;font-size:16px}
.drawer-b{padding:16px 18px;overflow:auto;flex:1}
.drawer-sec{margin-bottom:22px}
.drawer-sec h3{margin:0 0 10px;font-size:12px;text-transform:uppercase;letter-spacing:.05em;color:var(--muted)}
.stack{display:flex;flex-direction:column;gap:8px}
.input{border:1px solid var(--line);border-radius:8px;padding:10px 12px;font:inherit;width:100%;background:#fff}
.hint{font-size:12px;color:var(--muted);line-height:1.45;margin:0}
.toast{position:fixed;right:16px;bottom:16px;background:var(--accent);color:#fff;padding:12px 16px;
  border-radius:10px;opacity:0;pointer-events:none;transition:opacity .2s;z-index:80;max-width:320px;font-size:13px}
.toast.show{opacity:1}
.modal-scrim{display:none;position:fixed;inset:0;background:rgba(15,23,42,.4);z-index:70;align-items:center;justify-content:center;padding:16px}
.modal-scrim.open{display:flex}
.modal{background:var(--panel);border-radius:12px;border:1px solid var(--line);width:min(400px,100%);padding:18px;box-shadow:0 20px 50px rgba(15,23,42,.2)}
.modal h3{margin:0 0 6px;font-size:16px}
.modal .hint{margin-bottom:12px}
.modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
@media(max-width:900px){.metrics{grid-template-columns:repeat(2,1fr)}}
.traffic-up{color:#0369a1}.traffic-down{color:#047857}
@media(max-width:720px){
  th:nth-child(5),td:nth-child(5){display:none}
}
@media(max-width:560px){
  .metrics{grid-template-columns:1fr}.main{padding:14px}
  th:nth-child(3),td:nth-child(3),th:nth-child(4),td:nth-child(4){display:none}
  .topbar{padding:12px 14px}
}
</style>
</head>
<body>
<div class="shell">
  <header class="topbar">
    <div class="brand">
      <h1>HY2 AIO</h1>
      <div id="time" class="sub">正在读取数据…</div>
    </div>
    <div class="top-actions">
      <button id="syncBtn" class="btn primary" type="button">同步</button>
      <button id="menuBtn" class="btn" type="button" aria-haspopup="dialog">菜单</button>
    </div>
  </header>

  <main class="main">
    <div id="error" class="error">
      <button id="errorClose" class="notice-close" type="button" aria-label="关闭">×</button>
      <span id="errorText"></span>
    </div>
    <div id="hy2OffBanner" class="notice" role="status">
      HY2 已关闭。UDP 未监听，客户端无法连接。整机流量仍计入面板与 SSH。
    </div>
    <div id="notice" class="notice" role="note">
      <button id="noticeClose" class="notice-close" type="button" aria-label="关闭">×</button>
      套餐用量以「本月整机流量」为准（网卡本地计数，对齐云厂商限制）；Clash 订阅进度与此同步。用户表为 HY2 代理分摊参考。云厂商控制台仍是最终账单。
    </div>

    <div class="metrics">
      <div class="metric">
        <div class="label">本月整机（对齐云厂商）</div>
        <div id="traffic" class="value">--</div>
        <div id="remain" class="extra">--</div>
        <div class="bar"><i id="trafficBar" style="width:0"></i></div>
      </div>
      <div class="metric"><div class="label">CPU / 负载</div><div id="cpu" class="value">--</div><div id="load" class="extra">--</div></div>
      <div class="metric"><div class="label">内存 / Swap</div><div id="memory" class="value">--</div><div id="swap" class="extra">--</div></div>
      <div class="metric"><div class="label">磁盘 / 运行</div><div id="disk" class="value">--</div><div id="uptime" class="extra">--</div></div>
    </div>

    <section class="section">
      <div class="section-h">
        <h2>服务</h2>
        <button id="hy2Toggle" class="btn" type="button">关闭 HY2</button>
      </div>
      <div id="services" class="pills"></div>
    </section>

    <section class="section" style="margin-top:22px">
      <div class="section-h">
        <h2>用户</h2>
        <span id="userSummary" class="hint"></span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>用户</th>
              <th>状态</th>
              <th>上行</th>
              <th>下行</th>
              <th>合计</th>
              <th style="text-align:right;width:52px">操作</th>
            </tr>
          </thead>
          <tbody id="users"></tbody>
        </table>
      </div>
    </section>
    <div class="footer">60 秒自动刷新 · 操作后即时更新</div>
  </main>
</div>

<div id="scrim" class="scrim"></div>
<aside id="drawer" class="drawer" aria-hidden="true">
  <div class="drawer-h">
    <h2>功能菜单</h2>
    <button id="drawerClose" class="btn ghost" type="button" aria-label="关闭">×</button>
  </div>
  <div class="drawer-b">
    <div class="drawer-sec">
      <h3>用户</h3>
      <div class="stack">
        <input id="newUser" class="input" type="text" maxlength="32" placeholder="新用户名（字母数字 _ -）" autocomplete="off">
        <button id="addBtn" class="btn primary" type="button">添加用户</button>
        <p class="hint">添加后会重建配置；HY2 开启时会短暂重启 Hysteria。全员禁用会自动关闭 HY2。</p>
      </div>
    </div>
    <div class="drawer-sec">
      <h3>数据</h3>
      <div class="stack">
        <button id="drawerSync" class="btn" type="button">立即同步</button>
        <a class="btn" href="users.csv">下载用户 CSV</a>
        <a class="btn" href="history.csv">下载历史记录</a>
      </div>
    </div>
    <div class="drawer-sec">
      <h3>说明</h3>
      <p class="hint">整机流量对齐云厂商套餐；用户行为 HY2 分摊参考。速率模式只写入 Clash 订阅。</p>
    </div>
  </div>
</aside>

<div id="noteModal" class="modal-scrim" role="dialog" aria-modal="true" aria-labelledby="noteTitle">
  <div class="modal">
    <h3 id="noteTitle">修改备注</h3>
    <p id="noteHint" class="hint"></p>
    <input id="noteInput" class="input" type="text" maxlength="100" placeholder="例如 iPhone 13、笔记本">
    <div class="modal-actions">
      <button id="noteCancel" class="btn" type="button">取消</button>
      <button id="noteSave" class="btn primary" type="button">保存</button>
    </div>
  </div>
</div>

<div id="toast" class="toast"></div>

<script>
const $=id=>document.getElementById(id);
const bytes=value=>{let n=Number(value||0),i=0;const u=["B","KB","MB","GB","TB"];while(n>=1000&&i<u.length-1){n/=1000;i++}return n.toFixed(i<2?2:1)+" "+u[i]};
const duration=seconds=>{seconds=Math.max(0,Math.floor(Number(seconds)||0));return Math.floor(seconds/86400)+" 天 "+Math.floor(seconds%86400/3600)+" 小时"};
const formatActive=raw=>{
  if(!raw||raw==="从未")return "从未";
  const d=new Date(raw);
  if(Number.isNaN(d.getTime()))return String(raw);
  const p=n=>String(n).padStart(2,"0");
  return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());
};
const VALID_NAME=/^[A-Za-z0-9_-]{1,32}$/;
let toastTimer=null, openMenu=null, noteUser="";

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
function closeMenus(){
  if(openMenu){
    openMenu.classList.remove("open");
    const btn=openMenu._btn;
    if(btn)btn.classList.remove("open");
    openMenu.style.top="";openMenu.style.bottom="";openMenu.style.left="";openMenu.style.right="";
    openMenu=null;
  }
}
function positionMenu(menu,btn){
  const r=btn.getBoundingClientRect();
  const width=Math.max(menu.offsetWidth||168,168);
  const left=Math.min(Math.max(8,r.right-width),window.innerWidth-width-8);
  menu.style.left=left+"px";
  menu.style.right="auto";
  const spaceBelow=window.innerHeight-r.bottom;
  const spaceAbove=r.top;
  if(spaceBelow<260&&spaceAbove>spaceBelow){
    menu.style.top="auto";
    menu.style.bottom=(window.innerHeight-r.top+4)+"px";
  }else{
    menu.style.bottom="auto";
    menu.style.top=(r.bottom+4)+"px";
  }
}
function setDrawer(open){
  $("drawer").classList.toggle("open",open);
  $("scrim").classList.toggle("open",open);
  $("drawer").setAttribute("aria-hidden",open?"false":"true");
  if(open)closeMenus();
}
function setNoteModal(open,username,note){
  $("noteModal").classList.toggle("open",open);
  if(open){
    noteUser=username||"";
    $("noteHint").textContent="用户 "+noteUser;
    $("noteInput").value=note||"";
    setTimeout(()=>$("noteInput").focus(),50);
  }else noteUser="";
}

async function copyText(text){
  try{await navigator.clipboard.writeText(text)}catch(e){prompt("复制下面内容：",text)}
}
async function apiPost(path,payload){
  const response=await fetch(path,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload||{}),cache:"no-store"});
  const result=await response.json().catch(()=>({}));
  if(!response.ok||!result.ok)throw new Error(result.error||("HTTP "+response.status));
  return result;
}
async function copyCredential(username,kind){
  closeMenus();
  try{
    const result=await apiPost("api/user/credentials",{username,kind});
    await copyText(result.value);
    toast("已复制");
  }catch(error){toast("复制失败："+error.message)}
}
async function saveNote(){
  const note=String($("noteInput").value||"").trim();
  if(note.length>100){toast("备注最长 100 字符");return}
  const btn=$("noteSave");btn.disabled=true;
  try{
    await apiPost("api/user/note",{username:noteUser,note});
    setNoteModal(false);
    toast("备注已保存");
    await load();
  }catch(error){toast("保存失败："+error.message)}
  btn.disabled=false;
}
async function toggleUser(username,disabled){
  closeMenus();
  if(!disabled&&!confirm("确认禁用 "+username+"？该用户将立即无法连接，数据保留。"))return;
  try{
    const result=await apiPost(disabled?"api/user/enable":"api/user/disable",{username});
    toast(result.message||(disabled?"已启用 "+username:"已禁用 "+username));
    await load();
  }catch(error){toast("操作失败："+error.message)}
}
async function removeUser(username){
  closeMenus();
  if(!confirm("确认删除用户 "+username+"？此操作不可恢复。"))return;
  try{
    await apiPost("api/user/remove",{username});
    toast("已删除 "+username);
    await load();
  }catch(error){toast("删除失败："+error.message)}
}
async function rotateUser(username){
  closeMenus();
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
    setDrawer(false);
    await load();
  }catch(error){toast("添加失败："+error.message)}
  btn.disabled=false;
}
async function syncNow(){
  const buttons=[$("syncBtn"),$("drawerSync")];
  buttons.forEach(b=>{b.disabled=true});
  $("syncBtn").textContent="同步中…";
  try{
    await apiPost("api/sync",{});
    await load();
    toast("同步完成");
  }catch(error){toast("同步失败："+error.message)}
  buttons.forEach(b=>{b.disabled=false});
  $("syncBtn").textContent="同步";
}

function renderServices(services){
  const root=$("services");clearNode(root);
  Object.entries(services||{}).forEach(([name,status])=>{
    let cls="bad", label=status;
    if(status==="active")cls="ok";
    else if(status==="off"){cls="off";label="已关闭"}
    root.append(el("span",{className:"pill "+cls,text:name+"："+label}));
  });
}
async function toggleHy2(){
  const enabled=window.__hy2Enabled!==false;
  if(enabled&&!confirm("确认关闭 Hysteria？客户端将无法连接。"))return;
  const btn=$("hy2Toggle");
  if(btn)btn.disabled=true;
  try{
    await apiPost(enabled?"api/hy2/off":"api/hy2/on",{});
    toast(enabled?"HY2 已关闭":"HY2 已开启");
    await load();
  }catch(error){toast("操作失败："+error.message)}
  if(btn)btn.disabled=false;
}
function menuItem(text,handler,bad){
  return el("button",{type:"button",className:bad?"bad":"",text,onclick:handler});
}
function renderUsers(users){
  const root=$("users");clearNode(root);
  const list=users||[];
  $("userSummary").textContent=list.length+" 个账号";
  if(!list.length){
    root.append(el("tr",{},el("td",{colSpan:6,className:"hint",text:"暂无用户。打开右上角菜单添加。"})));
    return;
  }
  list.forEach(user=>{
    const note=String(user.note||"").trim();
    const statusClass=user.disabled?"ban":(user.online?"on":"off");
    const statusText=user.disabled?"已禁用":(user.online?"在线 "+user.online:"离线");
    const statusCell=el("div",{className:"status-cell"},
      el("span",{className:"status-dot "+statusClass,text:statusText}),
      el("span",{className:"status-active",text:"最后 "+formatActive(user.last_active)})
    );
    const menu=el("div",{className:"menu"});
    const btn=el("button",{className:"menu-btn",type:"button",title:"操作",text:"⋯",onclick:function(event){
      event.stopPropagation();
      const willOpen=!menu.classList.contains("open");
      closeMenus();
      if(willOpen){
        menu.classList.add("open");
        btn.classList.add("open");
        menu._btn=btn;
        openMenu=menu;
        positionMenu(menu,btn);
      }
    }});
    menu.append(
      menuItem("复制订阅",()=>copyCredential(user.username,"subscription")),
      menuItem("复制直链",()=>copyCredential(user.username,"direct")),
      menuItem("复制密码",()=>copyCredential(user.username,"password")),
      el("div",{className:"sep"}),
      menuItem("改备注",()=>{closeMenus();setNoteModal(true,user.username,note)}),
      menuItem("轮换密钥",()=>rotateUser(user.username)),
      menuItem(user.disabled?"启用":"禁用",()=>toggleUser(user.username,!!user.disabled),!user.disabled),
      el("div",{className:"sep"}),
      menuItem("删除",()=>removeUser(user.username),true)
    );
    const nameCell=el("div",{className:"user-cell"},
      el("span",{className:"user-name",text:user.username}),
      note?el("span",{className:"user-note",text:"("+note+")"}):null
    );
    root.append(el("tr",{className:user.disabled?"disabled":""},
      el("td",{},nameCell),
      el("td",{},statusCell),
      el("td",{className:"traffic-up",text:"↑ "+bytes(user.upload)}),
      el("td",{className:"traffic-down",text:"↓ "+bytes(user.download)}),
      el("td",{text:bytes(user.total)}),
      el("td",{className:"ops"},btn,menu)
    ));
  });
}
async function load(){
  try{
    const response=await fetch("data.json?t="+Date.now(),{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    const data=await response.json(),t=data.server.traffic;
    $("time").textContent="更新 "+data.generated_at+" · "+data.server.ip+" · "+data.server.domain;
    $("traffic").textContent=bytes(t.used)+" / "+bytes(t.limit);
    $("remain").textContent="入 "+bytes(t.rx)+" · 出 "+bytes(t.tx)+" · 剩余 "+bytes(t.remain);
    $("trafficBar").style.width=Math.min(100,Number(t.percent)||0)+"%";
    $("cpu").textContent=data.server.cpu+"%";$("load").textContent="负载 "+data.server.load.join(" / ");
    $("memory").textContent=data.server.memory.percent+"%";$("swap").textContent="Swap "+data.server.memory.swap_percent+"%";
    $("disk").textContent=data.server.disk.percent+"%";$("uptime").textContent="运行 "+duration(data.server.uptime);
    renderServices(data.server.services);
    const hy2On=data.server.hy2_enabled!==false;
    window.__hy2Enabled=hy2On;
    $("hy2OffBanner").classList.toggle("show",!hy2On);
    const toggle=$("hy2Toggle");
    if(toggle){
      toggle.textContent=hy2On?"关闭 HY2":"开启 HY2";
      toggle.classList.toggle("bad",hy2On);
    }
    renderUsers(data.users);
    $("errorText").textContent=(data.errors||[]).join("；");
    const errorText=$("errorText").textContent;
    const dismissed=(()=>{try{return localStorage.getItem(ERROR_KEY)}catch(e){return ""}})();
    $("error").classList.toggle("show",!!errorText&&dismissed!==errorText);
  }catch(error){
    $("errorText").textContent="读取失败："+error.message;
    $("error").classList.add("show");
  }
}

$("hy2Toggle").onclick=toggleHy2;
$("syncBtn").onclick=syncNow;
$("drawerSync").onclick=()=>{setDrawer(false);syncNow()};
$("menuBtn").onclick=()=>setDrawer(true);
$("drawerClose").onclick=()=>setDrawer(false);
$("scrim").onclick=()=>setDrawer(false);
$("addBtn").onclick=addUser;
$("newUser").addEventListener("keydown",event=>{if(event.key==="Enter")addUser()});
$("noteCancel").onclick=()=>setNoteModal(false);
$("noteSave").onclick=saveNote;
$("noteInput").addEventListener("keydown",event=>{if(event.key==="Enter")saveNote()});
$("noteModal").addEventListener("click",event=>{if(event.target===$("noteModal"))setNoteModal(false)});
document.addEventListener("click",closeMenus);
document.addEventListener("scroll",()=>{if(openMenu&&openMenu._btn)positionMenu(openMenu,openMenu._btn)},true);
window.addEventListener("resize",()=>{if(openMenu&&openMenu._btn)positionMenu(openMenu,openMenu._btn)});
document.addEventListener("keydown",event=>{
  if(event.key==="Escape"){closeMenus();setDrawer(false);setNoteModal(false)}
});
const NOTICE_KEY="hy2-aio-notice-dismissed-v3";
const ERROR_KEY="hy2-aio-error-dismissed";
if(localStorage.getItem(NOTICE_KEY)!=="1")$("notice").classList.add("show");
$("noticeClose").onclick=()=>{
  $("notice").classList.remove("show");
  try{localStorage.setItem(NOTICE_KEY,"1")}catch(e){}
};
$("errorClose").onclick=()=>{
  $("error").classList.remove("show");
  try{localStorage.setItem(ERROR_KEY,$("errorText").textContent)}catch(e){}
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
