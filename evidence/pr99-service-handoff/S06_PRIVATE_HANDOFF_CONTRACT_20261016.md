# S06 当前运行合同与私有通道接续边界（2026-10-16）

## 已取得的现场输入

R2#6217030577的1363份选定源码及WAL-aware SQLite离线恢复点已由Owner-root成功接收，回执#6217284394。执行验收集中申请中；不再复制或重跑。本点不是最终Writer数据截点。

本次Run38913529642三机非root Job全部SUCCESS：东京117015069721、国内117015069212、韩国117015069611。没有checkout/sudo、unit正文、命令参数、环境变量、凭据、数据库或业务HTTP读取；没有服务动作。脚本/原始摘要位于同目录。

## 必须依据本次证据修正的运行合同

1. 东京 `provider-neutral-tunnel.service` 的LoadState=not-found；`provider-neutral-tokyo-tunnel.service` loaded/active，Id/Names只有后者。不能当成已证明的别名，不能把原客服Wants的缺失依赖原样迁入后声称链路齐全。旧生产不修改；新候选必须明确依赖哪个实际端点并验收。
2. 东京Portal、WeCom、shim、executor均User=admin、WorkingDirectory=/opt/trading-system。三个SSH隧道的WorkingDirectory=/home/admin或空。不得用历史恢复Portal覆盖当前R4。
3. executor有准确drop-in `/etc/systemd/system/tokyo-restricted-model-executor.service.d/provider-health-alert.conf`；本次只读路径，正文未读。新合同必须明确是否需要该监护职责，不能因只迁主unit而遗漏。
4. 国内bridge使用openclaw_ops和既有runtime/internal-bridge；不是东京admin用户。不得直接照搬UID、Home或覆盖该既有运行树。
5. 韩国443实际监听，但非root ss不显示PID；nginx.service not-found。归属仍UNKNOWN，不占用或替换443。韩国既有novel/tailscale/数据库/Yibi/MoreLogin均保护。
6. 国内新增发现xuanjun-site-hub-preview.service为loaded/active；归其他PR122工作，不纳入本分支迁移、不停止或覆盖。
7. /root和/admin私有cron及user unit目录均权限不足。仅元数据采样，不得宣布没有调度或已穷尽全部服务。

## 下一批私有材料边界（不是执行许可证）

只为现有非API通道整理当前准确入口、服务运行身份、unit/drop-in、双端路由/监听/鉴权身份、必需非API状态。必要非API认证材料只能在可信root私有流程内加密直传，不在GitHub日志、评论、制品、命令参数或聊天中展示。旧交易API、TikTok等API配置不读取/投放/调用；若同文件混有API材料，停止整文件迁移，先制定字段级私有交接方案。

不能把整个runtime、/home/admin、/etc、数据库目录或历史归档直接恢复到生产。ReadWritePaths只是运行时允许写范围，不等于迁移白名单；operations-secretref-store等混合秘密目录尤其不能按目录打包。

当前约束明确：已有Dispatcher只授权原inspect/install；它不是任意root shell，不能用它读取私有配置、绕过本次复制的单次范围或修改服务。Owner长期授权允许继续做只读准备；真实新安装、上游切换、调度停止与东京退役仍须准确范围与回滚验收。

## 分批落地顺序

- S06：当前非API运行合同、最小私有材料、目标目录/端口及回滚绑定。先离线准备停止状态新候选，不覆盖既有current。
- S07：国内Portal与客户联系/客服/小说旧入口逐服务接续，沿用R4固定403，真实非写检查后再切各自上游；东京保持可回退。
- S08：RPC/隧道/VPN按双端实际依赖接续；UK原P2归原writer，不恢复mask、不启第二writer。
- S09：四项Finance/Billing timer及root/admin调度分别决定保留/迁移/停止；最终数据时点和唯一Writer另行准入，旧API延后不等于可忽略数据。
- S10：全部仍需职责接续或明确取消后再验收退役。静态站迁移或离线备份成功都不构成东京可关闭证明。

S06尚未安装。缺的是可验证的私有运行合同和目标接续执行，不是需要重审已通过的B/C、源码、历史备份、13项依赖或R2测试。
