import os, time, uuid, hashlib, json, requests, base64, random

XC_BASE_URL = "https://gw.xiaocantech.com/rpc"
CONFIG_FILE = "config.json"

def get_md5(d: str) -> str:
    return hashlib.md5(d.encode('utf-8')).hexdigest()

def get_nami(silk_id="781947515"):
    silk_str = str(silk_id) if silk_id else "781947515"
    allowed_chars = "0123456789abcdef"
    prefix = "".join(random.choice(allowed_chars) for _ in range(4))
    suffix = "".join(random.choice(allowed_chars) for _ in range(3))
    return f"{prefix}{silk_str}{suffix}"

def get_ashe(server: str, method: str, t: int, nami: str) -> str:
    sm = (server + "." + method).lower()
    x = get_md5(sm)
    return get_md5(x + str(t) + str(nami))

def extract_userid_from_token(token: str) -> str:
    try:
        parts = token.split(".")
        if len(parts) >= 2:
            payload_b64 = parts[1]
            pad = len(payload_b64) % 4
            if pad > 0:
                payload_b64 += "=" * (4 - pad)
            decoded = base64.urlsafe_b64decode(payload_b64).decode('utf-8')
            data = json.loads(decoded)
            return str(data.get("UserId", ""))
    except Exception as e:
        print(f"[Warn] JWT parse exception: {e}")
    return ""

def grab_single_attempt(attempt_idx: int, config: dict, target_item: dict) -> dict:
    now = int(time.time() * 1000)
    token = config.get("XC_TOKEN", "")
    userid = config.get("USER_ID") or extract_userid_from_token(token) or "15043925"
    silkid = config.get("SILK_ID") or userid or "781947515"
    city_code = config.get("CITY_CODE", 370200)
    lat = config.get("LAT", 36.30335)
    lng = config.get("LNG", 120.38446)

    server = "Silkworm"
    method = "SilkwormService.GrabPromotionQuota"
    nami = get_nami(silkid)
    ashe = get_ashe(server, method, now, nami)

    headers = {
        "Content-Type": "application/json",
        "serverName": server,
        "methodName": method,
        "X-Ashe": ashe,
        "X-Garen": str(now),
        "X-Nami": nami,
        "x-City": str(city_code),
        "x-Sivir": token,
        "x-Vayne": str(userid),
        "x-Teemo": str(silkid),
        "X-App-Sr": "20",
        "X-Platform": "mini",
        "X-Version": "3.21.4.79",
        "version": "3.21.4.79",
        "x-Annie": "XC",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541d41) XWEB/25560",
        "Referer": "https://servicewechat.com/wx52ae177248081591/810/page-frame.html",
        "xweb_xhr": "1"
    }

    payload = {
        "silk_id": int(silkid),
        "latitude": float(lat),
        "longitude": float(lng),
        "city_code": int(city_code),
        "promotion_id": int(target_item["promotion_id"]),
        "store_platform": 1 if target_item.get("platform") == "美团" else 2,
        "if_advance_order": target_item.get("is_advance", True),
        "if_pre_order": False,
        "app_id": 20
    }

    t_str = time.strftime("%H:%M:%S", time.localtime(now / 1000)) + f".{now % 1000:03d}"
    print(f"\n==================== [第 {attempt_idx} 次抢单请求全量日志 | {t_str}] ====================")
    print("📍 [请求网关地址]:", XC_BASE_URL)
    print("📋 [请求标头 Headers]:")
    for hk, hv in headers.items():
        if hk == "x-Sivir":
            print(f"   {hk}: {hv[:35]}... (Len: {len(hv)})")
        else:
            print(f"   {hk}: {hv}")
    print("\n📦 [请求 JSON Body]:")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

    try:
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        t_start = time.time()
        resp = requests.post(XC_BASE_URL, headers=headers, json=payload, timeout=6, verify=False)
        t_cost = (time.time() - t_start) * 1000
        res_text = resp.text
        try:
            res_json = resp.json()
        except:
            res_json = {"raw": res_text}

        status_code = resp.status_code
        print(f"\n📥 [响应结果 (HTTP {status_code}) | 耗时: {t_cost:.1f}ms]:")
        print(json.dumps(res_json, ensure_ascii=False, indent=2))
        print("========================================================================================\n")

        return {
            "attempt": attempt_idx,
            "time": t_str,
            "status_code": status_code,
            "response": res_json
        }
    except Exception as e:
        print(f"\n❌ [网络请求异常]: {e}")
        return {
            "attempt": attempt_idx,
            "time": t_str,
            "status_code": -1,
            "response": f"请求网络异常: {e}"
        }

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cfg_path = os.path.join(base_dir, CONFIG_FILE)

    with open(cfg_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    # 目标活动配置（甘煸记·干煸辣子鸡（青岛城阳万象汇店））
    target_item = {
        "name": "甘煸记·干煸辣子鸡（青岛城阳万象汇店）",
        "promotion_id": 133398245,
        "store_id": 2506622,
        "platform": "美团",
        "is_advance": True
    }

    print("=" * 75)
    print(f"🎯 目标店铺: {target_item['name']}")
    print(f"   promotion_id: {target_item['promotion_id']}")
    print(f"   store_id: {target_item['store_id']}")
    print(f"   platform: {target_item['platform']}")
    print(f"   is_advance: {target_item['is_advance']}")
    print("=" * 75)

    # 3次并发重试 (0ms, 300ms, 600ms)
    attempts = [1, 2, 3]
    delays = [0, 0.3, 0.6]

    for idx, d in zip(attempts, delays):
        if d > 0:
            time.sleep(d)
        res = grab_single_attempt(idx, config, target_item)

        # 检查是否成功
        if isinstance(res['response'], dict):
            status_obj = res['response'].get("status", {})
            if status_obj.get("code") == 0:
                order_id = res['response'].get("promotion_order_id")
                timeout_ts = res['response'].get("timeout")
                honesty_msg = res['response'].get("honesty_msg")
                print("\n" + "🎉" * 25)
                print(f"抢单成功！！推广订单号: {order_id}")
                print(f"超时时间戳: {timeout_ts}")
                if honesty_msg:
                    print(f"诚信提示: {honesty_msg}")
                print("🎉" * 25)
                break

if __name__ == "__main__":
    main()
