import streamlit as st
from google import genai
from google.genai import types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import pandas as pd

if "password_correct" not in st.session_state:
    st.session_state["password_correct"] = False

if not st.session_state["password_correct"]:
    st.title("🔒 論文データベースへようこそ")
    password = st.text_input("パスワードを入力してください", type="password")
    if st.button("ログイン"):
        # 入力されたパスワードと金庫のパスワードを照合
        if password == st.secrets["APP_PASSWORD"]:
            st.session_state["password_correct"] = True
            st.rerun() # 画面をリロードしてアプリ本体を表示
        else:
            st.error("パスワードが違います。")
    st.stop() # ログイン成功するまでは、絶対にここから下のコードを実行させない

# --- 設定（クラウドのSecretsを使用） ---
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = "1m-v3jzwTXqKndPnqXWN4-jsx35ROBhW2XIOaZ_ckKFc" 

client = genai.Client(api_key=GEMINI_API_KEY)

# --- SLA向け プロンプト定義 ---
PROMPT = """
添付された論文PDFを詳細に解析し、第二言語習得（SLA）研究の専門的な観点から以下の項目を日本語で抽出し、指定のJSON形式で返してください。

【抽出項目】
- title: タイトル
- authors: 著者名
- year: 出版年
- publisher_journal: 出版社、または掲載ジャーナル/会議名
- doi_url: DOIまたは論文の公式URL（PDF内から抽出）
- background: 研究背景・問題設定
- previous_research: 先行研究とそこでの課題
- objective: 研究目的・仮説
- target_language: 学習対象言語
- participants: 被験者の属性（L1、熟達度、人数、学習環境など）
- theoretical_framework: 依拠している理論やモデル
- linguistic_feature: 焦点となっている言語項目や技能
- method: 研究・実験手法
- results: 研究結果
- future_challenges: 今後の課題
- pedagogical_implications: 教育的示唆
- conclusion: 結論
- keywords: フィルタリング用の重要キーワード5つ（カンマ区切り）
- importance: 論文の重要度（研究分野への影響力や革新性に基づき、「高」「中」「低」のいずれかで評価）
- memo: ユーザー用メモ（AIはここは常に空文字 "" を出力してください）

【出力形式】
JSONのみを出力してください。
"""

# --- UI部分 ---
st.title("📄 SLA論文要約＆保存アプリ")

# PDFアップロード機能
uploaded_file = st.file_uploader("論文のPDFをアップロードしてください", type="pdf")

if uploaded_file is not None:
    if st.button("要約を開始して保存"):
        with st.spinner("論文を解析中...（数十秒かかる場合があります）"):
            try:
                # 1. アップロードされたPDFをGeminiが読み込める形式に変換
                pdf_part = types.Part.from_bytes(
                    data=uploaded_file.getvalue(),
                    mime_type="application/pdf",
                )
                
                # 2. Geminiで要約生成
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[PROMPT, pdf_part],
                    config=types.GenerateContentConfig(
                        response_mime_type="application/json",
                    )
                )
                
                # 3. 結果をJSONとして読み込む
                summary_dict = json.loads(response.text)
                
                # 画面に要約結果を表示
                st.success("要約が完了しました！")
                st.json(summary_dict)
                
                # 4. スプレッドシートに保存
                with st.spinner("スプレッドシートに保存中..."):
                    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
                    credentials_dict = dict(st.secrets["gcp_service_account"])
                    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
                    client_gs = gspread.authorize(creds)
                    sheet = client_gs.open_by_key(SPREADSHEET_ID).sheet1
                    
                    # スプレッドシートの列の順序に合わせてリスト化
                    row_data = [
                        summary_dict.get("title", ""),
                        summary_dict.get("authors", ""),
                        summary_dict.get("year", ""),
                        summary_dict.get("publisher_journal", ""),
                        summary_dict.get("doi_url", ""),
                        summary_dict.get("background", ""),
                        summary_dict.get("previous_research", ""),
                        summary_dict.get("objective", ""),
                        summary_dict.get("target_language", ""),
                        summary_dict.get("participants", ""),
                        summary_dict.get("theoretical_framework", ""),
                        summary_dict.get("linguistic_feature", ""),
                        summary_dict.get("method", ""),
                        summary_dict.get("results", ""),
                        summary_dict.get("future_challenges", ""),
                        summary_dict.get("pedagogical_implications", ""),
                        summary_dict.get("conclusion", ""),
                        summary_dict.get("keywords", ""),
                        summary_dict.get("importance", "中"), # 19列目：重要度
                        summary_dict.get("memo", "")          # 20列目：メモ
                    ]
                    
                    sheet.append_row(row_data)
                    st.success("スプレッドシートへの保存も完了しました！")
                    
            except Exception as e:
                st.error(f"エラーが発生しました: {e}")


# --- ここから下が追加部分：データベース検索・閲覧機能 ---

st.markdown("---")
st.header("📚 論文データベース検索")

try:
    # スプレッドシートの操作クライアントを再設定（読み込み用）
    scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
    credentials_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client_gs = gspread.authorize(creds)
    sheet = client_gs.open_by_key(SPREADSHEET_ID).sheet1

    # スプレッドシートから全データを取得
    records = sheet.get_all_records()
    
    if records:
        df = pd.DataFrame(records)
        
        # 列が存在しない場合（過去のデータ用・見出し忘れ対策）
        if "重要度" not in df.columns:
            df["重要度"] = "未評価"
        if "メモ" not in df.columns:
            df["メモ"] = ""

        # 検索窓と並べ替えメニューを横に並べる
        col1, col2 = st.columns([2, 1])
        
        with col1:
            search_query = st.text_input("🔍 キーワードで検索（すべて対象）")

        with col2:
            sort_option = st.selectbox(
                "並べ替え",
                ["追加が新しい順", "追加が古い順", "出版年（新しい順）", "出版年（古い順）", "タイトル（A-Z）", "重要度（高い順）"]
            )

        # --- 1. フィルター処理 ---
        if search_query:
            mask = df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
            filtered_df = df[mask]
        else:
            filtered_df = df

        # --- 2. 並べ替え処理 ---
        if sort_option == "追加が新しい順":
            filtered_df = filtered_df.iloc[::-1]  # 行を逆順にする（最新が上）
        elif sort_option == "追加が古い順":
            pass # そのまま
        elif sort_option == "出版年（新しい順）":
            filtered_df = filtered_df.sort_values(by="出版年", ascending=False)
        elif sort_option == "出版年（古い順）":
            filtered_df = filtered_df.sort_values(by="出版年", ascending=True)
        elif sort_option == "タイトル（A-Z）":
            filtered_df = filtered_df.sort_values(by="タイトル", ascending=True)
        elif sort_option == "重要度（高い順）":
            # 重要度を数値化してソート
            importance_map = {"高": 3, "中": 2, "低": 1, "未評価": 0}
            filtered_df["スコア"] = filtered_df["重要度"].map(importance_map).fillna(0)
            filtered_df = filtered_df.sort_values(by="スコア", ascending=False)

        st.write(f"該当件数: **{len(filtered_df)}件**")

        # --- 3. カード形式での表示 ---
        for index, row in filtered_df.iterrows():
            with st.container(border=True):
                # タイトルと重要度を横に並べる
                t_col1, t_col2 = st.columns([5, 1])
                with t_col1:
                    st.markdown(f"#### {row.get('タイトル', 'No Title')}")
                with t_col2:
                    st.markdown(f"**🌟重要度:** {row.get('重要度', '未評価')}")
                
                # 基本情報
                st.write(f"**著者:** {row.get('著者名', '')} | **出版年:** {row.get('出版年', '')}")
                st.write(f"**対象言語:** {row.get('学習対象言語', '')} | **焦点:** {row.get('焦点となる言語項目', '')}")
                
                # メモが入力されている場合は目立たせて表示
                if row.get("メモ", ""):
                    st.info(f"📝 **あなたのメモ:** {row['メモ']}")

                # 折りたたみメニュー（要約詳細）
                with st.expander("📖 要約の詳細を見る（クリックして展開）"):
                    st.markdown("**【研究背景】**")
                    st.write(row.get('研究背景', ''))
                    
                    st.markdown("**【被験者属性】**")
                    st.write(row.get('被験者属性', ''))
                    
                    st.markdown("**【実験手法】**")
                    st.write(row.get('実験手法', ''))

                    st.markdown("**【研究目的】**")
                    st.write(row.get('研究目的', ''))
                    
                    st.markdown("**【研究結果】**")
                    st.write(row.get('研究結果', ''))
                    
                    st.markdown("**【結論】**")
                    st.write(row.get('結論', ''))
                    
                    st.markdown("**【教育的示唆】**")
                    st.write(row.get('教育的示唆', ''))
                    
                    doi_url = row.get('DOI/URL', '')
                    if doi_url and str(doi_url).strip() != '':
                        st.markdown(f"[🔗 論文リンク (DOI/URL)]({doi_url})")

                # --- 編集機能 ---
                with st.expander("✏️ この論文の「メモ」と「重要度」を編集する"):
                    e_col1, e_col2 = st.columns([1, 3])
                    
                    current_imp = row.get("重要度", "中")
                    if current_imp not in ["高", "中", "低"]:
                        current_imp = "中"
                        
                    with e_col1:
                        new_importance = st.selectbox(
                            "重要度を変更", 
                            ["高", "中", "低"], 
                            index=["高", "中", "低"].index(current_imp),
                            key=f"imp_{index}"
                        )
                    with e_col2:
                        new_memo = st.text_area(
                            "メモを記入・編集", 
                            value=str(row.get("メモ", "")),
                            key=f"memo_{index}",
                            height=68
                        )
                        
                    if st.button("更新を保存", key=f"save_{index}"):
                        with st.spinner("スプレッドシートを更新中..."):
                            # スプレッドシートの行番号は、DataFrameの元のindex + 2 (見出し行＋0始まりのズレ)
                            # 重要度はS列(19列目)、メモはT列(20列目)
                            sheet.update_cell(index + 2, 19, new_importance)
                            sheet.update_cell(index + 2, 20, new_memo)
                            st.success("更新しました！")
                            st.rerun() # 画面をリロードして最新の情報を表示
                        
    else:
        st.info("スプレッドシートにまだデータがありません。論文を要約して追加してください！")
        
except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")