# G3身份、最小访问和状态来源
## 下一批仅元数据
G23_METADATA_COMMAND.txt固定国内原admin，经sudo只读已知路径元数据；服务账号/命名组UID/GID、根/父链/新release/venv/current、配置/secret/env、原DB及WAL/SHM/journal、原unit均在同一批。没有目录枚举、读取正文、执行项目文件或服务操作。ABSENT不是历史不存在证明；symlink不跟随，未知路径不扫描。新账号若未创建，按原S3明确范围创建，UID/GID由系统实际结果记录，不硬填100x。

## 准确权限适配方案（实施前绑定当前元数据，不先盲改）
- source/release及venv：root-owned，服务仅读/遍历，非服务/其他人不得写；不改原ProtectSystem=strict、ProtectHome、ReadWritePaths限定。
- /etc/xuanjun-cloud-oauth当前root0700：不能供服务读取。候选最小组访问为root:xuanjun_oauth、0750；父链不加组/其他写。需要组r-x而非仅x，因为private_bytes使用O_RDONLY|O_DIRECTORY打开父链。该目录无其他组成员方可采用；四份既存root0600的Nginx暂存文件不变，服务只看到名称不能读取正文。
- authority.json/session.secret/github.secret：xuanjun_oauth所有，0400、单硬链接、无ACL额外主体；放在上述root控制、服务不可写目录。原加载器只接受0400/0600，所以不能用root:service0640或文件ACL制造实际0640后宣称兼容。服务身份作为owner在沙箱外可改mode，故本方案不宣称配置对该UID密码学不可变；运行时ProtectSystem=strict阻断etc写，配置SHA仍绑定。若需要抵抗同UID沙箱外写者，必须另行设计，不能假称本方案提供。
- authority.env：root0600，仅systemd管理器读取；只含Manifest/config SHA等非秘密引用，不放真实秘密正文；无需授予服务读取env文件。
- /var/lib/xuanjun-cloud-oauth：xuanjun_oauth:同组0700；authority.sqlite0600、单链接。目录允许SQLite sidecar，仅此data根列ReadWritePaths；不改其他路径权限。
这些是具体目录/文件级部署适配，不是通用chmod/chown授权。按原S3已适用授权实施的对象不重复求批；若实测需新增组成员、ACL或其他范围，先集中说明对象/影响/回退后确认。不放开Certbot或其他应用目录。

## 首次初始化与已有历史
固定DB=/var/lib/xuanjun-cloud-oauth/authority.sqlite。旧原记录新独立authority未建立DB是历史事实，须与本批当前DB/sidecar元数据和原创建日志一起判定；本批不存在仅是瞬时事实。确认为首次新命名空间才沿原显式initialize_new_database，记录intent、文件inode/size、schema版本、结果和退出码，不自写DDL。create_app不会自动建库，入口mode=rw只开既有库。
若任何DB/sidecar存在、创建记录冲突、部分初始化或状态未知：保留原库/WAL/SHM，停止初始化，沿原事务/源版本/所有者查清。不用空库、删除sidecar或改名替换来恢复启动。本批不读DB正文，不将元数据称quick_check或数据恢复验收。

## 配置、启动、恢复
G2独立venv不依赖App。真正启动需要正常登记后回填audience/client/callback、四用途秘密各自引用与配置SHA；example enabled=false/null/clients={}不能启用。配置只初始catalog=[]，无业务Writer；出口未证/introspect继续403。UID/GID及访问通过后以同一正式unit/沙箱验服务可读、etc/source不可写、仅data可写、loopback18770，不创建临时宽权限unit冒充。失败保留新增对象和数据，不清库；已有运行版本存在才按原可兼容快照恢复，不动旧连接/英国成功阶段。
