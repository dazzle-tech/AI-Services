"""Pack the CC0 'Human Muscles' GLB (Grab3D, light version) into a compact file
that opens from file:// as a plain <script>.

    python tools/pack_body.py prototype/models/muscles-light.glb prototype/models/body-muscles.js

Layout of the gzip'd binary (little endian):
    u32 headerLength | JSON header (padded to 4) | int16 xyz * N | int8 xyz * N (pad to 4)
    | uint8 tone * N (pad to 4) | uint32 indices
The JSON header holds counts and the bounding box used to dequantise positions.
`tone` is the base-colour luminance sampled per vertex, which keeps the muscle
fibre and tendon pattern for shading.
"""
import base64
import gzip
import io
import json
import struct
import sys

import numpy as np
from PIL import Image

src, dst = sys.argv[1], sys.argv[2]
b = open(src, 'rb').read()
cl, _ = struct.unpack('<II', b[12:20])
j = json.loads(b[20:20 + cl])
off = 20 + cl
bl, _ = struct.unpack('<II', b[off:off + 8])
bin_ = b[off + 8: off + 8 + bl]


def accessor(i):
    a = j['accessors'][i]
    bv = j['bufferViews'][a['bufferView']]
    start = bv.get('byteOffset', 0) + a.get('byteOffset', 0)
    comps = {'SCALAR': 1, 'VEC2': 2, 'VEC3': 3}[a['type']]
    dt = {5126: '<f4', 5125: '<u4', 5123: '<u2'}[a['componentType']]
    arr = np.frombuffer(bin_, dtype=dt, count=a['count'] * comps, offset=start)
    return arr.reshape(-1, comps) if comps > 1 else arr


prim = j['meshes'][0]['primitives'][0]
pos = accessor(prim['attributes']['POSITION']).astype(np.float64)
nrm = accessor(prim['attributes']['NORMAL']).astype(np.float64)
uv = accessor(prim['attributes']['TEXCOORD_0']).astype(np.float64)
idx = accessor(prim['indices']).astype(np.uint32)
n = len(pos)

bv = j['bufferViews'][j['images'][0]['bufferView']]
img = Image.open(io.BytesIO(bin_[bv.get('byteOffset', 0): bv.get('byteOffset', 0) + bv['byteLength']])).convert('L')
tex = np.asarray(img, dtype=np.float64)
h, w = tex.shape
u = np.clip(uv[:, 0] % 1.0, 0, 1) * (w - 1)
v = np.clip(uv[:, 1] % 1.0, 0, 1) * (h - 1)  # glTF uv origin is top-left, same as the array
x0, y0 = np.floor(u).astype(int), np.floor(v).astype(int)
x1, y1 = np.minimum(x0 + 1, w - 1), np.minimum(y0 + 1, h - 1)
fx, fy = u - x0, v - y0
lum = (tex[y0, x0] * (1 - fx) * (1 - fy) + tex[y0, x1] * fx * (1 - fy)
       + tex[y1, x0] * (1 - fx) * fy + tex[y1, x1] * fx * fy)
lo, hi = np.percentile(lum, [1, 99])
tone = np.clip((lum - lo) / (hi - lo), 0, 1)
tone = (tone * 255).round().astype(np.uint8)

mn, mx = pos.min(axis=0), pos.max(axis=0)
q = np.round((pos - mn) / (mx - mn) * 65535).astype(np.int64) - 32768
q = q.astype(np.int16)
nq = np.clip(np.round(nrm * 127), -127, 127).astype(np.int8)

head = json.dumps({'count': int(n), 'index': int(len(idx)), 'min': mn.tolist(), 'max': mx.tolist()}).encode()
head += b' ' * ((4 - len(head) % 4) % 4)


def pad4(buf):
    return buf + b'\0' * ((4 - len(buf) % 4) % 4)


blob = struct.pack('<I', len(head)) + head
blob += pad4(q.tobytes()) + pad4(nq.tobytes()) + pad4(tone.tobytes()) + idx.astype('<u4').tobytes()
gz = gzip.compress(blob, 9)
b64 = base64.b64encode(gz).decode()
with open(dst, 'w', encoding='ascii') as f:
    f.write('/* Human Muscles, Grab3D, CC0 1.0 (public domain). Packed by tools/pack_body.py. */\n')
    f.write('window.PERSPECTIVE_BODY_B64="' + b64 + '";\n')
print('vertices', n, 'indices', len(idx), 'raw', len(blob), 'gzip', len(gz), 'js', len(b64))
