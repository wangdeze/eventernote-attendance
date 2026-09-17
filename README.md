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

默认情况下，点击“打开 GitHub 请求页”后会在当前页跳转到 GitHub issue 创建页，提交该 issue 后，仓库 workflow 会自动运行分析并将结果写入 `data/latest-result.json`。

如果后续给页面配置了轻量中间层请求入口（例如 Cloudflare Worker / Vercel Function），页面也可以直接提交请求，再由中间层触发同一个 workflow，而不需要改动分析主流程。

> 出于仓库安全考虑，issue 触发的自动分析只接受受信任的仓库协作者提交。
>
> 如果你是仓库维护者，也可以继续在 **Actions** 页面手动运行 `Run Eventernote attendance analysis`。

### 1.1 可选的直接提交入口配置

仓库内置了 `data/request-config.json`：

```json
{
  "request_mode": "issue",
  "request_proxy_url": ""
}
```

- `request_mode=issue`：页面使用 GitHub issue 作为请求入口
- `request_mode=proxy`：页面把表单 JSON `POST` 到 `request_proxy_url`

当使用 `proxy` 模式时，中间层只需要接收：

```json
{
  "user_id": "<eventernote-user-id>",
  "actor_name": "<actor-name>",
  "year": "2025"
}
```

然后再调用 GitHub `repository_dispatch` 事件（`event_type=analysis-request`）触发当前仓库的 `Run Eventernote attendance analysis` workflow。

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
- GitHub Pages 默认会把参数带到 GitHub issue 请求页；如果配置了轻量中间层，也可以改为由中间层直接触发 GitHub Actions
- 当前运行环境如果无法访问 Eventernote，将只生成错误结果 JSON

## GitHub Pages 配置

建议在仓库设置中将 GitHub Pages 指向默认分支根目录（root）。
启用后，首页会读取 `data/latest-result.json` 并展示最新一次分析结果，同时提供公开分析请求入口。
