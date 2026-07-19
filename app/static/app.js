let activePR;
const $ = s => document.querySelector(s);
function render(report) {
 $('#empty').hidden=true; $('#results').hidden=false; $('#score').textContent=report.risk_score; $('#verdict').textContent=report.verdict; $('#prtitle').textContent=`${report.repo} · ${report.title}`;
 $('#findings').innerHTML=report.findings.length ? report.findings.map(f=>`<article class="finding ${f.severity}"><div><span class="badge">${f.severity}</span><code>${f.path}:${f.line}</code></div><h3>${f.title}</h3><p>${f.explanation}</p><details><summary>Show proof & suggested fix</summary><ul>${f.evidence.map(e=>`<li>${e}</li>`).join('')}</ul><pre>${f.suggestion}</pre></details></article>`).join('') : '<p class="none">No verified risks were found. This does not prove the code is safe; it means the current verifier found no evidence-backed issue.</p>';
 $('#trace').innerHTML=report.trace.map(t=>`<li><b>${t.stage}</b><span>${t.detail}</span></li>`).join('');
}
function failure(message) { $('#error').hidden=false; $('#error').textContent=message; }
function modelEnabled() { return $('#use-model').checked; }
async function run() {
 activePR=await (await fetch('/api/demo')).json();
 const report=await (await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(activePR)})).json();
 render(report);
}
$('#run').onclick=run;
$('#custom-toggle').onclick=()=>{const panel=$('#custom'); panel.hidden=!panel.hidden; if(!panel.hidden) panel.scrollIntoView({behavior:'smooth'});};
$('#files').onchange=e=>{const files=[...e.target.files]; $('#selection').textContent=files.length?files.map(f=>f.name).join(', '):'No files selected'; $('#analyze').disabled=!files.length;};
$('#analyze').onclick=async()=>{const files=[...$('#files').files]; if(!files.length)return; $('#error').hidden=true; const reviews=await Promise.all(files.map(async file=>{const content=await file.text(); const patch=`@@ -0,0 +1,${content.split('\n').length} @@\n`+content.split('\n').map(line=>`+${line}`).join('\n'); return {path:file.name,patch};})); activePR={title:`Uploaded review: ${files.map(f=>f.name).join(', ')}`,repo:'local/upload',base_sha:'upload-base',head_sha:'upload-head',files:reviews,use_model:modelEnabled()}; const response=await fetch('/api/review',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(activePR)}); render(await response.json());};
$('#github-review').onclick=async()=>{const repo=$('#repo').value.trim(), pr_number=Number($('#pr-number').value); if(!repo||!pr_number){failure('Enter both a repository and pull-request number.');return;} $('#error').hidden=true; const response=await fetch('/api/github-pr',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({repo,pr_number,use_model:modelEnabled()})}); const data=await response.json(); if(!response.ok){failure(data.detail||'Could not review this pull request.');return;} activePR={repo,head_sha:'github-head',files:[],use_model:modelEnabled()}; render(data);};
$('#export').onclick=async()=>{if(!activePR)return;const data=await(await fetch('/api/github-payload',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(activePR)})).json();$('#payload').hidden=false;$('#payload').textContent=JSON.stringify(data,null,2)};
