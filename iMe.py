"""
iMe - キャレット付近にIME状態を表示する軽量ツール
依存: Python標準ライブラリのみ (tkinter + ctypes)
"""

import ctypes
import ctypes.wintypes as w
import tkinter as tk
import threading
import time
import signal

user32 = ctypes.windll.user32
imm32 = ctypes.windll.imm32
oleacc = ctypes.windll.oleacc

# API宣言
user32.GetForegroundWindow.restype = w.HWND
user32.GetWindowThreadProcessId.restype = w.DWORD
user32.SendMessageW.restype = ctypes.c_long
user32.GetGUIThreadInfo.restype = w.BOOL
user32.GetCursorPos.restype = w.BOOL
imm32.ImmGetDefaultIMEWnd.restype = w.HWND

WM_IME_CONTROL = 0x0283
IMC_GETOPENSTATUS = 0x0005
IMC_GETCONVERSIONMODE = 0x0001

# ========== 設定 ==========
ALWAYS_SHOW = False       # True: 常時表示 / False: 切替時のみ表示
HIDE_DELAY_MS = 800       # 切替時のみ表示の場合、消えるまでの時間(ms)
POS_FOLLOW_MS = 100       # 常時表示の場合、位置追従の間隔(ms)
POLL_INTERVAL = 0.05      # IME状態チェック間隔(秒)
FONT_SIZE = 14
OFFSET_X = 4              # キャレットからのX方向オフセット
OFFSET_Y = 8              # キャレットからのY方向オフセット
COLOR_JA = '#2563EB'      # 日本語モードの色(青)
COLOR_EN = '#444444'      # 英語モードの色(グレー)
OPACITY = 0.9
SHOW_ON_APP_SWITCH = True  # True: アプリ切替時もIME変化を表示 / False: 同一アプリ内の切替のみ
SHOW_ON_FOCUS = True       # True: テキスト入力欄にフォーカス時に表示 / False: IME切替時のみ
# ==========================


class GUITHREADINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", w.DWORD),
        ("flags", w.DWORD),
        ("hwndActive", w.HWND),
        ("hwndFocus", w.HWND),
        ("hwndCapture", w.HWND),
        ("hwndMenuOwner", w.HWND),
        ("hwndMoveSize", w.HWND),
        ("hwndCaret", w.HWND),
        ("rcCaret", w.RECT),
    ]


def get_ime_status():
    hwnd = user32.GetForegroundWindow()
    if not hwnd:
        return 'en'
    ime_wnd = imm32.ImmGetDefaultIMEWnd(hwnd)
    if not ime_wnd:
        return 'en'
    open_status = user32.SendMessageW(ime_wnd, WM_IME_CONTROL, IMC_GETOPENSTATUS, 0)
    if not open_status:
        return 'en'
    conv_mode = user32.SendMessageW(ime_wnd, WM_IME_CONTROL, IMC_GETCONVERSIONMODE, 0)
    if conv_mode & 0x1:
        return 'ja'
    return 'en'


def get_caret_pos():
    """キャレット位置を画面座標で取得。戻り値: (x, y, has_caret)"""
    hwnd = user32.GetForegroundWindow()
    tid = user32.GetWindowThreadProcessId(hwnd, None)

    gui = GUITHREADINFO()
    gui.cbSize = ctypes.sizeof(GUITHREADINFO)

    if user32.GetGUIThreadInfo(tid, ctypes.byref(gui)) and gui.hwndCaret:
        pt = w.POINT(gui.rcCaret.left, gui.rcCaret.bottom)
        user32.ClientToScreen(gui.hwndCaret, ctypes.byref(pt))
        return pt.x, pt.y, True

    # フォールバック: マウスカーソル位置
    pt = w.POINT()
    user32.GetCursorPos(ctypes.byref(pt))
    return pt.x, pt.y, False


class iMe:
    def __init__(self):
        self.root = tk.Tk()
        self.root.overrideredirect(True)
        self.root.attributes('-topmost', True)
        self.root.attributes('-alpha', 0.0)
        self.root.configure(bg='#222222')

        self.label = tk.Label(
            self.root,
            text='',
            font=('Segoe UI', FONT_SIZE, 'bold'),
            fg='white',
            bg='#222222',
            padx=12,
            pady=4,
        )
        self.label.pack()

        self.prev_status = None
        self.prev_hwnd = None
        self.prev_has_caret = False
        self.hide_timer = None
        self.running = True

        self.root.after(500, self._startup_check)

        self.thread = threading.Thread(target=self._poll, daemon=True)
        self.thread.start()

        # Ctrl+Cで終了できるようにする
        signal.signal(signal.SIGINT, lambda *_: self.quit())
        self._check_interrupt()

    def _check_interrupt(self):
        """tkinterのメインループ中でもCtrl+Cを拾えるようにする"""
        if self.running:
            self.root.after(200, self._check_interrupt)

    def _startup_check(self):
        status = get_ime_status()
        if status == 'ja':
            self.show('あ', COLOR_JA)
        else:
            self.show('A', COLOR_EN)
        print(f'[iMe] 起動OK - 現在: {status}')
        print(f'[iMe] IMEを切り替えると表示されます。Ctrl+Cで終了。')

    def show(self, text, color):
        x, y, has_caret = get_caret_pos()
        self.label.config(text=text, bg=color)
        self.root.configure(bg=color)
        self.root.geometry(f'+{x + OFFSET_X}+{y + OFFSET_Y}')
        self.root.attributes('-alpha', OPACITY)
        self._current_text = text
        self._current_color = color

        if ALWAYS_SHOW and has_caret:
            # キャレット取れた: 常時表示で追従
            if self.hide_timer:
                self.root.after_cancel(self.hide_timer)
                self.hide_timer = None
            self._follow_caret()
        else:
            # キャレット取れない or 切替時のみモード: 一定時間後に消す
            if self.hide_timer:
                self.root.after_cancel(self.hide_timer)
            self.hide_timer = self.root.after(HIDE_DELAY_MS, self._hide)

    def _hide(self):
        self.root.attributes('-alpha', 0.0)
        self._following = False

    def _follow_caret(self):
        """常時表示モード: キャレット位置に追従。キャレット取れなくなったら消す"""
        self._following = True
        if not self.running or not ALWAYS_SHOW:
            return
        x, y, has_caret = get_caret_pos()
        if has_caret:
            self.root.geometry(f'+{x + OFFSET_X}+{y + OFFSET_Y}')
            self.root.after(POS_FOLLOW_MS, self._follow_caret)
        else:
            # キャレット取れなくなった→消す
            self._hide()

    def _should_show(self, changed, app_switched, caret_appeared):
        if changed and (not app_switched or SHOW_ON_APP_SWITCH):
            return True
        if ALWAYS_SHOW and self.prev_status is None:
            return True
        if SHOW_ON_FOCUS and caret_appeared:
            return True
        return False

    def _poll(self):
        while self.running:
            try:
                status = get_ime_status()
                hwnd = user32.GetForegroundWindow()
                _, _, has_caret = get_caret_pos()
                app_switched = self.prev_hwnd is not None and hwnd != self.prev_hwnd
                changed = self.prev_status is not None and status != self.prev_status
                caret_appeared = has_caret and not self.prev_has_caret

                if self._should_show(changed, app_switched, caret_appeared):
                    if status == 'ja':
                        self.root.after(0, self.show, 'あ', COLOR_JA)
                    else:
                        self.root.after(0, self.show, 'A', COLOR_EN)
                self.prev_status = status
                self.prev_hwnd = hwnd
                self.prev_has_caret = has_caret
            except Exception as e:
                print(f'[iMe] Error: {e}')
            time.sleep(POLL_INTERVAL)

    def quit(self):
        self.running = False
        self.root.destroy()

    def run(self):
        self.root.mainloop()


if __name__ == '__main__':
    print('[iMe] 起動中...')
    app = iMe()
    app.run()
