"""Normalize an optional review photo locally and bind it to the review version."""
import base64
import io
from PIL import Image, ImageOps

from .materials import atomic_bytes
from .review import current_state
from .storage import read_json, review_dir, write_json


def save_photo(workspace, run_key, payload):
    state = current_state(workspace, run_key)
    if payload.get('revision') != state['revision']:
        raise ValueError('审阅内容已在其他页面更新，请刷新后再上传照片')
    folder = review_dir(workspace, run_key)
    resume = read_json(folder / 'resume.json')
    if payload.get('remove') is True:
        resume.pop('photo', None)
    else:
        encoded = payload.get('content_base64')
        if not isinstance(encoded, str) or len(encoded) > 2_666_668:
            raise ValueError('照片最多2MB，请选择PNG或JPG')
        try:
            content = base64.b64decode(encoded, validate=True)
            if len(content) > 2_000_000:
                raise ValueError('照片最多2MB')
            with Image.open(io.BytesIO(content)) as image:
                if image.format not in ('PNG', 'JPEG') or image.width * image.height > 10_000_000:
                    raise ValueError('照片需为PNG/JPG，且不超过1000万像素')
                normalized = ImageOps.exif_transpose(image).convert('RGB')
                normalized.thumbnail((1200, 1600))
                output = io.BytesIO()
                normalized.save(output, format='JPEG', quality=90)
        except (OSError, ValueError, Image.DecompressionBombError) as error:
            raise ValueError(str(error) if isinstance(error, ValueError) else '照片无法读取，请选择有效PNG或JPG') from None
        atomic_bytes(folder / 'photo.jpg', output.getvalue())
        resume['photo'] = 'photo.jpg'
    write_json(folder / 'resume.json', resume)
    return current_state(workspace, run_key)
