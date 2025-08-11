import io
import json
import pandas as pd
import streamlit as st

st.set_page_config(page_title="U-Value Calc (Python/Streamlit)", layout="wide")
st.title("U-Value Calc (Python/Streamlit)")

# ====== 設定 ======
DEFAULT_RSI = 0.11   # 室内表面熱伝達抵抗 [m²K/W]（例値）
DEFAULT_RSE = 0.04   # 室外表面熱伝達抵抗 [m²K/W]（例値）
DEFAULT_TB_RATIO = 0.17  # 熱橋部面積比（例: 17%）

# ====== 材料DBの読み込み ======
@st.cache_data
def load_materials(file_bytes: bytes | None) -> pd.DataFrame:
    if file_bytes:
        df = pd.read_csv(io.BytesIO(file_bytes))
    else:
        try:
            df = pd.read_csv("material_db.csv")
        except Exception:
            df = pd.DataFrame(columns=["category","name","lambda","density","notes"])
    # 列名正規化
    df = df.rename(columns={c: str(c).strip().lower() for c in df.columns})
    if "lambda" not in df.columns:
        # 同義語対応
        for alt in ["λ","valuea","lambda(w/mk)"]:
            if alt in df.columns:
                df["lambda"] = df[alt]
                break
    # 必須列を確保
    for c in ["category","name","lambda"]:
        if c not in df.columns:
            df[c] = ""
    # 数値化
    df["lambda"] = pd.to_numeric(df["lambda"], errors="coerce")
    return df[["category","name","lambda"]].dropna(subset=["name","lambda"]).reset_index(drop=True)

# ====== λ検索ユーティリティ ======
def lookup_lambda(materials: pd.DataFrame, category: str, name: str) -> float | None:
    if not name:
        return None
    df = materials
    if category:
        df = df[df["category"].astype(str) == str(category)]
    df = df[df["name"].astype(str) == str(name)]
    if df.empty:
        # カテゴリ不一致のときは名前だけで再検索
        df = materials[materials["name"].astype(str) == str(name)]
    if df.empty:
        return None
    return float(df.iloc[0]["lambda"])

# ====== R, U 計算 ======
def layer_R(thickness_mm: float, lam: float | None) -> float:
    """層抵抗 R = 厚み/λ（厚み[m]）"""
    if lam is None or lam <= 0:
        return 0.0
    t_m = max(0.0, (thickness_mm or 0) / 1000.0)
    return t_m / lam

def u_from_Rsum(Rsi: float, R_layers_sum: float, Rse: float) -> float:
    R_total = max(1e-9, Rsi + R_layers_sum + Rse)
    return 1.0 / R_total

def calc_results(layers: pd.DataFrame, materials: pd.DataFrame, Rsi: float, Rse: float, tb_ratio: float):
    """一般部・熱橋部それぞれのUを計算し、面積比で加重平均"""
    # 一般部
    Rsum_norm = 0.0
    for _, r in layers.iterrows():
        lam = lookup_lambda(materials, r["cat_normal"], r["mat_normal"])
        Rsum_norm += layer_R(r["thickness_mm"], lam)
    U_norm = u_from_Rsum(Rsi, Rsum_norm, Rse)

    # 熱橋部（未設定の層は一般部と同じ素材として扱う）
    Rsum_tb = 0.0
    for _, r in layers.iterrows():
        name_b = r.get("mat_bridge") or r.get("mat_normal")
        cat_b  = r.get("cat_bridge") or r.get("cat_normal")
        lam_b = lookup_lambda(materials, cat_b, name_b)
        Rsum_tb += layer_R(r["thickness_mm"], lam_b)
    U_tb = u_from_Rsum(Rsi, Rsum_tb, Rse)

    # 面積比で合成
    a_tb = max(0.0, min(1.0, tb_ratio))
    U_total = (1.0 - a_tb) * U_norm + a_tb * U_tb

    return {
        "Rsum_norm": Rsum_norm,
        "Rsum_tb": Rsum_tb,
        "U_norm": U_norm,
        "U_tb": U_tb,
        "U_total": U_total
    }

# ====== サイドバー：材料DB & 基本設定 ======
st.sidebar.header("1) Materials DB / 基本設定")
uploaded_db = st.sidebar.file_uploader("material_db.csv をアップロード（任意）", type=["csv"])
materials = load_materials(uploaded_db.read() if uploaded_db else None)

st.sidebar.caption(f"材料点数: {len(materials)}")
Rsi = st.sidebar.number_input("Rsi 室内表面抵抗 [m²K/W]", value=DEFAULT_RSI, step=0.01, format="%.2f")
Rse = st.sidebar.number_input("Rse 室外表面抵抗 [m²K/W]", value=DEFAULT_RSE, step=0.01, format="%.2f")
tb_ratio = st.sidebar.number_input("熱橋部面積比 (0〜1)", value=DEFAULT_TB_RATIO, min_value=0.0, max_value=1.0, step=0.01, format="%.2f")

# ====== 層データ（DataFrameベースUI） ======
st.header("2) 層構成（厚みは両部共通）")
st.caption("各レイヤーで『一般部用Material』『熱橋部用Material』を別々に選べます（未指定時は一般部と同じ）。")

# 候補リスト（カテゴリ→材料名）
cat_options = [""] + sorted(materials["category"].dropna().astype(str).unique().tolist())
def names_for(cat: str) -> list[str]:
    if not cat:
        return sorted(materials["name"].dropna().astype(str).unique().tolist())
    return sorted(materials.loc[materials["category"].astype(str)==str(cat), "name"].dropna().astype(str).unique().tolist())

# 初期層（例）
if "layers_df" not in st.session_state:
    st.session_state.layers_df = pd.DataFrame([
        {"order":1, "thickness_mm":12.5, "cat_normal":"仕上げ", "mat_normal":"石膏ボード12.5", "cat_bridge":"", "mat_bridge":""},
        {"order":2, "thickness_mm":105,  "cat_normal":"断熱材", "mat_normal":"グラスウール16K", "cat_bridge":"", "mat_bridge":""},
        {"order":3, "thickness_mm":9,    "cat_normal":"木質系", "mat_normal":"構造用合板",     "cat_bridge":"", "mat_bridge":""},
    ])

# data_editor の列設定
def colcfg_text(label): return st.column_config.TextColumn(label)
def colcfg_num(label, step=0.5, fmt="%.1f"): return st.column_config.NumberColumn(label, step=step, format=fmt)

layers_view = st.data_editor(
    st.session_state.layers_df,
    use_container_width=True,
    num_rows="dynamic",
    column_config={
        "order": colcfg_num("order", step=1, fmt="%.0f"),
        "thickness_mm": colcfg_num("thickness_mm [mm]", step=0.5, fmt="%.1f"),
        "cat_normal": colcfg_text("cat_normal"),
        "mat_normal": colcfg_text("mat_normal"),
        "cat_bridge": colcfg_text("cat_bridge"),
        "mat_bridge": colcfg_text("mat_bridge"),
    },
    hide_index=True
)

# 入力補助（カテゴリ選択→材料候補を提示）
with st.expander("素材候補ヘルプ（カテゴリ→材料名）", expanded=False):
    colA, colB = st.columns(2)
    with colA:
        sel_cat = st.selectbox("カテゴリを選択", cat_options, index=0)
    with colB:
        st.write("材料候補（クリックでコピー→セルに貼付）")
        st.write(names_for(sel_cat)[:100])

# 編集反映・並び替え
layers_clean = layers_view.copy()
layers_clean["order"] = pd.to_numeric(layers_clean["order"], errors="coerce").fillna(0).astype(int)
layers_clean = layers_clean.sort_values("order").reset_index(drop=True)
st.session_state.layers_df = layers_clean

# ====== 計算 ======
if layers_clean.empty:
    st.warning("レイヤーを1つ以上追加してください。")
else:
    res = calc_results(layers_clean, materials, Rsi, Rse, tb_ratio)

    st.header("3) 計算結果")
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("U 一般部 [W/m²K]", f"{res['U_norm']:.3f}")
    with col2:
        st.metric("U 熱橋部 [W/m²K]", f"{res['U_tb']:.3f}")
    with col3:
        st.metric("U 合成（面積比適用） [W/m²K]", f"{res['U_total']:.3f}")

    with st.expander("詳細（R の内訳）", expanded=False):
        st.write(f"Rsum 一般部（層合計）: **{res['Rsum_norm']:.3f} m²K/W**")
        st.write(f"Rsum 熱橋部（層合計）: **{res['Rsum_tb']:.3f} m²K/W**")
        st.write(f"Rsi: {Rsi:.2f} / Rse: {Rse:.2f}")
        st.write(f"熱橋部面積比: {tb_ratio:.2f}")

# ====== 保存/読み込み（JSON） ======
st.header("4) 設定の保存/読み込み（JSON）")
colS, colL = st.columns(2)
with colS:
    proj = {
        "Rsi": Rsi, "Rse": Rse, "thermalBridgeRatio": tb_ratio,
        "layers": st.session_state.layers_df.to_dict(orient="records")
    }
    j = json.dumps(proj, ensure_ascii=False, indent=2)
    st.download_button("プロジェクトをダウンロード（JSON）", j, file_name="uvalue_project.json", mime="application/json")
with colL:
    up = st.file_uploader("プロジェクトを読み込み（JSON）", type=["json"], key="projup")
    if up is not None:
        try:
            data = json.loads(up.read().decode("utf-8"))
            st.session_state.layers_df = pd.DataFrame(data.get("layers", []))
            st.session_state.layers_df = st.session_state.layers_df[["order","thickness_mm","cat_normal","mat_normal","cat_bridge","mat_bridge"]]
            st.session_state.layers_df["order"] = pd.to_numeric(st.session_state.layers_df["order"], errors="coerce").fillna(0).astype(int)
            st.experimental_rerun()
        except Exception as e:
            st.error(f"読み込みに失敗しました: {e}")