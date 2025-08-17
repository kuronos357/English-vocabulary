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

# --- Main Application ---

class WordFlashcardApp:
    def __init__(self, master):
        self.master = master
        self.master.title("英単語カード (Notion版)")
        self.master.geometry("900x600")

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
        try:
            response = requests.post(url, headers=self.headers, json={})
            response.raise_for_status()
            response_data = response.json()
        except requests.exceptions.RequestException as e:
            messagebox.showerror("APIエラー", f"Notionからのデータ取得に失敗しました.\n{e}")
            return

        word_list = []
        for page in response_data.get('results', []):
            props = page.get('properties', {})
            word_data = {
                '英語': get_text_from_property(props.get('英単語')),
                '日本語': get_text_from_property(props.get('日本語')),
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

        button_frame = tk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=10)
        
        self.toggle_button = tk.Button(button_frame, text="回答を表示", command=self.toggle_answer, height=2)
        self.toggle_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

        self.next_button = tk.Button(button_frame, text="次へ", command=self.next_word, height=2)
        self.next_button.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)

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
            return

        word_data = self.df.iloc[self.current_index]
        self.is_answer_visible = False

        self.word_content.config(text=word_data.get('英語', ''))
        for i, col_name in enumerate(self.sentence_english_cols):
            self.sentence_labels[i].config(text=word_data.get(col_name, ''))
        self.toggle_button.config(text="回答を表示")

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

    def next_word(self):
        if self.current_index < len(self.df) - 1:
            self.current_index += 1
            self.show_word()
        else:
            messagebox.showinfo("完了", "すべての単語の確認が終わりました。")
            self.current_index = 0 # Go back to the start
            self.show_word()

if __name__ == "__main__":
    root = tk.Tk()
    app = WordFlashcardApp(root)
    root.mainloop()