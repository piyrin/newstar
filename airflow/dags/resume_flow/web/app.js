'use strict';
const suppliedToken = new URLSearchParams(location.hash.slice(1)).get('token');
if (suppliedToken) sessionStorage.setItem('resume-review-token', suppliedToken);
let token = suppliedToken || sessionStorage.getItem('resume-review-token');
const reviewKey = new URLSearchParams(location.search).get('run_key');
const dagRunId = new URLSearchParams(location.search).get('dag_run_id');
history.replaceState(null, '', location.pathname + location.search);
let state, lastExport = '', latestExportKey = '', exportFailed = false, pollBusy = false;
const imageUrls = [];
let questionGroups = [], photoUrl = '', photoRequest = 0;
const $ = id => document.getElementById(id);
function el(tag, text) { const e = document.createElement(tag); e.textContent = text; return e; }
async function api(path, body) {
  path = reviewPath(path);
  const response = await fetch(path, {method:body?'POST':'GET', headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'}, ...(body?{body:JSON.stringify(body)}:{})});
  const result = await response.json(); if (!response.ok) {const error=Error(result.error);error.state=result.state;throw error;} return result;
}
function reviewPath(path) {
  const url = new URL(path, location.origin);
  if (reviewKey) url.searchParams.set('run_key', reviewKey);
  if (dagRunId) url.searchParams.set('dag_run_id', dagRunId);
  return url.pathname + url.search;
}
function selected() { return document.querySelector('input[name=template]:checked')?.value; }
function preview() {
  try {
    const data = JSON.parse($('resume').value), paper = $('preview');
    paper.replaceChildren(); paper.className = 'paper '+(selected()||'classic');
    const header=el('div',''),identity=el('div',''),contact=el('div',''),body=el('div','');
    header.className='resume-header';identity.className='resume-identity';contact.className='resume-contact';body.className='resume-body';
    identity.append(el('h3', data.name||'待补充姓名'));
    if(data.headline){const p=el('p',data.headline);p.className='headline';identity.append(p);}
    for (const c of data.contact||[]) {const p=el('p',(c.label||'')+' '+(c.value||''));p.className='contact';contact.append(p);}
    for(const value of data.availability||[]){if(value){const p=el('p',value);p.className='contact';contact.append(p);}}
    if(photoUrl){const image=el('img','');image.src=photoUrl;image.alt='简历照片';image.className='resume-photo';header.append(image);header.classList.add('has-photo');}
    header.append(identity,contact);
    if(!contact.childElementCount)header.classList.add('no-contact');
    paper.append(header,body);
    for (const section of data.sections||[]) {
      if(!section.items?.length)continue;
      const block=el('section',''),content=el('div','');block.className='resume-section';content.className='section-content';
      const skills=/技能|skill/i.test(section.title||''),bullets=skills||/项目|project/i.test(section.title||'');
      if(skills)block.classList.add('skills-section');
      block.append(el('h4',section.title),content);body.append(block);
      for (const item of section.items||[]) {
        const entry=el('div',''),heading=el('div','');entry.className='resume-entry';heading.className='entry-heading';
        if(skills&&!['subtitle','date','url'].some(key=>item[key])&&!item.highlights?.length) {
          const line=el('p','');line.className='compact-skills';
          if(item.title)line.append(el('b',item.title+'  '));
          line.append(document.createTextNode((item.paragraphs||[]).join(' / ')));
          entry.append(line);content.append(entry);continue;
        }
        if(item.title)heading.append(el('b',item.title));
        if(item.subtitle){const subtitle=el('span',item.subtitle);subtitle.className='entry-subtitle';heading.append(subtitle);}
        if(item.date){const date=el('span',item.date);date.className='entry-date';heading.append(date);}
        if(heading.childElementCount)entry.append(heading);
        if(item.url){const url=el('p',item.url);url.className='entry-url';entry.append(url);}
        const text=el('div','');text.className='entry-text';entry.append(text);
        for(const value of item.paragraphs||[]){const p=el('p',value);if(bullets)p.className='bullet';text.append(p);}
        for(const value of item.highlights||[]){const p=el('p',typeof value==='string'?value:(value.label?value.label+'：':'')+(value.text||''));p.className='bullet';text.append(p);}
        content.append(entry);
      }
    }
  } catch { $('preview').replaceChildren(el('p','正文 JSON 尚未完整，请继续编辑。')); }
}
function isContactQuestion(q) {
  return !(q.fact_ids||[]).length && (q.text||'').startsWith('缺少联系方式');
}
function contactKind(label) {
  const value=(label||'').toLowerCase();
  if(['邮箱','电子邮箱','email','e-mail'].includes(value))return 'email';
  if(['电话','手机','联系电话','手机号','phone','mobile'].includes(value))return 'phone';
  if(['主页','个人主页','github','网站','website','homepage'].includes(value))return 'website';
  if(['意向','意向城市','所在地','location','城市'].includes(value))return 'location';
  return '';
}
function contactValue(data, kind) {
  return (data.contact||[]).find(item=>contactKind(item.label)===kind)?.value||'';
}
function fillBasicFields(data) {
  $('basic-name').value=data.name||'';
  $('basic-headline').value=data.headline||'';
  $('basic-email').value=contactValue(data,'email');
  $('basic-phone').value=contactValue(data,'phone');
  $('basic-website').value=contactValue(data,'website');
  $('basic-location').value=contactValue(data,'location');
  $('basic-availability').value=(data.availability||[]).join('\n');
  const education=(data.sections||[]).find(section=>/教育|education/i.test(section.title));
  const item=education?.items.find(item=>item.education_fields)||education?.items[0];
  const values=item?.education_fields||state.form_fields?.education||{};
  for(const key of educationKeys)$('edu-'+key).value=values[key]||'';
}
const educationKeys=['school','college','major','degree','start','end','gpa','courses'];
function manualInputs() {
  const values=Object.fromEntries(['name','email','phone','headline','website','location','availability'].map(key=>[key,$('basic-'+key).value.trim()]));
  values.education=Object.fromEntries(educationKeys.map(key=>[key,$('edu-'+key).value.trim()]));
  return values;
}
function syncBasicFields() {
  const data=JSON.parse($('resume').value), values=manualInputs();
  data.name=values.name;data.headline=values.headline;
  for(const kind of ['email','phone','website','location']) {
    const contact=(data.contact||[]), match=contact.find(item=>contactKind(item.label)===kind);
    if(match && values[kind]) match.value=values[kind];
    data.contact=values[kind]?contact:contact.filter(item=>contactKind(item.label)!==kind);
    if(values[kind]&&!match)data.contact.push({label:{email:'邮箱',phone:'手机',website:'主页',location:'意向'}[kind],value:values[kind]});
  }
  data.availability=values.availability.split('\n').map(line=>line.trim()).filter(Boolean);
  applyEducationFields(data,values.education);
  $('resume').value=JSON.stringify(data,null,2);
  renderCompletion(data);
}
function applyEducationFields(data, values) {
  let section=(data.sections||[]).find(section=>/教育|education/i.test(section.title));
  let item=section?.items.find(item=>item.education_fields)||section?.items[0];
  const previous=item?.education_fields||state.form_fields?.education||Object.fromEntries(educationKeys.map(key=>[key,'']));
  if(educationKeys.every(key=>(previous[key]||'')===values[key]))return;
  if(!Object.values(values).some(Boolean)) {
    if(item){section.items=section.items.filter(entry=>entry!==item);if(!section.items.length)data.sections=data.sections.filter(entry=>entry!==section);}
    return;
  }
  if(!section){section={title:'教育背景',items:[]};data.sections.unshift(section);}
  if(!item){item={};section.items.unshift(item);}
  let title=values.school,date=[values.start,values.end].filter(Boolean).join(' — ');
  const paragraphs=[],details=[values.college,values.major,values.degree].filter(Boolean).join(' · ');
  if(details)paragraphs.push(details);
  if(values.gpa)paragraphs.push('GPA '+values.gpa);
  if(values.courses)paragraphs.push('主修课程 '+values.courses);
  if(!paragraphs.length){paragraphs.push(title||date);if(title)title='';else date='';}
  Object.assign(item,{title,subtitle:'',date,paragraphs,education_fields:{...values},fact_ids:[],user_entered:true});
}
function renderCompletion(data) {
  const needs=[];
  if(!data.name?.trim())needs.push('填写姓名。');
  if(!(data.contact||[]).some(item=>['email','phone'].includes(contactKind(item.label))&&item.value))needs.push('可补充手机或邮箱。');
  const educationLabels={school:'学校',major:'专业',degree:'学历',end:'毕业时间'};
  const missingEducation=Object.keys(educationLabels).filter(key=>!$('edu-'+key).value.trim());
  if(missingEducation.length)needs.push('教育背景可补充'+missingEducation.map(key=>educationLabels[key]).join('、')+'。');
  if(!data.availability?.length)needs.push('可补充实习时间或每周到岗安排。');
  if(!contactValue(data,'location'))needs.push('可填写意向城市。');
  const projects=(data.sections||[]).filter(section=>/项目|project/i.test(section.title)).flatMap(section=>section.items||[]);
  if(!projects.length)needs.push('可添加一个项目，说明项目名称和本人负责的工作。');
  else if(projects.some(item=>!item.title||!item.paragraphs?.length))needs.push('补全项目名称和具体内容。');
  if(projects.some(item=>item.pending_contribution))needs.push('项目介绍已整理，请核对并补充本人负责的工作。');
  $('completion-list').replaceChildren(...needs.map(text=>el('li',text)));
}
function renderBodyEditor(data) {
  $('body-editor').replaceChildren();
  (data.sections||[]).forEach((section,si)=>{
    if(/教育|education/i.test(section.title))return;
    const block=el('section','');block.className='body-section';block.append(el('h3',section.title));
    section.items.forEach((item,ii)=>{
      const card=el('details','');card.className='entry-editor';
      card.open=!item.paragraphs?.length||(!item.title&&/项目|project/i.test(section.title));
      card.append(el('summary',item.title||`第 ${ii+1} 条${section.title}`));
      if(item.pending_contribution)card.append(el('p','已从材料整理项目介绍，请核对本人职责后确认。'));
      const fields=el('div','');fields.className='basic-fields';
      for(const [key,label] of [['title','名称'],['subtitle','职责 / 技术栈'],['date','时间'],['url','项目链接']]) {
        if(!/项目|经历|经验|project|experience/i.test(section.title)&&key!=='title')continue;
        const field=el('label',label),input=el('input','');input.value=item[key]||'';
        input.addEventListener('input',()=>updateBodyItem(si,ii,key,input.value));field.append(input);fields.append(field);
      }
      const label=el('label','具体内容（每行一条）'),text=el('textarea','');text.value=(item.paragraphs||[]).join('\n');text.rows=4;
      text.addEventListener('input',()=>updateBodyItem(si,ii,'paragraphs',text.value.split('\n').map(line=>line.trim()).filter(Boolean)));
      label.className='full-field';label.append(text);fields.append(label);card.append(fields);
      const remove=el('button','移除此条');remove.type='button';remove.className='secondary';
      remove.addEventListener('click',()=>{
        const current=JSON.parse($('resume').value);current.sections[si].items.splice(ii,1);
        current.sections=current.sections.filter(entry=>entry.items.length);$('resume').value=JSON.stringify(current,null,2);
        renderBodyEditor(current);renderCompletion(current);preview();
      });card.append(remove);block.append(card);
    });
    $('body-editor').append(block);
  });
}
function updateBodyItem(sectionIndex,itemIndex,key,value) {
  try {
    const data=JSON.parse($('resume').value),item=data.sections[sectionIndex].items[itemIndex];
    item[key]=value;item.user_entered=true;
    $('resume').value=JSON.stringify(data,null,2);preview();
  }catch{$('status').textContent='请先修正高级编辑中的 JSON。';}
}
function render() {
  $('case').textContent = state.run_key;
  $('sample').hidden = !state.synthetic;
  $('resume').value = JSON.stringify(state.resume,null,2);
  fillBasicFields(state.resume);
  renderCompletion(state.resume);
  renderBodyEditor(state.resume);
  $('facts').replaceChildren();
  for(const fact of state.facts) {
    const row=el('div','');row.className='fact';
    row.append(el('b',`${fact.id} · ${fact.field}`),el('p',fact.value),el('small',`${fact.source} / ${fact.location} · ${fact.status}`),el('small','原文：'+fact.quote));$('facts').append(row);
  }
  const visibleQuestions=state.questions.filter(q=>!isContactQuestion(q));
  questionGroups=(state.question_groups||visibleQuestions.map(q=>({...q,question_ids:[q.id],facts:state.facts.filter(f=>(q.fact_ids||[]).includes(f.id))})))
    .map(group=>({...group,question_ids:group.question_ids.filter(id=>visibleQuestions.some(q=>q.id===id))})).filter(group=>group.question_ids.length);
  $('count').textContent = questionGroups.length?`（${questionGroups.length} 项核对）`:'';
  $('questions').replaceChildren();
  if(!questionGroups.length) $('questions').append(el('p','材料核对已完成，可继续编辑正文。'));
  questionGroups.forEach((group,i)=>{
    const records=state.questions.filter(q=>group.question_ids.includes(q.id));
    const project=(group.facts||[]).some(fact=>fact.field==='project');
    const row=el('div','');row.className='question';
    row.append(el('h3',project?'确认项目中的本人职责':/OCR|识别/.test(group.text)?'核对图片识别内容':'补充或核对材料信息'));
    row.append(el('p',project?'请核对哪些工作由你完成，可在下方补充具体职责。':/OCR|识别/.test(group.text)?'请对照原图核对识别文字，无法确认的内容可暂不采用。':'请补充准确表述，或选择暂不采用这组内容。'));
    const evidenceDetails=el('details','');evidenceDetails.className='evidence-details';
    evidenceDetails.append(el('summary',`查看材料依据（${(group.facts||[]).length} 条）`));
    for(const message of group.messages||[group.text])evidenceDetails.append(el('p',message));
    if(group.source||group.sourcefile)evidenceDetails.append(el('small','来源 '+(group.source||group.sourcefile)));
    for(const fact of group.facts||[]) {
      const evidence=el('div','');evidence.className='group-evidence';
      evidence.append(el('b',fact.value),el('small',`${fact.source||''} / ${fact.location||''}`),el('p','原文 '+(fact.quote||'')));evidenceDetails.append(evidence);
    }
    const mixed=new Set(records.map(q=>(q.resolution||'')+'\n'+(q.note||''))).size>1;
    if(mixed) {
      const details=el('details','');details.append(el('summary','查看已有处理结果'));
      records.forEach(q=>details.append(el('p',`${q.resolution||'待处理'} · ${q.note||'未填写说明'}`)));evidenceDetails.append(details);
    }
    const label=el('label','处理方式 '),select=el('select','');select.id='group-'+i;select.dataset.changed='false';
    for(const [v,t] of [['','待处理'],['confirmed','已核实'],['omitted','暂不采用']]) {const o=el('option',t);o.value=v;select.append(o);}
    select.value=new Set(records.map(q=>q.resolution||'')).size===1?(records[0].resolution||''):'';
    select.addEventListener('change',()=>{
      select.dataset.changed='true';
      if(select.value==='omitted'&&!note.value){note.value='用户选择省略本项及相关事实。';note.dataset.generated='true';}
      else if(select.value!=='omitted'&&note.dataset.generated==='true'){note.value='';note.dataset.generated='false';}
    });label.append(select);row.append(label);
    const note=el('input','');note.id='group-note-'+i;note.dataset.changed='false';
    note.value=new Set(records.map(q=>q.note||'')).size===1?(records[0].note||''):'';
    note.placeholder='确认时说明可空，省略原因可编辑';note.setAttribute('aria-label',group.text+'的可选说明');
    note.addEventListener('input',()=>{note.dataset.changed='true';note.dataset.generated='false';});evidenceDetails.append(note);
    if(project) {
      const contribution=el('textarea','');contribution.id='group-contribution-'+i;contribution.rows=2;
      contribution.placeholder='可填写你具体负责的模块、实现方法和可核实结果';contribution.setAttribute('aria-label','本人负责的工作');row.append(contribution);
      const adopt=el('button','整理为项目条目'),feedback=el('p','核实后可整理项目名称、职责和链接。');
      adopt.type='button';adopt.className='secondary adopt-project';adopt.disabled=select.value!=='confirmed';
      feedback.className='hint';feedback.setAttribute('role','status');
      feedback.id='group-feedback-'+i;
      select.addEventListener('change',()=>{adopt.disabled=select.value!=='confirmed';});
      adopt.addEventListener('click',()=>adoptProjectFacts(group,select,feedback));row.append(adopt,feedback);
    }
    row.append(evidenceDetails);
    $('questions').append(row);
  });
  document.querySelectorAll('input[name=template]').forEach(e=>e.checked=e.value===state.selection?.template_id);
  $('mode').value=state.selection?.mode||'print';$('paper').value=state.selection?.paper||'A4';preview();
}
async function adoptProjectFacts(group, select, feedback) {
  try {
    if(select.value!=='confirmed')throw Error('请先将本组处理方式选为“已核实 / 已补充”。');
    syncBasicFields();
    const data=JSON.parse($('resume').value);
    if(!Array.isArray(data.sections))throw Error('请先在高级编辑中将 sections 修正为栏目数组。');
    const i=questionGroups.indexOf(group),facts=(group.facts||[]).filter(fact=>fact.field==='project');
    feedback.textContent='正在整理项目结构…';
    const result=await api('/api/project-preview',{revision:state.revision,resume:data,fact_ids:facts.map(fact=>fact.id),contribution:$('group-contribution-'+i)?.value||''});
    $('resume').value=JSON.stringify(result.resume,null,2);renderBodyEditor(result.resume);preview();
    $('group-contribution-'+i).dataset.applied=$('group-contribution-'+i).value;
    feedback.textContent='已整理为项目条目，请在“经历与技能”中检查、修改后保存。';
  }catch(error){feedback.textContent=error.message;}
}
function buildPayload() {
  syncBasicFields();
  const questions=state.questions.map(q=>({...q}));
  questionGroups.forEach((group,i)=>{
    const select=$('group-'+i),note=$('group-note-'+i);
    for(const q of questions.filter(q=>group.question_ids.includes(q.id))) {
      if(select.dataset.changed==='true'){
        q.resolution=select.value;
        if(select.value==='omitted'&&!q.note&&note.dataset.generated==='true')q.note=note.value;
      }
      if(note.dataset.changed==='true')q.note=note.value;
    }
  });
  return {...state,resume:JSON.parse($('resume').value),manual_inputs:manualInputs(),selection:{schema_version:1,template_id:selected(),mode:$('mode').value,paper:$('paper').value},questions};
}
async function loadPhoto() {
  const request=++photoRequest;
  try {
    const response=await fetch(reviewPath('/api/photo'),{headers:{Authorization:'Bearer '+token},cache:'no-store'});
    if(!response.ok && response.status!==404)throw Error('照片预览读取失败，请重试。');
    const blob=response.ok?await response.blob():null;
    if(request!==photoRequest)return;
    if(photoUrl)URL.revokeObjectURL(photoUrl);
    photoUrl=blob?URL.createObjectURL(blob):'';
    $('remove-photo').hidden=!photoUrl;preview();
  } catch(error){$('photo-status').textContent=error.message;}
}
async function changePhoto(file) {
  const controls=[...document.querySelectorAll('button,input,select,textarea')].map(control=>[control,control.disabled]);
  controls.forEach(([control])=>{control.disabled=true;});
  try {
    if(file&&!/\.(png|jpe?g)$/i.test(file.name))throw Error('请选择 PNG 或 JPG 照片。');
    if(file&&file.size>2_000_000)throw Error('照片超过 2 MB，请选择较小的图片。');
    const localResume=JSON.parse($('resume').value);
    let body={remove:true,revision:state.revision};
    if(file) {
      const content=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result.split(',')[1]);reader.onerror=()=>reject(Error('照片读取失败'));reader.readAsDataURL(file);});
      body={name:file.name,content_base64:content,revision:state.revision};
    }
    const result=await api('/api/photo',body);
    state={...state,revision:result.state.revision,resume:{...state.resume,photo:result.state.resume.photo}};
    localResume.photo=result.state.resume.photo;
    $('resume').value=JSON.stringify(localResume,null,2);
    await loadPhoto();
    $('photo-status').textContent=file?'照片已保存。请核对后再确认导出。':'照片已移除。';
  }catch(error){
    $('photo-status').textContent=error.state?'内容已在另一页面更新。本页未保存内容仍保留，请先复制高级正文与处理说明，再刷新页面后上传照片。':error.message;
  }
  finally{controls.forEach(([control,disabled])=>{control.disabled=disabled;});$('photo-file').value='';}
}
async function submit(approve) {
  $('status').className='';
  const disabledButtons=[...document.querySelectorAll('button')].map(button=>[button,button.disabled]);
  disabledButtons.forEach(([button])=>{button.disabled=true;});
  try {
    if(!selected()) throw Error('请先选择一种模板。');
    if(approve&&!$('basic-name').value.trim())throw Error('请填写姓名。');
    if(!$('basic-email').checkValidity())throw Error('请检查邮箱格式，或留空。');
    for(let i=0;i<questionGroups.length;i++) {
      const contribution=$('group-contribution-'+i);
      if(contribution?.value.trim()&&contribution.dataset.applied!==contribution.value) {
        await adoptProjectFacts(questionGroups[i],$('group-'+i),$('group-feedback-'+i));
        if(contribution.dataset.applied!==contribution.value)throw Error($('group-feedback-'+i).textContent);
      }
    }
    const payload=buildPayload();
    const result=await api(approve?'/api/approve':'/api/save',payload);state=result.state;render();
    $('status').textContent=approve?'已确认，正在通知当前工作流继续生成 Word / PDF。':'修改已保存。';
    if(approve) {
      const storageKey='resume-export-'+(dagRunId||'legacy')+'-'+state.run_key+'-'+state.revision;
      if(exportFailed)sessionStorage.removeItem(storageKey);
      let requestId=sessionStorage.getItem(storageKey);
      if(!requestId){requestId=crypto.randomUUID();sessionStorage.setItem(storageKey,requestId);}
      const continuation = await api('/api/export',{request_id:requestId});
      const workflow = continuation.dag_run_id ? `（${continuation.dag_id || 'resume_prepare'} / ${continuation.dag_run_id}）` : '';
      $('status').textContent='已提交继续生成请求'+workflow+'，下面会显示处理进度和下载文件。';
      await pollExports();
    }
  } catch(error) {
    const conflict=error.message.includes('审阅内容已变化');
    if(error.state&&!conflict){state=error.state;render();}
    $('status').className='error';$('status').textContent=error.message+(conflict?'。本页输入仍保留，请复制所需内容后刷新。':'');
  }
  finally {disabledButtons.forEach(([button,disabled])=>{button.disabled=disabled;});}
}
$('resume').addEventListener('input',()=>{try{const data=JSON.parse($('resume').value);fillBasicFields(data);renderBodyEditor(data);renderCompletion(data);}catch{}preview();});
for(const id of [...['name','email','phone','headline','website','location','availability'].map(key=>'basic-'+key),...educationKeys.map(key=>'edu-'+key)])$(id).addEventListener('input',()=>{try{syncBasicFields();preview();}catch{$('status').textContent='请先修正高级编辑中的 JSON，再修改信息。';}});
$('photo-file').addEventListener('change',event=>{const file=event.target.files[0];if(file)void changePhoto(file);});
$('add-project').addEventListener('click',()=>{
  const data=JSON.parse($('resume').value);
  let projects=data.sections.find(section=>section.title==='项目经历');
  if(!projects){projects={title:'项目经历',items:[]};data.sections.push(projects);}
  projects.items.push({title:'',subtitle:'',date:'',url:'',paragraphs:[],fact_ids:[],user_entered:true});
  $('resume').value=JSON.stringify(data,null,2);renderBodyEditor(data);preview();
});
$('remove-photo').addEventListener('click',()=>changePhoto(null));document.querySelectorAll('input[name=template]').forEach(e=>e.addEventListener('change',preview));
$('save').addEventListener('click',()=>submit(false));$('approve').addEventListener('click',()=>submit(true));
async function fileBlob(name,key) {
  const path=reviewPath('/api/file?export_key='+encodeURIComponent(key)+'&name='+encodeURIComponent(name));
  const response=await fetch(path,{headers:{Authorization:'Bearer '+token}});
  if(!response.ok){const result=await response.json();throw Error(result.error);}
  return response.blob();
}
async function pollExports() {
  if(!state||pollBusy)return;
  pollBusy=true;
  try {
    const result=await api('/api/export-status');
    $('exports').hidden=false;
    const labels={waiting_input:'请先补充待确认项',waiting_review:'等待你审阅并确认',approved:'已确认，等待导出',waiting_visual:'Word / PDF 已生成并通过自动检查，请查看全部页面',final:'已确认最终版本',failed:'导出失败，请查看错误并处理后重试'};
    const execution=result.execution;
    exportFailed=result.state==='failed'||execution?.state==='failed';
    const steps = execution?.steps || execution?.tasks || [];
    const waitingReview = ['waiting_review','waiting_input'].includes(result.state) || steps.some(step => step.task_id === 'await_review' && ['up_for_reschedule','deferred'].includes(step.state));
    const stepLabels = { await_review: '人工审阅', export_resume: '生成 Word / PDF', publish_review: '准备审阅', snapshot_materials: '归档材料', organize_facts: '整理事实', write_draft: '起草正文' };
    const stateLabels = { success: '已完成', running: '执行中', queued: '等待执行', scheduled: '等待执行', failed: '失败', upstream_failed: '前序失败', skipped: '已跳过', up_for_retry: '等待重试', up_for_reschedule: '等待继续', deferred: '等待继续' };
    $('export-status').textContent=waitingReview?'当前工作流正在等待你审阅。点击“确认并生成 Word/PDF”后，本次运行继续执行后续任务。':execution?('流程进度 · '+(stateLabels[execution.state]||execution.state)+' · '+steps.map(step=>(stepLabels[step.task_id]||step.task_id)+' '+(stateLabels[step.state]||step.state||'等待执行')).join(' / ')):(labels[result.state]||result.state);
    if(exportFailed) {
      const failedStep=steps.find(step=>step.state==='failed');
      const reason=result.error||result.report?.failure_message||'';
      $('export-status').textContent='生成失败'+(failedStep?'，失败步骤 '+(stepLabels[failedStep.task_id]||failedStep.task_id):'')+'。'+reason;
    }
    if(result.report?.errors?.length)$('export-status').textContent+='：'+result.report.errors.join('；');
    $('export-location').textContent=result.directory?'文件保存在：'+result.directory:'';
    latestExportKey=result.export_key||'';
    $('accept-label').hidden=$('accept').hidden=result.state!=='waiting_visual';
    const signature=(result.export_key||'')+':'+result.state;
    if(signature===lastExport)return;
    lastExport=signature;
    imageUrls.splice(0).forEach(URL.revokeObjectURL);$('downloads').replaceChildren();$('pages').replaceChildren();$('all-pages').checked=false;
    for(const name of result.files||[]) {
      if(name.endsWith('.png')) {
        const blob=await fileBlob(name,result.export_key),url=URL.createObjectURL(blob);imageUrls.push(url);
        const img=el('img','');img.src=url;img.alt='导出文件页面 '+name;img.className='export-page';$('pages').append(img);
      } else {
        const button=el('button',name.endsWith('.pdf')?'下载 PDF':'下载 Word');button.className='secondary';
        button.addEventListener('click',async()=>{try{const url=URL.createObjectURL(await fileBlob(name,result.export_key));const a=el('a','');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),10000);}catch(e){$('export-status').textContent=e.message;}});
        $('downloads').append(button);
      }
    }
  } catch(error){$('exports').hidden=false;$('export-status').textContent=error.message;}
  finally{pollBusy=false;}
}
$('accept').addEventListener('click',async()=>{
  if(!$('all-pages').checked){$('export-status').textContent='请逐页查看后勾选确认。';return;}
  try{await api('/api/accept',{export_key:latestExportKey,confirm_all_pages:true});await pollExports();}catch(e){$('export-status').textContent=e.message;}
});
(async()=>{
  try {
    const response=await fetch(reviewPath('/api/session'),{headers:{'X-Resume-Portal':'1'}});
    if(response.ok){const session=await response.json();token=session.token;sessionStorage.setItem('resume-review-token',token);}
    state=await api('/api/state');render();await loadPhoto();
    await pollExports();setInterval(pollExports,3000);
  } catch(error){$('status').className='error';$('status').textContent=error.message+'。请从简历工作台重新进入此版本。';}
})();
