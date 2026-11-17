const J = (o, s = 200) => new Response(JSON.stringify(o), { status: s, headers: { "content-type": "application/json; charset=utf-8", "access-control-allow-origin": "*", "cache-control": "no-store" } });
export default {
  async fetch(req, env) {
    const u = new URL(req.url), p = u.pathname;
    if (p === "/api/reports") return J((await env.DATA.get("index", "json")) || []);
    if (p === "/api/latest") {
      const id = await env.DATA.get("latest");
      if (!id) return J({ error: "no report" }, 404);
      return J(await env.DATA.get("report:" + id, "json"));
    }
    const m = p.match(/^\/api\/report\/([\w.-]+)$/);
    if (m) { const r = await env.DATA.get("report:" + m[1], "json"); return r ? J(r) : J({ error: "not found" }, 404); }
    if (p === "/" || p === "/index.html") return new Response(HTML, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    return new Response("Not found", { status: 404 });
  },
};
const HTML = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>新词监控 · AI 工具站选词</title><style>
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--fg:#e6e8ee;--mut:#8b93a7;--acc:#5b8cff;--ok:#2fbf71;--warn:#f0a030;--bad:#e5534b}
*{box-sizing:border-box}body{margin:0;font:14px/1.6 -apple-system,BlinkMacSystemFont,"PingFang SC","Microsoft YaHei",sans-serif;background:var(--bg);color:var(--fg)}
header{padding:16px 20px;border-bottom:1px solid var(--line);display:flex;flex-wrap:wrap;gap:12px;align-items:center;justify-content:space-between;position:sticky;top:0;background:var(--bg);z-index:5}
h1{font-size:18px;margin:0}h2{font-size:16px;margin:0 0 10px}main{max-width:1400px;margin:0 auto;padding:16px}
.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;margin-bottom:16px}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:16px}
select,input{background:#0c0e12;color:var(--fg);border:1px solid var(--line);border-radius:6px;padding:6px 8px}
.mut{color:var(--mut)}a{color:var(--acc)}.md ul{padding-left:18px;margin:6px 0}.md p{margin:6px 0}.md blockquote{border-left:3px solid var(--acc);margin:8px 0;padding:4px 10px;color:var(--mut)}
.filters{display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px}
table{width:100%;border-collapse:collapse;font-size:13px}th,td{border-bottom:1px solid var(--line);padding:8px 6px;text-align:left;vertical-align:top}
th{cursor:pointer;white-space:nowrap;color:var(--mut);position:sticky;top:0;background:var(--card)}tr.row:hover{background:#1d212a;cursor:pointer}
.score{font-weight:700;padding:2px 8px;border-radius:12px;display:inline-block}.tag{display:inline-block;padding:1px 6px;border-radius:4px;background:#232838;margin:1px;font-size:12px}
.detail td{background:#12151b}.kv{display:grid;grid-template-columns:130px 1fr;gap:4px 12px}.kv b{color:var(--mut);font-weight:500}
.wrap{overflow-x:auto}.kv div{white-space:pre-wrap;word-break:break-word}.late{color:var(--warn);font-weight:600}
</style></head><body>
<header><div><h1>🔥 新词监控 · AI 付费工具站选词</h1><div class="mut" id="meta">加载中…</div></div>
<div>历史报告：<select id="hist"></select></div></header>
<main>
<div class="card"><h2>本期摘要</h2><div class="md" id="summary"></div></div>
<div class="card"><h2>新词总表 <span class="mut" id="cnt"></span></h2>
<div class="filters"><input id="q" placeholder="搜索关键词/说明…"><select id="fcat"><option value="">全部分类</option></select>
<select id="ftool"><option value="">全部工具类型</option></select><select id="fstat"><option value="">全部状态</option></select>
<select id="fmin"><option value="0">评分不限</option><option value="5">≥5</option><option value="6">≥6</option><option value="7">≥7</option><option value="8">≥8</option></select></div>
<div class="wrap"><table><thead><tr>
<th data-k="score">评分 ▾</th><th data-k="keyword">新词</th><th data-k="category">分类</th><th data-k="tool_type">工具类型</th><th data-k="trend">趋势</th>
<th data-k="general_ai_can_do">通用AI能否</th><th data-k="pay_potential">付费潜力</th><th data-k="difficulty">难度</th><th>推荐域名</th><th data-k="status">状态</th></tr></thead><tbody id="tb"></tbody></table></div>
<div class="mut">点击任一行展开完整字段。</div></div>
<div class="card"><h2>分类整理</h2><div class="grid" id="bycat"></div></div>
<div class="grid">
<div class="card"><h2>趋势观察</h2><div class="md" id="trends"></div></div>
<div class="card"><h2>已过热 / 放弃</h2><div class="md" id="dropped"></div></div>
<div class="card"><h2>下期重点跟踪</h2><div class="md" id="watch"></div></div>
<div class="card"><h2>数据缺口与说明</h2><div class="md" id="gaps"></div></div>
</div>
<div class="card"><h2>数据来源</h2><div id="sources"></div></div>
</main>
<script>
const $=s=>document.querySelector(s);const esc=s=>String(s??"").replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
function md(t){t=esc(t||"");const L=t.split("\\n");let h="",inl=false;const il=x=>x.replace(/\\*\\*(.+?)\\*\\*/g,"<b>$1</b>").replace(/\\[(.+?)\\]\\((https?:[^)]+)\\)/g,'<a href="$2" target="_blank">$1</a>').replace(/\`(.+?)\`/g,"<code>$1</code>");
for(const l of L){const m=l.match(/^\\s*(?:[-*]|\\d+\\.)\\s+(.*)/);if(m){if(!inl){h+="<ul>";inl=true}h+="<li>"+il(m[1])+"</li>";continue}if(inl){h+="</ul>";inl=false}
if(l.startsWith("&gt; "))h+="<blockquote>"+il(l.slice(5))+"</blockquote>";else if(l.trim())h+="<p>"+il(l)+"</p>"}if(inl)h+="</ul>";return h}
const sc=s=>{const c=s>=7.5?"var(--ok)":s>=5.5?"var(--warn)":"var(--bad)";return '<span class="score" style="background:'+c+'22;color:'+c+'">'+s+'</span>'};
let R=null,sortK="score",sortD=-1,open=new Set();
async function load(id){const r=await fetch(id?"/api/report/"+id:"/api/latest");R=await r.json();render()}
function opts(sel,vals,label){sel.innerHTML='<option value="">'+label+'</option>'+[...new Set(vals)].filter(Boolean).map(v=>'<option>'+esc(v)+'</option>').join("")}
function render(){if(!R||R.error){$("#meta").textContent="暂无报告";return}
$("#meta").textContent=R.title+" · 共 "+R.keywords.length+" 个词";$("#hist").value=R.report_id;
for(const[k,el]of[["summary_md","#summary"],["trends_md","#trends"],["dropped_md","#dropped"],["watchlist_md","#watch"],["gaps_md","#gaps"]])$(el).innerHTML=md(R[k]);
$("#sources").innerHTML=(R.sources||[]).map(s=>'<span class="tag"><a target="_blank" href="'+esc(s.url)+'">'+esc(s.name)+'</a></span>').join(" ");
opts($("#fcat"),R.keywords.map(k=>k.category),"全部分类");opts($("#ftool"),R.keywords.map(k=>k.tool_type),"全部工具类型");opts($("#fstat"),R.keywords.map(k=>k.status),"全部状态");
const cats={};R.keywords.forEach(k=>(cats[k.category]=cats[k.category]||[]).push(k));
$("#bycat").innerHTML=Object.entries(cats).map(([c,ks])=>'<div><h3 style="margin:0 0 6px;font-size:14px">'+esc(c)+' <span class="mut">('+ks.length+')</span></h3>'+ks.sort((a,b)=>b.score-a.score).map(k=>'<div>'+sc(k.score)+' '+esc(k.keyword)+'</div>').join("")+'</div>').join("");table()}
function table(){const q=$("#q").value.toLowerCase(),fc=$("#fcat").value,ft=$("#ftool").value,fs=$("#fstat").value,mn=+$("#fmin").value;
let ks=R.keywords.filter(k=>(!fc||k.category==fc)&&(!ft||k.tool_type==ft)&&(!fs||k.status==fs)&&k.score>=mn&&(!q||JSON.stringify(k).toLowerCase().includes(q)));
ks.sort((a,b)=>{const x=a[sortK],y=b[sortK];return (typeof x=="number"?x-y:String(x).localeCompare(String(y),"zh"))*sortD});$("#cnt").textContent="("+ks.length+")"+(R.keywords.length?"":" · 本轮无新词");
$("#tb").innerHTML=ks.map((k,i)=>{const id=k.keyword;let h='<tr class="row" data-id="'+esc(id)+'"><td>'+sc(k.score)+'</td><td><b>'+esc(k.keyword)+'</b>'+(k.late?' <span class="late">发现偏晚</span>':'')+(k.format_class?' <span class="tag">'+esc(k.format_class)+'</span>':'')+(k.lag_hours!=null?' <span class="mut">T0→入库 '+esc(k.lag_hours)+'h · '+esc(k.stage||'')+'</span>':'')+'<div class="mut">'+esc(k.cn_explain)+'</div></td><td>'+esc(k.category)+'</td><td>'+esc(k.tool_type)+'</td><td>'+esc(k.trend)+'</td><td>'+esc(k.general_ai_can_do)+'</td><td>'+esc(k.pay_potential)+'</td><td>'+esc(k.difficulty)+'</td><td>'+(k.domains||[]).map(d=>'<span class="tag" title="'+esc(d.status)+'">'+(d.status.startsWith("已")?"❌ ":"✅ ")+esc(d.domain)+'</span>').join("")+'</td><td>'+esc(k.status)+'</td></tr>';
if(open.has(id)){const f=[["来源平台",esc(k.source_platform)+' · <a target="_blank" href="'+esc(k.source_url)+'">链接</a>'+(k.extra_links||[]).map((l,j)=>' · <a target="_blank" href="'+esc(l)+'">补充'+(j+1)+'</a>').join("")],["首次出现",k.first_seen],["爆发时间",k.breakout_date],["热度证据",k.trend_evidence],["用户需求",k.user_need],["通用AI",k.general_ai_can_do+" — "+k.general_ai_reason],["底层能力",k.underlying_models],["成本估算",k.cost_estimate],["竞争情况",k.competition],["域名情况",k.domain_taken],["收费方式",k.pricing_model],["别名",(k.aliases||[]).join(" / ")],["预计搜索写法",(k.search_variants||[]).map(p=>p.text+"（"+p.status+"）").join("\\n")],["时间（UTC）",k.ingested_at?("T0 "+(k.t0&&typeof k.t0=="object"?(k.t0.earliest+" ~ "+k.t0.latest+"（时效按较早端算）"):k.t0)+"\\nT0 依据 "+(k.t0_basis||"")+"\\n发现时间 "+k.discovered_at+"\\n入库时间 "+k.ingested_at+"\\n时效 "+k.lag_hours+" h · 阶段 "+k.stage+(k.late?" · 发现偏晚":"")):""],["复制证据",(k.copy_evidence||[]).map(x=>(x.account||"")+" · "+(x.posted_at||"未知")+" · "+(x.data_seen||"未知")).join("\\n")],["分项评分（五项之和×4）",k.score_parts?(["timing|发现早晚","heat|热度","demand|需求","competition|竞争","monetize|变现"].map(s=>{const[a,n]=s.split("|");const x=k.score_parts[a]||{};return n+" "+(x.score??"?")+"/5 — "+(x.basis||"")}).join("\\n")+"\\n总分 "+k.score_parts.total+"/100 → score "+k.score):""],["不确定之处",Array.isArray(k.uncertainties)?k.uncertainties.join("\\n"):k.uncertainties],["风险",k.risks+(k.risk_types&&k.risk_types.length?"\\n风险类别："+k.risk_types.join("、"):"")+(k.risk_level?"\\n风险等级："+k.risk_level:"")],["区域机会",k.regions]];
h+='<tr class="detail"><td colspan="10"><div class="kv">'+f.filter(([a,b])=>b!==undefined&&b!==null&&b!=="").map(([a,b])=>'<b>'+a+'</b><div>'+(a=="来源平台"?b:esc(b))+'</div>').join("")+'</div></td></tr>'}return h}).join("");
document.querySelectorAll("tr.row").forEach(tr=>tr.onclick=()=>{const id=tr.dataset.id;open.has(id)?open.delete(id):open.add(id);table()})}
document.querySelectorAll("th[data-k]").forEach(th=>th.onclick=()=>{const k=th.dataset.k;sortD=sortK==k?-sortD:(k=="score"?-1:1);sortK=k;table()});
["#q","#fcat","#ftool","#fstat","#fmin"].forEach(s=>$(s).addEventListener("input",table));
$("#hist").onchange=e=>load(e.target.value);
fetch("/api/reports").then(r=>r.json()).then(ix=>{$("#hist").innerHTML=ix.map(r=>'<option value="'+esc(r.report_id)+'">'+esc(r.title)+'</option>').join("");load()});
</script></body></html>`;
