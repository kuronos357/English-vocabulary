import tkinter as tk
from tkinter import messagebox
import pandas as pd
import json
import os
import requests

# --- Helper Functions ---

def get_text_from_property(prop):
    """Notionのプロパティからテキストを取得"""
    if not prop:
        return ""
    if 'rich_text' in prop and prop['rich_text']:
        return prop['rich_text'][0].get('plain_text', '')
    if 'title' in prop and prop['title']:
        return prop['title'][0].get('plain_text', '')
    return ""

def get_number_from_property(prop):
    """Notionのプロパティから数値を取得"""
    return prop.get('number', 0) if prop else 0

def get_status_from_property(prop):
    """Notionのプロパティからステータスを取得"""
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

        self.df = pd.DataFrame()
        self.load_data_from_notion()
        
        self.current_index = 0
        self.todays_correct_count = 0
        self.is_answer_visible = False

        self.create_widgets()
        self.show_word()

    def load_config(self):
        """設定ファイルを読み込む"""
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            config_path = os.path.join(script_dir, '参照データ', 'config.json')
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            self.api_key = config.get("NOTION_API_KEY")
            self.database_id = config.get("DATABASE_ID")
            
            if not self.api_key or not self.database_id:
                messagebox.showerror("設定エラー", "config.jsonにNOTION_API_KEYとDATABASE_IDを設定してください。")
                return False
            return True
        except FileNotFoundError:
            messagebox.showerror("エラー", f"設定ファイルが見つかりません: {config_path}")
            return False
        except Exception as e:
            messagebox.showerror("エラー", f"設定ファイルの読み込み中にエラーが発生しました: {e}")
            return False

    def load_data_from_notion(self):
        """Notionデータベースから単語データを読み込む"""
        url = f"https://api.notion.com/v1/databases/{self.database_id}/query"
        # last_edited_time を基準に昇順でソートして、学習間隔が空いたものから出題
        sort_payload = {
            "sorts": [
                {
                    "property": "正誤",
                    "direction": "ascending"
                },
                {
                    "timestamp": "last_edited_time",
                    "direction": "ascending"
                }
            ]
        }
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
            }
            for i in range(1, 5):
                word_data[f'例文英語{i}'] = get_text_from_property(props.get(f'例文英語{i}'))
                word_data[f'例文日本語{i}'] = get_text_from_property(props.get(f'例文日本語{i}'))
            word_list.append(word_data)
        
        self.df = pd.DataFrame(word_list)
        if self.df.empty:
            messagebox.showinfo("情報", "Notionデータベースに単語が見つかりませんでした。")
        else:
            self.sentence_english_cols = [f'例文英語{i}' for i in range(1, 5)]
            self.sentence_japanese_cols = [f'例文日本語{i}' for i in range(1, 5)]

    def create_widgets(self):
        main_frame = tk.Frame(self.master, padx=10, pady=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        word_frame = tk.Frame(main_frame, relief=tk.RIDGE, borderwidth=2)
        word_frame.pack(fill=tk.X, pady=5)
        self.create_label(word_frame, "単語", font_size=16)
        self.word_content = self.create_content(word_frame, "", font_size=24)

        sentence_frame = tk.Frame(main_frame, relief=tk.RIDGE, borderwidth=2)
        sentence_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.create_label(sentence_frame, "例文", font_size=16)
        self.sentence_labels = [self.create_content(sentence_frame, "", font_size=12) for _ in range(4)]

        bottom_frame = tk.Frame(main_frame)
        bottom_frame.pack(fill=tk.X, pady=5)
        bottom_frame.grid_columnconfigure(0, weight=1)
        bottom_frame.grid_columnconfigure(1, weight=1)

        stats_frame = tk.Frame(bottom_frame, relief=tk.RIDGE, borderwidth=2)
        stats_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        self.create_label(stats_frame, "統計データ", font_size=14)
        self.stats_content = self.create_content(stats_frame, "", font_size=12, justify="left")

        button_frame = tk.Frame(bottom_frame, relief=tk.RIDGE, borderwidth=2)
        button_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        self.create_label(button_frame, "操作", font_size=14)
        
        self.toggle_button = tk.Button(button_frame, text="回答を表示", command=self.toggle_answer, height=2)
        self.toggle_button.pack(fill=tk.X, padx=10, pady=5)

        self.correct_button = tk.Button(button_frame, text="正解", command=lambda: self.record_and_next(correct=True), height=2, bg="lightgreen")
        self.correct_button.pack(fill=tk.X, padx=10, pady=5)
        
        self.incorrect_button = tk.Button(button_frame, text="不正解", command=lambda: self.record_and_next(correct=False), height=2, bg="lightcoral")
        self.incorrect_button.pack(fill=tk.X, padx=10, pady=5)

    def create_label(self, parent, text, font_size=14):
        label = tk.Label(parent, text=text, font=("Arial", font_size, "bold"))
        label.pack(pady=(5, 0))
        return label

    def create_content(self, parent, text, font_size=12, justify="center"):
        content = tk.Label(parent, text=text, font=("Arial", font_size), wraplength=800, justify=justify)
        content.pack(pady=5, padx=10, fill=tk.X)
        return content

    def show_word(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.word_content.config(text="単語がありません。")
            for label in self.sentence_labels:
                label.config(text="")
            self.stats_content.config(text="")
            return

        word_data = self.df.iloc[self.current_index]
        self.is_answer_visible = False

        self.word_content.config(text=word_data.get('英語', ''))
        for i, col_name in enumerate(self.sentence_english_cols):
            self.sentence_labels[i].config(text=word_data.get(col_name, ''))
        self.toggle_button.config(text="回答を表示")

        mistake_count = word_data.get('mistake_count', 0)
        status = word_data.get('正誤', '未')
        
        stats_text = f"""間違い回数: {mistake_count}
正誤ステータス: {status}
今日の正解数: {self.todays_correct_count}"""
        self.stats_content.config(text=stats_text)

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
            return
        
        if self.current_index < len(self.df) - 1:
            self.current_index += 1
            self.show_word()
        else:
            messagebox.showinfo("完了", "すべての単語の確認が終わりました。")
            self.current_index = 0
            self.show_word()

    def update_notion_page(self, page_id, properties):
        """特定のNotionページのプロパティを更新する"""
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
