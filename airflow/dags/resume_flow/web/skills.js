'use strict';
(() => {
  const $ = id => document.getElementById(id);
  let token, catalog, currentId, currentDetail, busy = false, polling = false, reviewLoadedFor;
  let reviewDirty = false, openedJudgmentFor;
  let requestId = crypto.randomUUID().replaceAll('-', ''), lastSubmittedConfig;
  const labels = {submitted:'等待 Airflow 调度', submission_failed:'提交失败，可重试', running:'主机执行中', finished:'实验执行结束', failed:'执行失败',
    success:'成功', queued:'排队', scheduled:'待执行', up_for_reschedule:'等待主机结果', up_for_retry:'重试等待',
    upstream_failed:'上游失败', skipped:'跳过'};
  const criteria = ['功能、限制、版本和许可准确', '两条给定命令准确', '实际空 CSV 的四列及顺序准确，无数据行',
    '未知事实保持未知', '反馈流转和维护职责可用，明确标为建议', '最终材料之间的事实一致'];
  function text(tag, value, className) {
    const element = document.createElement(tag);
    element.textContent = value;
    if (className) element.className = className;
    return element;
  }
  async function session() {
    const response = await fetch('/api/session', {headers:{'X-Resume-Portal':'1'}});
    if (!response.ok) throw new Error('工作台会话不可用，请刷新页面');
    token = (await response.json()).token;
  }
  async function api(path, payload, retried = false) {
    if (!token) await session();
    const response = await fetch(path, {method:payload ? 'POST':'GET',
      headers:{Authorization:'Bearer '+token, 'Content-Type':'application/json'},
      body:payload ? JSON.stringify(payload):undefined});
    if (response.status === 403 && !retried) { await session(); return api(path,payload,true); }
    const value = await response.json();
    if (!response.ok) throw new Error(value.error || '请求失败');
    return value;
  }
  function error(message) { $('page-error').hidden = !message; $('page-error').textContent = message || ''; }
  async function loadCatalog() {
    catalog = await api('/api/skills/catalog');
    $('bridge-status').textContent = catalog.bridge.online
      ? '● 本机执行桥在线' + (catalog.bridge.active_job ? ' · 正在执行 '+catalog.bridge.active_job : ' · 等待任务')
      : '○ 本机执行桥离线。请运行 experiments/skill_portal/start_bridge.ps1，已提交任务会保留在队列。';
    if (!$('request').value && catalog.case) $('request').value = catalog.case.request;
    $('case-facts').textContent = catalog.case ? JSON.stringify({facts:catalog.case.facts, criteria:catalog.case.criteria},null,2) : '实验输入尚未导入，请先启动配置脚本。';
    const cohortSignature=JSON.stringify(catalog.cohorts);
    if ($('cohorts').dataset.signature !== cohortSignature) {
      $('cohorts').dataset.signature=cohortSignature;
      $('cohorts').replaceChildren();
      for (const group of catalog.cohorts) {
        const card = text('div','', 'cohort');
        const incomplete=group.planned && (group.pending_review || group.completed < group.planned);
        card.append(text('p',group.model),text('b',`${group.correct}/${group.completed}`),
          text('p',`N${group.size} · ${incomplete ? '执行与内容复核进行中' : '内容复核通过 '+Math.round(group.accuracy*100)+'%'}`));
        if (group.planned) card.append(text('p',`计划 ${group.planned} 次 · 已执行 ${group.completed} 次 · 待内容复核 ${group.pending_review} 次`));
        const trials=document.createElement('details');
        trials.append(text('summary','展开本组每次运行'));
        for (const [index,id] of (group.jobs || []).entries()) {
          const job=catalog.jobs.find(item=>item.job_id===id);
          const button=text('button',`第${index+1}次 · ${job?.review?.label || '查看证据'}`,'quiet trial-button');
          button.type='button'; button.addEventListener('click',()=>selectJob(id).catch(e=>error(e.message)));
          trials.append(button);
        }
        card.append(trials);
        $('cohorts').append(card);
      }
    }
    const controls=catalog.context_control?.results || [];
    $('context-results').replaceChildren(...controls.map(row=>text('p',
      `${row.context===32768?'32k':'40k'} · 第${row.repeat}次 · ${row.http_status===400?'HTTP400，32849 > 32768':'返回原生工具调用，输入32849 tokens'} · ${row.seconds.toFixed(2)}秒`)));
    renderHistory();
    renderBoundaries();
  }
  function jobButton(label, id) {
    const button=text('button',label,'quiet'); button.type='button';
    button.addEventListener('click',()=>selectJob(id).catch(e=>error(e.message)));
    return button;
  }
  function renderBoundaries() {
    const signature=JSON.stringify(catalog.cohorts);
    if ($('boundary-models').dataset.signature===signature) return;
    $('boundary-models').dataset.signature=signature;
    $('boundary-models').replaceChildren();
    const models=[
      {title:'本地 Qwen3.5:9b · 32k', groups:catalog.cohorts.filter(g=>g.model.startsWith('Qwen') && g.model.includes('32k')),
       conclusion:'已正确完成到 N166。N170 与 N180 各3次均未通过。数量的稳定临界区间尚未定位。',
       failure:'内容错误在 N5 已出现。容量边界有直接重复证据，32849-token输入超过32768，两次都返回HTTP400。',
       actions:[['查看32k/40k重复对照','history-context-controls-20261112'],['查看N170超限','history-local-32768-170-1']]},
      {title:'本地 Qwen3.5:9b · 40k', groups:catalog.cohorts.filter(g=>g.model.startsWith('Qwen') && g.model.includes('40k')),
       conclusion:'增加容量后，同一失败请求能返回。完整任务100与166各1/3正确。',
       failure:'N166的一条完整任务生成8节点、最长链4，随后41226-token输入超过40960，再次失败。',
       actions:[['查看40k后续超限','history-local-40960-166-1'],['查看受控改进','history-context-controls-20261112']]},
      {title:'DeepSeek · legacy审查', groups:catalog.cohorts.filter(g=>g.model.startsWith('deepseek')),
       conclusion:'当前正确完成的最大实测规模为 N180，本轮3/10。数量稳定失败点与上下文容量故障尚未测出。',
       failure:'本轮N100与N180自动核验均10/10，逐文复核分别2/10和3/10正确。已发现未知事实被写成否定断言、建议规则冲突及歧义。',
       actions:[['查看N180正确任务','deepseek-20261113-n180-09'],['查看内容失败原句','deepseek-20261113-n180-08']]}
    ];
    for (const model of models) {
      const card=text('article','','boundary-card');
      card.append(text('h3',model.title),text('p',model.conclusion,'boundary-conclusion'));
      const table=document.createElement('table'), head=document.createElement('tr');
      for(const title of ['候选N','最终正确 / 完整任务','批次']) head.append(text('th',title));
      const thead=document.createElement('thead'), tbody=document.createElement('tbody');thead.append(head);table.append(thead,tbody);
      for(const group of model.groups) {
        const row=document.createElement('tr');
        row.append(text('td',group.size),text('td',`${group.correct}/${group.completed}`),
          text('td',group.planned?'11月13日新十次':group.completed===1?'11月12日单次':'历史重复组'));
        tbody.append(row);
      }
      card.append(table,text('p',model.failure));
      const actions=text('div','','actions');for(const [label,id] of model.actions)actions.append(jobButton(label,id));card.append(actions);
      $('boundary-models').append(card);
    }
  }
  function renderHistory() {
    const filter = $('history-filter').value;
    const rows = catalog.jobs.filter(job => filter === 'all' || (filter === 'web' ? job.origin === 'web' :
      filter === 'diagnostic' ? job.origin === 'integration-negative-control' : job.origin === 'history' && job.config.backend === filter));
    const signature=JSON.stringify(rows);
    if ($('history').dataset.signature===signature) return;
    $('history').dataset.signature=signature;
    $('history').replaceChildren();
    for (const job of rows) {
      const row = document.createElement('tr');
      row.append(text('td',job.job_id),text('td',`${job.config.backend} / ${job.config.size}`),
        text('td',labels[job.phase] || job.phase),text('td',job.review?.label || '待复核'));
      const action = document.createElement('td'), button = text('button','查看');
      button.type = 'button'; button.addEventListener('click',() => selectJob(job.job_id).catch(e=>error(e.message)));
      action.append(button); row.append(action); $('history').append(row);
    }
    if (!rows.length) { const row=document.createElement('tr'), cell=text('td','当前筛选下暂无运行记录'); cell.colSpan=5; row.append(cell); $('history').append(row); }
  }
  async function selectJob(id, scroll = true) {
    if (currentId !== id) {
      openedJudgmentFor = undefined;
      reviewLoadedFor = undefined;
      reviewDirty = false;
      criteria.forEach((_,i)=>{$('criterion-'+i).checked=false;});
      $('review-notes').value=''; $('review-message').textContent=''; $('preview').hidden=true;
      $('active').hidden=true;
    }
    currentId = id;
    $('selection-status').hidden=false;
    $('selection-status').textContent='正在打开运行 '+id+' 的判定与原始证据…';
    const url = new URL(location.href); url.searchParams.set('job_id',id); history.replaceState(null,'',url);
    await loadDetail();
    if (currentId!==id) return;
    $('selection-status').hidden=true;
    if (scroll) $('active').scrollIntoView({behavior:'smooth',block:'start'});
  }
  async function fileAction(name, preview, line = null) {
    const id=currentId;
    const path = '/api/skills/file?job_id='+encodeURIComponent(id)+'&name='+encodeURIComponent(name);
    if (preview) {
      const value = await api(path+'&preview=1');
      if (currentId!==id) return;
      $('preview').hidden=false; $('preview').replaceChildren(text('strong',name));
      const lines=value.content.split('\n');
      lines.forEach((content,index)=>{
        const item=text('span',`${index+1}  ${content}`,'preview-line');
        if(index+1===line)item.classList.add('focus-line');
        $('preview').append(item);
      });
      const focus=$('preview').querySelector('.focus-line');
      (focus || $('preview')).scrollIntoView({behavior:'smooth',block:'center'});
      return;
    }
    const response=await fetch(path,{headers:{Authorization:'Bearer '+token}});
    if (!response.ok) throw new Error((await response.json()).error);
    const url=URL.createObjectURL(await response.blob()), anchor=document.createElement('a');
    anchor.href=url; anchor.download=name.split('/').at(-1); anchor.click();
    setTimeout(()=>URL.revokeObjectURL(url),3000);
  }
  function renderOutcome(value) {
    const {job, result, explanation} = value;
    const review = result?.review;
    let state = 'pending', title = '等待执行', summary = labels[job.phase] || job.phase;
    let action = '', target = 'judgment';
    if (job.phase === 'failed' || job.phase === 'submission_failed' || result?.partial) {
      state = 'failed'; title = '执行失败';
      summary = job.error || result?.error || review?.label || '执行中断，已保存现有运行记录。';
      action = '定位执行问题';
      if (!explanation) target = job.error || result?.error || value.airflow_error ? 'run-error' : 'execution-log';
    } else if (!result) {
      title = job.phase === 'running' ? '执行中' : job.phase === 'finished' ? '结果归档中' : '等待执行';
      summary = '内容结论将在产物归档并完成六项复核后显示。';
    } else if (review?.state === 'invalidated') {
      title = '待重新复核'; summary = '最终文件已变化，现有内容复核需要更新。';
      action = '查看文件核验问题';
    } else if (!result.automatic_passed) {
      state = 'failed'; title = '自动核验未通过';
      summary = result.error || review?.label || '产物未满足自动核验要求。'; action = '定位问题';
    } else if (review?.state === 'accepted') {
      state = 'correct'; title = '正确'; summary = '自动核验通过，六项内容复核全部通过。';
      action = '查看通过依据';
    } else if (review?.state === 'rejected') {
      state = 'incorrect'; title = '内容未通过';
      const failed = (review.checks || []).flatMap((passed, index) => passed === false ? [index + 1] : []);
      summary = failed.length ? `自动核验通过，第 ${failed.join('、')} 项内容标准未通过。` : '自动核验通过，最终内容复核未通过。';
      action = '定位问题';
    } else if (review?.state === 'ambiguous') {
      title = '内容存在歧义'; summary = '内容复核存在待确认项，当前计入未通过。'; action = '查看争议位置';
    } else if (review?.state === 'diagnostic') {
      state = 'diagnostic'; title = '对照实验已归档'; summary = review.label; action = '查看对照证据';
    } else {
      title = '待内容复核'; summary = '自动核验通过，等待六项内容复核。';
      action = '进行内容复核'; target = 'review-section';
    }
    $('run-outcome').dataset.state = state;
    $('judgment').dataset.state = state;
    $('outcome-heading').textContent = title;
    $('outcome-summary').textContent = summary;
    $('outcome-action').hidden = !action;
    $('outcome-action').textContent = action;
    $('outcome-action').dataset.target = target;
  }
  function renderJudgment(explanation) {
    $('judgment').hidden=!explanation || openedJudgmentFor !== currentId;
    if(!explanation)return;
    const signature=JSON.stringify(explanation);
    if($('judgment').dataset.signature===signature)return;
    $('judgment').dataset.signature=signature;
    $('judgment-heading').textContent=explanation.title;
    $('judgment-verdict').textContent=explanation.verdict;
    $('judgment-standard').textContent=explanation.standard;
    $('judgment-reason').textContent=explanation.reason;
    $('judgment-verification').textContent=explanation.evidence.length
      ? (explanation.verified ? '以下片段已核对归档SHA256，行号来自真实文件。':'部分证据未通过文件核验，请先检查提示。') : '下方文件和复核说明可继续逐项检查。';
    $('judgment-criteria').replaceChildren(...(explanation.criteria || []).map(row=>text('li',`${row.passed?'✓ 复核通过':'待核对'} · ${row.title}`)));
    $('judgment-evidence').replaceChildren();
    for(const item of explanation.evidence) {
      const box=text('article','','evidence-excerpt');box.append(text('h4',item.label));
      if(item.verified) {
        box.append(text('p',`${item.name} · 定位第${item.line}行`,'mono'));
        const pre=document.createElement('pre');
        for(const row of item.lines) pre.append(text('span',`${row.number}  ${row.text}`,row.focus?'excerpt-line focus-line':'excerpt-line'));
        const button=text('button','打开原文件并定位这一行','quiet');button.type='button';
        button.addEventListener('click',()=>fileAction(item.name,true,item.line).catch(e=>error(e.message)));
        box.append(pre,button);
      } else box.append(text('p',item.error,'evidence-error'));
      $('judgment-evidence').append(box);
    }
  }
  function renderFiles(files, element) {
    const signature=JSON.stringify(files);
    if (element.dataset.signature===signature) return;
    element.dataset.signature=signature;
    element.replaceChildren();
    for (const file of files) {
      const row=document.createElement('li');
      row.append(text('span',file.name+' · '+file.bytes+' B','file-name'));
      for (const [label,preview] of [['预览',true],['下载',false]]) {
        const button=text('button',label,'quiet'); button.type='button';
        button.addEventListener('click',()=>fileAction(file.name,preview).catch(e=>error(e.message)));
        row.append(button);
      }
      element.append(row);
    }
    if (!files.length) element.append(text('li','尚无文件'));
  }
  async function loadDetail() {
    const id=currentId, value=await api('/api/skills/job?job_id='+encodeURIComponent(id));
    if (id !== currentId) return;
    currentDetail=value; const job=value.job, result=value.result;
    renderOutcome(value);
    renderJudgment(value.explanation);
    $('active').hidden=false; $('phase').textContent=labels[job.phase] || job.phase;
    $('job-id').textContent=job.job_id;
    const originLabel=job.origin==='history' ? '历史实验归档。' :
      job.origin==='integration-negative-control' ? '集成诊断记录。' : '网页提交记录。';
    $('run-note').textContent=originLabel+
      (value.airflow?.state==='success' ? (result && !result.automatic_passed
        ? '旧版 Airflow 显示归档成功，本次模型交付未通过。' : 'Airflow 已完成本次执行与归档。') : '');
    $('airflow-link').hidden=!job.airflow_url; $('airflow-link').href=job.airflow_url || '#';
    $('airflow-tasks').replaceChildren();
    for (const task of value.airflow?.tasks || []) $('airflow-tasks').append(text('li',task.task_id+' · '+(labels[task.state] || task.state || '待执行')));
    const failure=job.error || result?.error || value.airflow_error;
    $('run-error').hidden=!failure; $('run-error').textContent=failure || '';
    $('metrics').replaceChildren();
    const metrics=result?.metrics;
    for (const [label,key] of [['候选 Skill','skills'],['实际 Skill 种数','actual_skills'],['生成节点','nodes'],['最长链节点','chain']]) {
      const item=text('div','','metric'); item.append(text('b',metrics?.[key] ?? (key==='skills'?job.config.size:'—')),text('span',label)); $('metrics').append(item);
    }
    const dag=result?.dag || value.progress?.dag || [];
    const dagSignature=JSON.stringify(dag);
    if ($('skill-dag').dataset.signature !== dagSignature) {
      $('skill-dag').dataset.signature=dagSignature;
      $('skill-dag').replaceChildren();
      for (const node of dag) {
        const item=document.createElement('li'); item.append(text('strong',node.id+' · '+node.skill),
          text('p',node.depends_on.length ? '上游 '+node.depends_on.join('、')+' → 本节点' : '根节点 · 读取原始需求与 facts'),
          text('p','输入 '+(node.input_reference_ids.join('、') || '原始事实')+' · 输出 '+node.output_reference_ids.join('、')));
        const requestDetails=document.createElement('details');
        requestDetails.append(text('summary','查看本步请求'),text('pre',node.request));
        item.append(requestDetails); $('skill-dag').append(item);
      }
    }
    $('progress-note').textContent=result ? '链长由实际引用计算，包含实际生成的修订节点。' : `已保存 ${value.progress?.requests || 0} 份请求、${value.progress?.responses || 0} 份原始回复记录。`;
    renderFiles((result?.files || []).filter(f=>f.final),$('files'));
    renderFiles((result?.files || []).filter(f=>!f.final),$('evidence-files'));
    const reviewFiles=(result?.files || []).filter(f=>/content-review|adjudication|control-calls|summary\.json/.test(f.name));
    renderFiles(reviewFiles,$('review-evidence'));
    $('execution-log').textContent=value.log || '本条历史记录的原始请求与回复见证据文件。';
    $('review-section').hidden=!result;
    if (result) {
      $('review-state').textContent=result.review.label;
      $('review-explanation').textContent=result.review.notes || '';
      $('review-form').hidden=job.origin==='history' || result.partial === true || !result.files.some(f=>f.final);
      const reviewVersion=id+JSON.stringify(result.review);
      if (reviewLoadedFor !== reviewVersion && !reviewDirty) {
        criteria.forEach((_,i)=>{$('criterion-'+i).checked=result.review.checks?.[i] === true;});
        $('review-notes').value=result.review.notes || '';
        reviewLoadedFor=reviewVersion;
      }
    }
  }
  criteria.forEach((criterion,index)=>{
    const label=text('label','','check'), input=document.createElement('input'); input.type='checkbox'; input.id='criterion-'+index;
    label.append(input,document.createTextNode(criterion)); $('review-checks').append(label);
  });
  $('backend').addEventListener('change',()=>{
    const cloud=$('backend').value==='deepseek'; $('cost-label').hidden=!cloud; $('seed').disabled=cloud;
    $('model-note').textContent=cloud?'DeepSeek 将接收公开虚构用例、选中 Skill 原文及产物，产生 API 费用。采用 legacy 自动审查。':'本地 Qwen3.5:9b，32k 上下文，fact-evidence 自动审查。';
  });
  $('reset-request').addEventListener('click',()=>{if(catalog.case)$('request').value=catalog.case.request;});
  $('history-filter').addEventListener('change',renderHistory);
  document.querySelectorAll('[data-job]').forEach(button=>button.addEventListener('click',
    ()=>selectJob(button.dataset.job).catch(e=>error(e.message))));
  $('experiment-form').addEventListener('submit',async event=>{
    event.preventDefault(); if(busy)return; busy=true; $('start-button').disabled=true; error('');
    try {
      const settings={request:$('request').value, size:Number($('size').value),
        backend:$('backend').value,seed:Number($('seed').value),accept_api_cost:$('accept-cost').checked};
      const signature=JSON.stringify(settings);
      if (lastSubmittedConfig && lastSubmittedConfig!==signature) requestId=crypto.randomUUID().replaceAll('-','');
      lastSubmittedConfig=signature;
      const result=await api('/api/skills/start',{request_id:requestId,...settings});
      requestId=crypto.randomUUID().replaceAll('-',''); lastSubmittedConfig=undefined;
      $('submit-status').textContent='已提交 '+result.job_id;
      $('preview').hidden=true; await loadCatalog(); await selectJob(result.job_id);
    } catch(e) {error(e.message);} finally {busy=false;$('start-button').disabled=false;}
  });
  $('review-form').addEventListener('submit',async event=>{
    event.preventDefault();
    try { const result=await api('/api/skills/review',{job_id:currentId,checks:criteria.map((_,i)=>$('criterion-'+i).checked),notes:$('review-notes').value});
      reviewDirty=false; $('review-message').textContent=result.label; await loadDetail(); await loadCatalog();
    } catch(e) {$('review-message').textContent=e.message;}
  });
  $('review-form').addEventListener('input',()=>{reviewDirty=true;});
  $('outcome-action').addEventListener('click',()=>{
    const target = $($('outcome-action').dataset.target);
    if (target.id === 'judgment') {
      openedJudgmentFor = currentId;
      target.hidden = false;
    }
    const details = target.closest('details');
    if (details) details.open = true;
    target.scrollIntoView({behavior:'smooth',block:'start'});
    const heading = target.querySelector('h3') || target;
    heading.tabIndex = -1;
    heading.focus({preventScroll:true});
  });
  async function poll() {
    if(polling)return;polling=true;
    try {await loadCatalog();if(currentId)await loadDetail();error('');} catch(e){error(e.message);} finally {polling=false;}
  }
  (async()=>{
    try {await loadCatalog(); const selected=new URLSearchParams(location.search).get('job_id');if(selected)await selectJob(selected,false);}
    catch(e){error(e.message);}
    setInterval(poll,5000);
  })();
})();
