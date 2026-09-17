# eventernote-attendance

最小可用版 Eventernote 出勤率分析工具。

## 功能

- GitHub Actions 手动触发一次分析（`workflow_dispatch`）
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

### 1. 手动运行分析

在 GitHub 仓库的 **Actions** 页面运行 `Run Eventernote attendance analysis`，填写：

- `user_id`: Eventernote 用户 ID
- `actor_name`: 艺人名称
- `year`: 自然年

工作流会安装依赖、运行抓取脚本，并将结果写入 `data/latest-result.json`。

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
python scripts/fetch_attendance.py --user-id Tokuzawa353567 --actor-name 鈴木愛奈 --year 2025
```

## 结果格式

`data/latest-result.json` 在成功时会输出：

```json
{
  "status": "success",
  "user_id": "Tokuzawa353567",
  "requested_actor_name": "鈴木愛奈",
  "actor_name": "鈴木愛奈",
  "actor_id": "11198",
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
- 首版只面向“单用户 + 单艺人 + 单年份”的低频手动分析
- GitHub Pages 只是展示层，不负责触发抓取
- 当前运行环境如果无法访问 Eventernote，将只生成错误结果 JSON

## GitHub Pages 配置

建议在仓库设置中将 GitHub Pages 指向默认分支根目录（root）。
启用后，首页会读取 `data/latest-result.json` 并展示最新一次分析结果。
