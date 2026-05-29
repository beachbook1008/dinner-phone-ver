import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
import base64
from dotenv import load_dotenv

# --- 1. 初期設定 ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")

if api_key:
    # 404エラー対策：transport="rest" を指定して確実に繋ぐ
    genai.configure(api_key=api_key, transport="rest")
    # 429（回数制限）対策：一番安定して回数も使える1.5-flashを正しい名前で指定
    model = genai.GenerativeModel('gemini-3-flash-preview')
else:
    st.error("APIキーがないよ！.envファイルを確認してね。")
    st.stop()

st.set_page_config(page_title="Dinner Logic DX", layout="wide")

# --- 2. データの読み込み ---
@st.cache_data
def load_data():
    try:
        # ファイル名は dinner_list.csv
        df_raw = pd.read_csv("dinner_list.csv", header=None)
        df = df_raw.iloc[:, :5].copy()
        df.columns = ['id', 'store', 'name', 'genre', 'cal']
        df['cal'] = pd.to_numeric(df['cal'], errors='coerce').fillna(0)
        df['display'] = df['store'] + " - " + df['name'] + " (" + df['cal'].astype(int).astype(str) + "kcal)"
        return df
    except Exception as e:
        st.error(f"CSV読み込みエラー: {e}")
        return pd.DataFrame()

df = load_data()

# --- 3. サイドバー：彩音さんのこだわり設定 ---
# --- 5. メイン画面 ---
df_menu = load_menu()

st.title(f"🥘 美食家サンダーさん vs {user_id}")

with st.sidebar:
    # --- ここを追加！雷さんの画像を表示 ---
    if os.path.exists("mii_thunder.jpg"):
        st.image("mii_thunder.jpg", width=150, caption="美食家サンダー⚡️")
    # ------------------------------------
    
    st.header("👤 ステータス")
    st.success(f"User: {user_id}\nTarget: {user_row['target_weight']}kg")
    # ...以下、体重入力などが続く
    
    gender = st.radio("性別", ["女子", "男子"])
    weight = st.number_input("今の体重 (kg)", 30.0, 150.0, 55.0)
    target_weight = st.number_input("目標体重 (kg)", 30.0, 150.0, 52.0)
    height = st.number_input("身長 (cm)", 100.0, 220.0, 160.0)
    age = st.number_input("年齢", 15, 100, 20)
    
    st.markdown("---")
    st.header("🏃 運動・活動レベル")
    # 「座った状態」をLv.1にした具体的な選択肢
    levels = {
        "1.2：ほぼ座った状態（講義やPC作業がメイン）": 1.2, 
        "1.375：座り仕事中心だが、通学・買い物で少し歩く": 1.375, 
        "1.55：移動や立ち仕事が多く、適度に運動もする": 1.55, 
        "1.725：活発に運動している、または肉体労働": 1.725
    }
    selected_level = st.selectbox("今日の生活スタイル", list(levels.keys()))
    activity_value = levels[selected_level]

    st.markdown("---")
    st.header("⚡️ カスタム設定")
    char_name = st.text_input("キャラ名", value="サンダーさん")
    char_personality = st.text_area("性格設定", value="女子大生の親友。口癖は『あったまいいね！』。ライエット推し。")

# --- 4. 計算ロジック（基礎代謝 & TDEE） ---
if gender == "男子":
    bmr = 88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age)
else:
    bmr = 447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)

tdee = bmr * activity_value
# 1kg減らすのに7200kcal必要として30日で割る計算式
target_cal = tdee - ((weight - target_weight) * 7200 / 30)

st.title(f"🥗 {char_name}のライエット相談室")

col1, col2 = st.columns(2)
with col1:
    b_items = st.multiselect("🍙 朝に食べたもの", df['display'].tolist() if not df.empty else [])
with col2:
    l_items = st.multiselect("🥪 昼に食べたもの", df['display'].tolist() if not df.empty else [])

b_cal = df[df['display'].isin(b_items)]['cal'].sum() if not df.empty else 0
l_cal = df[df['display'].isin(l_items)]['cal'].sum() if not df.empty else 0
dinner_cal = target_cal - (b_cal + l_cal)

st.info(f"あなたの1日の消費目安: **{int(tdee)} kcal**")
st.success(f"目標達成まで、今日の晩御飯はあと **{int(dinner_cal)} kcal** 以内！")

# --- 5. 商品棚（上限ギリギリ攻め） ---
st.subheader("🍱 今夜のイチ推しメニュー")
if not df.empty:
    recs = df[df['cal'] <= dinner_cal].sort_values(by='cal', ascending=False).head(10)
    if not recs.empty:
        samples = recs.sample(min(len(recs), 5))
        cols = st.columns(5)
        for i, (_, row) in enumerate(samples.iterrows()):
            cols[i].metric(label=row['store'], value=f"{int(row['cal'])}kcal", delta=row['name'], delta_color="inverse")
    else:
        st.warning("上限オーバー！明日の朝から調整しよう。")

# --- 6. AI相談室 ---
st.divider()
if user_msg := st.chat_input(f"{char_name}に相談"):
    with st.chat_message("assistant", avatar="⚡️"):
        prompt = f"あなたは{char_name}です。性格:{char_personality}。今日の残りカロリーは{int(dinner_cal)}kcalです。この状況を踏まえて、親身に、かつ『あったまいいね！』を使いながら回答して。質問:{user_msg}"
        try:
            response = model.generate_content(prompt)
            st.write(response.text)
        except Exception as e:
            st.error(f"エラーが発生したよ: {e}")