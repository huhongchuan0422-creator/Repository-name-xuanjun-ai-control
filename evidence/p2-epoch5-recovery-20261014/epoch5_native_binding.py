"""One exact retained native binding update, under admitted install exclusion.

Preserves original bytes in the existing transaction archive, including any
private identity fields. Never prints values or creates new credentials.
"""
import hashlib,os,stat,tempfile
from epoch5_retained_state import NATIVE
from epoch3_preserve import ARCHIVE,exclusive_file,sync,authority
from inspect_epoch5 import file_data,T
from prepare_epoch5_bindings import native_binding_delta

def need(value,label):
 if not value:raise ValueError(label)
def update(before,after,manifest):
 original,unused=file_data(ARCHIVE+'/native-binding-original.json')
 need(native_binding_delta(original,'338e488c4203e23d6375726ec8067af815c2d0ec9ee74adc6925f8ef49de9c09')==before and native_binding_delta(original,manifest)==after,'NATIVE_BINDING_TRANSFORM')
 authority(ARCHIVE)
 raw,info=file_data(NATIVE)
 need(raw==before and (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode),info.st_nlink)==(0,0,0o644,1),
      'NATIVE_BINDING_PREVIOUS_IDENTITY')
 exclusive_file(T+'/epoch5-prior-native-binding.json',before)
 parent=os.path.dirname(NATIVE);meta=os.lstat(parent)
 need(stat.S_ISDIR(meta.st_mode) and meta.st_uid==0 and not meta.st_mode&0o022 and
      os.path.realpath(parent)==parent,'NATIVE_BINDING_PARENT')
 fd,path=tempfile.mkstemp(prefix='.epoch5-native-',dir=parent)
 try:
  os.fchmod(fd,0o644)
  with os.fdopen(fd,'wb') as stream:stream.write(after);stream.flush();os.fsync(stream.fileno())
  raw,current=file_data(NATIVE)
  need(raw==before and (current.st_dev,current.st_ino,current.st_uid,current.st_gid,current.st_mode,current.st_nlink)==
       (info.st_dev,info.st_ino,info.st_uid,info.st_gid,info.st_mode,info.st_nlink),'NATIVE_BINDING_CAS_CHANGED')
  os.replace(path,NATIVE);sync(parent)
  raw,current=file_data(NATIVE)
  need(raw==after and (current.st_uid,current.st_gid,stat.S_IMODE(current.st_mode),current.st_nlink)==(0,0,0o644,1),
       'NATIVE_BINDING_POST_IDENTITY')
  return {'old_sha256':hashlib.sha256(before).hexdigest(),'new_sha256':hashlib.sha256(after).hexdigest(),
          'original_preserved':True}
 finally:
  if os.path.lexists(path):os.unlink(path)
