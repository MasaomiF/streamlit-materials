import io
import pandas as pd
import streamlit as st
import json
import re

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

    def pick_col(dframe, names):
        for n in names:
            if n in dframe.columns:
                return n
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
    
    # evidence: standardA を根拠テキストとして採用（旧standardDにも配慮）
    std_a_col = pick_col(df, ["standarda", "standard_a"])  # 正式
    std_d_col = pick_col(df, ["standardd", "standard_d", "standerdd", "standerd_d"])  # 誤記/旧列
    if std_a_col:
        df["evidence"] = df[std_a_col]
    elif std_d_col:
        df["evidence"] = df[std_d_col]
    else:
        df["evidence"] = ""

    # コメント（リッチテキスト想定）
    # 優先: コメント / comment / note のいずれか
    cmt_col = pick_col(df, ["コメント", "comment", "note"])
    if cmt_col:
        df["comment_raw"] = df[cmt_col].astype(str)
    else:
        df["comment_raw"] = ""

    # ドキュメント列（JSONリッチテキストの可能性）
    doc_col = pick_col(df, ["ドキュメント", "document", "doc"])
    if doc_col:
        df["document_raw"] = df[doc_col].astype(str)
    else:
        df["document_raw"] = ""

    # コメントのプレーンテキストと簡易HTML生成
    def _to_plain_text(s: str) -> str:
        if not isinstance(s, str):
            return ""
        # HTMLを簡易除去
        s2 = re.sub(r"<[^>]+>", " ", s)
        # JSON(wix editorのような構造)からtextを抽出
        if s2.strip().startswith("{"):
            try:
                obj = json.loads(s2)
                texts = []
                def walk(node):
                    if isinstance(node, dict):
                        if node.get("type") == "TEXT" and "textData" in node and node["textData"].get("text"):
                            texts.append(node["textData"]["text"]) 
                        for v in node.values():
                            walk(v)
                    elif isinstance(node, list):
                        for it in node:
                            walk(it)
                walk(obj)
                if texts:
                    return "\n".join(texts)
            except Exception:
                pass
        return s2

    def _to_simple_html(s: str) -> str:
        if not isinstance(s, str):
            return ""
        # 既にHTMLのときはそのまま
        if "</" in s or "<p" in s or "<a" in s:
            return s
        # JSON風のときはテキスト抽出 + URLをリンク化
        try:
            if s.strip().startswith("{"):
                plain = _to_plain_text(s)
            else:
                plain = str(s)
        except Exception:
            plain = str(s)
        # URL自動リンク
        plain = re.sub(r"(https?://[\w\-./%?#=&]+)", r"<a href='\1' target='_blank'>\1</a>", plain)
        return "<div>" + plain.replace("\n", "<br>") + "</div>"

    # comment_html は コメント優先、なければドキュメントから生成
    df["comment_html"] = df["comment_raw"].apply(lambda s: _to_simple_html(s) if isinstance(s, str) and s.strip() else "")
    fallback_html = df["document_raw"].apply(lambda s: _to_simple_html(s) if isinstance(s, str) and s.strip() else "")
    df.loc[df["comment_html"].eq(""), "comment_html"] = fallback_html

    # 表示用の簡易プレーンテキスト列（テーブル用）
    df["comment"] = df["comment_html"].apply(lambda s: re.sub(r"<[^>]+>", " ", s).strip())

    # 必須列の確保
    for c in ["category","name","lambda","evidence","comment","comment_html"]:
        if c not in df.columns:
            df[c] = ""
    # 型整形
    df["lambda"] = pd.to_numeric(df["lambda"], errors="coerce")
    df["category"] = df["category"].astype(str)
    df["name"] = df["name"].astype(str)
    # 最低限の列にする
    return df[["category","name","lambda","evidence","comment","comment_html"]].dropna(subset=["name"]).reset_index(drop=True)

# ====== サイドバー：入力 ======
st.sidebar.header("データと検索条件")
uploaded = st.sidebar.file_uploader("material_db.csv をアップロード（任意）", type=["csv"]) 
materials = load_materials(uploaded.read() if uploaded else None)

st.sidebar.caption(f"材料件数: {len(materials)}")

# 検索条件
cat_options = ["(すべて)"] + sorted([c for c in materials["category"].dropna().unique().tolist() if str(c).strip() != ""]) 
sel_cat = st.sidebar.selectbox("カテゴリ", options=cat_options, index=0)

kw = st.sidebar.text_input("材料名キーワード（部分一致）", value="")

# ====== フィルタ適用 ======
view = materials.copy()
if sel_cat != "(すべて)":
    view = view[view["category"].astype(str) == str(sel_cat)]
if kw.strip():
    s = kw.strip().lower()
    view = view[view["name"].astype(str).str.lower().str.contains(s)]

# 並び替え
sort_col = st.sidebar.selectbox("並び替え列", ["name","category","lambda"], index=0)
sort_asc = st.sidebar.checkbox("昇順", value=True)
view = view.sort_values(by=sort_col, ascending=sort_asc, kind="mergesort").reset_index(drop=True)

# ====== 結果表示 ======
st.subheader("検索結果")
st.caption("列：category / name / lambda (W/mK) / evidence (standardA) / comment")
cols = ["category","name","lambda","evidence","comment"]
view_disp = view[cols] if all(c in view.columns for c in cols) else view
st.dataframe(view_disp, use_container_width=True, hide_index=True)

colA, colB = st.columns(2)
with colA:
    st.metric("表示件数", len(view))
with colB:
    if not view.empty:
        csv_bytes = view.to_csv(index=False).encode("utf-8")
        st.download_button("この結果をCSVダウンロード", csv_bytes, file_name="materials_filtered.csv", mime="text/csv")

# ====== リッチコメント表示 ======
if not view.empty:
    st.subheader("選択行のコメント（リッチ表示）")
    names = view["name"].tolist()
    sel_name = st.selectbox("表示する材料", options=names, index=0)
    row = view[view["name"] == sel_name].iloc[0]
    st.markdown(f"**Evidence (standardA):** {row['evidence']}")
    if str(row.get("comment_html", "")).strip():
        st.markdown(row["comment_html"], unsafe_allow_html=True)
    else:
        st.info("コメントはありません。")

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