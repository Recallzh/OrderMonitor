
# ==========================================
# 替换原来的 monitor_tybs_thread 函数
# ==========================================
def monitor_tybs_thread():
    global LATEST_TYBS_COUNT
    url = "https://tybs.onewo.com/api/dc-incident/town-api/list/queryIncidentCount"

    print("🔍 Tybs 监控线程已启动，等待凭证...")

    while IS_RUNNING:
        # 1. 检查是否有凭证
        if not TYBS_CONFIG["HEADERS"]:
            time.sleep(2)
            continue

        # 2. 构造请求
        headers = TYBS_CONFIG["HEADERS"].copy()
        
        # --- 关键修复：清理可能导致冲突的 Header ---
        headers.pop('content-length', None)
        headers.pop('Content-Length', None)
        headers.pop('host', None)     # 移除 Host，让 requests 自动生成
        headers.pop('Host', None)
        headers.pop('Accept-Encoding', None) # 移除压缩标识，防止乱码
        headers['Content-Type'] = 'application/json'

        # 3. 打印一次调试信息 (仅在第一次获取到 Header 时)
        # 这里为了不刷屏，你可以手动看控制台有没有这行字
        # print(f"DEBUG: 正在使用 {headers.get('MOBILE')} 进行请求...")

        payload = {
            "pageNum": 1,
            "pageSize": 15,
            "searchStatus": "1", # 1 代表待处理
            "selectContent": "",
            "startTime": "",
            "endTime": "",
            "projectCode": "",
            "businessTypeList": [],
            "projectCodeList": ["32020085"]
        }

        try:
            response = requests.post(url, headers=headers, json=payload, verify=False, timeout=10)
            
            # 🔥🔥🔥 调试核心：如果状态码不是 200，打印出来 🔥🔥🔥
            if response.status_code != 200:
                print(f"\r\n❌ [Tybs Error] 状态码: {response.status_code}")
                print(f"❌ 返回内容: {response.text}")
                # 如果是 401/403，说明凭证真的过期了或者签名不对
                if response.status_code in [401, 403]:
                    TYBS_CONFIG["HEADERS"] = {} 
                    print("⚠️ 凭证失效，已清空，请在浏览器刷新 Tybs 页面。")
            
            else:
                # 状态码是 200，但也许 JSON 结构变了？
                try:
                    res_json = response.json()
                    # print(f"DEBUG 返回: {res_json}") # 如果还是不显示，取消这行的注释看看返回了什么
                    
                    if 'data' in res_json and 'tobeProcessedCount' in res_json['data']:
                        count = res_json['data']['tobeProcessedCount']
                        LATEST_TYBS_COUNT = count
                        
                        if count > 0:
                            print(f"\r\n🔔 [Tybs工作台] 发现 {count} 个待处理工单！ \a")
                    else:
                        print(f"\r\n❌ [Tybs 数据异常] 找不到 count 字段: {res_json}")
                except Exception as e:
                    print(f"\r\n❌ [Tybs JSON解析失败] {e} | 内容: {response.text[:100]}")

        except Exception as e:
            # 🔥🔥🔥 把之前的 pass 改成了 print 🔥🔥🔥
            print(f"\r\n❌ [Tybs 请求报错] {e}")
            
        time.sleep(MONITOR_INTERVAL)
