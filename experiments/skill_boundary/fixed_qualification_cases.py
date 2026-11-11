"""Predeclared fictional smoke cases. Never alter the main CourseDock benchmark."""
from runner import BASE,REPO,read,save
from local_qualification import validate_case
from pathlib import Path


def cases():
    out={}
    def add(name,request,facts,checks,quote,required=()):
        out[name]={'eligible':True,'request':request,'facts':facts,'checks':checks,
            'scope':'original inline local text/code capability; one fictional functional smoke test',
            'boundary':'Use only supplied fictional inputs. No network, publishing or claim of execution; unknowns stay unknown.',
            'source_quote':quote,'required_literals':list(required)}
    add('avoid-ai-writing','Audit and rewrite the supplied paragraph in plain English. Preserve its measured values and uncertainty. Include issues, rewrite, changes and second-pass audit; under180 words.',
        {'paragraph':'We leverage a robust cache. In a synthetic run of20 requests,12 were cache hits. This may reduce repeated work; production latency has not been measured.'},
        ['Rewrite retains20 requests,12 hits and the synthetic scope.','Keeps uncertainty and unmeasured production latency, no invented improvement.','Identifies vague wording, rewrites plainly and performs a second pass.'],
        'Preserve factual claims, uncertainty, attributed quotations, code, identifiers, and the requested scope.', ['20','12'])
    add('better-writing','Review only the supplied interface copy. Return a before/after findings table with file:line and a short verification statement. Keep the established word Archive. Do not claim browser checks. Under180 words.',
        {'product_voice':'plain, calm','strings':[{'location':'locales/en.json:1','text':'Archive project'},{'location':'locales/en.json:2','text':'Oopsie! We messed up archiving. Just chill.'},{'location':'locales/en.json:3','text':'Retry archive'}],'behavior':'Archiving failed. The project remains available; Retry archive is an existing action.'},
        ['Flags the error tone and offers a calm actionable replacement.','Uses Archive/archive consistently with the given vocabulary.','Identifies inspected locations and leaves visual/accessibility verification unverified.'],
        'Errors say how to fix, next to where it broke', ['locales/en.json:2','archive'])
    add('clean-code','Refactor this supplied Python function using meaningful names. Rename the public function to double_positive as requested. Preserve order/duplicates and exclusion of zero/negative inputs. Include3 unittest cases for empty, mixed and repeated inputs. Do not claim tests ran.',
        {'code':'def f(xs):\n    r=[]\n    for x in xs:\n        if x>0:\n            r.append(x*2)\n    return r\n','inputs':[[],[-1,0,2],[2,2]],'runtime':'Python3, standard library only'},
        ['Runnable double_positive function preserves the original selection/multiplication.','Empty and duplicate-positive cases are handled.','Provides real assertions and does not claim execution.'],
        'Use Intention-Revealing Names', ['double_positive','unittest'])
    add('code-review-excellence','Review the supplied change against its contract. Give actionable severity-ranked findings and missing test cases, under180 words. Do not implement changes or claim tests ran.',
        {'file':'stats.py','code':'def mean(values):\n    return sum(values)/len(values)\n','contract':'For nonempty lists return arithmetic mean; for[] raise ValueError. No tests supplied.'},
        ['Identifies actual ZeroDivisionError for[] conflicting with ValueError contract.','Gives actionable review feedback with severity and rationale.','Requests empty/nonempty tests without inventing execution evidence.'],
        'Provide actionable feedback with severity and rationale.', ['ValueError','ZeroDivisionError'])
    add('code-documentation-code-explain','Explain the supplied Python function statically for a beginner. Show each supplied input and its result, explain the filter and empty case. Under150 words; do not run or claim timing measurements.',
        {'code':'def total_positive(values):\n    return sum(v for v in values if v>0)\n','inputs':[[],[-2,0,5],[1,3,-7]]},
        ['Explains the filter retaining only strictly positive values.','Correct results for the three inputs are0,5,4.','Explains empty sum and does not claim runtime or measured performance.'],
        'Explain code statically unless separate execution is authorized in an isolated environment.', ['0','5','4'])
    add('documentation-templates','Draft a compact README for the supplied fictional project, using only its facts. Include Quick Start, features, configuration and license. Unknown license must stay unknown. Under180 words.',
        {'name':'NoteCount','purpose':'Count lines in a local text file','quickstart':'python -m notecount sample.txt','configuration':'No configuration variables are specified.','license':None,'repo_url':None},
        ['Uses the exact supplied command and only the line-counting capability.','States license unknown rather than assuming MIT.','Does not invent repo links, defaults or configuration variables.'],
        'Replace illustrative paths, commands, dates and defaults with verified project facts.', ['python -m notecount sample.txt','unknown'])
    add('plan-writing','Produce a short plan, at most6 tasks, to fix the supplied clamp bug and update its existing tests. Name the affected files, dependency order and verification command. No implementation or claim of completed changes.',
        {'files':{'src/score.py':'def clamp(n):\n    return min(n,100)\n','tests/test_score.py':'import unittest\nfrom src.score import clamp\n# existing suite covers clamp(50)==50\n'},'desired':'Clamp integers to inclusive range0..100. Preserve50. Add boundary tests for-1,0,100,101.','verification':'python -m unittest discover -s tests'},
        ['Plans the lower-bound fix while preserving the upper bound and existing behavior.','Names both files and test-before/fix/verification dependencies.','Uses the given verification command without claiming it ran.'],
        'Each task should have a clear, verifiable outcome.', ['src/score.py','tests/test_score.py','python -m unittest discover -s tests'])
    add('openapi-spec-generation','Generate a complete small OpenAPI3.1.0 specification as JSON for the supplied API. Only the specified route; no invented authentication or server URLs. The200 object must require boolean ok. Include info.title and info.version.',
        {'title':'Local Ping API','version':'0.1.0','route':'GET /ping','response_status':'200','response_body_schema':{'type':'object','properties':{'ok':{'type':'boolean'}},'required':['ok']}},
        ['Parseable OpenAPI3.1.0 JSON with info and only GET/ping.','200 application/json response requires boolean ok.','No invented auth, endpoints or server URLs.'],
        'OpenAPI 3.1 specifications', ['3.1.0','/ping','ok'])
    add('async-python-patterns','Write Python3.11 async def fetch_many(ids, fetch). Await the supplied I/O coroutine concurrently, preserve input order, return[] for empty ids and propagate errors. Input has at most3 IDs; fetch handles its own timeout. Use stdlib only, no actual network or execution claims.',
        {'example_ids':[1,2,3],'fetch_contract':'async callable: returns id*2 after a variable awaitable delay; may raise ValueError; owns its timeout.','bound':3},
        ['Uses concurrent awaitables rather than sequential await in the iteration.','Preserves input order and handles empty input.','Uses only stdlib and propagates fetch errors without fake execution claims.'],
        'Pick concurrency patterns (tasks, gather, queues, pools) with cancellation rules.', ['fetch_many','asyncio'])
    add('requirements-writing','Write3 atomic EARS requirements in English from the facts: use When for the two events and If/Then for no records. Keep names/messages exact; no extra thresholds or UI features. Under120 words.',
        {'system':'ExportTool','rules':[{'trigger':'user selects Export with nonempty records','response':'write index.csv'},{'trigger':'export completes','response':'display Export complete'},{'condition':'there are no records','response':'display No records'}]},
        ['Three single-response requirements with the exact supplied behavior.','Event statements use When/system/shall and the no-record case uses If/Then.','No invented thresholds, additional behaviors or silently changed messages.'],
        'When `<trigger>`, the `<system>` shall `<response>`.', ['When','shall','If','index.csv','Export complete','No records'])
    add('postmortem-writing','Draft a concise English blameless postmortem from the three fictional log events. Separate deployment, detection and recovery. State root cause and data-loss status unknown. Suggestions must be labelled proposed, not completed. Under200 words.',
        {'timezone':'UTC','events':[{'time':'10:00','event':'deployment v0.2 completes'},{'time':'10:05','event':'error-rate alert detects10% errors'},{'time':'10:20','event':'rollback completes; error rate returns to baseline'}],'impact_start':None,'root_cause':None,'affected_users':None,'data_loss_status':None},
        ['Timeline preserves the three exact timestamps and event types.','Computes15 minutes from detection to recovery without claiming a known outage start.','Unknown root cause/data loss stay unknown; proposed follow-up is not claimed completed.'],
        'distinguish deployment time, impact start, detection and recovery.', ['10:00','10:05','10:20','unknown'])
    add('code-review-checklist','Perform a scoped static checklist review of the supplied function and contract. Report only actual findings and relevant missing tests. Mark unrelated security/integration areas not inspected; do not certify all checklist items. Under180 words.',
        {'file':'tags.py','code':'def unique_tags(tags):\n    return list(set(tags))\n','contract':'Return unique strings preserving the first-occurrence order.[] returns[]. No runtime tests have been supplied.'},
        ['Finds unordered set conversion violates first-occurrence ordering.','Suggests a behavior-preserving ordered deduplication and duplicate/empty tests.','Does not certify uninspected areas or claim tests ran.'],
        'Are edge cases handled?', ['set','order'])
    add('architecture-patterns','Design a small hexagonal architecture for the supplied backend. Give module/interface dependency direction, a migration outline and a validation test using a fake storage adapter. No external-service execution; under200 words.',
        {'application':'local notes backend','domain':'note naming rules must not import sqlite3','current':'domain/note_service.py directly opens SQLite; tests require a real DB.','desired':'swap storage without changing note naming logic','constraints':'one developer, no microservices, no durable external side effects'},
        ['Domain depends on an abstract port; SQLite adapter implements it without reverse domain-to-infrastructure coupling.','Composition boundary connects adapter and application; no unrequested microservice split.','Provides incremental migration and fake-adapter test verifying domain behavior.'],
        'Define module boundaries, interfaces, and dependency rules.', ['adapter','domain'])
    add('code-refactoring-refactor-clean','Refactor the supplied Python summarize function to remove duplicated filtering. Keep the public name, output keys, ordering, duplicates and KeyError on missing required keys. Include focused tests but do not claim execution; no new dependencies.',
        {'code':'def summarize(items):\n    a=[]\n    b=[]\n    for row in items:\n        if row["kind"]=="a": a.append(row["value"])\n    for row in items:\n        if row["kind"]=="b": b.append(row["value"])\n    return {"a":a,"b":b}\n','data':[{'kind':'a','value':1},{'kind':'b','value':2},{'kind':'a','value':1}],'edge_cases':'Empty list; an item missing kind; an item with kind a missing value.'},
        ['Removes duplicated filtering without changing public behavior.','Preserves duplicates/order and empty output structure.','Still raises KeyError for required missing fields; no fake run evidence.'],
        'Preserve public behavior, duplicate ordering, transactions, side-effect timing, errors and compatibility', ['summarize','KeyError'])
    return out


if __name__=='__main__':
    fixed=cases();by={r['name']:r for r in read(REPO/'tmp/skillfabri-spike/scale/registry.json')}
    original={r['name'] for r in read(BASE/'registry.json')}
    for name,case in fixed.items():
        assert name not in original and validate_case(case,Path(by[name]['path']).read_text(encoding='utf-8')),name
    save(BASE/'boundary-fixed-cases-01.json',fixed);save(BASE/'boundary-fixed-names-01.json',list(fixed))
    print('Frozen predeclared source-grounded cases',len(fixed))
