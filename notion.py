import tkinter as tk
from tkinter import messagebox
import pandas as pd
import json
import os
import requests
from datetime import datetime, timezone, timedelta

def get_text_from_property(prop):
    """
    Notionのページプロパティオブジェクトからテキストコンテンツを抽出する。
    様々なプロパティタイプ（リッチテキスト、タイトル、日付、セレクトなど）に対応。
    
    Args:
        prop (dict): Notion APIのプロパティオブジェクト
    
    Returns:
        str: 抽出されたテキスト。該当データがない場合は空文字。
    """
    if not prop:
        return ""
    prop_type = prop.get('type')
    if prop_type == 'rich_text' and prop['rich_text']:
        return prop['rich_text'][0].get('plain_text', '')
    if prop_type == 'title' and prop['title']:
        return prop['title'][0].get('plain_text', '')
    if prop_type == 'date' and prop['date']:
        return prop['date'].get('start', '')
    if prop_type == 'select' and prop['select']:
        return prop['select'].get('name', '')
    if prop_type == 'multi_select' and prop['multi_select']:
        return ", ".join([item.get('name', '') for item in prop['multi_select']])
    return ""

def get_number_from_property(prop):
    """
    Notionのページプロパティオブジェクトから数値（Number）を抽出する。
    
    Args:
        prop (dict): Notion APIのプロパティオブジェクト
    
    Returns:
        int or float: 抽出された数値。該当データがない場合は0。
    """
    return prop.get('number', 0) if prop else 0

def get_status_from_property(prop):
    """
    Notionのページプロパティオブジェクトからステータス（Status）の名前を抽出する。
    
    Args:
        prop (dict): Notion APIのプロパティオブジェクト
    
    Returns:
        str: 抽出されたステータス名。該当データがない場合は空文字。
    """
    return prop.get('status', {}).get('name', '') if prop else ''

# --- メインアプリケーション ---

class WordQuizApp:
    """
    英単語クイズアプリケーションのメインクラス。
    GUIの構築、イベント処理、Notionとのデータ連携など、アプリ全体の制御を担う。
    """
    def __init__(self, master):
        """
        アプリケーションの初期化処理。
        ウィンドウの設定、設定ファイルの読み込み、Notion APIの準備、
        データ読み込み、UIの構築を行う。
        """
        self.master = master
        self.master.title("英単語学習アプリ (Notion版)")
        self.master.geometry("900x1000")

        # --- 設定とAPI準備 ---
        self.api_key = None
        self.database_id = None
        # 設定ファイル(config.json)を読み込む。失敗した場合はアプリを終了。
        if not self.load_config():
            self.master.destroy()
            return
            
        # Notion APIと通信するためのHTTPヘッダー
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json',
        }

        # --- 統計データ ---
        # 今日の学習セッションの統計情報（アプリ内で随時更新）
        self.todays_total_answered = 0
        self.todays_correct_count = 0

        # --- データ読み込みと初期化 ---
        self.df = pd.DataFrame() # 単語データを格納するPandas DataFrame
        self.load_data_from_notion() # Notionから全単語データを読み込む
        self._load_todays_stats_from_notion() # Notionデータに基づき今日の統計を初期化
        
        # --- 状態管理 ---
        self.current_index = 0 # 現在表示している単語のインデックス
        self.is_answer_visible = False # 解答が表示されているかどうかのフラグ

        # --- UI構築 ---
        self.create_widgets() # GUIウィジェットを作成し配置する
        self.update_all_stats_displays() # 全ての統計表示を最新の情報に更新する

    def load_config(self):
        """
        設定ファイル '参照データ/config.json' を読み込む。
        ファイルが存在しない場合は、デフォルトの設定でファイルを自動生成する。
        APIキーやデータベースIDが設定されていない場合はエラーを表示する。
        
        Returns:
            bool: 設定の読み込みに成功したかどうか
        """
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_dir = os.path.join(script_dir, '参照データ')
        config_path = os.path.join(config_dir, 'config.json')

        try:
            # 設定ファイルを開いてJSONとして読み込む
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except FileNotFoundError:
            # ファイルが見つからない場合、ディレクトリを作成し、デフォルト設定でファイルを生成
            os.makedirs(config_dir, exist_ok=True)
            default_config = {
                "NOTION_API_KEY": "",
                "DATABASE_ID": "",
                "QUESTION_MODE": "未"
            }
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, indent=4, ensure_ascii=False)
            
            # ユーザーに設定ファイルの編集を促すメッセージを表示
            messagebox.showinfo(
                "設定ファイル生成",
                f"設定ファイルが見つからなかったため、以下に作成しました:\n"
                f"{config_path}\n\n"
                f"このファイルにAPIキーとデータベースIDを記入してから、アプリを再起動してください。"
            )
            return False # アプリを続行させないためにFalseを返す
        except json.JSONDecodeError as e:
            # JSONの形式が正しくない場合のエラー処理
            messagebox.showerror("設定エラー", f"config.jsonの形式が正しくありません。\n{e}")
            return False
        except Exception as e:
            # その他の予期せぬエラー処理
            messagebox.showerror("エラー", f"設定ファイルの読み込み中にエラーが発生しました: {e}")
            return False

        # 読み込んだ設定をインスタンス変数に格納
        self.api_key = config.get("NOTION_API_KEY")
        self.database_id = config.get("DATABASE_ID")
        self.question_mode = config.get("QUESTION_MODE", "未")

        # APIキーとデータベースIDが空でないかチェック
        if not self.api_key or not self.database_id:
            messagebox.showerror(
                "設定エラー",
                f"config.jsonにNOTION_API_KEYとDATABASE_IDが設定されていません。\n"
                f"以下を編集してください:\n{config_path}"
            )
            return False
        return True

    def load_data_from_notion(self):
        """
        Notionデータベースから全ての単語データを取得し、DataFrameに格納する。
        - ページネーションに対応し、100件以上のデータも全て取得する。
        - ターミナルに進捗状況を表示する。
        - 取得後、設定されたQUESTION_MODEに基づき単語の並び替えや絞り込みを行う。
        """
        print("---"" データ読み込み開始 ---")
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        # last_edited_timeでソートすることで、最近学習したものが後になるようにする
        payload = {"sorts": [{"timestamp": "last_edited_time", "direction": "ascending"}]}
        all_results = []
        page_count = 1

        # --- 1. データ取得ステージ (ページネーション対応) ---
        while True:
            # ターミナルに進捗を表示（同じ行を更新）
            print(f"\rNotionからデータを取得中... (ページ {page_count})", end='')
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                response.raise_for_status() # HTTPエラーがあれば例外を発生
                response_data = response.json()
            except requests.exceptions.RequestException as e:
                print("\nエラー: Notionからのデータ取得に失敗しました。")
                messagebox.showerror("APIエラー", f"Notionからのデータ取得に失敗しました.\n{e}")
                self.df = pd.DataFrame([]) # エラー時は空のDataFrameをセット
                return

            # 取得した結果をリストに追加
            all_results.extend(response_data.get('results', []))

            # まだ続きのページがあるかチェック
            if response_data.get('has_more'):
                page_count += 1
                # 次のページを取得するためのカーソルを設定
                payload['start_cursor'] = response_data.get('next_cursor')
            else:
                # 全てのページを取得したらループを抜ける
                break
        
        total_words = len(all_results)
        # 取得完了メッセージ（行頭の\rで進捗表示を上書きし、末尾のスペースで前の表示を消去）
        print(f"\rNotionからデータを取得完了。 ({total_words}件)      ")

        # --- 2. データ解析ステージ ---
        word_list = []
        if total_words > 0:
            print("データを解析中...")
            # 取得した全ページデータをループ処理
            for i, page in enumerate(all_results):
                props = page.get('properties', {})
                # 各プロパティをヘルパー関数で抽出し、辞書に格納
                word_data = {
                    'page_id': page.get('id'),
                    '英語': get_text_from_property(props.get('英単語')),
                    '日本語': get_text_from_property(props.get('日本語')),
                    'メモ': get_text_from_property(props.get('メモ')),
                    'mistake_count': get_number_from_property(props.get('間違えた回数')),
                    '正誤': get_status_from_property(props.get('正誤')),
                    '品詞': get_text_from_property(props.get('品詞')),
                    'やった日': get_text_from_property(props.get('やった日'))
                }
                
                # 例文も同様に抽出
                for j in range(1, 5):
                    word_data[f'例文英語{j}'] = get_text_from_property(props.get(f'例文英語{j}'))
                    word_data[f'例文日本語{j}'] = get_text_from_property(props.get(f'例文日本語{j}'))
                word_list.append(word_data)

                # 進捗バーをターミナルに表示
                percent = (i + 1) * 100 / total_words
                bar_length = 40
                filled_len = int(bar_length * (i + 1) // total_words)
                bar = '█' * filled_len + '-' * (bar_length - filled_len)
                print(f'\r  |{bar}| {percent:.1f}% ({i+1}/{total_words})', end='')
            
            print() # プログレスバーの後に改行
            print("データ解析完了。")

        print("--- データ読み込み完了 ---")
        
        # 解析した単語リストをPandas DataFrameに変換
        self.df = pd.DataFrame(word_list)
        
        # --- 3. 出題順の整理ステージ ---
        if self.df.empty:
            messagebox.showinfo("情報", "Notionデータベースに単語が見つかりませんでした。")
        else:
            # config.jsonのQUESTION_MODEに応じて、出題順を並べ替えたり絞り込んだりする
            # "未": 未学習の単語を優先的に出題
            if self.question_mode == "未":
                unanswered_df = self.df[self.df['正誤'].isin(['', '未'])]
                answered_df = self.df[~self.df['正誤'].isin(['', '未'])]
                self.df = pd.concat([unanswered_df, answered_df]).reset_index(drop=True)
            # "誤": 間違えた単語を優先的に出題
            elif self.question_mode == "誤":
                incorrect_df = self.df[self.df['正誤'] == '誤']
                other_df = self.df[self.df['正誤'] != '誤']
                self.df = pd.concat([incorrect_df, other_df]).reset_index(drop=True)
            # "正_only": 正解した単語のみ出題
            elif self.question_mode == "正_only":
                self.df = self.df[self.df['正誤'] == '正'].reset_index(drop=True)
            # "誤_only": 間違えた単語のみ出題
            elif self.question_mode == "誤_only":
                self.df = self.df[self.df['正誤'] == '誤'].reset_index(drop=True)
            # "未_only": 未学習の単語のみ出題
            elif self.question_mode == "未_only":
                self.df = self.df[self.df['正誤'].isin(['', '未'])].reset_index(drop=True)

            # 例文の列名をリストとして保持（後で使いやすくするため）
            self.sentence_english_cols = [f'例文英語{i}' for i in range(1, 5)]
            self.sentence_japanese_cols = [f'例文日本語{i}' for i in range(1, 5)]

    def create_widgets(self):
        """
        アプリケーションのGUIウィジェット（ボタン、ラベル、テキストボックス等）を作成し、
        ウィンドウ上に配置する。
        """
        # --- メインレイアウト ---
        main_frame = tk.Frame(self.master, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = tk.Frame(main_frame)
        top_frame.pack(fill=tk.BOTH, expand=True)

        # --- 単語表示エリア ---
        self.word_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.word_frame.pack(fill=tk.X, pady=5)
        self.create_label(self.word_frame, "単語", font_size=16)
        self.word_content = self.create_content(self.word_frame, "", font_size=24)

        # --- 例文表示エリア ---
        self.sentence_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.sentence_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.create_label(self.sentence_frame, "例文", font_size=16)
        self.sentence_labels = [self.create_content(self.sentence_frame, "", font_size=12) for _ in range(4)]

        # --- メモ表示・編集エリア ---
        self.memo_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.memo_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.create_label(self.memo_frame, "メモ", font_size=16)
        self.memo_content = tk.Text(self.memo_frame, font=("Arial", 12), height=4, wrap=tk.WORD)
        self.memo_content.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)

        # --- 下部エリア（統計と操作ボタン） ---
        bottom_frame = tk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=10)
        bottom_frame.grid_columnconfigure(0, weight=3) # 統計エリアを広く
        bottom_frame.grid_columnconfigure(1, weight=2) # ボタンエリア

        # --- 統計表示エリア ---
        stats_area_frame = tk.Frame(bottom_frame)
        stats_area_frame.grid(row=0, column=0, sticky="nsew", padx=5)

        # 現在の問題に関する統計
        q_stats_frame = tk.Frame(stats_area_frame, relief=tk.RIDGE, borderwidth=2)
        q_stats_frame.pack(fill=tk.X, pady=2)
        self.create_label(q_stats_frame, "問題の統計", font_size=12)
        self.per_question_stats_content = self.create_content(q_stats_frame, "", font_size=10, justify="left")

        # 今日の学習セッションの統計
        today_stats_frame = tk.Frame(stats_area_frame, relief=tk.RIDGE, borderwidth=2)
        today_stats_frame.pack(fill=tk.X, pady=2)
        self.create_label(today_stats_frame, "今日の統計", font_size=12)
        self.today_stats_content = self.create_content(today_stats_frame, "", font_size=10, justify="left")

        # 全体の統計
        overall_stats_frame = tk.Frame(stats_area_frame, relief=tk.RIDGE, borderwidth=2)
        overall_stats_frame.pack(fill=tk.X, pady=2)
        self.create_label(overall_stats_frame, "全体の統計", font_size=12)
        self.overall_stats_content = self.create_content(overall_stats_frame, "", font_size=10, justify="left")

        # --- 操作ボタンエリア ---
        button_frame = tk.Frame(bottom_frame, relief=tk.RIDGE, borderwidth=2)
        button_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        self.create_label(button_frame, "操作", font_size=14)
        
        self.toggle_button = tk.Button(button_frame, text="回答を表示", command=self.toggle_answer, height=2)
        self.toggle_button.pack(fill=tk.X, padx=10, pady=5)

        self.correct_button = tk.Button(button_frame, text="正解", command=lambda: self.record_and_next(correct=True), height=2, bg="lightgreen")
        self.correct_button.pack(fill=tk.X, padx=10, pady=5)
        
        self.incorrect_button = tk.Button(button_frame, text="不正解", command=lambda: self.record_and_next(correct=False), height=2, bg="lightcoral")
        self.incorrect_button.pack(fill=tk.X, padx=10, pady=5)

        self.save_memo_button = tk.Button(button_frame, text="メモを保存", command=self.save_memo, height=2)
        self.save_memo_button.pack(fill=tk.X, padx=10, pady=5)

    def save_memo(self):
        """
        メモ編集エリアの内容をNotionに保存する。
        """
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            return

        word_data = self.df.iloc[self.current_index]
        page_id = word_data['page_id']
        # テキストウィジェットから現在のテキストを取得
        memo_text = self.memo_content.get("1.0", tk.END).strip()

        # Notion APIに送信するためのデータを作成
        properties_to_update = {
            'メモ': {
                'rich_text': [{'text': {'content': memo_text}}]
            }
        }

        # Notionページを更新し、成功したらローカルのデータも更新
        if self.update_notion_page(page_id, properties_to_update):
            self.df.loc[self.current_index, 'メモ'] = memo_text
            messagebox.showinfo("成功", "メモを保存しました。")

    def on_resize(self, event=None):
        """
        (現在未使用) ウィンドウサイズが変更されたときにラベルの折り返し幅を調整するための関数。
        """
        try:
            # ウィジェットの幅に応じてテキストの折り返し長を調整
            word_wrap_length = self.word_frame.winfo_width() - 20
            if word_wrap_length > 1:
                self.word_content.config(wraplength=word_wrap_length)

            sentence_wrap_length = self.sentence_frame.winfo_width() - 20
            if sentence_wrap_length > 1:
                for label in self.sentence_labels:
                    label.config(wraplength=sentence_wrap_length)
        except (AttributeError, tk.TclError):
            # ウィジェットが存在しない場合のエラーを無視
            pass

    def create_label(self, parent, text, font_size=14):
        """UI作成のヘルパー: 指定された親ウィジェットに太字のラベルを作成する。"""
        label = tk.Label(parent, text=text, font=("Arial", font_size, "bold"))
        label.pack(pady=(5, 0))
        return label

    def create_content(self, parent, text, font_size=12, justify="center"):
        """UI作成のヘルパー: 指定された親ウィジェットにコンテンツ用のラベルを作成する。"""
        content = tk.Label(parent, text=text, font=("Arial", font_size), justify=justify)
        content.pack(pady=5, padx=10, fill=tk.X)
        return content

    def update_all_stats_displays(self):
        """全ての統計表示エリアを一度に更新する。"""
        self.update_per_question_stats_display()
        self.update_today_stats_display()
        self.update_overall_stats_display()

    def update_per_question_stats_display(self):
        """「問題の統計」エリアを現在の単語の情報で更新する。"""
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.per_question_stats_content.config(text="")
            return
        word_data = self.df.iloc[self.current_index]
        
        # 日付文字列を安全にフォーマットする
        date_str = word_data.get('やった日')
        if date_str and isinstance(date_str, str):
            try:
                # ISO形式の文字列をdatetimeオブジェクトに変換
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_str_formatted = date_obj.strftime('%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                date_str_formatted = 'N/A'
        else:
            date_str_formatted = 'N/A'
        
        # 表示するテキストを作成
        stats_text = (
            f"品詞: {word_data.get('品詞') or 'N/A'}\n"
            f"正誤ステータス: {word_data.get('正誤') or 'N/A'}\n"
            f"間違えた回数: {word_data.get('mistake_count') or 0}\n"
            f"やった日: {date_str_formatted}"
        )
        self.per_question_stats_content.config(text=stats_text)

    def update_today_stats_display(self):
        """「今日の統計」エリアを更新する。"""
        total = self.todays_total_answered
        correct = self.todays_correct_count
        incorrect = total - correct
        correct_rate = (correct / total * 100) if total > 0 else 0
        incorrect_rate = (incorrect / total * 100) if total > 0 else 0
        stats_text = (
            f"解答数: {total}\n"
            f"正解: {correct} ({correct_rate:.1f}%)\n"
            f"誤答: {incorrect} ({incorrect_rate:.1f}%)"
        )
        self.today_stats_content.config(text=stats_text)

    def update_overall_stats_display(self):
        """「全体の統計」エリアを更新する。"""
        if self.df.empty:
            self.overall_stats_content.config(text="")
            return
        total = len(self.df)
        correct = len(self.df[self.df['正誤'] == '正'])
        incorrect = len(self.df[self.df['正誤'] == '誤'])
        correct_rate = (correct / total * 100) if total > 0 else 0
        incorrect_rate = (incorrect / total * 100) if total > 0 else 0
        stats_text = (
            f"総単語数: {total}\n"
            f"正解済み: {correct} ({correct_rate:.1f}%)\n"
            f"誤答あり: {incorrect} ({incorrect_rate:.1f}%)"
        )
        self.overall_stats_content.config(text=stats_text)

    def _load_todays_stats_from_notion(self):
        """
        アプリ起動時に、Notionのデータ全体から「今日の統計」を計算して初期化する。
        """
        if self.df.empty:
            self.todays_total_answered = 0
            self.todays_correct_count = 0
            return

        # タイムゾーンを考慮して「今日」の日付を定義 (JST基準)
        now_utc = datetime.now(timezone.utc)
        now_jst = now_utc + timedelta(hours=9)
        today_jst = now_jst.date()

        # Notionの日付データ(UTC)をJSTの日付に変換して比較
        self.df['やった日_dt_utc'] = pd.to_datetime(self.df['やった日'], errors='coerce', utc=True)
        self.df['やった日_dt_jst'] = self.df['やった日_dt_utc'] + pd.Timedelta(hours=9)
        self.df['やった日_date_jst'] = self.df['やった日_dt_jst'].dt.date
        
        # 「やった日」が今日で、かつ解答済みの単語をフィルタリング
        todays_entries = self.df[
            (self.df['やった日_date_jst'] == today_jst) &
            (self.df['正誤'].isin(['正', '誤']))
        ]
        
        # 統計カウンターを初期化
        self.todays_total_answered = len(todays_entries)
        self.todays_correct_count = len(todays_entries[todays_entries['正誤'] == '正'])
        
        # 一時的に使用した列を削除
        self.df = self.df.drop(columns=['やった日_dt_utc', 'やった日_dt_jst', 'やった日_date_jst'])

    def show_word(self):
        """
        現在のインデックスに基づき、新しい単語と関連情報をUIに表示する。
        """
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.word_content.config(text="単語がありません。")
            for label in self.sentence_labels:
                label.config(text="")
            return

        word_data = self.df.iloc[self.current_index]
        self.is_answer_visible = False # まずは問題（英語）を表示
        
        # 各UIコンポーネントにテキストを設定
        self.word_content.config(text=word_data.get('英語', ''))
        self.memo_content.delete("1.0", tk.END)
        self.memo_content.insert("1.0", word_data.get('メモ', ''))
        for i, col_name in enumerate(self.sentence_english_cols):
            self.sentence_labels[i].config(text=word_data.get(col_name, ''))
        
        self.toggle_button.config(text="回答を表示")
        self.update_per_question_stats_display() # 問題ごとの統計を更新

    def toggle_answer(self):
        """
        「回答を表示」/「問題を表示」ボタンの処理。
        英語表示と日本語表示を切り替える。
        """
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            return
        word_data = self.df.iloc[self.current_index]
        
        if self.is_answer_visible:
            # 現在、回答が表示されている場合 -> 問題（英語）表示に戻す
            self.word_content.config(text=word_data.get('英語', ''))
            for i, col_name in enumerate(self.sentence_english_cols):
                self.sentence_labels[i].config(text=word_data.get(col_name, ''))
            self.toggle_button.config(text="回答を表示")
            self.is_answer_visible = False
        else:
            # 現在、問題が表示されている場合 -> 回答（日本語）表示に切り替え
            self.word_content.config(text=word_data.get('日本語', ''))
            for i, col_name in enumerate(self.sentence_japanese_cols):
                self.sentence_labels[i].config(text=word_data.get(col_name, ''))
            self.toggle_button.config(text="問題を表示")
            self.is_answer_visible = True

    def record_and_next(self, correct):
        """
        正解・不正解ボタンが押されたときの処理。
        - Notionページのプロパティを更新する。
        - 今日の統計を更新する。
        - ローカルのDataFrameを更新する。
        - 次の単語を表示する。
        """
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            return

        word_data = self.df.iloc[self.current_index]
        page_id = word_data['page_id']
        properties_to_update = {}
        
        # --- 統計とローカルデータの更新 ---
        self.todays_total_answered += 1
        if correct:
            # 正解の場合
            self.todays_correct_count += 1
            new_status = "正"
            self.df.loc[self.current_index, '正誤'] = new_status
        else:
            # 不正解の場合
            current_mistakes = word_data.get('mistake_count')
            if pd.isna(current_mistakes):
                current_mistakes = 0
            new_mistake_count = int(current_mistakes) + 1
            new_status = "誤"
            # Notionに送信するデータに「間違えた回数」を追加
            properties_to_update['間違えた回数'] = {'number': new_mistake_count}
            # ローカルのDataFrameも更新
            self.df.loc[self.current_index, 'mistake_count'] = new_mistake_count
            self.df.loc[self.current_index, '正誤'] = new_status

        # --- Notion更新データの準備 ---
        properties_to_update['正誤'] = {'status': {'name': new_status}}
        current_time_iso = datetime.now(timezone.utc).isoformat()
        properties_to_update['やった日'] = {'date': {'start': current_time_iso}}
        
        # --- Notion API呼び出し ---
        if not self.update_notion_page(page_id, properties_to_update):
            # 更新に失敗した場合、加算した統計を元に戻す
            self.todays_total_answered -= 1
            if correct: self.todays_correct_count -= 1
            return
        
        # ローカルの「やった日」も更新
        self.df.loc[self.df['page_id'] == page_id, 'やった日'] = current_time_iso
        
        # --- UI更新と次の単語へ ---
        self.update_today_stats_display()
        self.update_overall_stats_display()

        if self.current_index < len(self.df) - 1:
            self.current_index += 1
            self.show_word()
        else:
            # 全ての単語が終わったらメッセージを表示して最初に戻る
            messagebox.showinfo("完了", "すべての単語の確認が終わりました。")
            self.current_index = 0
            self.show_word()

    def update_notion_page(self, page_id, properties):
        """
        指定されたNotionページのプロパティを更新する汎用関数。
        
        Args:
            page_id (str): 更新するページのID
            properties (dict): 更新するプロパティの内容
        
        Returns:
            bool: 更新に成功したかどうか
        """
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {'properties': properties}
        try:
            response = requests.patch(url, headers=self.headers, json=payload)
            response.raise_for_status() # エラーがあれば例外を発生
            return True
        except requests.exceptions.RequestException as e:
            messagebox.showerror("更新エラー", f"Notionページの更新に失敗しました.\n{e}")
            return False

# --- アプリケーションの実行 ---
if __name__ == "__main__":
    root = tk.Tk()
    app = WordQuizApp(root)
    root.mainloop()