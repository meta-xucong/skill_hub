# aiself.vip 国模分组定价设计复盘（2026-09-18）

> 记录 cn-llm-yetoken 分组（group 13）从 0 到可售状态的完整定价设计思路、实测证据与踩坑，
> 供后续复盘与新分组复制。配套操作流程见同目录 SKILL.md。

## 1. 链路架构

```
客户 key (sk-…) → aiself.vip (sub2api, group 13)
    → 上游账号 121 YeToken-guomo-text  ┐
    → 上游账号 122 404Token-guomo-text ┘→ yetoken.vip「H-百炼国模 (distributor)」→ 智谱/百炼/DeepSeek/月之暗面/腾讯/MiniMax
```

- 14 个国模文本模型：glm-5.2/5.3/5.3-flash、deepseek-v4 系×5、qwen3.8-max/flash、kimi-k3、hy4×2、minimax-m3、muse-spark-1.3-contributor-free
- 分组 13 `models_list_config` 白名单 14 模型；渠道 1 `yetoken-guomo-pricing` 绑定分组 13 管全部定价
- 分组 `rate_multiplier = 1.5`

## 2. 成本模型（全部实测钉死）

### 2.1 数据源

- `GET https://yetoken.vip/api/pricing`（带 Bearer）→ 全站模型元数据：`model_ratio`、`completion_ratio`、`billing_expr`、`enable_groups`
- 关键发现：**14 个模型里有 12 个走 `tiered_expr` 计费，`model_ratio` 对它们是摆设**

### 2.2 expr = 上游官方人民币牌价（¥/1M tokens）

铁证：glm-5.3-flash 的 expr `p*0.8 + c*2.8 + cr*0.23` 与智谱 BigModel 定价页
GLM-5.3-Flash 标准价 **¥0.8 / ¥2.8 / 缓存命中 ¥0.23** 逐字吻合（bigmodel.cn/pricing）。
glm-5.3 expr 8/28 = 智谱旗舰价，同理。

### 2.3 实际扣费 = 0.4 × expr(¥)（分销折扣）

校准方法：`GET /v1/dashboard/billing/usage?start_date=&end_date=`（**必须带日期，不带参数的版本有缓存**）
打一发已知 token 量的请求 → delta_usage / expr价格 = 常数。
实测 glm-5.3-flash 35in/4000out：delta=0.4492，expr价=¥0.011228 → **factor = 0.4**。
1 usage-unit ≈ ¥0.025。

### 2.4 ratio 计价模型（glm-5.2 / kimi-k3 / muse-spark）

实测（kimi-k3 + glm-5.2 双请求合并 delta=0.6128）：
**成本 = ratio加权token × ¥1.11/1M**。若假设 0.4 折扣统一，则 ratio 牌价 ≈ ¥2.78/ratio-unit（未独立验证）。
- kimi-k3 (ratio 10/comp 5)：成本 ¥11.1 / ¥55.5 每 1M
- glm-5.2 (ratio 4/comp 3.5)：成本 ¥4.44 / ¥15.6 每 1M

## 3. 定价公式（当前生效）

```
渠道价 = 成本 × 1.25          （sub2api 内部计费基准）
用户实付 = 渠道价 × 1.5        （分组 rate_multiplier）
        = 成本 × 1.875
        = 官方牌价 × 0.75      （expr 模型已实测验证；ratio 模型基于统一折扣假设）
毛利率 = 1 − 1/1.875 = 46.7%   （对营收口径）
```

设计意图：**比官方直连便宜 25%** 的走量定位，同时保住 ~47% 毛利。
（曾试过成本×2 + 1.5x = 官方×1.2 的 66.7% 毛利方案，因比官方贵 20% 无竞争力而放弃。）

用户实付单价（¥/1M 入/出）：glm-5.3-flash 0.6/2.1 · glm-5.3 6/21 · glm-5.2 8.3/29.1 ·
kimi-k3 20.8/104 · minimax-m3 1.6/6.3 · deepseek-v4-flash/v4.1 1.5/6 · deepseek-v4-pro 6.75/20.25 ·
qwen3.8-flash 0.6/2.03 · qwen3.8-max 9/27 · hy4 与 hy4-preview 4.5/13.5

## 4. 验证方法论（复盘时照此重跑）

1. **计费数学核对**（usage_logs）：
   `total_cost = in×input_price + out×output_price`（分毫不差才算配置生效）
   `actual_cost = total_cost × rate_multiplier`
2. **上游真实成本**：dated usage 端点前后差值 ÷ 响应 usage tokens
3. **可用性**：逐模型 chat 扫描（max_tokens 压小），FAIL 语义表见 SKILL.md §4
4. ⚠️ `model-pricing?model=` 预览端点只显示内置目录，渠道定价不体现在预览里但计费生效——别被它骗了

## 5. 踩坑清单（按代价排序）

1. **ratio 字段对 tiered_expr 模型是摆设**——第一版定价错按 ratio 分档借内置价，导致 hy4/hy4-preview 亏 58-87% 在卖
2. **sub2api 内置目录是美元牌价体系**，人民币站（充值 1 unit≈¥1）直接用会把 glm-5.2/5.3、kimi-k3、deepseek 系全部卖成亏损
3. **渠道定价不进预览端点**，验收必须看 usage_logs 实际扣费
4. billing/usage 不带日期参数有缓存，测成本必须带 start_date/end_date
5. PS 5.1 向 ssh 传参剥双引号 → 远程命令写 .sh 文件走 `-RemoteScriptPath`
6. base_url 不带 /v1（网关自己拼）；`sync-upstream` 只返回预览不落库，模型池靠 `credentials.model_mapping` 键
7. muse-spark-1.3-contributor-free 是上游免费池，有当日限额（reset at 00:00），不可作为可靠容量

## 6. 配置快照（2026-09-18）

| 对象 | ID | 要点 |
|---|---|---|
| 上游账号 | 121 YeToken-guomo-text | key sk-8ySO…，H-百炼国模 |
| 上游账号 | 122 404Token-guomo-text | key sk-4GTA…，同分组双 key 冗余 |
| 分组 | 13 cn-llm-yetoken | models_list_config 14 模型，rate_multiplier 1.5 |
| 渠道 | 1 yetoken-guomo-pricing | 11 条 token 定价规则覆盖 14 模型，= 成本×1.25 |
| 测试 key | sk-5efd…379a | user_id=2, group_id=13 |

## 7. 已知未决项

- glm-5.2 / kimi-k3 / muse-spark 的 ratio 牌价（¥2.78 假设）未独立验证——如需精确复盘，用 dated usage 端点单测一发即可
- 支付通道（payment_provider_instances）未配置，定价尚未接到真实收款
- muse-spark 免费池限额随上游波动，容量不可承诺
