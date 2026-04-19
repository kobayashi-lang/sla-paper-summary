import streamlit as st
from google import genai
from google.genai import types
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import pandas as pd

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
                        summary_dict.get("keywords", "")
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
    # ★ここを修正しました（上と同じようにsecretsから読み込む）
    credentials_dict = dict(st.secrets["gcp_service_account"])
    creds = ServiceAccountCredentials.from_json_keyfile_dict(credentials_dict, scope)
    client_gs = gspread.authorize(creds)
    sheet = client_gs.open_by_key(SPREADSHEET_ID).sheet1

    # スプレッドシートから全データを取得
    records = sheet.get_all_records()
    
    if records:
        df = pd.DataFrame(records)

        # --- 1. フィルター機能（キーワード検索） ---
        search_query = st.text_input("🔍 キーワードで検索（タイトル、著者、要約内容などすべて対象）")

        if search_query:
            # 全列を対象にキーワードを含む行を抽出（大文字小文字を区別しない）
            mask = df.apply(lambda row: row.astype(str).str.contains(search_query, case=False).any(), axis=1)
            filtered_df = df[mask]
        else:
            filtered_df = df

        st.write(f"該当件数: **{len(filtered_df)}件**")

        # --- 2. カード形式での表示（Streamlit標準機能による完全対応版） ---
        for index, row in filtered_df.iterrows():
            # 枠線付きのコンテナ（カード）を作成。自動でダーク/ライトモードに対応します。
            with st.container(border=True):
                # タイトル
                st.markdown(f"#### {row.get('タイトル', 'No Title')}")
                
                # 基本情報
                st.write(f"**著者:** {row.get('著者名', '')} | **出版年:** {row.get('出版年', '')}")
                st.write(f"**対象言語:** {row.get('学習対象言語', '')} | **焦点:** {row.get('焦点となる言語項目', '')}")
                
                # 折りたたみメニュー（標準のexpanderを使用）
                with st.expander("📖 要約の詳細を見る（クリックして展開）"):
                    
                    # --- 追加したSLA特化の項目 ---
                    st.markdown("**【研究背景】**")
                    st.write(row.get('研究背景', ''))
                    
                    st.markdown("**【被験者属性】**")
                    st.write(row.get('被験者属性', ''))
                    
                    st.markdown("**【実験手法】**")
                    st.write(row.get('実験手法', ''))
                    # ----------------------------

                    st.markdown("**【研究目的】**")
                    st.write(row.get('研究目的', ''))
                    
                    st.markdown("**【研究結果】**")
                    st.write(row.get('研究結果', ''))
                    
                    st.markdown("**【結論】**")
                    st.write(row.get('結論', ''))
                    
                    st.markdown("**【教育的示唆】**")
                    st.write(row.get('教育的示唆', ''))
                    
                    # URLがあればリンク化する
                    doi_url = row.get('DOI/URL', '')
                    if doi_url and str(doi_url).strip() != '':
                        st.markdown(f"[🔗 論文リンク (DOI/URL)]({doi_url})")
                        
    else:
        st.info("スプレッドシートにまだデータがありません。論文を要約して追加してください！")
        
except Exception as e:
    st.error(f"データの読み込み中にエラーが発生しました: {e}")