import os, time, uuid, json, base64, subprocess, urllib.parse, re, requests
from typing import Dict, List, Optional
from Crypto.Cipher import AES, PKCS1_v1_5
from Crypto.PublicKey import RSA
from Crypto.Util.Padding import pad, unpad

SIGN_AES_KEY, LEGACY_AES_KEY = b"asdf545asdf4545d", b"jnd674751fh6fkgu"
BASE_URL, BASE_URL_V2 = "https://fz-gateway.waimaimingtang.com/api/", "https://wmapp-api-v2.waimaimingtang.com/api"
CONFIG_FILE, DATA_FILE, RAW_FILE, FILTER_FILE, NEW_FILE = "config.json", "data/waimai_shops.json", "data/waimai_raw.json", "filter_rules.json", "data/waimai_new.json"

class WaimaiMonitor:
    def __init__(self, config):
        self.config, self.token = config, config.get("WM_TOKEN", "").replace("填写", "")
        self.public_key, self.private_key = None, None

    def aes_encrypt(self, data: bytes, key: bytes) -> str:
        return base64.b64encode(AES.new(key, AES.MODE_ECB).encrypt(pad(data, 16))).decode('utf-8')
    def aes_decrypt(self, enc_data: str, key: bytes) -> bytes:
        return unpad(AES.new(key, AES.MODE_ECB).decrypt(base64.b64decode(enc_data)), 16)
    def rsa_encrypt(self, data: bytes, pub_key_str: str) -> str:
        return base64.b64encode(PKCS1_v1_5.new(RSA.importKey(f"-----BEGIN PUBLIC KEY-----\n{pub_key_str}\n-----END PUBLIC KEY-----")).encrypt(data)).decode('utf-8')
    def rsa_decrypt(self, enc_data_b64: str, priv_key_str: str) -> bytes:
        return PKCS1_v1_5.new(RSA.importKey(f"-----BEGIN RSA PRIVATE KEY-----\n{priv_key_str}\n-----END RSA PRIVATE KEY-----")).decrypt(base64.b64decode(enc_data_b64), b"error")

    def curl_post(self, url, headers: Dict, data: str = None, json_data: Dict = None) -> (int, str, Dict):
        # 自动识别系统：Linux 使用 curl, Windows 使用 curl.exe
        curl_cmd = "curl" if os.name != 'nt' else "curl.exe"
        cmd = [curl_cmd, "-s", "-i", "-X", "POST", url]
        for k, v in headers.items(): cmd.extend(["-H", f"{k}: {v}"])
        if json_data: cmd.extend(["-d", json.dumps(json_data)])
        elif data: cmd.extend(["-d", data])
        res = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='ignore')
        parts = res.stdout.split("\r\n\r\n", 1)
        if len(parts) < 2: parts = res.stdout.split("\n\n", 1)
        h, body = parts[0], parts[1] if len(parts) > 1 else ""
        sm = re.search(r'HTTP/.*? (\d+)', h)
        return int(sm.group(1)) if sm else 0, body.strip(), {l.split(":", 1)[0].strip().lower(): l.split(":", 1)[1].strip() for l in h.splitlines() if ":" in l}

    def build_headers(self):
        now, nonce = str(int(time.time() * 1000)), "".join([str(uuid.uuid4().int)[:16]])
        return {"application": "overbear_one", "token": self.token, "nonce": nonce, "timestamp": now, "sign": self.aes_encrypt((now + nonce).encode('utf-8'), SIGN_AES_KEY), "city": urllib.parse.quote(self.config["CITY_NAME"]), "appversion": "1.1.175", "Referer": "https://servicewechat.com/wx5762f23d920ad9e5/222/page-frame.html", "Content-Type": "application/json"}

    def fetch_keys(self):
        s, b, rh = self.curl_post(f"{BASE_URL}api/v2/index/newServiceConfig", self.build_headers(), json_data={"json": self.aes_encrypt(json.dumps({"city": self.config["CITY_NAME"]}).encode('utf-8'), LEGACY_AES_KEY)})
        if s == 200:
            d = json.loads(b).get("data")
            if d:
                kj = json.loads(self.aes_decrypt(d, LEGACY_AES_KEY).decode('utf-8'))
                self.public_key, self.private_key = kj["publicKey"], kj["privateKey"]
                return True
        return False

    def get_shop_list_page(self, sd=None):
        if not self.public_key and not self.fetch_keys(): return None
        rak = "".join([str(uuid.uuid4().hex)])[:32].encode('utf-8')
        payload = {"userLongitude": str(self.config["LNG"]), "userLatitude": str(self.config["LAT"]), "city": self.config["CITY_NAME"], "limit": 20, "sortWay": "comprehensive", "secKillFlag": 1, "signUpFlag": 2, "highRebatesFlag": 0, "noCommentFlag": 0, "userTypes": [1, 2, 3], "tabType": "bwc"}
        if sd: payload["scrollPageData"] = sd
        h = self.build_headers()
        h["encrypt-key"] = self.rsa_encrypt(base64.b64encode(rak), self.public_key)
        s, b, rh = self.curl_post(f"{BASE_URL_V2}/bwc/waimaimt-web-bwc/shopIndex/getShopList", h, data=self.aes_encrypt(json.dumps(payload).encode('utf-8'), rak))
        if s == 200:
            ek = rh.get("encrypt-key")
            if ek: return json.loads(self.aes_decrypt(b, base64.b64decode(self.rsa_decrypt(ek, self.private_key))).decode('utf-8'))
            return json.loads(b)
        return None

    def monitor(self):
        all_shops, sd, mp = [], None, (2 if not self.token else 10)
        print(f"歪麦多页抓取中... 坐标:({self.config['LAT']}, {self.config['LNG']}), 城市:{self.config['CITY_NAME']}, 最大页数:{mp}")
        for p in range(mp):
            res = self.get_shop_list_page(sd)
            if not res:
                print(f"  [!] 第 {p+1} 页请求失败 (网络异常)")
                break
            if res.get("code") != 200:
                print(f"  [!] 第 {p+1} 页停止：{res.get('code')} - {res.get('msg')}")
                break

            data_obj = res.get("data", {})
            pl = data_obj.get("data") or data_obj.get("list") or []

            if not pl:
                print(f"  [i] 第 {p+1} 页数据为空，抓取结束")
                break

            all_shops.extend(pl)
            print(f"  - 歪麦第 {p+1} 页抓取完成 ({len(pl)} 条)")

            sd = data_obj.get("scrollPageData")
            if not sd:
                if p + 1 < mp:
                    print(f"  [i] 第 {p+1} 页没有更多翻页标识 (scrollPageData 为空)，抓取结束")
                break
            time.sleep(1)
        return all_shops

def apply_filter(p, rules):
    name = p['name']
    cost = p.get("pay", 0) - p.get("back", 0)
    ratio = p.get("ratio") or 0

    # 1. 兴趣命中 (满足其一即可入围)
    is_interested = False
    if rules.get("include_keywords") and any(k in name for k in rules["include_keywords"]):
        is_interested = True

    if p.get("type") == "赏金":
        if ratio >= rules.get("min_ratio", 0.66):
            is_interested = True
    else:
        if cost <= rules.get("min_cost", 6.0):
            is_interested = True

    if not is_interested: return False

    # 2. 强制排除 (满足其一即被踢出)
    if any(k.lower() in name.lower() for k in rules.get("exclude_keywords", [])): return False
    if p['left'] < rules.get("min_inventory", 1): return False
    if p['distance_km'] > rules.get("max_distance", 5.0): return False
    if rules.get("only_available") and p.get("is_scheduled"): return False

    return True

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    def p(f): return os.path.join(base_dir, f)
    os.makedirs(p("data"), exist_ok=True)

    with open(p(CONFIG_FILE), 'r', encoding='utf-8') as f: config = json.load(f)
    for k in ["WM_TOKEN", "LAT", "LNG", "CITY_NAME", "PUSHPLUS_TOKEN", "REPO_TOKEN"]:
        if os.environ.get(k): config[k] = os.environ.get(k)

    rules = {"include_keywords":[], "exclude_keywords":[], "min_cost":6.0, "min_inventory":2, "only_available":True}
    if os.path.exists(p(FILTER_FILE)):
        with open(p(FILTER_FILE), 'r', encoding='utf-8') as f: rules.update(json.load(f))

    old_shops = {}
    if os.path.exists(p(DATA_FILE)):
        try:
            with open(p(DATA_FILE), 'r', encoding='utf-8') as f:
                old_data = json.load(f)
                if old_data.get("updated_at_fmt", "") == time.strftime("%Y-%m-%d"):
                    old_shops = {(s['name'], s['platform']): s for s in old_data.get("shops", [])}
        except: pass

    shops = WaimaiMonitor(config).monitor()
    if not shops: return print("未获取到商家。")

    all_raw = []
    for s in shops:
        sn, ds, logo = s.get("shopName", "未知商家"), s.get("distance", "0.0"), s.get("logoAddress", "")
        dk = float(ds.replace('km','')) if 'km' in str(ds).lower() else round(float(str(ds).replace('m',''))/1000, 2) if 'm' in str(ds).lower() else float(ds)
        for r in s.get("overbearfoodList", []):
            rd = r.get("maxGradeRebate") or {}
            plat = "美团" if "meituan" in str(r).lower() else "ele" in str(r).lower() and "饿了么" or "未知"
            ratio = r.get("meituanRatio") or r.get("elemeRatio") or r.get("rebateRatio")
            rtq = r.get("releaseTimeQuantum")
            st_str, is_sch, is_expired = "00:00", False, False
            if rtq and isinstance(rtq, str) and "-" in rtq:
                try:
                    times = rtq.split("-")
                    st_str = times[0][:5]
                    et_str = times[1][:5]

                    now_t = time.localtime()
                    now_m = now_t.tm_hour * 60 + now_t.tm_min

                    st_h, st_m = map(int, st_str.split(":"))
                    et_h, et_m = map(int, et_str.split(":"))

                    is_sch = (st_h * 60 + st_m) > now_m
                    is_expired = now_m > (et_h * 60 + et_m)
                except: pass

            is_sk = r.get("secKillFlag") == 1
            ratio_val = None

            # 获取库存，如果时间已过则强制为0
            left_count = int(r.get("surplusNumber", 0))
            if is_expired:
                left_count = 0
            if ratio and float(ratio) > 0:
                type_str, ratio_val = "赏金", float(ratio)
                if ratio_val > 1: ratio_val /= 10000 # 修正比例为小数
                mrm = float(r.get("maxReturnMoney") or rd.get("rebateMoney") or 0)
                if mrm > 100: mrm /= 100
                pay, back = 0.0, mrm
            else:
                type_str = "满减"
                pay = float(rd.get("fullMoney") or r.get("orderMoney", 0) / 100)
                back = float(rd.get("rebateMoney") or r.get("userRebate", 0) / 100)

            all_raw.append({"name": sn, "source": "歪麦", "platform": plat, "type": type_str, "pay": pay, "back": back, "ratio": ratio_val, "left": left_count, "distance_km": dk, "address": s.get("address", ""), "logo": logo, "category": s.get("category", ""), "start_time": st_str, "is_scheduled": is_sch, "is_seckill": is_sk})

    with open(p(RAW_FILE), 'w', encoding='utf-8') as f:
        json.dump({"updated_at": time.ctime(), "shops": all_raw}, f, indent=4, ensure_ascii=False)

    filtered = [s for s in all_raw if apply_filter(s, rules)]
    filtered.sort(key=lambda x: x['distance_km'])
    new_discoveries = [s for s in filtered if (s['name'], s['platform']) not in old_shops]

    # 保存临时新增 JSON 文件
    with open(p(NEW_FILE), "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(new_discoveries), "shops": new_discoveries}, f, indent=4, ensure_ascii=False)

    # 保存当前所有活跃（通过筛选）的列表
    with open(p("data/waimai_active.json"), "w", encoding="utf-8") as f:
        json.dump({"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(filtered), "shops": filtered}, f, indent=4, ensure_ascii=False)

    # 合并今日历史数据，防止重复运行出现“新发现”
    for s in filtered:
        key = (s['name'], s['platform'])
        if key not in old_shops:
            old_shops[key] = s

    final_shops = list(old_shops.values())
    final_shops.sort(key=lambda x: x['distance_km'])

    print(f"歪麦抓取完成！原始:{len(all_raw)}, 筛选后:{len(filtered)}, ✨新发现:{len(new_discoveries)}, 今日累计:{len(final_shops)}")
    with open(p(DATA_FILE), 'w', encoding='utf-8') as f:
        json.dump({"updated_at": time.ctime(), "updated_at_fmt": time.strftime("%Y-%m-%d"), "shops": final_shops}, f, indent=4, ensure_ascii=False)

if __name__ == "__main__": main()
