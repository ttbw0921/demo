import streamlit as st
import pandas as pd
import datetime as dt 
import base64
import requests
from io import StringIO

# --- 1. 設定 ---
REPO_NAME = "ttbw0921/demo" 
FILE_PATH_STOCK = "demo/inventory_main.csv"
FILE_PATH_LOG = "demo/stock_log_main.csv"
FILE_PATH_RESERVATION = "demo/reservations_main.csv"
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

SIZES_MASTER = ["大", "中", "小", " - "] 
VENDORS_MASTER = ["工場A", "工場B", "工場C", "工場D"]
USERS = ["担当者A", "担当者B", "担当者C"]

st.set_page_config(page_title="在庫管理システムDEMO", layout="wide")

# --- 2. 補助関数 ---
def get_now_jst():
    return dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S")

def get_opts(series):
    return ["すべて"] + sorted(series.dropna().unique().tolist())

def highlight_alert(row):
    color = 'background-color: #ffcccc' if row['在庫数'] <= row['アラート基準'] else ''
    return [color] * len(row)

def highlight_res_alert(row):
    color = 'background-color: #ffcccc' if row['出荷後在庫'] < 0 else ''
    return [color] * len(row)

# --- 3. GitHub関数 ---
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
    return res.status_code in [200, 201]

# --- 4. メイン処理 ---
df_stock, sha_stock = get_github_data(FILE_PATH_STOCK)
df_log, sha_log = get_github_data(FILE_PATH_LOG)
df_res_all, sha_res_all = get_github_data(FILE_PATH_RESERVATION)

st.title("📦 在庫管理システム DEMO")

if not df_stock.empty:
    # フィルタリング
    c1, c2, c3, c4 = st.columns(4)
    with c1: s_item = st.selectbox("検索:商品名", get_opts(df_stock["商品名"]))
    with c2: s_size = st.selectbox("検索:サイズ", get_opts(df_stock["サイズ"]))
    with c3: search_loc = st.text_input("検索:拠点名")
    with c4: s_vendor = st.selectbox("検索:取引先", get_opts(df_stock["取引先"]))

    df_disp = df_stock.copy()
    res_sum = df_res_all.groupby(["商品名", "サイズ", "地名"])["数量"].sum().reset_index().rename(columns={"数量": "予約計"}) if not df_res_all.empty else pd.DataFrame(columns=["商品名", "サイズ", "地名", "予約計"])
    df_disp = pd.merge(df_disp, res_sum, on=["商品名", "サイズ", "地名"], how="left").fillna({"予約計": 0})
    df_disp["有効在庫"] = df_disp["在庫数"] - df_disp["予約計"]

    if s_item != "すべて": df_disp = df_disp[df_disp["商品名"] == s_item]
    if s_size != "すべて": df_disp = df_disp[df_disp["サイズ"] == s_size]
    if search_loc.strip(): df_disp = df_disp[df_disp["地名"].astype(str).str.contains(search_loc)]
    if s_vendor != "すべて": df_disp = df_disp[df_disp["取引先"] == s_vendor]

    styled_df = df_disp.style.apply(highlight_alert, axis=1)
    event = st.dataframe(styled_df, use_container_width=True, hide_index=True, on_select="rerun", selection_mode="multi-row")
    
    # --- 5. 操作パネル ---
    st.divider()
    selected_indices = event.selection.rows
    if selected_indices:
        selected_data_list = df_disp.iloc[selected_indices]
        bulk_type = st.radio("操作区分", ["入庫", "出庫", "予約出庫", "調整"], horizontal=True)
        user_name = st.selectbox("担当者", USERS)
        
        update_payload = {}
        for i, row in selected_data_list.iterrows():
            with st.expander(f"📌 {row['商品名']} ({row['サイズ']} / {row['地名']})"):
                m_qty = st.number_input("数量", value=0, key=f"qty_{i}")
                new_loc = st.text_input("拠点変更", value=row['地名'], key=f"loc_{i}")
                update_payload[i] = {"type": bulk_type, "qty": m_qty, "loc": new_loc, "orig_data": row}

        if st.button("確定"):
            for idx, p in update_payload.items():
                row = p["orig_data"]
                target_idx = df_stock[df_stock["商品名"]==row["商品名"]].index[0]
                if p["type"] == "入庫": df_stock.at[target_idx, "在庫数"] += p["qty"]
                # (簡易版：必要に応じて複雑な更新ロジックをここに追記)
            update_github_data(FILE_PATH_STOCK, df_stock, sha_stock, "Bulk Update")
            st.rerun()

    # --- 6. 予約・履歴 ---
    st.divider()
    st.subheader("📜 入出庫履歴")
    if not df_log.empty:
        st.dataframe(df_log.sort_values("日時", ascending=False), use_container_width=True)
else:
    st.error("データが読み込めません")
