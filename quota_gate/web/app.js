"use strict";
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="gate-token"]').content;
let draft, current, savedRevision, dirty = false, toastTimer;
const reasons = {
  below_threshold: "至少一個視窗低於設定門檻；參與專案可使用 envfacts。",
  quota_sufficient: "兩個視窗都未低於各自門檻，目前不轉交 TokenEconomizer hook。",
  disabled_by_settings: "額度控制已關閉，所有專案都不轉交 TokenEconomizer hook。",
  project_excluded: "這個專案位於排除範圍內，不會參與 TokenEconomizer。",
  project_unknown: "無法確認專案路徑；有排除清單時先停用。",
  stale_snapshot: "額度快照已過期，先停用並等待重新讀取。",
  missing_5h_or_weekly: "缺少 5 小時或 Weekly 視窗，先停用。",
  reset_requires_refresh: "快照的額度重設時間已過，需重新讀取。",
  invalid_snapshot: "尚無有效額度快照，先維持停用。"
};
function describe(reason) { return reasons[reason] || "額度資料無法確認，先維持停用。"; }
function toast(text, error = false) {
  clearTimeout(toastTimer); $('toast').textContent = text; $('toast').className = `toast${error ? ' error' : ''}`;
  $('toast').hidden = false; toastTimer = setTimeout(() => { $('toast').hidden = true; }, 5000);
}
async function request(path, body) {
  const options = { headers: { 'X-Gate-Token': token } };
  if (body !== undefined) Object.assign(options, {method:'POST', headers:{...options.headers,'Content-Type':'application/json'},body:JSON.stringify(body)});
  const response = await fetch(path, options); const result = await response.json();
  if (!response.ok) throw new Error(result.error || '無法完成操作');
  return result;
}
function thresholds() {
  for (const [id, key] of [['5h','threshold_5h'],['weekly','threshold_weekly']]) {
    const raw = $(`threshold-${id}`).value;
    if (raw === '' || !Number.isFinite(Number(raw)) || Number(raw) < 0 || Number(raw) > 100) throw new Error('門檻請填入 0 到 100 的數字。');
    draft[key] = Number(raw);
  }
  draft.enabled = $('enabled').checked;
}
function dirtyNow() { dirty = true; $('save-status').textContent = '有尚未儲存的變更'; }
function renderProjects() {
  const list = $('project-list'); list.replaceChildren();
  $('project-count').textContent = `${draft.projects.length} 個已登錄`;
  if (!draft.projects.length) { const p=document.createElement('div');p.className='empty';p.textContent='尚未登錄專案。可加入需要排除的專案，或登錄常用專案。';list.append(p);return; }
  draft.projects.forEach((project,index)=>{
    const row=document.createElement('div'); row.className='project-row';
    const icon=document.createElement('span');icon.className='folder-icon';icon.textContent='▱';
    const info=document.createElement('div');info.className='project-info';
    const name=document.createElement('strong');name.textContent=project.name;
    const path=document.createElement('code');path.textContent=project.path;info.append(name,path);
    const status=document.createElement('span');status.className=`participation${project.excluded?' excluded':''}`;status.textContent=project.excluded?'不參與':'參與中';
    const toggle=document.createElement('label');toggle.className='switch';
    const check=document.createElement('input');check.type='checkbox';check.checked=!project.excluded;check.setAttribute('aria-label',`${project.name} 參與 TokenEconomizer`);
    const track=document.createElement('span');toggle.append(check,track);
    check.addEventListener('change',()=>{project.excluded=!check.checked;dirtyNow();renderProjects();$('preview-result').textContent='專案設定已變更，請重新試算。';});
    const remove=document.createElement('button');remove.type='button';remove.className='remove';remove.textContent='×';remove.setAttribute('aria-label',`移除 ${project.name}`);
    remove.addEventListener('click',()=>{draft.projects.splice(index,1);dirtyNow();renderProjects();toast('已從清單移除；儲存後此路徑會回到預設參與狀態。');});
    row.append(icon,info,status,toggle,remove);list.append(row);
  });
}
function renderQuota() {
  const quota=current.quota;
  for (const [id,key,tkey] of [['5h','remaining_5h','threshold_5h'],['weekly','remaining_weekly','threshold_weekly']]) {
    const value=quota[key];
    $(`remaining-${id}`).textContent=value === null ? '—' : Number(value.toFixed(1));
    $(`bar-${id}`).style.width=`${value === null ? 0 : value}%`;
    $(`marker-${id}`).style.left=`${draft[tkey]}%`;
    $(`caption-${id}`).textContent=value === null ? '資料待確認' : current.demo ? '模擬資料' : '本機快照';
  }
  const valid=quota.remaining_5h !== null && quota.remaining_weekly !== null;
  const active=draft.enabled && valid && (quota.remaining_5h<draft.threshold_5h || quota.remaining_weekly<draft.threshold_weekly);
  const reason=!draft.enabled?'disabled_by_settings':!valid?quota.reason:active?'below_threshold':'quota_sufficient';
  $('gate-title').textContent=active?'目前符合額度啟用條件':'目前不啟用 TokenEconomizer';
  $('gate-reason').textContent=describe(reason);
  $('status-icon').textContent=active?'✓':'○';$('status-icon').className=`status-icon${active?' on':''}`;
}
function setInitial(data) {
  current=data;draft=structuredClone(data.settings);savedRevision=data.revision;dirty=false;
  $('threshold-5h').value=$('slider-5h').value=draft.threshold_5h;
  $('threshold-weekly').value=$('slider-weekly').value=draft.threshold_weekly;
  $('enabled').checked=draft.enabled;
  $('mode').textContent=data.demo?'模擬模式 · DEMO':'本機設定 · 未驗證整合';
  $('notice-title').textContent=data.demo?'你正在使用模擬額度':'本機設定介面';
  $('notice-body').textContent=data.demo?'可切換情境測試規則；不讀帳號、不呼叫模型、不接入 Codex。':'讀取指定快照，不會自行安裝插件或連接帳號。';
  $('demo-controls').hidden=!data.demo;
  if(data.demo) $('scenario').value=data.scenario;
  $('settings-path').textContent=`設定：${data.settingsPath}`;$('snapshot-path').textContent=`額度：${data.snapshotPath}`;
  $('save-status').textContent='所有變更已儲存';renderProjects();renderQuota();
}
for (const id of ['5h','weekly']) {
  $(`slider-${id}`).addEventListener('input',()=>{$(`threshold-${id}`).value=$(`slider-${id}`).value;thresholds();dirtyNow();renderQuota();});
  $(`threshold-${id}`).addEventListener('input',()=>{dirtyNow();try{thresholds();$(`slider-${id}`).value=$(`threshold-${id}`).value;renderQuota();}catch{ $('save-status').textContent='請輸入 0–100 的門檻'; }});
}
$('enabled').addEventListener('change',()=>{draft.enabled=$('enabled').checked;dirtyNow();renderQuota();});
$('save').addEventListener('click',async()=>{try{thresholds();$('save').disabled=true;const result=await request('/api/settings',{settings:draft,revision:savedRevision});setInitial(result);toast('設定已儲存，下一次 hook 會讀取新規則。');}catch(e){toast(e.message,true);}finally{$('save').disabled=false;}});
$('add-project').addEventListener('submit',event=>{event.preventDefault();const name=$('project-name').value.trim(),path=$('project-path').value.trim();if(!name||(!path.startsWith('/')&&!path.startsWith('~/'))){toast('請填寫名稱與絕對路徑。',true);return;}if(draft.projects.some(p=>p.path===path)){toast('這個路徑已經在清單中。',true);return;}draft.projects.push({name,path,excluded:true});$('add-project').reset();dirtyNow();renderProjects();toast('已加入，預設不參與。請儲存設定。');});
$('preview-form').addEventListener('submit',async event=>{event.preventDefault();try{thresholds();const result=await request('/api/preview',{cwd:$('preview-path').value.trim(),settings:draft});$('preview-result').textContent=describe(result.decision.reason);$('preview-result').className=result.decision.reason==='project_excluded'?'blocked':result.decision.active?'eligible':'';}catch(e){toast(e.message,true);}});
$('scenario').addEventListener('change',async()=>{try{const data=await request('/api/scenario',{scenario:$('scenario').value});current=data;renderQuota();$('preview-result').textContent='模擬額度已更新，可重新試算專案。';}catch(e){toast(e.message,true);}});
$('reload').addEventListener('click',async()=>{if(dirty&&!confirm('重新載入將捨棄尚未儲存的變更，繼續嗎？'))return;try{setInitial(await request('/api/state'));toast('已重新載入設定。');}catch(e){toast(e.message,true);}});
window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
request('/api/state').then(setInitial).catch(e=>{toast(e.message,true);$('save').disabled=true;});
setInterval(async()=>{try{const data=await request('/api/state');current=data;if(!dirty)setInitial(data);else renderQuota();}catch{ $('gate-title').textContent='本機服務連線中斷';$('gate-reason').textContent='請確認 GUI 程式仍在執行。';}},10000);
