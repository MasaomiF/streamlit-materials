import os
import pandas as pd
import streamlit as st
import base64

st.set_page_config(page_title="Materials CSV Editor", layout="wide")
st.title("Materials CSV Editor")

# ====== CSV I/O ======
def load_csv() -> pd.DataFrame:
    """ローカルCSVファイルを読み込み"""
    try:
        if os.path.exists("material_db.csv"):
            return pd.read_csv("material_db.csv")
        else:
            return pd.DataFrame()
    except Exception as e:
        st.error(f"CSVファイルの読み込みに失敗しました: {e}")
        return pd.DataFrame()

def save_csv(df: pd.DataFrame) -> bool:
    """ローカルCSVファイルに保存"""
    try:
        df.to_csv("material_db.csv", index=False)
        return True
    except Exception as e:
        st.error(f"CSVファイルの保存に失敗しました: {e}")
        return False

def make_download_link(df: pd.DataFrame, filename: str = "material_db.csv") -> str:
    """ダウンロードリンクを生成"""
    csv = df.to_csv(index=False)
    b64 = base64.b64encode(csv.encode()).decode()
    return f'<a download="{filename}" href="data:text/csv;base64,{b64}">Download CSV</a>'

# ====== 初期ロード ======
if "df" not in st.session_state:
    st.session_state.df = load_csv()

# ====== サイドバー（フィルタ & インポート） ======
st.sidebar.header("Filters & Actions")

# 動的にフィルタ列を生成
if not st.session_state.df.empty:
    filter_columns = st.session_state.df.columns.tolist()
    filter_values = {}
    
    for col in filter_columns[:5]:  # 最初の5列のみフィルタ表示
        filter_values[col] = st.sidebar.text_input(f"{col} contains", "")

st.sidebar.subheader("CSV import (merge)")
uploaded = st.sidebar.file_uploader("Upload CSV", type=["csv"], accept_multiple_files=False)
if uploaded is not None:
    try:
        imp = pd.read_csv(uploaded)
        # 既存データとマージ（全列を保持）
        st.session_state.df = pd.concat([st.session_state.df, imp], ignore_index=True).drop_duplicates()
        st.sidebar.success("CSV をマージしました。")
    except Exception as e:
        st.sidebar.error(f"インポート失敗: {e}")

# ====== フィルタ適用 ======
view = st.session_state.df.copy()
if not st.session_state.df.empty and 'filter_values' in locals():
    try:
        for col, filter_value in filter_values.items():
            if filter_value and col in view.columns:
                # 安全なフィルタリング
                try:
                    view = view[view[col].astype(str).str.contains(filter_value, case=False, na=False)]
                except Exception:
                    # フィルタリングに失敗した場合はその列をスキップ
                    st.warning(f"列 '{col}' のフィルタリングに失敗しました")
    except Exception as e:
        st.error(f"フィルタの適用でエラーが発生しました: {e}")

# ====== 表示・編集 ======
st.subheader("テーブル編集")

# 列の設定を動的に生成（安全な方法）
column_config = {}
if not view.empty:
    for col in view.columns:
        try:
            # データ型を適切に判定
            col_dtype = view[col].dtype
            
            if pd.api.types.is_bool_dtype(col_dtype):
                # ブール型の場合はCheckboxColumnを使用
                column_config[col] = st.column_config.CheckboxColumn(col)
            elif pd.api.types.is_numeric_dtype(col_dtype):
                # 数値型の場合はNumberColumnを使用
                column_config[col] = st.column_config.NumberColumn(col, step=0.0001, format="%.4f")
            elif pd.api.types.is_datetime64_dtype(col_dtype):
                # 日時型の場合はDateColumnを使用
                column_config[col] = st.column_config.DatetimeColumn(col)
            else:
                # その他の場合はTextColumnを使用
                column_config[col] = st.column_config.TextColumn(col)
        except Exception:
            # エラーが発生した場合はデフォルトのTextColumnを使用
            column_config[col] = st.column_config.TextColumn(col)

# データエディターの設定を安全にする
try:
    edited = st.data_editor(
        view,
        num_rows="dynamic",
        use_container_width=True,
        column_config=column_config,
        hide_index=True,
    )
except Exception as e:
    st.error(f"データエディターの表示でエラーが発生しました: {e}")
    st.write("元のデータを表示します:")
    st.dataframe(view, use_container_width=True)
    edited = view  # 編集できない場合は元のデータを使用

# ====== 編集内容を元データへ反映 ======
if not view.empty and 'edited' in locals():
    try:
        f_reset = view.reset_index()
        e_reset = edited.reset_index(drop=True)
        base = st.session_state.df.copy()

        for i in range(min(len(f_reset), len(e_reset))):
            orig_idx = f_reset.loc[i, "index"]
            for col in view.columns:
                if col in base.columns:
                    try:
                        base.loc[orig_idx, col] = e_reset.loc[i, col]
                    except Exception:
                        # 個別のセルの更新に失敗した場合はスキップ
                        pass

        # 追加行
        if len(e_reset) > len(f_reset):
            try:
                new_rows = e_reset.iloc[len(f_reset):]
                base = pd.concat([base, new_rows], ignore_index=True)
            except Exception as e:
                st.warning(f"新規行の追加に失敗しました: {e}")

        st.session_state.df = base
    except Exception as e:
        st.error(f"編集内容の反映でエラーが発生しました: {e}")
        st.warning("編集内容が保存されませんでした。元のデータを維持します。")

# ====== 行削除（インデックス指定） ======
with st.expander("行削除（フィルタ後の表示インデックスで指定）"):
    idx_text = st.text_input("削除する行番号（例: 0,2,5-7）", "")
    if st.button("指定行を削除", type="primary"):
        try:
            target = set()
            for part in idx_text.split(','):
                part = part.strip()
                if not part:
                    continue
                if '-' in part:
                    a, b = part.split('-', 1)
                    a, b = int(a), int(b)
                    target |= set(range(min(a, b), max(a, b) + 1))
                else:
                    target.add(int(part))
            if not view.empty:
                base_idx = f_reset.iloc[list(target)]["index"].tolist()
                st.session_state.df = st.session_state.df.drop(index=base_idx).reset_index(drop=True)
                st.success(f"{len(base_idx)} 行を削除しました。")
        except Exception as e:
            st.error(f"削除失敗: {e}")

# ====== 保存 & ダウンロード ======
col1, col2 = st.columns(2)
with col1:
    if st.button("ローカルに保存", type="primary"):
        ok = save_csv(st.session_state.df)
        if ok:
            st.success("ローカルファイルに保存しました。")
        else:
            st.error("保存に失敗しました。")
with col2:
    st.markdown(make_download_link(st.session_state.df), unsafe_allow_html=True)

st.caption("※ 『ローカルに保存』を押した時点で永続化。セッション内の変更は自動保存されません。")