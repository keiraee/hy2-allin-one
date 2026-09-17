#!/usr/bin/env bash
# panel.sh - Web 面板 HTML 生成

write_panel() {
  install -d -o hy2-aio -g caddy -m 2750 "$WEB_DIR" "$WEB_DIR/downloads"
  log "写入面板：${WEB_DIR}/index.html"
  cat > "$WEB_DIR/index.html" <<'HTML'
<!doctype html>
<html lang="zh-CN" data-theme="light">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>HY2 AIO</title>
<script>try{var t=localStorage.getItem("hy2-aio-theme");if(t==="dark"||t==="light")document.documentElement.setAttribute("data-theme",t);else if(window.matchMedia&&window.matchMedia("(prefers-color-scheme: dark)").matches)document.documentElement.setAttribute("data-theme","dark")}catch(e){}</script>
<style>
:root{
  --bg:#ffffff;--surface:#ffffff;--surface-2:#f5f5f4;--surface-3:#e9e9e7;
  --line:#e4e4e1;--text:#111111;--muted:#5c5c59;--faint:#8c8c88;
  --accent:#2a78d6;--bad:#d9463f;
  --radius:6px;--drawer:320px;
  --font:Inter,-apple-system,"Segoe UI",system-ui,sans-serif;
  --mono:ui-monospace,"SF Mono",Menlo,Consolas,monospace;
  --shadow:0 8px 24px rgba(17,17,17,.08);
  color-scheme:light;
  font-family:var(--font);font-size:13.5px;line-height:1.45;
  color:var(--text);background:var(--bg);
}
html[data-theme="dark"]{
  --bg:#111111;--surface:#161616;--surface-2:#1e1e1e;--surface-3:#2a2a2a;
  --line:#2a2a29;--text:#ececea;--muted:#a3a3a0;--faint:#6f6f6c;
  --accent:#3987e5;--bad:#d9463f;
  --shadow:0 12px 32px rgba(0,0,0,.45);
  color-scheme:dark;
}
*{box-sizing:border-box}html,body{margin:0;min-height:100vh;background:var(--bg);color:var(--text)}
a{color:inherit}button,input,select{font:inherit;color:inherit}
.mono,.metric .value,.nav-status,th,td,.dest-ip,.visit-cell,.client-card .ip,.hour-col .lbl,.day-col .amt,.day-col .lbl{font-family:var(--mono);font-variant-numeric:tabular-nums}
.shell{min-height:100vh;display:flex;flex-direction:column}
.topbar{display:flex;align-items:center;justify-content:space-between;gap:16px;height:48px;
  padding:0 20px;background:var(--bg);border-bottom:1px solid var(--line);position:sticky;top:0;z-index:30}
.nav-left,.nav-right{display:flex;align-items:center;gap:14px;min-width:0}
.nav-right{flex-shrink:0}
.brand{font-size:13px;font-weight:700;letter-spacing:.02em;white-space:nowrap}
.nav-status{font-size:12px;color:var(--faint);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:min(42vw,520px)}
.icon-btn{width:28px;height:28px;border:1px solid var(--line);border-radius:4px;background:var(--surface);color:var(--muted);cursor:pointer;display:inline-flex;align-items:center;justify-content:center;padding:0}
.icon-btn:hover{background:var(--surface-2);color:var(--text)}
.ico{width:16px;height:16px;display:block;flex-shrink:0}
.metric .label,.section-h h2{display:flex;align-items:center;gap:6px}
.btn{border:1px solid var(--line);border-radius:4px;background:var(--surface);color:inherit;
  padding:5px 10px;cursor:pointer;text-decoration:none;display:inline-flex;align-items:center;gap:6px;line-height:1.3}
.btn:hover{background:var(--surface-2)}.btn:disabled{opacity:.55;cursor:wait}
.btn.primary{background:var(--text);color:var(--bg);border-color:var(--text)}
.btn.primary:hover{filter:brightness(1.08)}
.btn.bad{color:var(--bad);border-color:var(--line)}
.btn.ghost{border-color:transparent;background:transparent}
.btn.ghost:hover{background:var(--surface-2)}
.main{flex:1;padding:20px;max-width:1440px;width:100%;margin:0 auto}
.metrics{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px;margin-bottom:16px}
.metric{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.metric .label{font-size:13px;font-weight:700}.metric .value{font-size:20px;font-weight:700;margin-top:6px}
.metric .extra{font-size:12px;color:var(--faint);margin-top:4px}
.bar{height:4px;background:var(--surface-3);border-radius:2px;overflow:hidden;margin-top:10px}
.bar i{display:block;height:100%;background:var(--accent);border-radius:2px}
.section{margin-top:8px}
.section-h{display:flex;align-items:center;justify-content:space-between;gap:10px;margin:0 0 10px}
.section-h h2{margin:0;font-size:13px;font-weight:700}
.pills{display:flex;flex-wrap:wrap;gap:8px}
.pill{font-size:12px;padding:5px 9px;border-radius:4px;border:1px solid var(--line);background:var(--surface);color:var(--muted)}
.pill.ok{color:var(--accent)}.pill.bad{color:var(--bad)}.pill.off{color:var(--faint)}
.table-wrap{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);overflow:auto}
table{width:100%;border-collapse:collapse}
th,td{padding:10px 12px;text-align:left;border-bottom:1px solid var(--line);font-size:13px;vertical-align:middle}
th{font-size:11.5px;color:var(--faint);font-weight:600;background:var(--surface);text-transform:none}
td.num,.dest-table td:nth-child(n+6){text-align:right}
#trafficLiveTable th:nth-child(n+6),#trafficSiteTable th:nth-child(n+4),#trafficSiteTable td:nth-child(n+4){text-align:right}
.table-wrap th:nth-child(4),.table-wrap td:nth-child(4),.table-wrap th:nth-child(5),.table-wrap td:nth-child(5),.table-wrap th:nth-child(6),.table-wrap td:nth-child(6),.table-wrap th:nth-child(7),.table-wrap td:nth-child(7){text-align:right}
tr:last-child td{border-bottom:0}
tr:hover td{background:var(--surface-2)}
tr.disabled td{opacity:.55}
.user-cell{display:flex;align-items:baseline;gap:6px;flex-wrap:wrap}
.user-name{font-weight:650;font-family:var(--mono)}
.user-note{color:var(--muted);font-size:12px}
.status-cell{display:flex;flex-direction:column;gap:2px;align-items:flex-start}
.status-dot{display:inline-flex;align-items:center;gap:6px}
.status-dot.on{color:var(--accent)}.status-dot.ban{color:var(--bad)}.status-dot.off{color:var(--faint)}
.status-active{font-size:12px;color:var(--faint);font-family:var(--mono)}
.ops{position:relative;text-align:right}
.menu-btn{width:28px;height:28px;border-radius:4px;border:1px solid transparent;background:transparent;
  cursor:pointer;display:inline-flex;align-items:center;justify-content:center;padding:0;color:var(--muted)}
.menu-btn:hover,.menu-btn.open{background:var(--surface-2);border-color:var(--line);color:var(--text)}
.menu{display:none;position:fixed;min-width:168px;background:var(--surface);
  border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow);padding:4px;z-index:45;
  max-height:calc(100vh - 16px);overflow:auto}
.menu.open{display:block}
.menu button{display:block;width:100%;text-align:left;border:0;background:transparent;padding:8px 10px;
  border-radius:4px;font:inherit;cursor:pointer;color:var(--text)}
.menu button:hover{background:var(--surface-2)}
.menu button.bad{color:var(--bad)}
.menu .sep{height:1px;background:var(--line);margin:4px}
.notice,.error{display:none;margin:0 0 14px;padding:10px 12px;border-radius:var(--radius);font-size:13px;line-height:1.45;border:1px solid var(--line);position:relative;padding-right:36px}
.notice.show,.error.show{display:block}
.notice{background:var(--surface-2);color:var(--muted)}
.notice-close{position:absolute;top:4px;right:4px;width:28px;height:28px;border:0;border-radius:4px;
  background:transparent;cursor:pointer;color:var(--muted);display:inline-flex;align-items:center;justify-content:center;padding:0}
.error{background:var(--surface);color:var(--bad);border-color:var(--bad)}
.error .notice-close{color:var(--bad)}
.footer{margin-top:18px;font-size:12px;color:var(--faint)}
.scrim{display:none;position:fixed;inset:0;background:rgba(17,17,17,.28);z-index:50}
.scrim.open{display:block}
.drawer{position:fixed;top:0;right:0;height:100%;width:min(var(--drawer),100%);background:var(--surface);
  border-left:1px solid var(--line);z-index:60;transform:translateX(100%);transition:transform .2s ease;
  display:flex;flex-direction:column}
.drawer.open{transform:translateX(0)}
.drawer-h{display:flex;align-items:center;justify-content:space-between;padding:12px 16px;border-bottom:1px solid var(--line);height:48px}
.drawer-h h2{margin:0;font-size:13px;font-weight:700}
.drawer-b{padding:16px;overflow:auto;flex:1}
.drawer-sec{margin-bottom:22px}
.drawer-sec h3{margin:0 0 10px;font-size:12px;color:var(--faint);font-weight:650}
.stack{display:flex;flex-direction:column;gap:8px}
.input{border:1px solid var(--line);border-radius:4px;padding:8px 10px;width:100%;background:var(--surface);font-family:var(--mono)}
.input:focus{outline:none;border-color:var(--text)}
.hint{font-size:12px;color:var(--muted);line-height:1.45;margin:0}
.toast{position:fixed;right:16px;bottom:16px;background:var(--text);color:var(--bg);padding:10px 14px;
  border-radius:var(--radius);opacity:0;pointer-events:none;transition:opacity .2s;z-index:100;max-width:320px;font-size:13px}
.toast.show{opacity:1}
.busy-scrim{display:none;position:fixed;inset:0;background:rgba(17,17,17,.42);z-index:90;align-items:center;justify-content:center;padding:16px}
.busy-scrim.open{display:flex}
html[data-theme="dark"] .busy-scrim{background:rgba(0,0,0,.55)}
.busy-card{display:flex;flex-direction:column;align-items:center;gap:10px;min-width:168px;padding:18px 22px;background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);box-shadow:var(--shadow)}
.busy-spin,.btn-spin{width:22px;height:22px;border:2px solid var(--surface-3);border-top-color:var(--accent);border-radius:99px;animation:busy-rotate .7s linear infinite;flex-shrink:0}
.btn-spin{width:14px;height:14px;border-width:1.5px}
@keyframes busy-rotate{to{transform:rotate(360deg)}}
.busy-card .hint{margin:0;text-align:center}
.btn.is-busy{cursor:wait}
.modal-scrim{display:none;position:fixed;inset:0;background:rgba(17,17,17,.4);z-index:70;align-items:center;justify-content:center;padding:8px}
.modal-scrim.open{display:flex}
.modal{background:var(--surface);border-radius:var(--radius);border:1px solid var(--line);width:min(400px,100%);padding:16px;box-shadow:var(--shadow)}
.modal h3{margin:0 0 6px;font-size:14px}
.modal .hint{margin-bottom:12px}
.modal-actions{display:flex;justify-content:flex-end;gap:8px;margin-top:14px}
.modal.traffic-modal{width:100%;height:100%;max-width:none;max-height:none;min-width:0;min-height:0;padding:0;display:flex;flex-direction:column;overflow:hidden;border-radius:var(--radius);background:var(--bg)}
.traffic-modal-h{display:flex;align-items:center;justify-content:space-between;padding:0 16px;height:48px;border-bottom:1px solid var(--line);background:var(--bg)}
.traffic-modal-h h2{margin:0;font-size:13px;font-weight:700}
.traffic-body{padding:16px 20px 20px;overflow:auto;flex:1;background:var(--bg)}
.traffic-kpis{display:grid;grid-template-columns:repeat(8,minmax(0,1fr));gap:10px;margin-bottom:12px}
.traffic-kpis .metric{padding:12px 14px}
.traffic-kpis .value{font-size:20px;margin-top:6px}
.traffic-kpis .hot{color:var(--bad)}
.traffic-peak{display:none;margin:0 0 12px;padding:10px 12px;border-radius:var(--radius);background:var(--surface-2);border:1px solid var(--line);color:var(--bad);font-size:13px}
.traffic-peak.show{display:block}
.traffic-summary{margin:0 0 12px;padding:10px 12px;border-radius:var(--radius);background:var(--surface-2);border:1px solid var(--line);color:var(--text);font-size:13px}
.traffic-tile{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:12px 14px}
.chart-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px;margin:0 0 12px}
.chart-grid .span-2{grid-column:span 2}
.traffic-board{display:grid;grid-template-columns:minmax(0,1.45fr) minmax(0,1fr);gap:12px;margin:0 0 12px}
.traffic-tables{display:grid;grid-template-columns:minmax(0,1fr) minmax(0,1.15fr);gap:12px;margin-top:12px}
.traffic-tables .dest-wrap{max-height:min(46vh,460px)}
.traffic-insights{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin:0 0 12px}
.traffic-stat{padding:12px 14px}
.traffic-stat .label{font-size:13px;font-weight:700}
.traffic-stat .value{font-size:20px;font-weight:700;margin:6px 0 4px;font-family:var(--mono)}
.traffic-stat .track{height:4px;background:var(--surface-3);border-radius:2px;overflow:hidden;margin-top:8px}
.traffic-stat .fill{display:block;height:100%;border-radius:2px;background:var(--accent)}
.hour-profile{display:flex;align-items:flex-end;gap:4px;height:170px}
.hour-col{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;min-width:0;height:100%}
.hour-col .bar{display:block;width:100%;border-radius:2px 2px 0 0;min-height:3px;background:var(--accent)}
.hour-col.peak .bar{background:var(--bad)}
.hour-col .lbl{font-size:11px;color:var(--faint);margin-top:6px}
.hour-profile.empty,.week-split.empty{display:flex;align-items:center;justify-content:center;height:170px}
.chart-empty{display:flex;flex-direction:column;align-items:center;gap:6px;color:var(--faint);font-size:12px}
.chart-empty .ico{width:20px;height:20px;opacity:.75}
.heat-cell.now{box-shadow:inset 0 0 0 1px var(--text)}
.day-cols{display:flex;align-items:stretch;gap:10px;height:170px}
.day-col{flex:1;display:flex;flex-direction:column;justify-content:flex-end;align-items:center;min-width:0}
.day-col .stack-bar{display:flex;flex-direction:column;justify-content:flex-end;width:100%;min-height:4px;border-radius:2px 2px 0 0;overflow:hidden}
.day-col .stack-bar i{display:block;width:100%;min-height:0}
.day-col .stack-bar .up{background:var(--muted)}
.day-col .stack-bar .down{background:var(--accent)}
.day-col .amt{font-size:11px;color:var(--text);margin:0 0 6px;white-space:nowrap}
.day-col .lbl{font-size:11px;color:var(--faint);white-space:nowrap;margin-top:4px}
.trend-note{font-size:12px;color:var(--muted);margin:6px 0 0}
.site-bars{display:flex;flex-direction:column;gap:8px;margin:0}
.site-bar-row{display:grid;grid-template-columns:minmax(0,1.4fr) minmax(0,2.2fr) auto;gap:10px;align-items:center;font-size:12px}
.site-bar-row .track{height:4px;background:var(--surface-3);border-radius:2px;overflow:hidden}
.site-bar-row .fill{display:block;height:100%;border-radius:2px;background:var(--accent)}
.traffic-mix{display:grid;grid-template-columns:170px minmax(0,1fr);gap:16px;align-items:center;margin:0}
.traffic-mix.hide{display:none}
.mix-svg{width:170px;height:170px;display:block}
.mix-legend{display:flex;flex-direction:column;gap:6px;font-size:12px}
.mix-legend span{display:flex;align-items:center;gap:8px;width:100%;min-width:0}
.mix-legend i{width:8px;height:8px;border-radius:99px;display:block;flex-shrink:0}
.mix-legend b{font-weight:650;word-break:break-all;min-width:0;flex:1}
.mix-legend em{font-style:normal;color:var(--faint);margin-left:auto;white-space:nowrap;font-family:var(--mono)}
.traffic-block{margin-bottom:0}
.traffic-block-h{display:flex;align-items:baseline;justify-content:space-between;gap:8px;margin-bottom:10px}
.traffic-block-h h3{margin:0;font-size:13px;font-weight:700}
.heat-wrap{overflow:auto}
.heat{display:grid;grid-template-columns:72px repeat(24,minmax(18px,1fr));gap:3px;align-items:center;min-width:780px}
.heat .h,.heat .d{font-size:11px;color:var(--faint);font-family:var(--mono)}
.heat .h{text-align:center}
.heat-cell{display:block;height:18px;border-radius:2px}
.heat-cell.peak{outline:1px solid var(--bad);outline-offset:0}
.heat-legend{display:flex;align-items:center;gap:6px;margin-top:10px;font-size:12px;color:var(--faint)}
.heat-legend b{width:14px;height:8px;border-radius:2px;display:block}
.trend-svg{width:100%;height:260px;display:block}
.updown{display:flex;height:4px;border-radius:2px;overflow:hidden;font-size:0;margin-top:12px}
.updown i{display:block;min-width:0;height:100%}
.updown .up{background:var(--muted)}
.updown .down{background:var(--accent)}
.updown-legend{display:flex;gap:12px;margin-top:8px;font-size:12px;color:var(--muted);font-family:var(--mono)}
.traffic-empty{display:none;margin:0 0 12px;padding:10px 12px;border-radius:var(--radius);background:var(--surface);border:1px solid var(--line)}
.traffic-empty.show{display:block}
.traffic-charts.hide{display:none}
.traffic-egress{margin:0;padding:0;border:0;background:transparent;font-size:13px}
.traffic-egress div+div{margin-top:6px}
.client-cards{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:8px;margin-top:10px}
.client-card{padding:10px 12px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface-2)}
.client-card .ip{font-weight:700;font-size:13px}
.client-card.on{border-color:var(--accent)}
.client-card.on .ip{color:var(--accent)}
.client-card .meta{font-size:12px;color:var(--faint);margin-top:4px}
.week-split{display:grid;grid-template-columns:1fr 1fr;gap:10px;margin-top:12px}
.week-card{padding:12px 14px;border:1px solid var(--line);border-radius:var(--radius);background:var(--surface)}
.week-card .label{font-size:12px;color:var(--muted)}
.week-card .value{font-size:20px;font-weight:700;margin:6px 0;font-family:var(--mono)}
.week-card .track{height:4px;background:var(--surface-3);border-radius:2px;overflow:hidden}
.week-card .fill{display:block;height:100%;border-radius:2px;background:var(--accent)}
.port-tag{display:inline-block;font-size:11px;color:var(--muted);background:var(--surface-2);border-radius:4px;padding:1px 6px;margin-left:4px;font-weight:600}
.dest-wrap{overflow:auto;border:1px solid var(--line);border-radius:var(--radius)}
.dest-table{width:100%;border-collapse:collapse;font-size:12px}
.dest-table th,.dest-table td{padding:8px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}
.dest-table th{font-size:11.5px;color:var(--faint);font-weight:600;background:var(--surface)}
.dest-table tr:last-child td{border-bottom:0}
.dest-host{font-weight:650;word-break:break-all}
.dest-ip{color:var(--accent)}
.visit-cell{white-space:nowrap}
.visit-cell .hint{margin:2px 0 0;font-size:11px;color:var(--faint)}
th.sortable{cursor:pointer;user-select:none;white-space:nowrap}
th.sortable:hover{color:var(--text)}
th.sortable.active{color:var(--text)}
th.sortable.active::after{content:attr(data-dir);margin-left:4px;font-size:10px}
.traffic-up{color:var(--muted)}.traffic-down{color:var(--accent)}
@media(max-width:1400px){
  .traffic-kpis{grid-template-columns:repeat(4,1fr)}
}
@media(max-width:1100px){
  .chart-grid{grid-template-columns:repeat(2,minmax(0,1fr))}
  .traffic-board,.traffic-tables,.traffic-insights{grid-template-columns:1fr}
  .traffic-kpis{grid-template-columns:repeat(4,1fr)}
  .metrics{grid-template-columns:repeat(2,1fr)}
}
@media(max-width:900px){
  .metrics{grid-template-columns:repeat(2,1fr)}
  .traffic-kpis{grid-template-columns:repeat(2,1fr)}
  .nav-status{display:none}
}
@media(max-width:720px){
  .table-wrap th:nth-child(3),.table-wrap td:nth-child(3),
  .table-wrap th:nth-child(7),.table-wrap td:nth-child(7){display:none}
  .traffic-kpis,.chart-grid,.traffic-board,.traffic-tables,.traffic-insights{grid-template-columns:1fr}
  .chart-grid .span-2{grid-column:auto}
  .traffic-mix{grid-template-columns:1fr}
  #trafficLiveTable th:nth-child(3),#trafficLiveTable td:nth-child(3),
  #trafficLiveTable th:nth-child(4),#trafficLiveTable td:nth-child(4){display:none}
  #trafficSiteTable th:nth-child(4),#trafficSiteTable td:nth-child(4),
  #trafficSiteTable th:nth-child(5),#trafficSiteTable td:nth-child(5){display:none}
}
@media(max-width:560px){
  .metrics{grid-template-columns:1fr}.main{padding:14px}
  .table-wrap th:nth-child(4),.table-wrap td:nth-child(4),
  .table-wrap th:nth-child(5),.table-wrap td:nth-child(5){display:none}
  .topbar{padding:0 12px}
  #trafficLiveTable th:nth-child(5),#trafficLiveTable td:nth-child(5),
  #trafficLiveTable th:nth-child(6),#trafficLiveTable td:nth-child(6),
  #trafficLiveTable th:nth-child(7),#trafficLiveTable td:nth-child(7){display:none}
  #trafficSiteTable th:nth-child(2),#trafficSiteTable td:nth-child(2),
  #trafficSiteTable th:nth-child(3),#trafficSiteTable td:nth-child(3),
  #trafficSiteTable th:nth-child(7),#trafficSiteTable td:nth-child(7){display:none}
}
</style>
</head>
<body>
<svg xmlns="http://www.w3.org/2000/svg" width="0" height="0" style="position:absolute;overflow:hidden" aria-hidden="true">
  <symbol id="i-sun" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/></symbol>
  <symbol id="i-moon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9z"/></symbol>
  <symbol id="i-x" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M18 6 6 18M6 6l12 12"/></symbol>
  <symbol id="i-menu" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 6h16M4 12h16M4 18h16"/></symbol>
  <symbol id="i-refresh" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><path d="M21 3v6h-6"/></symbol>
  <symbol id="i-more" viewBox="0 0 24 24" fill="currentColor" stroke="none"><circle cx="6" cy="12" r="1.5"/><circle cx="12" cy="12" r="1.5"/><circle cx="18" cy="12" r="1.5"/></symbol>
  <symbol id="i-power" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2v10"/><path d="M18.36 6.64a9 9 0 1 1-12.73 0"/></symbol>
  <symbol id="i-chart" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M18 20V10M12 20V4M6 20v-6"/></symbol>
  <symbol id="i-activity" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M22 12h-4l-3 7L9 5l-3 7H2"/></symbol>
  <symbol id="i-cpu" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="6" y="6" width="12" height="12" rx="1.5"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/></symbol>
  <symbol id="i-memory" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="7" width="18" height="10" rx="1.5"/><path d="M7 7v10M17 7v10M11 10h2M11 14h2"/></symbol>
  <symbol id="i-disk" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M4 20V8l4-4h12v16z"/><path d="M8 20v-6h8v6M8 4v4h7"/></symbol>
  <symbol id="i-server" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="6" rx="1.5"/><rect x="3" y="14" width="18" height="6" rx="1.5"/><path d="M7 7h.01M7 17h.01"/></symbol>
  <symbol id="i-users" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.75" stroke-linecap="round" stroke-linejoin="round"><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="3"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></symbol>
</svg>
<div class="shell">
  <header class="topbar">
    <div class="nav-left">
      <div class="brand">HY2 AIO</div>
    </div>
    <div class="nav-right">
      <div id="time" class="nav-status">正在读取数据…</div>
      <button id="themeBtn" class="icon-btn" type="button" aria-label="切换到深色" title="主题"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-moon"/></svg></button>
      <button id="syncBtn" class="btn primary" type="button"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-refresh"/></svg>同步</button>
      <button id="menuBtn" class="btn" type="button" aria-haspopup="dialog"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-menu"/></svg>菜单</button>
    </div>
  </header>

  <main class="main">
    <div id="error" class="error">
      <button id="errorClose" class="notice-close" type="button" aria-label="关闭"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-x"/></svg></button>
      <span id="errorText"></span>
    </div>
    <div id="hy2OffBanner" class="notice" role="status">
      HY2 已关闭。UDP 未监听，客户端无法连接。整机流量仍计入面板与 SSH。
    </div>
    <div id="notice" class="notice" role="note">
      <button id="noticeClose" class="notice-close" type="button" aria-label="关闭"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-x"/></svg></button>
      套餐用量以「本月整机流量」为准（网卡本地计数，对齐云厂商限制）；Clash 订阅进度与此同步。用户表为 HY2 代理分摊参考。云厂商控制台仍是最终账单。
    </div>

    <div class="metrics">
      <div class="metric">
        <div class="label"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-activity"/></svg>本月整机</div>
        <div id="traffic" class="value">--</div>
        <div id="remain" class="extra">--</div>
        <div class="bar"><i id="trafficBar" style="width:0"></i></div>
      </div>
      <div class="metric"><div class="label"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-cpu"/></svg>CPU / 负载</div><div id="cpu" class="value">--</div><div id="load" class="extra">--</div></div>
      <div class="metric"><div class="label"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-memory"/></svg>内存 / Swap</div><div id="memory" class="value">--</div><div id="swap" class="extra">--</div></div>
      <div class="metric"><div class="label"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-disk"/></svg>磁盘 / 运行</div><div id="disk" class="value">--</div><div id="uptime" class="extra">--</div></div>
    </div>
    <section class="section">
      <div class="section-h">
        <h2><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-server"/></svg>服务</h2>
        <button id="hy2Toggle" class="btn" type="button"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-power"/></svg>关闭 HY2</button>
      </div>
      <div id="services" class="pills"></div>
    </section>
    <section class="section">
      <div class="section-h">
        <h2><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-users"/></svg>用户</h2>
        <span id="userSummary" class="hint"></span>
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th class="sortable" data-sort="username">用户</th>
              <th class="sortable" data-sort="online">状态</th>
              <th>速率模式</th>
              <th class="sortable" data-sort="upload">上行</th>
              <th class="sortable" data-sort="download">下行</th>
              <th class="sortable" data-sort="total">合计</th>
              <th class="sortable" data-sort="lifetime_total">历史累计</th>
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
    <button id="drawerClose" class="btn ghost" type="button" aria-label="关闭"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-x"/></svg></button>
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
        <select id="logRange" class="input">
          <option value="1h">最近 1 小时</option>
          <option value="24h" selected>最近 24 小时</option>
          <option value="3d">最近 3 天</option>
        </select>
        <button id="exportLogs" class="btn" type="button">导出日志</button>
        <p class="hint">与菜单 18 相同：Hysteria / 面板 / Caddy。超过 10000 行时只留最新部分。</p>
      </div>
    </div>
    <div class="drawer-sec">
      <h3>备份</h3>
      <div class="stack">
        <button id="backupBtn" class="btn" type="button">立即备份</button>
        <p class="hint">手动创建一份完整备份快照，包含配置、证书和用户数据。</p>
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

<div id="trafficModal" class="modal-scrim" role="dialog" aria-modal="true" aria-labelledby="trafficTitle">
  <div class="modal traffic-modal">
    <div class="traffic-modal-h">
      <div>
        <h2 id="trafficTitle">流量分析</h2>
        <p id="trafficUser" class="hint" style="margin:4px 0 0"></p>
      </div>
      <button id="trafficClose" class="btn ghost" type="button" aria-label="关闭"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-x"/></svg></button>
    </div>
    <div class="traffic-body">
      <div class="traffic-kpis">
        <div class="metric"><div class="label">本月合计</div><div id="trafficMonth" class="value">--</div><div id="trafficMonthExtra" class="extra">--</div></div>
        <div class="metric"><div class="label">高峰时段</div><div id="trafficPeakVal" class="value hot">--</div><div id="trafficPeakExtra" class="extra">--</div></div>
        <div class="metric"><div class="label">最忙一天</div><div id="trafficBusyDay" class="value">--</div><div id="trafficBusyExtra" class="extra">--</div></div>
        <div class="metric"><div class="label">占整机</div><div id="trafficShare" class="value">--</div><div id="trafficShareExtra" class="extra">--</div></div>
        <div class="metric"><div class="label">当前连接</div><div id="trafficLiveCount" class="value">--</div><div id="trafficLiveExtra" class="extra">--</div></div>
        <div class="metric"><div class="label">近 7 日站点</div><div id="trafficSiteCount" class="value">--</div><div id="trafficSiteExtra" class="extra">--</div></div>
        <div class="metric"><div class="label">平均连接</div><div id="trafficSessionAvg" class="value">--</div><div id="trafficSessionExtra" class="extra">--</div></div>
        <div class="metric"><div class="label">白天用量</div><div id="trafficDayShare" class="value">--</div><div id="trafficDayShareExtra" class="extra">07:00–23:00</div></div>
      </div>
      <p id="trafficSummary" class="traffic-summary">正在整理这个用户的用量…</p>
      <p id="trafficPeak" class="traffic-peak"></p>
      <p id="trafficEmpty" class="traffic-empty hint">还没有 5 分钟增量曲线，热力会先空着；本月用量和站点仍可看。</p>
      <div id="trafficCharts" class="traffic-charts">
        <div class="chart-grid">
          <div class="traffic-tile traffic-block span-2">
            <div class="traffic-block-h">
              <h3>时段热力</h3>
              <span class="hint">越深越多 · 描边格是此刻</span>
            </div>
            <div class="heat-wrap"><div id="trafficHeat" class="heat" role="img" aria-label="近7日每小时流量热力"></div></div>
            <div id="trafficHeatLegend" class="heat-legend"></div>
            <p id="trafficHeatHint" class="hint" style="margin-top:8px">颜色越深蓝这一小时越多，悬停可看具体用量。</p>
          </div>
          <div class="traffic-tile traffic-block">
            <div class="traffic-block-h">
              <h3>作息曲线</h3>
              <span class="hint">7 天压成一天</span>
            </div>
            <div id="trafficHours" class="hour-profile empty" role="img" aria-label="一天中各小时用量"><div class="chart-empty"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-chart"/></svg><span>暂无数据，请先同步历史流量</span></div></div>
            <p id="trafficHoursHint" class="hint" style="margin-top:8px"></p>
          </div>
          <div class="traffic-tile traffic-block span-2">
            <div class="traffic-block-h">
              <h3>增量趋势</h3>
              <span class="hint">灰=上行 · 蓝=下行 · 红点峰值</span>
            </div>
            <div id="trafficTrend"></div>
          </div>
          <div class="traffic-tile traffic-block">
            <div class="traffic-block-h">
              <h3>按日用量</h3>
              <span class="hint">灰上行 · 蓝下行</span>
            </div>
            <div id="trafficDays" class="day-cols" role="img" aria-label="近7日用量"></div>
            <div class="traffic-block-h" style="margin-top:14px">
              <h3>上下行结构</h3>
              <span id="trafficSplitHint" class="hint"></span>
            </div>
            <div id="trafficUpDown" class="updown" role="img" aria-label="上下行比例"></div>
          </div>
        </div>
        <div class="traffic-insights">
          <div class="traffic-tile traffic-stat">
            <div class="label">白天 / 夜间</div>
            <div id="trafficDayNightVal" class="value">--</div>
            <div id="trafficDayNightHint" class="hint">白天按 07:00–23:00 计</div>
            <div class="track"><i id="trafficDayNightFill" class="fill" style="width:0"></i></div>
          </div>
          <div class="traffic-tile traffic-stat">
            <div class="label">工作日 / 周末</div>
            <div id="trafficWeek" class="week-split empty"><div class="chart-empty"><svg class="ico" viewBox="0 0 24 24" aria-hidden="true"><use href="#i-chart"/></svg><span>暂无数据</span></div></div>
            <p id="trafficWeekHint" class="hint" style="margin-top:8px"></p>
          </div>
          <div class="traffic-tile traffic-stat">
            <div class="label">最近一次连接</div>
            <div id="trafficLastSession" class="value">--</div>
            <div id="trafficLastSessionHint" class="hint">来自连接日志配对</div>
            <div class="label" style="margin-top:12px">已结束会话</div>
            <div id="trafficSessionCount" class="value">--</div>
            <div id="trafficSessionCountHint" class="hint">含仍在线的连接</div>
          </div>
        </div>
      </div>
      <div class="traffic-board">
        <div class="traffic-tile traffic-block">
          <div class="traffic-block-h">
            <h3>出口与客户端</h3>
            <span class="hint">外站看到的地址 · 用户侧 IP</span>
          </div>
          <div id="trafficEgress" class="traffic-egress">
            <div id="trafficEgressLine">出口 IP：--</div>
            <div id="trafficClient">客户端：--</div>
            <div id="trafficClients" class="client-cards"></div>
          </div>
        </div>
        <div class="traffic-tile traffic-block">
          <div class="traffic-block-h">
            <h3>站点构成</h3>
            <span class="hint">近 7 日 Top 5 + 其他 · 按根域名合并</span>
          </div>
          <div id="trafficMix" class="traffic-mix"></div>
          <p id="trafficMixHint" class="hint" style="margin:8px 0 12px"></p>
          <div id="trafficSiteBars" class="site-bars"></div>
        </div>
      </div>
      <div class="traffic-tables">
        <div class="traffic-tile traffic-block">
          <div class="traffic-block-h">
            <h3>当前连接</h3>
            <span class="hint">点表头排序 · 含访问时间</span>
          </div>
          <div class="dest-wrap"><table id="trafficLiveTable" class="dest-table"><thead><tr>
            <th class="sortable" data-sort="host" aria-sort="none">网站</th>
            <th class="sortable" data-sort="client" aria-sort="none">客户端</th>
            <th class="sortable" data-sort="ip" aria-sort="none">目标 IP</th>
            <th class="sortable" data-sort="port" aria-sort="none">端口</th>
            <th class="sortable" data-sort="state" aria-sort="none">状态</th>
            <th class="sortable" data-sort="upload" aria-sort="none">上行</th>
            <th class="sortable" data-sort="download" aria-sort="none">下行</th>
            <th class="sortable" data-sort="total" aria-sort="none">合计</th>
            <th class="sortable" data-sort="last_active" aria-sort="none">访问时间</th>
          </tr></thead><tbody id="trafficLive"></tbody></table></div>
        </div>
        <div class="traffic-tile traffic-block">
          <div class="traffic-block-h">
            <h3>访问站点</h3>
            <span class="hint">近 7 日 · 含首次 / 最近访问时间</span>
          </div>
          <div class="dest-wrap"><table id="trafficSiteTable" class="dest-table"><thead><tr>
            <th class="sortable" data-sort="host" aria-sort="none">网站</th>
            <th class="sortable" data-sort="ip" aria-sort="none">IP</th>
            <th class="sortable" data-sort="port" aria-sort="none">端口</th>
            <th class="sortable" data-sort="upload" aria-sort="none">上行</th>
            <th class="sortable" data-sort="download" aria-sort="none">下行</th>
            <th class="sortable" data-sort="total" aria-sort="none">合计</th>
            <th class="sortable" data-sort="hits" aria-sort="none">次数</th>
            <th class="sortable" data-sort="share" aria-sort="none">占比</th>
            <th class="sortable" data-sort="first_seen" aria-sort="none">首次访问</th>
            <th class="sortable" data-sort="last_seen" aria-sort="none">最近访问</th>
          </tr></thead><tbody id="trafficSites"></tbody></table></div>
          <p class="hint" style="margin-top:8px">访问时间来自连接日志和采样。短连接会记进站点列表。Clash TUN 走 IP 时，仍需服务端嗅探才能显示域名。</p>
        </div>
      </div>
    </div>
  </div>
</div>

<div id="busyScrim" class="busy-scrim" aria-hidden="true" aria-busy="false">
  <div class="busy-card" role="status">
    <span class="busy-spin" aria-hidden="true"></span>
    <p id="busyText" class="hint">处理中，请稍候…</p>
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
  const totals=series.map((_,i)=>ups[i]+downs[i]);
  const maxLine=Math.max(1,...ups,...downs);
  const W=1100,H=280,padL=64,padR=20,padT=24,padB=36;
  const innerW=W-padL-padR, innerH=H-padT-padB;
  const x=i=>series.length<=1?padL:padL+innerW*i/Math.max(series.length-1,1);
  const y=v=>padT+innerH-(v/maxLine*innerH);
  const line=values=>values.map((v,i)=>x(i)+","+y(v)).join(" ");
  const area=values=>values.map((v,i)=>x(i)+","+y(v)).join(" ")+" "+x(values.length-1)+","+y(0)+" "+x(0)+","+y(0);
  const peakIdx=totals.reduce((best,value,i)=>value>totals[best]?i:best,0);
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
  const peakX=x(peakIdx), peakY=y(Math.max(ups[peakIdx],downs[peakIdx]));
  svg.append(svgNode("circle",{cx:peakX,cy:peakY,r:4.5,fill:bad}));
  const peakLabel=bytes(totals[peakIdx]);
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
  trend.append(el("p",{className:"trend-note",text:"红点峰值约 "+bytes(totals[peakIdx])+"（↑ "+bytes(ups[peakIdx])+" · ↓ "+bytes(downs[peakIdx])+"）。纵轴最大 "+bytes(maxLine)+"。"}));
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
function renderSiteRows(){
  const siteRoot=$("trafficSites");clearNode(siteRoot);
  const sites=sortedRows(siteList,siteSort);
  markSort($("trafficSiteTable"),siteSort);
  if(!sites.length){
    siteRoot.append(el("tr",{},el("td",{colSpan:10,className:"hint",text:"还没有采样到访问站点"})));
    return;
  }
  sites.forEach(row=>{
    siteRoot.append(el("tr",{},
      el("td",{className:"dest-host"},
        el("div",{text:row.host||"--"}),
        row.root&&row.root!==row.host?el("div",{className:"hint",text:row.root}):null
      ),
      el("td",{className:"dest-ip",text:row.ip||"--"}),
      el("td",{},el("span",{text:row.port||"--"}),portName(row.port)?el("span",{className:"port-tag",text:portName(row.port)}):null),
      el("td",{className:"traffic-up",text:"↑ "+bytes(row.upload)}),
      el("td",{className:"traffic-down",text:"↓ "+bytes(row.download)}),
      el("td",{text:Number(row.total)?bytes(row.total):(Number(row.hits)||0)+" 次"}),
      el("td",{text:String(row.hits||0)+" 次"}),
      el("td",{text:formatPct(row.share)}),
      visitCell(row.first_seen||row.last_seen),
      visitCell(row.last_seen)
    ));
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
async function copyCredential(username,kind){
  closeMenus();
  try{
    const result=await apiPost("api/user/credentials",{username,kind});
    await copyText(result.value);
    toast("已复制");
  }catch(error){toast("复制失败："+error.message)}
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
  if(!disabled&&!confirm("确认禁用 "+username+"？该用户将立即无法连接，数据保留。"))return;
  await runMutate(null,async()=>{
    try{
      const result=await apiPost(disabled?"api/user/enable":"api/user/disable",{username});
      toast(result.message||(disabled?"已启用 "+username:"已禁用 "+username));
      await load();
    }catch(error){toast("操作失败："+error.message)}
  },disabled?"正在启用用户…":"正在禁用用户…");
}
async function removeUser(username){
  closeMenus();
  if(!confirm("确认删除用户 "+username+"？此操作不可恢复。"))return;
  await runMutate(null,async()=>{
    try{
      await apiPost("api/user/remove",{username});
      toast("已删除 "+username);
      await load();
    }catch(error){toast("删除失败："+error.message)}
  },"正在删除用户…");
}
async function rotateUser(username){
  closeMenus();
  if(!confirm("确认轮换 "+username+" 的密码与订阅 token？旧订阅将失效。"))return;
  await runMutate(null,async()=>{
    try{
      await apiPost("api/user/rotate",{username});
      toast("已轮换 "+username+" 的密钥");
      await load();
    }catch(error){toast("轮换失败："+error.message)}
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
      const message=String(error&&error.message||"");
      if(/用户已存在/.test(message)){
        await load();
        if((userList||[]).some(user=>user.username===username)){
          input.value="";
          toast("已添加 "+username);
          setDrawer(false);
          return;
        }
      }
      toast("添加失败："+message);
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
  if(enabled&&!confirm("确认关闭 Hysteria？客户端将无法连接。"))return;
  await runMutate($("hy2Toggle"),async()=>{
    try{
      await apiPost(enabled?"api/hy2/off":"api/hy2/on",{});
      toast(enabled?"HY2 已关闭":"HY2 已开启");
      await load();
    }catch(error){toast("操作失败："+error.message)}
  },enabled?"正在关闭 HY2…":"正在开启 HY2…");
}
function menuItem(text,handler,bad){
  return el("button",{type:"button",className:bad?"bad":"",text,onclick:handler});
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
      menuItem("复制订阅",()=>copyCredential(user.username,"subscription")),
      menuItem("复制直链",()=>copyCredential(user.username,"direct")),
      menuItem("复制密码",()=>copyCredential(user.username,"password")),
      el("div",{className:"sep"}),
      menuItem("流量分析",()=>{closeMenus();openTraffic(user.username)}),
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
    $("time").textContent=(ver&&ver!=="unknown"?("v"+ver+" · "):"")+"更新 "+data.generated_at+" · "+data.server.ip+" · "+data.server.domain;
    $("traffic").textContent=bytes(t.used)+" / "+bytes(t.limit);
    $("remain").textContent="入 "+bytes(t.rx)+" · 出 "+bytes(t.tx)+" · 剩余 "+bytes(t.remain);
    const pctVal=Math.min(100,Number(t.percent)||0);
    $("trafficBar").style.width=pctVal+"%";
    $("trafficBar").style.background=pctVal>=90?"var(--bad)":"var(--accent)";
    $("cpu").textContent=data.server.cpu+"%";$("load").textContent="负载 "+data.server.load.join(" / ");
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
setInterval(load,60000);
</script>
</body>
</html>
HTML

  chown -R hy2-aio:caddy "$WEB_DIR"
  find "$WEB_DIR" -type d -exec chmod 2750 {} \;
  find "$WEB_DIR" -type f -exec chmod 0640 {} \;
}
