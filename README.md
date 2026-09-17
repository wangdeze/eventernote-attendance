# eventernote-attendance

最小可用版 Eventernote 出勤率分析工具。

## 功能

- 从 GitHub Pages 网页发起一次分析请求
- 输入 Eventernote 用户 ID、艺人名称、年份
- 内部自动解析艺人名称到 Eventernote 艺人页/ID
- 抓取用户活动页与艺人活动页，过滤指定年份并匹配活动
- 生成 `data/latest-result.json`
- GitHub Pages 静态页面展示分析结果、错误信息和活动明细

## 仓库结构

```text
.
├── .github/workflows/run-analysis.yml
├── app.js
├── data/latest-result.json
├── doc/requirements-and-plan.md
├── index.html
├── requirements.txt
├── scripts/fetch_attendance.py
├── style.css
└── tests/test_fetch_attendance.py
```

## 使用方式

### 1. 从网页提交分析请求

打开 GitHub Pages 首页，填写：

- `user_id`: Eventernote 用户 ID
- `actor_name`: 艺人名称
- `year`: 自然年

页面对外只保留一个“提交分析请求”按钮：默认会跳转到 GitHub issue 创建页；当你把请求模式切换为 `proxy` 后，会优先通过轻量中间层（例如 Cloudflare Worker / Vercel Function）提交参数，由中间层在仓库内自动创建请求 issue 并触发分析 workflow，最终结果写入 `data/latest-result.json`。

> 对外页面只暴露一个“提交分析请求”按钮；若未配置中间层，同一个按钮会回退到 GitHub issue 创建页。
>
> 如果你是仓库维护者，也可以继续在 **Actions** 页面手动运行 `Run Eventernote attendance analysis`。

### 1.1 中间层提交入口配置

仓库内置了 `data/request-config.json`：

```json
{
  "request_mode": "issue",
  "request_proxy_url": ""
}
```

- `request_mode=proxy`：页面优先走中间层提交；若 `request_proxy_url` 为空则回退到 GitHub issue 请求页
- `request_mode=issue`：页面直接使用同一个按钮跳转到 GitHub issue 请求页
- `request_proxy_url`：页面把表单 JSON `POST` 到该地址

当使用 `proxy` 模式时，中间层只需要接收：

```json
{
  "user_id": "<eventernote-user-id>",
  "actor_name": "<actor-name>",
  "year": "2025"
}
```

中间层收到请求后，建议执行两步：

1. 使用 GitHub API 创建 `analysis-request` issue（保留模板中的三行参数）  
2. 再调用 GitHub `repository_dispatch` 事件（`event_type=analysis-request`）触发当前仓库的 `Run Eventernote attendance analysis` workflow

这样可以同时保留请求审计记录（issue）和自动触发能力（dispatch）。

### 2. 查看结果

启用 GitHub Pages 后，打开站点首页即可查看：

- 用户 ID
- 艺人名称
- 年份
- 该艺人全年活动总数
- 用户已出席活动数
- 出勤率
- 已出席 / 未出席活动明细

页面本身不会直接抓取 Eventernote，而是读取仓库中的最新 JSON 结果。

## 本地开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m unittest discover -s tests
python scripts/fetch_attendance.py --user-id <eventernote-user-id> --actor-name <actor-name> --year <year>
```

## 结果格式

`data/latest-result.json` 在成功时会输出：

```json
{
  "status": "success",
  "user_id": "<user-id>",
  "requested_actor_name": "<actor-name>",
  "actor_name": "<resolved-actor-name>",
  "actor_id": "<actor-id>",
  "year": 2025,
  "total_actor_events": 48,
  "attended_events": 18,
  "attendance_rate": 0.375,
  "warnings": [],
  "events": []
}
```

抓取失败、页面结构变化或艺人名称解析失败时，脚本会改为输出 `status=error` 的 JSON，静态页面也会展示错误信息。

## 限制

- 依赖 Eventernote 公开页面，页面结构变化时可能需要更新解析逻辑
- 每次只处理“单用户 + 单艺人 + 单年份”的低频分析请求
- GitHub Pages 请求入口优先依赖中间层地址；未配置时会回退到 GitHub issue 请求页
- 当前运行环境如果无法访问 Eventernote，将只生成错误结果 JSON

## GitHub Pages 配置

建议在仓库设置中将 GitHub Pages 指向默认分支根目录（root）。
启用后，首页会读取 `data/latest-result.json` 并展示最新一次分析结果，同时提供公开分析请求入口。
