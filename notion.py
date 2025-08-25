import tkinter as tk
from tkinter import ttk, messagebox
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
    """
    def __init__(self, master):
        self.master = master
        self.master.title("英単語学習アプリ (Notion版)")
        self.master.geometry("900x1200")

        # --- 設定用変数 ---
        self.api_key_var = tk.StringVar()
        self.db_id_var = tk.StringVar()
        self.mode_unanswered_var = tk.BooleanVar()
        self.mode_incorrect_var = tk.BooleanVar()
        self.mode_correct_var = tk.BooleanVar()

        # --- 設定とAPI準備 ---
        self.question_mode = []
        self.headers = {}
        self.load_config()
        self.update_headers()

        # --- データ管理 ---
        self.master_df = pd.DataFrame() # Notionから取得した全データを保持
        self.df = pd.DataFrame()        # フィルタリング後のクイズ用データ

        # --- 統計データ ---
        self.todays_total_answered = 0
        self.todays_correct_count = 0

        # --- UI構築と初回データ読み込み ---
        self.create_widgets()
        if self.api_key_var.get() and self.db_id_var.get():
            self.load_data_from_notion() # master_dfを埋める
            self.refilter_and_display_words() # master_dfからdfを作成して表示
        else:
            messagebox.showwarning("設定不足", "APIキーまたはデータベースIDが設定されていません。\n「設定」タブで設定を完了してください。")

        # --- 状態管理 ---
        self.current_index = 0
        self.is_answer_visible = False

    def update_headers(self):
        self.headers = {
            'Authorization': f'Bearer {self.api_key_var.get()}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json',
        }

    def load_config(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        self.config_dir = os.path.join(script_dir, '参照データ')
        self.config_path = os.path.join(self.config_dir, 'config.json')
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            config = {}
        self.api_key_var.set(config.get("NOTION_API_KEY", ""))
        self.db_id_var.set(config.get("DATABASE_ID", ""))
        self.question_mode = config.get("QUESTION_MODE", ["未"])
        self.mode_unanswered_var.set("未" in self.question_mode)
        self.mode_incorrect_var.set("誤" in self.question_mode)
        self.mode_correct_var.set("正" in self.question_mode)

    def save_settings_and_refilter(self):
        if not self.api_key_var.get() or not self.db_id_var.get():
            messagebox.showerror("エラー", "APIキーとデータベースIDは必須です。")
            return

        new_modes = []
        if self.mode_unanswered_var.get(): new_modes.append("未")
        if self.mode_incorrect_var.get(): new_modes.append("誤")
        if self.mode_correct_var.get(): new_modes.append("正")

        if not new_modes:
            print("エラー", "少なくとも1つの出題モードを選択してください。")
            return

        os.makedirs(self.config_dir, exist_ok=True)
        config = {
            "NOTION_API_KEY": self.api_key_var.get(),
            "DATABASE_ID": self.db_id_var.get(),
            "QUESTION_MODE": new_modes
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        print("成功", "設定を保存しました。出題内容を更新します。")
        self.question_mode = new_modes
        
        # APIキーが変更された可能性があるためヘッダーを更新
        self.update_headers()

        # master_dfが空（初回起動時など）ならNotionから読み込み、そうでなければメモリから再フィルター
        if self.master_df.empty:
             self.load_data_from_notion() # master_dfを埋める
        
        self.refilter_and_display_words()

    def refilter_and_display_words(self):
        """メモリ上のマスターデータから単語をフィルタリングし、UIを更新する"""
        if self.master_df.empty:
            print("マスターデータが空のため、フィルタリングをスキップします。")
            self.df = pd.DataFrame([])
        else:
            # --- フィルタリングステージ ---
            source_df = self.master_df.copy()
            selected_statuses = []
            if "未" in self.question_mode:
                selected_statuses.extend(['', '未'])
            if "誤" in self.question_mode:
                selected_statuses.append('誤')
            if "正" in self.question_mode:
                selected_statuses.append('正')

            if selected_statuses:
                self.df = source_df[source_df['正誤'].isin(selected_statuses)].reset_index(drop=True)
            else:
                self.df = pd.DataFrame([])

        if self.df.empty:
            messagebox.showinfo("情報", "選択されたモードに該当する単語がありませんでした。")

        # --- UIリセット ---
        self._load_todays_stats_from_notion()
        self.current_index = 0
        self.update_all_stats_displays()
        self.show_word()

    def create_widgets(self):
        main_frame = tk.Frame(self.master, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        tab_control = ttk.Notebook(main_frame)
        quiz_tab = ttk.Frame(tab_control)
        settings_tab = ttk.Frame(tab_control)
        tab_control.add(quiz_tab, text='クイズ')
        tab_control.add(settings_tab, text='設定')
        tab_control.pack(expand=1, fill="both")
        self.create_quiz_tab(quiz_tab)
        self.create_settings_tab(settings_tab)

    def create_quiz_tab(self, parent_tab):
        top_frame = tk.Frame(parent_tab)
        top_frame.pack(fill=tk.BOTH, expand=True)
        self.word_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.word_frame.pack(fill=tk.X, pady=5)
        self.create_label(self.word_frame, "単語", font_size=16)
        self.word_content = self.create_content(self.word_frame, "", font_size=24)
        self.sentence_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.sentence_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.create_label(self.sentence_frame, "例文", font_size=16)
        self.sentence_labels = [self.create_content(self.sentence_frame, "", font_size=12) for _ in range(4)]
        self.memo_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.memo_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.create_label(self.memo_frame, "メモ", font_size=16)
        self.memo_content = tk.Text(self.memo_frame, font=("Arial", 12), height=4, wrap=tk.WORD)
        self.memo_content.pack(pady=5, padx=10, fill=tk.BOTH, expand=True)
        bottom_frame = tk.Frame(parent_tab)
        bottom_frame.pack(fill=tk.X, pady=10)
        bottom_frame.grid_columnconfigure(0, weight=3)
        bottom_frame.grid_columnconfigure(1, weight=2)
        stats_area_frame = tk.Frame(bottom_frame)
        stats_area_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        q_stats_frame = tk.Frame(stats_area_frame, relief=tk.RIDGE, borderwidth=2)
        q_stats_frame.pack(fill=tk.X, pady=2)
        self.create_label(q_stats_frame, "問題の統計", font_size=12)
        self.per_question_stats_content = self.create_content(q_stats_frame, "", font_size=10, justify="left")
        today_stats_frame = tk.Frame(stats_area_frame, relief=tk.RIDGE, borderwidth=2)
        today_stats_frame.pack(fill=tk.X, pady=2)
        self.create_label(today_stats_frame, "今日の統計", font_size=12)
        self.today_stats_content = self.create_content(today_stats_frame, "", font_size=10, justify="left")
        overall_stats_frame = tk.Frame(stats_area_frame, relief=tk.RIDGE, borderwidth=2)
        overall_stats_frame.pack(fill=tk.X, pady=2)
        self.create_label(overall_stats_frame, "全体の統計", font_size=12)
        self.overall_stats_content = self.create_content(overall_stats_frame, "", font_size=10, justify="left")
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

    def create_settings_tab(self, parent_tab):
        settings_frame = tk.Frame(parent_tab, padx=20, pady=20)
        settings_frame.pack(fill=tk.BOTH, expand=True)
        tk.Label(settings_frame, text="Notion APIキー:", font=("Arial", 12, "bold")).pack(anchor='w', pady=(10,2))
        tk.Entry(settings_frame, textvariable=self.api_key_var, font=("Arial", 12), width=60, show="*").pack(fill=tk.X, padx=5, pady=(0,10))
        tk.Label(settings_frame, text="データベースID:", font=("Arial", 12, "bold")).pack(anchor='w', pady=(10,2))
        tk.Entry(settings_frame, textvariable=self.db_id_var, font=("Arial", 12), width=60).pack(fill=tk.X, padx=5, pady=(0,10))
        tk.Label(settings_frame, text="正誤プロパティの出題モード:", font=("Arial", 12, "bold")).pack(anchor='w', pady=(20,2))
        modes_frame = tk.Frame(settings_frame)
        modes_frame.pack(fill=tk.X, padx=5)
        tk.Checkbutton(modes_frame, text="未学習", variable=self.mode_unanswered_var, font=("Arial", 11)).pack(anchor='w')
        tk.Checkbutton(modes_frame, text="間違えた問題", variable=self.mode_incorrect_var, font=("Arial", 11)).pack(anchor='w')
        tk.Checkbutton(modes_frame, text="正解した問題", variable=self.mode_correct_var, font=("Arial", 11)).pack(anchor='w')
        save_button = tk.Button(settings_frame, text="設定を保存", command=self.save_settings_and_refilter, font=("Arial", 14, "bold"), bg="lightblue")
        save_button.pack(fill=tk.X, padx=5, pady=20)

    def load_data_from_notion(self):
        """
        Notionデータベースから全ての単語データを取得し、マスターDataFrameに格納する。
        """
        print("---"" 全データ読み込み開始 ---")
        url = f"https://api.notion.com/v1/databases/{self.db_id_var.get()}/query"
        payload = {"sorts": [{"timestamp": "last_edited_time", "direction": "ascending"}]}
        all_results = []
        page_count = 1
        while True:
            print(f"\rNotionからデータを取得中... (ページ {page_count})", end='')
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                response_data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"\nエラー: Notionからのデータ取得に失敗しました。\n{e}")
                messagebox.showerror("APIエラー", f"Notionからのデータ取得に失敗しました.\n{e}")
                self.master_df = pd.DataFrame([])
                return
            all_results.extend(response_data.get('results', []))
            if response_data.get('has_more'):
                page_count += 1
                payload['start_cursor'] = response_data.get('next_cursor')
            else:
                break
        total_words = len(all_results)
        print(f"\rNotionから全データを取得完了。 ({total_words}件)      ")
        word_list = []
        if total_words > 0:
            for page in all_results:
                props = page.get('properties', {})
                word_list.append({
                    'page_id': page.get('id'),
                    '英語': get_text_from_property(props.get('英単語')),
                    '日本語': get_text_from_property(props.get('日本語')),
                    'メモ': get_text_from_property(props.get('メモ')),
                    'mistake_count': get_number_from_property(props.get('間違えた回数')),
                    '正誤': get_status_from_property(props.get('正誤')),
                    '品詞': get_text_from_property(props.get('品詞')),
                    'やった日': get_text_from_property(props.get('やった日')),
                    '例文英語1': get_text_from_property(props.get('例文英語1')),
                    '例文日本語1': get_text_from_property(props.get('例文日本語1')),
                    '例文英語2': get_text_from_property(props.get('例文英語2')),
                    '例文日本語2': get_text_from_property(props.get('例文日本語2')),
                    '例文英語3': get_text_from_property(props.get('例文英語3')),
                    '例文日本語3': get_text_from_property(props.get('例文日本語3')),
                    '例文英語4': get_text_from_property(props.get('例文英語4')),
                    '例文日本語4': get_text_from_property(props.get('例文日本語4')),
                })
        self.master_df = pd.DataFrame(word_list)
        self.sentence_english_cols = [f'例文英語{i}' for i in range(1, 5)]
        self.sentence_japanese_cols = [f'例文日本語{i}' for i in range(1, 5)]
        print("--- 全データ読み込み完了 ---")

    def save_memo(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            return
        word_data = self.df.iloc[self.current_index]
        page_id = word_data['page_id']
        memo_text = self.memo_content.get("1.0", tk.END).strip()
        properties_to_update = {'メモ': {'rich_text': [{'text': {'content': memo_text}}]}}
        if self.update_notion_page(page_id, properties_to_update):
            self.df.loc[self.current_index, 'メモ'] = memo_text
            self.master_df.loc[self.master_df['page_id'] == page_id, 'メモ'] = memo_text
            print("成功", "メモを保存しました。")

    def create_label(self, parent, text, font_size=14):
        label = tk.Label(parent, text=text, font=("Arial", font_size, "bold"))
        label.pack(pady=(5, 0))
        return label

    def create_content(self, parent, text, font_size=12, justify="center"):
        content = tk.Label(parent, text=text, font=("Arial", font_size), justify=justify)
        content.pack(pady=5, padx=10, fill=tk.X)
        return content

    def update_all_stats_displays(self):
        self.update_per_question_stats_display()
        self.update_today_stats_display()
        self.update_overall_stats_display()

    def update_per_question_stats_display(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.per_question_stats_content.config(text="")
            return
        word_data = self.df.iloc[self.current_index]
        date_str = word_data.get('やった日')
        date_str_formatted = 'N/A'
        if date_str and isinstance(date_str, str):
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_str_formatted = date_obj.strftime('%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                pass
        mistake_count_val = word_data.get('mistake_count')
        mistake_count = int(mistake_count_val) if pd.notna(mistake_count_val) else 0
        stats_text = (
            f"品詞: {word_data.get('品詞') or 'N/A'}\n"
            f"正誤ステータス: {word_data.get('正誤') or 'N/A'}\n"
            f"間違えた回数: {mistake_count}\n"
            f"やった日: {date_str_formatted}"
        )
        self.per_question_stats_content.config(text=stats_text)

    def update_today_stats_display(self):
        total = self.todays_total_answered
        correct = self.todays_correct_count
        incorrect = total - correct
        correct_rate = (correct / total * 100) if total > 0 else 0
        stats_text = (
            f"解答数: {total}\n"
            f"正解: {correct} ({correct_rate:.1f}%)\n"
            f"誤答: {incorrect} ({100 - correct_rate:.1f}%)"
        )
        self.today_stats_content.config(text=stats_text)

    def update_overall_stats_display(self):
        if self.master_df.empty:
            self.overall_stats_content.config(text="")
            return
        total = len(self.master_df)
        correct = len(self.master_df[self.master_df['正誤'] == '正'])
        incorrect = len(self.master_df[self.master_df['正誤'] == '誤'])
        correct_rate = (correct / total * 100) if total > 0 else 0
        incorrect_rate = (incorrect / total * 100) if total > 0 else 0
        stats_text = (
            f"総単語数: {total}\n"
            f"正解済み: {correct} ({correct_rate:.1f}%)\n"
            f"誤答あり: {incorrect} ({incorrect_rate:.1f}%)\n"
            f"未回答: {total - (correct + incorrect)} ({100 - (correct_rate + incorrect_rate):.1f}%)"
        )
        self.overall_stats_content.config(text=stats_text)

    def _load_todays_stats_from_notion(self):
        if self.df.empty:
            self.todays_total_answered = 0
            self.todays_correct_count = 0
            return
        now_utc = datetime.now(timezone.utc)
        now_jst = now_utc + timedelta(hours=9)
        today_jst = now_jst.date()
        df_copy = self.df.copy()
        df_copy['やった日_dt_utc'] = pd.to_datetime(df_copy['やった日'], errors='coerce', utc=True)
        df_copy['やった日_dt_jst'] = df_copy['やった日_dt_utc'] + pd.Timedelta(hours=9)
        df_copy['やった日_date_jst'] = df_copy['やった日_dt_jst'].dt.date
        todays_entries = df_copy[
            (df_copy['やった日_date_jst'] == today_jst) &
            (df_copy['正誤'].isin(['正', '誤']))
        ]
        self.todays_total_answered = len(todays_entries)
        self.todays_correct_count = len(todays_entries[todays_entries['正誤'] == '正'])

    def show_word(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.word_content.config(text="単語がありません。設定を確認してください。")
            for label in self.sentence_labels:
                label.config(text="")
            self.memo_content.delete("1.0", tk.END)
            return
        word_data = self.df.iloc[self.current_index]
        self.is_answer_visible = False
        self.word_content.config(text=word_data.get('英語', ''))
        self.memo_content.delete("1.0", tk.END)
        self.memo_content.insert("1.0", word_data.get('メモ', ''))
        for i, col_name in enumerate(self.sentence_english_cols):
            self.sentence_labels[i].config(text=word_data.get(col_name, ''))
        self.toggle_button.config(text="回答を表示")
        self.update_per_question_stats_display()

    def toggle_answer(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            return
        word_data = self.df.iloc[self.current_index]
        if self.is_answer_visible:
            self.word_content.config(text=word_data.get('英語', ''))
            for i, col_name in enumerate(self.sentence_english_cols):
                self.sentence_labels[i].config(text=word_data.get(col_name, ''))
            self.toggle_button.config(text="回答を表示")
            self.is_answer_visible = False
        else:
            self.word_content.config(text=word_data.get('日本語', ''))
            for i, col_name in enumerate(self.sentence_japanese_cols):
                self.sentence_labels[i].config(text=word_data.get(col_name, ''))
            self.toggle_button.config(text="問題を表示")
            self.is_answer_visible = True

    def record_and_next(self, correct):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            return
        word_data = self.df.iloc[self.current_index]
        page_id = word_data['page_id']
        properties_to_update = {}
        self.todays_total_answered += 1
        if correct:
            self.todays_correct_count += 1
            new_status = "正"
        else:
            current_mistakes = word_data.get('mistake_count', 0)
            if pd.isna(current_mistakes):
                current_mistakes = 0
            new_mistake_count = int(current_mistakes) + 1
            new_status = "誤"
            properties_to_update['間違えた回数'] = {'number': new_mistake_count}
            self.master_df.loc[self.master_df['page_id'] == page_id, 'mistake_count'] = new_mistake_count

        self.df.loc[self.current_index, '正誤'] = new_status
        self.master_df.loc[self.master_df['page_id'] == page_id, '正誤'] = new_status

        properties_to_update['正誤'] = {'status': {'name': new_status}}
        current_time_iso = datetime.now(timezone.utc).isoformat()
        properties_to_update['やった日'] = {'date': {'start': current_time_iso}}
        
        if self.update_notion_page(page_id, properties_to_update):
            self.df.loc[self.df['page_id'] == page_id, 'やった日'] = current_time_iso
            self.master_df.loc[self.master_df['page_id'] == page_id, 'やった日'] = current_time_iso
        else:
            self.todays_total_answered -= 1
            if correct: self.todays_correct_count -= 1
            return
        
        self.update_today_stats_display()
        self.update_overall_stats_display()

        if self.current_index < len(self.df) - 1:
            self.current_index += 1
            self.show_word()
        else:
            messagebox.showinfo("完了", "現在のモードでの学習が完了しました。")
            self.refilter_and_display_words()

    def update_notion_page(self, page_id, properties):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {'properties': properties}
        try:
            response = requests.patch(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as e:
            messagebox.showerror("更新エラー", f"Notionページの更新に失敗しました.\n{e}")
            return False

# --- アプリケーションの実行 ---
if __name__ == "__main__":
    root = tk.Tk()
    app = WordQuizApp(root)
    root.mainloop()
