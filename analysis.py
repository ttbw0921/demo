import streamlit as st
import pandas as pd
import plotly.express as px
import requests
import base64
from io import StringIO
import datetime as dt

# --- 設定 ---
REPO_NAME = "iplan381/zaiko-kanri"
FILE_PATH_LOG = "stock_log_main.csv"
FILE_PATH_MASTER = "item_master.csv"
FILE_PATH_RESERVATION = "reservations_main.csv"  # 予約データ用に追加
GITHUB_TOKEN = st.secrets["GITHUB_TOKEN"]

st.set_page_config(page_title="出庫分析", layout="wide")

@st.cache_data(ttl=60)
def get_github_data(file_path):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{file_path}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    if res.status_code == 200:
        content = res.json()
        csv_text = base64.b64decode(content["content"]).decode("utf-8")
        return pd.read_csv(StringIO(csv_text)).fillna("")
    return pd.DataFrame()

# GitHub保存用関数（マスタ用）
def save_master_to_github(df_to_save):
    url = f"https://api.github.com/repos/{REPO_NAME}/contents/{FILE_PATH_MASTER}"
    headers = {"Authorization": f"token {GITHUB_TOKEN}"}
    res = requests.get(url, headers=headers)
    sha = res.json().get("sha") if res.status_code == 200 else None
    
    content = base64.b64encode(df_to_save.to_csv(index=False).encode("utf-8")).decode("utf-8")
    data = {"message": "Update master data", "content": content}
    if sha:
        data["sha"] = sha
    res_put = requests.put(url, headers=headers, json=data)
    return res_put.status_code

# 各データの読み込み
df_log_raw = get_github_data(FILE_PATH_LOG)
df_master = get_github_data(FILE_PATH_MASTER)
df_res_raw = get_github_data(FILE_PATH_RESERVATION)

if df_master.empty:
    df_master = pd.DataFrame(columns=["商品名", "サイズ", "入り数"])

st.title("📈 在庫動態分析")

if not df_log_raw.empty:
    # --- データ前処理 ---
    df = df_log_raw.copy()
    df["日時"] = pd.to_datetime(df["日時"], errors='coerce', format='mixed')
    df = df.dropna(subset=["日時"])
    df["数量"] = pd.to_numeric(df["数量"], errors='coerce').fillna(0)
    
    # 1. 実績データのベース作成
    df_out_all = df[df["区分"].str.contains("出庫")].copy()
    df_out_all["データ種別"] = "実績" 

    # --- 🔍 絞り込み条件（サイドバー） ---
    with st.sidebar:
        st.markdown("### 🔗 クイック移動")
        c1, c2 = st.columns(2)
        c1.link_button("📦 在庫管理", "https://zaiko-kanri.streamlit.app/")
        c2.link_button("🚚 発注管理", "https://zaiko-kanri-qzelakcnxralslk3ac27ex.streamlit.app/")
        st.divider()
    
        st.sidebar.header("🔍 絞り込み条件")

        # 【新機能】予約スイッチと合体処理
        show_reservation = st.checkbox("📅 出庫予約を含めて分析する", value=False)
        
        if show_reservation and not df_res_raw.empty:
            df_res = df_res_raw.copy()
            df_res["日時"] = pd.to_datetime(df_res["予約日"], errors='coerce')
            df_res["数量"] = pd.to_numeric(df_res["数量"], errors='coerce').fillna(0)
            df_res["データ種別"] = "予約"
            df_out_all = pd.concat([df_out_all, df_res], ignore_index=True)

        # 項目詳細の作成
        df_out_all["項目詳細"] = df_out_all["商品名"].astype(str) + " | " + df_out_all["サイズ"].astype(str) + " | " + df_out_all["地名"].astype(str)

        # カレンダー用の日付計算
        min_d = df_out_all["日時"].min().date()
        max_d = df_out_all["日時"].max().date()
        start_default = max(min_d, max_d - dt.timedelta(days=30))
        
        date_range = st.date_input("📅 期間を選択", [start_default, max_d], min_value=min_d, max_value=max_d)

        all_item_list = ["すべて表示"] + sorted(df_out_all["商品名"].unique().tolist())
        all_size_list = ["すべて表示"] + sorted(df_out_all["サイズ"].unique().tolist())
        all_loc_list = ["すべて表示"] + sorted(df_out_all["地名"].unique().tolist())

        sel_item = st.selectbox("📦 商品名を選択", all_item_list)
        sel_size = st.selectbox("📏 サイズを選択", all_size_list)
        sel_loc = st.selectbox("📍 地名を選択", all_loc_list)
        
        exclude_wrapping = st.checkbox("包装紙を除外する", value=False)
        show_compare = st.checkbox("昨年対比を表示する", value=True)

    # --- 最終的なフィルタリング実行 ---
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
        df_final = df_out_all[(df_out_all["日時"].dt.date >= start_date) & (df_out_all["日時"].dt.date <= end_date)].copy()
        
        # 昨年対比用（実績のみで比較）
        ls, le = start_date - dt.timedelta(days=365), end_date - dt.timedelta(days=365)
        df_last = df_out_all[(df_out_all["データ種別"] == "実績") & (df_out_all["日時"].dt.date >= ls) & (df_out_all["日時"].dt.date <= le)].copy()
    else:
        st.info("カレンダーで開始日と終了日を選択してください。")
        st.stop()

    if sel_item != "すべて表示":
        df_final, df_last = df_final[df_final["商品名"] == sel_item], df_last[df_last["商品名"] == sel_item]
    if sel_size != "すべて表示":
        df_final, df_last = df_final[df_final["サイズ"] == sel_size], df_last[df_last["サイズ"] == sel_size]
    if sel_loc != "すべて表示":
        df_final, df_last = df_final[df_final["地名"] == sel_loc], df_last[df_last["地名"] == sel_loc]
    if exclude_wrapping:
        df_final = df_final[~df_final["地名"].str.contains("包装紙", na=False)]
        df_last = df_last[~df_last["地名"].str.contains("包装紙", na=False)]

    st.divider()

    # --- 表示ロジック ---
    if not df_final.empty:
        df_sum_this = df_final.groupby(["商品名", "サイズ"])["数量"].sum().reset_index()
        df_m_calc = pd.merge(df_sum_this, df_master, on=["商品名", "サイズ"], how="left")
        df_m_calc["入り数"] = pd.to_numeric(df_m_calc["入り数"], errors='coerce').fillna(1).astype(int)
        
        total_cases_this = df_m_calc["数量"].sum()
        total_pcs_this = (df_m_calc["数量"] * df_m_calc["入り数"]).sum()
        qty_last = df_last["数量"].sum()
        
        cols = st.columns(5) if show_compare else st.columns(4)
        with cols[0]: st.metric("期間内 合計出荷(バラ)", f"{int(total_pcs_this):,}")
        with cols[1]: st.metric("期間内 合計ケース数", f"{int(total_cases_this):,} cs")
        
        if show_compare:
            diff_pct = f"{round(((total_cases_this - qty_last) / qty_last) * 100, 1)}%" if qty_last > 0 else "---"
            with cols[2]: st.metric("前年同期実績(cs)", f"{int(qty_last):,}")
            with cols[3]: st.metric("前年同期比", diff_pct)
            with cols[4]: st.metric("稼働詳細項目数", f"{df_final['項目詳細'].nunique()}")
        else:
            with cols[2]: st.metric("稼働詳細項目数", f"{df_final['項目詳細'].nunique()}")
            with cols[3]: st.metric("平均出荷量(cs)", f"{round(df_final['数量'].mean(), 1)}")

        tab1, tab2, tab4, tab5, tab_m = st.tabs(["📊 傾向", "📦 商品別出荷集計", "⚠️ 不動・安全在庫", "🔢 履歴明細", "⚙️ マスタ設定"])

        with tab1:
            st.subheader("📦 詳細項目別ランキング（上位20件）")
            # 実績と予約を色分けして表示
            summary_rank = df_final.groupby(["項目詳細", "データ種別"])["数量"].sum().reset_index().sort_values("数量", ascending=True).tail(20)
            fig_rank = px.bar(summary_rank, y="項目詳細", x="数量", orientation='h', text_auto=True, color="データ種別",
                              color_discrete_map={"実績": "#3B82F6", "予約": "#F59E0B"})
            fig_rank.update_layout(coloraxis_showscale=False)
            st.plotly_chart(fig_rank, use_container_width=True)

            c1, c2 = st.columns(2)
            with c1:
                st.subheader("📍 地名別")
                st.plotly_chart(px.pie(df_final, values='数量', names='地名', hole=0.4), use_container_width=True)
            with c2:
                st.subheader("📅 曜日別傾向")
                df_final["曜日"] = df_final["日時"].dt.day_name()
                day_jp = {'Monday':'月','Tuesday':'火','Wednesday':'水','Thursday':'木','Friday':'金','Saturday':'土','Sunday':'日'}
                summary_day = df_final.groupby(["曜日", "データ種別"])["数量"].sum().reset_index()
                summary_day["表示曜日"] = summary_day["曜日"].map(day_jp)
                fig_day = px.bar(summary_day, x="表示曜日", y="数量", text_auto=True, color="データ種別",
                                 color_discrete_map={"実績": "#3B82F6", "予約": "#F59E0B"},
                                 category_orders={"表示曜日": ['月', '火', '水', '木', '金', '土', '日']})
                st.plotly_chart(fig_day, use_container_width=True)

        with tab2:
            st.subheader("📦 指定期間の出荷合計（入り数換算）")
            summary_prod = df_final.groupby(["商品名", "サイズ"])["数量"].sum().reset_index().rename(columns={"数量": "出荷ケース数"})
            df_merged = pd.merge(summary_prod, df_master, on=["商品名", "サイズ"], how="left")
            df_merged["入り数"] = pd.to_numeric(df_merged["入り数"], errors='coerce').fillna(1).astype(int)
            df_merged["合計バラ数"] = df_merged["出荷ケース数"] * df_merged["入り数"]
            st.dataframe(df_merged.sort_values("合計バラ数", ascending=False), use_container_width=True, hide_index=True)

        with tab4:
            col_w1, col_w2 = st.columns(2)
            with col_w1:
                st.subheader("⚠️ 不動在庫 (実績のみ)")
                df_db = df_out_all[df_out_all["データ種別"] == "実績"].copy()
                if sel_item != "すべて表示": df_db = df_db[df_db["商品名"] == sel_item]
                if sel_size != "すべて表示": df_db = df_db[df_db["サイズ"] == sel_size]
                if sel_loc != "すべて表示": df_db = df_db[df_db["地名"] == sel_loc]
                now = pd.Timestamp.now()
                dead = df_db.groupby("項目詳細")["日時"].max().reset_index()
                dead["経過日数"] = (now - dead["日時"]).dt.days
                st.dataframe(dead.sort_values("経過日数", ascending=False), use_container_width=True, hide_index=True)
            with col_w2:
                st.subheader("💡 推奨・安全在庫")
                safety_df = df_final.groupby("項目詳細")["数量"].agg(['mean', 'std']).reset_index().fillna(0)
                safety_df["推奨在庫"] = (safety_df["mean"] + 2 * safety_df["std"]).round(0)
                st.dataframe(safety_df[["項目詳細", "推奨在庫"]].sort_values("推奨在庫", ascending=False), use_container_width=True, hide_index=True)

        with tab5:
            st.subheader("🔢 履歴明細")
            st.dataframe(df_final[["日時", "商品名", "サイズ", "地名", "数量", "データ種別"]].sort_values("日時", ascending=False), use_container_width=True, hide_index=True)

        with tab_m:
            st.subheader("⚙️ 入り数マスタの編集")
            current_items = df_out_all[["商品名", "サイズ"]].drop_duplicates()
            df_editor = pd.merge(current_items, df_master, on=["商品名", "サイズ"], how="left")
            df_editor["入り数"] = df_editor["入り数"].fillna(1)
            edited_df = st.data_editor(df_editor, use_container_width=True, hide_index=True, num_rows="dynamic")
            if st.button("マスタをGitHubに保存する"):
                with st.spinner("保存中..."):
                    edited_df["入り数"] = pd.to_numeric(edited_df["入り数"], errors='coerce').fillna(1).astype(int)
                    if save_master_to_github(edited_df) in [200, 201]:
                        st.success("マスタをGitHubに保存したよ！")
                        st.cache_data.clear()
                        st.rerun()
                    else:
                        st.error("保存に失敗しました。")
    else:
        st.info("選択された条件に該当するデータがありません。")
else:
    st.error("データの読み込みに失敗しました。")
