import tkinter as tk
from tkinter import messagebox
import pandas as pd
from datetime import datetime

class WordQuizApp:
    def __init__(self, master):
        self.master = master
        self.master.title("英単語学習アプリ")
        self.master.geometry("900x900")

        self.file_path = '/home/kuronos357/programming/Project/Question-generator/English/参照データ/英単語mk3.csv'
        self.load_data()
        self.current_index = 0
        self.todays_correct_count = 0
        self.is_answer_visible = False

        self.create_widgets()
        self.show_word()

    def load_data(self):
        try:
            self.df = pd.read_csv(self.file_path)
            # 'Unnamed:' で始まる不要な列を削除
            self.df = self.df.loc[:, ~self.df.columns.str.contains('^Unnamed')]
            
            # 例文の数を動的に取得
            self.sentence_english_cols = sorted([col for col in self.df.columns if col.startswith('例文英語')])
            self.sentence_japanese_cols = sorted([col for col in self.df.columns if col.startswith('例文日本語')])
            self.num_sentences = len(self.sentence_english_cols)

            self.df['last_learned_date'] = pd.to_datetime(self.df['last_learned_date'], errors='coerce')
            self.df = self.df.sort_values(by='last_learned_date', ascending=True, na_position='first').reset_index(drop=True)
        except FileNotFoundError:
            messagebox.showerror("エラー", f"ファイルが見つかりません: {self.file_path}")
            self.master.destroy()
            return
        except Exception as e:
            messagebox.showerror("エラー", f"データの読み込み中にエラーが発生しました: {e}")
            self.master.destroy()
            return

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
        self.sentence_labels = [self.create_content(sentence_frame, "", font_size=12) for _ in range(self.num_sentences)]

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

        self.prev_button = tk.Button(button_frame, text="戻る", command=self.prev_word, height=2)
        self.prev_button.pack(fill=tk.X, padx=10, pady=5)

    def create_label(self, parent, text, font_size=14):
        label = tk.Label(parent, text=text, font=("Arial", font_size, "bold"))
        label.pack(pady=(5, 0))
        return label

    def create_content(self, parent, text, font_size=12, justify="center"):
        content = tk.Label(parent, text=text, font=("Arial", font_size), wraplength=380, justify=justify)
        content.pack(pady=5, padx=10, fill=tk.X)
        return content

    def show_word(self):
        if self.df.empty or not (0 <= self.current_index < len(self.df)):
            self.word_content.config(text="単語がありません。")
            return

        word_data = self.df.iloc[self.current_index]
        self.is_answer_visible = False

        self.word_content.config(text=word_data.get('英語', ''))
        for i, col_name in enumerate(self.sentence_english_cols):
            self.sentence_labels[i].config(text=word_data.get(col_name, ''))
        self.toggle_button.config(text="回答を表示")

        date_str = word_data['last_learned_date'].strftime('%Y-%m-%d %H:%M') if pd.notna(word_data['last_learned_date']) else '未学習'
        mistake_count = word_data.get('mistake_count', 0)
        correct_count = word_data.get('correct_count', 0)
        
        stats_text = f"""最終学習日: {date_str}
間違い回数: {mistake_count}
累計正解数: {correct_count}
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

        # カウントを整数として扱うために、NaNを0に変換
        self.df['correct_count'] = self.df['correct_count'].fillna(0).astype(int)
        self.df['mistake_count'] = self.df['mistake_count'].fillna(0).astype(int)

        if correct:
            self.df.loc[self.current_index, 'correct_count'] += 1
            self.todays_correct_count += 1
        else:
            self.df.loc[self.current_index, 'mistake_count'] += 1
        
        self.df.loc[self.current_index, 'last_learned_date'] = datetime.now()
        
        if self.current_index < len(self.df) - 1:
            self.current_index += 1
            self.show_word()
        else:
            self.word_content.config(text="最後の単語です。お疲れ様でした！")
            for label in self.sentence_labels:
                label.config(text="")

    def prev_word(self):
        if self.current_index > 0:
            self.current_index -= 1
            self.show_word()

    def on_closing(self):
        if messagebox.askokcancel("終了", "学習データを保存して終了しますか？"):
            try:
                self.df.to_csv(self.file_path, index=False, encoding='utf-8')
                self.master.destroy()
            except Exception as e:
                messagebox.showerror("エラー", f"ファイルの保存中にエラーが発生しました: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = WordQuizApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_closing)
    root.mainloop()
