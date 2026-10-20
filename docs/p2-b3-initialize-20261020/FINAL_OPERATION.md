# B3新隔离epoch1初始化｜最终待确认操作

仅本批初始化子检查点，不是完整B3或生产激活。B1/B2不重装；旧R03仍UNKNOWN。
薄适配复用原ActivationStore；不连接旧Grant、不创建DB/WAL、不bind socket、不启服务。

## 固定交付

- 源码/测试受影响Hosted版本5752051795755e4a27ea5863e2a731e24f566f92；
  [CI39366424078](https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/39366424078) SUCCESS，Python3.11/3.12各14项。
- request.json 2122字节，SHA256 d843a697e17e516aa92cb47a4c507527152f65d25b11ccdcc43d27b7fd878dbb。
- config 1056字节，SHA256 f772644e9a8587cda9e0df4c1e53dc64d647195407d29c69ef52625ebb0160ad。
- Python ELF：6809944字节，SHA256 9bee109da0dce17a7c9eeaca9f420cc6770a9fe143b9382d73bd22fe59b21a5f。
- descriptor head/file SHA256 6d3c95521492ba90640e723081a8d0f21fa2a2bfb3c896c0708ecb86e8ef93f1。
- 预期原提交回执SHA256 bede2ebc9f9c5458c92307c974358eb61947e7ec80a9611cc76735891ffae433。
- 可取得单文件制品固定1f455da15131ddd885439f8903c85e14251663b7，
  scripts/p2_b3_owner_initialize_20261020.py，78182字节，
  SHA256 36399b8c57a4acf116c8074a52acab34fd3ee258e41f31edb1f93ea6e629c4ad。
  内含准确工具bytes/request/预期输出文件，不依赖临时本地路径或浮动分支。
- initialize.py SHA256 26dd90276a2e07b471af55cf2eb9b8b0c371f7080f8e91697a384e351eeaa874；
  原Store SHA256 169a30ee858ef0e1ecb0b366702f35463993db34042410a43bc98018a9471eb4。

## 实际动作及副作用（本轮均未执行）

1. 宿主从固定Commit下载校验后，O_EXCL新建base/b3-owner-initialize-20261020.py root:root0600。
   取既有state/.formal-cli.lock（缺失会创建root0600），非阻塞排他；父base仍root:root0700。
2. 宿主root只读B1原manifest和receipt，保存原摘要及inode/权限/mtime/ctime；
   仅写本次输入副本，不chmod/chown原件。读取可能更新atime。
3. 新建base/b3-input-20261020及sources、tools准确嵌套目录，root:1002 0550，
   写request、两份B1来源副本、initialize及原Store工具root:1002 0440。
4. 新建base/b3-initialize、data、run，1002:1002 0700；
   新建base/logs/b3-initialize-20261020，root:root0700。无递归权限操作。
5. 三个独立Docker容器execute→退出→inspect→退出→同请求recover。
   均--interactive无TTY、固定镜像ID、UID1002、network none、cap-drop ALL、
   no-new-privileges、只读根、512MiB/swap1GiB/pids96。
   仅挂本次input→/input只读、本次B3root→同名绝对路径读写。
   不挂原B1/B2、生产数据/凭据或Docker Socket。宿主Python3.6.8保持。
6. 薄适配写.initialize.lock0600、intent/config/原commit-receipt0400，
   保留.pending-*临时文件及发布硬链接；原Store创建activation子目录0700、
   activation.lock/epochs.jsonl/active.json0644，追加并持久化唯一epoch1/PREPARED。
   Store descriptor发布可能创建.activation-*临时文件；SIGKILL残留保留，不扫除。
   不调用原03–09序列，不创建SQLite/数据库/WAL/socket或业务服务，不发布生产批准。
7. 宿主保存本脚本/request、三次stdout/stderr/CID/实际container状态/result、
   原提交回执副本和最终summary。容器不--rm，保留终态现场。
   每步120秒截止；超时只停止本次CID，不触碰其他容器或旧Writer。
8. 每步必须COMMITTED、相同固定身份/原回执、真实文件字节/摘要/uid/gid/mode正确；
   新进程inspect与recover后全文件集合/inode/mtime不变、仅一个epoch，
   B1两源件及base权限不变，才输出B3_NEW_INITIALIZATION_SUBCHECKPOINT_PASS。
   不能以Docker退出0替代结果，也不能报完整七批/P2已完成。

## 恢复点

- intent/config中断：原SHA与身份核对后，recover不覆盖发布缺失部分。
- 原Store append后descriptor前：核唯一epoch1完整链和所有expected身份，再reconcile；
  不重调prepare、不创建epoch2。
- descriptor完成、receipt未发布：recover只发布预期不可变receipt。
- 已COMMITTED：同请求execute/inspect/recover返回原回执，不能重装或改原回执。
- 错身份/摘要/损坏/未知文件归属：HOLD并保留现场。首次宿主脚本遇既有B3路径拒绝覆盖；
  不盲重跑首次命令。通过已保存request和原适配recover处理准确故障，必要时另交对应现场命令。

## 最终命令（仅Owner确认以上动作后执行）

```bash
# 收件窗口：Owner｜B3新隔离初始化（确认实际动作后执行）
sudo -n /usr/bin/python3 -I -B -S - <<'PY'
import os,stat,hashlib,runpy
from pathlib import Path
from urllib.request import build_opener,ProxyHandler
assert os.geteuid()==0
assert os.uname().nodename.split('.')[0]=='iZd7oeikknn1z21sq6ji6zZ'
base=Path('/var/lib/xuanjun-p2-isolated-test')
info=os.lstat(str(base))
assert stat.S_ISDIR(info.st_mode)
assert (info.st_uid,info.st_gid,stat.S_IMODE(info.st_mode))==(0,0,0o700)
url='https://raw.githubusercontent.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/1f455da15131ddd885439f8903c85e14251663b7/scripts/p2_b3_owner_initialize_20261020.py'
with build_opener(ProxyHandler({})).open(url,timeout=45) as response:
    raw=response.read(131073)
assert len(raw)==78182
assert hashlib.sha256(raw).hexdigest()=='36399b8c57a4acf116c8074a52acab34fd3ee258e41f31edb1f93ea6e629c4ad'
compile(raw,'B3_OWNER_CONFIRMED_OPERATION','exec')
path=base/'b3-owner-initialize-20261020.py'
fd=os.open(str(path),os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,'wb') as out:
    out.write(raw);out.flush();os.fsync(out.fileno())
fd=os.open(str(base),os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
try:os.fsync(fd)
finally:os.close(fd)
runpy.run_path(str(path),run_name='__main__')
PY
```

回传完整stdout及RETAINED_SUMMARY路径；失败也回原始错误，保留所有本批文件/容器。
本轮本地Docker与英国Docker安装均NOT_EXECUTED。
