# sub2api-upstream-integration

把任意 OpenAI 兼容上游（中转站 API key）作为上游账号，接入自建 [Sub2API](https://github.com/Wei-Shaw/sub2api) 实例，完成账号 / 分组 / 模型清单 / 计费验证的全流程，并沉淀了针对本站定制构建的实测坑位。

## 用途

- 新买了某个中转站的 key（yetoken / wokey / liuhe 类），想挂进自己的 sub2api 转售或自用
- 新增分组、调整模型白名单、做全链路端到端验收
- 无面板登录凭据时，通过 VPS SSH + 数据库获取管理面访问能力

## 前置

- VPS SSH 私钥走 [meta-xucong/VPS_SSH_KEY](https://github.com/meta-xucong/VPS_SSH_KEY) 仓库的官方 `Invoke-EncryptedSsh.ps1` 解密脚本（统一口令另行提供）
- sub2api 部署在 `/opt/sub2api/deploy`（Docker：sub2api / postgres / redis），应用监听 `127.0.0.1:8081`

## 工作流概要

1. **SSH 侦察**：确认主机 / 容器 / 版本 / 反代域名
2. **管理权限**：优先尝试 `.env` 初始密码登录；失效则按 sub2api 原生机制在 `settings` 表 mint `admin_api_key`（明文比对，`x-api-key` header 调用 `/api/v1/admin/*`）
3. **建上游账号**：`platform=openai, type=apikey`，`credentials` 内放 `api_key + base_url（不带 /v1）+ model_mapping（恒等映射，决定可用模型池）`
4. **建分组**：`models_list_config = {enabled, models}`（注意：本定制构建**没有**上游 HEAD 的 `model_allowlist` 字段）
5. **测试 key**：`api_keys` 表明文存储，可直接 INSERT 造测试 key
6. **全链路验证**：`/v1/models` 精确核对 → 逐模型 chat 实测（含 usage 记账）→ 公网域名复测

## 最小示例

```bash
# 1. 探测上游
curl -s https://yetoken.vip/v1/models -H "Authorization: Bearer sk-xxx"

# 2. 建账号（admin api key 认证）
curl -s -X POST http://127.0.0.1:8081/api/v1/admin/accounts \
  -H "x-api-key: admin-xxx" -H 'Content-Type: application/json' \
  -d '{"name":"YeToken-guomo-text","platform":"openai","type":"apikey",
       "credentials":{"api_key":"sk-xxx","base_url":"https://yetoken.vip",
         "model_mapping":{"glm-5.3-flash":"glm-5.3-flash"}},
       "concurrency":5,"rate_multiplier":1,"confirm_mixed_channel_risk":true}'

# 3. 建分组 + models_list_config，绑账号，造测试 key，跑 /v1/models 与逐模型 chat
```

## 实测战绩（2026-09-18）

- yetoken「H-百炼国模 (distributor)」key：14 个国模文本模型接入 aiself.vip
- 公网 `/v1/models` 精确 14 模型；逐模型 chat **13/14 通过**（唯一 FAIL 为上游免费池当日限额，非配置问题）

## 关键坑位速查

| 坑 | 结论 |
|---|---|
| PS 5.1 传参剥双引号 | 远程命令一律写 .sh 文件走 `-RemoteScriptPath` |
| PowerShell 工具吞 stdout | `*>` 落盘 + `iconv -f UTF-16LE -t UTF-8` 读 |
| `sync-upstream` 不落库 | 只返回预览；模型池靠 `credentials.model_mapping` |
| `model_allowlist` 被静默丢弃 | 本构建用 `groups.models_list_config` |
| base_url 带 /v1 | 不要带，网关自己拼 |
| 上游报错语义 | `insufficient balance`=没钱；`Usage limit ... 00:00`=免费池限额；`503 model_not_found`=分组无此模型 |
