'use strict';
(() => {
  const $ = id => document.getElementById(id);
  const form = $('prepare-form');
  const tokenKey = 'resume-review-token';
  const runKey = 'resume-portal-active-run';
  let token = sessionStorage.getItem(tokenKey);
  let sessionPromise;
  let jobsBusy = false;
  let runBusy = false;
  let submitting = false;
  let activeRun = null;
  let cases = [];
  let selectedFiles = [];
  let importing = false;
  let importRequestId = null;
  let importedCase = null;
  const intakeId = new URLSearchParams(location.search).get('intake_id');
  let activeIntake = null, intakeBusy = false, intakeInitialized = false, intakeChildObserved = false;
  try { activeRun = JSON.parse(sessionStorage.getItem(runKey) || 'null'); } catch (_) { sessionStorage.removeItem(runKey); }
  if (!activeRun || typeof activeRun.dag_run_id !== 'string') activeRun = null;
  if (intakeId && activeRun?.dag_run_id !== 'intake-'+intakeId) activeRun=null;
  const stateLabels = {
    queued: '等待执行', scheduled: '等待执行', running: '正在整理', success: '整理完成',
    failed: '整理失败', upstream_failed: '前序步骤失败', skipped: '已跳过',
    up_for_retry: '等待重试', up_for_reschedule: '等待继续', deferred: '等待继续',
    pending: '等待处理', prepared: '待人工审阅', ready: '待人工审阅',
    draft: '待人工审阅', approved: '已确认', exported: '已导出', reviewed: '已审阅',
    needs_review: '待人工审阅', awaiting_review: '待人工审阅', ready_for_review: '待人工审阅',
    waiting_input: '有待确认项', waiting_review: '待人工审阅', waiting_visual: '待查看成品', final: '最终版本'
  };
  const taskLabels = {
    open_material_page:'打开材料页',await_materials:'等待提交材料',snapshot_materials: '归档材料', organize_facts: '整理事实', write_draft: '起草正文', publish_review: '准备审阅', await_review: '等待人工审阅', export_resume: '生成 Word / PDF',
    discover_inputs: '读取材料', collect_materials: '读取材料', extract_materials: '提取文字',
    extract_evidence: '提取依据', extract_facts: '提取事实', prepare_resume: '整理简历',
    build_evidence: '整理依据', draft_resume: '起草正文', generate_draft: '起草正文',
    validate_draft: '检查草稿', save_draft: '保存草稿', prepare: '整理草稿',
    discover: '读取材料', extract: '提取文字', draft: '起草正文', persist: '保存草稿'
  };
  function message(id, text, error = false) {
    $(id).textContent = text;
    $(id).classList.toggle('error', error);
  }
  function shortError(value) {
    const raw = typeof value === 'string' ? value : value && typeof value.message === 'string' ? value.message : '';
    return raw ? raw.replace(/\s+/g, ' ').slice(0, 240) : '未能完成操作，请稍后重试或在 Airflow 查看详情。';
  }
  async function getSession() {
    if (!sessionPromise) sessionPromise = (async () => {
      const response = await fetch('/api/session', { headers: { 'X-Resume-Portal': '1' }, cache: 'no-store' });
      if (!response.ok) throw new Error('无法连接本机工作台，请确认服务正在运行。');
      const data = await response.json();
      if (!data.token) throw new Error('无法建立工作台会话，请刷新页面重试。');
      token = data.token;
      sessionStorage.setItem(tokenKey, token);
    })().finally(() => { sessionPromise = null; });
    return sessionPromise;
  }
  async function api(path, options = {}, retry = true) {
    if (!token) await getSession();
    const response = await fetch(path, {
      ...options, cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...options.headers, Authorization: `Bearer ${token}` }
    });
    if (response.status === 401 && retry) {
      token = null;
      sessionStorage.removeItem(tokenKey);
      await getSession();
      return api(path, options, false);
    }
    let data;
    try { data = await response.json(); } catch (_) { throw new Error(`工作台返回了无法读取的结果（${response.status}），请重试。`); }
    if (!response.ok) throw new Error(shortError(data.error || data.detail || `请求失败（${response.status}）`));
    return data;
  }
  function badge(state) {
    const item = document.createElement('span');
    item.className = 'badge';
    item.textContent = stateLabels[state] || '待查看';
    if (['failed', 'upstream_failed'].includes(state)) item.classList.add('failed');
    else if (['queued', 'pending', 'scheduled', 'running', 'up_for_retry', 'waiting_input'].includes(state)) item.classList.add('waiting');
    return item;
  }
  function element(tag, className, text) {
    const item = document.createElement(tag);
    if (className) item.className = className;
    if (text !== undefined) item.textContent = text;
    return item;
  }
  function setCases(nextCases) {
    const next = nextCases.filter(item => typeof item === 'string');
    if (JSON.stringify(cases) !== JSON.stringify(next) || $('case-id').disabled) {
      const selected = $('case-id').value;
      cases = next;
      $('case-id').replaceChildren();
      if (!cases.length) $('case-id').append(new Option('暂无材料案例', ''));
      for (const caseId of cases) $('case-id').append(new Option(caseId, caseId));
      if (cases.includes(selected)) $('case-id').value = selected;
      $('case-id').disabled = !cases.length;
      const importCase = $('import-case').value;
      $('import-case').replaceChildren(new Option('新建材料案例', ''));
      for (const caseId of cases) $('import-case').append(new Option(caseId, caseId));
      if (cases.includes(importCase)) $('import-case').value = importCase;
    }
    $('case-note').hidden = Boolean(cases.length);
    if (importedCase && cases.includes(importedCase)) {
      $('case-id').value = importedCase;
      $('import-case').value = importedCase;
      importedCase = null;
      updateImportTarget();
    }
    $('prepare-button').disabled = submitting || !cases.length;
    applyIntake();
  }
  function applyIntake() {
    if (!activeIntake) return;
    const caseId = activeIntake.case_id;
    for (const id of ['case-id','import-case']) {
      if (![...$(id).options].some(option=>option.value===caseId)) $(id).append(new Option(caseId,caseId));
      $(id).value=caseId;$(id).disabled=true;
    }
    $('new-case').value=caseId;$('new-case').required=false;$('new-case-label').hidden=true;
    $('import-case-hint').hidden=true;
    $('intake-panel').hidden=false;
    const waiting=activeIntake.state==='waiting_materials';
    $('prepare-heading').textContent='提交材料，继续流程';
    $('prepare-note').textContent='已关联本次 Airflow 触发';
    $('intake-state').textContent={waiting_materials:'等待提交材料',submitted:'材料已提交',cancelled:'本次等待已结束',superseded:'已合并到新流程',expired:'入口已过期'}[activeIntake.state]||activeIntake.state;
    $('intake-description').textContent=`材料案例 ${caseId} · 对应 Airflow ${activeIntake.dag_id}，本页已绑定本次触发。`;
    $('prepare-button').textContent=waiting?'提交材料并继续':'材料已提交';
    $('prepare-button').disabled=submitting||!waiting||importing||githubBusy;
    for(const id of ['target','jd','mode','choose-files','import-files','github-button','github-url','github-ref','github-contribution','clear-files'])$(id).disabled=!waiting||importing||githubBusy;
    $('import-button').disabled=!waiting||importing||!selectedFiles.length;
    $('intake-cancel').hidden=!waiting;
    $('intake-replacement').hidden=!activeIntake.replacement_url;
    if(activeIntake.replacement_url){const next=new URL(activeIntake.replacement_url,location.origin);$('intake-replacement').href=next.origin===location.origin?next.href:'/';}
  }
  async function pollIntake() {
    if (!intakeId||intakeBusy) return;
    intakeBusy=true;
    try {
      activeIntake=await api('/api/intake?intake_id='+encodeURIComponent(intakeId));
      if (!intakeInitialized) {
        $('target').value=activeIntake.defaults.target||'';$('jd').value=activeIntake.defaults.jd||'';
        $('mode').value=activeIntake.defaults.mode;
        $('mode').dispatchEvent(new Event('change'));
        await api('/api/intake-opened',{method:'POST',body:JSON.stringify({intake_id:intakeId})});
        intakeInitialized=true;
      }
      applyIntake();
      if(activeIntake.child&&!activeRun&&!intakeChildObserved) {
        intakeChildObserved=true;
        activeRun={dag_id:'resume_prepare',dag_run_id:activeIntake.child_run_id};
        sessionStorage.setItem(runKey,JSON.stringify(activeRun));
        showRun({...activeIntake.child,preparation:undefined});
      }
    } catch(error){message('submit-status',shortError(error),true);}
    finally{intakeBusy=false;}
  }
  function renderDrafts(runs) {
    const list = document.createDocumentFragment();
    for (const run of runs) {
      const row = element('li', 'draft');
      const main = element('div', 'draft-main');
      main.append(element('h3', 'draft-title', run.target || '未填写目标岗位'));
      const meta = element('div', 'draft-meta');
      meta.append(badge(run.state));
      if (run.synthetic) meta.append(element('span', 'synthetic', '虚构样例'));
      if(run.case_id)meta.append(element('span','draft-case',run.case_id));
      if(run.updated_at)meta.append(element('span','',new Date(run.updated_at*1000).toLocaleString('zh-CN',{month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit'})));
      const pending = run.pending_groups ?? (Array.isArray(run.pending_questions) ? run.pending_questions.length : Number(run.pending_questions) || 0);
      if (pending > 0) meta.append(element('span', '', `${pending} 项待确认`));
      if (run.export_key) meta.append(element('span', '', '已有导出文件'));
      main.append(meta);
      if (run.error) main.append(element('p', 'draft-error', shortError(run.error)));
      row.append(main);
      const actions=element('div','draft-actions');
      if (run.review_url || run.run_key) {
        const link = element('a', 'draft-link', '进入审阅 →');
        link.href = reviewUrl(run.review_url, run.run_key, run.workflow?.dag_run_id);
        actions.append(link);
      }
      const remove=element('button','draft-delete','删除');remove.type='button';
      remove.setAttribute('aria-label','删除草稿 '+(run.target||'未填写目标岗位'));
      remove.addEventListener('click',()=>draftAction('delete',run.run_key,remove));actions.append(remove);row.append(actions);
      list.append(row);
    }
    $('draft-list').replaceChildren(list);
    $('draft-count').textContent = String(runs.length);
    $('empty-drafts').hidden = Boolean(runs.length);
  }
  async function draftAction(action,key,button) {
    button.disabled=true;
    message('draft-action-status',action==='delete'?'正在删除草稿并结束关联的等待运行…':'正在恢复草稿…');
    try {
      await api('/api/draft-'+action,{method:'POST',body:JSON.stringify({run_key:key})});
      message('draft-action-status',action==='delete'?'草稿已删除，可在下方恢复。关联的等待运行已结束。':'草稿已恢复，可重新审阅并确认生成。');
    }catch(error){message('draft-action-status',shortError(error),true);}
    finally{await loadJobs();button.disabled=false;}
  }
  function renderTrash(records) {
    $('draft-trash').hidden=!records.length;$('trash-count').textContent=records.length?`（${records.length}）`:'';
    $('trash-list').replaceChildren(...records.map(record=>{
      const row=element('li','draft'),main=element('div','draft-main');
      main.append(element('h3','draft-title',record.target||record.case_id||'已删除草稿'));
      if(record.state==='pending')main.append(element('p','hint','部分工作流尚未结束，可重试删除或恢复。'));
      const actions=element('div','draft-actions'),restore=element('button','quiet-button','恢复');restore.type='button';
      restore.addEventListener('click',()=>draftAction('restore',record.run_key,restore));actions.append(restore);
      if(record.state==='pending') {const retry=element('button','quiet-button','重试结束运行');retry.type='button';retry.addEventListener('click',()=>draftAction('delete',record.run_key,retry));actions.append(retry);}
      row.append(main,actions);return row;
    }));
  }
  async function loadJobs() {
    if (jobsBusy) return;
    jobsBusy = true;
    $('refresh').disabled = true;
    try {
      const data = await api('/api/jobs');
      if (!Array.isArray(data.cases) || !Array.isArray(data.runs)) throw new Error('案例或草稿列表暂时无法读取，请重试。');
      setCases(data.cases);
      $('guide-status').textContent=data.browser_guide_connected?' · 自动弹窗已连接':' · 自动弹窗引导未连接';
      renderDrafts(data.runs);
      renderTrash(data.deleted_drafts||[]);
      const pending=(data.intakes||[]).filter(item=>item.id!==intakeId);
      $('pending-inputs').hidden=!pending.length;
      $('pending-input-list').replaceChildren(...pending.map(item=>{
        const row=element('li','draft'),link=element('a','draft-link','填写材料 →');
        row.append(element('span','',`材料案例 ${item.case_id}`));link.href=item.url;
        const actions=element('div','draft-actions'),cancel=element('button','quiet-button','结束等待');cancel.type='button';cancel.setAttribute('aria-label','结束材料等待 '+item.case_id);
        cancel.addEventListener('click',()=>stopIntake(item.id,cancel));actions.append(link,cancel);row.append(actions);return row;
      }));
      message('jobs-status', '');
    } catch (error) { message('jobs-status', `列表更新失败：${shortError(error)}`, true); }
    finally { jobsBusy = false; $('refresh').disabled = false; }
  }
  function safeAirflowUrl(value) {
    try {
      const url = new URL(value, 'http://localhost:8080');
      if (['http:', 'https:'].includes(url.protocol) && ['localhost', '127.0.0.1', '[::1]'].includes(url.hostname)) return url.href;
    } catch (_) { /* Keep the known local destination. */ }
    return 'http://localhost:8080';
  }
  function reviewUrl(value, key, dagRunId) {
    if (value) {
      try {
        const url = new URL(value, location.origin);
        if (url.origin === location.origin) return url.href;
      } catch (_) { /* Fall back to the known review route. */ }
    }
    const query = new URLSearchParams();
    if (key) query.set('run_key', key);
    if (dagRunId) query.set('dag_run_id', dagRunId);
    return '/review?' + query;
  }
  function showRun(data) {
    $('active-section').hidden = false;
    const tasks = Array.isArray(data.tasks) ? data.tasks : Array.isArray(data.steps) ? data.steps : [];
    const waitingReview = tasks.some(task => task.task_id === 'await_review' && ['up_for_reschedule', 'deferred', 'running', 'scheduled'].includes(task.state));
    const state = waitingReview ? 'awaiting_review' : data.state;
    $('active-state').replaceWith(Object.assign(badge(state), { id: 'active-state' }));
    $('active-heading').textContent = waitingReview ? '等待人工审阅' : state === 'failed' ? '材料整理未完成' : state === 'success' ? '流程已完成' : '流程正在执行';
    $('active-description').textContent = waitingReview ? '草稿已准备好，请进入审阅，核对后确认继续生成 Word / PDF。当前 Airflow 流程会等待你的确认。' : state === 'success' ? '可进入审阅页查看草稿与生成的文件。' : state === 'failed' ? '本次流程未完成，可查看运行详情后重新开始。' : '任务已交给 Airflow。你可以留在此页查看进度，或稍后回来。';
    $('task-list').replaceChildren(...tasks.map((task, index) => {
      const row = element('li');
      const dot = element('span', 'task-dot');
      dot.classList.add(['success', 'failed', 'running'].includes(task.state) ? task.state : 'pending');
      dot.setAttribute('aria-hidden', 'true');
      const taskState = task.task_id === 'await_review' && waitingReview ? '等待人工审阅' : stateLabels[task.state] || '等待执行';
      row.append(dot, element('span', '', taskLabels[task.task_id] || `流程步骤 ${index + 1}`), element('span', 'task-status', taskState));
      return row;
    }));
    const failed = tasks.find(task => ['failed', 'upstream_failed'].includes(task.state));
    $('active-error').hidden = state !== 'failed' && !data.error;
    $('active-error').textContent = shortError(data.error || (failed ? '有整理步骤失败，请在 Airflow 查看原因后重试。' : '整理失败，请在 Airflow 查看运行详情。'));
    const preparation = data.preparation || {};
    $('active-review').hidden = !preparation.review_url && !preparation.run_key;
    if (!$('active-review').hidden) $('active-review').href = reviewUrl(preparation.review_url, preparation.run_key, data.dag_run_id || activeRun?.dag_run_id);
    if (preparation.skip) $('active-description').textContent = '材料未发生变化，已找到可继续审阅的草稿。';
    $('active-airflow').href = safeAirflowUrl(data.url || 'http://localhost:8080');
  }
  async function pollRun() {
    if (!activeRun || runBusy) return;
    const polledRun = activeRun;
    runBusy = true;
    try {
      const data = await api(`/api/run?dag_id=${encodeURIComponent(polledRun.dag_id || 'resume_prepare')}&dag_run_id=${encodeURIComponent(polledRun.dag_run_id)}`);
      if (activeRun !== polledRun) return;
      showRun(data);
      if (['success', 'failed'].includes(data.state)) {
        activeRun = null;
        sessionStorage.removeItem(runKey);
        await loadJobs();
      }
    } catch (error) {
      if (activeRun !== polledRun) return;
      $('active-section').hidden = false;
      $('active-error').hidden = false;
      $('active-error').textContent = `运行状态更新失败：${shortError(error)} 页面会继续重试。`;
    } finally { runBusy = false; }
  }
  $('mode').addEventListener('change', () => {
    $('mode-note').textContent = $('mode').value === 'offline'
      ? '离线演示使用固定规则生成虚构样例，不调用模型，仅用于体验工作流，请勿作为真实经历投递。'
      : 'DeepSeek 会接收材料中提取的文字，整理事实并起草正文。请先确认材料适合发送。';
  });
  $('refresh').addEventListener('click', loadJobs);
  function updateImportTarget() {
    const isNew = !$('import-case').value;
    $('new-case-label').hidden = !isNew;
    $('new-case').required = isNew;
    importRequestId = null;
    githubRequestId = null;
  }
  function renderSelectedFiles() {
    $('selected-files').replaceChildren(...selectedFiles.map(file => element('li', '', `${file.name} · ${(file.size / 1024).toFixed(1)} KB`)));
    $('import-button').disabled = importing || !selectedFiles.length;
    $('clear-files').hidden = !selectedFiles.length;
  }
  function addFiles(files) {
    if (importing || (activeIntake && activeIntake.state!=='waiting_materials')) return;
    const next = [...selectedFiles, ...files];
    if (next.length > 100) throw new Error('每次最多导入 100 个文件，请清空后重新选择。');
    for (const file of next) {
      if (file.webkitRelativePath || !/\.(txt|md|docx|pdf|png|jpe?g)$/i.test(file.name)) throw new Error(`不支持 ${file.name}，请选择 TXT、Markdown、DOCX、PDF 或图片文件。`);
      if (file.size > 5 * 1024 * 1024) throw new Error(`${file.name} 超过单文件 5 MB 限制。`);
    }
    if (next.reduce((sum, file) => sum + file.size, 0) > 20 * 1024 * 1024) throw new Error('所选文件总大小超过 20 MB，请分批导入。');
    selectedFiles = next;
    importRequestId = null;
    message('import-status', `已选择 ${next.length} 个文件，点击“导入到本机”完成保存。`);
    $('import-results').replaceChildren();
    renderSelectedFiles();
  }
  function fileBase64(file) {
    return new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(reader.result.slice(reader.result.indexOf(',') + 1));
      reader.onerror = () => reject(new Error(`无法读取 ${file.name}，请重新选择。`));
      reader.readAsDataURL(file);
    });
  }
  $('import-case').addEventListener('change', updateImportTarget);
  $('new-case').addEventListener('input', () => { importRequestId = null; githubRequestId = null; });
  $('choose-files').addEventListener('click', () => $('import-files').click());
  $('import-files').addEventListener('change', event => {
    try { addFiles(Array.from(event.target.files)); } catch (error) { message('import-status', shortError(error), true); }
    event.target.value = '';
  });
  $('clear-files').addEventListener('click', () => {
    selectedFiles = [];
    importRequestId = null;
    renderSelectedFiles();
    message('import-status', '');
  });
  for (const eventName of ['dragenter', 'dragover']) $('drop-zone').addEventListener(eventName, event => {
    event.preventDefault();
    if (!importing) $('drop-zone').classList.add('dragging');
  });
  $('drop-zone').addEventListener('dragleave', event => {
    if (!$('drop-zone').contains(event.relatedTarget)) $('drop-zone').classList.remove('dragging');
  });
  $('drop-zone').addEventListener('drop', event => {
    event.preventDefault();
    $('drop-zone').classList.remove('dragging');
    try {
      const items = Array.from(event.dataTransfer.items || []);
      if (items.some(item => item.webkitGetAsEntry?.()?.isDirectory)) throw new Error('请选择文件，目录无法导入。');
      const files = Array.from(event.dataTransfer.files);
      if (!files.length) throw new Error('未检测到可导入的文件。');
      addFiles(files);
    } catch (error) { message('import-status', shortError(error), true); }
  });
  // Prevent a misplaced file drop from navigating away from the workbench.
  for (const eventName of ['dragover', 'drop']) document.addEventListener(eventName, event => {
    if (Array.from(event.dataTransfer?.types || []).includes('Files')) event.preventDefault();
  });
  $('import-form').addEventListener('submit', async event => {
    event.preventDefault();
    if (importing || !selectedFiles.length || !$('import-form').reportValidity()) return;
    const caseId = $('import-case').value || $('new-case').value;
    if (!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(caseId)) {
      message('import-status', '案例名称需以英文字母或数字开头，使用 1–80 位英文字母、数字、下划线和连字符。', true);
      return;
    }
    importing = true;
    const controls = ['import-case', 'new-case', 'choose-files', 'clear-files', 'import-files'];
    controls.forEach(id => { $(id).disabled = true; });
    renderSelectedFiles();
    $('import-button').textContent = '正在导入…';
    message('import-status', '正在读取并保存到本机…');
    try {
      const files = await Promise.all(selectedFiles.map(async file => ({ name: file.name, content_base64: await fileBase64(file) })));
      importRequestId ||= crypto.randomUUID();
      const result = await api('/api/import', { method: 'POST', body: JSON.stringify({ case_id: caseId, request_id: importRequestId, files }) });
      const actions = { added: '已添加', unchanged: '内容相同，已跳过', updated: '已更新并备份', renamed: '已另存新名' };
      $('import-results').replaceChildren(...result.files.map(file => element('li', '', `${file.name} · ${actions[file.action] || file.action}${file.stored_name && file.stored_name !== file.name ? ' → ' + file.stored_name : ''}`)));
      message('import-status', `已导入案例 ${result.case_id}。保存位置 ${result.directory}。现在可以填写目标岗位并开始整理。`);
      importedCase = result.case_id;
      selectedFiles = [];
      importRequestId = null;
      await loadJobs();
    } catch (error) { message('import-status', `导入失败：${shortError(error)} 可直接重试。`, true); }
    finally {
      importing = false;
      controls.forEach(id => { $(id).disabled = false; });
      $('import-button').textContent = '导入到本机';
      renderSelectedFiles();
      applyIntake();
    }
  });
  let githubBusy=false, githubRequestId=null;
  $('github-form').addEventListener('input',()=>{githubRequestId=null;});
  $('github-form').addEventListener('submit',async event=>{
    event.preventDefault();
    if(githubBusy||!$('github-form').reportValidity())return;
    const caseId=$('import-case').value||$('new-case').value.trim();
    if(!/^[A-Za-z0-9][A-Za-z0-9_-]{0,79}$/.test(caseId)) {
      message('github-status','请先在上方选择材料案例，或填写有效的新案例文件夹名。',true);return;
    }
    const url=$('github-url').value.trim();
    if(!/^https:\/\/github\.com\/[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+\/?$/.test(url)) {
      message('github-status','请填写完整仓库链接，例如 https://github.com/owner/repo。',true);return;
    }
    githubBusy=true;$('github-button').disabled=true;
    const controls=['github-url','github-ref','github-contribution','import-case','new-case'];
    const disabled=controls.map(id=>[$(id),$(id).disabled]);disabled.forEach(([control])=>{control.disabled=true;});
    message('github-status','正在从 GitHub 读取项目并保存来源快照…');
    try {
      githubRequestId||=crypto.randomUUID();
      const result=await api('/api/github',{method:'POST',body:JSON.stringify({case_id:caseId,url,ref:$('github-ref').value.trim(),contribution:$('github-contribution').value.trim(),request_id:githubRequestId})});
      $('github-results').replaceChildren(...(result.files||[]).map(file=>element('li','',typeof file==='string'?file:(file.name||file.stored_name||''))),...(result.issues||[]).map(issue=>element('li','',typeof issue==='string'?issue:JSON.stringify(issue))));
      message('github-status',`已导入案例 ${result.case_id}。commit ${result.commit||'见来源快照'}。保存位置 ${result.directory||'本机案例目录'}。请核实本人贡献后开始整理。`);
      importedCase=result.case_id;githubRequestId=null;await loadJobs();
    }catch(error){message('github-status',`GitHub 导入失败：${shortError(error)} 请检查链接、分支及仓库访问权限后重试。`,true);}
    finally{githubBusy=false;$('github-button').disabled=false;disabled.forEach(([control,wasDisabled])=>{control.disabled=wasDisabled;});applyIntake();}
  });
  form.addEventListener('submit', async event => {
    event.preventDefault();
    if (submitting || !form.reportValidity()) return;
    const target = $('target').value.trim();
    submitting = true;
    $('prepare-button').disabled = true;
    $('prepare-button').textContent = '正在提交…';
    message('submit-status', '正在提交材料整理任务…');
    try {
      if(intakeId) {
        activeIntake=await api('/api/intake-submit',{method:'POST',body:JSON.stringify({intake_id:intakeId,target,jd:$('jd').value,mode:$('mode').value})});
        applyIntake();
        message('submit-status','材料已提交，Airflow 的等待步骤会自动通过并继续整理。');
        return;
      }
      const data = await api('/api/prepare', {
        method: 'POST',
        body: JSON.stringify({ case_id: $('case-id').value, target, jd:$('jd').value, mode: $('mode').value, request_id: crypto.randomUUID() })
      });
      if (!data.dag_run_id) throw new Error('未收到运行记录，请查看 Airflow 后再试。');
      activeRun = { dag_run_id: data.dag_run_id, dag_id: data.dag_id || 'resume_prepare' };
      sessionStorage.setItem(runKey, JSON.stringify(activeRun));
      message('submit-status', '已提交，准备完成后即可进入人工审阅。');
      showRun({ state: data.state || 'queued', tasks: [] });
      await pollRun();
    } catch (error) { message('submit-status', `提交失败：${shortError(error)}`, true); }
    finally {
      submitting = false;
      $('prepare-button').disabled = !cases.length;
      $('prepare-button').textContent = '开始整理 ↗';
      applyIntake();
    }
  });
  async function init() {
    try { await getSession(); } catch (error) { message('jobs-status', shortError(error), true); }
    await pollIntake();
    await Promise.all([loadJobs(), pollRun()]);
    setInterval(() => { if (!document.hidden) { void loadJobs(); void pollIntake(); void pollRun(); } }, 2500);
  }
  async function stopIntake(id,button) {
    button.disabled=true;
    try{await api('/api/intake-cancel',{method:'POST',body:JSON.stringify({intake_id:id})});await loadJobs();await pollIntake();}
    catch(error){message('submit-status',shortError(error),true);}
    finally{button.disabled=false;}
  }
  $('intake-cancel').addEventListener('click',()=>stopIntake(intakeId,$('intake-cancel')));
  void init();
})();
