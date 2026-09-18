# v2 动态版本

当前目录是按 `doc/v2-dynamic-frontend-plan.md` 启动的升级实现。

## 包含内容

- `index.html`：实时分析页面
- `app.js`：直接调用分析接口并渲染结果
- `style.css`：v2 页面样式
- `data/runtime-config.json`：前端接口地址配置
- `backend/api.py`：统一请求校验与 JSON 响应封装
- `backend/server.py`：可直接运行的 HTTP API

## 本地运行

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m v2.backend.server --host 127.0.0.1 --port 8000
python -m http.server 8081 -d v2
```

默认情况下，通过 `http://127.0.0.1:8081/` 打开的页面会请求：

- `http://127.0.0.1:8000/api/analyze`（本地 HTTP 访问时）
- `<当前站点>/api/analyze`（同域部署时）
- `v2/data/runtime-config.json` 中配置的 `analyze_api_url`（显式覆盖时）

如果页面本身通过 HTTPS 打开，则 `analyze_api_url` 也必须是 HTTPS 地址。

如果前端和 API 分域部署，请在 API 启动时显式配置：

```bash
python -m v2.backend.server --host 127.0.0.1 --port 8000 --allow-origin https://<your-frontend-origin>
```

如果直接以 `file://` 打开 `v2/index.html`，浏览器会发送 `Origin: null`；这种模式下需要显式启动：

```bash
python -m v2.backend.server --host 127.0.0.1 --port 8000 --allow-origin null
```
