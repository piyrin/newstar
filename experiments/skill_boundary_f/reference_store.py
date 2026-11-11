"""Exact, typed references for persisted outputs; filenames are never aliases."""
import hashlib
import copy
from pathlib import Path


def model_reference(ref):
    """F model view: stable locators; preserve physical storage and full bodies."""
    if ref.get('artifact')==ref.get('content'):
        result=copy.deepcopy({k:v for k,v in ref.items() if k!='artifact'})
    else:
        result=copy.deepcopy(ref)
    ident=result.get('reference_id')
    if ident:
        for key in ['path','document_path']:
            if key in result:result[key]='artifact://'+ident
    for asset in result.get('files',[]):
        if asset.get('reference_id'):asset['path']='artifact://'+asset['reference_id']
    return result


def model_feedback(feedback, references):
    """Only storage-location metadata changes; error values and quotes stay exact."""
    locators={}
    for ref in references:
        ident=ref.get('reference_id')
        if ident:
            for key in ['path','document_path']:
                if ref.get(key):locators[str(ref[key])]='artifact://'+ident
        for asset in ref.get('files',[]):
            if asset.get('reference_id'):
                locators[str(asset['path'])]='artifact://'+asset['reference_id']
    def view(value):
        if isinstance(value,dict):
            return {key:(locators[item] if key in {'path','document_path'}
                    and isinstance(item,str) and item in locators else view(item))
                    for key,item in value.items()}
        if isinstance(value,list):return [view(item) for item in value]
        return copy.deepcopy(value)
    return view(feedback)


class ReferenceStore:
    def __init__(self):
        self._refs = {}

    def ids(self):
        return list(self._refs)

    def register(self, node_id, skill, doc_path, body, files, depth):
        doc_path = Path(doc_path)
        if doc_path.read_text(encoding='utf-8') != body:
            raise ValueError('document does not match persisted output')
        for file in files:
            actual = hashlib.sha256(Path(file['path']).read_bytes()).hexdigest()
            if actual != file['sha256']:
                raise ValueError('attachment digest mismatch')
        common = {'producer_node_id': node_id, 'skill': skill, 'depth': depth}
        number = node_id.removeprefix('STEP-')
        attachments = []
        refs = []
        for i, file in enumerate(files, 1):
            ident = f'FILE-{number}-{i:02}'
            asset = {**file, 'reference_id': ident}
            attachments.append(asset)
            content = Path(file['path']).read_text(encoding='utf-8-sig')
            refs.append({**common, 'reference_id': ident, 'kind': 'file',
                         'path': file['path'], 'content': content, 'artifact': content,
                         'files': [asset]})
        ident = f'DOC-{number}'
        document = {**common, 'reference_id': ident, 'kind': 'document',
                    'path': str(doc_path), 'document_path': str(doc_path),
                    'content': body, 'artifact': body, 'files': attachments}
        outputs = [document] + refs
        if any(r['reference_id'] in self._refs for r in outputs):
            raise ValueError('duplicate output reference')
        self._refs.update({r['reference_id']: r for r in outputs})
        return {'producer_node_id': node_id, 'outputs': outputs}

    def resolve(self, ids):
        if not isinstance(ids, list) or any(not isinstance(i,str) or i not in self._refs for i in ids):
            raise ValueError('unknown reference; use exact returned reference_id')
        return [self._refs[i] for i in ids]

    def producers(self, ids):
        return list(dict.fromkeys(r['producer_node_id'] for r in self.resolve(ids)))

    def select(self, manifest):
        if not isinstance(manifest,dict):
            raise ValueError('manifest must be a JSON object')
        if not isinstance(manifest.get('deliverables'),list):
            raise ValueError('deliverables must be a JSON array of objects, not a JSON-encoded string')
        selected = {}
        for item in manifest.get('deliverables', []):
            if not isinstance(item,dict):
                raise ValueError('each deliverable must be a JSON object with reference_ids')
            refs = item.get('reference_ids')
            if not isinstance(refs, list) or not refs:
                raise ValueError('empty final reference list')
            for ref in self.resolve(refs):
                selected[ref['reference_id']] = ref
        if not selected:
            raise ValueError('no actual final outputs')
        return selected
