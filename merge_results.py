import json, os, time, requests

def send_pushplus_notification(token, title, content):
    if not token:
        print("PushPlus Token 未配置，跳过推送。")
        return

    url = "http://www.pushplus.plus/send"
    payload = {
        "token": token,
        "title": title,
        "content": content,
        "template": "html"
    }
    headers = {"Content-Type": "application/json"}

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=15)
        res_json = response.json()
        if res_json.get("code") == 200:
            print(f"PushPlus 推送成功: {res_json.get('msg')}")
        else:
            print(f"PushPlus 推送失败: {res_json.get('msg')}")
    except Exception as e:
        print(f"PushPlus 推送异常: {e}")

def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    data_dir = os.path.join(base_dir, "data")
    new_shops_file = os.path.join(base_dir, "new_shops.json")
    config_file = os.path.join(base_dir, "config.json")

    all_new_shops = []
    all_active_shops = []

    # 合并新发现
    for filename in ["waimai_new.json", "xiaocan_new.json"]:
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    all_new_shops.extend(json.load(f).get("shops", []))
            except: pass

    # 合并所有活跃条目
    for filename in ["waimai_active.json", "xiaocan_active.json"]:
        filepath = os.path.join(data_dir, filename)
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    all_active_shops.extend(json.load(f).get("shops", []))
            except: pass

    # 写入根目录
    result = {"updated_at": time.strftime("%Y-%m-%d %H:%M:%S"), "count": len(all_new_shops), "shops": all_new_shops}
    with open(new_shops_file, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=4, ensure_ascii=False)

    print(f"合并完成！新发现: {len(all_new_shops)}, 总活跃: {len(all_active_shops)}")

    if all_new_shops:
        push_token = ""
        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    push_token = os.environ.get("PUSHPLUS_TOKEN") or config.get("PUSHPLUS_TOKEN")
            except: pass

        if push_token:
            # HTML 基础结构
            c_op = '<div style="margin:0 15px;border:1px solid #e1e4e8;border-radius:12px;overflow:hidden;background:#fff;box-shadow:0 2px 12px rgba(0,0,0,0.08);font-family:sans-serif;">'
            # 使用 colgroup 锁定列宽，确保双卡片对齐
            t_op = '<table cellspacing="0" cellpadding="10" style="width:100%;border-collapse:collapse;table-layout:fixed;font-size:13px;">' \
                   '<colgroup><col style="width:55%"><col style="width:20%"><col style="width:25%"></colgroup>'

            header = f'<div style="height:15px;background:#fff"></div>{c_op}{t_op}' \
                     '<tr style="background:#fafafa;border-bottom:1px solid #f0f0f2;">' \
                     '<th style="text-align:left;color:#888;font-weight:500;">商家</th>' \
                     '<th style="text-align:center;color:#888;font-weight:500;">满返</th>' \
                     '<th style="text-align:center;color:#888;font-weight:500;">来源</th></tr>'
            footer = '</table></div><div style="height:100000px"></div>'

            # 精准去重逻辑
            new_keys = {(s['name'], s['platform']) for s in all_new_shops}
            remaining_shops = [s for s in all_active_shops if (s['name'], s['platform']) not in new_keys]

            # 准备待渲染的所有行
            all_rows = []

            def gen_row_html(i, s, is_last):
                raw_name = s.get("name", "未知")
                js_name = raw_name.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
                shop_id = f"s_{i}"
                logo_url = s.get("logo", "")
                source_val = s.get('source', '')
                plat_val = s.get('platform', '')
                plat_short = "美" if "美团" in plat_val else "饿" if "饿了么" in plat_val else plat_val
                bg, txt = ("#e0f2fe", "#0369a1") if source_val == "小蚕" else ("#f3e8ff", "#7e22ce") if source_val == "歪麦" else ("#f1f5f9", "#475569")
                badge = f'<span style="background:{bg};color:{txt};padding:2px 4px;border-radius:4px;font-size:11px">{source_val}({plat_short})</span>'
                comb = f"<b>{int(s.get('ratio', 0)*100)}%</b>" if s.get("type") == "赏金" else f"{int(s.get('pay', 0))}-<b>{int(s.get('back', 0))}</b>"
                copy_js = f"let s=this.style;let t=document.createElement('textarea');t.value='{js_name}';document.body.append(t);t.select();document.execCommand('copy');t.remove();s.color='#007aff';setTimeout(()=>s.color='#1a1a1a',200);return!1"
                i_sty = f"width:32px;height:32px;border-radius:4px;border:1px solid #eee;background:#fafafa url(\'{logo_url}\') 50%/cover no-repeat" if logo_url else "width:32px;height:32px;border-radius:4px;border:1px solid #eee;background:#fafafa"
                merchant_html = f'<table cellspacing="0" cellpadding="0" style="width:100%;table-layout:fixed"><tr><td width="32" valign="middle"><div style="{i_sty}"></div></td><td width="10"></td><td valign="middle" style="line-height:1.4"><b><a id="{shop_id}" href="#" onclick="{copy_js}" style="text-decoration:none;color:#1a1a1a">{raw_name}</a></b></td></tr></table>'
                row_style = "border-bottom: 1px solid #f5f5f7;" if not is_last else ""
                return f'<tr style="{row_style}"><td valign="middle">{merchant_html}</td><td align="center" valign="middle">{comb}</td><td align="center" valign="middle">{badge}</td></tr>'

            # 1. 生成新发现行
            for i, s in enumerate(all_new_shops):
                is_last = (i == len(all_new_shops) - 1)
                all_rows.append(gen_row_html(f"n_{i}", s, is_last))

            # 2. 注入双卡片分割逻辑
            if all_new_shops and remaining_shops:
                # 闭合卡片 1，插入间距，开启卡片 2 (不带表头)
                all_rows.append(f'</table></div><div style="height:15px;background:#fff"></div>{c_op}{t_op}')

            # 3. 生成剩余活跃行
            for i, s in enumerate(remaining_shops):
                is_last = (i == len(remaining_shops) - 1)
                all_rows.append(gen_row_html(f"a_{i}", s, is_last))

            # 分片发送逻辑
            batches = []
            current_batch = []
            current_len = len(header) + len(footer)

            for row_html in all_rows:
                if current_len + len(row_html) > 18000:
                    batches.append(current_batch)
                    current_batch = []
                    current_len = len(header) + len(footer)
                current_batch.append(row_html)
                current_len += len(row_html)

            if current_batch:
                batches.append(current_batch)

            total_batches = len(batches)
            for idx, batch in enumerate(batches):
                title = f"🍔 外卖新发现 ({len(all_new_shops)}条)"
                if total_batches > 1: title += f" ({idx+1}/{total_batches})"

                content = header + "".join(batch) + footer
                print(f"推送分片 {idx+1}/{total_batches} 长度: {len(content)} 字符")
                send_pushplus_notification(push_token, title, content)
                if idx < total_batches - 1: time.sleep(3)
        else:
            print("未配置 PushPlus Token。")

if __name__ == "__main__": main()
