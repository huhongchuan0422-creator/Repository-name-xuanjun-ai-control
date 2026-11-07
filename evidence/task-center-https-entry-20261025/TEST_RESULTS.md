# 适用验证结果

## 同版通过

- `python3 -m unittest -v tests.test_task_center_session_auth tests.test_task_center_app`
  - 15/15 通过，退出码 0。
  - 覆盖 base path、正确/错误 Host、缺失/错误 Origin、伪造转发头、CSRF、Secure/
    HttpOnly/SameSite/Cookie Path、退出清除、默认 loopback 兼容、WAL 只读投影。
- `node --test tests/task_center_digital_twin.test.cjs`
  - 1/1 通过，退出码 0。
- Nginx 候选 location 放入非特权独立语法 fixture 后执行 `nginx -t`
  - syntax ok / test successful，退出码 0。
  - 启动前出现无法打开系统默认 error log 的 alert，但读取候选配置和最终语法检查成功；
    没有读取私钥、没有加载或修改现场配置。

原始输出：`targeted-python.log`、`ui-node.log`、`nginx-syntax.log`。

## 全仓发现但不归因于本改动

尝试 `python3 -m unittest discover -s tests -p 'test_*.py'`：运行 685 项，11 FAIL、100 ERROR、
1 SKIP，退出码 1。失败集中在与本改动无关的社区/P2/Stage5、旧迁移以及要求受信 release
目录的测试；典型门禁为 `HOLD_UNTRUSTED_RELEASE_DIRECTORY`，另有缺失浏览器测试模块。
本轮未修改这些范围，也未降低其门禁；因此不将全仓写成 PASS。变更相关的 15 项定向
测试全部通过。

## 尚未执行

- 现场 Nginx 完整 `nginx -T`（root-only include 冲突仍 UNKNOWN）。
- 新 release、unit 参数或 Nginx 配置安装。
- 真实 HTTPS 浏览器登录与五角色业务旅程。
- DNS/TLS/防火墙/公网端口变更（均非本轮授权）。
