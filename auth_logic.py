import time
import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
import time
takagi_avatar = "takagi.jpg" if os.path.exists("takagi.jpg") else "👨‍🏫"
from datetime import datetime
from dotenv import load_dotenv

# --- 1. 初期設定 ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key, transport="rest")
    model = genai.GenerativeModel('models/gemini-3-flash-preview')
else:
    st.error("APIキーがないよ！")
    st.stop()

# 💡 自作したstyleとai_configをインポート
import style
import ai_config

st.set_page_config(page_title="Dinner Logic DX", layout="wide")

# 💡 別ファイルのおしゃれCSSを適用
style.apply_custom_css()

# --- 2. データ管理関数 ---
USER_FILE = "user_settings.csv"
MENU_FILE = "dinner_list.csv"

def get_all_users():
    cols = ["user_id", "password", "target_weight", "last_update", "consecutive_days"]
    
    # 💡 パソコン（ローカル）の時はCSVから、Streamlit Cloudの時はネット上（secrets）から安全に読み込む
    if "user_db" in st.secrets:
        try:
            # ネット上の秘密のURL（Googleスプレッドシート等）からデータを読み込む仕組み
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
        
    # パソコン用にも保存する（元のまま）
    df.to_csv(USER_FILE, index=False)
    
    # 💡 【修正点】Googleスプレッドシート連携用の安全なバックアップ送信処理
    if "db_backup_url" in st.secrets and st.secrets["db_backup_url"]:
        try:
            # st.experimental_connection や外部Webhook等、安全に外部シートへデータを投げるリクエスト
            import requests
            # JSON形式でGoogleスプレッドシート等へバックアップを自動送信
            requests.post(st.secrets["db_backup_url"], json=df.to_dict(orient="records"), timeout=5)
        except:
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
    
    if pd.isna(last_update_str) or pd.isna(current_consecutive):
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

# 🍪 安全にブラウザからCookieを読み込む
cookie_user_id = st.context.cookies.get("saved_user_id")

# Cookieが残っていたら自動ログイン
if not st.session_state['is_logged_in'] and cookie_user_id:
    df = get_all_users()
    match = df[df['user_id'].astype(str) == str(cookie_user_id)]
    if not match.empty:
        user_info = match.iloc[0]
        reset_basic_info_on_month_start(cookie_user_id)
        
        consecutive_days = calculate_consecutive_days(cookie_user_id)
        save_user(cookie_user_id, user_info['password'], user_info['target_weight'], consecutive_days)
        
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
            st.markdown("<p style='text-align: center; color: #666; font-size: 14px;'>新しくアカウントを作成してサンダーさんと一緒にダイエットを始めましょう！</p>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                n_id = st.text_input("希望ID", key="reg_id", placeholder="ユーザーID")
                n_pw = st.text_input("パスワード", type="password", key="reg_pw", placeholder="パスワード")
                st.markdown("")
                col_a, col_b = st.columns(2)
                with col_a:
                    if st.button("📝 登録", use_container_width=True):
                        if n_id and n_pw:
                            save_user(n_id, n_pw)
                            st.success("登録完了！🥢 さあ、始めましょう！")
                            st.session_state['show_register'] = False
                            st.rerun()
                        else:
                            st.error("IDとパスワードを入力してね！")
                with col_b:
                    if st.button("🔙 戻る", use_container_width=True):
                        st.session_state['show_register'] = False
                        st.rerun()
    else:
        st.markdown("<div style='text-align: center;'><h1 style='color: #2196F3;'>🔐 今日からあなたもライエット</h1></div>", unsafe_allow_html=True)
        with st.container(border=True):
            st.markdown("<p style='text-align: center; color: #666; font-size: 14px;'>美食家サンダーさんとの美食ダイエット of 冒険へようこそ！</p>", unsafe_allow_html=True)
            col1, col2, col3 = st.columns([1, 2, 1])
            with col2:
                l_id = st.text_input("ユーザーID", key="login_id", placeholder="IDを入力")
                l_pw = st.text_input("パスワード", type="password", key="login_pw", placeholder="パスワードを入力")
                st.markdown("")
                if st.button("🔓 ログイン", use_container_width=True):
                    df = get_all_users()
                    match = df[(df['user_id'].astype(str) == l_id) & (df['password'].astype(str) == l_pw)]
                    if not match.empty:
                        user_info = match.iloc[0]
                        reset_basic_info_on_month_start(l_id)
                        
                        consecutive_days = calculate_consecutive_days(l_id)
                        save_user(l_id, user_info['password'], user_info['target_weight'], consecutive_days)
                        
                        st.session_state['height'] = float(user_info.get('height', 160.0))
                        st.session_state['weight'] = float(user_info.get('weight', 55.0))
                        st.session_state['age'] = int(user_info.get('age', 20))
                        st.session_state['gender'] = user_info.get('gender', "女子")
                        
                        st.session_state['is_logged_in'] = True
                        st.session_state['current_user'] = l_id
                        
                        # 🍪 JavaScriptで安全にCookieに書き込む
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
user_row = df_users[df_users['user_id'].astype(str) == user_id].iloc[0]
df_menu = load_menu()

# C. 目標設定画面
if pd.isna(user_row['target_weight']) or datetime.now().day == 1:
    st.title(f"📅 目標設定 ({user_id})")
    t_w = st.number_input("今月の目標体重 (kg)", 30.0, 150.0, 52.0)
    if st.button("目標を保存"):
        save_user(user_id, user_row['password'], t_w)
        st.rerun()
    st.stop()

# --- 4. メイン画面の準備 ---
if os.path.exists("mii_thunder.jpg"):
    thunder_avatar = "mii_thunder.jpg"
elif os.path.exists("mii_thunder.png"):
    thunder_avatar = "mii_thunder.png"
else:
    thunder_avatar = "⚡️"

st.title(f"🥘 推し活 で ライエット")

consecutive_days = int(user_row.get('consecutive_days', 1))
st.markdown("---")
with st.container(border=True):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"<div style='text-align: center;'><h2 style='color: #ff6b6b; margin-bottom: 5px;'>🔥 連続ログイン</h2><p style='font-size: 16px; color: #666; margin: 5px 0;'>あなたは今日で</p><p style='font-size: 48px; font-weight: bold; color: #ff6b6b; margin: 10px 0;'>{consecutive_days}</p><p style='font-size: 16px; color: #666; margin-top: 5px;'>日連続で頑張ってるよ！</p></div>", unsafe_allow_html=True)

st.markdown("---")

with st.sidebar:
    st.image(thunder_avatar, width=150, caption="美食家サンダー⚡️")
    st.header("👤 ステータス")
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
        ["サンダーさん ", "高木先生モード", "フォーマル "]
    )
    
    if st.button("ログアウト"):
        # 🍪 JavaScriptを使って安全にCookieを消去
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
    st.subheader("🍽️ 選択されたメニュー")
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

# --- 6. 自動挨拶（キャラクター分岐対応版） ---
st.divider()

if ai_persona == "高木先生モード":
    current_avatar = takagi_avatar
elif ai_persona == "サンダーさん ":
    current_avatar = thunder_avatar
else:
    current_avatar = "🤖"

with st.chat_message("assistant", avatar=current_avatar):
    if ai_persona == "高木先生モード":
        if dinner_cal > 500:
            st.write(f"Hello {user_id}さん！今日の残り枠は {int(dinner_cal)}kcal もありますね. This is perfect！素晴らしい投資効率（ROI）ですよ. 夜は美味しいものを楽しんでくださいね！")
        elif dinner_cal > 0:
            st.write(f"順調にコントロールできていますね. Excellent！{user_id}さんの毎日の努力は素晴らしい asset（資産）になりますよ. この調子で頑張りましょう！")
        else:
            st.write(f"Oh... カロリーオーバーしてしまいましたね. でも大丈夫ですよ！Don't worry. 明日の朝からまたメタバースのように新しい気持ちで、ウェイトコントロールに投資していきましょう！")
    else:
        if dinner_cal > 500:
            st.write(f"あったまいいね！今日はまだ {int(dinner_cal)}kcal も余裕があるね。美味しいもの探しに行こうよ！")
        elif dinner_cal > 0:
            st.write(f"今のところ順調。夜は控えめな美食を楽しんで！")
        else:
            st.write(f"ちょっと！もうカロリーオーバー！明日は食べすぎ禁止ね！")

# --- 7. おすすめメニュー表示 ---
st.subheader(" おすすめメニュー")
if not df_menu.empty:
    recs = df_menu[df_menu['cal'] <= dinner_cal].sort_values(by='cal', ascending=False).head(5)
    if not recs.empty:
        cols = st.columns(5, gap="medium")
        for i, (_, row) in enumerate(recs.iterrows()):
            with cols[i]:
                with st.container(border=True):
                    st.markdown(f"<h3 style='text-align: center;'>🍽️</h3>", unsafe_allow_html=True)
                    st.markdown(f"<p style='text-align: center; font-weight: bold; font-size: 16px;'>{row['store']}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='text-align: center; color: #666; font-size: 14px;'>{row['name']}</p>", unsafe_allow_html=True)
                    st.markdown(f"<p style='text-align: center; color: #ff6b6b; font-size: 18px; font-weight: bold;'>✨ {int(row['cal'])} kcal</p>", unsafe_allow_html=True)
                    if st.button("選択する", key=f"rec_{i}", use_container_width=True):
                        st.session_state['selected_dinner'] = row['name']
                        st.session_state['selected_dinner_cal'] = int(row['cal'])
                        st.success(f"「{row['name']}」を夕食に選択しました！")
    else:
        st.warning("おすすめメニューが見つかりません。")
else:
    st.error("メニューが読み込めません。")

# --- 7.5 朝昼夕の合計摂取カロリー表示 ---
breakfast_cal = df_menu[df_menu['display'].isin(b_items)]['cal'].sum()
lunch_cal = df_menu[df_menu['display'].isin(l_items)]['cal'].sum()
total_cal = breakfast_cal + lunch_cal + st.session_state['selected_dinner_cal']

st.markdown("---")
st.subheader("本日の栄養摂取状況")
with st.container(border=True):
    c1, c2 = st.columns(2)
    c3, c4 = st.columns(2)
    with c1:
        st.metric(label=" 朝食", value=f"{int(breakfast_cal)} kcal")
    with c2:
        st.metric(label=" 昼食", value=f"{int(lunch_cal)} kcal")
    with c3:
        st.metric(label=" 夕食", value=f"{st.session_state['selected_dinner_cal']} kcal")
    with c4:
        st.metric(label=" 合計", value=f"{int(total_cal)} kcal")

# --- 8. AI相談室 ---
if ai_persona == "高木先生モード":
    chat_placeholder = "高木先生にWeb3やライエットの相談をする"
elif ai_persona == "フォーマル (教授ウケ重視)":
    chat_placeholder = "AIアシスタントに論理的な相談をする"
else:
    chat_placeholder = "美食家サンダーさんに相談"

if user_msg := st.chat_input(chat_placeholder):
    with st.chat_message("assistant", avatar=current_avatar):
        sys_prompt = ai_config.get_system_prompt(ai_persona, user_id)
        prompt = f"{sys_prompt}\n残り{int(dinner_cal)}kcal。質問:{user_msg}"
        try:
            response = model.generate_content(prompt)
            st.write(response.text)
        except Exception as e:
            st.error(f"AIエラー: {e}")

# --- サイドバーの最下部にBGMを配置 ---
with st.sidebar:
    st.markdown("---")
    st.write("🎵 BGM")
    st.video("https://youtu.be/l7Tr8xb_tFk", format="video/mp4", start_time=0)