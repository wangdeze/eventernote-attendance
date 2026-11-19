# Ubuntu 24.04 私人服务器部署

适用于已经配置 HTTPS 的 Nginx 服务器。使用独立的 `deploy` 用户（无需 sudo）、
Gunicorn 和 systemd；整站通过 HTTPS Basic Auth 保护。不要公开 8000 端口，
不要将本地调试用的 `v2.backend.server` 用于公网部署。

下面用 `attendance.tqs.homes` 举例。管理员和 deploy 的命令必须分别执行。
仓库代码先上传或发布，再在服务器执行；本地工作区的改动不会自动出现在 GitHub。

## 1. 管理员准备目录

```bash
sudo apt update
sudo apt install -y python3-venv git nginx apache2-utils
sudo install -d -m 755 -o deploy -g deploy /srv/eventernote
```

## 2. deploy 安装应用

以 deploy 登录后执行（如果仓库私有，需要你配置独立的只读仓库访问权限，
不要把访问令牌写入 clone URL 或聊天）：

```bash
git clone --branch v2 --single-branch https://github.com/wangdeze/eventernote-attendance.git /srv/eventernote/app
python3 -m venv /srv/eventernote/venv
/srv/eventernote/venv/bin/pip install -r /srv/eventernote/app/deploy/requirements.txt
install -d -m 755 /srv/eventernote/www/data
install -m 644 /srv/eventernote/app/v2/index.html /srv/eventernote/app/v2/app.js /srv/eventernote/app/v2/style.css /srv/eventernote/www/
install -m 644 /srv/eventernote/app/v2/data/runtime-config.json /srv/eventernote/www/data/
```

只发布这些静态文件，不要把仓库或整个 `v2/` 目录作为 Nginx 网站根目录。
默认 runtime-config 已支持同域 `/api/analyze`，无需修改本地调试配置。

## 3. 管理员启用后端和网站密码

```bash
sudo install -m 644 /srv/eventernote/app/deploy/eventernote.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now eventernote
curl --fail http://127.0.0.1:8000/health
sudo htpasswd -cB /etc/nginx/eventernote.htpasswd attendance
sudo chown root:www-data /etc/nginx/eventernote.htpasswd
sudo chmod 640 /etc/nginx/eventernote.htpasswd
sudo install -m 644 /srv/eventernote/app/deploy/eventernote-limits.conf /etc/nginx/conf.d/
sudo install -m 644 /srv/eventernote/app/deploy/eventernote.nginx.conf /etc/nginx/snippets/
```

`htpasswd` 会交互式提示输入网站密码；不要把密码作为命令行参数或发到聊天。
这里的 `attendance` 是网站用户名，不是系统用户。只有首次创建密码文件使用 `-c`；
增加用户或修改密码时用 `sudo htpasswd -B /etc/nginx/eventernote.htpasswd 用户名`。

找到当前站点配置：

```bash
sudo nginx -T
```

在属于 `attendance.tqs.homes`、监听 HTTPS 443 的 `server` 块中，
保留 Certbot 的证书和 TLS 配置，删除该块原有的 `root`、`index` 和 `location /`，
然后添加：

```nginx
include /etc/nginx/snippets/eventernote.nginx.conf;
```

不要添加到仅用于 HTTP 跳转的 server 块，不要覆盖整个 Certbot 配置。
不要留下额外可绕过认证的静态文件或 API location。随后：

```bash
sudo nginx -t && sudo systemctl reload nginx
```

## 4. 验证

```bash
curl -I https://attendance.tqs.homes/
curl -i -X POST -H 'Content-Type: application/json' --data '{}' https://attendance.tqs.homes/api/analyze
curl -u attendance https://attendance.tqs.homes/data/runtime-config.json
curl -u attendance -H 'Content-Type: application/json' --data '{}' https://attendance.tqs.homes/api/analyze
```

前两项未带密码，必须返回 401；第三项提示输入密码，成功后应返回配置 JSON；
第四项认证后应返回参数校验错误 JSON（HTTP 400），而不是 404、502 或 HTML。
浏览器打开站点，输入网站账号密码，再用真实参数进行一次分析。
检查外部不能直接连接 8000 端口，并且 HTTP 只跳转到 HTTPS，不提供页面或 API。

每个 IP 的分析请求限速为每分钟一次，可突发额外两次，整站最多两个并行分析连接。
单次分析最长约十分钟；超时会终止 Gunicorn 工作进程并返回网关错误，
不会生成假的成功结果。当前版本不提供持久任务队列，超时后需重试。
Basic Auth 没有独立的注销页面，浏览器可能缓存凭据；只在可信设备上使用。

故障排查：

```bash
sudo systemctl status eventernote --no-pager
sudo journalctl -u eventernote -n 50 --no-pager
sudo tail -n 50 /var/log/nginx/error.log
```

## 更新

deploy 用户在 `/srv/eventernote/app` 执行 `git pull --ff-only`，
重新执行依赖安装与静态文件发布命令。管理员执行
`sudo systemctl restart eventernote`，然后重复验证。
如果更新了 systemd 或 Nginx 模板，需要管理员重新安装对应配置并检查后再重载。
这是手动部署流程；尚未配置 GitHub Actions 自动部署。
