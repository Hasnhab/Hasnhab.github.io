import os
import re
import json
import html
from datetime import datetime
from mitmproxy import http
from urllib.parse import parse_qs, urlparse

# Strict storage under project folder
desktop = os.path.join(os.path.expanduser("~"), "Desktop")
BASE_DIR = os.path.join(desktop, "graphql_harvester")
os.makedirs(BASE_DIR, exist_ok=True)

REPO_HTML    = os.path.join(BASE_DIR, "repository.html")
SESSION_HTML = os.path.join(BASE_DIR, "session.html")
REPO_INDEX   = os.path.join(BASE_DIR, "index.json")

ASSETS_DIR = os.path.join(BASE_DIR, "assets")
os.makedirs(ASSETS_DIR, exist_ok=True)
LOGO_REL_PATH = "assets/logo_xvisor03.png"  # place your file at Desktop/graphql_harvester/assets/logo_xvisor03.png

# State (accumulative + session)
repo_items = []
repo_seen_docids = set()
session_items = []
session_seen_docids = set()

# Global caches
CACHE_DOC_BY_BASE = {}
CACHE_VARS_BY_BASE = {}
CACHE_MODULE_BY_BASE = {}

# Observed parameters store
# OBSERVED_PARAMS[normKey] = {"values": {reprValue: count}, "count": int}
OBSERVED_PARAMS = {}

def _norm_key(k: str) -> str:
    if not k:
        return ""
    s = str(k).strip()
    s1 = re.sub(r"[^A-Za-z0-9_]", "", s)
    return s1.lower()

def _repr_value(v):
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    try:
        if isinstance(v, str):
            return json.dumps(v)  # quoted
        return json.dumps(v)
    except Exception:
        return str(v)

def _observed_add_from_dict(d: dict):
    for k, v in (d or {}).items():
        nk = _norm_key(k)
        if not nk:
            continue
        val_repr = _repr_value(v)
        slot = OBSERVED_PARAMS.get(nk) or {"values": {}, "count": 0}
        slot["values"][val_repr] = slot["values"].get(val_repr, 0) + 1
        slot["count"] += 1
        OBSERVED_PARAMS[nk] = slot

def _observed_top_value(nk: str):
    slot = OBSERVED_PARAMS.get(nk)
    if not slot:
        return None
    vals = slot["values"]
    if not vals:
        return None
    return sorted(vals.items(), key=lambda x: (-x[1], x[0]))[0][0]

def _observed_snapshot():
    out = {}
    for nk, slot in OBSERVED_PARAMS.items():
        topv = _observed_top_value(nk)
        tops = sorted(slot["values"].items(), key=lambda x: (-x[1], x[0]))[:5]
        out[nk] = {
            "count": slot.get("count", 0),
            "value": topv if topv is not None else None,
            "values": [{"v": k, "c": c} for k, c in tops]
        }
    return out

# ---------- HTML UI ----------
def _html_header(title, banner_color, subtitle="By Hasan Habeeb", page_kind="repo"):
    table_id = "repo_graphql_table" if page_kind == "repo" else "session_graphql_table"
    observed_json = json.dumps(_observed_snapshot(), ensure_ascii=False)
    tpl = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>__TITLE__</title>
<style>
  :root{
    --bg:#0a0b10; --bg2:#0d0f16; --fg:#e5e7eb; --muted:#9ca3af;
    --panel:#12141b; --panel2:#0f1218; --border:#1f2430;
    --brandRed:#ff2a2a; --brandGlow:#ff3b3b;
    --ok:#10b981; --warn:#f59e0b; --danger:#ef4444;
    --fontBrand: 'Inter','Segoe UI',Arial,sans-serif;
  }
  *{box-sizing:border-box}
  html,body{height:100%}
  body{margin:0; padding:0 18px 24px; font-family:var(--fontBrand); color:var(--fg); background:var(--bg); overflow-y:auto;}
  .bg-logo{position:fixed; inset:0; z-index:0; pointer-events:none; background-image:url('__LOGO_PATH__'); background-repeat:no-repeat; background-position:center 20%; background-size:900px auto; opacity:0.06; filter:blur(28px) saturate(140%); mix-blend-mode:screen; transform:translateZ(0);}
  .app-root{position:relative; z-index:1; min-height:100vh; padding-top:10px;}
  .banner{position:relative; display:flex; align-items:center; justify-content:space-between; gap:12px; flex-wrap:wrap; padding:14px 18px; margin:0 -18px 16px; color:#fff; background:linear-gradient(90deg, rgba(25,25,30,0.9), rgba(12,12,16,0.95)); border-bottom:1px solid rgba(255,255,255,0.06); box-shadow:0 6px 30px rgba(0,0,0,0.6), inset 0 -1px 0 rgba(255,255,255,0.02);}
  .brand-left{display:flex; align-items:center; gap:12px}
  .brand-logo-img{width:56px; height:56px; object-fit:contain; filter: drop-shadow(0 0 18px rgba(255,42,42,0.55)); border-radius:8px; background:linear-gradient(180deg, rgba(255,255,255,0.03), rgba(0,0,0,0.12)); padding:6px}
  .brand-text{display:flex; flex-direction:column; line-height:1.05}
  .brand-name{font-weight:900; font-size:20px; color:#fff; text-shadow:0 0 8px var(--brandGlow)}
  .brand-page{font-weight:800; font-size:14px; color:#cbd5e1; opacity:0.95}
  .brand-sub{font-size:13px; font-weight:800; background:rgba(255,42,42,0.08); border:1px solid rgba(255,42,42,0.25); padding:6px 10px; border-radius:999px;}
  .kpis{display:flex; gap:10px; flex-wrap:wrap; margin-bottom:10px}
  .kpi{background:var(--panel2); border:1px solid var(--border); border-radius:8px; padding:10px; min-width:150px}
  .kpi .label{font-size:12px; color:var(--muted)}
  .kpi .value{font-size:18px; font-weight:700; color:var(--fg)}
  .toolbar{display:flex; flex-wrap:wrap; gap:8px; align-items:center; margin:8px 0 12px}
  .toolbar input,.toolbar textarea{padding:6px 10px; border:1px solid var(--border); background:var(--panel); color:var(--fg); border-radius:6px}
  .toolbar button{padding:6px 10px; border:1px solid var(--border); background:var(--panel2); color:var(--fg); border-radius:6px; cursor:pointer; transition: box-shadow 120ms ease}
  .toolbar button:hover{box-shadow:0 6px 24px rgba(255,42,42,0.09), 0 0 0 1px rgba(255,42,42,0.14)}
  .dash-grid{display:grid; grid-template-columns:1.3fr 1fr; gap:12px}
  .panel{background:var(--panel); border:1px solid var(--border); border-radius:8px; padding:12px}
  .panel h4{margin:0 0 10px 0; font-weight:800; color:#cbd5e1}
  .card{background:var(--panel2); border:1px solid var(--border); border-radius:8px; padding:10px}
  .card h5{margin:0 0 8px 0; color:#9ca3af; font-size:13px}
  .row{display:flex; gap:8px; align-items:center; flex-wrap:wrap}
  .muted{color:var(--muted)}
  .hint-badge{display:inline-flex; align-items:center; gap:6px; padding:2px 8px; font-size:12px; border-radius:999px; background:#10131a; border:1px solid #1f2430; color:#cbd5e1;}
  .hint-badge .dot{width:6px; height:6px; border-radius:50%; background:var(--warn)}
  .observed-panel{margin-top:10px; background:#10131a; border:1px solid #1f2430; border-radius:8px; padding:10px}
  .observed-row{display:grid; grid-template-columns: 1.2fr .7fr 1fr auto auto; gap:8px; align-items:center; margin-bottom:8px}
  .observed-key{font-weight:700; color:#e5e7eb}
  .observed-count{color:#9ca3af; font-size:12px}
  .observed-select{width:100%; padding:6px 8px; border:1px solid var(--border); background:#0f1218; color:#e5e7eb; border-radius:6px}
  .observed-actions .btn{margin-right:6px}
  table{width:100%; border-collapse:collapse; background:var(--panel2); border:1px solid var(--border)}
  th,td{border:1px solid var(--border); padding:8px 10px; vertical-align:top; font-size:13px}
  th{background:var(--panel); text-align:left; color:var(--muted)}
  tr:nth-child(even) td{background:#0d1118}
  pre{margin:0; white-space:pre-wrap; word-break:break-word; font-family:Consolas, monospace; font-size:12px; color:#cbd5e1}
  #detail_overlay{display:none; position:fixed; inset:0; background:rgba(0,0,0,0.65); z-index:10000; align-items:center; justify-content:center}
  #detail_overlay.active{display:flex}
  .detail_card{width:96vw; height:92vh; display:flex; flex-direction:column; background:var(--panel2); border:1px solid var(--border); border-radius:10px}
  .detail_header{display:flex; justify-content:space-between; align-items:center; padding:10px 12px; border-bottom:1px solid var(--border); gap:8px; flex-wrap:wrap}
  .pill{display:inline-flex; align-items:center; gap:6px; padding:4px 8px; border-radius:999px; background:#0f1218; border:1px solid #1f2430; color:#cbd5e1; font-size:12px}
  .btn{padding:6px 10px; border:1px solid var(--border); background:var(--panel); color:var(--fg); border-radius:6px; cursor:pointer; transition: box-shadow 120ms ease}
  .btn:hover{box-shadow:0 6px 24px rgba(255,42,42,0.08)}
  .detail_body{flex:1; display:grid; grid-template-columns:2fr 1fr; gap:12px; padding:12px; overflow:hidden}
  .block{background:#0f1218; border:1px solid #1f2430; border-radius:8px; padding:10px; display:flex; flex-direction:column; overflow:hidden}
  .json-tree{font-family:Consolas, monospace; font-size:12px; color:#cbd5e1; flex:1 1 auto; overflow:auto; background:#0d1118; border:1px solid #1f2430; border-radius:6px; padding:8px}
  .json-k{color:#93c5fd}
  .json-v-str{color:#86efac}
  .json-v-num{color:#fde68a}
  .json-v-bool{color:#fca5a5}
  .json-collapser{cursor:pointer; user-select:none; color:#a5b4fc; margin-right:6px}
  .hint-table{width:100%; border-collapse:collapse; background:#0d1118; border:1px solid #1f2430}
  .hint-table th,.hint-table td{border:1px solid #1f2430; padding:6px 8px; font-size:12px}
  .hint-ok{color:#10b981}
  .hint-miss{color:#ef4444}
  .host-pill,.src-pill{background:#0d1118; border:1px solid #1f2430; border-radius:999px; padding:4px 8px; color:#cbd5e1; font-size:12px; display:inline-flex; gap:6px; align-items:center}
  .auto-pill{background:rgba(255,42,42,0.12); border-color:rgba(255,42,42,0.35);}
  @media (max-width:900px){ .dash-grid{grid-template-columns:1fr} .brand-logo-img{width:48px; height:48px} .brand-name{font-size:18px} .observed-row{grid-template-columns:1fr 1fr 1fr auto auto}}
</style>
<script>
(function(){
  const tableId = "__TABLE_ID__";
  const pageKind = "__PAGE_KIND__";
  window.__OBSERVED__ = __OBSERVED_JSON__;

  function getRows(){ const t=document.getElementById(tableId); if(!t) return []; return Array.from(t.querySelectorAll('tbody tr')); }
  function parseJSONSafe(s){ try { return JSON.parse(s); } catch(e){ return null; } }
  function rowObj(tr){
    const tds = tr.querySelectorAll('td');
    const pre = tds[2] ? tds[2].querySelector('pre') : null;
    const vars = pre ? pre.innerText : "{}";
    return {
      idx: tds[0]?.innerText.trim() || "",
      docid: tds[1]?.innerText.trim() || "",
      v: vars,
      vObj: parseJSONSafe(vars) || {},
      module: tr.getAttribute('data-module') || "",
      varsjson: tr.getAttribute('data-varsjson') || "",
      host: tr.getAttribute('data-host') || "",
      src: tr.getAttribute('data-src') || "",
      tr
    };
  }

  function normKey(k){
    if(!k) return '';
    const s = String(k).trim();
    const s1 = s.replace(/[^A-Za-z0-9_]/g,'');
    return s1.toLowerCase();
  }

  function applyFilters(){
    const idf = (document.getElementById('filter_docid')||{value:''}).value.toLowerCase();
    const mf  = (document.getElementById('filter_module')||{value:''}).value.toLowerCase();
    const hf  = (document.getElementById('filter_host')||{value:''}).value.toLowerCase();
    const tf  = (document.getElementById('filter_text')||{value:''}).value.toLowerCase();
    getRows().forEach(tr=>{
      const o=rowObj(tr);
      const hay=(o.docid+' '+o.module+' '+o.host+' '+o.v).toLowerCase();
      const show = (!idf || o.docid.toLowerCase().includes(idf))
                && (!mf  || o.module.toLowerCase().includes(mf))
                && (!hf  || o.host.toLowerCase().includes(hf))
                && (!tf  || hay.includes(tf));
      tr.style.display = show ? '' : 'none';
    });
    // Auto-add observed hints before rendering badges/panels
    autoAddObservedCandidates();
    updateKPIs();
    renderRepeatedHints();
    renderPatternMatches();
    updateBulkHintBadge();
    renderObservedPanel();
  }

  function updateKPIs(){
    const all=getRows(), vis=all.filter(tr=>tr.style.display!=='none');
    const t=document.getElementById('kpi_total'); const v=document.getElementById('kpi_visible');
    if(t) t.textContent=all.length; if(v) v.textContent=vis.length;
  }

  function openDetailFromTr(tr){
    const o=rowObj(tr), ov=document.getElementById('detail_overlay'); if(!ov) return;
    document.getElementById('det_docid').textContent=o.docid||'';
    document.getElementById('det_module').textContent=o.module||'';
    document.getElementById('det_host').textContent=o.host||'(unknown)';
    document.getElementById('det_src').textContent=o.src||'(unknown)';
    renderJSONTreeFromObj(o.vObj||{}, document.getElementById('det_vars'));
    ov.classList.add('active');
  }
  function closeDetail(){ const ov=document.getElementById('detail_overlay'); if(ov) ov.classList.remove('active'); }

  function attachClicks(){
    getRows().forEach(tr=>{
      tr.addEventListener('click', (e)=>{ if(['BUTTON','INPUT','SELECT','A','TEXTAREA','LABEL'].includes(e.target.tagName)) return; openDetailFromTr(tr); });
    });
  }

  function renderJSONTreeFromObj(obj, container){
    if(!obj || typeof obj!=='object'){ container.textContent='(empty)'; return; }
    container.innerHTML=''; container.appendChild(jsonNode(obj,'root'));
  }
  function jsonNode(value,key){
    const wrap=document.createElement('div'); wrap.className='json-entry';
    if(typeof value==='object' && value!==null){
      const isArray=Array.isArray(value);
      const details=document.createElement('details'); details.open=true;
      const summary=document.createElement('summary');
      const coll=document.createElement('span'); coll.className='json-collapser'; coll.textContent=isArray?'[]':'{}';
      const k=document.createElement('span'); k.className='json-k'; k.textContent=key==='root'?(isArray?`Array[${value.length}]`:'Object'):key+':';
      summary.appendChild(coll); summary.appendChild(k); details.appendChild(summary);
      Object.keys(value).forEach(chKey=>{
        const chWrap=document.createElement('div'); chWrap.style.marginLeft='16px'; chWrap.appendChild(jsonNode(value[chKey], chKey)); details.appendChild(chWrap);
      });
      wrap.appendChild(details);
    } else {
      const k=document.createElement('span'); k.className='json-k'; k.textContent=key==='root'?'':key+': ';
      let v=document.createElement('span');
      if(typeof value==='string'){ v.className='json-v-str'; v.textContent=JSON.stringify(value); }
      else if(typeof value==='number'){ v.className='json-v-num'; v.textContent=String(value); }
      else if(typeof value==='boolean'){ v.className='json-v-bool'; v.textContent=String(value); }
      else if(value===null){ v.className='json-v-bool'; v.textContent='null'; }
      wrap.appendChild(k); wrap.appendChild(v);
    }
    return wrap;
  }

  // Injection state
  const LS_KEY = 'pf_injection_rules';
  const LS_PRESETS_KEY = 'pf_injection_presets';
  const LS_AUTO_KEY = 'pf_auto_added_rules'; // normalized keys marked as auto-added
  let injectionRules = loadRules();
  let presets = loadPresets();
  let autoAdded = loadAutoAdded(); // Set-like object { nk: true }
  let tempOverlayRules = {}; // normalizedKey -> value
  let useTempOverlayOnExport = false;

  function loadRules(){
    const raw = localStorage.getItem(LS_KEY);
    if(!raw) return {};
    try { const obj = JSON.parse(raw); return (obj && typeof obj==='object') ? obj : {}; } catch(e){ return {}; }
  }
  function saveRules(){
    try { localStorage.setItem(LS_KEY, JSON.stringify(injectionRules)); } catch(e){}
    renderRulesList(); renderRepeatedHints(); renderPatternMatches(); updateBulkHintBadge(); renderObservedPanel();
  }
  function loadPresets(){
    const raw = localStorage.getItem(LS_PRESETS_KEY);
    if(!raw) return {};
    try { const obj = JSON.parse(raw); return (obj && typeof obj==='object') ? obj : {}; } catch(e){ return {}; }
  }
  function savePresets(){ try { localStorage.setItem(LS_PRESETS_KEY, JSON.stringify(presets)); } catch(e){} renderPresetsList(); }

  function loadAutoAdded(){
    const raw = localStorage.getItem(LS_AUTO_KEY);
    if(!raw) return {};
    try { const obj = JSON.parse(raw); return (obj && typeof obj==='object') ? obj : {}; } catch(e){ return {}; }
  }
  function saveAutoAdded(){
    try { localStorage.setItem(LS_AUTO_KEY, JSON.stringify(autoAdded)); } catch(e){}
  }

  function resolveValueToken(valStr){
    const s = String(valStr).trim();
    if (s === '') return '';
    if (s.toLowerCase() === 'null') return null;
    if (s.toLowerCase() === 'true') return true;
    if (s.toLowerCase() === 'false') return false;
    if (/^-?\d+$/.test(s)) { try { return parseInt(s,10); } catch(e){ return s; } }
    const m = s.match(/^["'](.*)["']$/);
    return m ? m[1] : s;
  }
  function setRule(key, value){
    const k = normKey(key);
    if(!k) return;
    injectionRules[k] = resolveValueToken(value);
    saveRules();
  }
  function removeRule(key){
    const k = normKey(key);
    delete injectionRules[k];
    delete autoAdded[k]; // also unmark auto-added if removed
    saveAutoAdded();
    saveRules();
  }
  function clearRules(){
    injectionRules = {};
    autoAdded = {};
    saveAutoAdded();
    saveRules();
  }

  // Add rule and mark as auto-added (batch friendly: no save)
  function addAutoRule(nk, value){
    if(!nk) return;
    injectionRules[nk] = resolveValueToken(value);
    autoAdded[nk] = true;
  }

  function exportRulesJSON(){
    safeDownload(JSON.stringify(injectionRules, null, 2), tableId+'_injection_rules.json');
  }
  function importRulesJSON(ev){
    const file = ev.target.files[0]; if(!file) return;
    const reader = new FileReader();
    reader.onload = function(){
      try { const obj = JSON.parse(reader.result); if(obj && typeof obj==='object'){ injectionRules = obj; } } catch(e){}
      saveRules();
      ev.target.value = '';
    };
    reader.readAsText(file, 'utf-8');
  }

  function renderRulesList(){
    const box = document.getElementById('inj_rules_list');
    const search = (document.getElementById('inj_rule_search')||{value:''}).value.trim().toLowerCase();
    if(!box) return;
    const keys = Object.keys(injectionRules).sort().filter(k=>!search || k.toLowerCase().includes(search));
    const rows = keys.map(k=>{
      const v = injectionRules[k];
      const autoTag = autoAdded[k] ? '<span class="pill auto-pill" title="Added automatically">auto</span>' : '';
      return `<div style="display:grid;grid-template-columns: 1fr auto auto auto;gap:8px;margin-bottom:6px;align-items:center;">
                <span class="muted">${k}</span>
                <span>${JSON.stringify(v)}</span>
                ${autoTag}
                <button class="btn" onclick="_dash_removeRule('${k}')">Remove</button>
              </div>`;
    });
    box.innerHTML = rows.length ? rows.join('') : '<div class="muted">(no rules)</div>';
  }

  function applyRulesToObj(varsObj){
    const out = {};
    Object.keys(varsObj||{}).forEach(k=>{ out[k] = varsObj[k]; });
    Object.keys(out).forEach(origKey=>{
      const nk = normKey(origKey);
      if(nk in injectionRules){
        out[origKey] = injectionRules[nk];
      }
    });
    Object.keys(out).forEach(origKey=>{
      const nk = normKey(origKey);
      if(nk in tempOverlayRules){
        out[origKey] = tempOverlayRules[nk];
      }
    });
    return out;
  }

  // Presets
  function renderPresetsList(){ const box = document.getElementById('inj_presets_list'); if(!box) return; const names = Object.keys(presets).sort();
    box.innerHTML = names.length ? names.map(name=>(`<div style="display:flex;gap:6px;align-items:center;margin-bottom:6px;">
         <span class="muted">${name}</span>
         <button class="btn" onclick="_dash_loadPreset('${name}')">Load</button>
         <button class="btn" onclick="_dash_deletePreset('${name}')">Delete</button>
       </div>`)).join('') : '<div class="muted">(no presets)</div>';
  }
  function saveCurrentAsPreset(){ const name = (document.getElementById('inj_preset_name')||{value:''}).value.trim(); if(!name) return; presets[name] = injectionRules; savePresets(); }
  function loadPreset(name){ const p = presets[name]; if(!p || typeof p!=='object') return; injectionRules = JSON.parse(JSON.stringify(p)); saveRules(); }
  function deletePreset(name){ delete presets[name]; savePresets(); }

  // Pattern Injection
  function collectVisibleKeys(){
    const rows=getVisibleRowsOrdered();
    const keysSet = new Set();
    const byKey = {};
    rows.forEach(o=>{
      const obj = o.vObj || parseJSONSafe(o.varsjson || o.v) || {};
      Object.keys(obj||{}).forEach(k=>{
        keysSet.add(k);
        byKey[k] = (byKey[k]||0)+1;
      });
    });
    return { keys:Array.from(keysSet), freq:byKey };
  }
  function renderPatternMatches(){
    const inp = document.getElementById('pattern_search');
    const box = document.getElementById('pattern_results');
    if(!inp || !box) return;
    const q = (inp.value||'').toLowerCase().trim();
    const {keys,freq} = collectVisibleKeys();
    const filtered = q ? keys.filter(k=>k.toLowerCase().includes(q)) : [];
    filtered.sort((a,b)=> (freq[b]||0)-(freq[a]||0) || a.localeCompare(b));
    const rows = filtered.slice(0,200).map(k=>`<div style="display:flex;justify-content:space-between;gap:8px;margin-bottom:4px;"><span>${k}</span><span class="muted">x${freq[k]||1}</span></div>`);
    box.innerHTML = rows.length ? rows.join('') : '<div class="muted">(no matches)</div>';
  }
  function applyPatternPreview(){
    const q = (document.getElementById('pattern_search')||{value:''}).value.toLowerCase().trim();
    const valStr = (document.getElementById('pattern_value')||{value:''}).value;
    const val = resolveValueToken(valStr);
    tempOverlayRules = {};
    if(q){
      const {keys} = collectVisibleKeys();
      keys.forEach(k=>{
        if(k.toLowerCase().includes(q)){
          tempOverlayRules[normKey(k)] = val;
        }
      });
    }
    previewApply();
  }
  function togglePatternExport(){ const cb = document.getElementById('pattern_export_enable'); useTempOverlayOnExport = !!(cb && cb.checked); }

  function getVisibleRowsOrdered(){ return getRows().filter(tr=>tr.style.display!=='none').map(tr=>rowObj(tr)); }
  function isInjectionEnabled(){ const cb = document.getElementById('inj_enable'); return !!(cb && cb.checked); }

  function compactJSONStringFromRow(o){
    const src = o.varsjson && o.varsjson.trim() ? o.varsjson : (o.v ? o.v : "{}");
    const obj = parseJSONSafe(src);
    let finalObj = (obj && typeof obj==='object') ? obj : null;

    const overlayActiveForExport = useTempOverlayOnExport;

    if(finalObj && (isInjectionEnabled() || overlayActiveForExport)){
      const stash = tempOverlayRules;
      if(!overlayActiveForExport){ tempOverlayRules = {}; }
      finalObj = applyRulesToObj(finalObj);
      tempOverlayRules = stash;
    }

    if(finalObj){ try { return JSON.stringify(finalObj); } catch(e){} }
    return String(src).replace(/\r?\n+/g, ' ').trim();
  }

  function safeDownload(content, filename){
    const ts = new Date();
    const pad = (n)=> String(n).padStart(2,'0');
    const stamp = ts.getFullYear()+''+pad(ts.getMonth()+1)+''+pad(ts.getDate())+'_'+pad(ts.getHours())+''+pad(ts.getMinutes());
    const base = filename.replace(/[\s\(\)]+/g,'_');
    const name = base.replace(/__TABLE_ID__/g, tableId) + '_' + stamp;
    const a=document.createElement('a');
    a.href='data:text/plain;charset=utf-8,'+encodeURIComponent(content);
    a.download=name;
    a.click();
  }

  function exportVariablesPitchfork(){ const lines=getVisibleRowsOrdered().map(o=>compactJSONStringFromRow(o)); safeDownload(lines.join('\n'), '__TABLE_ID___variables_pitchfork.txt'); }
  function exportDocIdsAligned(){ const lines=getVisibleRowsOrdered().map(o=>o.docid || ''); safeDownload(lines.join('\n'), '__TABLE_ID___doc_ids_aligned.txt'); }
  function exportPitchforkPair(){
    const rows=getVisibleRowsOrdered(), seen=new Set(), vOut=[], idOut=[];
    for(const o of rows){
      const vOne=compactJSONStringFromRow(o); const idOne=o.docid || '';
      const key=vOne+'||'+idOne; if(seen.has(key)) continue; seen.add(key);
      vOut.push(vOne); idOut.push(idOne);
    }
    safeDownload(vOut.join('\n'), '__TABLE_ID___variables_pitchfork.txt');
    setTimeout(()=>safeDownload(idOut.join('\n'), '__TABLE_ID___doc_ids_aligned.txt'), 150);
  }

  function previewApply(){
    getRows().forEach(tr=>{
      if(tr.style.display==='none') return;
      const o=rowObj(tr);
      const pre = tr.querySelector('td:nth-child(3) pre');
      if(!pre) return;
      const obj = parseJSONSafe(o.varsjson || o.v) || {};
      const applied = applyRulesToObj(obj);
      try { pre.innerText = JSON.stringify(applied, null, 2); } catch(e){}
    });
  }
  function previewApplyInjection(){ previewApply(); }
  function resetPreview(){
    tempOverlayRules = {};
    useTempOverlayOnExport = false;
    const cb1 = document.getElementById('pattern_export_enable'); if(cb1) cb1.checked = false;
    getRows().forEach(tr=>{
      const o=rowObj(tr);
      const pre = tr.querySelector('td:nth-child(3) pre');
      if(!pre) return;
      const src = o.varsjson && o.varsjson.trim() ? o.varsjson : (o.v ? o.v : "{}");
      pre.innerText = src;
    });
  }

  // Repeated variables insight
  function renderRepeatedHints(){
    const box = document.getElementById('inj_repeated_hints'); if(!box) return;
    const rows = getVisibleRowsOrdered();
    const freq = {};
    rows.forEach(o=>{
      const obj = o.vObj || parseJSONSafe(o.varsjson || o.v) || {};
      Object.keys(obj||{}).forEach(k=>{
        const nk = normKey(k);
        if(!nk) return;
        freq[nk] = freq[nk] || { origSet: new Set(), count: 0 };
        freq[nk].count += 1;
        freq[nk].origSet.add(k);
      });
    });
    const entries = Object.keys(freq).map(nk=>({nk, count:freq[nk].count, covered: (nk in injectionRules), examples: Array.from(freq[nk].origSet).slice(0,5)}));
    entries.sort((a,b)=> b.count - a.count || a.nk.localeCompare(b.nk));
    const top = entries.filter(e=>e.count>1).slice(0,50);
    const rowsHtml = top.length ? top.map(e=>{
      const cls = e.covered ? 'hint-ok' : 'hint-miss';
      const status = e.covered ? 'covered' : 'missing';
      const ex = e.examples.join(', ');
      const autoTag = autoAdded[e.nk] ? ' · <span class="hint-ok" title="Auto-added">auto</span>' : '';
      return `<tr><td>${ex}</td><td>${e.count}</td><td class="${cls}">${status}${autoTag}</td><td><button class="btn" onclick="_dash_setRule('${e.nk}', (document.getElementById('inj_quick_value')||{value:''}).value || '1234')">Add rule</button></td></tr>`;
    }).join('') : '<tr><td colspan="4" class="muted">(no repeats among visible rows)</td></tr>';
    box.innerHTML = `<table class="hint-table"><thead><tr><th>Variable examples</th><th>Count</th><th>Status</th><th>Action</th></tr></thead><tbody>${rowsHtml}</tbody></table>`;
  }

  // Observed parameters bulk-hint (consistent normalization)
  function collectObservedCandidates(){
    const observed = window.__OBSERVED__ || {};
    const {keys} = collectVisibleKeys();
    const presentNKs = new Set(keys.map(k=>normKey(k))); // normalized intersection base

    const candidates = [];
    const byNkOrig = {};
    keys.forEach(k=>{
      const nk = normKey(k);
      if(!nk) return;
      (byNkOrig[nk] = byNkOrig[nk] || []).push(k);
    });

    Object.keys(observed).forEach(nk=>{
      const info = observed[nk];
      if(!info || typeof info.value === 'undefined' || info.value === null) return;
      if(presentNKs.has(nk)){
        const origs = byNkOrig[nk] || [nk];
        const displayKey = origs[0];
        const values = Array.isArray(info.values) ? info.values : [{v:info.value,c:info.count||1}];
        candidates.push({key: displayKey, nk, top: info.value, count: info.count||0, values});
      }
    });
    candidates.sort((a,b)=> (b.count - a.count) || a.key.localeCompare(b.key));
    return candidates;
  }

  // Automatically add missing observed candidates into rules (uses top observed value)
  function autoAddObservedCandidates(){
    const candidates = collectObservedCandidates();
    const missing = candidates.filter(c=>!(c.nk in injectionRules));
    if(missing.length === 0) return;
    missing.forEach(c=>{
      addAutoRule(c.nk, c.top);
    });
    saveAutoAdded();
    saveRules();
  }

  function updateBulkHintBadge(){
    const badge = document.getElementById('bulk_hint_badge');
    if(!badge) return;
    const candidates = collectObservedCandidates();
    const uncovered = candidates.filter(c=>!(c.nk in injectionRules));
    // After auto-add, uncovered should be 0; keep badge subtle, show count if any
    if(uncovered.length > 0){
      badge.style.display = 'inline-flex';
      const countEl = badge.querySelector('.count');
      if(countEl) countEl.textContent = String(uncovered.length);
    } else {
      badge.style.display = 'none';
    }
  }

  // Click still adds any remaining uncovered candidates directly to rules
  function onBulkHintClick(){
    const candidates = collectObservedCandidates().filter(c=>!(c.nk in injectionRules));
    if(candidates.length === 0) return;
    candidates.forEach(c=>addAutoRule(c.nk, c.top));
    saveAutoAdded();
    saveRules();
  }

  // Observed interactive panel
  function renderObservedPanel(){
    const box = document.getElementById('observed_panel'); if(!box) return;
    const list = collectObservedCandidates();
    if(list.length === 0){
      box.innerHTML = '<div class="muted">(no live intersections with visible output variables)</div>';
      return;
    }
    const htmlRows = list.map(item=>{
      const covered = (item.nk in injectionRules);
      const autoTag = autoAdded[item.nk] ? ' <span class="pill auto-pill" title="Added automatically">auto</span>' : '';
      const coverBadge = covered ? `<span class="hint-ok" title="In rules">covered</span>${autoTag}` : `<span class="hint-miss" title="Not in rules">missing</span>`;
      const select = `<select class="observed-select" data-nk="${item.nk}" id="obs_sel_${item.nk}">
         ${item.values.map(it=>`<option value="${it.v}">${it.v} (x${it.c})</option>`).join('')}
       </select>`;
      return `<div class="observed-row">
        <div class="observed-key">${item.key}</div>
        <div class="observed-count">seen: x${item.count} · ${coverBadge}</div>
        <div>${select}</div>
        <div class="observed-actions">
          <button class="btn" onclick="_dash_obsAdd('${item.nk}', '${item.key}')">Add</button>
          <button class="btn" onclick="_dash_obsPreview('${item.nk}')">Preview</button>
        </div>
        <div class="observed-actions">
          <button class="btn" onclick="_dash_obsUpdate('${item.nk}', '${item.key}')">Add/Update</button>
          <button class="btn" onclick="_dash_obsReset('${item.nk}')">Reset</button>
        </div>
      </div>`;
    }).join('');
    const head = `<div class="row" style="justify-content:space-between;align-items:center;margin-bottom:8px;">
      <span class="muted">Observed in live /api/graphql (intersections auto-added to rules)</span>
      <div>
        <button class="btn" onclick="_dash_obsPreviewAll()">Preview all</button>
        <button class="btn" onclick="_dash_resetPreview()">Reset preview</button>
      </div>
    </div>`;
    box.innerHTML = head + htmlRows;
  }

  // Observed panel actions
  function getSelectedValue(nk){
    const sel = document.getElementById('obs_sel_'+nk);
    if(!sel) return null;
    return sel.value;
  }
  function obsAdd(nk, displayKey){
  const v = getSelectedValue(nk);
  if(v === null) return;
  // بدلاً من إضافتها إلى textarea، نضيفها مباشرة إلى rules
  setRule(displayKey, v);
  autoAdded[normKey(displayKey)] = true;
  saveAutoAdded();
  saveRules();
  }

  function obsUpdate(nk, displayKey){
    const v = getSelectedValue(nk);
    if(v === null) return;
    setRule(displayKey, v);
  }
  function obsPreview(nk){
    const v = getSelectedValue(nk);
    if(v === null) return;
    tempOverlayRules[nk] = resolveValueToken(v);
    previewApply();
  }
  function obsReset(nk){
    delete tempOverlayRules[nk];
    previewApply();
  }
  function obsPreviewAll(){
    const list = collectObservedCandidates();
    tempOverlayRules = {};
    list.forEach(item=>{
      const v = (getSelectedValue(item.nk) ?? item.top);
      tempOverlayRules[item.nk] = resolveValueToken(v);
    });
    previewApply();
  }

  // Wire
  window._dash_applyFilters=applyFilters;
  window._dash_exportVariablesPitchfork=exportVariablesPitchfork;
  window._dash_exportDocIdsAligned=exportDocIdsAligned;
  window._dash_exportPitchforkPair=exportPitchforkPair;
  window._dash_closeDetail=closeDetail;

  window._dash_setRule=setRule;
  window._dash_removeRule=removeRule;
  window._dash_clearRules=clearRules;
  window._dash_previewApplyInjection=previewApplyInjection;
  window._dash_resetPreview=resetPreview;
  window._dash_savePreset=saveCurrentAsPreset;
  window._dash_loadPreset=loadPreset;
  window._dash_deletePreset=deletePreset;
  window._dash_exportRulesJSON=exportRulesJSON;
  window._dash_importRulesJSON=importRulesJSON;

  window._dash_renderPatternMatches=renderPatternMatches;
  window._dash_applyPatternPreview=applyPatternPreview;
  window._dash_togglePatternExport=togglePatternExport;

  window._dash_onBulkHintClick=onBulkHintClick;

  window._dash_obsAdd=obsAdd;
  window._dash_obsUpdate=obsUpdate;
  window._dash_obsPreview=obsPreview;
  window._dash_obsReset=obsReset;
  window._dash_obsPreviewAll=obsPreviewAll;

  document.addEventListener('DOMContentLoaded', function(){
    // Auto-add observed candidates on first load as well
    autoAddObservedCandidates();
    updateKPIs(); attachClicks();
    renderRulesList(); renderPresetsList(); renderRepeatedHints();
    renderPatternMatches();
    updateBulkHintBadge();
    renderObservedPanel();
  });
})();
</script>
</head>
<body>
  <div class="bg-logo" aria-hidden="true"></div>
  <div class="app-root">
<div class="banner">
  <div class="brand-left">
    <img src="__LOGO_PATH__" alt="XVISOR03 Logo" class="brand-logo-img">
    <div class="brand-text">
      <div class="brand-name">XVISOR03</div>
      <div class="brand-page">__TITLE__</div>
    </div>
  </div>
  <div class="brand-sub">__SUBTITLE__</div>
</div>

<div class="kpis">
  <div class="kpi"><div class="label">Total rows</div><div class="value" id="kpi_total">0</div></div>
  <div class="kpi"><div class="label">Visible</div><div class="value" id="kpi_visible">0</div></div>
</div>

<div class="toolbar">
  <input id="filter_docid" placeholder="Filter by doc_id..." oninput="_dash_applyFilters()">
  <input id="filter_module" placeholder="Filter by module name..." oninput="_dash_applyFilters()">
  <input id="filter_host" placeholder="Filter by host (e.g., adsmanager.facebook.com)..." oninput="_dash_applyFilters()">
  <input id="filter_text" placeholder="Full-text filter..." oninput="_dash_applyFilters()">
  <button onclick="_dash_exportVariablesPitchfork()">Export Variables (Pitchfork)</button>
  <button onclick="_dash_exportDocIdsAligned()">Export Doc IDs (Aligned)</button>
  <button onclick="_dash_exportPitchforkPair()">Export Pitchfork Pair</button>
</div>

<div class="dash-grid">
  <div class="dash-col">
    <div class="panel">
      <h4>Rules and presets</h4>
      <div class="card">
        <h5>Manage rules</h5>
        <div class="row">
          <input id="inj_key" placeholder="Variable key (e.g., actor_id, pageID)" style="min-width:220px;">
          <input id="inj_value" placeholder='Value (e.g., 1234 or "abc")' style="min-width:220px;">
          <button class="btn" onclick="_dash_setRule(document.getElementById('inj_key').value, document.getElementById('inj_value').value)">Add/Update</button>
          <button class="btn" onclick="_dash_clearRules()">Clear all</button>
          <span class="row"><input type="checkbox" id="inj_enable"><label for="inj_enable">Use injection on export</label></span>
        </div>
        <div class="row" style="margin-top:6px;">
          <input id="inj_rule_search" placeholder="Search rules..." oninput="(function(){ _dash_applyFilters(); })()">
          <button class="btn" onclick="_dash_exportRulesJSON()">Export rules JSON</button>
          <label class="btn" style="cursor:pointer;">
            Import rules JSON
            <input type="file" accept=".json,application/json" style="display:none" onchange="_dash_importRulesJSON(event)">
          </label>
        </div>
        <div id="inj_rules_list" class="card" style="margin-top:8px; max-height:180px; overflow:auto;"></div>
      </div>

      <div class="card">
        <h5>Presets</h5>
        <div class="row">
          <input id="inj_preset_name" placeholder="Preset name (e.g., Test IDs)">
          <button class="btn" onclick="_dash_savePreset()">Save current rules</button>
        </div>
        <div id="inj_presets_list" class="card" style="margin-top:8px; max-height:160px; overflow:auto;"></div>
      </div>

      <div class="card">
        <h5>Repeated variables insight</h5>
        <div class="row" style="margin-bottom:6px;">
          <span class="muted">Quick value for adding rules:</span>
          <input id="inj_quick_value" placeholder='e.g., 1234 or "foo"' style="min-width:150px;">
        </div>
        <div id="inj_repeated_hints" class="card" style="max-height:200px; overflow:auto;"></div>
      </div>
    </div>
  </div>

  <div class="dash-col">
    <div class="panel">
      <h4>Pattern and bulk injection</h4>
      <div class="card">
        <h5>Pattern injection (substring match, case-insensitive)</h5>
        <div class="row">
          <input id="pattern_search" placeholder='Type substring (e.g., "id" or "page")' oninput="_dash_renderPatternMatches()" style="min-width:220px;">
          <input id="pattern_value" placeholder='Set value for all matches (e.g., 1234 or "x")' style="min-width:220px;">
          <button class="btn" onclick="_dash_applyPatternPreview()">Apply to visible (preview)</button>
        </div>
        <div class="row" style="margin-top:6px;">
          <input type="checkbox" id="pattern_export_enable" onclick="_dash_togglePatternExport()">
          <label for="pattern_export_enable">Use pattern overlay on export (no raw change)</label>
        </div>
        <div id="pattern_results" class="card" style="margin-top:8px; max-height:160px; overflow:auto;"></div>
      </div>

      <div class="card">
        <h5>Bulk add (one per line: key=value)
          <span id="bulk_hint_badge" class="hint-badge" style="display:none;">
            <span class="dot"></span><span>hint: <span class="count">0</span> observed</span>
          </span>
        </h5>
        <textarea id="inj_bulk" style="width:100%; height:140px;" placeholder="actor_id=1234
page_id=1234
pageID=1234
pageid=1234
id=1234
entityID=1234
asset_id=1234
ids=1234
user_id=1234"></textarea>
        <div class="row" style="margin-top:6px;">
          <button class="btn" onclick="
            (function(){
              const t=document.getElementById('inj_bulk').value;
              t.split(/\r?\n/).forEach(line=>{
                const m=line.split('=');
                if(m.length>=2){
                  const key=m[0].trim();
                  const val=m.slice(1).join('=').trim();
                  _dash_setRule(key, val);
                }
              });
            })();
          ">Add lines</button>
          <button class="btn" onclick="_dash_previewApplyInjection()">Apply to visible (preview)</button>
          <button class="btn" onclick="_dash_resetPreview()">Reset preview</button>
        </div>

        <div class="observed-panel" id="observed_panel"></div>
      </div>
    </div>
  </div>
</div>

<div class="panel" style="margin-top:12px;">
  <h4>Data</h4>
  <table id="__TABLE_ID__">
    <thead>
      <tr>
        <th>#</th><th>Doc ID</th><th>Variables (JSON)</th><th>Module</th><th>Host</th>
      </tr>
    </thead>
    <tbody>
"""
    return (tpl.replace("__TITLE__", html.escape(title))
               .replace("__SUBTITLE__", html.escape(subtitle))
               .replace("__TABLE_ID__", table_id)
               .replace("__PAGE_KIND__", page_kind)
               .replace("__OBSERVED_JSON__", observed_json)
               .replace("__LOGO_PATH__", html.escape(LOGO_REL_PATH)))

def _html_footer():
    return """
    </tbody>
  </table>
</div>

<div id="detail_overlay" onclick="_dash_closeDetail()">
  <div class="detail_card" onclick="event.stopPropagation()">
    <div class="detail_header">
      <div class="pill"><span class="dot" style="background:#10b981;"></span><span class="label">Doc ID: <span id="det_docid"></span></span></div>
      <div class="pill"><span class="dot" style="background:#38bdf8;"></span><span class="label">Module: <span id="det_module"></span></span></div>
      <div class="host-pill"><span class="dot" style="background:#f59e0b;"></span><span class="label">Host: <span id="det_host"></span></span></div>
      <div class="src-pill"><span class="dot" style="background:#f59e0b;"></span><span class="label">Source: <span id="det_src"></span></span></div>
      <button class="btn" onclick="_dash_closeDetail()">Close</button>
    </div>
    <div class="detail_body">
      <div class="block">
        <h5>Variables</h5>
        <div id="det_vars" class="json-tree"></div>
      </div>
      <div class="block">
        <h5>Notes</h5>
        <div class="muted">- Collapsible JSON tree.<br>- Injection applies on export/preview only; raw data remains intact.<br>- Pattern overlays and observed bulk-hints can be previewed/reset easily.<br>- Host and source show target domain and the statics file URL containing the query.</div>
      </div>
    </div>
  </div>
</div>

</div> <!-- .app-root -->
</body>
</html>
"""

def _row_html(idx, doc_id, variables, module, host="", src=""):
    vars_str = json.dumps(variables, ensure_ascii=False, indent=2) if isinstance(variables, dict) else str(variables)
    return (
        f"<tr data-module=\"{html.escape(module)}\" data-varsjson=\"{html.escape(vars_str)}\" data-host=\"{html.escape(host or '')}\" data-src=\"{html.escape(src or '')}\">"
        f"<td>{idx}</td>"
        f"<td>{html.escape(str(doc_id))}</td>"
        f"<td><pre>{html.escape(vars_str)}</pre></td>"
        f"<td class='muted'>{html.escape(module)}</td>"
        f"<td class='muted'>{html.escape(host or '')}</td>"
        "</tr>\n"
    )

# ---------- Index (repo) ----------
def _load_repo_index():
    if os.path.exists(REPO_INDEX):
        try:
            with open(REPO_INDEX, "r", encoding="utf-8") as f:
                data = json.load(f)
                items = data.get("items", [])
                for it in items:
                    if "host" not in it: it["host"] = ""
                    if "src" not in it: it["src"] = ""
                return items
        except Exception:
            pass
    return []

def _save_repo_index(items):
    safe_items = []
    for it in items:
        safe_items.append({
            "doc_id": it.get("doc_id"),
            "variables": it.get("variables", {}),
            "module": it.get("module", ""),
            "ts": it.get("ts", ""),
            "host": it.get("host", ""),
            "src": it.get("src", "")
        })
    with open(REPO_INDEX, "w", encoding="utf-8") as f:
        json.dump({"items": safe_items}, f, ensure_ascii=False, indent=2)

def _render_html(items, path, page_kind):
    title = "graphql_harvester - Repository" if page_kind == "repo" else "graphql_harvester - Session"
    table_kind = "repo" if page_kind == "repo" else "session"
    with open(path, "w", encoding="utf-8") as f:
        f.write(_html_header(title, "#e02424", subtitle="By Hasan Habeeb", page_kind=table_kind))
        for i, it in enumerate(items, start=1):
            f.write(_row_html(i, it["doc_id"], it["variables"], it.get("module", ""), it.get("host", ""), it.get("src", "")))
        f.write(_html_footer())

# ---------- Parsing utilities (strict) ----------
MODULE_BLOCK_RE = re.compile(
    r'__d\(\s*"([^"]+)"\s*,.*?\(function\([^\)]*\)\s*\{\s*(.*?)\s*\}\s*\)\s*,.*?\)\s*;',
    re.S
)
DOCID_EXPORT_RE = re.compile(r'e\.exports\s*=\s*"(\d+)"')

LOCAL_ARG_BLOCK_RE = re.compile(r'\{[^{}]*kind\s*:\s*"LocalArgument"[^{}]*\}', re.S)
NAME_IN_BLOCK_RE    = re.compile(r'name\s*:\s*"([^"]+)"')
DEFAULT_IN_BLOCK_RE = re.compile(r'defaultValue\s*:\s*([^,\}]+)')
VARIABLE_NAME_RE    = re.compile(r'variableName\s*:\s*"([^"]+)"')

ENTRYPOINT_PAIR_RE = re.compile(
    r'parameters\s*:\s*\w\(\s*"([^"]+)"\s*\)\s*,[\s\S]*?variables\s*:\s*\{(.*?)\}',
    re.S
)
VAR_KEY_RE = re.compile(r'([A-Za-z_][A-Za-z0-9_]*)\s*:')

def _extract_modules(text):
    modules = {}
    for m in MODULE_BLOCK_RE.finditer(text):
        name, body = m.groups()
        modules[name] = body
    return modules

def _base_name_from_operation(module_name):
    if module_name.endswith("_facebookRelayOperation"):
        return module_name[:-len("_facebookRelayOperation")]
    return None

def _normalize_default_token(token: str):
    if token is None:
        return None
    s = token.strip()
    if s == "!0": return False
    if s == "!1": return True
    if s.lower() == "null": return None
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    if re.search(r'WebPixelRatio\.get\(\)', s):
        return 1
    if re.fullmatch(r'-?\d+', s):
        try: return int(s)
        except: return s
    if s == "true": return True
    if s == "false": return False
    return None

def _collect_variables_from_graphql(graphql_body):
    names = set(VARIABLE_NAME_RE.findall(graphql_body))
    defaults_map = {}
    for block in LOCAL_ARG_BLOCK_RE.findall(graphql_body):
        nm = None
        dv = None
        m_name = NAME_IN_BLOCK_RE.search(block)
        if m_name:
            nm = m_name.group(1)
            names.add(nm)
        m_def = DEFAULT_IN_BLOCK_RE.search(block)
        if m_def:
            dv = _normalize_default_token(m_def.group(1))
        if nm:
            defaults_map[nm] = dv
    variables = {}
    for n in sorted(names):
        variables[n] = defaults_map.get(n, None)
    return variables

def _infer_default_for_key_from_varblock(var_key: str, var_block: str):
    m = re.search(rf'{re.escape(var_key)}\s*:\s*(.+?)(?:,|\n|\}})', var_block, re.S)
    if not m:
        return None
    token = m.group(1).strip()
    m_tern = re.search(r'\?\s*[^:]+:\s*(.+)$', token)
    if m_tern:
      dv = _normalize_default_token(m_tern.group(1))
      if dv is not None:
          return dv
    dv = _normalize_default_token(token)
    return dv

def _collect_variables_from_entrypoint(entry_body: str, base_name: str):
    variables = {}
    for params_name, var_block in ENTRYPOINT_PAIR_RE.findall(entry_body):
        if params_name != f"{base_name}$Parameters":
            continue
        keys = VAR_KEY_RE.findall(var_block)
        for k in keys:
            if k not in variables:
                variables[k] = _infer_default_for_key_from_varblock(k, var_block)
        break
    return variables

def _collect_variables_from_parameters_blocks(full_text: str, base_name: str):
    variables = {}
    for params_name, var_block in ENTRYPOINT_PAIR_RE.findall(full_text):
        if params_name != f"{base_name}$Parameters":
            continue
        keys = VAR_KEY_RE.findall(var_block)
        for k in keys:
            if k not in variables:
                variables[k] = _infer_default_for_key_from_varblock(k, var_block)
        break
    return variables

def _merge_vars(existing: dict, newvars: dict):
    if not isinstance(existing, dict) or not existing:
        return dict(newvars) if isinstance(newvars, dict) else {}
    if not isinstance(newvars, dict) or not newvars:
        return existing
    merged = dict(existing)
    for k, v in newvars.items():
        if k not in merged or merged[k] is None:
            merged[k] = v
    return merged

# ---------- Upsert helpers ----------
def _upsert_repo(docid, variables, module, ts, host="", src=""):
    for it in repo_items:
        if it.get("doc_id") == docid:
            it["variables"] = _merge_vars(it.get("variables", {}), variables)
            it["module"] = module or it.get("module", "")
            it["ts"] = ts or it.get("ts", "")
            if host and not it.get("host"): it["host"] = host
            if src and not it.get("src"): it["src"] = src
            return False
    repo_items.append({"doc_id": docid, "variables": variables, "module": module, "ts": ts, "host": host or "", "src": src or ""})
    repo_seen_docids.add(docid)
    return True

def _upsert_session(docid, variables, module, ts, host="", src=""):
    for it in session_items:
        if it.get("doc_id") == docid:
            it["variables"] = _merge_vars(it.get("variables", {}), variables)
            it["module"] = module or it.get("module", "")
            it["ts"] = ts or it.get("ts", "")
            if host and not it.get("host"): it["host"] = host
            if src and not it.get("src"): it["src"] = src
            return False
    if docid not in session_seen_docids:
        session_seen_docids.add(docid)
        session_items.append({"doc_id": docid, "variables": variables, "module": module, "ts": ts, "host": host or "", "src": src or ""})
        return True
    return False

# ---------- Harvest (multi-file support) ----------
def _harvest_from_text(txt: str):
    modules = _extract_modules(txt)
    if not modules:
        return {}

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    local_doc_by_base = {}
    for name, body in modules.items():
        base = _base_name_from_operation(name)
        if not base: continue
        m_doc = DOCID_EXPORT_RE.search(body)
        if not m_doc: continue
        docid = m_doc.group(1)
        local_doc_by_base[base] = docid
        CACHE_DOC_BY_BASE[base] = docid
        CACHE_MODULE_BY_BASE[base] = base

    for name, body in modules.items():
        if name.endswith(".graphql"):
            base = name[:-len(".graphql")]
            vars_graphql = _collect_variables_from_graphql(body)
            CACHE_VARS_BY_BASE[base] = _merge_vars(CACHE_VARS_BY_BASE.get(base, {}), vars_graphql)
            CACHE_MODULE_BY_BASE[base] = base

    for name, body in modules.items():
        if name.endswith(".entrypoint"):
            for params_name, var_block in ENTRYPOINT_PAIR_RE.findall(body):
                if params_name.endswith("$Parameters"):
                    base = params_name[:-len("$Parameters")]
                    variables = {}
                    keys = VAR_KEY_RE.findall(var_block)
                    for k in keys:
                        variables[k] = _infer_default_for_key_from_varblock(k, var_block)
                    CACHE_VARS_BY_BASE[base] = _merge_vars(CACHE_VARS_BY_BASE.get(base, {}), variables)
                    CACHE_MODULE_BY_BASE[base] = base

    for params_name, var_block in ENTRYPOINT_PAIR_RE.findall(txt):
        if params_name.endswith("$Parameters"):
            base = params_name[:-len("$Parameters")]
            variables = {}
            keys = VAR_KEY_RE.findall(var_block)
            for k in keys:
                variables[k] = _infer_default_for_key_from_varblock(k, var_block)
            CACHE_VARS_BY_BASE[base] = _merge_vars(CACHE_VARS_BY_BASE.get(base, {}), variables)
            CACHE_MODULE_BY_BASE[base] = base

    pairs = {}
    candidate_bases = set(local_doc_by_base.keys()) | set(CACHE_DOC_BY_BASE.keys())
    for base in sorted(candidate_bases):
        docid = local_doc_by_base.get(base) or CACHE_DOC_BY_BASE.get(base)
        if not docid: continue

        variables = {}
        graphql_name = f"{base}.graphql"
        if graphql_name in modules:
            variables = _collect_variables_from_graphql(modules[graphql_name])
        else:
            newname = base[:-5] if base.endswith("Query") else base
            entry_name = f"{newname}.entrypoint"
            entry_body = modules.get(entry_name)
            variables = _collect_variables_from_entrypoint(entry_body, base) if entry_body else {}

        if not variables:
            variables = _collect_variables_from_parameters_blocks(txt, base)

        if (not variables) and (base in CACHE_VARS_BY_BASE):
            variables = CACHE_VARS_BY_BASE.get(base, {})

        if variables:
            CACHE_VARS_BY_BASE[base] = _merge_vars(CACHE_VARS_BY_BASE.get(base, {}), variables)

        pairs[docid] = {
            "doc_id": docid,
            "variables": variables if isinstance(variables, dict) else {},
            "module": CACHE_MODULE_BY_BASE.get(base, base),
            "ts": ts
        }

    return pairs

# ---------- mitmproxy hooks ----------
def load(_l):
    global repo_items, repo_seen_docids
    repo_items = _load_repo_index()
    repo_seen_docids = set(it["doc_id"] for it in repo_items if "doc_id" in it)
    _render_html([], SESSION_HTML, page_kind="session")
    _render_html(repo_items, REPO_HTML, page_kind="repo")

def response(flow: http.HTTPFlow):
    try:
        ct = flow.response.headers.get("Content-Type", "").lower()
        url = flow.request.pretty_url
        url_lc = url.lower()
        is_js = (".js" in url_lc) or ("javascript" in ct)
        if not is_js:
            return

        body = flow.response.get_text() or ""
        if not body or ("__d(" not in body):
            return

        pairs = _harvest_from_text(body)
        if not pairs:
            return

        host = (flow.request.host or "").strip().lower()
        src = url.strip()

        updated_session = False
        updated_repo = False

        for docid, rec in pairs.items():
            new_repo = _upsert_repo(docid, rec["variables"], rec["module"], rec["ts"], host, src)
            updated_repo = updated_repo or new_repo

            new_sess = _upsert_session(docid, rec["variables"], rec["module"], rec["ts"], host, src)
            updated_session = updated_session or new_sess

        if updated_repo:
            _save_repo_index(repo_items)
            _render_html(repo_items, REPO_HTML, page_kind="repo")
        if updated_session:
            _render_html(session_items, SESSION_HTML, page_kind="session")

    except Exception:
        return

def _parse_graphql_variables_from_body(req_text: str):
    """
    Robust extractor:
    - JSON dict: {"variables": {...}} or variables as JSON string.
    - JSON array: [{"variables": {...}}, ...]
    - form-urlencoded: variables=... (JSON string)
    """
    if not req_text:
        return []

    # Try JSON first
    try:
        obj = json.loads(req_text)
        if isinstance(obj, dict):
            vars_field = obj.get("variables")
            if isinstance(vars_field, dict):
                return [vars_field]
            if isinstance(vars_field, str):
                try:
                    parsed = json.loads(vars_field)
                    if isinstance(parsed, dict):
                        return [parsed]
                except Exception:
                    pass
            return []
        if isinstance(obj, list):
            out = []
            for item in obj:
                if isinstance(item, dict):
                    v = item.get("variables")
                    if isinstance(v, dict):
                        out.append(v)
                    elif isinstance(v, str):
                        try:
                            pv = json.loads(v)
                            if isinstance(pv, dict):
                                out.append(pv)
                        except Exception:
                            pass
            return out
    except Exception:
        pass

    # Fallback: form-urlencoded
    try:
        qs = parse_qs(req_text, keep_blank_values=True)
        vars_list = qs.get("variables") or qs.get("Variables") or []
        out = []
        for v in vars_list:
            try:
                parsed = json.loads(v)
                if isinstance(parsed, dict):
                    out.append(parsed)
            except Exception:
                continue
        if out:
            return out
    except Exception:
        pass

    return []

def request(flow: http.HTTPFlow):
  
    try:
        url = (flow.request.pretty_url or "")
        url_lc = url.lower()
        if "/api/graphql" not in url_lc:
            return

        # Extract variables from GET query if present
        try:
            parsed_url = urlparse(url)
            q = parse_qs(parsed_url.query, keep_blank_values=True)
            vars_q = q.get("variables") or q.get("Variables") or []
            for vstr in vars_q:
                try:
                    pobj = json.loads(vstr)
                    if isinstance(pobj, dict):
                        _observed_add_from_dict(pobj)
                except Exception:
                    pass
        except Exception:
            pass

        # Extract variables from body (supports multiple encodings)
        req_text = flow.request.get_text() or ""
        vars_sets = _parse_graphql_variables_from_body(req_text)
        for vars_obj in vars_sets:
            _observed_add_from_dict(vars_obj)

        # Re-render both pages so __OBSERVED__ refreshes everywhere
        _render_html(session_items, SESSION_HTML, page_kind="session")
        _render_html(repo_items, REPO_HTML, page_kind="repo")

    except Exception:
        return

def done():
    pass
