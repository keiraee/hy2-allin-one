const $=id=>document.getElementById(id);
const bytes=value=>{let n=Number(value||0),i=0;const u=["B","KB","MB","GB","TB"];while(n>=1000&&i<u.length-1){n/=1000;i++}return n.toFixed(i<2?2:1)+" "+u[i]};
const duration=seconds=>{seconds=Math.max(0,Math.floor(Number(seconds)||0));return Math.floor(seconds/86400)+" 天 "+Math.floor(seconds%86400/3600)+" 小时"};
// data.json 是后端每 60s 落一次的静态快照，页面看到的永远是「某个时刻」的数字。
// 把「这份数据有多旧」直接标出来，用户就不会把 55 秒前的 CPU 当成实时值。
const dataAgeText=raw=>{
  if(!raw)return "";
  const t=new Date(raw);
  if(Number.isNaN(t.getTime()))return "";
  const sec=Math.max(0,Math.round((Date.now()-t.getTime())/1000));
  if(sec<70)return sec+" 秒前";
  if(sec<3600)return Math.round(sec/60)+" 分钟前";
  return Math.round(sec/3600)+" 小时前";
};
const formatActive=raw=>{
  if(!raw||raw==="从未")return "从未";
  const d=new Date(raw);
  if(Number.isNaN(d.getTime()))return String(raw);
  const p=n=>String(n).padStart(2,"0");
  return d.getFullYear()+"-"+p(d.getMonth()+1)+"-"+p(d.getDate())+" "+p(d.getHours())+":"+p(d.getMinutes());
};
const VALID_NAME=/^[A-Za-z0-9_-]{1,32}$/;
const THEME_KEY="hy2-aio-theme";
function themeColor(name,fallback){
  const v=getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v||fallback||"";
}
function heatColors(){
  return document.documentElement.getAttribute("data-theme")==="dark"
    ?["#2a2a2a","#1c3554","#24558a","#2d6cb8","#3987e5","#5aa0f0"]
    :["#e9e9e7","#d4e4f7","#a8c8ee","#6ea4e0","#2a78d6","#1d5fad"];
}
function mixColors(){
  return document.documentElement.getAttribute("data-theme")==="dark"
    ?["#3987e5","#5aa0f0","#7ab3f2","#a3c4f0","#6f6f6c","#3a3a38"]
    :["#1d5fad","#2a78d6","#4a8fdc","#6ea4e0","#8c8c88","#c5c5c2"];
}
function currentTheme(){
  return document.documentElement.getAttribute("data-theme")==="dark"?"dark":"light";
}
function applyTheme(theme){
  const next=theme==="dark"?"dark":"light";
  document.documentElement.setAttribute("data-theme",next);
  try{localStorage.setItem(THEME_KEY,next)}catch(e){}
  const btn=$("themeBtn");
  if(btn){
    btn.setAttribute("aria-label",next==="dark"?"切换到浅色":"切换到深色");
    btn.replaceChildren(iconSvg(next==="dark"?"sun":"moon"));
  }
}
function initTheme(){
  let saved="";
  try{saved=localStorage.getItem(THEME_KEY)||""}catch(e){}
  if(saved==="dark"||saved==="light")applyTheme(saved);
  else if(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches)applyTheme("dark");
  else applyTheme("light");
}
let toastTimer=null, openMenu=null, noteUser="";
let mutateBusy=false;
let userList=[], liveList=[], siteList=[];
let userSort={key:"username",dir:1};
let liveSort={key:"total",dir:-1};
let siteSort={key:"total",dir:-1};

function toast(message){
  const node=$("toast");
  node.textContent=message;
  node.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer=setTimeout(()=>node.classList.remove("show"),2200);
}
function setBusyOverlay(open,message){
  const node=$("busyScrim");
  if(!node)return;
  node.classList.toggle("open",!!open);
  node.setAttribute("aria-hidden",open?"false":"true");
  node.setAttribute("aria-busy",open?"true":"false");
  const text=$("busyText");
  if(text)text.textContent=message||"处理中，请稍候…";
  if(open)closeMenus();
}
function buttonSpinner(){
  return el("span",{className:"btn-spin","aria-hidden":"true","data-busy-spin":"1"});
}
async function runMutate(button,work,message){
  if(mutateBusy)return;
  mutateBusy=true;
  const label=message||"处理中，请稍候…";
  setBusyOverlay(true,label);
  if(button){
    button.disabled=true;
    button.classList.add("is-busy");
    if(!button.querySelector("[data-busy-spin]"))button.prepend(buttonSpinner());
  }
  try{await work()}
  finally{
    mutateBusy=false;
    setBusyOverlay(false);
    if(button){
      button.querySelectorAll("[data-busy-spin]").forEach(node=>node.remove());
      button.classList.remove("is-busy");
      button.disabled=false;
    }
  }
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
  if(spaceBelow<300&&spaceAbove>spaceBelow){
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
function setTrafficModal(open){
  $("trafficModal").classList.toggle("open",!!open);
  $("trafficModal").setAttribute("aria-hidden",open?"false":"true");
  if(!open)return;
}
function pad2(n){return String(n).padStart(2,"0")}
function sortValue(row,key){
  if(key==="online")return row.disabled?-1:Number(row.online||0);
  if(key==="username"||key==="host"||key==="ip"||key==="client")return String(row[key]||row.client_ip||"");
  if(key==="port")return Number(row.port)||0;
  if(key==="upload"||key==="download"||key==="hits")return Number(row[key])||0;
  if(key==="total"||key==="bytes")return Number(row.total!=null?row.total:(Number(row.upload)||0)+(Number(row.download)||0));
  if(key==="lifetime_total")return Number(row.lifetime_total)||0;
  if(key==="share")return Number(row.share)||0;
  if(key==="state")return streamState(row.state);
  if(key==="last_seen"||key==="first_seen"||key==="last_active")return Date.parse(row[key])||0;
  return String(row[key]||"");
}
function sortedRows(list,sort){
  return [...(list||[])].sort((a,b)=>{
    const va=sortValue(a,sort.key), vb=sortValue(b,sort.key);
    let cmp;
    if(typeof va==="number"&&typeof vb==="number")cmp=va-vb;
    else cmp=String(va).localeCompare(String(vb),"en",{numeric:true});
    if(cmp===0&&sort.key==="total")cmp=(Number(a.hits)||0)-(Number(b.hits)||0);
    return cmp*sort.dir;
  });
}
function markSort(table,sort){
  if(!table)return;
  table.querySelectorAll("th[data-sort]").forEach(th=>{
    const on=th.getAttribute("data-sort")===sort.key;
    th.classList.toggle("active",on);
    th.setAttribute("data-dir",on?(sort.dir>0?"▲":"▼"):"");
    th.setAttribute("aria-sort",on?(sort.dir>0?"ascending":"descending"):"none");
  });
}
function bindSortHeaders(root,sort,apply){
  if(!root)return;
  root.querySelectorAll("th[data-sort]").forEach(th=>{
    th.onclick=()=>{
      const key=th.getAttribute("data-sort");
      if(sort.key===key)sort.dir*=-1;
      else{sort.key=key;sort.dir=(key==="username"||key==="host"||key==="client"||key==="ip")?1:-1;}
      apply();
    };
  });
}
function formatClock(raw){
  if(!raw||raw==="从未")return "--";
  const d=new Date(raw);
  if(Number.isNaN(d.getTime()))return String(raw);
  return pad2(d.getMonth()+1)+"-"+pad2(d.getDate())+" "+pad2(d.getHours())+":"+pad2(d.getMinutes())+":"+pad2(d.getSeconds());
}
function visitCell(raw){
  if(!raw)return el("td",{className:"hint",text:"--"});
  return el("td",{className:"visit-cell",title:formatActive(raw)},
    el("div",{text:formatClock(raw)}),
    el("div",{className:"hint",text:relTime(raw)})
  );
}
function relTime(raw){
  if(!raw||raw==="从未")return "从未";
  const d=new Date(raw);
  if(Number.isNaN(d.getTime()))return String(raw);
  const sec=Math.round((Date.now()-d.getTime())/1000);
  if(sec<0)return formatActive(raw);
  if(sec<45)return "刚刚";
  if(sec<3600)return Math.max(1,Math.round(sec/60))+" 分钟前";
  if(sec<86400)return Math.max(1,Math.round(sec/3600))+" 小时前";
  if(sec<7*86400)return Math.max(1,Math.round(sec/86400))+" 天前";
  return formatActive(raw);
}
function weekdayName(date){return "日一二三四五六".charAt(date.getDay())}
function chartEmpty(text){
  return el("div",{className:"chart-empty"},iconSvg("chart"),el("span",{text:text||"暂无数据"}));
}
function formatClientIps(list){
  if(!list||!list.length)return "暂无（用户连上后从连接日志采集）";
  return list.map(item=>{
    const addr=item.ip+(item.port?":"+item.port:"");
    return item.last_seen?addr+"（"+relTime(item.last_seen)+"）":addr;
  }).join("、");
}
function portName(port){
  const names={80:"HTTP",443:"HTTPS",53:"DNS",22:"SSH",853:"DoT",123:"NTP",25:"SMTP",465:"SMTPS",587:"SMTP",993:"IMAPS",995:"POP3S"};
  return names[String(port||"").trim()]||"";
}
function portLabel(port){
  const p=String(port||"").trim();
  if(!p)return "--";
  const name=portName(p);
  return name?p+" "+name:p;
}
function streamState(raw){
  const s=String(raw||"").toLowerCase();
  if(!s||s==="estab"||s==="established"||s==="open"||s==="active")return "进行中";
  if(s.indexOf("close")!==-1||s==="fin"||s==="end")return "已结束";
  return String(raw);
}
function siteSharePct(row,list){
  const bytesTotal=(list||[]).reduce((n,item)=>n+(Number(item.total)||0),0);
  const hitsTotal=(list||[]).reduce((n,item)=>n+(Number(item.hits)||0),0);
  if(bytesTotal)return (Number(row.total)||0)/bytesTotal*100;
  if(hitsTotal)return (Number(row.hits)||0)/hitsTotal*100;
  return 0;
}
function formatPct(n){
  const value=Number(n)||0;
  if(!value)return "0%";
  return (value>=10?value.toFixed(0):value.toFixed(1))+"%";
}
function formatDuration(seconds){
  seconds=Math.max(0,Math.floor(Number(seconds)||0));
  if(!seconds)return "";
  if(seconds<60)return seconds+" 秒";
  if(seconds<3600)return Math.max(1,Math.round(seconds/60))+" 分钟";
  const hours=Math.floor(seconds/3600), minutes=Math.round(seconds%3600/60);
  return hours+" 小时"+(minutes?" "+minutes+" 分钟":"");
}
function groupSitesByRoot(sites){
  const map={};
  (sites||[]).forEach(row=>{
    const key=row.root||row.host||"--";
    if(!map[key])map[key]={host:key,root:key,total:0,hits:0,upload:0,download:0,share:0};
    map[key].total+=Number(row.total)||0;
    map[key].hits+=Number(row.hits)||0;
    map[key].upload+=Number(row.upload)||0;
    map[key].download+=Number(row.download)||0;
  });
  const grouped=Object.values(map).sort((a,b)=>(b.total-a.total)||(b.hits-a.hits));
  return grouped.map(row=>Object.assign(row,{share:siteSharePct(row,grouped)}));
}
function dayKey(date){return date.getFullYear()+"-"+pad2(date.getMonth()+1)+"-"+pad2(date.getDate())}
function lastDays(n){
  const days=[], now=new Date();
  now.setHours(0,0,0,0);
  for(let i=n-1;i>=0;i--){
    const d=new Date(now);
    d.setDate(now.getDate()-i);
    days.push(d);
  }
  return days;
}
function heatColor(value,max,empty){
  const palette=heatColors();
  if(!value)return empty?themeColor("--surface-3",palette[0]):palette[0];
  if(!max)return palette[0];
  return palette[Math.min(palette.length-1,Math.max(1,Math.round(value/max*(palette.length-1))))];
}
function hourLabel(date){
  return pad2(date.getMonth()+1)+"/"+pad2(date.getDate())+" "+pad2(date.getHours())+":00";
}
async function openTraffic(username){
  closeMenus();
  setTrafficModal(true);
  $("trafficUser").textContent=username+" · 近 7 日";
  $("trafficSummary").textContent="正在整理 "+username+" 的用量…";
  $("trafficMonth").textContent="读取中…";
  $("trafficMonthExtra").textContent="--";
  $("trafficPeakVal").textContent="--";
  $("trafficPeakExtra").textContent="--";
  $("trafficBusyDay").textContent="--";
  $("trafficBusyExtra").textContent="--";
  $("trafficShare").textContent="--";
  $("trafficShareExtra").textContent="--";
  $("trafficLiveCount").textContent="--";
  $("trafficLiveExtra").textContent="--";
  $("trafficSiteCount").textContent="--";
  $("trafficSiteExtra").textContent="--";
  if($("trafficSessionAvg")){$("trafficSessionAvg").textContent="--";$("trafficSessionExtra").textContent="--"}
  if($("trafficDayShare")){$("trafficDayShare").textContent="--";$("trafficDayShareExtra").textContent="07:00–23:00"}
  if($("trafficDayNightVal"))$("trafficDayNightVal").textContent="--";
  if($("trafficLastSession"))$("trafficLastSession").textContent="--";
  if($("trafficSessionCount"))$("trafficSessionCount").textContent="--";
  $("trafficEgressLine").textContent="出口 IP：--";
  $("trafficClient").textContent="客户端：--";
  if($("trafficClients"))clearNode($("trafficClients"));
  clearNode($("trafficLive"));
  clearNode($("trafficSites"));
  if($("trafficSiteBars"))clearNode($("trafficSiteBars"));
  if($("trafficMix")){clearNode($("trafficMix"));$("trafficMix").classList.add("hide")}
  if($("trafficMixHint"))$("trafficMixHint").textContent="";
  $("trafficPeak").classList.remove("show");
  $("trafficEmpty").classList.remove("show");
  $("trafficCharts").classList.remove("hide");
  try{
    const result=await apiPost("api/user/traffic",{username});
    renderTraffic(result);
  }catch(error){
    setTrafficModal(false);
    toast("分析失败："+error.message);
  }
}
function svgNode(name,attrs,text){
  const node=document.createElementNS("http://www.w3.org/2000/svg",name);
  Object.entries(attrs||{}).forEach(([key,value])=>{
    if(value!=null&&value!=="")node.setAttribute(key,String(value));
  });
  if(text!=null&&text!=="")node.append(document.createTextNode(String(text)));
  return node;
}
// 客户端图标：优先用 icons/<name>-32.webp（1x）+ srcset 带 64（2x）。
// 图标文件是可选资源，装不上就 onerror 退回内置 sprite，绝不留空白。
function clientIcon(name){
  const img=document.createElement("img");
  img.className="ico client-ico";
  img.alt="";
  img.width=15; img.height=15;
  img.src="icons/"+name+"-32.webp";
  img.srcset="icons/"+name+"-32.webp 1x, icons/"+name+"-64.webp 2x";
  img.loading="lazy";
  img.onerror=function(){
    const svg=iconSvg(name);
    img.replaceWith(svg);
  };
  return img;
}
function iconSvg(name){
  const svg=svgNode("svg",{class:"ico",viewBox:"0 0 24 24","aria-hidden":"true"});
  svg.append(svgNode("use",{href:"#i-"+name}));
  return svg;
}
function setBtnIcon(node,name,label){
  if(!node)return;
  const kids=[iconSvg(name)];
  if(label)kids.push(document.createTextNode(label));
  node.replaceChildren(...kids);
}
function renderTraffic(data){
  const month=data.month||{};
  $("trafficMonth").textContent=bytes(month.total);
  $("trafficMonthExtra").textContent="上行 "+bytes(month.upload)+" · 下行 "+bytes(month.download)+(Number(month.lifetime_total)>Number(month.total)?(" · 累计 "+bytes(month.lifetime_total)):"");
  $("trafficShare").textContent=(Number(month.share_percent)||0).toFixed(1)+"%";
  $("trafficShareExtra").textContent=Number(month.share_percent)?"相对本月整机用量":"整机本月还没有用量";
  $("trafficSplitHint").textContent="本月 上行 "+bytes(month.upload)+" · 下行 "+bytes(month.download);
  renderSessionStats(data.sessions||{});
  renderDestinations(data);
  const total=Math.max(0,Number(month.total)||0);
  const upPct=total?Math.round(Number(month.upload||0)/total*100):0;
  const downPct=total?100-upPct:0;
  const split=$("trafficUpDown");clearNode(split);
  if(total){
    split.append(
      el("i",{className:"up",style:{width:upPct+"%"},text:"↑ "+bytes(month.upload)+"  "+upPct+"%"}),
      el("i",{className:"down",style:{width:Math.max(downPct,0)+"%"},text:"↓ "+bytes(month.download)+"  "+downPct+"%"})
    );
  }else{
    split.append(el("i",{className:"down",style:{width:"100%"},text:"暂无本月流量"}));
  }
  const series=Array.isArray(data.series)?data.series:[];
  const hasSeries=!!(data.has_history&&series.length);
  $("trafficEmpty").classList.toggle("show",!hasSeries);
  $("trafficCharts").classList.remove("hide");
  const days=lastDays(7);
  const hours=[...Array(24).keys()];
  const now=new Date();
  const heat={};
  const daily={};
  days.forEach(day=>{heat[dayKey(day)]=Array(24).fill(0);daily[dayKey(day)]={up:0,down:0,total:0,hits:0}});
  series.forEach(item=>{
    const d=new Date(item.t);
    if(Number.isNaN(d.getTime()))return;
    const key=dayKey(d);
    if(!heat[key])return;
    const up=Number(item.up)||0, down=Number(item.down)||0, hour=d.getHours();
    heat[key][hour]+=up+down;
    daily[key].up+=up;daily[key].down+=down;daily[key].total+=up+down;daily[key].hits+=1;
  });
  let maxHeat=0, peakCell=null, busy=null;
  days.forEach(day=>{
    const key=dayKey(day);
    hours.forEach(hour=>{
      const value=heat[key][hour];
      if(value>maxHeat){maxHeat=value;peakCell={key,hour,value,date:new Date(day.getFullYear(),day.getMonth(),day.getDate(),hour)}}
    });
    if(!busy||daily[key].total>busy.total)busy={key,total:daily[key].total,date:day,up:daily[key].up,down:daily[key].down};
  });
  if(!(peakCell&&peakCell.value))peakCell=null;
  if(!(busy&&busy.total))busy=null;
  $("trafficPeakVal").textContent=peakCell?("周"+weekdayName(peakCell.date)+" "+pad2(peakCell.hour)+":00"):"--";
  $("trafficPeakExtra").textContent=peakCell?("这一小时 "+bytes(peakCell.value)):"还没有高峰";
  $("trafficBusyDay").textContent=busy?(pad2(busy.date.getMonth()+1)+"月"+busy.date.getDate()+"日 周"+weekdayName(busy.date)):"--";
  $("trafficBusyExtra").textContent=busy?("当天 "+bytes(busy.total)+" · ↑ "+bytes(busy.up)+" · ↓ "+bytes(busy.down)):"还没有按日增量";
  $("trafficSummary").textContent=buildTrafficSummary(data,peakCell,busy);
  const peakNode=$("trafficPeak");
  if(peakCell){
    const endHour=(peakCell.hour+1)%24;
    peakNode.textContent="最近高峰在周"+weekdayName(peakCell.date)+" "+pad2(peakCell.hour)+":00–"+pad2(endHour)+":00，大约 "+bytes(peakCell.value)+"。热力图描红的那一格就是这里。";
    peakNode.classList.add("show");
  }else peakNode.classList.remove("show");
  const heatRoot=$("trafficHeat");clearNode(heatRoot);
  heatRoot.append(el("span"));
  hours.forEach(hour=>heatRoot.append(el("span",{className:"h",text:hour%2===0?String(hour):""})));
  days.forEach(day=>{
    const key=dayKey(day);
    heatRoot.append(el("span",{className:"d",text:day.getDate()+"·周"+weekdayName(day)}));
    hours.forEach(hour=>{
      const value=heat[key][hour];
      const isPeak=peakCell&&peakCell.key===key&&peakCell.hour===hour;
      const isNow=dayKey(day)===dayKey(now)&&hour===now.getHours();
      heatRoot.append(el("span",{
        className:"heat-cell"+(isPeak?" peak":"")+(isNow?" now":""),
        title:"周"+weekdayName(day)+" "+hourLabel(new Date(day.getFullYear(),day.getMonth(),day.getDate(),hour))+(isNow?" · 此刻":"")+" · "+bytes(value),
        style:{background:heatColor(value,maxHeat,value===0)}
      }));
    });
  });
  const legend=$("trafficHeatLegend");clearNode(legend);
  legend.append(el("span",{text:"低"}));
  heatColors().forEach(color=>legend.append(el("b",{style:{background:color}})));
  legend.append(el("span",{text:maxHeat?"高（峰值约 "+bytes(maxHeat)+"/小时） · 描边=此刻":"高 · 描边=此刻"}));
  const heatHint=$("trafficHeatHint");
  if(heatHint){
    heatHint.textContent=peakCell
      ?("峰值一格是周"+weekdayName(peakCell.date)+" "+pad2(peakCell.hour)+":00，约 "+bytes(peakCell.value)+"。把鼠标放在其他格子上也能看该小时用量。")
      :"颜色越深蓝这一小时越多。同步几次后会出现高峰。";
  }
  const hourTotals=Array(24).fill(0);
  days.forEach(day=>hours.forEach(hour=>{hourTotals[hour]+=heat[dayKey(day)][hour]}));
  const maxHour=Math.max(1,...hourTotals);
  let busyHour=0;
  hourTotals.forEach((value,hour)=>{if(value>hourTotals[busyHour])busyHour=hour});
  const hourRoot=$("trafficHours");
  if(hourRoot){
    clearNode(hourRoot);
    if(!hasSeries){
      hourRoot.classList.add("empty");
      hourRoot.append(chartEmpty("暂无数据，请先同步历史流量"));
    }else{
      hourRoot.classList.remove("empty");
      hours.forEach(hour=>{
        hourRoot.append(el("div",{
          className:"hour-col"+(hour===busyHour&&hourTotals[hour]?" peak":""),
          title:pad2(hour)+":00 · "+bytes(hourTotals[hour])
        },
          el("span",{className:"bar",style:{height:Math.max(2,Math.round(hourTotals[hour]/maxHour*160))+"px"}}),
          el("span",{className:"lbl",text:hour%3===0?String(hour):""})
        ));
      });
    }
  }
  const hoursHint=$("trafficHoursHint");
  if(hoursHint){
    hoursHint.textContent=hasSeries
      ?"这个号近 7 日多半在 "+pad2(busyHour)+":00 前后最忙（合计 "+bytes(hourTotals[busyHour])+"）。柱子是每天同一小时加总。"
      :"还没有 5 分钟增量，作息曲线会先空着。";
  }
  renderDayNight(hourTotals,hasSeries);
  const maxDay=Math.max(1,...days.map(day=>daily[dayKey(day)].total));
  const dayRoot=$("trafficDays");clearNode(dayRoot);
  days.forEach(day=>{
    const row=daily[dayKey(day)];
    const isBusy=busy&&busy.key===dayKey(day);
    const upH=Math.round((row.up||0)/maxDay*180);
    const downH=Math.round((row.down||0)/maxDay*180);
    dayRoot.append(el("div",{
      className:"day-col",
      title:pad2(day.getMonth()+1)+"/"+pad2(day.getDate())+" 周"+weekdayName(day)+" · "+bytes(row.total)+"（↑ "+bytes(row.up)+" · ↓ "+bytes(row.down)+"）",
      style:isBusy?{outline:"2px solid var(--accent)",outlineOffset:"2px",borderRadius:"8px",padding:"4px 2px"}:null
    },
      el("span",{className:"amt",text:row.total?bytes(row.total):""}),
      el("span",{className:"stack-bar"},
        el("i",{className:"up",style:{height:Math.max(row.up?4:0,upH)+"px"}}),
        el("i",{className:"down",style:{height:Math.max(row.down?4:0,downH)+"px"}})
      ),
      el("span",{className:"lbl",text:"周"+weekdayName(day)}),
      el("span",{className:"lbl",text:pad2(day.getMonth()+1)+"/"+pad2(day.getDate())})
    ));
  });
  renderWeekSplit(series,hasSeries);
  const trend=$("trafficTrend");clearNode(trend);
  if(!hasSeries){
    trend.append(el("p",{className:"hint",text:"还没有 5 分钟增量，连上并点同步几次后会出现曲线。"}));
    return;
  }
  const ups=series.map(item=>Number(item.up)||0);
  const downs=series.map(item=>Number(item.down)||0);
  // 纵轴顶只由两条线各自的峰值决定 —— 图里画的就是单条线的值。
  // （曾经拿 ups+downs 之和当峰值标签，但纵轴按单线算，
  //  结果标签写着 540.6 MB 比纵轴顶 519.8 MB 还高，点也对不上。）
  const maxLine=Math.max(1,...ups,...downs);
  const W=1100,H=280,padL=64,padR=20,padT=24,padB=36;
  const innerW=W-padL-padR, innerH=H-padT-padB;
  const x=i=>series.length<=1?padL:padL+innerW*i/Math.max(series.length-1,1);
  const y=v=>padT+innerH-(v/maxLine*innerH);
  const line=values=>values.map((v,i)=>x(i)+","+y(v)).join(" ");
  const area=values=>values.map((v,i)=>x(i)+","+y(v)).join(" ")+" "+x(values.length-1)+","+y(0)+" "+x(0)+","+y(0);
  // 峰值点 = 图上真正最高的那个数据点（单条线），
  // 这样红点、标签、纵轴三者指的是同一个东西。
  const peakIdx=ups.reduce((best,_,i)=>{
    const cur=Math.max(ups[i],downs[i]), prev=Math.max(ups[best],downs[best]);
    return cur>prev?i:best;
  },0);
  const svg=svgNode("svg",{
    viewBox:"0 0 "+W+" "+H,
    class:"trend-svg",
    role:"img",
    "aria-label":"近7日上行与下行增量"
  });
  const lineColor=themeColor("--line","#e4e4e1");
  const faint=themeColor("--faint","#8c8c88");
  const muted=themeColor("--muted","#5c5c59");
  const accent=themeColor("--accent","#2a78d6");
  const bad=themeColor("--bad","#d9463f");
  const mono=themeColor("--mono",'ui-monospace,"SF Mono",Menlo,Consolas,monospace');
  [0,0.25,0.5,0.75,1].forEach(ratio=>{
    const yy=y(maxLine*ratio);
    svg.append(svgNode("line",{x1:padL,x2:W-padR,y1:yy,y2:yy,stroke:lineColor,"stroke-width":1}));
    svg.append(svgNode("text",{x:padL-8,y:yy+4,"text-anchor":"end","font-size":11,fill:faint,"font-family":mono},bytes(maxLine*ratio)));
  });
  svg.append(svgNode("path",{d:"M"+area(ups),fill:accent,opacity:"0.12"}));
  svg.append(svgNode("polyline",{fill:"none",stroke:muted,"stroke-width":2,points:line(ups)}));
  svg.append(svgNode("polyline",{fill:"none",stroke:accent,"stroke-width":2.5,points:line(downs)}));
  const peakVal=Math.max(ups[peakIdx],downs[peakIdx]);
  const peakX=x(peakIdx), peakY=y(peakVal);
  svg.append(svgNode("circle",{cx:peakX,cy:peakY,r:4.5,fill:bad}));
  const peakLabel=bytes(peakVal);
  const labelY=peakY<36?peakY+18:peakY-10;
  svg.append(svgNode("text",{x:Math.min(Math.max(peakX,padL+40),W-padR-40),y:labelY,"text-anchor":"middle","font-size":12,"font-weight":700,fill:bad,"font-family":mono},"峰值 "+peakLabel));
  const tickCount=Math.min(5,series.length);
  const tickAt=i=>tickCount<=1?0:Math.round(i*(series.length-1)/(tickCount-1));
  for(let i=0;i<tickCount;i++){
    const idx=tickAt(i);
    const stamp=new Date(series[idx].t);
    if(Number.isNaN(stamp.getTime()))continue;
    svg.append(svgNode("text",{x:x(idx),y:H-10,"text-anchor":"middle","font-size":11,fill:faint,"font-family":mono},hourLabel(stamp)));
  }
  trend.append(svg);
  trend.append(el("p",{className:"trend-note",text:"红点峰值 "+bytes(peakVal)+"（↑ "+bytes(ups[peakIdx])+" · ↓ "+bytes(downs[peakIdx])+"）。纵轴最大 "+bytes(maxLine)+"。"}));
}
function buildTrafficSummary(data,peakCell,busy){
  const name=String(data.username||"该用户");
  const month=data.month||{};
  const monthTotal=Number(month.total)||0;
  const share=Number(month.share_percent)||0;
  const live=(data.live||[]).length;
  const sites=(data.sites||[]).length;
  const parts=[name+" 本月已用 "+bytes(monthTotal)+(share?("，约占整机 "+share.toFixed(1)+"%"):"")];
  if(peakCell)parts.push("最近高峰在周"+weekdayName(peakCell.date)+" "+pad2(peakCell.hour)+":00 左右");
  else if(busy)parts.push("近 7 日最忙是 "+pad2(busy.date.getMonth()+1)+"月"+busy.date.getDate()+"日");
  if(live)parts.push("此刻 "+live+" 条连接");
  else if((data.client_ips||[]).length)parts.push("最近客户端 "+data.client_ips[0].ip);
  else if(sites)parts.push("近 7 日见到 "+sites+" 个站点");
  else parts.push("还没有连上记录，同步后再看");
  return parts.join("。")+"。";
}
function renderSessionStats(sessions){
  const avg=Number(sessions.avg_seconds)||0;
  const last=Number(sessions.last_seconds)||0;
  const count=Number(sessions.count)||0;
  const finished=Number(sessions.finished)||0;
  if($("trafficSessionAvg"))$("trafficSessionAvg").textContent=avg?formatDuration(avg):"--";
  if($("trafficSessionExtra"))$("trafficSessionExtra").textContent=finished?("已结束 "+finished+" 次"):"还没有配对到完整连接";
  if($("trafficLastSession"))$("trafficLastSession").textContent=last?formatDuration(last):(avg?formatDuration(avg):"--");
  if($("trafficLastSessionHint"))$("trafficLastSessionHint").textContent=last?"最近一次从连上到断开":"日志里还没有完整的断开记录";
  if($("trafficSessionCount"))$("trafficSessionCount").textContent=count?String(count):"0";
  if($("trafficSessionCountHint"))$("trafficSessionCountHint").textContent=finished?("结束 "+finished+" · 仍在线 "+Math.max(0,count-finished)):"含仍在线的连接";
}
function renderDayNight(hourTotals,hasSeries){
  let dayBytes=0,nightBytes=0;
  (hourTotals||[]).forEach((value,hour)=>{
    if(hour>=7&&hour<23)dayBytes+=value;else nightBytes+=value;
  });
  const total=dayBytes+nightBytes;
  const dayPct=total?Math.round(dayBytes/total*100):0;
  if($("trafficDayShare"))$("trafficDayShare").textContent=total?dayPct+"%":"--";
  if($("trafficDayShareExtra"))$("trafficDayShareExtra").textContent=total?("白天 "+bytes(dayBytes)+" · 夜间 "+bytes(nightBytes)):"07:00–23:00";
  if($("trafficDayNightVal"))$("trafficDayNightVal").textContent=total?("白天 "+dayPct+"%"):"--";
  if($("trafficDayNightHint")){
    $("trafficDayNightHint").textContent=hasSeries&&total
      ?(dayPct>=55?"白天更忙 · 夜间 "+bytes(nightBytes):dayPct<=45?"夜间更忙 · 白天 "+bytes(dayBytes):"白天和夜间差不多")
      :"白天按 07:00–23:00 计";
  }
  if($("trafficDayNightFill"))$("trafficDayNightFill").style.width=(total?dayPct:0)+"%";
}
function renderDestinations(data){
  const ip=String(data.egress_ip||"").trim()||"--";
  $("trafficEgressLine").textContent="出口 IP："+ip+"（外站看到的地址）";
  liveList=Array.isArray(data.live)?data.live:[];
  siteList=(Array.isArray(data.sites)?data.sites:[]).map(row=>Object.assign({},row,{share:siteSharePct(row,data.sites||[])}));
  const liveCount=liveList.length, siteCount=siteList.length;
  $("trafficLiveCount").textContent=String(liveCount);
  $("trafficLiveExtra").textContent=data.online?("在线设备 "+data.online):"当前活动流";
  $("trafficSiteCount").textContent=String(siteCount);
  $("trafficSiteExtra").textContent=data.last_active&&data.last_active!=="从未"?("最后活跃 "+relTime(data.last_active)):"近 7 日采样";
  $("trafficClient").textContent=siteCount||liveCount||(data.client_ips||[]).length
    ?("客户端 "+((data.client_ips||[]).length||0)+" 个地址")
    :"客户端：暂无记录";
  renderClientCards(data.client_ips||[], liveList);
  renderSiteBars(siteList);
  renderSiteMix(groupSitesByRoot(siteList));
  renderLiveRows();
  renderSiteRows();
}
function renderWeekSplit(series,hasSeries){
  const root=$("trafficWeek");
  const hint=$("trafficWeekHint");
  if(!root)return;
  clearNode(root);
  if(!hasSeries){
    root.classList.add("empty");
    root.append(chartEmpty("暂无数据"));
    if(hint)hint.textContent="还没有增量，工作日和周末会先空着。";
    return;
  }
  root.classList.remove("empty");
  let weekday=0,weekend=0;
  (series||[]).forEach(item=>{
    const d=new Date(item.t);
    if(Number.isNaN(d.getTime()))return;
    const value=(Number(item.up)||0)+(Number(item.down)||0);
    const day=d.getDay();
    if(day===0||day===6)weekend+=value; else weekday+=value;
  });
  const max=Math.max(1,weekday,weekend);
  const cards=[{key:"wd",title:"工作日",value:weekday,cls:""},{key:"we",title:"周末",value:weekend,cls:" we"}];
  cards.forEach(card=>{
    root.append(el("div",{className:"week-card"+card.cls},
      el("div",{className:"label",text:card.title}),
      el("div",{className:"value",text:bytes(card.value)}),
      el("div",{className:"track"},el("i",{className:"fill",style:{width:Math.round(card.value/max*100)+"%"}})),
      el("div",{className:"hint",text:formatPct(card.value/(weekday+weekend||1)*100)})
    ));
  });
  if(hint){
    if(!weekday&&!weekend)hint.textContent="这几天几乎没有增量。";
    else if(weekday>weekend)hint.textContent=weekend?"工作日用量大约是周末的 "+(weekday/weekend).toFixed(1)+" 倍。":"近 7 日用量都在工作日。";
    else if(weekend>weekday)hint.textContent=weekday?"周末大约是工作日的 "+(weekend/weekday).toFixed(1)+" 倍。":"近 7 日用量都在周末。";
    else hint.textContent="近 7 日工作日和周末差不多。";
  }
}
function renderClientCards(list,live){
  const root=$("trafficClients");
  if(!root)return;
  clearNode(root);
  if(!list||!list.length){
    root.append(el("div",{className:"hint",text:"还没有采集到客户端 IP。用户连上后会从连接日志写入。"}));
    return;
  }
  const liveIps=new Set((live||[]).map(row=>row.client).filter(Boolean));
  list.forEach(item=>{
    const online=liveIps.has(item.ip);
    const duration=formatDuration(item.session_seconds);
    root.append(el("div",{className:"client-card"+(online?" on":"")},
      el("div",{className:"ip",text:item.ip+(item.port?":"+item.port:"")}),
      el("div",{className:"meta",text:(online?"此刻在线":"最近出现")+" · "+(item.last_seen?relTime(item.last_seen):"--")+(duration?" · 最近连接 "+duration:"")})
    ));
  });
}
function renderSiteBars(sites){
  const root=$("trafficSiteBars");
  if(!root)return;
  clearNode(root);
  const rows=(sites||[]).slice(0,8);
  if(!rows.length){root.style.display="none";return}
  root.style.display="";
  const max=Math.max(1,...rows.map(row=>Number(row.total)||Number(row.hits)||0));
  rows.forEach((row,index)=>{
    const weight=Number(row.total)||Number(row.hits)||0;
    const pct=Math.round(weight/max*100);
    const right=Number(row.total)
      ?bytes(row.total)+" · "+formatPct(row.share)+" · ↑ "+bytes(row.upload)+" · ↓ "+bytes(row.download)
      :formatPct(row.share)+" · "+(Number(row.hits)||0)+" 次";
    root.append(el("div",{className:"site-bar-row"},
      el("span",{className:"dest-host",text:(index+1)+". "+(row.host||"--")+(row.root&&row.root!==row.host?" · "+row.root:"")}),
      el("span",{className:"track"},el("i",{className:"fill",style:{width:pct+"%"}})),
      el("span",{className:"hint",text:right})
    ));
  });
}
function renderSiteMix(sites){
  const root=$("trafficMix");
  const hint=$("trafficMixHint");
  if(!root)return;
  clearNode(root);
  const rows=sites||[];
  if(!rows.length){
    root.classList.add("hide");
    if(hint)hint.textContent="";
    return;
  }
  root.classList.remove("hide");
  const weight=row=>Number(row.total)||Number(row.hits)||0;
  const total=rows.reduce((n,row)=>n+weight(row),0)||1;
  const top=rows.slice(0,5);
  const rest=rows.slice(5).reduce((n,row)=>n+weight(row),0);
  const palette=mixColors();
  const parts=top.map((row,i)=>({label:row.host||"--",value:weight(row),color:palette[i]}));
  if(rest)parts.push({label:"其他",value:rest,color:palette[5]});
  const cx=100,cy=100,r=78,ir=44;
  const svg=svgNode("svg",{viewBox:"0 0 200 200",class:"mix-svg",role:"img","aria-label":"站点流量构成"});
  let angle=-Math.PI/2;
  const usable=parts.filter(part=>part.value>0);
  if(usable.length<=1){
    svg.append(svgNode("circle",{cx,cy,r,fill:(usable[0]||parts[0]||{}).color||palette[5]}));
  }else{
    usable.forEach(part=>{
      const slice=part.value/total*Math.PI*2;
      const start=angle;
      angle+=slice;
      const x1=cx+r*Math.cos(start), y1=cy+r*Math.sin(start);
      const x2=cx+r*Math.cos(angle), y2=cy+r*Math.sin(angle);
      const large=slice>Math.PI?1:0;
      svg.append(svgNode("path",{d:"M "+cx+" "+cy+" L "+x1+" "+y1+" A "+r+" "+r+" 0 "+large+" 1 "+x2+" "+y2+" Z",fill:part.color}));
    });
  }
  svg.append(svgNode("circle",{cx,cy,r:ir,fill:themeColor("--surface","#ffffff")}));
  const lead=usable[0]||parts[0];
  const mixMono=themeColor("--mono",'ui-monospace,"SF Mono",Menlo,Consolas,monospace');
  svg.append(svgNode("text",{x:cx,y:cy-4,"text-anchor":"middle","font-size":16,"font-weight":700,fill:themeColor("--text","#111111"),"font-family":mixMono},lead?formatPct(lead.value/total*100):""));
  svg.append(svgNode("text",{x:cx,y:cy+16,"text-anchor":"middle","font-size":12,fill:themeColor("--faint","#8c8c88"),"font-family":mixMono},"最大一块"));
  const legend=el("div",{className:"mix-legend"});
  parts.forEach(part=>{
    legend.append(el("span",{},
      el("i",{style:{background:part.color}}),
      el("b",{text:part.label}),
      el("em",{text:formatPct(part.value/total*100)})
    ));
  });
  root.append(svg,legend);
  if(hint)hint.textContent=lead?("近 7 日里，"+lead.label+" 大约占 "+formatPct(lead.value/total*100)+"。其余站点合在「其他」里。"):"";
}
function renderLiveRows(){
  const liveRoot=$("trafficLive");clearNode(liveRoot);
  const live=sortedRows(liveList,liveSort);
  markSort($("trafficLiveTable"),liveSort);
  if(!live.length){
    liveRoot.append(el("tr",{},el("td",{colSpan:9,className:"hint",text:"当前没有活动连接"})));
    return;
  }
  live.forEach(row=>{
    const up=Number(row.upload)||0, down=Number(row.download)||0;
    liveRoot.append(el("tr",{},
      el("td",{className:"dest-host",text:row.host||"--"}),
      el("td",{className:"dest-ip",text:row.client||"--"}),
      el("td",{className:"dest-ip",text:row.ip||"--"}),
      el("td",{},el("span",{text:row.port||"--"}),portName(row.port)?el("span",{className:"port-tag",text:portName(row.port)}):null),
      el("td",{text:streamState(row.state)}),
      el("td",{className:"traffic-up",text:"↑ "+bytes(up)}),
      el("td",{className:"traffic-down",text:"↓ "+bytes(down)}),
      el("td",{text:bytes(up+down)}),
      visitCell(row.last_active)
    ));
  });
}
// 在站点行下方插入/移除一行详情（占满整表宽度，不挤压任何列）。
// 详情行本身不参与排序与统计，纯展示。
function toggleSiteDetail(tr,row){
  const next=tr.nextElementSibling;
  if(next&&next.classList.contains("site-detail")){
    next.remove();
    return;
  }
  // 同时只展开一行，避免堆得满屏
  const root=$("trafficSites");
  if(root)root.querySelectorAll(".site-detail").forEach(node=>node.remove());

  const host=String(row.host||"--");
  const items=[
    ["完整域名",el("span",{className:"full-host",text:host})],
  ];
  const rootDomain=String(row.root||"").trim();
  if(rootDomain&&rootDomain!==host)items.push(["归属主域",rootDomain]);
  if(row.ip)items.push(["IP",String(row.ip)]);
  if(row.port)items.push(["端口",String(row.port)+(portName(row.port)?("（"+portName(row.port)+"）"):"")]);
  items.push(["上行 / 下行","↑ "+bytes(row.upload)+"　↓ "+bytes(row.download)]);
  items.push(["合计",bytes(row.total)]);
  items.push(["访问次数",String(row.hits||0)+" 次"]);
  items.push(["占比",formatPct(row.share)]);
  if(row.first_seen)items.push(["首次访问",formatActive(row.first_seen)]);
  if(row.last_seen)items.push(["最近访问",formatActive(row.last_seen)]);

  const dl=el("dl",{});
  items.forEach(([k,v])=>{
    dl.append(el("dt",{text:k}),el("dd",{},typeof v==="string"?document.createTextNode(v):v));
  });
  const detail=el("tr",{className:"site-detail"},
    el("td",{colSpan:10},el("div",{className:"site-detail-inner"},dl))
  );
  tr.after(detail);
  // 表格容器有 max-height，展开后详情可能在可视区外，滚进来一点
  requestAnimationFrame(()=>{
    try{ detail.scrollIntoView({block:"nearest",behavior:"smooth"}); }catch(e){}
  });
}

function renderSiteRows(){
  const siteRoot=$("trafficSites");clearNode(siteRoot);
  const sites=sortedRows(siteList,siteSort);
  markSort($("trafficSiteTable"),siteSort);
  if(!sites.length){
    siteRoot.append(el("tr",{},el("td",{colSpan:10,className:"hint",text:"还没有采样到访问站点"})));
    return;
  }
  sites.forEach(row=>{
    const host=String(row.host||"--");
    const root=String(row.root||"").trim();
    // 域名太长时单行省略，全名放 title 悬停看；点一下在行下方展开完整信息。
    const hostTd=el("td",{className:"dest-host",title:host+"（点击展开）"},
      el("span",{text:host}));
    if(root&&root!==host)hostTd.append(el("span",{className:"root-alias",text:"· "+root}));

    const tr=el("tr",{},
      hostTd,
      el("td",{className:"dest-ip",text:row.ip||"--"}),
      el("td",{},el("span",{text:row.port||"--"}),portName(row.port)?el("span",{className:"port-tag",text:portName(row.port)}):null),
      el("td",{className:"traffic-up",text:"↑ "+bytes(row.upload)}),
      el("td",{className:"traffic-down",text:"↓ "+bytes(row.download)}),
      el("td",{text:Number(row.total)?bytes(row.total):(Number(row.hits)||0)+" 次"}),
      el("td",{text:String(row.hits||0)+" 次"}),
      el("td",{text:formatPct(row.share)}),
      visitCell(row.first_seen||row.last_seen),
      visitCell(row.last_seen)
    );
    hostTd.onclick=()=>toggleSiteDetail(tr,row);
    siteRoot.append(tr);
  });
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
function userInList(username){
  return (userList||[]).some(user=>user.username===username);
}
async function syncUsersQuiet(){
  try{await load()}catch(e){}
}
async function copyCredential(username,kind){
  closeMenus();
  try{
    const result=await apiPost("api/user/credentials",{username,kind});
    await copyText(result.value);
    const label=kind==="subscription"?"Clash":kind==="subscription-v2ray"?"v2ray":kind==="subscription-singbox"?"sing-box":null;
    toast(label?("已复制 "+label+" 订阅链接"):"已复制");
  }catch(error){toast("复制失败："+error.message)}
}
// 打开二维码弹窗：先问后端拿这个用户对应格式的订阅链接，再在 Canvas 上画码。
//
// 为什么要问后端：订阅链接带 token，面板不持有明文凭据，统一由 api/user/credentials
// 给，避免前端自己拼 URL 拼错（尤其 fmt 参数和 panel_path 前缀）。
let qrCurrentUrl = "";
async function openQr(username, kind){
  closeMenus();
  const label = kind==="subscription"?"Clash":kind==="subscription-v2ray"?"v2ray":kind==="subscription-singbox"?"sing-box":"订阅";
  let url = "";
  try{
    const result = await apiPost("api/user/credentials",{username,kind});
    url = String(result.value||"");
  }catch(error){
    toast("获取订阅链接失败："+error.message);
    return;
  }
  qrCurrentUrl = url;
  $("qrHint").textContent = username + " · " + label;
  $("qrUrlText").textContent = url;
  const wrap = $("qrCanvasWrap");
  const fallback = $("qrFallback");
  const canvas = $("qrCanvas");

  // 二维码库没加载成功（文件没装/被拦）就只给文字链接，不假装能扫
  if(typeof qrcode !== "function"){
    wrap.hidden = true;
    fallback.hidden = false;
  }else{
    try{
      drawQr(canvas, url);
      wrap.hidden = false;
      fallback.hidden = true;
    }catch(error){
      wrap.hidden = true;
      fallback.hidden = false;
    }
  }
  $("qrModal").classList.add("open");
  setTimeout(()=>$("qrDone").focus(),50);
}

// 用 qrcode-generator 取模块矩阵，自己画到 canvas。
// 不依赖库自带的图片输出：那要 <img src=data:>，虽然 CSP 允许 data:，
// 但 canvas 更可控（清晰度、留白、配色都能定）。
function drawQr(canvas, text){
  const qr = qrcode(0, "M");          // 0 = 自动选版本，M = 15% 容错
  qr.addData(text);
  qr.make();
  const count = qr.getModuleCount();
  const quiet = 4;                     // 静区，QR 规范要求至少 4 格
  const total = count + quiet * 2;
  const scale = Math.max(2, Math.floor(240 / total));
  const px = total * scale;
  canvas.width = px;
  canvas.height = px;
  const ctx = canvas.getContext("2d");
  // 用不透明底：透明背景在深色主题下会跟底色糊在一起，手机扫不出来
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, px, px);
  ctx.fillStyle = "#000000";
  for(let r = 0; r < count; r++){
    for(let c = 0; c < count; c++){
      if(qr.isDark(r, c)){
        ctx.fillRect((c + quiet) * scale, (r + quiet) * scale, scale, scale);
      }
    }
  }
  // 逻辑尺寸交给 CSS，位图按 scale 放大，保证高分屏不糊
  canvas.style.width = "240px";
  canvas.style.height = "240px";
  canvas.style.imageRendering = "pixelated";
}

function closeQr(){
  $("qrModal").classList.remove("open");
  qrCurrentUrl = "";
}

async function saveNote(){
  const username=noteUser;
  const note=String($("noteInput").value||"").trim();
  if(!username)return;
  if(note.length>100){toast("备注最长 100 字符");return}
  await runMutate($("noteSave"),async()=>{
    try{
      await apiPost("api/user/note",{username,note});
      setNoteModal(false);
      toast("备注已保存");
      await load();
    }catch(error){toast("保存失败："+error.message)}
  },"正在保存备注…");
}
async function toggleUser(username,disabled){
  closeMenus();
  if(!disabled&&!confirm("确认禁用 "+username+"？\n\n他会被立即踢下线，重连也过不去。流量与数据保留。"))return;
  await runMutate(null,async()=>{
    try{
      const result=await apiPost(disabled?"api/user/enable":"api/user/disable",{username});
      toast(result.message||(disabled?"已启用 "+username:"已禁用 "+username));
      await load();
    }catch(error){
      await syncUsersQuiet();
      toast("操作失败："+error.message);
    }
  },disabled?"正在启用用户…":"正在禁用用户…");
}
async function kickUser(username){
  closeMenus();
  if(!confirm("确认把 "+username+" 踢下线？\n\n只断开现有连接，不会禁用。他重连仍可连上（适合让他换 IP）。"))return;
  await runMutate(null,async()=>{
    try{
      const result=await apiPost("api/user/kick",{username});
      if(result&&result.kicked){
        toast("已踢下线："+username);
      }else{
        toast((result&&result.message)||"没有可断开的连接");
      }
      await load();
    }catch(error){
      toast("踢下线失败："+error.message);
    }
  },"正在踢下线…");
}
async function removeUser(username){
  closeMenus();
  if(!confirm("确认删除用户 "+username+"？\n\n他会立即断线，且此操作不可恢复。"))return;
  await runMutate(null,async()=>{
    try{
      await apiPost("api/user/remove",{username});
      toast("已删除 "+username);
      await load();
    }catch(error){
      await syncUsersQuiet();
      if(!userInList(username)){
        toast("已删除 "+username);
        return;
      }
      toast("删除失败："+error.message);
    }
  },"正在删除用户…");
}
async function rotateUser(username){
  closeMenus();
  if(!confirm("确认轮换 "+username+" 的密码与订阅 token？\n\n旧订阅立即失效，他会断线需重新配置。"))return;
  await runMutate(null,async()=>{
    try{
      await apiPost("api/user/rotate",{username});
      toast("已轮换 "+username+" 的密钥");
      await load();
    }catch(error){
      await syncUsersQuiet();
      toast("轮换失败："+error.message);
    }
  },"正在轮换密钥…");
}
async function addUser(){
  const input=$("newUser");
  const username=String(input.value||"").trim();
  if(!VALID_NAME.test(username)){toast("用户名仅允许字母、数字、下划线、短横线，长度 1-32");return}
  await runMutate($("addBtn"),async()=>{
    try{
      await apiPost("api/user/add",{username});
      input.value="";
      toast("已添加 "+username);
      setDrawer(false);
      await load();
    }catch(error){
      await syncUsersQuiet();
      if(userInList(username)){
        input.value="";
        toast("已添加 "+username);
        setDrawer(false);
        return;
      }
      toast("添加失败："+error.message);
    }
  },"正在添加用户…");
}
async function exportLogs(){
  const range=$("logRange")?$("logRange").value||"24h":"24h";
  const btn=$("exportLogs");
  if(btn)btn.disabled=true;
  try{
    const response=await fetch("api/logs/export",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({range}),cache:"no-store"});
    const type=response.headers.get("Content-Type")||"";
    if(!response.ok||type.includes("application/json")){
      const result=await response.json().catch(()=>({}));
      throw new Error(result.error||("HTTP "+response.status));
    }
    const blob=await response.blob();
    const match=/filename="?([^"]+)"?/.exec(response.headers.get("Content-Disposition")||"");
    const name=match?match[1]:"hy2-logs.txt";
    const url=URL.createObjectURL(blob);
    const link=document.createElement("a");
    link.href=url;link.download=name;document.body.appendChild(link);link.click();link.remove();
    URL.revokeObjectURL(url);
    toast("已导出日志");
  }catch(error){toast("导出失败："+error.message)}
  if(btn)btn.disabled=false;
}
async function syncNow(){
  await runMutate($("syncBtn"),async()=>{
    const extra=$("drawerSync");
    if(extra)extra.disabled=true;
    try{
      await apiPost("api/sync",{});
      await load();
      toast("同步完成");
    }catch(error){toast("同步失败："+error.message)}
    finally{if(extra)extra.disabled=false;}
  },"正在同步…");
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
  if(enabled&&!confirm("确认关闭 Hysteria？HY2 节点将无法连接，VLESS 仍可用。"))return;
  await runMutate($("hy2Toggle"),async()=>{
    try{
      await apiPost(enabled?"api/hy2/off":"api/hy2/on",{});
      toast(enabled?"HY2 已关闭":"HY2 已开启");
      await load();
    }catch(error){toast("操作失败："+error.message)}
  },enabled?"正在关闭 HY2…":"正在开启 HY2…");
}
const SUB_ICONS=new Set(["clash","v2ray","singbox"]);
function menuItem(text,handler,bad,disabled,icon){
  // 注意第三个参数是「危险操作标红」，不是「禁用」。要置灰请传第四个参数。
  // 之前把两件事混在一个参数上，结果「离线用户不能踢」变成了「离线用户标红」。
  // 第五个参数是图标名（sprite id 去掉 i- 前缀）。
  const node=el("button",{type:"button",className:bad?"bad":"",onclick:handler});
  if(icon){
    // 订阅项用真客户端图标；其余菜单项仍用 sprite
    node.append(SUB_ICONS.has(icon) ? clientIcon(icon) : iconSvg(icon));
    node.append(el("span",{text}));
  }else{
    node.textContent=text;
  }
  if(disabled){
    node.disabled=true;
    node.classList.add("disabled");
    node.title="当前不可用";
    node.onclick=null;
  }
  return node;
}
// 可展开的菜单项：点一下展开子动作（复制链接 / 二维码导入）。
// 父项本身不直接执行动作——订阅对用户来说总是「要么复制要么扫码」，
// 直接点击要猜他想要哪个，不如让他选。
function menuItemExpandable(text, icon, children){
  const wrap=el("div",{className:"mi-group"});
  const head=el("button",{type:"button",className:"mi-head"});
  head.append(SUB_ICONS.has(icon) ? clientIcon(icon) : iconSvg(icon));
  head.append(el("span",{text}));
  head.append(el("span",{className:"mi-caret",text:"›"}));
  const sub=el("div",{className:"mi-sub"});
  children.forEach(node=>sub.append(node));
  head.onclick=function(event){
    event.stopPropagation();
    const open=wrap.classList.toggle("open");
    head.setAttribute("aria-expanded", open?"true":"false");
  };
  wrap.append(head, sub);
  return wrap;
}

// 一个订阅项：展开后给「复制链接」和「二维码导入」两个动作。
function subMenu(username, label, kind, icon){
  return menuItemExpandable(label, icon, [
    menuSubItem("复制链接", ()=>copyCredential(username, kind), "copy"),
    menuSubItem("二维码导入", ()=>openQr(username, kind), "qr"),
  ]);
}

function menuSubItem(text, handler, icon){
  const node=el("button",{type:"button",className:"mi-sub-item",onclick:handler});
  if(icon) node.append(iconSvg(icon));
  node.append(el("span",{text}));
  return node;
}

function renderUsers(users){
  if(users)userList=users;
  const root=$("users");clearNode(root);
  const list=sortedRows(userList,userSort);
  markSort(document.querySelector(".table-wrap table"),userSort);
  $("userSummary").textContent=list.length+" 个账号 · 点表头排序";
  if(!list.length){
    root.append(el("tr",{},el("td",{colSpan:8,className:"hint",text:"暂无用户。打开右上角菜单添加。"})));
    return;
  }
  list.forEach(user=>{
    const note=String(user.note||"").trim();
    const statusClass=user.disabled?"ban":(user.online?"on":"off");
    const statusText=user.disabled?"已禁用":(user.online?"在线 "+user.online:"离线");
    const statusKids=[
      el("span",{className:"status-dot "+statusClass,text:statusText}),
      el("span",{className:"status-active",text:"最后 "+formatActive(user.last_active)})
    ];
    if(user.client_ip)statusKids.push(el("span",{className:"status-active",text:"客户端 "+user.client_ip}));
    const statusCell=el("div",{className:"status-cell"},...statusKids);
    const menu=el("div",{className:"menu"});
    const btn=el("button",{className:"menu-btn",type:"button",title:"操作"});
    btn.append(iconSvg("more"));
    btn.onclick=function(event){
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
    };
    menu.append(
      subMenu(user.username,"Clash 订阅","subscription","clash"),
      subMenu(user.username,"v2ray 订阅","subscription-v2ray","v2ray"),
      subMenu(user.username,"sing-box 订阅","subscription-singbox","singbox"),
      el("div",{className:"sep"}),
      menuItem("复制直链",()=>copyCredential(user.username,"direct")),
      menuItem("复制密码",()=>copyCredential(user.username,"password")),
      el("div",{className:"sep"}),
      menuItem("流量分析",()=>{closeMenus();openTraffic(user.username)}),
      menuItem("改备注",()=>{closeMenus();setNoteModal(true,user.username,note)}),
      menuItem("轮换密钥",()=>rotateUser(user.username)),
      menuItem("踢下线",()=>kickUser(user.username),false,!user.online),
      menuItem(user.disabled?"启用":"禁用",()=>toggleUser(user.username,!!user.disabled),!user.disabled),
      el("div",{className:"sep"}),
      menuItem("删除",()=>removeUser(user.username),true)
    );
    const nameCell=el("div",{className:"user-cell"},
      el("span",{className:"user-name",text:user.username}),
      note?el("span",{className:"user-note",text:"("+note+")"}):null
    );
    const modeText=user.mode||"BBR";
    root.append(el("tr",{className:user.disabled?"disabled":""},
      el("td",{},nameCell),
      el("td",{},statusCell),
      el("td",{text:modeText}),
      el("td",{className:"traffic-up",text:"↑ "+bytes(user.upload)}),
      el("td",{className:"traffic-down",text:"↓ "+bytes(user.download)}),
      el("td",{text:bytes(user.total)}),
      el("td",{text:bytes(user.lifetime_total||0)}),
      el("td",{className:"ops"},btn,menu)
    ));
  });
}
async function load(){
  try{
    const response=await fetch("data.json?t="+Date.now(),{cache:"no-store"});
    if(!response.ok)throw new Error("HTTP "+response.status);
    const data=await response.json(),t=data.server.traffic;
    const ver=String(data.version||"").replace(/^v/i,"").trim();
    const ageText=dataAgeText(data.generated_at);
    $("time").textContent=(ver&&ver!=="unknown"?("v"+ver+" · "):"")+"更新 "+data.generated_at+(ageText?"（"+ageText+"）":"")+" · "+data.server.ip+" · "+data.server.domain;
    const unlimited=!(Number(t.limit)>0);
    $("traffic").textContent=bytes(t.used)+(unlimited?" / 无限":" / "+bytes(t.limit));
    $("remain").textContent="入 "+bytes(t.rx)+" · 出 "+bytes(t.tx)+(unlimited?" · 不限量":" · 剩余 "+bytes(t.remain));
    const pctVal=unlimited?0:Math.min(100,Number(t.percent)||0);
    $("trafficBar").style.width=pctVal+"%";
    $("trafficBar").style.background=pctVal>=90?"var(--bad)":"var(--accent)";
    $("cpu").textContent=data.server.cpu+"%";
    // 负载相对核数才有意义：4 核跑 4.0 就是满载，1 核跑 4.0 已经爆了。
    // 后端带上核数，这里换算成更直观的「负载 / 核数」。
    const cores=Number(data.server.cpu_cores)||0;
    const loads=data.server.load||[];
    $("load").textContent="负载 "+loads.join(" / ")+(cores>1?"（"+cores+" 核）":"");
    $("memory").textContent=data.server.memory.percent+"%";$("swap").textContent="Swap "+data.server.memory.swap_percent+"%";
    $("disk").textContent=data.server.disk.percent+"%";$("uptime").textContent="运行 "+duration(data.server.uptime);
    renderServices(data.server.services);
    const hy2On=data.server.hy2_enabled!==false;
    window.__hy2Enabled=hy2On;
    $("hy2OffBanner").classList.toggle("show",!hy2On);
    const toggle=$("hy2Toggle");
    if(toggle){
      setBtnIcon(toggle,"power",hy2On?"关闭 HY2":"开启 HY2");
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
$("themeBtn").onclick=()=>applyTheme(currentTheme()==="dark"?"light":"dark");
$("drawerSync").onclick=()=>{setDrawer(false);syncNow()};
$("exportLogs").onclick=exportLogs;
$("backupBtn").onclick=async function(){
  await runMutate($("backupBtn"),async()=>{
    try{
      const result=await apiPost("api/backup",{});
      toast("备份完成"+(result.backup?"："+result.backup:""));
    }catch(error){toast("备份失败："+error.message)}
  },"正在备份…");
};
$("menuBtn").onclick=()=>setDrawer(true);
// 二维码弹窗的事件绑定
if($("qrClose"))$("qrClose").onclick=closeQr;
if($("qrDone"))$("qrDone").onclick=closeQr;
if($("qrCopy"))$("qrCopy").onclick=async()=>{
  if(!qrCurrentUrl)return;
  try{ await copyText(qrCurrentUrl); toast("已复制订阅链接"); }
  catch(error){ toast("复制失败："+error.message); }
};
$("qrModal").onclick=function(event){ if(event.target===this)closeQr(); };
$("drawerClose").onclick=()=>setDrawer(false);
$("scrim").onclick=()=>setDrawer(false);
$("addBtn").onclick=addUser;
$("newUser").addEventListener("keydown",event=>{
  if(event.key!=="Enter")return;
  event.preventDefault();
  if(event.repeat||mutateBusy)return;
  addUser();
});
$("noteCancel").onclick=()=>setNoteModal(false);
$("noteSave").onclick=saveNote;
$("noteInput").addEventListener("keydown",event=>{
  if(event.key!=="Enter")return;
  event.preventDefault();
  if(event.repeat||mutateBusy)return;
  saveNote();
});
$("noteModal").addEventListener("click",event=>{if(event.target===$("noteModal"))setNoteModal(false)});
$("trafficClose").onclick=()=>setTrafficModal(false);
$("trafficModal").addEventListener("click",event=>{if(event.target===$("trafficModal"))setTrafficModal(false)});
bindSortHeaders(document.querySelector(".table-wrap table"),userSort,()=>renderUsers());
bindSortHeaders($("trafficLiveTable"),liveSort,renderLiveRows);
bindSortHeaders($("trafficSiteTable"),siteSort,renderSiteRows);
document.addEventListener("click",closeMenus);
document.addEventListener("scroll",()=>{if(openMenu&&openMenu._btn)positionMenu(openMenu,openMenu._btn)},true);
window.addEventListener("resize",()=>{if(openMenu&&openMenu._btn)positionMenu(openMenu,openMenu._btn)});
document.addEventListener("keydown",event=>{
  if(event.key==="Escape"){closeMenus();setDrawer(false);setNoteModal(false);setTrafficModal(false)}
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
initTheme();
load();
// 后端每 60s 落一次 data.json，前端 10s 拉一次就够及时了：
// 拉的是同一份静态文件，多拉几次成本几乎为零（nginx + 一个 JSON 文件），
// 但用户点开页面时不用干等一分钟才看到数字变化。
// 页面在后台时不拉（等切回来再说），省小机器的带宽和电量。
let refreshTimer=setInterval(()=>{
  if(document.hidden)return;
  load();
},10000);
document.addEventListener("visibilitychange",()=>{
  if(!document.hidden)load();
});
