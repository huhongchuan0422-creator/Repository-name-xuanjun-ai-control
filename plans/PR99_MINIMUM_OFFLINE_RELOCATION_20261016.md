# PR99 最小离线搬迁：Owner范围收敛（2026-10-16）

本页沿原PR99/原分支补充执行范围，不新建任务。Owner明确：API以后重建；当前已有API不单独读取、解密、配置或使用，只保留接入通道；既有加密恢复包仅按密文保全。API和新签名身份不再作为离线文件搬迁的前提。

## 本轮完成口径
目标是把需要保留的代码、运行环境和必要历史数据安全落到目标机，并保留原执行/桥接/隧道通道；韩国交易服务保持停止。完成文件搬迁不能报告真实交易或唯一Writer切换通过。已有B安装和C候选均保留，不重开发/打包/测试，不新增C安装器。

## 已有可复用成果（不重做）
- B离线安装及收尾：#6209166651限定验收通过。
- 固定root通道：Owner-root安装成功；实际Runner调用成功，Run38886245115/Job116924571943；只支持inspect/install，不支持任意shell/备份导出。
- 原冻结C制品：#6213125007已补齐44/44绑定及30/30 runtime独立核验；本次不安装或启动C。
- 既有东京加密恢复基线：#6166635563、#6166680343。
  固定路径 /root/xj-recovery-package.DZWI6n/recovery-baseline.tar.gz.enc；
  1,320,571,760字节，SHA256 ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093。
  此为历史Owner-root回执；当前没有重新读取/解密/备份。
  历史基线覆盖范围比币安最小迁移广，禁止整包覆盖/etc、/home、生产API或现有服务；韩国已有小说/PostgreSQL/Redis/MoreLogin保持不动。

## 最少执行顺序
1. 固定上述既有基线身份，核实受保护异机副本及恢复密钥托管是否已经存在；已有则直接复用。只搬密文不等于恢复能力完备，密钥只能走既有私有管理通道。
2. 如缺异机副本，经可信admin/root私有路径拷贝固定密文至韩国新私有隔离目录，目标验证准确大小和SHA；不中途解密，不把备份或密钥上传GitHub、日志或聊天，不覆盖任何生产对象。
3. 如需恢复，只按原最小范围提取代码/必要历史数据到新的隔离目录，核对内容及运行依赖；不解密或激活旧API、不导入整套旧systemd/cron，不启动服务/调度，不创建Writer。
4. 保存真实目标文件/校验/隔离回执。最终数据时点、真实业务激活与东京退役仍须独立确认；不把历史基线作为当前最终一致快照。

## 真实新增现场事实
Run38886874470：韩国Job116926645339、东京Job116926645389 SUCCESS；非root UID1001，无checkout、sudo、HTTP、凭据或数据库内容读取。
- 韩国broker xuanjun_binance=UID/GID986、nologin；worker名称未创建；1986–1995 UID/GID均未分配（采样时点）。
- 韩国三个C候选根目录均ABSENT。
- 东京权威数据库文件为46,907,392字节，dev64771/inode1601016；采样时WAL/SHM未见。未打开数据库、未读取schema/订单；瞬时未见WAL不证明无Writer，也不授权普通文件复制活库。
- DNS解析为一次只读候选信息，不是API权限/网络验收；Owner已取消把API作为当前搬迁前置。
原C134/通道22及重新打包步骤在本次Hosted CI已明确SKIPPED；CI范围门禁真实Run38886880295/Job116926661256通过。

## 当前真实执行缺口
root私有基线的受保护异机复制尚无执行回执。当前韩国固定通道不能导出/导入备份，东京旧固定helper也只提供巡检；不能用这两条命令冒充已经拥有任意root文件传输能力。
因此本窗口未拷贝、解密或恢复该基线，未修改API、网络通道、数据库或服务。下一动作只解决这条私有文件搬运路径；不因该缺口扩大到API建设或重新审C源码。

## 最小私有搬运方式

在当前韩国Owner-root终端，通过已有SSH信任向固定东京admin@47.245.53.152拉取固定密文。StrictHostKeyChecking=yes、BatchMode=yes、ConnectTimeout=10，不新增SSH密钥/known_hosts/权限；实际hostname必须等于东京固定主机；源SHA和目标SHA都绑定历史已审基线。只写韩国新的0700私有目录；全程不解密、不触碰已有API/桥接/隧道/生产目录或服务。
若现有SSH路由不可用，在创建目标目录之前停止并报告该唯一通道缺口，不能自行关闭主机校验或改用明文/公开制品。实际命令尚未执行。备份解密密钥的私有托管及应用选择性恢复仍未实机确认，不把密文落地单独算作完整迁移。

## Owner-root一次密文私有拉取命令（未执行）

以下只在韩国Owner-root终端运行；既有SSH信任失败就停止，不增加权限或改主机校验。

```bash
bash <<'BASH'
set -euo pipefail
test "$EUID" -eq 0
test "$(hostname -s)" = iZmj7a5kwr75qc1tul4kf9Z
umask 077
XJ_SSH=(-T -o BatchMode=yes -o StrictHostKeyChecking=yes -o ConnectTimeout=10 -o ConnectionAttempts=1 -o ClearAllForwardings=yes)
ssh "${XJ_SSH[@]}" admin@47.245.53.152 'test "$(hostname -s)" = iZ6wee8q9z4t03hvqumwfhZ && sudo -n test -r /root/xj-recovery-package.DZWI6n/recovery-baseline.tar.gz.enc' || { echo 'STOP：现有东京SSH/root读取通道不可用；未复制，未新增权限。'; exit 2; }
D=/root/xuanjun-offline-baseline-20261016
mkdir -m 0700 "$D"
trap 'echo "HOLD：保留私有目录和未完成文件，不覆盖、不重跑。"; exit 2' ERR
timeout 900 ssh "${XJ_SSH[@]}" admin@47.245.53.152 'sudo -n /usr/bin/env -i PATH=/usr/sbin:/usr/bin:/sbin:/bin LANG=C /bin/bash -s' <<'REMOTE' | dd of="$D/baseline.enc.partial" bs=4M status=progress
set -euo pipefail
test "$EUID" -eq 0
test "$(hostname -s)" = iZ6wee8q9z4t03hvqumwfhZ
F=/root/xj-recovery-package.DZWI6n/recovery-baseline.tar.gz.enc
test -f "$F" && test ! -L "$F"
test "$(stat -c %u:%h "$F")" = 0:1
test "$(stat -c %s "$F")" = 1320571760
printf '%s  %s\n' ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093 "$F" | sha256sum -c - >/dev/null
cat "$F"
REMOTE
test "$(stat -c %s "$D/baseline.enc.partial")" = 1320571760
printf '%s  %s\n' ac43ec29186d4901016083387e6235288004abde6232792a2cc46d23f8e01093 "$D/baseline.enc.partial" | sha256sum -c -
mv -T "$D/baseline.enc.partial" "$D/recovery-baseline.tar.gz.enc"
sync -f "$D/recovery-baseline.tar.gz.enc"
echo "ENCRYPTED_BASELINE_OFFSITE=PASS API_UNTOUCHED=YES SERVICE_ACTIONS=0"
echo "PRIVATE_DESTINATION=$D/recovery-baseline.tar.gz.enc DECRYPTION=NOT_RUN"
BASH
```
