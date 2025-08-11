import os
import io
import base64
from typing import Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Materials CSV Editor", layout="wide")
st.title("Materials CSV Editor")

# 元のCSVの列構造を保持するため、EXPECTED_COLUMNSの制限を削除
# EXPECTED_COLUMNS = ["category", "name", "lambda", "density", "notes"]
# NUMERIC_COLUMNS = ["lambda", "density"]

# ------------------------
# GitHub クライアント
# ------------------------
try:
    from github import Github  # PyGithub
    GITHUB_AVAILABLE = True
except Exception:
    GITHUB_AVAILABLE = False


def gh_params() -> Tuple[str, str, str]:
    repo = st.secrets.get("GH_REPO")
    branch = st.secrets.get("GH_BRANCH", "main")
    path = st.secrets.get("GH_FILE_PATH", "material_db.csv")
    return repo, branch, path


def get_github_client():
    token = st.secrets.get("GITHUB_TOKEN")
    if not token or not GITHUB_AVAILABLE:
        return None
    return Github(token)

# ------------------------
# CSV I/O
# ------------------------

def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()

    try:
        # 元の列構造を保持し、基本的なクリーニングのみ行う
        # 小文字・トリム
        norm = {c: str(c).strip() for c in df.columns}
        df = df.rename(columns=norm)
        
        # 各列のデータ型を適切に処理
        for col in df.columns:
            try:
                # 空文字列やNaNを適切に処理
                if df[col].dtype == 'object':
                    # 空文字列をNaNに変換
                    df[col] = df[col].replace('', pd.NA)
                    
                    # ブール型の可能性をチェック
                    unique_values = df[col].dropna().unique()
                    if len(unique_values) <= 2:
                        # True/False、1/0、'true'/'false'などの値をチェック
                        bool_values = set()
                        for val in unique_values:
                            if isinstance(val, str):
                                val_lower = str(val).lower()
                                if val_lower in ['true', 'false', '1', '0', 'yes', 'no']:
                                    bool_values.add(val)
                        
                        if len(bool_values) >= 2:
                            # ブール型として処理
                            df[col] = df[col].map({
                                'true': True, 'True': True, '1': True, 'yes': True, 'Yes': True,
                                'false': False, 'False': False, '0': False, 'no': False, 'No': False
                            }).fillna(df[col])
                            continue
                    
                    # 数値化を試行
                    numeric_values = pd.to_numeric(df[col], errors='coerce')
                    # 数値化できた列のみ更新
                    if not numeric_values.isna().all():
                        df[col] = numeric_values
                        
            except Exception:
                # 個別の列の処理に失敗した場合はそのまま
                pass
        
        return df
    except Exception as e:
        st.error(f"データの正規化でエラーが発生しました: {e}")
        return df  # エラーが発生した場合は元のデータを返す


def load_csv_from_github() -> pd.DataFrame:
    repo_name, branch, path = gh_params()
    client = get_github_client()
    if client and repo_name:
        repo = client.get_repo(repo_name)
        file = repo.get_contents(path, ref=branch)
        content = base64.b64decode(file.content)
        return pd.read_csv(io.BytesIO(content))
    # ローカルフォールバック
    if os.path.exists("material_db.csv"):
        return pd.read_csv("material_db.csv")
    return pd.DataFrame()


def save_csv_to_github(df: pd.DataFrame, message: str = "update material_db.csv") -> bool:
    repo_name, branch, path = gh_params()
    client = get_github_client()
    csv_bytes = df.to_csv(index=False).encode("utf-8")

    if client and repo_name:
        repo = client.get_repo(repo_name)
        try:
            contents = repo.get_contents(path, ref=branch)
            repo.update_file(path, message, csv_bytes, contents.sha, branch=branch)
        except Exception:
            repo.create_file(path, message, csv_bytes, branch=branch)
        return True
    # ローカル保存（開発用）
    with open("material_db.csv", "wb") as f:
        f.write(csv_bytes)
    return True


def make_download_link(df: pd.DataFrame, filename: str = "material_db.csv") -> str:
    b = df.to_csv(index=False).encode("utf-8")
    b64 = base64.b64encode(b).decode()
    return f'<a download="{filename}" href="data:text/csv;base64,{b64}">Download CSV</a>'

# ------------------------
# 初期ロード
# ------------------------
if "df" not in st.session_state:
    st.session_state.df = normalize_columns(load_csv_from_github())

# ------------------------
# サイドバー（フィルタ & インポート）
# ------------------------
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
        imp = normalize_columns(imp)
        
        # 既存データとマージ（全列を保持）
        st.session_state.df = pd.concat([st.session_state.df, imp], ignore_index=True).drop_duplicates()
        st.sidebar.success("CSV をマージしました。")
    except Exception as e:
        st.sidebar.error(f"インポート失敗: {e}")

# ------------------------
# フィルタ適用
# ------------------------
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

# ------------------------
# 表示・編集
# ------------------------
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

# 編集内容を元データへ反映
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

        st.session_state.df = normalize_columns(base)
    except Exception as e:
        st.error(f"編集内容の反映でエラーが発生しました: {e}")
        st.warning("編集内容が保存されませんでした。元のデータを維持します。")

# ------------------------
# 行削除（インデックス指定）
# ------------------------
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

# ------------------------
# 保存 & ダウンロード
# ------------------------
col1, col2 = st.columns(2)
with col1:
    if st.button("GitHub に保存（コミット）", type="primary"):
        ok = save_csv_to_github(st.session_state.df)
        if ok:
            st.success("保存しました（GitHub またはローカル）。")
        else:
            st.error("保存に失敗しました。")
with col2:
    st.markdown(make_download_link(st.session_state.df), unsafe_allow_html=True)

st.caption("※ 『GitHub に保存』を押した時点で永続化。セッション内の変更は自動保存されません。")