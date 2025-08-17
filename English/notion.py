import tkinter as tk
from tkinter import messagebox
import pandas as pd
import json
import os
import requests
from datetime import datetime

# --- Helper Functions ---

def get_text_from_property(prop):
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
    return ""

def get_number_from_property(prop):
    return prop.get('number', 0) if prop else 0

def get_status_from_property(prop):
    return prop.get('status', {}).get('name', '') if prop else ''

# --- Main Application ---

class WordQuizApp:
    def __init__(self, master):
        self.master = master
        self.master.title("英単語学習アプリ (Notion版)")
        self.master.geometry("900x900")

        self.api_key = None
        self.database_id = None
        if not self.load_config():
            self.master.destroy()
            return
            
        self.headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Notion-Version': '2022-06-28',
            'Content-Type': 'application/json',
        }

        # Initialize stats trackers
        self.todays_total_answered = 0
        self.todays_correct_count = 0

        self.df = pd.DataFrame()
        self.load_data_from_notion()
        
        self.current_index = 0
        self.is_answer_visible = False

        self.create_widgets()
        self.update_all_stats_displays()

    def load_config(self):
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, '参照データ', 'config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            self.api_key = config.get("NOTION_API_KEY")
            self.database_id = config.get("DATABASE_ID")
            self.question_mode = config.get("QUESTION_MODE", "未")
            if not self.api_key or not self.database_id:
                messagebox.showerror("設定エラー", "config.jsonにNOTION_API_KEYとDATABASE_IDを設定してください。")
                return False
            return True
        except Exception as e:
            messagebox.showerror("エラー", f"設定ファイルの読み込み中にエラーが発生しました: {e}")
            return False

    def load_data_from_notion(self):
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        sort_payload = {"sorts": [{"timestamp": "last_edited_time", "direction": "ascending"}]}
        try:
            response = requests.post(url, headers=self.headers, json=sort_payload)
            response.raise_for_status()
            response_data = response.json()
        except requests.exceptions.RequestException as e:
            messagebox.showerror("APIエラー", f"Notionからのデータ取得に失敗しました.\n{e}")
            return

        word_list = []
        for page in response_data.get('results', []):
            props = page.get('properties', {})
            word_data = {
                'page_id': page.get('id'),
                '英語': get_text_from_property(props.get('英単語')),
                '日本語': get_text_from_property(props.get('日本語')),
                'mistake_count': get_number_from_property(props.get('間違えた回数')),
                '正誤': get_status_from_property(props.get('正誤')),
                '品詞': get_text_from_property(props.get('品詞')),
                '最終更新日時': page.get('last_edited_time') # Accessing top-level property
            }
            for i in range(1, 5):
                word_data[f'例文英語{i}'] = get_text_from_property(props.get(f'例文英語{i}'))
                word_data[f'例文日本語{i}'] = get_text_from_property(props.get(f'例文日本語{i}'))
            word_list.append(word_data)
        
        self.df = pd.DataFrame(word_list)
        if self.df.empty:
            messagebox.showinfo("情報", "Notionデータベースに単語が見つかりませんでした。")
        else:
            # Apply question mode sorting
            if self.question_mode == "未":
                # Prioritize '未' or empty '正誤'
                unanswered_df = self.df[self.df['正誤'].isin(['', '未'])]
                answered_df = self.df[~self.df['正誤'].isin(['', '未'])]
                self.df = pd.concat([unanswered_df, answered_df]).reset_index(drop=True)
            elif self.question_mode == "誤":
                # Prioritize '誤'
                incorrect_df = self.df[self.df['正誤'] == '誤']
                other_df = self.df[self.df['正誤'] != '誤']
                self.df = pd.concat([incorrect_df, other_df]).reset_index(drop=True)
            
            self.sentence_english_cols = [f'例文英語{i}' for i in range(1, 5)]
            self.sentence_japanese_cols = [f'例文日本語{i}' for i in range(1, 5)]

    def create_widgets(self):
        main_frame = tk.Frame(self.master, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        top_frame = tk.Frame(main_frame)
        top_frame.pack(fill=tk.BOTH, expand=True)

        self.word_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.word_frame.pack(fill=tk.X, pady=5)
        self.create_label(self.word_frame, "単語", font_size=16)
        self.word_content = self.create_content(self.word_frame, "", font_size=24)

        self.sentence_frame = tk.Frame(top_frame, relief=tk.RIDGE, borderwidth=2)
        self.sentence_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.create_label(self.sentence_frame, "例文", font_size=16)
        self.sentence_labels = [self.create_content(self.sentence_frame, "", font_size=12) for _ in range(4)]

        bottom_frame = tk.Frame(main_frame)
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

    def on_resize(self, event=None):
        try:
            # Adjust wraplength based on the widget's actual width
            word_wrap_length = self.word_frame.winfo_width() - 20  # Subtract padding
            if word_wrap_length > 1:
                self.word_content.config(wraplength=word_wrap_length)

            sentence_wrap_length = self.sentence_frame.winfo_width() - 20  # Subtract padding
            if sentence_wrap_length > 1:
                for label in self.sentence_labels:
                    label.config(wraplength=sentence_wrap_length)
        except (AttributeError, tk.TclError):
            # This can happen if widgets are not yet created or are destroyed.
            pass

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
        
        # Safely get and format date
        date_str = word_data.get('最終更新日時')
        if date_str and isinstance(date_str, str):
            try:
                date_obj = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                date_str_formatted = date_obj.strftime('%Y-%m-%d %H:%M')
            except (ValueError, TypeError):
                date_str_formatted = 'N/A'
        else:
            date_str_formatted = 'N/A'
        
        stats_text = (
            f"品詞: {word_data.get('品詞') or 'N/A'}\n"
            f"正誤ステータス: {word_data.get('正誤') or 'N/A'}\n"
            f"最終更新日時: {date_str_formatted}"
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

    def show_word(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.word_content.config(text="単語がありません。")
            for label in self.sentence_labels:
                label.config(text="")
            return

        word_data = self.df.iloc[self.current_index]
        self.is_answer_visible = False
        self.word_content.config(text=word_data.get('英語', ''))
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
            self.df.loc[self.current_index, '正誤'] = new_status
        else:
            current_mistakes = word_data.get('mistake_count')
            if pd.isna(current_mistakes):
                current_mistakes = 0
            new_mistake_count = int(current_mistakes) + 1
            new_status = "誤"
            properties_to_update['間違えた回数'] = {'number': new_mistake_count}
            self.df.loc[self.current_index, 'mistake_count'] = new_mistake_count
            self.df.loc[self.current_index, '正誤'] = new_status

        properties_to_update['正誤'] = {'status': {'name': new_status}}
        
        if not self.update_notion_page(page_id, properties_to_update):
            self.todays_total_answered -= 1
            if correct: self.todays_correct_count -= 1
            return
        
        self.update_today_stats_display()
        self.update_overall_stats_display()

        if self.current_index < len(self.df) - 1:
            self.current_index += 1
            self.show_word()
        else:
            messagebox.showinfo("完了", "すべての単語の確認が終わりました。")
            self.current_index = 0
            self.show_word()

    def update_notion_page(self, page_id, properties):
        url = f"https://api.notion.com/v1/pages/{page_id}"
        payload = {'properties': properties}
        try:
            response = requests.patch(url, headers=self.headers, json=payload)
            response.raise_for_status()
            # Update last edited time in dataframe after successful patch
            self.df.loc[self.df['page_id'] == page_id, '最終更新日時'] = datetime.now().isoformat()
            return True
        except requests.exceptions.RequestException as e:
            messagebox.showerror("更新エラー", f"Notionページの更新に失敗しました.\n{e}")
            return False

if __name__ == "__main__":
    root = tk.Tk()
    app = WordQuizApp(root)
    root.mainloop()
