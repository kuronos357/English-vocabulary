import tkinter as tk
from tkinter import ttk, messagebox
import pandas as pd
import json
import os
import re
import requests
from datetime import datetime, timezone, timedelta
import threading
import queue

def get_text_from_property(prop):
    """
    Notionのページプロパティオブジェクトからテキストコンテンツを抽出する。
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
    return prop.get('number', 0) if prop else 0

def get_status_from_property(prop):
    return prop.get('status', {}).get('name', '') if prop else ''

class WordQuizApp:
    def __init__(self, master):
        self.master = master
        self.master.title("英単語学習アプリ (Notion版)")
        self.master.geometry("900x1200")

        self.api_key_var = tk.StringVar()
        self.db_id_var = tk.StringVar()
        self.mode_unanswered_var = tk.BooleanVar()
        self.mode_incorrect_var = tk.BooleanVar()
        self.mode_correct_var = tk.BooleanVar()
        self.mode_correct_with_mistakes_var = tk.BooleanVar()
        self.timer_seconds_var = tk.IntVar()

        self.question_mode = []
        self.headers = {}
        self.timer_id = None
        self.indicator_timer_id = None
        self.load_config()
        self.update_headers()

        self.master_df = pd.DataFrame()
        self.df = pd.DataFrame()

        self.todays_total_answered = 0
        self.todays_correct_count = 0
        
        self.create_widgets()
        if self.api_key_var.get() and self.db_id_var.get():
            self.start_loading_thread()
        else:
            messagebox.showwarning("設定不足", "APIキーまたはデータベースIDが設定されていません。\n「設定」タブで設定を完了してください。")

        self.current_index = 0
        self.is_answer_visible = False

    def extract_id_from_url(self, url_or_id):
        """NotionのURLからデータベースID(32文字の16進数)を抽出する。"""
        if not isinstance(url_or_id, str):
            return ""
        match = re.search(r'([a-f0-9]{32})', url_or_id)
        if match:
            return match.group(1)
        return url_or_id

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
        self.timer_seconds_var.set(config.get("TIMER_SECONDS", 30))
        self.mode_unanswered_var.set("未" in self.question_mode)
        self.mode_incorrect_var.set("誤" in self.question_mode)
        self.mode_correct_var.set("正" in self.question_mode)
        self.mode_correct_with_mistakes_var.set("正(誤)" in self.question_mode)

    def save_settings_and_refilter(self):
        raw_db_id = self.db_id_var.get()
        cleaned_db_id = self.extract_id_from_url(raw_db_id)
        self.db_id_var.set(cleaned_db_id)

        if not self.api_key_var.get() or not self.db_id_var.get():
            messagebox.showerror("エラー", "APIキーとデータベースIDは必須です。")
            return

        new_modes = []
        if self.mode_unanswered_var.get(): new_modes.append("未")
        if self.mode_incorrect_var.get(): new_modes.append("誤")
        if self.mode_correct_var.get(): new_modes.append("正")
        if self.mode_correct_with_mistakes_var.get(): new_modes.append("正(誤)")

        if not new_modes:
            print("エラー", "少なくとも1つの出題モードを選択してください。")
            return

        os.makedirs(self.config_dir, exist_ok=True)
        config = {
            "NOTION_API_KEY": self.api_key_var.get(),
            "DATABASE_ID": self.db_id_var.get(),
            "QUESTION_MODE": new_modes,
            "TIMER_SECONDS": self.timer_seconds_var.get()
        }
        with open(self.config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=4, ensure_ascii=False)

        print("成功", "設定を保存しました。出題内容を更新します。")
        self.question_mode = new_modes
        
        self.update_headers()

        if self.master_df.empty:
            self.start_loading_thread()
        else:
            self.refilter_and_display_words()

    def refilter_and_display_words(self):
        if self.master_df.empty:
            self.df = pd.DataFrame([])
        else:
            source_df = self.master_df.copy()
            
            final_condition = pd.Series([False] * len(source_df), index=source_df.index)

            if "未" in self.question_mode:
                final_condition |= source_df['正誤'].isin(['', '未'])
            if "誤" in self.question_mode:
                final_condition |= (source_df['正誤'] == '誤')
            if "正" in self.question_mode:
                final_condition |= (source_df['正誤'] == '正')
            if "正(誤)" in self.question_mode:
                source_df['mistake_count'] = pd.to_numeric(source_df['mistake_count'], errors='coerce').fillna(0)
                final_condition |= ((source_df['正誤'] == '正') & (source_df['mistake_count'] > 0))

            if final_condition.any():
                self.df = source_df[final_condition].reset_index(drop=True)
            else:
                self.df = pd.DataFrame([])

        if self.df.empty:
            messagebox.showinfo("情報", "選択されたモードに該当する単語がありませんでした。")

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
        self.original_content_fg_color = self.word_content.cget("foreground")
        self.timer_progress_bar = ttk.Progressbar(self.word_frame, orient='horizontal', mode='determinate')
        self.timer_progress_bar.pack(fill=tk.X, padx=10, pady=5, side=tk.BOTTOM)

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
        tk.Label(settings_frame, text="データベースID (URL可):", font=("Arial", 12, "bold")).pack(anchor='w', pady=(10,2))
        tk.Entry(settings_frame, textvariable=self.db_id_var, font=("Arial", 12), width=60).pack(fill=tk.X, padx=5, pady=(0,10))
        
        tk.Label(settings_frame, text="タイマー時間 (秒):", font=("Arial", 12, "bold")).pack(anchor='w', pady=(10,2))
        tk.Entry(settings_frame, textvariable=self.timer_seconds_var, font=("Arial", 12), width=10).pack(anchor='w', padx=5, pady=(0,10))

        tk.Label(settings_frame, text="正誤プロパティの出題モード:", font=("Arial", 12, "bold")).pack(anchor='w', pady=(20,2))
        modes_frame = tk.Frame(settings_frame)
        modes_frame.pack(fill=tk.X, padx=5)
        tk.Checkbutton(modes_frame, text="未学習", variable=self.mode_unanswered_var, font=("Arial", 11)).pack(anchor='w')
        tk.Checkbutton(modes_frame, text="間違えた問題", variable=self.mode_incorrect_var, font=("Arial", 11)).pack(anchor='w')
        tk.Checkbutton(modes_frame, text="正解した問題", variable=self.mode_correct_var, font=("Arial", 11)).pack(anchor='w')
        tk.Checkbutton(modes_frame, text="正解しているが、過去に間違えたことがある問題", variable=self.mode_correct_with_mistakes_var, font=("Arial", 11)).pack(anchor='w')
        save_button = tk.Button(settings_frame, text="設定を保存", command=self.save_settings_and_refilter, font=("Arial", 14, "bold"), bg="lightblue")
        save_button.pack(fill=tk.X, padx=5, pady=20)
        tk.Label(settings_frame, text="※APIキー/DB IDを変更した際はアプリの再起動すること。", font=("Arial", 9)).pack(anchor='w', pady=(10,2))

    

    def start_loading_thread(self):
        self.word_content.config(text="Notionからデータを読み込み中...")
        self.timer_progress_bar.config(mode='determinate', maximum=20, value=0)
        self.toggle_button.config(state=tk.DISABLED)
        self.correct_button.config(state=tk.DISABLED)
        self.incorrect_button.config(state=tk.DISABLED)
        self.save_memo_button.config(state=tk.DISABLED)

        self.data_queue = queue.Queue()
        threading.Thread(target=self.load_data_from_notion, args=(self.data_queue,), daemon=True).start()
        self.master.after(100, self.check_loading_queue)

    def check_loading_queue(self):
        try:
            while not self.data_queue.empty():
                message_type, *payload = self.data_queue.get_nowait()
                
                if message_type == 'progress':
                    page_count, = payload
                    self.word_content.config(text=f"データを取得中... (ページ {page_count})")
                    self.timer_progress_bar.config(value=page_count)

                elif message_type == 'done':
                    self.timer_progress_bar.config(mode='determinate', value=0)

                    self.toggle_button.config(state=tk.NORMAL)
                    self.correct_button.config(state=tk.NORMAL)
                    self.incorrect_button.config(state=tk.NORMAL)
                    self.save_memo_button.config(state=tk.NORMAL)

                    df, error = payload
                    if error:
                        messagebox.showerror("APIエラー", f"Notionからのデータ取得に失敗しました.\n{error}")
                        self.master_df = pd.DataFrame([])
                        self.word_content.config(text="読み込みに失敗しました。")
                    else:
                        self.master_df = df
                        self.sentence_english_cols = [f'例文英語{i}' for i in range(1, 5)]
                        self.sentence_japanese_cols = [f'例文日本語{i}' for i in range(1, 5)]
                    
                    self.refilter_and_display_words()
                    return
        except queue.Empty:
            pass
        
        self.master.after(100, self.check_loading_queue)

    def load_data_from_notion(self, q):
        print("---"" 全データ読み込み開始 ---")
        url = f"https://api.notion.com/v1/databases/{self.db_id_var.get()}/query"
        payload = {"sorts": [{"timestamp": "last_edited_time", "direction": "ascending"}]}
        all_results = []
        page_count = 1
        while True:
            print(f"\rNotionからデータを取得中... (ページ {page_count})", end='')
            q.put(('progress', page_count))
            try:
                response = requests.post(url, headers=self.headers, json=payload)
                response.raise_for_status()
                response_data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"エラー: Notionからのデータ取得に失敗しました。{e}")
                q.put(('done', None, e))
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
        master_df = pd.DataFrame(word_list)
        q.put(('done', master_df, None))
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
            messagebox.showinfo("成功", "メモを保存しました。")

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
        incorrect_rate = (incorrect / total * 100) if total > 0 else 0
        stats_text = (
            f"解答数: {total}\n"
            f"正解: {correct} ({correct_rate:.1f}%)\n"
            f"誤答: {incorrect} ({incorrect_rate:.1f}%)"
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

    def start_timer(self):
        self.cancel_timer()
        self.word_content.config(fg=self.original_content_fg_color)
        self.timer_progress_bar.config(value=0)

        timer_seconds = self.timer_seconds_var.get()
        if timer_seconds > 0:
            self.timer_progress_bar["maximum"] = timer_seconds * 10
            self.timer_progress_bar["value"] = timer_seconds * 10
            self.time_left = timer_seconds * 10
            self.timer_id = self.master.after(timer_seconds * 1000, self.on_timer_end)
            self.indicator_timer_id = self.master.after(100, self.update_timer_indicator)

    def update_timer_indicator(self):
        if self.time_left > 0:
            self.time_left -= 1
            self.timer_progress_bar["value"] = self.time_left
            self.indicator_timer_id = self.master.after(100, self.update_timer_indicator)

    def on_timer_end(self):
        self.word_content.config(fg='red')
        self.timer_id = None
        self.timer_progress_bar["value"] = 0

    def cancel_timer(self):
        if self.timer_id:
            self.master.after_cancel(self.timer_id)
            self.timer_id = None
        if self.indicator_timer_id:
            self.master.after_cancel(self.indicator_timer_id)
            self.indicator_timer_id = None

    def show_word(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.word_content.config(text="単語がありません。設定を確認してください。")
            for label in self.sentence_labels:
                label.config(text="")
            self.memo_content.delete("1.0", tk.END)
            return
        
        self.start_timer()
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
        
        self.cancel_timer()
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

if __name__ == "__main__":
    root = tk.Tk()
    app = WordQuizApp(root)
    root.mainloop()
