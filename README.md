# なんでもマッチング (DiscordBot-Hackason42Tokyo)

/together　コマンドを使用して、代表者同士でマッチングするよ！

/cancel　コマンドでキャンセルできるよ！

マッチングするdetail内容を増やしたい場合は、srcs/models.pyの編集と、それに対応したDiscordチャンネルの新規作成をしてね！

初回起動では、42APIから42Tokyo生徒のintraとそれに付随した顔写真のURLを取得＆キャッシュするため、時間がかかるよ！

```
touch bot-test/.env
```

```
cat << EOF > bot-test/.env
DISCORD_TOKEN=
GUILD_ID=
FORTYTWO_APP_UID=
FORTYTWO_APP_SECRET=
EOF
```

```
cd bot-test
```

```
docker compose up --build
```

42API Document (FORTYTWO_APP_UID, FORTYTWO_APP_SECRET)

https://api.intra.42.fr/apidoc

Discord Dev Portal (DISCORD_TOKEN, GUILD_ID)

https://discord.com/developers/home
