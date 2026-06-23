import streamlit as st
import pandas as pd
import datetime as dt 
import base64
import requests
from io import StringIO

def get_now_jst():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")

# --- 1. 設定（ポートフォリオ用にダミー化） ---
REPO_NAME = "ttbw0921/demo"
FILE_PATH_STOCK = "inventory_main.csv"
FILE_PATH_LOG = "stock_log_main.csv"
FILE_PATH_RESERVATION = "reservations_main.csv"
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

SIZES_MASTER = ["大", "中", "小", " - "] 
VENDORS_MASTER = ["工場A", "工場B", "工場C", "工場D"] 
USERS = ["担当者A", "担当者B", "担当者C"]

st.set_page_config(page_title="在庫管理システムDEMO", layout="wide")

# --- 2. GitHub関数 ---
def get_github_data(file_path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content = res.json()
        csv_text = base64.b64decode(content["content"]).decode("utf-8")
        df = pd.read_csv(StringIO(csv_text))
        return df.fillna(""), content["sha"]
    return pd.DataFrame(), None

def update_github_data(file_path, df, sha, message):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    csv_content = df.to_csv(index=False)
    data = {
        "message": message,
        "content": base64.b64encode(csv_content.encode("utf-8")).decode("utf-8"),
        "sha": sha
    }
    res = requests.put(url, headers=headers, json=data)
    
    # 🌟 エラーが起きたら画面に原因を赤く表示するデバッグ機能
    if res.status_code not in [200, 201]:
        st.error(f"❌ GitHub更新エラー ({file_path}): ステータスコード {res.status_code}")
        st.json(res.json()) # エラーメッセージの生データを表示
        return False
        
    return True

# 予約を自動処理する関数
def process_reservations(df_stock, sha_stock, df_log, sha_log):
    df_res, sha_res = get_github_data(FILE_PATH_RESERVATION)
    if df_res.empty: return df_stock, df_log
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    df_res["予約日_dt"] = pd.to_datetime(df_res["予約日"]).dt.date
    to_process = df_res[df_res["予約日_dt"] <= today]
    if not to_process.empty:
        new_logs = []
        for _, row in to_process.iterrows():
            mask = (df_stock["商品名"] == row["商品名"]) & (df_stock["サイズ"] == row["サイズ"]) & (df_stock["地名"] == row["地名"])
            if mask.any():
                idx = df_stock[mask].index[0]
                df_stock.at[idx, "在庫数"] -= row["数量"]
                df_stock.at[idx, "最終更新日"] = get_now_jst()
                new_logs.append({
                    "日時": get_now_jst(), "商品名": row["商品名"], "サイズ": row["サイズ"], 
                    "地名": row["地名"], "区分": "出庫(予約実行)", "数量": row["数量"], 
                    "在庫数": df_stock.at[idx, "在庫数"], "担当者": row["担当者"]
                })
        df_res_remain = df_res[df_res["予約日_dt"] > today].drop(columns=["予約日_dt"])
        update_github_data(FILE_PATH_STOCK, df_stock, sha_stock, "Auto Reservation Exec")
        update_github_data(FILE_PATH_LOG, pd.concat([df_log, pd.DataFrame(new_logs)], ignore_index=True), sha_log, "Auto Res Log")
        update_github_data(FILE_PATH_RESERVATION, df_res_remain, sha_res, "Clean up Reservation")
        st.success(f"📢 本日の出庫予約を在庫に反映しました")
        st.rerun()
    return df_stock, df_log

def get_opts(series):
    items = sorted([str(x) for x in series.unique() if str(x).strip() != ""])
    return ["すべて"] + items

def highlight_res_alert(row):
    styles = [''] * len(row)
    if "出荷後在庫" in row.index and row["出荷後在庫"] < 0:
        return ['background-color: #d9534f; color: white'] * len(row)
    return styles

def highlight_alert(row):
    styles = [''] * len(row)
    if "有効在庫" in row.index and row["有効在庫"] < row["アラート基準"]:
        return ['background-color: #d9534f; color: white'] * len(row)
    return styles

# データ読み込み
df_stock, sha_stock = get_github_data(FILE_PATH_STOCK)
df_log, sha_log = get_github_data(FILE_PATH_LOG)
df_res_all, sha_res_all = get_github_data(FILE_PATH_RESERVATION)
df_stock, df_log = process_reservations(df_stock, sha_stock, df_log, sha_log)

# --- 3. サイドバー：新規商品登録 ---
with st.sidebar:
        st.markdown("### 🔗 クイック移動")
        c1, c2 = st.columns(2)
        c1.link_button("📊 分析画面", "https://tt-demo-analysis.streamlit.app/")
        c2.link_button("🚚 発注管理", "https://order-demo.streamlit.app/")
        st.divider()

with st.sidebar:
    st.header("✨ 新規商品登録")
    n_item = st.text_input("商品名", key="sidebar_n_item")
    n_size = st.selectbox("サイズ", SIZES_MASTER, key="sidebar_n_size")
    n_loc = st.text_input("拠点・倉庫名", key="sidebar_n_loc") # 「地名」を「拠点・倉庫名」として汎用化
    n_vendor = st.selectbox("取引先", VENDORS_MASTER, key="sidebar_n_vendor")
    n_stock = st.number_input("初期在庫", min_value=0, value=0, key="sidebar_n_stock")
    n_alert = st.number_input("アラート基準", min_value=0, value=5, key="sidebar_n_alert")
    
    if st.button("新規登録実行", use_container_width=True, type="primary"):
        is_duplicate = not df_stock[(df_stock["商品名"] == n_item) & (df_stock["サイズ"] == n_size) & (df_stock["地名"] == n_loc)].empty
        if is_duplicate:
            st.error(f"❌ 重複エラー")
        elif n_item and n_loc:
            now = get_now_jst()
            new_row = pd.DataFrame([{"最終更新日": now, "商品名": n_item, "サイズ": n_size, "地名": n_loc, "在庫数": n_stock, "アラート基準": n_alert, "取引先": n_vendor}])
            new_log = pd.DataFrame([{"日時": now, "商品名": n_item, "サイズ": n_size, "地名": n_loc, "区分": "新規登録", "数量": n_stock, "在庫数": n_stock, "担当者": "システム"}])
            if update_github_data(FILE_PATH_STOCK, pd.concat([df_stock, new_row], ignore_index=True), sha_stock, "Add Item") and \
               update_github_data(FILE_PATH_LOG, pd.concat([df_log, pd.DataFrame(new_log)], ignore_index=True), sha_log, "Add Log"):
                st.success("登録完了")
                st.rerun()

# --- 4. メイン：在庫一覧 ---
st.title("📦 在庫管理システム DEMO")

c1, c2, c3, c4 = st.columns(4)
with c1: s_item = st.selectbox("検索:商品名", get_opts(df_stock["商品名"]), key="filter_item")
with c2: s_size = st.selectbox("検索:サイズ", get_opts(df_stock["サイズ"]), key="filter_size")
with c3: search_loc = st.text_input("検索:拠点・倉庫名（手入力）", placeholder="例: 東京第一倉庫", key="filter_loc")
with c4: s_vendor = st.selectbox("検索:取引先", get_opts(df_stock["取引先"]), key="filter_vendor")

# 有効在庫の計算
df_disp = df_stock.copy()
res_sum = df_res_all.groupby(["商品名", "サイズ", "地名"])["数量"].sum().reset_index().rename(columns={"数量": "予約計"}) if not df_res_all.empty else pd.DataFrame(columns=["商品名", "サイズ", "地名", "予約計"])
if not res_sum.empty:
    df_disp = pd.merge(df_disp, res_sum, on=["商品名", "サイズ", "地名"], how="left").fillna({"予約計": 0})
else:
    df_disp["予約計"] = 0
df_disp["有効在庫"] = df_disp["在庫数"] - df_disp["予約計"]

# フィルタリング
if s_item != "すべて": df_disp = df_disp[df_disp["商品名"] == s_item]
if s_size != "すべて": df_disp = df_disp[df_disp["サイズ"] == s_size]
if search_loc.strip(): df_disp = df_disp[df_disp["地名"].astype(str).str.contains(search_loc, na=False)]
if s_vendor != "すべて": df_disp = df_disp[df_disp["取引先"] == s_vendor]

# 表示列の整理
disp_cols = ["最終更新日", "商品名", "サイズ", "地名", "在庫数", "有効在庫", "アラート基準", "取引先"]
df_show = df_disp[disp_cols].sort_values("最終更新日", ascending=False) if not df_disp.empty else pd.DataFrame(columns=disp_cols)
styled_df = df_show.style.apply(highlight_alert, axis=1)

event = st.dataframe(
    styled_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row",
    column_config={
        "在庫数": st.column_config.NumberColumn("実在庫", format="%d"),
        "有効在庫": st.column_config.NumberColumn("有効在庫", format="%d")
    }
)

# --- 5. 操作パネル ---
st.divider()
if not df_show.empty:
    selected_indices = event.selection.rows
    if selected_indices:
        selected_data_list = df_show.iloc[selected_indices]
        st.markdown(f"### 📋 {len(selected_data_list)} 件の一括操作")
        
        # --- 1. 共通設定 ---
        with st.container(border=True):
            st.markdown("**⚡ 全選択データへの共通設定**")
            cc1, cc2, cc3 = st.columns([1.5, 1, 1])
            with cc1:
                bulk_type = st.radio("操作区分を一括変更", ["入庫", "出庫", "予約出庫", "調整"], horizontal=True)
            with cc2:
                is_not_res = (bulk_type != "予約出庫")
                bulk_date = st.date_input("共通の予約日", value=dt.date.today() + dt.timedelta(days=1), disabled=is_not_res)
            with cc3:
                user_name = st.selectbox("担当者", ["-- 選択 --"] + USERS)

        if user_name != "-- 選択 --":
            update_payload = {}
            for i, row in selected_data_list.iterrows():
                with st.expander(f"📌 {row['商品名']} ({row['サイズ']} / {row['地名']})", expanded=True):
                    col1, col2, col3, col4, col5 = st.columns([1.5, 1, 1.2, 1, 0.6])
                    with col1:
                        st.info(f"区分: {bulk_type}")
                    with col2:
                        m_qty = st.number_input("数量", min_value=0 if bulk_type != "調整" else -10000, value=0, key=f"qty_{i}")
                    with col3:
                        if bulk_type == "予約出庫":
                            res_date = bulk_date
                            st.write(f"予定: {res_date}")
                            new_loc = row['地名']
                        else:
                            new_loc = st.text_input("拠点変更", value=row['地名'], key=f"loc_{i}")
                            res_date = None
                    with col4:
                        new_alert = st.number_input("アラート基準", min_value=0, value=int(row['アラート基準']), key=f"alt_{i}")
                    with col5:
                        is_delete = st.checkbox("削除", key=f"del_{i}")
                    
                    update_payload[i] = {
                        "type": bulk_type, "qty": m_qty, "loc": new_loc, "alert": new_alert, 
                        "delete": is_delete, "res_date": res_date, "orig_data": row
                    }

            # --- 確定画面（ポップオーバー） ---
            with st.popover("✅ 内容を確認して確定", use_container_width=True):
                st.markdown(f"### ⚠️ 以下の内容で確定しますか？")
                
                summary_list = []
                for idx, p in update_payload.items():
                    row = p["orig_data"]
                    item_detail =  f"{row['商品名']} {row['サイズ']} {row['地名']} {p['qty']}"
                    
                    if p["delete"]:
                        summary_list.append(f"🔥 **削除**: {row['商品名']} ({row['サイズ']}) {row['地名']}")
                    elif p["qty"] != 0 or p["loc"] != row["地名"]:
                        if p["type"] == "予約出庫":
                            summary_list.append(f"📅 **{p['type']}**: {item_detail} (予約日:{p['res_date']})")
                        else:
                            current_item =  f"{row['商品名']} {row['サイズ']} {p['loc']} {p['qty']}"
                            loc_change = f" (拠点変更: {row['地名']} → {p['loc']})" if p["loc"] != row["地名"] else ""
                            summary_list.append(f"📝 **{p['type']}**: {current_item}{loc_change}")
                
                if summary_list:
                    for item in summary_list:
                        st.write(item)
                    st.divider()
                    
                    if st.button("👌 実行する", type="primary", use_container_width=True):
                        st.write("データを更新中...")
                        new_df_stock = df_stock.copy()
                        new_logs = []
                        new_reservations = df_res_all.copy()
                        now = get_now_jst()

                        for idx, p in update_payload.items():
                            row = p["orig_data"]
                            mask = (new_df_stock["商品名"] == row["商品名"]) & (new_df_stock["サイズ"] == row["サイズ"]) & (new_df_stock["地名"] == row["地名"])
                            if not mask.any(): continue
                            target_idx = new_df_stock[mask].index[0]

                            if p["delete"]:
                                new_df_stock = new_df_stock.drop(target_idx)
                            else:
                                if p["type"] == "予約出庫":
                                    res_row = pd.DataFrame([{"予約日": str(p["res_date"]), "商品名": row["商品名"], "サイズ": row["サイズ"], "地名": row["地名"], "数量": p["qty"], "担当者": user_name}])
                                    new_reservations = pd.concat([new_reservations, res_row], ignore_index=True)
                                else:
                                    if p["type"] == "入庫": new_df_stock.at[target_idx, "在庫数"] += p["qty"]
                                    elif p["type"] == "出庫": new_df_stock.at[target_idx, "在庫数"] -= p["qty"]
                                    elif p["type"] == "調整": new_df_stock.at[target_idx, "在庫数"] = p["qty"]
                                    new_df_stock.at[target_idx, "地名"], new_df_stock.at[target_idx, "アラート基準"], new_df_stock.at[target_idx, "最終更新日"] = p["loc"], p["alert"], now
                                    new_logs.append({"日時": now, "商品名": row["商品名"], "サイズ": row["サイズ"], "地名": p["loc"], "区分": p["type"], "数量": p["qty"], "在庫数": new_df_stock.at[target_idx, "在庫数"], "担当者": user_name})

                        if update_github_data(FILE_PATH_STOCK, new_df_stock, sha_stock, "Stock Update") and \
                           update_github_data(FILE_PATH_LOG, pd.concat([df_log, pd.DataFrame(new_logs)], ignore_index=True), sha_log, "Add Log") and \
                           update_github_data(FILE_PATH_RESERVATION, new_reservations, sha_res_all, "Add Res"):
                            st.success("完了！")
                            st.rerun()
                else:
                    st.write("変更なし")
                    
# --- 6. 予約・履歴 ---
st.divider()

# --- A. 出庫予約リスト ---
st.subheader("📅 出庫予約リスト")
if not df_res_all.empty:
    df_rv = pd.merge(df_res_all, df_stock[["商品名", "サイズ", "地名", "在庫数"]], on=["商品名", "サイズ", "地名"], how="left").fillna({"在庫数": 0})
    df_rv["予約日_tmp"] = pd.to_datetime(df_rv["予約日"])
    df_rv = df_rv.sort_values(["商品名", "サイズ", "地名", "予約日_tmp"])
    
    df_rv["累積予約数"] = df_rv.groupby(["商品名", "サイズ", "地名"])["数量"].cumsum()
    df_rv["全予約合計"] = df_rv.groupby(["商品名", "サイズ", "地名"])["数量"].transform("sum")
    df_rv["出荷後在庫"] = df_rv["在庫数"] - df_rv["累積予約数"]
    df_rv["全体有効在庫"] = df_rv["在庫数"] - df_rv["全予約合計"]

    df_rv = df_rv.reset_index()
    df_rv["tmp_id"] = range(len(df_rv))

    res_filter_item = st.selectbox("予約検索:商品名", get_opts(df_rv["商品名"]), key="res_f_item")
    df_rv_display = df_rv.copy()
    if res_filter_item != "すべて":
        df_rv_display = df_rv_display[df_rv_display["商品名"] == res_filter_item]

    df_rv_display["予約日"] = pd.to_datetime(df_rv_display["予約日"]).dt.date
    res_disp_cols = ["予約日", "商品名", "サイズ", "地名", "数量", "在庫数", "出荷後在庫", "全体有効在庫", "担当者"]

    styled_rv = df_rv_display[res_disp_cols].style.apply(highlight_res_alert, axis=1)

    res_event = st.dataframe(
        styled_rv, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row",
        column_config={
            "予約日": st.column_config.DateColumn("予約日", format="YYYY-MM-DD"),
            "数量": st.column_config.NumberColumn("予約数", format="%d"),
            "在庫数": st.column_config.NumberColumn("現在の実在庫", format="%d"),
            "出荷後在庫": st.column_config.NumberColumn("今回の出荷後残数", format="%d"),
            "全体有効在庫": st.column_config.NumberColumn("全予約完了後の残数", format="%d"),
        }
    )
    
    selected_indices = res_event.selection.rows
    if selected_indices:
        st.markdown(f"#### ✍️ 選択中の予約 ({len(selected_indices)}件) を編集")
        df_selected = df_rv_display.iloc[selected_indices]
        
        res_updates = {}
        for i, row in df_selected.iterrows():
            orig_idx = row["index"]
            with st.expander(f"予約: {row['商品名']} ({row['サイズ']} / {row['地名']})", expanded=True):
                c1, c2, c3 = st.columns([1.5, 1, 0.5])
                with c1: upd_date = st.date_input("予約日変更", value=row['予約日'], key=f"up_res_d_{orig_idx}")
                with c2: upd_qty = st.number_input("数量変更", min_value=1, value=int(row['数量']), key=f"up_res_q_{orig_idx}")
                with c3: is_res_del = st.checkbox("削除", key=f"up_res_del_{orig_idx}")
                res_updates[orig_idx] = {"date": upd_date, "qty": upd_qty, "delete": is_res_del}

        if st.button("✅ 予約の変更/削除を確定する", type="primary", use_container_width=True):
            new_df_res = df_res_all.copy()
            for o_idx, val in res_updates.items():
                if val["delete"]:
                    new_df_res = new_df_res.drop(o_idx)
                else:
                    new_df_res.at[o_idx, "予約日"] = str(val["date"])
                    new_df_res.at[o_idx, "数量"] = val["qty"]
            
            update_github_data(FILE_PATH_RESERVATION, new_df_res, sha_res_all, "Fixed Index Sync Issue")
            st.rerun()
else:
    st.write("現在予約はありません。")

st.divider()

# --- B. 入出庫履歴 ---
st.subheader("📜 入出庫履歴")

if not df_log.empty:
    col_log1, col_log2, col_log3, col_log4, col_log5 = st.columns([1.5, 1.2, 1, 1, 1.2])
    
    with col_log1:
        df_log["日時"] = pd.to_datetime(df_log["日時"], errors='coerce')
        df_log = df_log.dropna(subset=["日時"])
        min_date, max_date = df_log["日時"].min().date(), df_log["日時"].max().date()
        log_date_range = st.date_input("期間", value=(min_date, max_date), key="log_date_filter")
    
    with col_log2:
        l_item = st.selectbox("履歴検索:商品名", get_opts(df_log["商品名"]), key="log_f_item")
    with col_log3:
        l_size = st.selectbox("履歴検索:サイズ", get_opts(df_log["サイズ"]), key="log_f_size")
    with col_log4:
        l_loc = st.selectbox("履歴検索:拠点名", get_opts(df_log["地名"]), key="log_f_loc")
    
    with col_log5:
        all_types = [t for t in sorted(df_log["区分"].unique()) if t not in ["基準変更", "編集"] and str(t).strip() != ""]
        selected_types = st.multiselect("区分（複数可）", options=all_types, key="log_type_filter")

    df_log_filtered = df_log.copy()
    
    if isinstance(log_date_range, tuple) and len(log_date_range) == 2:
        df_log_filtered = df_log_filtered[(df_log_filtered["日時"].dt.date >= log_date_range[0]) & (df_log_filtered["日時"].dt.date <= log_date_range[1])]
    
    if l_item != "すべて": df_log_filtered = df_log_filtered[df_log_filtered["商品名"] == l_item]
    if l_size != "すべて": df_log_filtered = df_log_filtered[df_log_filtered["サイズ"] == l_size]
    if l_loc != "すべて": df_log_filtered = df_log_filtered[df_log_filtered["地名"] == l_loc]
    
    if selected_types:
        df_log_filtered = df_log_filtered[df_log_filtered["区分"].isin(selected_types)]

    disp_log_cols = ["日時", "商品名", "サイズ", "地名", "区分", "数量", "在庫数", "担当者"]
    st.dataframe(
        df_log_filtered[disp_log_cols].sort_values("日時", ascending=False),
        use_container_width=True, hide_index=True,
        column_config={
            "日時": st.column_config.DatetimeColumn("日時", format="YYYY-MM-DD HH:mm"),
            "数量": st.column_config.NumberColumn("数", format="%d"),
            "在庫数": st.column_config.NumberColumn("現在庫", format="%d")
        }
    )
