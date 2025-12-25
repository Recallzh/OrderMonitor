import requests
import json
import urllib3
import base64
import uuid
import time
import datetime
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_v1_5

# ================= 🔧 全局配置 (会自动更新) 🔧 =================
# 这些变量现在是动态的，会被本地服务器更新
GLOBAL_CONFIG = {
    "TOKEN": "",
    "COOKIE": "",
    "SYSTEM_ID": "0e9e407230db4436a56ca1d0df23c255", # 默认值，也会更新
    "TYPE_HEADER": "heimdallr"
}

MONITOR_INTERVAL = 30 # 刷新间隔(秒)
LOCAL_PORT = 8899     # 本地通信端口

# ==========================================================

LATEST_ORDERS = []
IS_RUNNING = True
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 模块1: 本地 HTTP 服务器 (接收浏览器发来的参数) ---
class ConfigHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        global GLOBAL_CONFIG
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            new_config = json.loads(post_data.decode('utf-8'))
            
            # 更新全局配置
            if 'token' in new_config: GLOBAL_CONFIG["TOKEN"] = new_config['token']
            if 'cookie' in new_config: GLOBAL_CONFIG["COOKIE"] = new_config['cookie']
            if 'systemId' in new_config: GLOBAL_CONFIG["SYSTEM_ID"] = new_config['systemId']
            
            print(f"\n\n♻️  [{datetime.datetime.now().strftime('%H:%M:%S')}] 收到浏览器更新！Token已自动刷新。")
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        except Exception as e:
            print(f"接收配置出错: {e}")

def run_server():
    server = HTTPServer(('localhost', LOCAL_PORT), ConfigHandler)
    print(f"📡 本地监听端口 {LOCAL_PORT} 已启动，等待浏览器投喂数据...")
    server.serve_forever()

# --- 模块2: 加密逻辑 ---
def get_security_headers():
    nonce = str(uuid.uuid4())
    timestamp = str(int(time.time() * 1000))
    public_key_str = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAg7jHfGUlvynIWwa9UNls5DFABtoVwVXBPZ3bVNUtai2xoTjI3q0xOoV3V5qgIEJdcxUQbKBQ1I2JMUXBkNoVFanbC9znnb4cyThMejwZQvMfC6tx+gr27UZey3spGM0TmhRMbczmD/yKk3Io0Ui6P3woNY6GERlO/H4xsPdrv97UGFwOSaMJnabOfgrs5etEGGxeBZ9ge4cdsAH2o8Le3lnFA0x40SBIgm+RevEuyxwKNxQu/1t3QklVs1m+s9WMYv9fZp39gDuzLpiCR8lsL8nWoYWf0mQcsErWXa8Jjn1oayztEN94/XtahZS+17PfOxTBL3iGhIBmiUEgESP6VQIDAQAB
-----END PUBLIC KEY-----"""
    try:
        key = RSA.import_key(public_key_str)
        cipher = PKCS1_v1_5.new(key)
        payload = f"nonce={nonce}".encode('utf-8')
        ciphertext = cipher.encrypt(payload)
        sign = base64.b64encode(ciphertext).decode('utf-8')
        return {"nonce": nonce, "timestamp": timestamp, "sign": sign}
    except Exception as e:
        return None

# --- 模块3: 监控逻辑 ---
def monitor_thread_func():
    global LATEST_ORDERS
    url = "https://heimdallr.onewo.com/api/task/courier/admin/task/work-order/queryCourierTaskWorkOrderEtlPage"

    while IS_RUNNING:
        # 还没收到 Token 时，先空转
        if not GLOBAL_CONFIG["TOKEN"]:
            time.sleep(2)
            continue

        security_data = get_security_headers()
        if not security_data:
            time.sleep(5)
            continue

        headers = {
            "Accept": "application/json, text/plain, */*",
            "Authorization": GLOBAL_CONFIG["TOKEN"],
            "COMPANY": "00000000000000000000000000000000",
            "Content-Type": "application/json",
            "Need-Permission": "false",
            "Origin": "https://heimdallr.onewo.com",
            "Referer": "https://heimdallr.onewo.com/remote-event-center-new/",
            "System-Tag": "web",
            "USER": "3abf642db9b84f1a8958920cde509aed",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Cookie": GLOBAL_CONFIG["COOKIE"],
            "nonce": security_data["nonce"],
            "timestamp": security_data["timestamp"],
            "sign": security_data["sign"],
            "systemId": GLOBAL_CONFIG["SYSTEM_ID"],
            "type": GLOBAL_CONFIG["TYPE_HEADER"]
        }

        # 仅包含待接受
        target_status = "['1', '1001', '1002', '1003', '1004', '1005', '1013', '1014', '4040']"

        payload = {
            "workorderStatus": target_status,
            "fmWoType": "OD",
            "current": 1,
            "limit": 20,
            "startTime": "2025-09-27 00:00:00",
            "endTime": "2025-12-28 23:59:59",
            "type": "1"
        }

        try:
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=15)
            
            if response.status_code == 200:
                result = response.json()
                data_block = result.get('data')

                if data_block:
                    raw_list = data_block.get('records') or data_block.get('rows') or []
                else:
                    raw_list = []

                # 只留状态为 1 (待接受) 的
                LATEST_ORDERS = [x for x in raw_list if x.get('workorderStatus') == '1']

                count = len(LATEST_ORDERS)
                current_time = datetime.datetime.now().strftime("%H:%M:%S")

                if count > 0:
                    print(f"\r\n[{current_time}] 🔴 警告：发现 {count} 个 待处理工单！(输入 ls 查看) \a")
                else:
                    print(f"\r[{current_time}] 监控运行中... 暂无数据   ", end="")
            elif response.status_code == 401:
                print(f"\r\n[{datetime.datetime.now().strftime('%H:%M:%S')}] ⚠️  Token 已过期，等待浏览器自动刷新...", end="")
            else:
                print(f"\r❌ 接口异常: {response.status_code}", end="")

        except Exception as e:
            print(f"\r❌ 网络错误: {e}", end="")
        
        time.sleep(MONITOR_INTERVAL)

# --- 主程序 ---
def main():
    global IS_RUNNING
    print("\n=== OD工单监控系统 (浏览器联动版) ===")
    print("🚀 系统启动中...")

    # 1. 启动接收服务器线程
    t_server = threading.Thread(target=run_server)
    t_server.daemon = True
    t_server.start()

    # 2. 启动监控线程
    t_monitor = threading.Thread(target=monitor_thread_func)
    t_monitor.daemon = True
    t_monitor.start()

    print("\n👉 请确保浏览器已安装油猴脚本，并打开了工单页面。")
    print("👉 等待第一次数据同步...\n")

    while True:
        cmd = input().strip().lower()
        if cmd == 'ls':
            count = len(LATEST_ORDERS)
            if count == 0:
                print("\n✅ 当前无新工单。")
            else:
                print(f"\n{'='*20} 新工单列表 ({count}) {'='*20}")
                for i, order in enumerate(LATEST_ORDERS):
                    print(f"{i+1}. 状态: 【{order.get('workorderStatusName')}】")
                    print(f"   单号: {order.get('workorderNo')}")
                    print(f"   标题: {order.get('workorderTitle')}")
                    print(f"   地址: {order.get('address')}")
                    print(f"   描述: {order.get('workorderDescription')[:30]}...") 
                    print("-" * 40)
                print("================================================\n")
        elif cmd == 'q':
            IS_RUNNING = False
            print("正在退出...")
            break

if __name__ == "__main__":
    main()


