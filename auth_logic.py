import time
import hashlib
import streamlit as st
import pandas as pd
import os
from datetime import datetime
from dotenv import load_dotenv
from openai import OpenAI  # 💡 Groq通信用のライブラリ

# --- アバター・画像の存在チェック ---
takagi_avatar = "takagi.jpg" if os.path.exists("takagi.jpg") else "👨‍🏫"
rai_avatar = "mii_thunder.jpg" if os.path.exists("mii_thunder.jpg") else "⚡️"
all_friends_img = "allfriends.jpg" if os.path.exists("allfriends.jpg") else None
takagi_rai_img = "takagirai.jpg" if os.path.exists("takagirai.jpg") else None

# --- 1. 初期設定 ---
load_dotenv()

# 💡 SecretsからGroqのAPIキーを最優先に読み込む
groq_api_key = st.secrets.get("GROQ_API_KEY", os.getenv("GROQ_API_KEY"))

if groq_api_key:
    # OpenAIの規格を利用してGroqの高速サーバーに接続
    client = OpenAI(
        api_key=groq_api_key,
        base_url="https://api.groq.com/openai/v1"
    )
else:
    st.error("GroqのAPIキー（GROQ_API_KEY）がシークレットまたは環境変数に見つかりません！")
    st.stop()

import style
import ai_config

st.set_page_config(page_title="Dinner Logic DX", layout="wide")
style.apply_custom_css()

# --- 2. データ管理関数 ---
USER_FILE = "user_settings.csv"
MENU_FILE = "dinner_list.csv"

def hash_password(password):
    if not password:
        return ""
    return hashlib.sha256(str(password).encode('utf-8')).hexdigest()

def get_all_users():
    cols = ["user_id", "password", "target_weight", "last_update", "consecutive_days"]
    if "user_db" in st.secrets and st.secrets["user_db"]:
        try:
            df = pd.read_csv(st.secrets["user_db"])
            for c in cols:
                if c not in df.columns: df[c] = None
            return df
        except:
            return pd.DataFrame(columns=cols)
            
    if os.path.exists(USER_FILE):
        try:
            df = pd.read_csv(USER_FILE)
            for c in cols:
                if c not in df.columns: df[c] = None
            return df
        except:
            return pd.DataFrame(columns=cols)
    return pd.DataFrame(columns=cols)

def save_user(user_id, password, target_weight=None, consecutive_days=None, is_password_hashed=False):
    df = get_all_users()
    u_str = str(user_id)
    stored_password = password
    
    if password and not is_password_hashed:
        stored_password = hash_password(password)
        
    if u_str in df['user_id'].astype(str).values:
        idx = df[df['user_id'].astype(str) == u_str].index[0]
        if password and not is_password_hashed:
            df.at[idx, 'password'] = stored_password
        if target_weight is not None:
            df.at[idx, 'target_weight'] = target_weight
            df.at[idx, 'last_update'] = datetime.now().strftime("%Y-%m-%d")
        if consecutive_days is not None:
            df.at[idx, 'consecutive_days'] = consecutive_days
    else:
        new_row = pd.DataFrame({
            "user_id": [user_id], 
            "password": [stored_password], 
            "target_weight": [target_weight], 
            "last_update": [datetime.now().strftime("%Y-%m-%d")], 
            "consecutive_days": [consecutive_days or 1]
        })
        df = pd.concat([df, new_row], ignore_index=True)
        
    df.to_csv(USER_FILE, index=False)
    
    if "db_backup_url" not in st.secrets:
        pass 
    elif st.secrets["db_backup_url"]:
        try:
            import requests
            import json
            clean_df = df.copy()
            clean_df = clean_df.replace({pd.NA: "", None: ""}).fillna("")
            
            json_data = json.dumps(clean_df.to_dict(orient="records"))
            requests.post(st.secrets["db_backup_url"], data=json_data, headers={"Content-Type": "application/json"}, timeout=10)
        except Exception:
            pass

def reset_basic_info_on_month_start(user_id):
    if datetime.now().day != 1:
        return
    df = get_all_users()
    u_str = str(user_id)
    if u_str not in df['user_id'].astype(str).values:
        return
    idx = df[df['user_id'].astype(str) == u_str].index[0]
    df.at[idx, 'target_weight'] = pd.NA
    df.at[idx, 'last_update'] = datetime.now().strftime("%Y-%m-%d")
    df.to_csv(USER_FILE, index=False)

def calculate_consecutive_days(user_id):
    df = get_all_users()
    u_str = str(user_id)
    if u_str not in df['user_id'].astype(str).values:
        return 1
    idx = df[df['user_id'].astype(str) == u_str].index[0]
    last_update_str = df.at[idx, 'last_update']
    current_consecutive = df.at[idx, 'consecutive_days']
    
    if pd.isna(last_update_str) or str(last_update_str).strip() == "" or pd.isna(current_consecutive):
        return 1
    try:
        last_update = datetime.strptime(last_update_str, "%Y-%m-%d").date()
        today = datetime.now().date()
        if (today - last_update).days == 1:
            return int(current_consecutive) + 1
        elif (today - last_update).days == 0:
            return int(current_consecutive)
        else:
            return 1
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

# --- 3. 画面制御ロジック ---
if 'is_logged_in' not in st.session_state:
    st.session_state['is_logged_in'] = False
if 'show_register' not in st.session_state:
    st.session_state['show_register'] = False
if 'selected_dinner' not in st.session_state:
    st.session_state['selected_dinner'] = None
if 'selected_dinner_cal' not in st.session_state:
    st.session_state['selected_dinner_cal'] = 0

cookie_user_id = st.context.cookies.get("saved_user_id")

if not st.session_state['is_logged_in'] and cookie_user_id:
        df = get_all_users()
        match = df[df['user_id'].astype(str) == str(cookie_user_id)]
        if not match.empty:
            user_info = match.iloc[0]
            reset_basic_info_on_month_start(cookie_user_id)
            consecutive_days = calculate_consecutive_days(cookie_user_id)
            save_user(cookie_user_id, user_info['password'], user_info['target_weight'], consecutive_days, is_password_hashed=True)
            st.session_state['height'] = float(user_info.get('height', 160.0))
            st.session_state['weight'] = float(user_info.get('weight', 55.0))
            st.session_state['age'] = int(user_info.get('age', 20))
            st.session_state['gender'] = user_info.get('gender', "女子")
            st.session_state['is_logged_in'] = True
            st.session_state['current_user'] = cookie_user_id
            st.rerun()

# A. ログイン・登録画面
if not st.session_state['is_logged_in']:
    if st.session_state['show_register']:
        st.markdown("<div style='text-align: center;'><h1 style='color: #ff6b6b;'>📝 新規会員登録</h1></div>", unsafe_allow_html=True)
        with st.container(border=True):
            if all_friends_img:
                st.image(all_friends_img, use_container_width=True, caption="E班メンバー一同でサポートします！")
            st.markdown("<p style='text-align: center; color: #666; font-size: 14px;'>新しくアカウントを作成して一緒にダイエットを始めましょう！</p>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                n_id = st.text_input("希望ID", key="reg_id", placeholder="ユーザーID")
                n_pw = st.text_input("パスワード", type="password", key="reg_pw", placeholder="パスワード")
                st.markdown("")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button(" 登録", use_container_width=True):
                        if n_id and n_pw:
                            save_user(n_id, n_pw)
                            st.success("登録完了！ さあ、始めましょう！")
                            st.session_state['show_register'] = False
                            st.rerun()
                        else:
                            st.error("IDとパスワードを入力してね！")
                with col_b:
                    if st.button(" 戻る", use_container_width=True):
                        st.session_state['show_register'] = False
                        st.rerun()
    else:
        st.markdown("<div style='text-align: center;'><h1 style='color: #2196F3;'>🔐 今日からダイエット</h1></div>", unsafe_allow_html=True)
        with st.container(border=True):
            if all_friends_img:
                st.image(all_friends_img, use_container_width=True, caption="デジタル変革実験 E班プロジェクト")
                
            st.markdown("<p style='text-align: center; color: #666; font-size: 14px;'>先生・メンバーとの美食ダイエットへようこそ！</p>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                l_id = st.text_input("ユーザーID", key="login_id", placeholder="IDを入力")
                l_pw = st.text_input("パスワード", type="password", key="login_pw", placeholder="パスワードを入力")
                st.markdown("")
                if st.button("🔓 ログイン", use_container_width=True):
                    df = get_all_users()
                    hashed_input_pw = hash_password(l_pw)
                    match = df[(df['user_id'].astype(str) == l_id) & (df['password'].astype(str) == hashed_input_pw)]
                    if not match.empty:
                        user_info = match.iloc[0]
                        reset_basic_info_on_month_start(l_id)
                        consecutive_days = calculate_consecutive_days(l_id)
                        save_user(
                            user_id=l_id, 
                            password=user_info['password'], 
                            target_weight=user_info['target_weight'], 
                            consecutive_days=consecutive_days, 
                            is_password_hashed=True
                        )
                        st.session_state['height'] = float(user_info.get('height', 160.0))
                        st.session_state['weight'] = float(user_info.get('weight', 55.0))
                        st.session_state['age'] = int(user_info.get('age', 20))
                        st.session_state['gender'] = user_info.get('gender', "女子")
                        st.session_state['is_logged_in'] = True
                        st.session_state['current_user'] = l_id
                        
                        st.components.v1.html(f"""
                            <script>
                                document.cookie = "saved_user_id={l_id}; max-age=2592000; path=/; Secure; SameSite=Lax";
                            </script>
                        """, height=0)
                           
                        st.success(f"ログイン成功！おかえりなさい、{l_id}さん ")
                        time.sleep(0.5)
                        st.rerun()
                    else: 
                        st.error("IDまたはパスワードが間違っています！")
                st.markdown("")
                if st.button("✨ 新規登録はこちら", use_container_width=True):
                    st.session_state['show_register'] = True
                    st.rerun()
    st.stop()

# B. ログイン後のデータ取得
user_id = st.session_state['current_user']
df_users = get_all_users()
match_users = df_users[df_users['user_id'].astype(str) == user_id]
user_row = match_users.iloc[0] if not match_users.empty else pd.Series({"user_id": user_id, "password": "", "target_weight": None, "consecutive_days": 1})
df_menu = load_menu()

# C. 目標設定画面
#if pd.isna(user_row['target_weight']) or datetime.now().day == 1:

today_str = datetime.now().strftime("%Y-%m-%d")
last_update_str = str(user_row.get('last_update', ''))

# 「目標が空っぽ」または「今日が1日、かつ、今日まだ更新していない（日をまたいで起動しっぱなしの場合など）」
if pd.isna(user_row['target_weight']) or (datetime.now().day == 1 and last_update_str != today_str):
    st.title(f"📅 目標設定 ({user_id})")
    t_w = st.number_input("今月の目標体重 (kg)", 30.0, 150.0, 52.0)
    if st.button("目標を保存"):
        # 💡 引数がズレないように名前付き（キーワード引数）で安全に保存します
        save_user(
            user_id=user_id, 
            password=user_row['password'], 
            target_weight=t_w, 
            is_password_hashed=True
        )
        st.rerun()
    st.stop()

# --- 4. メイン画面の準備 ---
st.title(f"今日からダイエット")

consecutive_days = int(user_row.get('consecutive_days', 1))
st.markdown("---")
with st.container(border=True):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"<div style='text-align: center;'><h2 style='color: #ff6b6b; margin-bottom: 5px;'>🔥 連続ログイン</h2><p style='font-size: 16px; color: #666; margin: 5px 0;'>あなたは今日で</p><p style='font-size: 48px; font-weight: bold; color: #ff6b6b; margin: 10px 0;'>{consecutive_days}</p><p style='font-size: 16px; color: #666; margin-top: 5px;'>日連続で頑張ってるよ！</p></div>", unsafe_allow_html=True)

st.markdown("---")

# --- サイドバーの設定 ---
with st.sidebar:
    if takagi_rai_img:
        st.image(takagi_rai_img, use_container_width=True, caption="開発チーム: 高木先生 & 雷さん")
    else:
        st.markdown("👥 **チーム高木＆雷**")
        
    st.header(" ステータス")
    st.success(f"User: {user_id}\nTarget: {user_row['target_weight']}kg")
    
    weight = st.number_input("今の体重 (kg)", 30.0, 150.0, st.session_state['weight'])
    height = st.number_input("身長 (cm)", 100.0, 220.0, st.session_state['height'])
    age = st.number_input("年齢", 15, 100, st.session_state['age'])
    gender = st.radio("性別", ["女子", "男子"], index=["女子", "男子"].index(st.session_state['gender']))
    
    st.markdown("---")
    levels = {"1.2：座りっぱなし": 1.2, "1.375：軽い運動": 1.375, "1.55：適度な運動": 1.55, "1.725：活発な運動": 1.725, "1.9：非常に活発": 1.9}
    activity = levels[st.selectbox("生活スタイル", list(levels.keys()))]
    
    st.markdown("---")
    st.header(" 発表用AI設定")
    ai_persona = st.selectbox(
        "AIのキャラクター",
        ["雷さん", "高木先生モード","安藤先生モード" ,"フォーマル"]
    )
    
    if st.button("ログアウト"):
        st.components.v1.html("""
            <script>
                document.cookie = "saved_user_id=; max-age=0; path=/; Secure; SameSite=Lax";
            </script>
        """, height=0)
        st.session_state.clear()
        st.rerun()

# --- 5. 計算ロジック ---
bmr = (447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)) if gender == "女子" else (88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age))
target_cal = (bmr * activity) - ((weight - float(user_row['target_weight'])) * 7200 / 30)

col1, col2 = st.columns(2)
with col1:
    b_items = st.multiselect("朝食", df_menu['display'].tolist() if not df_menu.empty else [])
with col2:
    l_items = st.multiselect("昼食", df_menu['display'].tolist() if not df_menu.empty else [])

if b_items or l_items:
    st.subheader("選択されたメニュー")
    col1, col2 = st.columns(2)
    if b_items:
        with col1:
            with st.container(border=True):
                st.markdown(f"<h3 style='text-align: center; color: #ffa500;'>🌅 朝食</h3>", unsafe_allow_html=True)
                for item in b_items:
                    st.markdown(f"<p style='text-align: center; color: #666; font-size: 14px; font-weight: bold;'>✓ {item}</p>", unsafe_allow_html=True)
    if l_items:
        with col2:
            with st.container(border=True):
                st.markdown(f"<h3 style='text-align: center; color: #4CAF50;'>☀️ 昼食</h3>", unsafe_allow_html=True)
                for item in l_items:
                    st.markdown(f"<p style='text-align: center; color: #666; font-size: 14px; font-weight: bold;'>✓ {item}</p>", unsafe_allow_html=True)

dinner_cal = target_cal - (df_menu[df_menu['display'].isin(b_items)]['cal'].sum() + df_menu[df_menu['display'].isin(l_items)]['cal'].sum())
st.metric("今日の残り枠", f"{int(dinner_cal)} kcal")
# --- 🚨 低体重・カロリー不足アラート機能 ---
if height > 0:
    bmi = weight / ((height / 100) ** 2)
    if bmi < 18.5:
        if "高木先生" in ai_persona:
            st.error(f"🚨 **高木先生からの緊急アラート:** BMIが {bmi:.1f} と非常に低く、過度な減量リスク（資産毀損）があります！直ちにウェイトコントロールのポートフォリオを見直し、健康への『先行投資』を増やしてください！")
        elif "安藤先生" in ai_persona:
            st.error(f"🚨 **安藤先生からの指摘:** BMIが {bmi:.1f} です。統計的にもこれは明らかに『低体重（外れ値）』の領域に入っていますよ。これ以上の食事制限はロジックが破綻しています。まずは適切な栄養摂取のコード（食事）を実行してください。インデントのズレくらい容認できません！")
        else:
            st.error(f"🚨 **雷さんからの怒りのアラート:** ちょっと彩音、BMIが {bmi:.1f} しかないよ！？これ以上痩せたらマジで怒るからね！ちゃんと食べて！")

# 2. 極端なカロリー不足のチェック
if dinner_cal < 300:
    if "安藤先生" in ai_persona:
        st.warning(f"⚠️ **安藤先生からの警告:** 残り許容カロリーが {int(dinner_cal)} kcal と少なすぎます。基礎代謝（BMR）の分散を考慮しない極端な制限は、体調不良という致命的なランタイムエラーを引き起こしますよ。")
    else:
        st.warning("⚠️ **健康管理警告:** 本日の残り許容カロリーが少なすぎます。基礎代謝を下回る極端な制限はリバウンドや体調不良の原因になります。")
st.markdown("---")
st.subheader("🌙 夜ご飯の提案と選択")

if not df_menu.empty:
    suitable_dinner = df_menu[df_menu['cal'] <= dinner_cal]
    if not suitable_dinner.empty:
        st.info(f"💡 今日の残り枠（{int(dinner_cal)} kcal）に収まるおすすめのメニューが {len(suitable_dinner)} 件見つかりました！")
        display_options = suitable_dinner['display'].tolist()
    else:
        st.warning("⚠️ 残り枠に収まるメニューがありません。低カロリーなメニューを検討するか、全メニューから選択してください。")
        display_options = df_menu['display'].tolist()
        
    selected_option = st.selectbox(
        "今夜のメニューを決定する:",
        ["未選択"] + display_options,
        index=0 if st.session_state['selected_dinner'] is None else (display_options.index(st.session_state['selected_dinner']) + 1 if st.session_state['selected_dinner'] in display_options else 0)
    )
    
    if selected_option != "未選択":
        matched_row = df_menu[df_menu['display'] == selected_option].iloc[0]
        st.session_state['selected_dinner'] = matched_row['display']
        st.session_state['selected_dinner_cal'] = float(matched_row['cal'])
        
        st.markdown(f"""
        <div class="menu-card">
            <h4 style="margin:0; color:#ff6f00;">選択中の夜ご飯</h4>
            <p style="margin:5px 0 0 0; font-weight:bold;">{matched_row['store']} - {matched_row['name']}</p>
            <p style="margin:2px 0 0 0; color:#6b7280; font-size:14px;">{int(matched_row['cal'])} kcal ({matched_row['genre']})</p>
        </div>
        """, unsafe_allow_html=True)
    else:
        st.session_state['selected_dinner'] = None
        st.session_state['selected_dinner_cal'] = 0.0
else:
    st.error("メニューデータ（dinner_list.csv）が読み込めていないため、夜ご飯の提案ができません。")

# --- 6. 自動挨拶（アバター切り替え対応版） ---
if "高木先生" in ai_persona:
    current_avatar = takagi_avatar
    bubble_class = "chat-bubble takagi-bubble"
elif "雷さん" in ai_persona:
    current_avatar = rai_avatar
    bubble_class = "chat-bubble rai-bubble"
else:
    current_avatar = "🤖"
    bubble_class = "chat-bubble"

st.divider()

with st.chat_message("assistant", avatar=current_avatar):
    if "高木先生" in ai_persona:
        if dinner_cal > 500:
            msg = f"Hello {user_id}さん！今日の残り枠は {int(dinner_cal)}kcal もありますね. This is perfect！素晴らしい投資効率（ROI）ですよ. 夜は美味しいものを楽しんでくださいね！"
        elif dinner_cal > 0:
            msg = f"順調にコントロールできていますね. Excellent！{user_id}さんの毎日の努力は素晴らしい asset（資産）になりますよ. この調子で頑張りましょう！"
        else:
            msg = f"Don't worry. 明日の朝からまたメタバースのように新しい気持ちで、ウェイトコントロールに投資していきましょう！"
    else:
        if dinner_cal > 500:
            msg = f"あったまいいね！今日はまだ {int(dinner_cal)}kcal も余裕があるね。美味しいもの探しに行おうよ！"
        elif dinner_cal > 0:
            msg = f"今のところ順調。夜は控えめな美食を楽しんで！"
        else:
            msg = f"今日もがんばっていこ！"
            
    st.markdown(f'<div class="{bubble_class}">{msg}</div>', unsafe_allow_html=True)

# --- 7.5 朝昼夕の合計摂取カロリー表示 ---
breakfast_cal = df_menu[df_menu['display'].isin(b_items)]['cal'].sum() if not df_menu.empty else 0
lunch_cal = df_menu[df_menu['display'].isin(l_items)]['cal'].sum() if not df_menu.empty else 0
dinner_selected_cal = st.session_state['selected_dinner_cal']
total_cal = breakfast_cal + lunch_cal + dinner_selected_cal

st.markdown("---")
st.subheader("📊 本日の栄養摂取状況")

with st.container(border=True):
    # グラフを消した分、4列にして数値をスッキリ横並びに配置
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        st.metric(label="🌅 朝食", value=f"{int(breakfast_cal)} kcal")
    with c2:
        st.metric(label="☀️ 昼食", value=f"{int(lunch_cal)} kcal")
    with c3:
        st.metric(label="🌙 夕食", value=f"{int(dinner_selected_cal)} kcal")
    with c4:
        st.metric(label="🔥 合計摂取", value=f"{int(total_cal)} kcal")
# --- 8. AI相談室 (Groq API 移行版) ---
if "chat_history" not in st.session_state:
    st.session_state.chat_history = []

if "高木先生" in ai_persona:
    chat_placeholder = "高木先生にWeb3やダイエットの相談をする"
elif "安藤先生" in ai_persona:
    chat_placeholder = "安藤先生にPythonや統計検定３級の相談をする"
elif "フォーマル" in ai_persona:
    chat_placeholder = "AIアシスタントに論理的な相談をする"
else:
    chat_placeholder = "雷に相談"

col_chat1, col_chat2 = st.columns([4, 1])
with col_chat2:
    if st.button("履歴クリア", use_container_width=True):
        st.session_state.chat_history = []
        st.rerun()

# 1. 過去のチャット履歴の描画
for msg in st.session_state.chat_history:
    with st.chat_message(msg["role"], avatar=msg["avatar"]):
        st.markdown(f'<div class="{msg["class"]}">{msg["content"]}</div>', unsafe_allow_html=True)

# 2. ユーザーの新しい入力処理
if user_msg := st.chat_input(chat_placeholder):
    with st.chat_message("user", avatar="👤"):
        st.markdown(f'<div class="chat-bubble user-bubble">{user_msg}</div>', unsafe_allow_html=True)
    
    st.session_state.chat_history.append({
        "role": "user",
        "content": user_msg,
        "class": "chat-bubble user-bubble",
        "avatar": "👤"
    })

    # Groq APIへのリクエスト処理
    with st.chat_message("assistant", avatar=current_avatar):
        current_status = f"""
[User Status Context]
- Target Weight: {user_row['target_weight']} kg
- Current Weight: {weight} kg
- Activity Level Factor: {activity}
- Remaining Calorie Budget for Dinner: {int(dinner_cal)} kcal
- Total Calorie Intake Today: {int(total_cal)} kcal
  * Breakfast: {int(breakfast_cal)} kcal
  * Lunch: {int(lunch_cal)} kcal
  * Tonight's Dinner: {st.session_state['selected_dinner'] or 'Not selected yet'} ({dinner_selected_cal} kcal)
"""
        try:
            sys_prompt = ai_config.get_system_prompt(ai_persona, user_id)
        except Exception:
            sys_prompt = "あなたは論理的で丁寧なAIアシスタントです。"

        # 💡 タコ（たこ焼き）を検知した場合の高木先生の拒否プロンプトを念押し補強
        if "高木先生" in ai_persona and any(x in user_msg or x in str(st.session_state['selected_dinner']) for x in ["タコ", "たこ", "tako", "Octopus"]):
            sys_prompt += "\n【CRITICAL WARNING】ユーザーからタコ（たこ焼き等）の話が出ました！全力で拒否し、別のヘルシーな投資（代替の食べ物）を英語を交えて提案してください！"

        context_reminder = "[Important Note: Please keep your response short, sweet, and perfectly match your character persona!]"
        
        with st.spinner("AIが爆速で回答を生成中..."):
            try:
                # 💡 無料枠で非常に軽快かつ賢い「llama-3.1-8b-instant」を指定
                response = client.chat.completions.create(
                    model="llama-3.1-8b-instant",
                    messages=[
                        {"role": "system", "content": f"{sys_prompt}\n\n{current_status}\n\n{context_reminder}"},
                        {"role": "user", "content": user_msg}
                    ],
                    temperature=0.75
                )
                
                ai_response_text = response.choices[0].message.content
                
                # 回答を画面に描画＆履歴に保存
                st.markdown(f'<div class="{bubble_class}">{ai_response_text}</div>', unsafe_allow_html=True)
                
                st.session_state.chat_history.append({
                    "role": "assistant",
                    "content": ai_response_text,
                    "class": bubble_class,
                    "avatar": current_avatar
                })
                
            except Exception as e:
                st.error(f"Groq API通信エラーが発生しました: {e}\nAPIキーが正しくセットされているか確認してください。")