#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import sys
import json
import uuid
import time
import signal
import shutil
import gc
import subprocess
import platform
import zipfile
import hashlib
import base64
from pathlib import Path
from urllib.parse import quote
import urllib.request

# ======================================================================
# 核心配置区
# ======================================================================
DOMAIN = "example.com"            # 你的域名（Cloudflare 代理开启橙色云朵）
UUID = ""                         # 留空自动生成或写入固定值
PORT = ""                         # 留空将自动获取分配的端口
NODE_NAME = "Panel"               # 节点名称前缀
WSPATH = ""                       # 留空则基于 UUID 生成固定路径
# ======================================================================

class VLESSXrayProxy:
    def __init__(self, domain, user_uuid, config_port, node_name):
        self.uuid = user_uuid or os.environ.get("UUID") or str(uuid.uuid4())
        
        if WSPATH:
            self.path = WSPATH if WSPATH.startswith('/') else '/' + WSPATH
        else:
            path_hash = hashlib.md5(self.uuid.encode()).hexdigest()[:8]
            self.path = f"/{path_hash}"
            
        final_port = config_port or os.environ.get("PORT") or os.environ.get("SERVER_PORT")
        if not final_port:
            print("[!] 错误：无法获取有效端口。")
            sys.exit(1)
            
        self.port = int(final_port)
        self.domain = domain
        self.node_base_name = node_name
        self.process = None
        self.xray_dir = Path("./xray")
        self.xray_path = self.xray_dir / "xray"
        self.setup_signals()

    def setup_signals(self):
        def handler(signum, frame):
            self.cleanup()
            sys.exit(0)
        signal.signal(signal.SIGINT, handler)
        if hasattr(signal, "SIGTERM"):
            signal.signal(signal.SIGTERM, handler)

    def get_isp_info(self):
        print("[*] 正在查询 ISP 信息...")
        apis = [
            ("https://api.ip.sb/geoip", lambda d: f"{d['country_code']}-{d['organization']}"),
            ("https://www.cloudflare.com/cdn-cgi/trace", lambda d: next(l.split('=')[1] for l in d.split('\n') if l.startswith('loc=')) + "-CF")
        ]
        for url, parser in apis:
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=5) as res:
                    data = res.read().decode()
                    parsed = json.loads(data) if 'json' in res.getheader('Content-Type', '').lower() else data
                    isp = parser(parsed).replace(" ", "_")
                    print(f"[+] ISP 获取成功: {isp}")
                    return isp
            except:
                continue
        return "Unknown"

    def download_xray(self):
        if self.xray_path.exists():
            return True
        machine = platform.machine().lower()
        arch = "64" if "x86" in machine or "amd64" in machine else "arm64-v8a"
        url = f"https://github.com/XTLS/Xray-core/releases/latest/download/Xray-linux-{arch}.zip"
        try:
            print(f"[*] 下载 Xray 内核 ({arch})...")
            urllib.request.urlretrieve(url, "xray.zip")
            with zipfile.ZipFile("xray.zip", "r") as zip_ref:
                self.xray_dir.mkdir(exist_ok=True)
                zip_ref.extract("xray", path=self.xray_dir)
            os.chmod(self.xray_path, 0o755)
            os.remove("xray.zip")
            return True
        except Exception as e:
            print(f"[!] 下载失败: {e}")
            return False

    def start(self):
        if not self.download_xray(): return False

        # 生成 Xray 配置
        config = {
            "log": {"loglevel": "error"},
            "inbounds": [{
                "port": self.port,
                "protocol": "vless",
                "settings": {"clients": [{"id": self.uuid}], "decryption": "none"},
                "streamSettings": {"network": "ws", "wsSettings": {"path": self.path}}
            }],
            "outbounds": [{"protocol": "freedom"}],
            "policy": {"levels": {"0": {"bufferSize": 64, "connIdle": 120}}}
        }
        with open("config.json", "w") as f:
            json.dump(config, f, indent=2)

        isp = self.get_isp_info()
        node_full_name = f"{self.node_base_name}-{isp}"
        raw_link = f"vless://{self.uuid}@{self.domain}:443?encryption=none&security=tls&type=ws&host={quote(self.domain)}&path={quote(self.path)}&sni={quote(self.domain)}#{quote(node_full_name)}"
        b64_link = base64.b64encode(raw_link.encode()).decode()
        
        # --- 写入文件逻辑 ---
        try:
            with open("vless_xray_links.txt", "w", encoding="utf-8") as f:
                f.write(b64_link + "\n")
            print("[+] 订阅已写入 vless_xray_links.txt")
        except Exception as e:
            print(f"[!] 写入文件失败: {e}")

        # 输出到控制台
        print("\n" + "="*60)
        print("🔗 VLESS 订阅链接 (Base64)::")
        print(b64_link)
        print("="*60 + "\n")

        # 启动进程
        env = os.environ.copy()
        env.update({"GOMEMLIMIT": "15MiB", "GOGC": "15"})
        self.process = subprocess.Popen(
            [str(self.xray_path), "run", "-config", "config.json"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env
        )
        return True

    def cleanup(self):
        if self.process: self.process.terminate()
        for f in ["config.json", "xray.zip"]:
            if os.path.exists(f): os.remove(f)

def main():
    gc.enable()
    proxy = VLESSXrayProxy(DOMAIN, UUID, PORT, NODE_NAME)
    if proxy.start():
        print(f"\n✅ 服务运行中：{proxy.port}")
        try:
            while True:
                time.sleep(30)
                if proxy.process.poll() is not None:
                    print("[!] 进程退出，正在重启...")
                    proxy.start()
                gc.collect()
        except KeyboardInterrupt: pass
    proxy.cleanup()

if __name__ == "__main__":
    main()
