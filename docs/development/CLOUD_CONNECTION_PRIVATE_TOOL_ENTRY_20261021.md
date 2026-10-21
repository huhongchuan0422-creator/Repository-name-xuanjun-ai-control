# 玄钧AI新：私有文件工具接入增量（未启用）

原PR17，接线原任务，不另建任务。不开通OSS、不新增公网入站端口、不启动B5/SDK或任何业务项目。

## 当前真实成果

- 已确认的常驻服务xuanjun-cloud-connection.service已经英国启用；运行源码f3bfc3fe，enrollment交付21a7a603，原三文件pin不变。
- Work当前窗口经GitHub提交三台任务，英国持久队列领取并回传SUCCESS与真实InvokeId；准确任务及回执见原PR17。
- 原三任务成功后重启新服务，PID改变而request/invoke不变；重复同一request ID未创建第四个任务；竞争进程在flock处拒绝，无远端执行。
- 三份非敏感/etc/os-release文件通过原认证Workbench下载到当前Work容器；包861字节，SHA256 b59a4b1e3389ebd651828984fff6e751f567132b64299ea71877eac6503da729；包及各文件SHA独立复算一致。
- 文件保留到当前用户可读取的文件空间，library_file_id=libfile_c1bcf45341948191b59d04556b69c95e；此项不冒充常驻自动文件API。
- STS旧会话记录Expiration=2026-10-21T15:29:22Z；15:30:02Z后原持久身份再次取得三台角色并核AccountId，无Owner重新登录，没有保存Token。
- 真实第二开发窗口调用仍未执行。当前窗口浏览器认证不能推定其他窗口共享认证。

## 为什么需要新增私有工具接入

已有GitHub连接器可提交任务、读取非秘密结果；不适合传送私有文件正文。
当前文件已实测经认证浏览器取回，但此方法依赖该窗口现有会话，不能算后台通用文件交付完成。
不把阿里云RAM权限或英国服务存在当成ChatGPT已经加载私有文件工具。

官方可选正常机制：OpenAI Secure MCP Tunnel，英国主动出站连接，私有stdio MCP适配器不开放公网监听。
官方文档：
- https://developers.openai.com/api/docs/guides/secure-mcp-tunnels
- https://developers.openai.com/api/docs/guides/custom-mcp-server
- https://learn.chatgpt.com/docs/extend/mcp

该机制需要真实OpenAI Platform组织、目标ChatGPT工作区、tunnel_id、受限运行凭据及正常插件登记。
Tunnels Read/Manage与Read/Use、工作区插件准入分别核实；没有实测不得标可用。
这里只用隧道输送工具请求，不调用模型推理API；文档没有证明本账号费用/权限状态，本轮不得承诺零费用或已具备隧道权限。
平台登录页面已实际打开并显示登录墙，尚未登录，不创建账号、密钥或隧道。

## 本次源码候选范围

production/cloud_connection/private_mcp.py：标准输入输出JSON-RPC，每消息16KiB上限，支持初始化/通知/ping/两项只读工具；不设网络监听。

| 工具 | 准确范围 |
|---|---|
| connection_status | 只按request ID读取现有只读数据库中的状态/InvokeId/目标；不领取、不执行、不重试 |
| read_result_file | 只返回SUCCESS任务已批准的/etc/os-release结果；绑定原invoke、SHA、字节数及受保护文件引用；无任意路径/URL/命令参数 |

私有文件数据仅通过获准的私有工具回传，绝不放公开GitHub评论或Artifact。
此适配器只读现有队列，不能签发业务安装批准，也不增加生产Writer。
工作区范围和访问主体必须在真实平台确认；初始化握手不是身份认证，不以握手成功冒充OAuth/RBAC完成。
当前不支持任意客户材料、密钥、安装、采购或全运维指令；未来需按原项目准确授权注册受控动作。

## 待确认并实施的新增对象（尚未实施）

1. 原账号的一个私有隧道及单一目标工作区关联；若已有合适对象则复用，不重复创建。
2. 一个仅Tunnels Read+Use的受限运行凭据，英国root私有保管；不写聊天/源码/命令参数/公开日志。
3. 官方tunnel-client独立进程与本只读stdio适配器，和现有连接服务、旧P2分离；不改其current或额度/事务记录。
4. 私有插件只登记上述两项只读工具；实际调用后才认定工具加载完成，第二真实开发窗口另行实测。
5. 新持久访问/凭据/工作区共享须按正常机制完成具体确认；不因当前root服务获准而推定新平台访问已获准。

本轮只完成代码、离线验证和准确交付。不安装客户端、不创建隧道、不扩大访问、不签发业务许可。
