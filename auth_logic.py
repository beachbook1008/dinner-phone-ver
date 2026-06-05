import time
import streamlit as st
import pandas as pd
import google.generativeai as genai
import os
from datetime import datetime
from dotenv import load_dotenv
from PIL import Image
import threading
import re
import hashlib
import json

# --- アバター・画像の存在チェック ---
takagi_avatar = "takagi.jpg" if os.path.exists("takagi.jpg") else "👨‍🏫"
rai_avatar = "mii_thunder.jpg" if os.path.exists("mii_thunder.jpg") else "👨‍🏫"
all_friends_img = "allfriends.jpg" if os.path.exists("allfriends.jpg") else None
takagirai_img = "takagirai.jpg" if os.path.exists("takagirai.jpg") else None

# --- 1. 初期設定 ---
load_dotenv()
api_key = os.getenv("GEMINI_API_KEY")
if api_key:
    genai.configure(api_key=api_key)
    model_vision = genai.GenerativeModel('gemini-2.5-flash')       # 画像用（超高精度）
    model_chat = genai.GenerativeModel('gemini-2.5-flash-lite')   # 雑談用（超軽量）
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
    
    if "db_backup_url" not in st.secrets or not st.secrets["db_backup_url"]:
        pass
    else:
        def run_backup_async(url, data_str):
            try:
                import requests
                requests.post(url, data=data_str, headers={"Content-Type": "application/json"}, timeout=10)
            except:
                pass

        import json
        clean_df = df.fillna("")
        json_data = json.dumps(clean_df.to_dict(orient="records"))
        threading.Thread(target=run_backup_async, args=(st.secrets["db_backup_url"], json_data), daemon=True).start()

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
if 'selected_dinner' not in st.session_state: st.session_state['selected_dinner'] = None

# カロリー＆料理名保存場所の初期化
if 'vision_breakfast_cal' not in st.session_state: st.session_state['vision_breakfast_cal'] = 0
if 'vision_lunch_cal' not in st.session_state: st.session_state['vision_lunch_cal'] = 0
if 'selected_dinner_cal' not in st.session_state: st.session_state['selected_dinner_cal'] = 0
if 'last_analyzed_hash' not in st.session_state: st.session_state['last_analyzed_hash'] = None

# AI認識した料理名を個別に保持するセッション
if 'breakfast_food_name' not in st.session_state: st.session_state['breakfast_food_name'] = ""
if 'lunch_food_name' not in st.session_state: st.session_state['lunch_food_name'] = ""
if 'dinner_food_name' not in st.session_state: st.session_state['dinner_food_name'] = ""

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

# --- サイドバーの設定 ---
with st.sidebar:
    if takagirai_img:
        st.image(takagirai_img, use_container_width=True, caption="開発チーム: 高木先生 & 雷さん")
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
    ai_persona = st.selectbox("AIのキャラクター", ["雷さん ", "高木先生モード", "フォーマル "])
    
    if st.button("ログアウト"):
        st.components.v1.html("""
            <script>
                document.cookie = "saved_user_id=; max-age=0; path=/; Secure; SameSite=Lax";
            </script>
        """, height=0)
        st.session_state.clear()
        st.rerun()

# タイトル表示と連続ログイン表示
st.title(f"今日からダイエット")
consecutive_days = int(user_row.get('consecutive_days', 1))
st.markdown("---")
with st.container(border=True):
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown(f"<div style='text-align: center;'><h2 style='color: #ff6b6b; margin-bottom: 5px;'>🔥 連続ログイン</h2><p style='font-size: 16px; color: #666; margin: 5px 0;'>あなたは今日で</p><p style='font-size: 48px; font-weight: bold; color: #ff6b6b; margin: 10px 0;'>{consecutive_days}</p><p style='font-size: 16px; color: #666; margin-top: 5px;'>日連続で頑張ってるよ！</p></div>", unsafe_allow_html=True)

st.markdown("---")

# --- 4. 画像・チャット入力 UI配置 ---
if ai_persona == "高木先生モード":
    chat_placeholder = "高木先生にWeb3やライエットの相談をする"
elif ai_persona == "フォーマル":
    chat_placeholder = "AIアシスタントに論理的な相談をする"
else:
    chat_placeholder = "雷さんに相談"

uploaded_file = st.file_uploader("📸 食べたもの（またはこれから食べる予定）の画像をアップロード", type=["jpg", "jpeg", "png"])

meal_timing = ""
if uploaded_file:
    st.image(uploaded_file, caption="送信準備完了", width=250)
    
    btn_col1, btn_col2 = st.columns([3, 1])
    with btn_col1:
        meal_timing = st.radio("💡 これはいつのご飯ですか？", ["朝食（食べた）", "昼食（食べた）", "夜ご飯（これから食べる）"], horizontal=True)
    with btn_col2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        if st.button("🔄 区分を変更して再解析"):
            st.session_state['last_analyzed_hash'] = None

suggest_button = st.button("🍽️ AIに夜ご飯を提案してもらう！（dinner_listから選択）")
chat_input_val = st.chat_input(chat_placeholder)

user_msg = None
is_vision_mode = False

if uploaded_file and meal_timing:
    try:
        file_bytes = uploaded_file.getvalue()
        current_file_hash = hashlib.md5(file_bytes).hexdigest() + f"_{meal_timing}"
        
        # 🌟 ハッシュロック判定（解析成功時のみロックする仕様）
        if st.session_state.get('last_analyzed_hash') != current_file_hash:
            is_vision_mode = True
            if "夜ご飯" in meal_timing:
                user_msg = f"【システム通知】ユーザーが「{meal_timing}」の画像を送信しました。これからこれを夜ご飯に食べようと思っています。画像から料理名を特定し、カロリーを計算してアドバイスをください。"
            else:
                user_msg = f"【システム通知】ユーザーが「{meal_timing}」の画像を送信しました。ユーザーはすでにこの料理を食べ終わっています。画像から料理を認識し、「〇〇を食べたんだな！」「画像を見たぞ！」と、画像認識をしたことと、{meal_timing}を食べた事実を明確に受け止めるリアクションをしてください（※代わりのメニュー提案は一切不要です）。"
    except:
        pass

# --- 5. AI相談のリアルタイム処理（一本化・最新迎撃版） ---
ai_printed_text = ""
if user_msg:
    tmp_bmr = (447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)) if gender == "女子" else (88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age))
    tmp_target = (tmp_bmr * activity) - ((weight - float(user_row['target_weight'])) * 7200 / 30)
    tmp_csv_b = df_menu[df_menu['display'].isin(st.session_state.get('b_items_sel', []))]['cal'].sum() if not df_menu.empty else 0
    tmp_csv_l = df_menu[df_menu['display'].isin(st.session_state.get('l_items_sel', []))]['cal'].sum() if not df_menu.empty else 0
    
    current_status = f"""
[User Status Context]
- Target Weight: {user_row['target_weight']} kg
- Current Weight: {weight} kg
- Activity Level Factor: {activity}
- Remaining Calorie Budget for Dinner: {int(tmp_target - (tmp_csv_b + st.session_state['vision_breakfast_cal']) - (tmp_csv_l + st.session_state['vision_lunch_cal']))} kcal
"""
    sys_prompt = ai_config.get_system_prompt(ai_persona, user_id)
    
    if is_vision_mode:
        sys_prompt += f"\n\n【システムからの絶対命令】\n" \
                      f"1. あなたの発言（セリフ）の文章とは別に、必ず回答の「一番最後の行」に料理の名前と推定カロリーを以下の仕様のJSONフォーマットだけで出力してください。他の文字を混ぜてはいけません。\n" \
                      f"```json\n" \
                      f"{{\n" \
                      f"  \"food_name\": \"特定した料理名\",\n" \
                      f"  \"calorie\": 123\n" \
                      f"}}\n" \
                      f"```\n" \
                      f"2. 文面は必ず現在のキャラクター（{ai_persona.strip()}）なりきって「画像を見た事実」や「{meal_timing}に食べた事実」に明確に触れて作成してください。"

    prompt = f"{sys_prompt}\n\n{current_status}\n\nUser Question: {user_msg}"
    spinner_msg = "雷さんが画像を爆速でパケット解析中 ⚡" if ai_persona == "雷さん " else "AIがアドバイスを生成中..."

    with st.sidebar:
        st.markdown(f"**🔧 Debug Status**\n- Vision Mode: `{is_vision_mode}`\n- Hash: `{st.session_state.get('last_analyzed_hash')[:8] if st.session_state.get('last_analyzed_hash') else 'None'}`")

    with st.spinner(spinner_msg):
        try:
            if is_vision_mode and uploaded_file is not None:
                img = Image.open(uploaded_file)
                response = model_vision.generate_content([prompt, img])
            else:
                response = model_chat.generate_content(prompt)
            
            ai_printed_text = response.text
            extracted_cal = 0
            food_name = ""
            
            if is_vision_mode:
                # 🔍 開発者用バックエンド生データ確認アコーディオン
                with st.expander("🔍 開発者デバッグ: Gemini Vision 生の応答データ"):
                    st.text(ai_printed_text)
                
                try:
                    # 第一防衛線: ```json をパース
                    json_match = re.search(r'```json\s*(\{.*?\})\s*```', ai_printed_text, re.DOTALL)
                    if not json_match:
                        # 第二防衛線: 生JSON単体をパース
                        json_match = re.search(r'(\{.*?\})', ai_printed_text, re.DOTALL)
                        
                    if json_match:
                        json_str = json_match.group(1)
                        ai_printed_text = ai_printed_text.replace(json_match.group(0), "").strip()
                        
                        data = json.loads(json_str)
                        food_name = data.get("food_name", "")
                        extracted_cal = int(data.get("calorie", 0))
                    
                    # 救済リカバリーロジック: JSONが壊れていても文章の「◯◯kcal」を正規表現で引っこ抜く
                    if extracted_cal == 0:
                        cal_text_match = re.search(r'(\d+)\s*kcal', ai_printed_text, re.IGNORECASE)
                        if cal_text_match:
                            extracted_cal = int(cal_text_match.group(1))
                            food_name = "解析メニュー（テキスト救済）"
                            st.toast("💡 JSON不備を検知。テキストからカロリーデータを救済抽出しました。", icon="ℹ️")
                            
                except Exception as json_err:
                    st.error(f"⚠️ JSON解析エラー (パース失敗): {json_err}")
            
            if is_vision_mode:
                st.info(f"📋 **解析判定ログ** | food=`{food_name}` | cal=`{extracted_cal}kcal` | vision_mode=`{is_vision_mode}`")

            # 🌟 抽出完了（成功時）のみデータを各時間帯に代入し、ここでハッシュロックをかける
            if extracted_cal > 0 and meal_timing:
                if "朝食" in meal_timing:
                    st.session_state['vision_breakfast_cal'] = extracted_cal
                    st.session_state['breakfast_food_name'] = food_name
                elif "昼食" in meal_timing:
                    st.session_state['vision_lunch_cal'] = extracted_cal
                    st.session_state['lunch_food_name'] = food_name
                elif "夜ご飯" in meal_timing:
                    st.session_state['selected_dinner_cal'] = extracted_cal
                    st.session_state['dinner_food_name'] = food_name
                    
                st.session_state['last_analyzed_hash'] = current_file_hash
                
                if food_name:
                    st.toast(f"🍳 AI画像認識成功: 「{food_name}」", icon="✨")
                    
        except Exception as e:
            st.error(f"🔥 Vision/Chat例外発生: {type(e).__name__}")
            st.error(f"🔥 例外内容: {e}")

            extracted_cal = 600
            food_name = "画像解析メニュー（自動判定）"
            if is_vision_mode:
                # 🌟 = ではなく += にして、AIの本来のセリフ（または枠）の前にシステム通知を「付け足す」形にします！
                system_notice = "【システム通知: 自動判定モード起動】\nAPI接続制限を検知したため、システムを自動判定モードに切り替えました。\n\n画像の料理データをプログラム側で安全に自動算出（一律600kcal）し、計算を継続します。デモの実演には影響ありません。"
                ai_printed_text = f"{system_notice}\n\n{ai_printed_text}" if ai_printed_text else system_notice
                st.session_state['last_analyzed_hash'] = current_file_hash

# --- 6. 確定したカロリー計算とメニューのセレクトボックス表示 ---
bmr = (447.593 + (9.247 * weight) + (3.098 * height) - (4.330 * age)) if gender == "女子" else (88.362 + (13.397 * weight) + (4.799 * height) - (5.677 * age))
target_cal = (bmr * activity) - ((weight - float(user_row['target_weight'])) * 7200 / 30)

col1, col2 = st.columns(2)
with col1:
    b_items = st.multiselect("朝食", df_menu['display'].tolist() if not df_menu.empty else [], key="b_items_sel")
with col2:
    l_items = st.multiselect("昼食", df_menu['display'].tolist() if not df_menu.empty else [], key="l_items_sel")

if (b_items or l_items or 
    st.session_state['breakfast_food_name'] or 
    st.session_state['lunch_food_name'] or 
    st.session_state['dinner_food_name']):
    
    st.subheader("選択・解析されたメニュー")
    col_b, col_l, col_d = st.columns(3)
    
    with col_b:
        with st.container(border=True):
            st.markdown(f"<h3 style='text-align: center; color: #ffa500;'>🌅 朝食</h3>", unsafe_allow_html=True)
            if st.session_state['breakfast_food_name']:
                st.markdown(f"<div style='text-align: center; background-color: #fff3cd; padding: 5px; border-radius: 5px; font-weight: bold; color: #856404; margin-bottom: 8px;'>🤖 AI認識: {st.session_state['breakfast_food_name']} ({st.session_state['vision_breakfast_cal']}kcal)</div>", unsafe_allow_html=True)
            for item in b_items:
                st.markdown(f"<p style='text-align: center; color: #666; font-size: 14px; font-weight: bold;'>✓ {item}</p>", unsafe_allow_html=True)
                
    with col_l:
        with st.container(border=True):
            st.markdown(f"<h3 style='text-align: center; color: #4CAF50;'>☀️ 昼食</h3>", unsafe_allow_html=True)
            if st.session_state['lunch_food_name']:
                st.markdown(f"<div style='text-align: center; background-color: #d4edda; padding: 5px; border-radius: 5px; font-weight: bold; color: #155724; margin-bottom: 8px;'>🤖 AI認識: {st.session_state['lunch_food_name']} ({st.session_state['vision_lunch_cal']}kcal)</div>", unsafe_allow_html=True)
            for item in l_items:
                st.markdown(f"<p style='text-align: center; color: #666; font-size: 14px; font-weight: bold;'>✓ {item}</p>", unsafe_allow_html=True)

    with col_d:
        with st.container(border=True):
            st.markdown(f"<h3 style='text-align: center; color: #2196F3;'>🌙 夕食</h3>", unsafe_allow_html=True)
            if st.session_state['dinner_food_name']:
                st.markdown(f"<div style='text-align: center; background-color: #cce5ff; padding: 5px; border-radius: 5px; font-weight: bold; color: #004085; margin-bottom: 8px;'>🤖 AI認識: {st.session_state['dinner_food_name']} ({st.session_state['selected_dinner_cal']}kcal)</div>", unsafe_allow_html=True)
            else:
                st.markdown(f"<p style='text-align: center; color: #999; font-size: 13px; font-style: italic;'>画像未解析</p>", unsafe_allow_html=True)

csv_breakfast_cal = df_menu[df_menu['display'].isin(b_items)]['cal'].sum() if not df_menu.empty else 0
csv_lunch_cal = df_menu[df_menu['display'].isin(l_items)]['cal'].sum() if not df_menu.empty else 0

breakfast_cal = csv_breakfast_cal + st.session_state['vision_breakfast_cal']
lunch_cal = csv_lunch_cal + st.session_state['vision_lunch_cal']
dinner_selected_cal = st.session_state['selected_dinner_cal']

total_cal = breakfast_cal + lunch_cal + dinner_selected_cal
# 🌟 残り枠計算の引き算修正
dinner_cal = target_cal - breakfast_cal - lunch_cal - dinner_selected_cal

st.metric("今日の残り枠", f"{int(dinner_cal)} kcal")

# --- 7. 自動挨拶 & AI相談のチャット表示 ---
st.divider()

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
    if ai_printed_text:
        st.markdown(f'<div class="{bubble_class}">{ai_printed_text}</div>', unsafe_allow_html=True)
    else:
        # 🌟 高木先生モードの初期挨拶
        if ai_persona == "高木先生モード":
            if dinner_cal > 500:
                msg = f"Hello {user_id}さん！今日の残り枠は {int(dinner_cal)}kcal もありますね。This is perfect！素晴らしい投資効率（ROI）ですよ。夜は美味しいものを楽しんでくださいね！"
            elif dinner_cal > 0:
                msg = f"順調にコントロールできていますね。Excellent！{user_id}さんの毎日の努力は素晴らしい asset（資産）になりますよ。この調子で頑張りましょう！"
            else:
                msg = f"Oh... カロリーオーバーしてしまいましたね。でも大丈夫ですよ！Don't worry. 明日の朝からまたメタバースのように新しい気持ちで、ウェイトコントロールに投資していきましょう！"
        
        # 🌟 フォーマルモードの初期挨拶
        elif ai_persona == "フォーマル ":
            if dinner_cal > 0:
                msg = f"お疲れ様です、{user_id}さん。現在の残りカロリーは {int(dinner_cal)}kcal です。目標達成に向けて順調なペースを維持しています。この調子で管理を継続しましょう。"
            else:
                msg = f"カロリー制限値を超過しています。本日の摂取傾向を分析し、明日の食事メニューで調整を行うことを推奨します。"
                
        # 🌟 雷さんモードの初期挨拶（デフォルト）
        else:
            if dinner_cal > 500:
                msg = f"あったまいいね！今日はまだ {int(dinner_cal)}kcal も余裕があるね。美味しいもの探しに行こうよ！"
            elif dinner_cal > 0:
                msg = f"今のところ順調。夜は控えめな美食を楽しんで！"
            else:
                msg = f"ちょっと！もうカロリーオーバー！明日は食べすぎ禁止ね！"
                
        st.markdown(f'<div class="{bubble_class}">{msg}</div>', unsafe_allow_html=True)

# --- 8. 栄養摂取状況グラフの表示 ---
st.markdown("---")
st.subheader("📊 本日の栄養摂取状況とバランス")
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
    left_cal = max(0, int(dinner_cal))
    raw_labels = ['朝食', '昼食', '夕食', '残り枠']
    raw_sizes = [breakfast_cal, lunch_cal, dinner_selected_cal, left_cal]
    raw_colors = ['#ffa500', '#4CAF50', '#2196F3', '#e0e0e0']
    
    labels, sizes, colors = [], [], []
    for s, l, c in zip(raw_sizes, raw_labels, raw_colors):
        if s > 0:
            labels.append(l)
            sizes.append(s)
            colors.append(c)
            
    if len(sizes) == 0:
        sizes, labels, colors = [100], ['1日の目標枠'], ['#e0e0e0']
    
    import matplotlib.pyplot as plt
    import matplotlib.font_manager as fm
    
    font_path = download_font_cached()
    fp = fm.FontProperties(fname=font_path) if os.path.exists(font_path) else fm.FontProperties(family='sans-serif')
    
    fig, ax = plt.subplots(figsize=(4, 4))
    wedges, texts, autotexts = ax.pie(
        sizes, labels=labels, autopct=lambda p: '{:.1f}%'.format(p) if p > 0 else '',
        startangle=90, colors=colors,
        textprops={'color': "black", 'size': 9, 'fontproperties': fp}, 
        wedgeprops=dict(width=0.4, edgecolor='white')
    )
    plt.setp(autotexts, size=8, weight="bold", fontproperties=fp)
    ax.axis('equal')  
    st.pyplot(fig)

with st.sidebar:
    st.markdown("---")
    st.write("🎵 BGM")
    st.video("https://youtu.be/l7Tr8xb_tFk")  # ⭕ 完全なプレーンURLにする