# 1. ベースイメージ: 軽量かつCライブラリの互換性が高いslimを採用
FROM python:3.11-slim

# 2. 環境変数の設定 (Pythonの挙動制御とタイムゾーン)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TZ=Asia/Tokyo

# 3. 作業ディレクトリの設定
WORKDIR /app

# 4. 依存関係のインストール (レイヤーキャッシュの活用)
# ソースコードより先にrequirements.txtをコピーすることで、コード変更時の再インストールをスキップする
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 5. セキュリティ: 非rootユーザーの作成と切り替え
# コンテナ内をroot権限で実行するのは重大な脆弱性（コンテナエスケープ等のリスク）を招くため禁止
RUN useradd -m botuser
USER botuser

# 6. ソースコードのコピー
COPY src/ ./src/

# 7. 実行コマンド
CMD ["python", "src/main.py"]