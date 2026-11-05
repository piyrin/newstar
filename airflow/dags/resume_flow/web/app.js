'use strict';
const suppliedToken = new URLSearchParams(location.hash.slice(1)).get('token');
if (suppliedToken) sessionStorage.setItem('resume-review-token', suppliedToken);
const token = suppliedToken || sessionStorage.getItem('resume-review-token');
history.replaceState(null, '', location.pathname);
let state;
const $ = id => document.getElementById(id);
function el(tag, text) { const e = document.createElement(tag); e.textContent = text; return e; }
async function api(path, body) {
  const response = await fetch(path, {method:body?'POST':'GET', headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'}, ...(body?{body:JSON.stringify(body)}:{})});
  const result = await response.json(); if (!response.ok) {const error=Error(result.error);error.state=result.state;throw error;} return result;
}
function selected() { return document.querySelector('input[name=template]:checked')?.value; }
function preview() {
  try {
    const data = JSON.parse($('resume').value), paper = $('preview');
    paper.replaceChildren(); paper.className = 'paper '+(selected()||'classic');
    paper.append(el('h3', data.name||'待补充姓名'), el('p',data.headline||''));
    for (const c of data.contact||[]) paper.append(el('p',(c.label||'')+' '+(c.value||'')));
    for (const section of data.sections||[]) {
      paper.append(el('h4',section.title));
      for (const item of section.items||[]) {
        if(item.title) paper.append(el('b',item.title));
        for(const p of item.paragraphs||[]) paper.append(el('p',p));
      }
    }
  } catch { $('preview').replaceChildren(el('p','正文 JSON 尚未完整，请继续编辑。')); }
}
function render() {
  $('case').textContent = state.run_key;
  $('sample').hidden = !state.synthetic;
  $('resume').value = JSON.stringify(state.resume,null,2);
  $('count').textContent = `(${state.questions.length})`;
  $('facts').replaceChildren();
  for(const fact of state.facts) {
    const row=el('div','');row.className='fact';
    row.append(el('b',`${fact.id} · ${fact.field}`),el('p',fact.value),el('small',`${fact.source} / ${fact.location} · ${fact.status}`),el('small','原文：'+fact.quote));$('facts').append(row);
  }
  $('questions').replaceChildren();
  if(!state.questions.length) $('questions').append(el('p','没有自动发现的缺失项，仍请核对事实与正文。'));
  state.questions.forEach((q,i)=>{
    const row=el('div','');row.className='question';row.append(el('p',q.text));
    const label=el('label','处理方式 '),select=el('select','');select.id='q-'+i;
    for(const [v,t] of [['','待处理'],['confirmed','已核实 / 已补充'],['omitted','明确省略']]) {const o=el('option',t);o.value=v;select.append(o);}
    select.value=q.resolution;label.append(select);row.append(label);
    const note=el('input','');note.id='note-'+i;note.value=q.note;note.placeholder='填写补充依据或省略原因';note.setAttribute('aria-label',q.text+'的处理依据');row.append(note);$('questions').append(row);
  });
  document.querySelectorAll('input[name=template]').forEach(e=>e.checked=e.value===state.selection?.template_id);
  $('mode').value=state.selection?.mode||'print';$('paper').value=state.selection?.paper||'A4';preview();
}
async function submit(approve) {
  $('status').className='';
  document.querySelectorAll('button').forEach(b=>b.disabled=true);
  try {
    if(!selected()) throw Error('请先选择一种模板。');
    const payload={...state,resume:JSON.parse($('resume').value),selection:{schema_version:1,template_id:selected(),mode:$('mode').value,paper:$('paper').value},questions:state.questions.map((q,i)=>({...q,resolution:$('q-'+i).value,note:$('note-'+i).value}))};
    const result=await api(approve?'/api/approve':'/api/save',payload);state=result.state;render();
    $('status').textContent=approve?'已确认，可以触发导出工作流。修改正文或模板后需要重新确认。':'修改已保存，尚未批准导出。';
  } catch(error) {if(error.state){state=error.state;render();}$('status').className='error';$('status').textContent=error.message;}
  finally {document.querySelectorAll('button').forEach(b=>b.disabled=false);}
}
$('resume').addEventListener('input',preview);document.querySelectorAll('input[name=template]').forEach(e=>e.addEventListener('change',preview));
$('save').addEventListener('click',()=>submit(false));$('approve').addEventListener('click',()=>submit(true));
api('/api/state').then(data=>{state=data;render();}).catch(error=>{$('status').className='error';$('status').textContent=error.message+'。请重新使用终端中的完整链接打开。';});
