import time
import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
from datetime import datetime
from dotenv import load_dotenv
import threading

# --- アバターの存在チェック ---
takagi_avatar = "takagi.jpg" if os.path.exists("takagi.jpg") else "👨‍🏫"
rai_avatar = "mii_thunder.jpg" if os.path.exists("mii_thunder.jpg") else "👨‍🏫"
all_friends_img = "allfriends.jpg" if os.path.exists("allfriends.jpg") else None
takagirai_img = "takagirai.jpg" if os.path.exists("takagirai.jpg") else None

# --- 1. 初期設定 ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    # 🌟 安定版モデルをチャット専用として読み込み
    model_chat = genai.GenerativeModel('gemini-1.5-flash')
else:
    st.error("APIキーが設定されていません。")
    st.stop()

import style
import ai_config

st.set_page_config(page_title="Dinner Logic DX", layout="wide")
style.apply_custom_css()

# --- 2. データ管理関数 ---
USER_FILE = "user_settings.csv"
MENU_FILE = "dinner_list.csv"

def get_all_users():
    cols = ["user_id", "password", "target_weight", "last_update", "consecutive_days"]
    if os.path.exists(USER_FILE):
        try:
            df = pd.read_csv(USER_FILE)
            for c in cols:
                if c not in df.columns: df[c] = None
            return df
        except:
            return pd.DataFrame(columns=cols)
    return pd.DataFrame(columns=cols)

def save_user(user_id, password, target_weight=None, consecutive_days=None):
    df = get_all_users()
    u_str = str(user_id)
    if u_str in df['user_id'].astype(str).values:
        idx = df[df['user_id'].astype(str) == u_str].index[0]
        if password: df.at[idx, 'password'] = password
        if target_weight is not None:
            df.at[idx, 'target_weight'] = target_weight
            df.at[idx, 'last_update'] = datetime.now().strftime("%Y-%m-%d")
        if consecutive_days is not None:
            df.at[idx, 'consecutive_days'] = consecutive_days
    else:
        new_row = pd.DataFrame({"user_id": [user_id], "password": [password], "target_weight": [target_weight], "last_update": [datetime.now().strftime("%Y-%m-%d")], "consecutive_days": [consecutive_days or 1]})
        df = pd.concat([df, new_row], ignore_index=True)
    df.to_csv(USER_FILE, index=False)

def reset_basic_info_on_month_start(user_id):
    if datetime.now().day != 1: return
    df = get_all_users()
    u_str = str(user_id)
    if u_str not in df['user_id'].astype(str).values: return
    idx = df[df['user_id'].astype(str) == u_str].index[0]
    df.at[idx, 'target_weight'] = pd.NA
    df.at[idx, 'last_update'] = datetime.now().strftime("%Y-%m-%d")
    df.to_csv(USER_FILE, index=False)

def calculate_consecutive_days(user_id):
    df = get_all_users()
    u_str = str(user_id)
    if u_str not in df['user_id'].astype(str).values: return 1
    idx = df[df['user_id'].astype(str) == u_str].index[0]
    last_update_str = df.at[idx, 'last_update']
    current_consecutive = df.at[idx, 'consecutive_days']
    if pd.isna(last_update_str) or pd.isna(current_consecutive): return 1
    try:
        last_update = datetime.strptime(last_update_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        if (today - last_update).days == 1: return int(current_consecutive) + 1
        elif (today - last_update).days == 0: return int(current_consecutive)
        else: return 1
    except:
        return 1

@st.cache_data
def load_menu():
    try:
        df_m = pd.read_csv(MENU_FILE, header=None).iloc[:, :5]
        df_m.columns = ['id', 'store', 'name', 'genre', 'cal']
        df_m['cal'] = pd.to_numeric(df_m['cal'], errors='coerce').fillna(0)
        df_m['display'] = df_m['store'] + " - " + df_m['name'] + " (" + df_m['cal'].astype(int).astype(str) + "kcal)"
        return df_m
    except:
        return pd.DataFrame()

@st.cache_resource
def download_font_cached():
    f_url = "https://github.com/googlefonts/morisawa-biz-ud-gothic/raw/main/fonts/ttf/BIZUDGothic-Regular.ttf"
    f_path = "BIZUDGothic-Regular.ttf"
    if not os.path.exists(f_path):
        try:
            import urllib.request
            urllib.request.urlretrieve(f_url, f_path)
        except:
            pass
    return f_path

# --- 3. 画面制御ロジック ---
if 'is_logged_in' not in st.session_state: st.session_state['is_logged_in'] = False
if 'show_register' not in st.session_state: st.session_state['show_register'] = False

cookie_user_id = st.context.cookies.get("saved_user_id")

if not st.session_state['is_logged_in'] and cookie_user_id:
    df = get_all_users()
    match = df[df['user_id'].astype(str) == str(cookie_user_id)]
    if not match.empty:
        user_info = match.iloc[0]
        st.session_state['height'] = float(user_info.get('height', 160.0))
        st.session_state['weight'] = float(user_info.get('weight', 55.0))
        st.session_state['age'] = int(user_info.get('age', 20))
        st.session_state['gender'] = user_info.get('gender', "女子")
        st.session_state['is_logged_in'] = True
        st.session_state['current_user'] = cookie_user_id
        st.rerun()

# A. ログイン画面
if not st.session_state['is_logged_in']:
    st.markdown("<div style='text-align: center;'><h1 style='color: #2196F3;'>🔐 今日からダイエット</h1></div>", unsafe_allow_html=True)
    with st.container(border=True):
        if all_friends_img:
            st.image(all_friends_img, use_container_width=True, caption="デジタル変革実験 プロジェクト")
        st.markdown("<p style='text-align: center; color: #666; font-size: 14px;'>ログインして始めましょう！</p>", unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            l_id = st.text_input("ユーザーID", key="login_id")
            l_pw = st.text_input("パスワード", type="password", key="login_pw")
            if st.button("🔓 ログイン", use_container_width=True):
                df = get_all_users()
                match = df[(df['user_id'].astype(str) == l_id) & (df['password'].astype(str) == l_pw)]
                if not match.empty:
                    user_info = match.iloc[0]
                    st.session_state['is_logged_in'] = True
                    st.session_state['current_user'] = l_id
                    st.rerun()
                else: 
                    st.error("IDかパスワードが違います")
    st.stop()

# B. ログイン後のデータ取得
user_id = st.session_state['current_user']
df_users = get_all_users()
match_users = df_users[df_users['user_id'].astype(str) == user_id]
user_row = match_users.iloc[0] if not match_users.empty else pd.Series({"user_id": user_id, "password": "", "target_weight": 50.0, "consecutive_days": 1})
df_menu = load_menu()

# --- サイドバーの設定 ---
with st.sidebar:
    if takagirai_img:
        st.image(takagirai_img, use_container_width=True, caption="開発チーム")
        
    st.header(" ステータス")
    weight = st.number_input("今の体重 (kg)", 30.0, 150.0, st.session_state.get('weight', 55.0))
    height = st.number_input("身長 (cm)", 100.0, 220.0, st.session_state.get('height', 160.0))
    age = st.number_input("年齢", 15, 100, st.session_state.get('age', 20))
    gender = st.radio("性別", ["女子", "男子"], index=0)
    
    st.markdown("---")
    levels = {"1.2：座りっぱなし": 1.2, "1.375：軽い運動": 1.375, "1.55：適度な運動": 1.55}
    activity = levels[st.selectbox("生活スタイル", list(levels.keys()))]
    
    st.markdown("---")
    ai_persona = st.selectbox("AIのキャラクター", ["雷さん ", "高木先生モード", "フォーマル "])
    
    if st.button("ログアウト"):
        st.session_state.clear()
        st.rerun()

st.title(f"今日からダイエット")
st.markdown("---")

# --- 4. 計算ロジックとメニュー選択（3列） ---
bmr = (447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)) if gender == "女子" else (88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age))
target_cal = (bmr * activity) - ((weight - float(user_row.get('target_weight', weight))) * 7200 / 30)
if target_cal < 1200: target_cal = 1800.0  # 🌟 安全弁

st.subheader("🍽️ 本日の食事メニューを選択")
col1, col2, col3 = st.columns(3)
with col1:
    b_items = st.multiselect("🌅 朝食", df_menu['display'].tolist() if not df_menu.empty else [])
with col2:
    l_items = st.multiselect("☀️ 昼食", df_menu['display'].tolist() if not df_menu.empty else [])
with col3:
    d_items = st.multiselect("🌙 夕食", df_menu['display'].tolist() if not df_menu.empty else [])

breakfast_cal = df_menu[df_menu['display'].isin(b_items)]['cal'].sum() if not df_menu.empty else 0
lunch_cal = df_menu[df_menu['display'].isin(l_items)]['cal'].sum() if not df_menu.empty else 0
dinner_cal_selected = df_menu[df_menu['display'].isin(d_items)]['cal'].sum() if not df_menu.empty else 0

total_cal = breakfast_cal + lunch_cal + dinner_cal_selected
dinner_left_cal = target_cal - total_cal

st.metric("今日の残り枠", f"{int(dinner_left_cal)} kcal")

# --- 5. チャット入力とAI提案ロジック ---
st.divider()
suggest_button = st.button("✨ AIに残りカロリーに合った夜ご飯を提案してもらう！")
chat_input_val = st.chat_input("AIキャラクターに相談する")

user_msg = None
if chat_input_val:
    user_msg = chat_input_val
if suggest_button:
    menu_list_str = "\n".join(df_menu['display'].tolist())
    user_msg = f"現在の私の残りカロリー枠は {int(dinner_left_cal)} kcalです。以下の【メニューリスト】の中から、カロリー枠にぴったり収まる一番おすすめの食事を1つ提案してください！\n\n【メニューリスト】\n{menu_list_str}"

ai_printed_text = ""
if user_msg:
    sys_prompt = ai_config.get_system_prompt(ai_persona, user_id)
    prompt = f"{sys_prompt}\n\n[Remaining Calorie]: {int(dinner_left_cal)} kcal\n\nUser Question: {user_msg}"
    
    with st.spinner("AIが考え中..."):
        try:
            response = model_chat.generate_content(prompt)
            ai_printed_text = response.text
        except Exception as e:
            ai_printed_text = "【通信エラー】現在AIサーバーが混雑しています。少し待ってから再度お試しください。"

# --- 6. AIキャラクターのチャット表示 ---
if ai_persona == "高木先生モード":
    current_avatar, bubble_class = takagi_avatar, "chat-bubble takagi-bubble"
elif ai_persona == "雷さん ":
    current_avatar, bubble_class = rai_avatar, "chat-bubble rai-bubble"
else:
    current_avatar, bubble_class = "🤖", "chat-bubble"

with st.chat_message("assistant", avatar=current_avatar):
    if ai_printed_text:
        st.markdown(f'<div class="{bubble_class}">{ai_printed_text}</div>', unsafe_allow_html=True)
    else:
        if ai_persona == "高木先生モード":
            msg = f"Hello！今日の残り枠は {int(dinner_left_cal)}kcal です。メニューから食事を選んで、投資効率（ROI）を高めましょう！"
        else:
            msg = f"あったまいいね！今日はあと {int(dinner_left_cal)}kcal 食べられるよ！上のメニュー表から選んでみて！"
        st.markdown(f'<div class="{bubble_class}">{msg}</div>', unsafe_allow_html=True)

# --- 7. 栄養摂取状況グラフ ---
st.markdown("---")
st.subheader("📊 本日の栄養摂取状況とバランス")
chart_col1, chart_col2 = st.columns([1, 1])

with chart_col1:
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            st.metric(label="🌅 朝食", value=f"{int(breakfast_cal)} kcal")
            st.metric(label="🌙 夕食", value=f"{int(dinner_cal_selected)} kcal")
        with c2:
            st.metric(label="☀️ 昼食", value=f"{int(lunch_cal)} kcal")
            st.metric(label="🔥 合計摂取", value=f"{int(total_cal)} kcal")

with chart_col2:
    left_cal = max(0, int(dinner_left_cal))
    raw_labels = ['朝食', '昼食', '夕食', '残り枠']
    raw_sizes = [breakfast_cal, lunch_cal, dinner_cal_selected, left_cal]
    raw_colors = ['#ffa500', '#4CAF50', '#2196F3', '#e0e0e0']
    
    labels, sizes, colors = [], [], []
    for s, l, c in zip(raw_sizes, raw_labels, raw_colors):
        if s > 0:
            labels, sizes, colors = labels + [l], sizes + [s], colors + [c]
            
    if not sizes: sizes, labels, colors = [100], ['1日の目標枠'], ['#e0e0e0']
    
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    font_path = download_font_cached()
    fp = fm.FontProperties(fname=font_path) if os.path.exists(font_path) else fm.FontProperties(family='sans-serif')
    
    fig, ax = plt.subplots(figsize=(4, 4))
    ax.pie(sizes, labels=labels, autopct=lambda p: '{:.1f}%'.format(p) if p > 0 else '', startangle=90, colors=colors, textprops={'fontproperties': fp})
    ax.axis('equal')  
    st.pyplot(fig)

with st.sidebar:
    st.video("https://youtu.be/l7Tr8xb_tFk")