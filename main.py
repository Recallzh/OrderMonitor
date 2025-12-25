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

# ================= 🔧 全局配置 (动态更新) 🔧 =================
# 1. Heimdallr (旧的那个)
HEIMDALLR_CONFIG = {
    "TOKEN": "",
    "COOKIE": "",
    "SYSTEM_ID": "0e9e407230db4436a56ca1d0df23c255",
    "TYPE_HEADER": "heimdallr"
}

# 2. Tybs (新的这个 - 工作台)
TYBS_CONFIG = {
    "HEADERS": {} # 直接存储整个 Header 字典
}

MONITOR_INTERVAL = 30 # 刷新间隔(秒)
LOCAL_PORT = 8899     # 本地通信端口

# 状态存储
LATEST_HEIMDALLR_ORDERS = []
LATEST_TYBS_COUNT = -1 # -1表示未初始化
IS_RUNNING = True

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# --- 模块1: 本地 HTTP 服务器 (接收双路数据) ---
class ConfigHandler(BaseHTTPRequestHandler):
    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_POST(self):
        global HEIMDALLR_CONFIG, TYBS_CONFIG
        content_length = int(self.headers['Content-Length'])
        post_data = self.rfile.read(content_length)
        
        try:
            data = json.loads(post_data.decode('utf-8'))
            source = data.get('source')
            current_time = datetime.datetime.now().strftime('%H:%M:%S')

            if source == 'heimdallr':
                # 更新旧系统配置
                if 'token' in data: HEIMDALLR_CONFIG["TOKEN"] = data['token']
                if 'cookie' in data: HEIMDALLR_CONFIG["COOKIE"] = data['cookie']
                if 'systemId' in data: HEIMDALLR_CONFIG["SYSTEM_ID"] = data['systemId']
                print(f"♻️  [{current_time}] Heimdallr 凭证已更新")

            elif source == 'tybs':
                # 更新新系统配置 (直接存 Headers)
                TYBS_CONFIG["HEADERS"] = data.get('headers', {})
                print(f"♻️  [{current_time}] Tybs 工作台凭证已更新")
            
            self.send_response(200)
            self.send_header('Access-Control-Allow-Origin', '*')
            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(b'{"status":"ok"}')
        except Exception as e:
            print(f"配置接收错误: {e}")

def run_server():
    server = HTTPServer(('localhost', LOCAL_PORT), ConfigHandler)
    print(f"📡 本地监听端口 {LOCAL_PORT} 已启动...")
    server.serve_forever()

# --- 模块2: 辅助加密 (Heimdallr专用) ---
def get_heimdallr_security():
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
    except:
        return None

# --- 模块3: Tybs 监控线程 (新功能) ---
def monitor_tybs_thread():
    global LATEST_TYBS_COUNT
    url = "https://tybs.onewo.com/api/dc-incident/town-api/list/queryIncidentCount"

    while IS_RUNNING:
        # 1. 检查是否有凭证
        if not TYBS_CONFIG["HEADERS"]:
            time.sleep(3)
            continue

        # 2. 构造请求
        # 注意：这里直接使用浏览器传过来的 Header，但也需要手动覆盖一些不应该被缓存的
        headers = TYBS_CONFIG["HEADERS"].copy()
        # 移除可能引起问题的 content-length 或 host，保留核心鉴权参数
        headers.pop('content-length', None)
        headers.pop('Content-Length', None)
        headers['Content-Type'] = 'application/json'

        # 固定 Payload (根据你的 curl)
        payload = {
            "pageNum": 1,
            "pageSize": 15,
            "searchStatus": "1",
            "selectContent": "",
            "startTime": "",
            "endTime": "",
            "projectCode": "",
            "businessTypeList": [],
            "projectCodeList": ["32020085"]
        }

        try:
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            if response.status_code == 200:
                res_json = response.json()
                # 提取 tobeProcessedCount
                if 'data' in res_json and 'tobeProcessedCount' in res_json['data']:
                    count = res_json['data']['tobeProcessedCount']
                    LATEST_TYBS_COUNT = count
                    
                    if count > 0:
                        print(f"\r\n🔔 [Tybs工作台] 发现 {count} 个待处理工单！ \a")
                else:
                    # 格式不对
                    pass
            elif response.status_code == 401 or response.status_code == 403:
                # 凭证失效，清空等待更新
                TYBS_CONFIG["HEADERS"] = {}
                print("\r\n⚠️ [Tybs] 凭证失效，请在浏览器刷新 Tybs 页面...")
        except Exception as e:
            # print(f"Tybs Error: {e}")
            pass
            
        time.sleep(MONITOR_INTERVAL)

# --- 模块4: Heimdallr 监控线程 (旧功能) ---
def monitor_heimdallr_thread():
    global LATEST_HEIMDALLR_ORDERS
    url = "https://heimdallr.onewo.com/api/task/courier/admin/task/work-order/queryCourierTaskWorkOrderEtlPage"

    while IS_RUNNING:
        if not HEIMDALLR_CONFIG["TOKEN"]:
            time.sleep(2)
            continue

        sec = get_heimdallr_security()
        if not sec: continue

        headers = {
            "Authorization": HEIMDALLR_CONFIG["TOKEN"],
            "Cookie": HEIMDALLR_CONFIG["COOKIE"],
            "systemId": HEIMDALLR_CONFIG["SYSTEM_ID"],
            "nonce": sec["nonce"],
            "timestamp": sec["timestamp"],
            "sign": sec["sign"],
            "type": HEIMDALLR_CONFIG["TYPE_HEADER"],
            "Content-Type": "application/json",
            "COMPANY": "00000000000000000000000000000000",
            "USER": "3abf642db9b84f1a8958920cde509aed",
            "Need-Permission": "false"
        }

        payload = {
            "workorderStatus": "['1', '1001', '1002', '1003', '1004', '1005', '1013', '1014', '4040']", 
            "fmWoType": "OD",
            "current": 1, "limit": 20,
            "startTime": "2025-09-27 00:00:00",
            "endTime": "2026-12-28 23:59:59",
            "type": "1"
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            if resp.status_code == 200:
                data = resp.json().get('data', {})
                raw_list = data.get('records') or data.get('rows') or []
                LATEST_HEIMDALLR_ORDERS = [x for x in raw_list if x.get('workorderStatus') == '1']
                
                if len(LATEST_HEIMDALLR_ORDERS) > 0:
                    print(f"\r\n🔴 [Heimdallr] 发现 {len(LATEST_HEIMDALLR_ORDERS)} 个新工单！ \a")
            elif resp.status_code == 401:
                HEIMDALLR_CONFIG["TOKEN"] = ""
                print("\r\n⚠️ [Heimdallr] Token 过期，等待浏览器更新...")
        except:
            pass
            
        time.sleep(MONITOR_INTERVAL)

# --- 主程序 ---
def main():
    global IS_RUNNING
    print("\n=== 双系统工单监控终端 (v3.0) ===")
    print("1. Tybs工作台 (待处理计数)")
    print("2. Heimdallr系统 (新单详情)")
    print("--------------------------------")

    # 启动所有线程
    threading.Thread(target=run_server, daemon=True).start()
    threading.Thread(target=monitor_tybs_thread, daemon=True).start()
    threading.Thread(target=monitor_heimdallr_thread, daemon=True).start()

    print("\n🚀 系统已启动，等待浏览器投喂凭证...")

    while True:
        current_time = datetime.datetime.now().strftime("%H:%M:%S")
        
        # 构建显示状态
        tybs_status = "等待凭证..."
        if TYBS_CONFIG["HEADERS"]:
            tybs_status = f"{LATEST_TYBS_COUNT} 个" if LATEST_TYBS_COUNT >= 0 else "检测中..."
            if LATEST_TYBS_COUNT > 0: tybs_status += " [!] "

        heim_status = "等待凭证..."
        if HEIMDALLR_CONFIG["TOKEN"]:
            c = len(LATEST_HEIMDALLR_ORDERS)
            heim_status = f"{c} 个" if c >= 0 else "检测中..."
            if c > 0: heim_status += " [!] "

        # 单行刷新显示
        print(f"\r[{current_time}] Tybs待办: {tybs_status}  |  Heimdallr待办: {heim_status}      ", end="")
        
        # 简单命令处理
        # 这里为了不阻塞显示，使用非阻塞输入比较麻烦，所以还是保留之前的 ls 逻辑，但稍微改一下
        # 为了让 print \r 正常工作，我们稍微 sleep 一下，不需要一直狂刷
        time.sleep(1) 
        
        # 如果你想输入命令，可以在这里加 input，但会打断上面的即时刷新。
        # 建议直接通过上面的报警来看。如果一定要查 Heimdallr 详情，我们可以另开一个 input 线程，或者像下面这样简单的 hack:
        # (由于双线程监控，input 会卡住主线程刷新，所以这里推荐【只看报警，不手动查询】)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        IS_RUNNING = False
        print("\n退出...")
