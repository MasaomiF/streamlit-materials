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
    # 重複列名にも対応して、最初に有効な値を返すSeriesを取得
    def pick_series(dframe: pd.DataFrame, names: list[str]):
        for n in names:
            if n in dframe.columns:
                # 同名の重複列をすべて取得して左から優先
                sub = dframe.loc[:, dframe.columns == n]
                if isinstance(sub, pd.DataFrame):
                    if sub.shape[1] == 1:
                        return sub.iloc[:, 0]
                    # 行方向で左→右に値を補完して先頭列を採用
                    return sub.bfill(axis=1).iloc[:, 0]
                else:
                    return dframe[n]
        return None
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
    # evidence (standarda)
    if "evidence" not in df.columns:
        s = pick_series(df, ["standarda", "standard_a"])
        if s is not None:
            df["evidence"] = s
    if "evidence" not in df.columns:
        df["evidence"] = ""
    # comment
    if "comment" not in df.columns:
        s = pick_series(df, ["comment", "comments", "備考", "説明", "note", "コメント"])
        if s is not None:
            df["comment"] = s
    if "comment" not in df.columns:
        df["comment"] = ""
    # 必須列の確保
    for c in ["category","name","lambda"]:
        if c not in df.columns:
            df[c] = ""
    # 型整形
    df["lambda"] = pd.to_numeric(df["lambda"], errors="coerce")
    df["category"] = df["category"].astype(str)
    df["name"] = df["name"].astype(str)
    df["evidence"] = df["evidence"].astype(str)
    df["comment"] = df["comment"].astype(str)
    # 最低限の列にする
    return df[["category","name","lambda","evidence","comment"]].dropna(subset=["name"]).reset_index(drop=True)

# ====== サイドバー：入力 ======
st.sidebar.header("データと検索条件")
materials = load_materials(None)

st.sidebar.caption(f"材料件数: {len(materials)}")

# 検索条件
cat_options = ["(すべて)"] + sorted([c for c in materials["category"].dropna().unique().tolist() if str(c).strip() != ""]) 
sel_cat = st.sidebar.selectbox("カテゴリ", options=cat_options, index=0)

kw = st.sidebar.text_input("材料名キーワード（部分一致）", value="")

sort_col = st.sidebar.selectbox("並び替え列", ["name","category","lambda"], index=0)
sort_asc = st.sidebar.checkbox("昇順", value=True)

# ====== フィルタ適用 ======
view = materials.copy()
if sel_cat != "(すべて)":
    view = view[view["category"].astype(str) == str(sel_cat)]
if kw.strip():
    s = kw.strip().lower()
    view = view[view["name"].astype(str).str.lower().str.contains(s)]

# 並び替え
view = view.sort_values(by=sort_col, ascending=sort_asc, kind="mergesort").reset_index(drop=True)

# ====== 結果表示 ======
st.subheader("検索結果")
st.caption("列：category / name / lambda (W/mK) / evidence / comment")
st.dataframe(view[["category","name","lambda","evidence","comment"]], use_container_width=True, hide_index=True)