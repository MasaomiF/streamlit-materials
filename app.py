import io
import pandas as pd
import streamlit as st

st.set_page_config(page_title="Materials Search", layout="wide")
st.title("Materials Search（シンプル版）")

# ====== データ読み込み ======
@st.cache_data
def load_materials(file_bytes: bytes | None) -> pd.DataFrame:
    if file_bytes:
        _buf = io.BytesIO(file_bytes)
        for enc in (None, "utf-8", "utf-8-sig", "cp932", "shift_jis", "latin1"):
            try:
                _buf.seek(0)
                df = pd.read_csv(_buf, encoding=enc) if enc else pd.read_csv(_buf)
                break
            except Exception:
                df = None
        if df is None:
            df = pd.DataFrame(columns=["category","name","lambda"])  # フォールバック
    else:
        df = None
        for enc in (None, "utf-8", "utf-8-sig", "cp932", "shift_jis", "latin1"):
            try:
                df = pd.read_csv("material_db.csv", encoding=enc) if enc else pd.read_csv("material_db.csv")
                break
            except Exception:
                df = None
        if df is None:
            df = pd.DataFrame(columns=["category","name","lambda"])  # 空の雛形
    # 列名を正規化
    df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
    # 同義列の吸収
    # lambda
    if "lambda" not in df.columns:
        for alt in ["λ", "valuea", "lambda(w/mk)", "lam", "thermal_conductivity"]:
            if alt in df.columns:
                df["lambda"] = df[alt]
                break
    # name
    if "name" not in df.columns:
        for alt in ["material", "材料", "素材", "name_ja", "material_name", "品名", "名称"]:
            if alt in df.columns:
                df["name"] = df[alt]
                break
    # category
    if "category" not in df.columns:
        for alt in ["カテゴリ", "カテゴリー", "分類", "category_name", "group", "種別"]:
            if alt in df.columns:
                df["category"] = df[alt]
                break
    # 必須列の確保
    for c in ["category","name","lambda"]:
        if c not in df.columns:
            df[c] = ""
    # 型整形
    df["lambda"] = pd.to_numeric(df["lambda"], errors="coerce")
    df["category"] = df["category"].astype(str)
    df["name"] = df["name"].astype(str)
    # 最低限の列にする
    return df[["category","name","lambda"]].dropna(subset=["name"]).reset_index(drop=True)

# ====== サイドバー：入力 ======
st.sidebar.header("データと検索条件")
uploaded = st.sidebar.file_uploader("material_db.csv をアップロード（任意）", type=["csv"]) 
materials = load_materials(uploaded.read() if uploaded else None)

st.sidebar.caption(f"材料件数: {len(materials)}")

# 検索条件
cat_options = ["(すべて)"] + sorted([c for c in materials["category"].dropna().unique().tolist() if str(c).strip() != ""]) 
sel_cat = st.sidebar.selectbox("カテゴリ", options=cat_options, index=0)

kw = st.sidebar.text_input("材料名キーワード（部分一致）", value="")

import math
lam_min = float(materials["lambda"].min()) if not materials.empty else 0.0
lam_max_val = float(materials["lambda"].max()) if not materials.empty else 1.0
lam_max_ceil = math.ceil(lam_max_val)

r = st.sidebar.slider(
    "λ範囲 [W/mK]",
    min_value=0.0,
    max_value=lam_max_ceil,
    value=(max(0.0, min(lam_min, lam_max_ceil)), max(0.0, min(lam_max_val, lam_max_ceil))),
    step=0.01
)

sort_col = st.sidebar.selectbox("並び替え列", ["name","category","lambda"], index=0)
sort_asc = st.sidebar.checkbox("昇順", value=True)

# ====== フィルタ適用 ======
view = materials.copy()
if sel_cat != "(すべて)":
    view = view[view["category"].astype(str) == str(sel_cat)]
if kw.strip():
    s = kw.strip().lower()
    view = view[view["name"].astype(str).str.lower().str.contains(s)]
view = view[(view["lambda"].fillna(0) >= r[0]) & (view["lambda"].fillna(0) <= r[1])]

# 並び替え
view = view.sort_values(by=sort_col, ascending=sort_asc, kind="mergesort").reset_index(drop=True)

# ====== 結果表示 ======
st.subheader("検索結果")
st.caption("列：category / name / lambda (W/mK)")
st.dataframe(view, use_container_width=True, hide_index=True)

colA, colB = st.columns(2)
with colA:
    st.metric("表示件数", len(view))
with colB:
    if not view.empty:
        csv_bytes = view.to_csv(index=False).encode("utf-8")
        st.download_button("この結果をCSVダウンロード", csv_bytes, file_name="materials_filtered.csv", mime="text/csv")

# ====== ヘルプ ======
with st.expander("使い方ヘルプ", expanded=False):
    st.markdown(
        """
        - 左側で **カテゴリ**・**材料名キーワード**・**λ範囲** を指定して絞り込みます。
        - 表の右上のメニューから列の並び替えやフィルタも追加できます。
        - **この結果をCSVダウンロード** で絞り込んだ一覧を保存できます。
        - 既定で `material_db.csv` を同じフォルダから読み込みます。更新したCSVをアップすると即時反映されます。
        """
    )