# PR122 静态体验发布：规范URL验收修复

原事务 pr122-hub-experience-20261016 已由 Owner 回滚，许可6215846584已消费。回执6216022307保留。不能再次apply或覆盖现场。

目标机实际观察：根目录 about.html 存在；Nginx仅公开 location = /about，以 try_files /about.html 服务。默认location /返回404。回滚后 /about.html同样404，首页200，故该404不能认定新UI回归；失败是发布器把磁盘文件名错误视作公开URL。

最小修复：新增smoke_routes，将已有根目录HTML映射为现有无扩展名入口，index.html映射/；其他已公开前缀与新路由保持。原Nginx生成结果、407份页面/资源、UI及规则不变，不开放通用HTML匹配、不弱化字节/CSP/nosniff校验。

新增真实隔离Nginx回归使用目标机观察到的14个根目录规范入口及既有前缀，默认拒绝其他路径。核对所有overlay对应公开URL字节与安全头、规范跳转、raw /about.html仍404、未知/私有路径拒绝、既有代理保留。该测试是Hosted loopback HTTP，不冒充国内HTTPS验收。

替代身份：事务pr122-hub-experience-20261016-r2，release pr122-hub-experience-ca7ab933-r2。原静态TAR保持b66eba8c958b10925064053f41dc575a6eb301616bc414d139cdddd98a2e7cb3；发布包装/Manifest/wrapper/HOST_PINS重新计算。旧r2官网基线仍需执行时核对。修复和准确CI/实际制品完成后集中增量复审，并申请新的单次许可及回滚。未批准前不部署。动态机制、客户中心、DNS、东京及其他服务不在本次范围。
