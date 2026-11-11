"""Lossless artifact storage, compact planner receipts, explicit full reads."""
import hashlib
from reference_store import model_reference


def receipt_result(result):
    outputs=[]
    for stored_ref in result['outputs']:
        ref=model_reference(stored_ref)
        content=ref['content']
        outputs.append({k:v for k,v in ref.items() if k not in {'content','artifact'}} | {
            'content_characters':len(content),'content_sha256':hashlib.sha256(content.encode('utf-8')).hexdigest(),
            'body_access':'read_artifacts returns the complete stored body; downstream Skill artifact_ids always resolve to complete content'})
    return {**result,'outputs':outputs,'planner_view':'receipts; bodies unchanged on disk'}
