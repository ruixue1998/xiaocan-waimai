import os, time, uuid, hashlib, json, requests
from typing import Dict, List, Optional

XC_BASE_URL, CONFIG_FILE, DATA_FILE, RAW_FILE, FILTER_FILE, NEW_FILE = \
    "https://gw.xiaocantech.com/rpc", "config.json", "data/xiaocan_shops.json", "data/xiaocan_raw.json", "filter_rules.json", "data/xiaocan_new.json"

def get_md5(d): return hashlib.md5(d.encode('utf-8')).hexdigest()
def get_nami(): u = str(uuid.uuid4()).replace("-", ""); return u[:4] + "0" + u[4:15]
def get_ashe(s, m, t, n): return get_md5(f"{get_md5(f'{s}.{m}'.lower())}{t}{n}")

def fetch_rpc(server, method, payload, token="", city_code=None):
    now, nami = int(time.time() * 1000), get_nami()
    ashe = get_ashe(server, method, now, nami)
    headers = {
        "Content-Type": "application/json", "servername": server, "methodname": method,
        "X-Ashe": ashe, "X-Garen": str(now), "X-Nami": nami, "appid": "20",
        "X-Platform": "mini", "version": "3.15.9.10", "X-Version": "3.15.9.10", "x-Annie": "XC",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/144.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Windows WindowsWechat/WMPF WindowsWechat(0x63090a13) UnifiedPCWindowsWechat(0xf2541d3f) XWEB/25558",
        "Referer": "https://servicewechat.com/wx52ae84595214/965/page-frame.html", "xweb_xhr": "1"
    }
    if token: headers["token"] = token
    if city_code: headers["x-City"] = str(city_code)
    try:
        import urllib3; urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
        resp = requests.post(XC_BASE_URL, headers=headers, json=payload, timeout=15, verify=False)
        return resp.json() if resp.status_code == 200 else {}
    except: return {}

def parse_item(item):
    is_shangjin = "ratio" in item
    store = item.get("store") or item
    name = store.get("name", "未知")
    dist_raw = item.get("distance") or item.get("delivery_distance") or 0
    dk = float(str(dist_raw).replace("km","")) if "km" in str(dist_raw) else round(float(str(dist_raw).replace("m",""))/1000, 2)
    st_h, st_m = item.get("start_time_hour", 0), item.get("start_time_minute", 0)
    is_advance = item.get("if_can_advance_order", False)
    now_t = time.localtime()
    is_scheduled = (st_h * 60 + st_m) > (now_t.tm_hour * 60 + now_t.tm_min)

    base = {"name": name, "source": "小蚕", "distance_km": dk, "address": store.get("address", ""), "logo": store.get("icon", ""), "start_time": f"{st_h:02d}:{st_m:02d}", "is_advance": is_advance, "is_scheduled": is_scheduled}

    results = []
    if is_shangjin:
        # 修正：优先使用 plan_activity_info_list 中的 user_ratio，否则 app 显示会偏大
        plans = item.get("plan_activity_info_list", [])
        main_plan = plans[0] if plans else item

        ratio_val = main_plan.get("user_ratio") or main_plan.get("ratio") or 0
        max_back_val = main_plan.get("user_max_commission") or main_plan.get("max_commission") or 0

        res = base.copy()
        res.update({
            "platform": "美团", "type": "赏金", "pay": 0.0, "back": 0.0,
            "ratio": round(float(ratio_val) / 10000, 4),
            "max_back": round(float(max_back_val) / 100, 2),
            "left": int(item.get("inventory") or 0)
        })
        results.append(res)
    else:
        for pk, pn in [("meituan", "美团"), ("eleme", "饿了么")]:
            if item.get(f"{pk}_status") == 1:
                left_count = int(item.get(f"{pk}_left_number") or 0)

                # 检查是否已过结束时间，如果已结束则视为无库存
                curr_ts = int(time.time())
                end_ts = item.get("end_date_timestamp", 0)
                if end_ts > 0 and curr_ts > end_ts:
                    left_count = 0

                res = base.copy()
                res.update({"type": "满减", "platform": pn, "pay": round(float(item.get(f"{pk}_order_money", 0))/100, 2), "back": round(float(item.get(f"{pk}_user_rebate", 0))/100, 2), "left": left_count})
                results.append(res)
    return results

def apply_filter(s, rules):
    name = s['name']
    cost = s.get("pay", 0) - s.get("back", 0)
    ratio = s.get("ratio") or 0

    # 1. 兴趣命中 (满足其一即可入围)
    is_interested = False
    if rules.get("include_keywords") and any(k in name for k in rules["include_keywords"]):
        is_interested = True

    if s.get("type") == "赏金":
        if ratio >= rules.get("min_ratio", 0.66):
            is_interested = True
    else:
        if cost <= rules.get("min_cost", 6.0):
            is_interested = True

    if not is_interested: return False

    # 2. 强制排除 (满足其一即被踢出)
    if any(k.lower() in name.lower() for k in rules.get("exclude_keywords", [])): return False
    if s['left'] < rules.get("min_inventory", 1): return False
    if s['distance_km'] > rules.get("max_distance", 5.0): return False
    if rules.get("only_available") and s['is_scheduled'] and not s['is_advance']: return False

    return True

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    def p(f): return os.path.join(base_dir, f)
    os.makedirs(p("data"), exist_ok=True)

    with open(p(CONFIG_FILE), 'r', encoding='utf-8') as f: config = json.load(f)
    token = os.environ.get("XC_TOKEN") or config.get("XC_TOKEN")
    lat = os.environ.get("LAT") or config.get("LAT")
    lng = os.environ.get("LNG") or config.get("LNG")
    city = os.environ.get("CITY_CODE") or config.get("CITY_CODE")
    if not city: city = config.get("cityCode")
    if not token: token = config.get("token", "")
    if "填入" in str(token): token = ""

    rules = {"include_keywords":[], "exclude_keywords":[], "min_cost":6.0, "min_inventory":2, "only_available":True}
    if os.path.exists(p(FILTER_FILE)):
        with open(p(FILTER_FILE), 'r', encoding='utf-8') as f: rules.update(json.load(f))

    old_shops = {}
    if os.path.exists(p(DATA_FILE)):
        try:
            with open(p(DATA_FILE), 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                if old_data.get("updated_at", "").split(" ")[0] == time.strftime("%Y-%m-%d"):
                    old_shops = {(s['name'], s['platform']): s for s in old_data.get("shops", [])}
        except: pass

    print(f"小蚕多页抓取中... 坐标:({lat}, {lng}), 城市:{city}")

    all_raw_items = []
    # 1. 抓取多页霸王餐 (10页共计300个)
    for page in range(10):
        offset = page * 30
        res = fetch_rpc("SilkwormRec", "RecService.GetStorePromotionList",
                       {"latitude": float(lat or 0), "longitude": float(lng or 0), "city_code": int(city or 0),
                        "offset": offset, "number": 30, "promotion_sort": 3, "store_type": 0, "app_id": 20}, token, city)
        plist = res.get("promotion_list", [])
        if not plist: break
        all_raw_items.extend(plist)
        print(f"  - 霸王餐第 {page+1} 页抓取完成 ({len(plist)} 条)")
        time.sleep(1)

    # 2. 抓取赏金活动
    res_shangjin = fetch_rpc("SilkwormFusion", "FusionService.GetMeiTuanPromotions", {"lat": float(lat or 0), "lon": float(lng or 0), "silk_id": 897154359, "pv_id": "", "scene": 1, "app_id": 20}, token)
    slist = res_shangjin.get("list", [])
    all_raw_items.extend(slist)
    print(f"  - 赏金活动抓取完成 ({len(slist)} 条)")

    # 3. 解析并去重
    seen_keys = set()
    all_raw = []
    for item in all_raw_items:
        for parsed in parse_item(item):
            key = (parsed['name'], parsed['platform'])
            if key not in seen_keys:
                all_raw.append(parsed)
                seen_keys.add(key)

    with open(p(RAW_FILE), "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(all_raw), "shops": all_raw}, f, indent=4, ensure_ascii=False)

    filtered = [s for s in all_raw if apply_filter(s, rules)]
    filtered.sort(key=lambda x: x['distance_km'])
    new_discoveries = [s for s in filtered if (s['name'], s['platform']) not in old_shops]

    # 保存临时新增 JSON 文件
    with open(p(NEW_FILE), "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(new_discoveries), "shops": new_discoveries}, f, indent=4, ensure_ascii=False)

    # 保存当前所有活跃（通过筛选）的列表
    with open(p("data/xiaocan_active.json"), "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(filtered), "shops": filtered}, f, indent=4, ensure_ascii=False)

    # 合并今日历史数据，防止重复运行出现“新发现”
    for s in filtered:
        key = (s['name'], s['platform'])
        if key not in old_shops:
            old_shops[key] = s

    final_shops = list(old_shops.values())
    final_shops.sort(key=lambda x: x['distance_km'])

    print(f"小蚕抓取完成！去重后总计:{len(all_raw)}, 筛选后:{len(filtered)}, ✨新发现:{len(new_discoveries)}, 今日累计:{len(final_shops)}")
    with open(p(DATA_FILE), "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(final_shops), "shops": final_shops}, f, indent=4, ensure_ascii=False)

if __name__ == "__main__": main()
