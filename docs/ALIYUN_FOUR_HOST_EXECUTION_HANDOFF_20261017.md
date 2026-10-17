# 四台轻量应用服务器自动执行能力交接

Owner：胡洪川。2026-10-17 09:40 CST 完成真实验收，沿用既有长期项目授权及原 PR/任务。此文说明已有能力，不替代各任务准确版本的生产放行。

## 已验证能力

通过 GitHub Actions → 英国 RAM 用户 AccessKey → STS AssumeRole → SWAS RunCommand → DescribeInvocationResult，四机实际以 root 执行固定只读身份命令并取得成功终态，hostname/instance/invoke/nonce/uid0 均匹配。无需 Owner 逐次输入服务器 SSH 密码或粘贴命令。当前已提交的工作流只执行固定只读检查；后续业务命令由执行方按原任务实现、验证后下发，不存在已经安装的任意命令 RPC 服务。

仓库 huhongchuan0422-creator/Repository-name-xuanjun-ai-control；原 PR99；分支 build/tokyo-korea-migration-prep-20261014。

| 主机 | 地域ID | SWAS实例ID | 角色ARN |
|---|---|---|---|
| 英国 | eu-west-1 | 40dfc6a47d5e4363b9da7d0d6ab01cb1 | acs:ram::1107191612880779:role/xuanjun-ai-esc |
| 韩国 | ap-northeast-2 | 09207081a09a466aa0079b07b5e3e7ca | acs:ram::1691189778575891:role/xuanjun-automation |
| 国内 | cn-shanghai | 3a22c458934142eea89ec6e3bf481a57 | acs:ram::1384884686754410:role/xuanjun-automation |
| 东京 | ap-northeast-1 | 68985c531add4e90a131aef703a389e6 | acs:ram::1384884686754410:role/xuanjun-automation |

预期hostname依次 iZd7oeikknn1z21sq6ji6zZ、iZmj7a5kwr75qc1tul4kf9Z、iZvt5t8tlrm8oiZ、iZ6wee8q9z4t03hvqumwfhZ。默认 /usr/bin/python3：英国/韩国3.6.8，国内/东京3.11.6。韩国续接程序明确使用 /usr/bin/python3.11。

## 凭据与可复用入口

原仓库 Actions Repository secrets：ALIYUN_ACCESS_KEY_ID、ALIYUN_ACCESS_KEY_SECRET。仅工作流运行时引用，不读取/输出/转发密钥值，不另建账号或重复要求授权。当前角色已能 AssumeRole 和远程root命令执行；未逐项实测购买、删除、DNS等全部云API，不能把通道验收称为所有云API验收。

工作流 .github/workflows/aliyun-four-host-readonly.yml；准确提交17d86427670671b65280c5d22ee952c0e178a85e。
实际 https://github.com/huhongchuan0422-creator/Repository-name-xuanjun-ai-control/actions/runs/38991455661/attempts/2 ，job117275780078 SUCCESS。原始日志已读。证据 evidence/pr99-service-handoff/aliyun-execution/four-host-identity-20261017.json。

有同仓库 GitHub 写入及 Actions 日志/运行权限的 ChatGPT、Dots 可复用代码和 secrets 引用，通过原任务下发已授权命令。聊天文本本身不提供会话工具或账号连接；新窗口先核验自身 GitHub 工具可用，不能仅凭此文声称已登录主机。当前无需本地 SSH、也不应索取 root 密码。四机身份工作流的 PR 触发限定同仓库 PR99 和该 head 分支；其 workflow_dispatch 尚不代表任意新分支或主分支已经注册该入口。修改工作流会触发 PR 检查；不为触发另建重复任务。

## 执行及边界

每个修改性任务绑定准确脚本SHA与主机；执行前核对当前任务状态、旧执行者及单writer；仅下发一次，保存 InvokeId 后查询终态，未知不得盲目重跑。由原任务执行方记录真实 commit/run/job/InvokeId 与结果，继续原 canonical ledger。禁止输出业务密钥、数据库内容或私有业务材料到公开仓库、聊天、Actions日志/制品。机间私有材料保留服务器私有通道。

长期授权范围内的常规检查、修复、测试和已放行部署自主执行，无需再向 Owner 请求相同权限。生产准入仍按原任务：不得绕过独立审核或准确制品许可，不得启动第二writer，不得解除旧mask让测试通过；DNS/生产入口切换、币安交易与Writer转移、东京退役仍继承原HOLD，直到各自既有条件满足。RAM root能力不等于这些条件已满足。

PR99当前断点：国内v3 contact健康200，portal/customer_service缺 authentic internal-bridge domestic_bridge_cert.sha256；v4桥接材料/当前124源码哈希核对/复制品隔离启动脚本已准备，尚未执行。新SWAS迁移只读预检 .github/workflows/aliyun-s07-preflight.yml，准确提交b61a3940c56fb4bd1eff21c1258732a5e83d055d。英国P2与本次迁移分别由各原执行方负责，不启动并行写入。
