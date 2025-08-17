import json
import os
import requests

def load_config():
    """設定ファイルを読み込み、APIキーとデータベースIDを返す"""
    try:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        config_path = os.path.join(script_dir, '..', 'ログ・設定', 'config.json')
        
        print(f"設定ファイルを読み込みます: {config_path}")
        
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
        
        api_key = config.get("NOTION_API_KEY")
        database_id = config.get("DATABASE_ID")
        
        if not api_key or not database_id:
            print("エラー: config.jsonにNOTION_API_KEYとDATABASE_IDを設定してください。")
            return None, None
            
        return api_key, database_id
    except FileNotFoundError:
        print(f"エラー: 設定ファイルが見つかりません: {config_path}")
        return None, None
    except Exception as e:
        print(f"エラー: 設定ファイルの読み込み中にエラーが発生しました: {e}")
        return None, None

def query_notion_database(api_key, database_id):
    """Notionデータベースに問い合わせて結果を返す"""
    url = f"https://api.notion.com/v1/databases/{database_id}/query"
    headers = {
        'Authorization': f'Bearer {api_key}',
        'Notion-Version': '2022-06-28',
        'Content-Type': 'application/json',
    }
    
    print(f"Notionデータベースに問い合わせます: {url}")
    
    try:
        response = requests.post(url, headers=headers, json={})
        response.raise_for_status()
        print("✓ Notionからのデータ取得に成功しました。")
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"✗ Notion APIへのリクエスト中にエラーが発生しました: {e}")
        if e.response:
            print(f"レスポンス内容: {e.response.text}")
        return None

def main():
    """メイン処理"""
    api_key, database_id = load_config()
    if not api_key:
        return
        
    data = query_notion_database(api_key, database_id)
    
    if data:
        print("\n--- 取得データ (JSON) ---")
        # 読みやすいように整形して出力
        print(json.dumps(data, indent=2, ensure_ascii=False))
        print("\n--------------------------")
        print(f"合計 {len(data.get('results', []))} 件のページを取得しました。")

if __name__ == "__main__":
    main()
