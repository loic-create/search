# --- TFTP — Companies Explorer (smart intent + semantic) ----------------------
from typing import List, Any, Dict
from openai import OpenAI as OpenAIClient
import pandas as pd
import numpy as np
import unicodedata
import os
import streamlit as st
from pathlib import Path

# ============================ CONFIG (tweakable) ===============================

# 🔐 API key from Streamlit Secrets (define it in Streamlit Cloud: Settings → Secrets)
# Secrets must contain: OPENAI_API_KEY="sk-...."
API_KEY = st.secrets["HARDCODED_API_KEY"]

EMBEDDING_MODEL = "text-embedding-3-small"

ENABLE_SEMANTIC = True
SEMANTIC_CANDIDATE_K = 2000
SEMANTIC_TOP_N = 1000

# "Priority" soft text columns
PRIORITY_COLS = ["name", "evidence", "keywords", "ville"]

# ============================ Streamlit Chrome =================================

st.set_page_config(
    page_title="TFTP — Companies Explorer",
    page_icon="Logo-time-planet-.png",
    layout="wide"
)
st.title("Team For The Planet — Investor Companies Explorer")

# --- Theme & Typography (kept from v4, with tweaks) ---------------------------
THEME = """
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Manrope:wght@400;600;700;800&display=swap" rel="stylesheet">

<style>
:root{
  --bg:#062b2b;
  --bg2:#041f1f;
  --card1:#0a3332;
  --card2:#092b2a;
  --ink:#EFFFFA;
  --muted:#CFE6E3;
  --line:#1b4948;
  --mint:#8FF3E3;
  --mint-strong:#66E5D1;
  --radius:10px;
  --radius-sm:8px;
  --shadow:0 18px 46px rgba(0,0,0,.35), 0 6px 16px rgba(0,0,0,.35);
}

html, body, .stApp {
  font-family: Manrope, Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
  background:
    radial-gradient(60vw 40vw at 10% -10%, rgba(143,243,227,.10), transparent 60%),
    radial-gradient(50vw 35vw at 90% 0%, rgba(143,243,227,.06), transparent 60%),
    linear-gradient(180deg, var(--bg), var(--bg2)) !important;
  color: var(--ink);
}
.block-container{padding-top: 1.2rem; max-width: 96vw;}
h1, h2, h3, .stMarkdown h1 { color:#E9FFFB !important; letter-spacing:.2px; text-shadow:0 1px 0 rgba(0,0,0,.25); }
section.main > div:has(> .stMarkdown + div) {
  background: linear-gradient(180deg, var(--card1), var(--card2));
  border: 1px solid var(--line);
  border-radius: var(--radius);
  box-shadow: var(--shadow);
  padding: 18px 18px 10px 18px;
}
label, .stCaption, .stRadio > label, .stCheckbox > label, .stSelectbox > label,
.stMultiSelect > label, .stTextInput > label, .stNumberInput > label,
.stSlider > label, .stToggle > label, .stColumns label, .stMarkdown label {
  color: #ffffff !important; opacity: 1 !important; text-shadow: none !important;
}
.stSlider span, .stToggle span, .stTextInput label span, .st-emotion-cache * label span { color:#ffffff !important; }
.stTextInput > div > div > input {
  background: #f2f4f7 !important; border: 1px solid var(--line) !important; color: #121212 !important;
  caret-color: #121212 !important; border-radius: var(--radius-sm) !important; font-weight: 600 !important;
}
.stTextInput > div > div > input::placeholder{ color: #4b4b4b !important; opacity: 1 !important; font-weight: 500 !important; }
.stTextInput label, .stTextInput label span, .stTextInput > label > div { color: #ffffff !important; font-weight: 700 !important; font-size: 1rem !important; opacity: 1 !important; }
.stTextInput > div > div > input:focus {
  outline: none !important; border-color: var(--mint) !important; box-shadow: 0 0 0 3px rgba(143,243,227,.28) !important;
}
[data-testid="stTable"], .stDataFrame { border-radius: var(--radius); overflow: visible !important; box-shadow: var(--shadow); }
.stDataFrame [data-testid="stHorizontalBlock"]{ overflow-x: visible !important; }
.stDataFrame table { table-layout: auto !important; width: 100% !important; }
.stDataFrame td, .stDataFrame th {
  border-color: rgba(255,255,255,.06) !important; color: var(--ink) !important; padding: 6px 8px !important;
  font-size: 13px !important; line-height: 1.2 !important; white-space: normal !important; word-break: break-word !important;
}
.stDataFrame [class*="row_heading"], .stDataFrame [class*="blank"] { background: #0d3a39 !important; color: var(--muted) !important; }
.stDataFrame [class*="col_heading"] { background: #0d3a39 !important; color: var(--muted) !important; font-weight: 800 !important; border-bottom: 1px solid var(--line) !important; }
.stDataFrame tbody tr:nth-child(odd) td { background: rgba(255,255,255,.02) !important; }
.stDataFrame tbody tr:nth-child(even) td { background: rgba(255,255,255,.04) !important; }
.muted{ color: var(--muted); }
:root { font-size: 15.5px; }
</style>
"""
HIDE_HEADER = """
<style>
header {visibility: hidden;}
footer {visibility: hidden;}
#MainMenu {visibility: hidden;}
</style>
"""
st.markdown(HIDE_HEADER, unsafe_allow_html=True)
st.markdown(THEME, unsafe_allow_html=True)

# ============================ Data Loading ====================================

@st.cache_data
def load_data() -> pd.DataFrame:
    base = Path(__file__).resolve().parent  # folder where this .py lives (your 'search/' folder)
    candidates = [
        base / "Companies.xlsx",
        base / "Companies.csv",
    ]
    last_exc = None
    for p in candidates:
        try:
            if p.exists() and p.suffix.lower() == ".csv":
                return pd.read_csv(p)
            if p.exists() and p.suffix.lower() in (".xlsx", ".xls"):
                return pd.read_excel(p)
        except Exception as e:
            last_exc = e
            continue
    st.error("Couldn't load Companies.xlsx / Companies.csv")
    if last_exc is not None:
        st.exception(last_exc)
    return pd.DataFrame()

df_raw = load_data()

# ============================ Canonical Schema =================================

ALIASES = {
    "nom": "name",
    "compagnie": "name",
    "entreprise": "name",
    "mots cles": "keywords",
    "mots-clés": "keywords",
    "keywords": "keywords",
    "city": "ville",
    "town": "ville",
    "localite": "ville",
    "localité": "ville",
    "preuve": "evidence",
    "justificatif": "evidence",
}

def norm(s: Any) -> str:
    if s is None: return ""
    s = str(s).lower()
    s = unicodedata.normalize("NFD", s)
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn")
    s = "".join(ch for ch in s if ch.isalnum() or ch in " -_/&.")
    return " ".join(s.split())

def canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty: return df
    rename_map = {}
    for c in df.columns:
        nc = norm(c)
        new = ALIASES.get(nc, c)
        if new in df.columns and new != c:
            new = c
        rename_map[c] = new
    return df.rename(columns=rename_map)

df = canonicalize_columns(df_raw)
st.write(f"**Rows loaded:** {len(df):,}")

TEXT_COLS: set = set(
    c for c in df.columns
    if df[c].dtype == object or pd.api.types.is_string_dtype(df[c])
)
NUM_COLS: set = set(
    c for c in df.columns
    if pd.api.types.is_integer_dtype(df[c]) or pd.api.types.is_float_dtype(df[c])
)

def compute_soft_text_cols(df: pd.DataFrame) -> List[str]:
    priority = [c for c in PRIORITY_COLS if c in df.columns]
    others = [c for c in TEXT_COLS if c not in priority]
    return priority + others

SOFT_TEXT_COLS: List[str] = compute_soft_text_cols(df)

# ============================ Semantic Search ==================================

@st.cache_data(show_spinner=False)
def embed_texts_cached(api_key: str, model: str, texts: List[str]) -> np.ndarray:
    client = OpenAIClient(api_key=api_key)
    resp = client.embeddings.create(model=model, input=texts)
    vecs = [d.embedding for d in resp.data]
    arr = np.array(vecs, dtype=np.float32)
    norms = np.linalg.norm(arr, axis=1, keepdims=True) + 1e-10
    return arr / norms

def _build_semantic_text_for_row(row: pd.Series, cols: List[str], weights: Dict[str, float]) -> str:
    base = {"name":3, "evidence":2, "keywords":2, "ville":2}
    parts: List[str] = []
    for c in cols:
        val = "" if c not in row or pd.isna(row[c]) else str(row.get(c, ""))
        if not val:
            continue
        w = float(weights.get(c, 1.0))
        rep = max(1, int(round(base.get(c,1) * w)))
        parts.extend([val] * rep)
    return " | ".join(parts)

def semantic_filter(
    df: pd.DataFrame,
    cols: List[str],
    terms: List[str],
    api_key: str,
    weights: Dict[str, float],
    candidate_k: int = SEMANTIC_CANDIDATE_K,
    top_n: int = SEMANTIC_TOP_N
) -> pd.DataFrame:
    if df.empty or not terms:
        df = df.copy()
        df["semantic_score"] = np.nan
        return df
    cand = df.head(candidate_k).copy()
    texts = []
    for _, row in cand.iterrows():
        texts.append(_build_semantic_text_for_row(row, cols, weights))
    q_embs = embed_texts_cached(api_key, EMBEDDING_MODEL, terms)
    q_vec = q_embs.mean(axis=0, keepdims=True)
    q_vec = q_vec / (np.linalg.norm(q_vec, axis=1, keepdims=True) + 1e-10)
    row_vecs = embed_texts_cached(api_key, EMBEDDING_MODEL, texts)
    sims = (row_vecs @ q_vec.T).ravel()
    disp = (sims + 1.0) / 2.0  # map [-1,1] → [0,1]
    cand = cand.assign(semantic_score=disp)
    cand = cand.sort_values("semantic_score", ascending=False).head(top_n)
    return cand

# ============================ Pipeline Runner (simplifié) ======================

def run_pipeline(user_query: str, df: pd.DataFrame, api_key: str, weights: Dict[str, float]) -> pd.DataFrame:
    soft_cols = compute_soft_text_cols(df)
    results = semantic_filter(
        df, soft_cols, [user_query], api_key,
        weights=weights,
        candidate_k=SEMANTIC_CANDIDATE_K, top_n=SEMANTIC_TOP_N
    )
    return results

# ============================ Main UI =========================================

if df.empty:
    st.stop()

st.subheader("Search")

query = st.text_input("Type a natural-language query", "")

with st.expander("Pondération des critères (optionnel)"):
    col1, col2 = st.columns(2)
    with col1:
        w_ville = st.slider("Importance de la **localisation (ville)**", 0.2, 3.0, 1.8, 0.1)
        w_name = st.slider("Importance du **nom**", 0.2, 3.0, 1.0, 0.1)
    with col2:
        w_keywords = st.slider("Importance des **mots-clés**", 0.2, 3.0, 1.0, 0.1)
        w_evidence = st.slider("Importance des **preuves/evidence**", 0.2, 3.0, 1.0, 0.1)

weights = {"ville": w_ville, "name": w_name, "keywords": w_keywords, "evidence": w_evidence}

# Use the single source of truth for key:
api_key = API_KEY

if query:
    if not api_key:
        st.error("Missing OpenAI API key.")
        st.stop()

    results = run_pipeline(query, df, api_key, weights)

    if "semantic_score" not in results.columns:
        results["semantic_score"] = 1.0

    cols = list(results.columns)
    if "semantic_score" in cols:
        cols = ["semantic_score"] + [c for c in cols if c != "semantic_score"]
        results = results[cols]

    use_filter = st.toggle("Activer le filtre de score (0–1)", value=True)
    threshold = st.slider("Seuil de score sémantique", 0.0, 1.0, 0.7, 0.01)

    if use_filter:
        results = results[results["semantic_score"] >= float(threshold)]

    results = results.sort_values("semantic_score", ascending=False)

    st.markdown(f"**{len(results):,} result(s){' (filtrés)' if use_filter else ''}**")

    col_config = {
        "semantic_score": st.column_config.ProgressColumn(
            "Semantic score",
            help="Pertinence sémantique de 0 à 1",
            min_value=0.0,
            max_value=1.0,
            format="%.2f",
            width="small",
        )
    }
    for c in results.columns:
        if c != "semantic_score":
            col_config[c] = st.column_config.Column(c, width="small")

    st.dataframe(
        results,
        use_container_width=True,
        column_config=col_config,
        height=600,
    )
