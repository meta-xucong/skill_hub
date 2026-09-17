---
name: sub2api-upstream-integration
display_name: Sub2API 上游接入
description: 把 OpenAI 兼容中转站（yetoken/wokey/liuhe 类）作为上游账号接入用户自建的 sub2api 中转站（aiself.vip，VPS 45.113.1.228），含 SSH 通道、管理权限获取、账号/分组/模型清单配置与全链路验证。触发词：接入上游、sub2api 加账号、加分组、aiself、接中转站。
version: 1.0.0
author: meta-xucong
agent_created: true
---

# Sub2API 上游接入工作流

目标：把任意 OpenAI 兼容上游（中转站 key）挂进用户自建 sub2api，对外提供模型服务。

## 0. 环境事实（2026-09-18 实测）

- 站点：`https://aiself.vip`（nginx 443）；VPS `45.113.1.228`，SSH 端口 `27793`，用户 root，Debian 12
- 部署：`/opt/sub2api/deploy`，Docker 三件套 sub2api/postgres/redis；应用 `127.0.0.1:8081`；Postgres `sub2api/sub2api`（密码在 `.env`）
- 构建：**定制版** `0.1.173-smart-router-image-failover`（镜像 `sub2api:wokey-billing-content-url-*`），与上游 HEAD 有 API 差异（见 §4 坑位）
- DB 凭据：`.env` 的 `POSTGRES_PASSWORD`；`ADMIN_PASSWORD` 已失效勿用

## 1. SSH 通道（必须走仓库官方脚本）

- 私钥仓库：`meta-xucong/VPS_SSH_KEY`（gh CLI 已登录），`hosts/sub2api/key.enc.json` + `scripts/Invoke-EncryptedSsh.ps1`
- **仓库 AI 规则**：解密/验证必须用仓库脚本，禁止自写解密替代；统一口令向用户索取
- 本地副本目录：`~/.ssh/vps_repo/`（scripts + hosts/sub2api）
- 调用模板（PowerShell）：
  `& "$env:USERPROFILE\.ssh\vps_repo\scripts\Invoke-EncryptedSsh.ps1" -EncryptedKeyPath ...key.enc.json -HostName 45.113.1.228 -Port 27793 -User root -Passphrase '<口令>' -RemoteScriptPath <本地bash脚本> *> <输出文件>`
- **坑 A**：PS 5.1 向 ssh 传参会剥内层双引号 → 远程命令**一律写成本地 .sh 文件**走 `-RemoteScriptPath`（脚本内部引号安全），不要用 `-RemoteCommand` 传复杂命令
- **坑 B**：PowerShell 工具可能吞 stdout → 输出 `*>` 落盘到工作区 tmp/，再用 `iconv -f UTF-16LE -t UTF-8` 转码读取（PowerShell 5.1 重定向产物是 UTF-16LE）

## 2. 管理权限（admin API key）

- admin 认证：`x-api-key: <admin-api-key>`，与 settings 表 `admin_api_key` 行**明文比对**（`crypto/subtle`），对应"第一个管理员"身份
- settings 表结构：`key varchar(100) unique, value text, updated_at timestamptz`（**无 created_at**）
- mint（幂等 UPSERT）：
  `INSERT INTO settings (key, value) VALUES ('admin_api_key', 'admin-<'openssl rand -hex 32'>') ON CONFLICT (key) DO UPDATE SET value=EXCLUDED.value, updated_at=now();`
- 冒烟：`GET /api/v1/admin/settings/admin-api-key` 带 x-api-key → `{"code":0,...,"masked_key":...}` 即成功
- 事后可在后台删除该 key 撤销授权

## 3. 资源创建（全部走 `http://127.0.0.1:8081/api/v1/admin/*` + x-api-key）

### 3.1 上游账号 `POST /admin/accounts`
```json
{"name":"<名字>","platform":"openai","type":"apikey",
 "credentials":{"api_key":"sk-...","base_url":"https://<上游域名>",
   "model_mapping":{"<模型>":"<模型>", "...":"..."}},
 "concurrency":5,"priority":10,"rate_multiplier":1,"confirm_mixed_channel_risk":true}
```
- **base_url 不带 /v1**（网关自己拼路径）
- **model_mapping 必须有**：openai 平台 apikey 账号的"可用模型池" = mapping 的键；恒等映射即可。没有它 → /v1/models 空或回落 gpt 默认目录
- `POST /admin/accounts/:id/models/sync-upstream` 只返回上游模型**预览**，不落库，仅用于生成 mapping
- 绑分组：`PUT /admin/accounts/:id` + `{"group_ids":[gid]}`（DB 侧 account_groups）

### 3.2 分组 `POST /admin/groups`
```json
{"name":"<分组名>","description":"...","platform":"openai","rate_multiplier":1,
 "subscription_type":"standard",
 "models_list_config":{"enabled":true,"models":["模型A","模型B"]}}
```
- **坑 C（版本差异）**：上游 HEAD 用 `model_allowlist`，本定制构建**没有该字段**（静默丢弃、`groups.model-allowlist-candidates` 404），对应物是 groups 表 `models_list_config` jsonb。先 `SELECT models_list_config FROM groups WHERE id=<参考分组>` 看活例（volcengine/kimi 组都是这模式）

### 3.3 测试 key（无面板 JWT 时）
- api_keys 表**明文**存 key：`INSERT INTO api_keys (user_id, key, name, group_id, status) VALUES (2, 'sk-<'openssl rand -hex 32'>', '<名字>', <gid>, 'active');`
- user_id=2 是管理员；先看 `user_allowed_groups` 是否限制用户分组

## 4. 验证清单

1. `GET /v1/models`（新 key）→ 应精确列出 models_list_config 的模型
2. 逐模型 `POST /v1/chat/completions`（max_tokens 小值）→ 记录 OK/FAIL + usage
3. 公网复测 `https://aiself.vip/v1/models` + 一次 chat
4. 常见 FAIL 语义：`credit insufficient balance`=上游 key 没钱；`Usage limit reached ... reset at 00:00`=上游免费池当日限额；`503 model_not_found`=上游分组无此模型

## 5. 回滚

- `DELETE /api/v1/admin/accounts/:id`（删账号）、`DELETE /api/v1/admin/groups/:id`（删分组）
- DB：`UPDATE api_keys SET deleted_at=now() WHERE key='sk-...'`（软删）
- 撤销 admin 授权：`DELETE FROM settings WHERE key='admin_api_key'`

## 6. 相关联资产

- 探测上游能力：先跑 `GET <上游>/v1/models`（图像站另查 `/v1/images/models`，见 yetoken/wokey 经验）
- 用户 skill_hub 仓库约定：`meta-xucong/skill_hub`，新 skill 可按其结构提交
