import streamlit as st

def apply_custom_css():
    st.markdown("""
    <style>
        /* 全体：読みやすい日本語向けフォント、背景は明るい白 */
        html, body, [data-testid="stMarkdownContainer"], .stApp {
            font-family: "Noto Sans JP", "Hiragino Kaku Gothic ProN", Meiryo, system-ui, -apple-system, "Segoe UI", Roboto, sans-serif !important;
            background-color: #ffffff !important;
            color: #222222 !important;
            font-size: 16px !important;
            line-height: 1.6 !important;
        }
/* 💬 喋っている風の吹き出しスタイル */
        .chat-bubble {
            background-color: #f1f5f9 !important; /* 薄いグレー */
            border-radius: 16px !important;
            padding: 12px 16px !important;
            margin-top: 5px !important;
            display: inline-block !important;
            max-width: 85% !important;
            color: #222222 !important;
            position: relative !important;
            box-shadow: 0 2px 8px rgba(0, 0, 0, 0.05) !important;
        }

        /* 高木先生モードの時は少しインテリジェンスな薄い青に */
        .takagi-bubble {
            background-color: #e0f2fe !important; /* 薄い青 */
            border-left: 4px solid #0284c7 !important;
        }

        /* 雷さんの時は元気な薄い黄色に */
        .rai-bubble {
            background-color: #fef9c3 !important; /* 薄い黄 */
            border-left: 4px solid #eab308 !important;
        }
        /* サイドバー：シンプルで情報が見やすい */
        [data-testid="stSidebar"] {
            background-color: #f8f9fa !important;
            border-right: 1px solid #e6e6e6 !important;
            padding: 16px !important;
        }

        /* 見出しをはっきりさせる（視認性向上） */
        h1, h2, h3 {
            color: #111827 !important;
            font-weight: 700 !important;
            letter-spacing: 0.2px !important;
        }

        /* カード／コンテナ：余白を広めに、角丸、薄い影 */
        .stContainer, div[data-testid="stForm"], div[data-testid="stMetric"] {
            background: #ffffff !important;
            border-radius: 12px !important;
            padding: 14px !important;
            box-shadow: 0 6px 18px rgba(15, 23, 42, 0.04) !important;
            border: 1px solid rgba(15, 23, 42, 0.04) !important;
        }

        /* 入力欄：大きくて触りやすく */
        .stTextInput input, .stNumberInput input, textarea, .stSelectbox select {
            font-size: 16px !important;
            padding: 10px 12px !important;
            border-radius: 10px !important;
            border: 1px solid #e5e7eb !important;
            background: #ffffff !important;
            color: #111827 !important;
        }

        /* コンビニらしいアクセント色（オレンジ）をブランドカラーに */
        :root {
            --cstore-accent: #ff6f00;
            --cstore-accent-2: #ffc107;
        }

        /* ボタン：十分なサイズ・コントラスト、文字は折り返し可能 */
        .stButton>button {
            display: inline-flex !important;
            align-items: center !important;
            justify-content: center !important;
            padding: 12px 28px !important;
            border-radius: 12px !important;
            border: none !important;
            background: linear-gradient(180deg, var(--cstore-accent) 0%, #ff8a1f 100%) !important;
            color: #ffffff !important;
            font-weight: 700 !important;
            font-size: 16px !important;
            box-shadow: 0 6px 12px rgba(0,0,0,0.08) !important;
            transition: transform 0.12s ease, box-shadow 0.12s ease !important;
            white-space: normal !important; /* 長いラベルは改行して表示 */
            word-break: break-word !important;
        }

        /* 全幅ボタンの扱い */
        .stButton>button[data-testid="baseButton-secondaryFormSubmit"],
        .stButton>button[data-testid="baseButton-secondary"] {
            width: 100% !important;
            text-align: center !important;
        }

        .stButton>button:hover {
            transform: translateY(-2px) !important;
            box-shadow: 0 10px 24px rgba(0,0,0,0.12) !important;
        }

        /* メニューカード風のアイテム表示（コンビニの陳列風） */
        .menu-card {
            display: inline-block !important;
            width: calc(33.333% - 12px) !important;
            margin: 6px !important;
            vertical-align: top !important;
            background: linear-gradient(180deg, #ffffff 0%, #fffbf2 100%) !important;
            border-radius: 10px !important;
            padding: 12px !important;
            box-shadow: 0 6px 16px rgba(15,23,42,0.04) !important;
            border-left: 6px solid var(--cstore-accent-2) !important;
        }

        /* st.metric の強調表示を読みやすく */
        [data-testid="stMetricValue"] {
            font-size: 2rem !important;
            font-weight: 800 !important;
            color: #0f172a !important;
        }

        [data-testid="stMetricLabel"] {
            font-weight: 600 !important;
            color: #6b7280 !important;
        }

        /* 小さいテキストやフッターの視認性を確保 */
        .css-1lcbmhc, .css-1avcm0n {
            color: #374151 !important;
            font-size: 14px !important;
        }

        /* レスポンシブ調整 */
        @media (max-width: 900px) {
            .menu-card { width: calc(50% - 12px) !important; }
        }
        @media (max-width: 520px) {
            .menu-card { width: 100% !important; }
            .stButton>button { padding: 12px 18px !important; }
        }
    </style>
    """, unsafe_allow_html=True)