# iMe

macOSの入力ソースインジケーターをパクったWindows IMEインジケーター。

IMEを切り替えると、キャレット（またはマウスカーソル）付近に「あ」「A」がポップアップ表示される。

## 動機

Windowsでは、IMEが日本語なのか英語なのかタスクバーの小さい「あ/A」を見るしかない。macOSには切り替え時にカーソル付近にポップアップが出る機能がある。それのパチモン。

## 必要なもの

- Python 3（標準ライブラリのみ、pip install不要）

## 使い方

```
python iMe.py
```

Ctrl+Cで終了。

## 設定

`iMe.py` 上部の定数を編集：

```python
ALWAYS_SHOW = False        # True: 常時表示 / False: 切替時のみ表示
HIDE_DELAY_MS = 800        # 消えるまでの時間(ms)
FONT_SIZE = 14
COLOR_JA = '#2563EB'       # 日本語モードの色
COLOR_EN = '#444444'       # 英語モードの色
SHOW_ON_APP_SWITCH = True  # True: アプリ切替時も表示 / False: 同一アプリ内のみ
SHOW_ON_FOCUS = True       # True: テキスト入力欄にフォーカス時に表示 / False: IME切替時のみ
```

## 仕組み

- `ImmGetDefaultIMEWnd` + `SendMessage` でIME状態をポーリング（50ms間隔）
- `GetGUIThreadInfo` でキャレット位置を取得（取れないアプリではマウス位置にフォールバック）
- tkinterで半透明オーバーレイ表示

## キャレット位置について

Win32標準コントロールを使うアプリ（メモ帳など）ではキャレット位置に表示される。ブラウザやVSCodeなど自前描画のアプリではキャレットが取れないため、マウスカーソル付近に表示される。
