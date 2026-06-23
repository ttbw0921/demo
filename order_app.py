import streamlit as st
import pandas as pd
import requests
import base64
from datetime import datetime, timedelta, timezone
import io

# --- 1. 設定（URLバグ防止のため完全に固定） ---
REPO_NAME = "ttbw0921/demo"
FILE_PATH_ORDERS = "order_log.csv"
FILE_PATH_MASTER = "material_master.csv"
FILE_PATH_VENDOR = "vendor_master.csv"
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]
def get_now_jst():return datetime.now(timezone(timedelta(hours=9)))

# --- 2. GitHub連携関数 ---
def get_github_data(file_path, default_cols):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content = res.json()
        csv_data = base64.b64decode(content["content"]).decode("utf-8")
        if not csv_data.strip():
            return pd.DataFrame(columns=default_cols), content["sha"]
        df = pd.read_csv(io.StringIO(csv_data))
        for col in default_cols:
            if col not in df.columns: df[col] = ""
        return df[default_cols], content["sha"]
    else:
        return pd.DataFrame(columns=default_cols), None

def update_github_data(file_path, df, sha, message):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    csv_content = df.to_csv(index=False)
    content_base64 = base64.b64encode(csv_content.encode("utf-8")).decode("utf-8")
    data = {"message": message, "content": content_base64, "sha": sha}
    res = requests.put(url, headers=headers, json=data)
    return res.status_code

st.set_page_config(page_title="発注管理", layout="wide", page_icon="📦")

# データ読み込み
order_cols = ["id","category","item_name","product_name","request_date","quantity","vendor","order_date","delivery_date","status"]
master_cols = ["category", "item_name", "product_name"]
vendor_cols = ["vendor_name"]
df_orders, sha_orders = get_github_data(FILE_PATH_ORDERS, order_cols)
df_master, sha_master = get_github_data(FILE_PATH_MASTER, master_cols)
df_vendor, sha_vendor = get_github_data(FILE_PATH_VENDOR, vendor_cols)

# 各ステータスのデータ抽出
pending_df = df_orders[df_orders['status'] == '未対応'].copy()
ordered_df = df_orders[df_orders['status'] == '発注済み'].copy()
count = len(pending_df)

# --- 👈 サイドバー：新規発注依頼 ---
with st.sidebar:
    st.title("🔗 クイック移動")
    col1, col2 = st.columns(2)
    col1.link_button("📦 在庫管理", "https://zaiko-kanri.app/")
    col2.link_button("📊 分析画面", "https://zaiko-kanri-f8bgjer2kscsa9ack7ervi.streamlit.app//")
    st.divider()

with st.sidebar:
    st.title("➕ 新規発注依頼")
    st.divider()
    if df_master.dropna(how='all').empty:
        st.warning("先にマスタ登録が必要です。")
    else:
        cats = [c for c in df_master["category"].unique() if pd.notna(c) and c != ""]
        c_cat = st.selectbox("1. カテゴリ", cats)
        items = df_master[df_master["category"] == c_cat]["item_name"].unique()
        c_item = st.selectbox("2. 資材名", items)
        prods = df_master[(df_master["category"] == c_cat) & (df_master["item_name"] == c_item)]["product_name"].unique()
        c_prod = st.selectbox("3. 商品名", prods)
        if st.button("依頼を送信", type="primary", use_container_width=True):
            new_id = int(df_orders['id'].max() + 1) if not df_orders.empty else 1
            now = get_now_jst().strftime("%Y-%m-%d %H:%M")
            new_row = pd.DataFrame([{"id": new_id, "category": c_cat, "item_name": c_item, "product_name": c_prod, "request_date": now, "status": "未対応"}])
            df_updated = pd.concat([df_orders, new_row], ignore_index=True)
            if update_github_data(FILE_PATH_ORDERS, df_updated, sha_orders, "New Request") in [200, 201]:
                st.toast("✅ 依頼を送信しました！")
                st.rerun()

    st.divider()
    with st.expander("⚙️ マスタ登録"):
        with st.form("master_form", clear_on_submit=True):
            m_cat = st.selectbox("カテゴリ", ["化粧箱", "トレイ", "ダンボール", "包装紙", "その他"])
            m_item = st.text_input("資材名")
            m_prod = st.text_input("商品名")
            if st.form_submit_button("マスタに追加", use_container_width=True):
                if m_item and m_prod:
                    new_m_row = pd.DataFrame([{"category": m_cat, "item_name": m_item, "product_name": m_prod}])
                    df_m_updated = pd.concat([df_master, new_m_row], ignore_index=True).drop_duplicates()
                    if update_github_data(FILE_PATH_MASTER, df_m_updated, sha_master, "Update Master") in [200, 201]:
                        st.toast(f"✅ 「{m_item}」を登録しました")
                        st.rerun()

    with st.expander("🏢 発注先マスタ登録"):
        with st.form("vendor_form", clear_on_submit=True):
            v_name = st.text_input("発注先名（仕入先）")
            if st.form_submit_button("発注先を追加", use_container_width=True):
                if v_name:
                    new_v_row = pd.DataFrame([{"vendor_name": v_name}])
                    df_v_updated = pd.concat([df_vendor, new_v_row], ignore_index=True).drop_duplicates()
                    update_github_data(FILE_PATH_VENDOR, df_v_updated, sha_vendor, "Update Vendor Master")
                    st.rerun()

# --- メイン画面 ---
st.title("📦 資材発注管理")

if count > 0:
    st.markdown(f"""
        <div style="background-color: #ff4b4b; color: white; padding: 12px 25px; border-radius: 8px; font-size: 18px; font-weight: bold; text-align: left; margin-bottom: 25px;">
            ⚠️ 未対応の依頼が {count} 件あります
        </div>
    """, unsafe_allow_html=True)

st.subheader("📝 発注処理待ち")
if not pending_df.empty:
    pending_df.insert(0, "選択", False)
    edited_p = st.data_editor(
        pending_df, 
        hide_index=True, use_container_width=True, 
        column_order=["選択", "category", "item_name", "product_name", "request_date"],
        column_config={"id": None, "quantity": None, "vendor": None, "order_date": None, "delivery_date": None, "status": None},
        disabled=["category", "item_name", "product_name", "request_date"],
        key="pending_editor"
    )
    
    selected_ids = pending_df.loc[edited_p[edited_p["選択"] == True].index, "id"].tolist()
    if selected_ids:
        # ---- 削除ボタン ----
        if st.button("❌ チェックした項目を削除する", type="secondary", use_container_width=True):
            df_orders = df_orders[~df_orders["id"].isin(selected_ids)]
            update_github_data(FILE_PATH_ORDERS, df_orders, sha_orders, "Delete Requests")
            st.toast("🗑️ 選択した依頼を削除しました")
            st.rerun()
            
        with st.form("process_form"):
            payload = {}
            vendor_list = df_vendor["vendor_name"].tolist() if not df_vendor.empty else []
            for sid in selected_ids:
                row = pending_df[pending_df["id"] == sid].iloc[0]
                st.markdown(f"**📍 {row['item_name']} ({row['product_name']})**")
                c1, c2, c3 = st.columns(3)
                
                qty_input = c1.number_input("数量", min_value=1, key=f"q_{sid}")
                
                if vendor_list:
                    vendor_input = c2.selectbox("発注先", vendor_list, key=f"v_{sid}")
                else:
                    vendor_input = c2.text_input("発注先（マスタ未登録）", key=f"v_{sid}")
                
                date_input = c3.date_input("納品予定", key=f"d_{sid}")
                
                payload[sid] = {
                    "qty": qty_input, 
                    "vendor": vendor_input, 
                    "date": date_input
                }
            
            # 安全に型を揃えて代入する処理をフォームの「内側」に配置
            if st.form_submit_button("✅ チェックした項目を発注済みにする", use_container_width=True):
                for oid, v in payload.items():
                    idx = df_orders[df_orders['id'] == oid].index[0]
                    df_orders.at[idx, "quantity"] = int(v['qty'])
                    df_orders.at[idx, "vendor"] = str(v['vendor'])
                    df_orders.at[idx, "delivery_date"] = str(v['date'])
                    df_orders.at[idx, "status"] = "発注済み"
                    df_orders.at[idx, "order_date"] = get_now_jst().strftime("%Y-%m-%d")
                update_github_data(FILE_PATH_ORDERS, df_orders, sha_orders, "Ordered")
                st.rerun()
else:
    st.info("現在、新規の依頼はありません。")

st.markdown("<br>", unsafe_allow_html=True)

with st.expander(f"🚚 発注済み・入荷待ち ({len(ordered_df)}件)", expanded=False):
    if not ordered_df.empty:
        ordered_df.insert(0, "入荷", False)
        edited_ordered = st.data_editor(
            ordered_df,
            hide_index=True, use_container_width=True,
            column_order=["入荷", "category", "item_name", "product_name", "quantity", "vendor", "delivery_date", "order_date"],
            column_config={"id": None, "status": None, "request_date": None},
            disabled=["category", "item_name", "product_name", "vendor", "order_date"],
            key="ordered_editor"
        )
        if st.button("✅ チェック項目の納品を確認しました", type="primary", use_container_width=True):
            for i, row in edited_ordered.iterrows():
                orig_id = row["id"]
                idx = df_orders[df_orders["id"] == orig_id].index[0]
                df_orders.at[idx, "quantity"] = row["quantity"]
                df_orders.at[idx, "delivery_date"] = str(row["delivery_date"])
                if row["入荷"]:
                    df_orders.at[idx, "status"] = "完了"
            update_github_data(FILE_PATH_ORDERS, df_orders, sha_orders, "Delivery Confirmed")
            st.rerun()
    else:
        st.write("現在、入荷待ちの資材はありません。")

done_df = df_orders[df_orders['status'] == '完了'].sort_values("delivery_date", ascending=False)
with st.expander(f"👌 完了履歴 (直近{len(done_df.head(30))}件)", expanded=False):
    if not done_df.empty:
        st.dataframe(done_df[["category", "item_name", "product_name", "quantity", "vendor", "delivery_date", "request_date"]].head(30), use_container_width=True, hide_index=True)
    else:
        st.write("完了した履歴はありません。")
