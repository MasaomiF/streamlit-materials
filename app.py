import io
import pandas as pd
import streamlit as st
import html
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

    # comment（優先: comment / comments / 備考 / 説明 / note / コメント）
    if "comment" not in df.columns:
        s = pick_series(df, ["comment", "comments", "備考", "説明", "note", "コメント"])
        if s is not None:
            df["comment"] = s
    if "comment" not in df.columns:
        df["comment"] = ""

    # ドキュメント列（JSONリッチテキスト/HTML想定）を補助入力として扱う
    doc_series = pick_series(df, ["ドキュメント", "document", "doc"]) or ""
    df["document_raw"] = doc_series.astype(str) if hasattr(doc_series, "astype") else str(doc_series)

    # ---- リッチテキスト → HTML 変換器 ----
    def _autolink(text: str) -> str:
        # URLを<a>化
        return re.sub(r"(https?://[\w\-./%?#=&]+)", r"<a href='\1' target='_blank' rel='noopener'>\1</a>", text)

    def rich_to_html(val: object) -> str:
        if val is None or (isinstance(val, float) and pd.isna(val)):
            return ""
        s = str(val).strip()
        if not s:
            return ""
        # Wix/Editor風 JSON（nodes を持つ）をテキスト化
        if s.startswith("{") and '"nodes"' in s:
            try:
                import json as _json
                doc = _json.loads(s)
                parts = []
                for node in doc.get("nodes", []):
                    if isinstance(node, dict) and node.get("type") == "PARAGRAPH":
                        texts = []
                        for t in node.get("nodes", []):
                            if isinstance(t, dict) and t.get("type") == "TEXT":
                                td = t.get("textData", {})
                                txt = td.get("text", "")
                                url = None
                                for d in td.get("decorations", []) or []:
                                    if d.get("type") == "LINK":
                                        url = d.get("linkData", {}).get("link", {}).get("url")
                                if url:
                                    texts.append(f"<a href='{html.escape(url)}' target='_blank' rel='noopener'>{html.escape(txt or url)}</a>")
                                else:
                                    texts.append(html.escape(txt))
                        parts.append("<p>" + "".join(texts) + "</p>")
                return "".join(parts)
            except Exception:
                # JSONとして扱えなければ通常処理へフォールバック
                pass
        # 既にHTMLっぽいならそのまま
        if "<" in s and ">" in s:
            return s
        # プレーンテキスト → エスケープ＆リンク化＆改行変換
        s = html.escape(s)
        s = _autolink(s)
        return s.replace("\n", "<br>")

    # コメント本文：commentが空ならdocument_rawを使う
    base_text = df["comment"].astype(str)
    needs_fallback = base_text.str.strip().eq("")
    base_text = base_text.where(~needs_fallback, df["document_raw"])  # 空ならドキュメントで補完

    # HTMLへ変換（以降、comment列はHTMLとして扱う）
    df["comment"] = base_text.map(rich_to_html)

    # 必須列の確保
    for c in ["category","name","lambda","evidence","comment"]:
        if c not in df.columns:
            df[c] = ""

    # 型整形
    df["lambda"] = pd.to_numeric(df["lambda"], errors="coerce")
    df["category"] = df["category"].astype(str)
    df["name"] = df["name"].astype(str)
    df["evidence"] = df["evidence"].astype(str)
    # df["comment"] は既にHTML文字列

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
st.caption("列：category / name / lambda (W/mK) / evidence / comment（※commentはリッチテキストを解釈して表示）")

# ---- リッチテキスト対応のHTMLテーブル描画 ----
# 安全のため、comment以外はHTMLエスケープし、commentはそのまま挿入して装飾を生かす
cols = ["category","name","lambda","evidence","comment"]
view_disp = view[cols] if all(c in view.columns for c in cols) else view

# シンプルなスタイル
table_css = """
<style>
.materials-table {width: 100%; border-collapse: collapse;}
.materials-table th, .materials-table td {border: 1px solid #ddd; padding: 8px; vertical-align: top;}
.materials-table th {background: #f6f6f6; position: sticky; top: 0; z-index: 1;}
.materials-table td pre {margin: 0; white-space: pre-wrap;}
.wrap {word-break: break-word;}
</style>
"""

headers = ["category", "name", "lambda (W/mK)", "evidence", "comment"]
rows_html = []
for _, r in view_disp.iterrows():
    cat = html.escape(str(r.get("category", "")))
    name = html.escape(str(r.get("name", "")))
    lam = r.get("lambda", "")
    lam_str = "" if pd.isna(lam) else html.escape(f"{lam}")
    evd = html.escape(str(r.get("evidence", "")))
    # commentはリッチ（HTML）をそのまま差し込み／空なら空文字
    cmt_html = str(r.get("comment", ""))  # ここは既にHTML
    cmt_cell = cmt_html if cmt_html.strip() else ""
    rows_html.append(
        f"<tr>\n<td class='wrap'>{cat}</td>\n<td class='wrap'>{name}</td>\n<td>{lam_str}</td>\n<td class='wrap'>{evd}</td>\n<td class='wrap'>{cmt_cell}</td>\n</tr>"
    )

table_html = table_css + "<table class='materials-table'>" \
    + "<thead><tr>" + "".join(f"<th>{html.escape(h)}</th>" for h in headers) + "</tr></thead>" \
    + "<tbody>" + "".join(rows_html) + "</tbody></table>"

st.markdown(table_html, unsafe_allow_html=True)