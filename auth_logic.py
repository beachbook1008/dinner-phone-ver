import time
import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image

# --- アバター・画像の存在チェック ---
takagi_avatar = "takagi.jpg" if os.path.exists("takagi.jpg") else "👨‍🏫"
# 💡 雷さんの単体画像
rai_avatar = "mii_thunder.jpg" if os.path.exists("mii_thunder.jpg") else "⚡️"
# 💡 集合写真とツーショット画像
all_friends_img = "allfriends.jpg" if os.path.exists("allfriends.jpg") else None
takagi_rai_img = "takagirai.jpg" if os.path.exists("takagirai.jpg") else None

# --- 1. 初期設定 ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key, transport="rest")
    model = genai.GenerativeModel('models/gemini-3-flash-preview')
else:
    st.error("APIキーがないよ！")
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
    
    if "db_backup_url" not in st.secrets:
        st.error("🚨 エラー理由：StreamlitのSecretsに『db_backup_url』という名前が登録されていません！")
    elif not st.secrets["db_backup_url"]:
        st.error("🚨 エラー理由：Secretsの『db_backup_url = \"\"』の中身が空っぽになっています！")
    else:
        try:
            import requests
            import json
            clean_df = df.fillna("")
            json_data = json.dumps(clean_df.to_dict(orient="records"))
            res = requests.post(st.secrets["db_backup_url"], data=json_data, headers={"Content-Type": "application/json"}, timeout=10)
            if res.status_code == 200:
                st.success(f"⭕ Googleへの送信自体は成功しました！Googleからの返事: {res.text}")
            else:
                st.error(f"❌ Google側で拒否されました。エラーコード: {res.status_code} / 返事: {res.text}")
        except Exception as e:
            st.error(f"💥 通信エラーが起きました。エラー内容: {e}")

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

cookie_user_id = st.context.cookies.get("saved_user_id")

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
            # 💡 新規登録画面の上部にも華やかに集合写真を配置
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
            # 💡 【ご要望】ログイン画面のトップにみんなの写真（allfriends.jpg）を表示！
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
if pd.isna(user_row['target_weight']) or datetime.now().day == 1:
    st.title(f"📅 目標設定 ({user_id})")
    t_w = st.number_input("今月の目標体重 (kg)", 30.0, 150.0, 52.0)
    if st.button("目標を保存"):
        save_user(user_id, user_row['password'], t_w)
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
    # 💡 【ご要望】高木先生と雷さんのツーショット画像をサイドバー上部にマスコットとして組み込み！
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
        ["雷さん ", "高木先生モード", "フォーマル "]
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

# --- 6. 自動挨拶（アバター切り替え対応版） ---
# --- 6. 自動挨拶（アバター切り替え対応版） ---
st.divider()

# 💡 キャラクターの選択状態に応じてアバターと吹き出しの色を決定！
if ai_persona == "高木先生モード":
    current_avatar = takagi_avatar
    bubble_class = "chat-bubble takagi-bubble"
elif ai_persona == "雷さん ":
    current_avatar = rai_avatar
    bubble_class = "chat-bubble rai-bubble"
else:
    current_avatar = "🤖"
    bubble_class = "chat-bubble"

with st.chat_message("assistant", avatar=current_avatar):
    if ai_persona == "高木先生モード":
        if dinner_cal > 500:
            msg = f"Hello {user_id}さん！今日の残り枠は {int(dinner_cal)}kcal もありますね. This is perfect！素晴らしい投資効率（ROI）ですよ. 夜は美味しいものを楽しんでくださいね！"
        elif dinner_cal > 0:
            msg = f"順調にコントロールできていますね. Excellent！{user_id}さんの毎日の努力は素晴らしい asset（資産）になりますよ. この調子で頑張りましょう！"
        else:
            msg = f"Oh... カロリーオーバーしてしまいましたね. でも大丈夫ですよ！Don't worry. 明日の朝からまたメタバースのように新しい気持ちで、ウェイトコントロールに投資していきましょう！"
    else:
        if dinner_cal > 500:
            msg = f"あったまいいね！今日はまだ {int(dinner_cal)}kcal も余裕があるね。美味しいもの探しに行こうよ！"
        elif dinner_cal > 0:
            msg = f"今のところ順調。夜は控えめな美食を楽しんで！"
        else:
            msg = f"ちょっと！もうカロリーオーバー！明日は食べすぎ禁止ね！"
            
    # 💡 st.write の代わりに吹き出し用のHTMLで文字を囲む！
    st.markdown(f'<div class="{bubble_class}">{msg}</div>', unsafe_allow_html=True)
# --- 7.5 朝昼夕の合計摂取カロリー表示 ---
breakfast_cal = df_menu[df_menu['display'].isin(b_items)]['cal'].sum()
lunch_cal = df_menu[df_menu['display'].isin(l_items)]['cal'].sum()
dinner_selected_cal = st.session_state['selected_dinner_cal']
total_cal = breakfast_cal + lunch_cal + dinner_selected_cal

st.markdown("---")
st.subheader("📊 本日の栄養摂取状況とバランス")

# 💡 左右に分割して、左に数字、右に円グラフを並べる！
chart_col1, chart_col2 = st.columns([1, 1])

with chart_col1:
    with st.container(border=True):
        c1, c2 = st.columns(2)
        with c1:
            st.metric(label="🌅 朝食", value=f"{int(breakfast_cal)} kcal")
            st.metric(label="🌙 夕食", value=f"{int(dinner_selected_cal)} kcal")
        with c2:
            st.metric(label="☀️ 昼食", value=f"{int(lunch_cal)} kcal")
            st.metric(label="🔥 合計摂取", value=f"{int(total_cal)} kcal")

with chart_col2:
    # 💡 グラフ用のデータを準備（残り枠がマイナスの時は0にする）
    left_cal = max(0, int(dinner_cal)) if 'dinner_cal' in locals() else 0
    
    raw_labels = ['朝食', '昼食', '夕食', '残り枠']
    raw_sizes = [breakfast_cal, lunch_cal, dinner_selected_cal, left_cal]
    raw_colors = ['#ffa500', '#4CAF50', '#2196F3', '#e0e0e0']
    
    # 💡 【文字の重なり解消！】0のデータはグラフの部品から完全に除外する
    labels = []
    sizes = []
    colors = []
    for s, l, c in zip(raw_sizes, raw_labels, raw_colors):
        if s > 0:
            labels.append(l)
            sizes.append(s)
            colors.append(c)
            
    # 何も入力されていない（または全部0）の時は、スッキリした1つのグレー円にする
    if len(sizes) == 0:
        sizes = [100]
        labels = ['1日の目標枠']
        colors = ['#e0e0e0']
    
    # 💡 【真・文字化け対策】ちゃんと「日本語」が入っている美しいフォントを直接適用する！
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    import urllib.request
    import os

    # 1. 日本語対応のフォント（BIZ UDゴシック）をダウンロード
    font_url = "https://github.com/googlefonts/morisawa-biz-ud-gothic/raw/main/fonts/ttf/BIZUDGothic-Regular.ttf"
    font_path = "BIZUDGothic-Regular.ttf"
    if not os.path.exists(font_path):
        try:
            urllib.request.urlretrieve(font_url, font_path)
        except:
            pass
            
    # 2. フォントのデータを準備
    if os.path.exists(font_path):
        fp = fm.FontProperties(fname=font_path)
    else:
        fp = fm.FontProperties(family='sans-serif')
    
    # 3. グラフを描画（textpropsで直接日本語フォントを指定！）
    fig, ax = plt.subplots(figsize=(4, 4))
    wedges, texts, autotexts = ax.pie(
        sizes, 
        labels=labels, 
        autopct=lambda p: '{:.1f}%'.format(p) if p > 0 else '', 
        startangle=90, 
        colors=colors,
        textprops={'color': "black", 'size': 9, 'fontproperties': fp}, 
        wedgeprops=dict(width=0.4, edgecolor='white') # ドーナツの幅
    )
    plt.setp(autotexts, size=8, weight="bold", fontproperties=fp)
    ax.axis('equal')  
    
    # Streamlitの画面にグラフを表示！
    st.pyplot(fig)

# --- 8. AI相談室 ---
# --- 8. AI相談室 ---
if ai_persona == "高木先生モード":
    chat_placeholder = "高木先生にWeb3やライエットの相談をする"
elif ai_persona == "フォーマル":
    chat_placeholder = "AIアシスタントに論理的な相談をする"
else:
    chat_placeholder = "雷さんに相談"

st.markdown("---")

# 🌟 1. 画像アップロードとタイミング選択
uploaded_file = st.file_uploader("📸 食べたもの（またはこれから食べる予定）の画像をアップロード", type=["jpg", "jpeg", "png"])

meal_timing = ""
if uploaded_file:
    st.image(uploaded_file, caption="送信準備完了", width=250)
    # 🌟 いつのご飯かを選択（横並びのラジオボタン）
    meal_timing = st.radio(
        "💡 これはいつのご飯ですか？", 
        ["朝食（食べた）", "昼食（食べた）", "夜ご飯（これから食べる）"], 
        horizontal=True
    )

# 🌟 2. 夜ご飯提案ボタン（CSV読み込み機能付き）
suggest_button = st.button("🍽️ AIに夜ご飯を提案してもらう！（dinner_listから選択）")

# 🌟 3. メッセージの組み立て
user_msg = None
chat_input_val = st.chat_input(chat_placeholder)

if chat_input_val:
    user_msg = chat_input_val
    # 画像があってタイミングも選ばれている場合、プロンプトの先頭に情報を付与する
    if uploaded_file and meal_timing:
        user_msg = f"【画像情報: {meal_timing}】\n" + user_msg

elif suggest_button:
    # CSVファイルを読み込んでAIに渡すプログラミング
    try:
        df_menu_raw = pd.read_csv(MENU_FILE)
        # Geminiが処理しやすいようにCSVの全テキストデータを変数に格納
        menu_data = df_menu_raw.to_csv(index=False)
        
        user_msg = f"今日の夜ご飯を提案して！以下の【dinner_list.csv】のデータを参考にして、おすすめのメニューとカロリー計算を教えて！\n\n【dinner_list.csv】\n{menu_data}"
    except Exception as e:
        user_msg = "今日の夜ご飯を提案して！おすすめのメニューとカロリー計算を教えて！（※dinner_list.csvが読み込めませんでした）"

# 🌟 4. メッセージ（またはボタンの自動テキスト）があればGeminiの処理を走らせる
if user_msg:
    with st.chat_message("assistant", avatar=current_avatar):
        # 1. 各種変数の状況を、AIがパッと理解できる構造化テキストにする
        current_status = f"""
[User Status Context]
- Target Weight: {user_row['target_weight']} kg
- Current Weight: {weight} kg
- Activity Level Factor: {activity}
- Remaining Calorie Budget for Dinner: {int(dinner_cal)} kcal
- Total Calorie Intake Today: {int(total_cal)} kcal
  * Breakfast: {int(breakfast_cal)} kcal (Selected: {', '.join(b_items) if b_items else 'None'})
  * Lunch: {int(lunch_cal)} kcal (Selected: {', '.join(l_items) if l_items else 'None'})
  * Dinner (Selected from recommendation): {st.session_state['selected_dinner'] or 'Not selected yet'} ({dinner_selected_cal} kcal)
"""

        # 2. システムプロンプト、現在のステータス、ユーザーの質問を綺麗に結合
        sys_prompt = ai_config.get_system_prompt(ai_persona, user_id)
        prompt = f"{sys_prompt}\n\n{current_status}\n\nUser Question: {user_msg}"
        
        # 💡 キャラクターごとにスピナーのメッセージを切り替える設定
        if ai_persona == "高木先生モード":
            spinner_msg = "AIプロンプトをメタバースに送信中... 10 seconds ほどお待ちください... 🌐"
        elif ai_persona == "雷さん ":
            spinner_msg = "雷さんが美味しいお店を爆速検索中"
        else:
            spinner_msg = "AIが論理的なアドバイスを生成しています... "

        # 💡 try-except の外側を with st.spinner() で囲む
        with st.spinner(spinner_msg):
            try:
                if uploaded_file is not None:
                    img = Image.open(uploaded_file)
                    response = model.generate_content([prompt, img])
                else:
                    response = model.generate_content(prompt)
                
                # キャラクターに応じた吹き出しクラスを再度判定
                if ai_persona == "高木先生モード":
                    bubble_class = "chat-bubble takagi-bubble"
                elif ai_persona == "雷さん ":
                    bubble_class = "chat-bubble rai-bubble"
                else:
                    bubble_class = "chat-bubble"
                
                # 💡 AIの返答を吹き出し風のHTMLでラッピングして表示
                st.markdown(f'<div class="{bubble_class}">{response.text}</div>', unsafe_allow_html=True)
                
            except Exception as e:
                st.error(f"AIエラー: {e}")

# --- サイドバーの最下部にBGMを配置 ---
with st.sidebar:
    st.markdown("---")
    st.write("🎵 BGM")
    st.video("https://youtu.be/l7Tr8xb_tFk", format="video/mp4", start_time=0)