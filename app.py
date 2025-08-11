import os
import io
import base64
from typing import Tuple

import pandas as pd
import streamlit as st

st.set_page_config(page_title="Materials CSV Editor", layout="wide")
st.title("Materials CSV Editor")

EXPECTED_COLUMNS = ["category", "name", "lambda", "density", "notes"]
NUMERIC_COLUMNS = ["lambda", "density"]

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
    if df is None:
        return pd.DataFrame(columns=EXPECTED_COLUMNS)
    # 列名を小文字化
    df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
    # 足りない列を補完
    for col in EXPECTED_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[EXPECTED_COLUMNS]
    # 数値列を数値化
    for col in NUMERIC_COLUMNS:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    return df


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
    return pd.DataFrame(columns=EXPECTED_COLUMNS)


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
filter_category = st.sidebar.text_input("Category contains", "")
filter_name = st.sidebar.text_input("Name contains", "")

st.sidebar.subheader("CSV import (merge)")
uploaded = st.sidebar.file_uploader("Upload CSV", type=["csv"], accept_multiple_files=False)
if uploaded is not None:
    try:
        imp = pd.read_csv(uploaded)
        imp = normalize_columns(imp)
        # upsert key
        imp_key = imp["category"].astype(str).str.strip().str.lower() + "::" + imp["name"].astype(str).str.strip().str.lower()
        imp["__key"] = imp_key

        cur = st.session_state.df.copy()
        cur_key = cur["category"].astype(str).str.strip().str.lower() + "::" + cur["name"].astype(str).str.strip().str.lower()
        cur["__key"] = cur_key
        cur_index_by_key = {k: i for i, k in enumerate(cur["__key"]) }

        for _, row in imp.iterrows():
            k = row["__key"]
            if k in cur_index_by_key:
                i = cur_index_by_key[k]
                for c in EXPECTED_COLUMNS:
                    cur.at[i, c] = row[c]
            else:
                cur = pd.concat([cur, pd.DataFrame([row[EXPECTED_COLUMNS]])], ignore_index=True)
        st.session_state.df = normalize_columns(cur.drop(columns=["__key"]))
        st.sidebar.success("CSV をマージしました（category+name で upsert）。")
    except Exception as e:
        st.sidebar.error(f"インポート失敗: {e}")

# ------------------------
# フィルタ適用
# ------------------------
view = st.session_state.df.copy()
if filter_category:
    view = view[view["category"].astype(str).str.contains(filter_category, case=False, na=False)]
if filter_name:
    view = view[view["name"].astype(str).str.contains(filter_name, case=False, na=False)]

# ------------------------
# 表示・編集
# ------------------------
st.subheader("テーブル編集")
edited = st.data_editor(
    view,
    num_rows="dynamic",
    use_container_width=True,
    column_config={
        "lambda": st.column_config.NumberColumn("lambda (W/mK)", help="Thermal conductivity", step=0.0001, format="%.4f"),
        "density": st.column_config.NumberColumn("density (kg/m³)", step=1, format="%.0f"),
        "category": st.column_config.TextColumn("category"),
        "name": st.column_config.TextColumn("name"),
        "notes": st.column_config.TextColumn("notes"),
    },
    hide_index=True,
)

# 編集内容を元データへ反映
f_reset = view.reset_index()
e_reset = edited.reset_index(drop=True)
base = st.session_state.df.copy()

for i in range(min(len(f_reset), len(e_reset))):
    orig_idx = f_reset.loc[i, "index"]
    base.loc[orig_idx, EXPECTED_COLUMNS] = e_reset.loc[i, EXPECTED_COLUMNS].values

# 追加行
if len(e_reset) > len(f_reset):
    new_rows = e_reset.iloc[len(f_reset):][EXPECTED_COLUMNS]
    base = pd.concat([base, new_rows], ignore_index=True)

st.session_state.df = normalize_columns(base)

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