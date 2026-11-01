# OpenAlex 免费 Key 获取与接入教程

适用于任何学科。首次使用OpenAlex建议配置；用户可以暂不配置，仍可小规模匿名试用或使用其他来源。已配置不重复询问。免费Key仍有限额，不承诺永不429。

## 1. 为什么要配

截至2026-10-31，官方说明：无Key每天$0.10等值用量，已验证邮箱的免费Key每天$1，无需付款方式。普通关键词检索每次10 credits；列表/筛选1 credit，单实体DOI/ID查询免费，OpenAlex Content API PDF下载100 credits。匿名大约100次普通搜索就可耗尽日预算，各种请求混用则更少；不是“每天100篇论文”。每次分页都是一次请求。

每日UTC零点（中国/新加坡08:00）重置。普通匿名10请求/秒、免费Key30请求/秒；特殊重请求另有限速。429既可能是瞬时限速，也可能是预算不足。免费Key还是跨过首个游标页的必要条件，不能用缩小每页数量解决认证限制。

费率与限额会变化，先查官方：[认证与限速](https://help.openalex.org/api/authentication/)、[操作费用](https://help.openalex.org/access/example-costs/)。这里的美元是服务预算额度，不表示已从用户银行卡扣款。Skill不自动购买额度。

## 2. 获取免费 Key（推荐网页方式）

1. 打开 [OpenAlex](https://openalex.org/)，注册或登录你的账号，使用你能收信的真实邮箱。
2. 按网页/邮件提示完成邮箱验证；若没收到，检查垃圾邮件与邮箱拼写。
3. 打开 [Settings → API key](https://openalex.org/settings/api)，复制自己的Key。页面具体布局以官方网站为准。
4. 把Key保存在本地凭据管理器或环境变量中，**不要贴进聊天、报告、GitHub、公开截图或脚本源码**。不要使用别人的Key。

官方还提供“Agent申请＋邮件激活”方式，但必须先有用户明确同意及真实邮箱，不能杜撰邮箱或擅自发送申请。已有账号优先从设置页复制；邮件未激活的Key会返回`403 key_not_activated`。本Skill不会自动申请或发送邮件。

## 3. Windows PowerShell 安全输入（当前窗口有效）

在你自己的终端执行，提示时粘贴Key；输入不回显，命令历史不包含Key字面值：

```powershell
$openAlexSecret = Read-Host '粘贴 OpenAlex API Key（不会显示）' -AsSecureString
$env:OPENALEX_API_KEY = [System.Net.NetworkCredential]::new('', $openAlexSecret).Password
Remove-Variable openAlexSecret
python skills/literature-discovery-acquisition/scripts/openalex_access.py
python skills/literature-discovery-acquisition/scripts/openalex_access.py --online
```

环境变量中的值仍是进程可读明文，不是加密保险箱；不要运行`Get-ChildItem Env:`、`echo $env:OPENALEX_API_KEY`来展示它。只检查布尔状态或运行诊断脚本。

当前窗口设置只传给此后从它启动的子进程；已经打开的桌面Agent/MCP服务不会自动获得。若要让以后启动的桌面宿主继承，可由用户明确选择再执行：

```powershell
# 可选：持久保存到当前Windows用户环境，不需要管理员权限。
# 仅在你愿意持久保存且当前环境变量已设好时执行。
[Environment]::SetEnvironmentVariable('OPENALEX_API_KEY', $env:OPENALEX_API_KEY, 'User')
```

随后完全退出并重新打开宿主及其MCP服务；若宿主仍没继承，需要从已配置终端启动或重新登录Windows。Windows用户环境变量不是加密存储，公用电脑不建议持久保存。

移除配置：

```powershell
Remove-Item Env:OPENALEX_API_KEY -ErrorAction SilentlyContinue
[Environment]::SetEnvironmentVariable('OPENALEX_API_KEY', $null, 'User')
```

## 4. macOS/Linux/WSL（当前终端有效）

```bash
read -r -s -p 'OpenAlex API Key: ' OPENALEX_API_KEY; printf '\n'
export OPENALEX_API_KEY
python3 skills/literature-discovery-acquisition/scripts/openalex_access.py --online
```

上述`read -s -p`示例适用于bash；zsh/fish请使用该shell的隐藏输入方式或凭据管理器。需要长期保存时优先使用本地凭据管理方案；不要把真实Key写进受版本控制的shell脚本。Windows与WSL环境各自独立，Windows配置不会自动等于WSL已配置。

## 5. 怎么判断已接入

- `key_configured=false`：当前进程没读到Key；按教程设置，再从同一进程环境重试。
- `key_configured=true`：只证明环境变量存在；离线状态`NOT_RUN`不表示有效。
- `--online`返回`online_validation=ACCEPTED`、退出码0：OpenAlex接受了配置，报告只输出额度响应头白名单，不输出Key。该请求只查一次`/rate-limit`，不是关键词搜索。
- `OPENALEX_KEY_NOT_ACTIVATED`：去邮箱完成激活；不要不停重试。
- `OPENALEX_AUTH_REQUIRED_OR_INVALID`：确认复制完整、Key未撤销、宿主已重启；若怀疑泄漏，在官网撤销/轮换。
- `OPENALEX_BUDGET_EXHAUSTED`：已明确预算不足，应等重置、减范围、改用其他来源或由用户自行选择付费。重复重试不会补充余额。
- `OPENALEX_RATE_LIMIT_OR_BUDGET`：仅凭429无法区分，查看安全处理后的响应与剩余额度；瞬时限速可退避，不能直接宣称日额度耗尽。当前脚本不会自动无限重试。

`X-RateLimit-Remaining`与`X-RateLimit-Reset`帮助判断余额和距离重置的秒数。第三方工具可能自行认证、计费、缓存或使用其他出口，以该工具实际配置和响应为准。

## 6. 本套件具体怎么用 Key

`agent_search.py`的关键词搜索、种子查询、前向/后向引用，以及`download_oa_papers.py`的DOI OA解析均读取进程环境`OPENALEX_API_KEY`，通过Authorization头发送给HTTPS `api.openalex.org`，不拼进URL。没有配置则提示一次匿名限制，仍允许用户选择的匿名路径。

用同一终端执行原有命令即可，无须加含秘密的命令行参数：

```powershell
python skills/literature-discovery-acquisition/scripts/agent_search.py -q '你的研究主题' --execution-depth standard -o result.json
python skills/literature-discovery-acquisition/scripts/download_oa_papers.py -i result.json -o papers
```

Key不自动注入第三方MCP；给MCP配置时只按其官方支持方式设置环境，并重启服务后验证。不要把本地脚本成功当成所有工具都成功。

本脚本**不自动加载`.env`**；仅把Key放进文件而没有导入环境不生效。如自行使用dotenv，请确保文件不入版本控制、不被报告收集。可选`OPENALEX_MAILTO`仅填真实联系人，不增加配额，不用Skill作者或虚构邮箱冒充用户。

出版社直链PDF下载不使用OpenAlex Key，也不等于OpenAlex Content API付费下载；不能按下载篇数反推OpenAlex剩余额度。增加每页数量可减少请求；降低每页数量可能使同样结果花费更多请求。
