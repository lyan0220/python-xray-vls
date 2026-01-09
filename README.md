# Pterodactyl面板Python环境

## 部署方式：上传文件 app.py

* 启动命令
```
python app.py
```

## 注意
1. 节点只支持 CDN 模式，请确保域名(example.com) 已在 Cloudflare 解析并开启代理。
2. 你需要通过 Cloudflare 的 **Origin Rules** 将流量路由到代理监听端口: (面板分配端口)
3. Cloudflare 的 SSL/TLS 加密模式必须为 **灵活 (Flexible)**。
