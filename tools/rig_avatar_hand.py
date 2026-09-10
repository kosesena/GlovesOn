"""Add a conservative three-joint finger rig without changing existing bone frames.
Run with Blender's Python (numpy): blender -b --python tools/rig_avatar_hand.py.
Coordinates were measured on the existing glove, in its unposed mesh space.
"""
from pathlib import Path
import json, struct
import numpy as np
root = Path(__file__).resolve().parents[1]
raw = (root / 'web/assets/avatar/worker.glb').read_bytes()
n = struct.unpack_from('<I', raw, 12)[0]
doc = json.loads(raw[20:20+n]); data = bytearray(raw[28+n:])
def read(i):
 a=doc['accessors'][i];v=doc['bufferViews'][a['bufferView']]
 dtype={5126:'<f4',5123:'<u2',5121:'u1'}[a['componentType']]
 width={'SCALAR':1,'VEC2':2,'VEC3':3,'VEC4':4,'MAT4':16}[a['type']]
 return np.frombuffer(data,dtype=dtype,count=a['count']*width,offset=v.get('byteOffset',0)+a.get('byteOffset',0)).reshape(-1,width).copy()
def append(arr,kind,component=5126):
 while len(data)%4:data.append(0)
 offset=len(data);data.extend(arr.astype({5126:'<f4',5123:'<u2'}[component]).tobytes())
 view=len(doc['bufferViews']);doc['bufferViews'].append({'buffer':0,'byteOffset':offset,'byteLength':len(data)-offset})
 index=len(doc['accessors']);doc['accessors'].append({'bufferView':view,'componentType':component,'count':len(arr),'type':kind});return index
skin=doc['skins'][0];inv=read(skin['inverseBindMatrices']).reshape(-1,4,4).transpose(0,2,1)
hand_node=next(i for i,n in enumerate(doc['nodes']) if n.get('name')=='RightHand');hand_joint=skin['joints'].index(hand_node)
hand_world=np.linalg.inv(inv[hand_joint]); rotations=hand_world[:3,:3].copy()
attrs=doc['meshes'][0]['primitives'][0]['attributes'];pos=read(attrs['POSITION']);joints=read(attrs['JOINTS_0']);weights=read(attrs['WEIGHTS_0'])
# Blender Z-up measurements -> glTF Y-up mesh coordinates.
def coord(p):return np.array([p[0],p[2],-p[1]]) / 100
specs=[('Thumb',(-34.7,-7.3,85),(-35.1,-11.1,78.5)),('Index',(-39.1,-7.1,83),(-43.1,-7.3,75)),('Middle',(-37.4,-4.8,83),(-40.8,-4.6,74)),('Ring',(-36.9,-2.4,83),(-39.5,-2.3,74.5)),('Pinky',(-36.5,0,83),(-38.3,.1,76.1))]
fingers=[]
for name,base,tip in specs:
 base,tip=coord(base),coord(tip);parent=hand_node;parent_world=hand_world;indices=[]
 for segment,fraction in enumerate([0,.43,.73]):
  world=hand_world.copy();world[:3,3]=base+(tip-base)*fraction
  local=np.linalg.inv(parent_world)@world;node=len(doc['nodes']);doc['nodes'].append({'name':f'Right{name}{segment+1}','matrix':local.T.reshape(-1).tolist()})
  doc['nodes'][parent].setdefault('children',[]).append(node);indices.append(len(skin['joints']));skin['joints'].append(node);inv=np.concatenate([inv,np.linalg.inv(world)[None]])
  parent=node;parent_world=world
 fingers.append((base,tip,indices))
changed=0
for i,p in enumerate(pos):
 matches=np.where(joints[i]==hand_joint)[0]
 if not len(matches):continue
 slot=matches[0];weight=float(weights[i,slot])
 if weight<.05:continue
 candidates=[]
 for base,tip,indices in fingers:
  axis=tip-base;t=float(np.dot(p-base,axis)/np.dot(axis,axis));nearest=base+np.clip(t,0,1)*axis
  candidates.append((float(np.linalg.norm(p-nearest)),t,indices))
 distance,t,indices=min(candidates)
 influence=np.clip(t/.22,0,1)
 if influence<=0 or distance>.032:continue
 # Preserve all other skin influences, blend the finger root into the palm.
 f=np.clip(t,0,1); segment=0 if f<.43 else 1 if f<.73 else 2
 existing={int(k):float(w) for k,w in zip(joints[i],weights[i]) if w>0};existing[hand_joint]=weight*(1-influence);existing[indices[segment]]=weight*influence
 # Blend neighbouring joints near each knuckle to avoid a hard crease.
 for boundary,k in [(.43,1),(.73,2)]:
  if abs(f-boundary)<.09:
   blend=(f-boundary+.09)/.18;existing.pop(indices[segment],None);existing[indices[k-1]]=weight*influence*(1-blend);existing[indices[k]]=weight*influence*blend
 entries=sorted(existing.items(),key=lambda x:-x[1])[:4];total=sum(w for _,w in entries);joints[i]=0;weights[i]=0
 for slot,(joint,w) in enumerate(entries):joints[i,slot]=joint;weights[i,slot]=w/total
 changed+=1
attrs['JOINTS_0']=append(joints,'VEC4',5123);attrs['WEIGHTS_0']=append(weights,'VEC4');skin['inverseBindMatrices']=append(inv.transpose(0,2,1).reshape(-1,16),'MAT4');doc['buffers'][0]['byteLength']=len(data)
assert np.allclose(weights.sum(axis=1),1,atol=.001)
encoded=json.dumps(doc,separators=(',',':')).encode();encoded+=b' '*((-len(encoded))%4)
while len(data)%4:data.append(0)
out=struct.pack('<III',0x46546c67,2,28+len(encoded)+len(data))+struct.pack('<II',len(encoded),0x4e4f534a)+encoded+struct.pack('<II',len(data),0x004e4942)+data
(root/'web/assets/avatar/worker-fingers.glb').write_bytes(out)
print(f'Added 15 joints; reassigned {changed} glove vertices; original rig preserved.')
