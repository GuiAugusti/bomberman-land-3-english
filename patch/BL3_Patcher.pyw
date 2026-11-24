#!/usr/bin/env python3
"""
BL3 English Patcher: applies the Bomberman Land 3 English patch (.bl3p), shipped with the patch.
Double-click this file (Windows runs .pyw files without a console window).
Needs Python 3 (standard library only) and bl3_apply_patch.py in the same folder.

The window is drawn in the style of the game's own menus (orange bands, purple field, glass
capsules with a fuse, gold prompts), with a plain progress bar.
The rounded font in fonts/ (M+ Rounded 1c, SIL Open Font License) is loaded for this program only
on Windows; elsewhere the window falls back to a system font. Credits shows the patch's logo once a
game image is chosen: the game's logo is read from that image (bl3_logo.py), with the project's own
ENGLISH! subtitle (images/) laid over it, so no game graphics ship with the patcher.
Cartoon sound effects (sounds/, the project's own, made by docs/tools/make_patcher_sounds.py) play
on Windows (winsound) and where afplay / paplay / aplay exist; the speaker button mutes them.
Nothing is picked automatically: the three steps start empty every time. It only notes the last
English game it made (shown in Details) and whether the sound is muted, in
%APPDATA%\\BL3_Patcher\\settings.json on Windows, ~/.config/bl3_patcher/settings.json elsewhere;
Clear deletes that folder.

The release also has it as a Windows .exe (no Python needed), built by the public repo's GitHub
workflow with PyInstaller from this same file (fonts/, sounds/ and images/ go inside it).
"""
import os, sys, json, math, time, queue, base64, shutil, threading, subprocess, traceback, webbrowser
import tkinter as tk
from tkinter import filedialog, font as tkfont

HERE = os.path.dirname(os.path.abspath(__file__))       # the patcher's files (fonts, sounds, images)
sys.path.insert(0, HERE)
# where the file pickers open: next to the patcher; for the .exe (PyInstaller) HERE is a temporary
# folder its files are unpacked to, so they open next to the .exe instead
START = os.path.dirname(sys.executable) if getattr(sys, 'frozen', False) else HERE
import bl3_apply_patch as core
try:
    import winsound                            # Windows: the sound effects (standard library)
except ImportError:
    winsound = None
try:
    import bl3_logo                            # the logo for Credits, read from the player's own disc image
except ImportError:
    bl3_logo = None

APP_TITLE = 'BL3 English Patcher'
WINDOW_TITLE = 'BL3 English Patcher'
PROJECT_URL = 'https://github.com/GuiAugusti/bomberman-land-3-english'
FONT_FILES = ('MPLUSRounded1c-Black.ttf', 'MPLUSRounded1c-ExtraBold.ttf')
HEAVY, BOLD = 'Rounded Mplus 1c Black', 'Rounded Mplus 1c ExtraBold'

# colours of the game's menus (TOP MENU / OPTIONS screens)
BAND, BAND_EDGE, STRIP, STRIP_LIGHT = '#fc8a44', '#da862a', '#fbbb54', '#f3ec7a'
FIELD, BLOB_GREEN, BLOB_BLUE, BLOB_LINE = '#8a6e9b', '#4b7c44', '#3d6183', '#231c33'
CAP_EDGE, CAP_EDGE_HI, CAP_TOP, CAP_BOTTOM = '#08b4d6', '#86ecff', '#7c7ec6', '#a8cdea'
CAP_WARN, INSET = '#ff6a4d', '#2b2e68'
BAR_DONE, BAR_DONE_HI = '#45c35a', '#a6f0a0'      # the progress bar when the patch is applied
OFF_TOP, OFF_BOTTOM, OFF_EDGE, OFF_INSET, OFF_TEXT, OFF_LINE = '#6f6a8c', '#8b88a7', '#9b98b5', '#4a4668', '#cfcbe0', '#3f3a58'
TEXT, TEXT_LINE = '#a8e8f2', '#252b6c'
PILL, PILL_EDGE, PILL_TEXT, PILL_OFF = '#ffcb53', '#e0962c', '#3d3653', '#efd9a6'
ROPE, ASH, BOMB, INK = '#d39a5c', '#4b4f63', '#231f38', '#1d1a2e'
LOG_BG = '#2a2140'

W = 740
TOP_H, FIELD_Y1 = 64, 404                     # top band height; bottom of the purple field
H_SMALL, H_BIG = 547, 699                     # window height without / with the details log

HINTS = {
    None: 'Everything is ready. Click the PATCH! bomb.',
    'src': 'Your own untouched .bin, extracted from your game disc in Redump format. It is only read, never changed.',
}

def settings_path():
    base = os.environ.get('APPDATA') if sys.platform.startswith('win') else None
    base = base or os.environ.get('XDG_CONFIG_HOME') or os.path.join(os.path.expanduser('~'), '.config')
    return os.path.join(base, 'BL3_Patcher' if sys.platform.startswith('win') else 'bl3_patcher', 'settings.json')

def load_settings():
    try:
        with open(settings_path(), encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}

def save_settings(data):
    path = settings_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        tmp = path + '.tmp'
        with open(tmp, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=1)
        os.replace(tmp, path)
    except OSError:
        pass                      # remembering paths is a convenience; never block patching

def output_name(src):
    """file name of the English image: the original's, with (Japan) turned into (English)"""
    stem = os.path.splitext(os.path.basename(src))[0] if src else 'Bomberman Land 3 (Japan)'
    stem = stem.replace('(Japan)', '(English)') if '(Japan)' in stem else stem + ' (English)'
    return stem + '.bin'

def show_in_folder(path):
    """open the folder that holds `path` (with the file selected, on Windows)"""
    try:
        if sys.platform.startswith('win'):
            subprocess.Popen(['explorer', '/select,', os.path.normpath(path)])
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', '-R', path])
        else:
            subprocess.Popen(['xdg-open', os.path.dirname(path)])
    except OSError:
        pass

def clear_saved_data():
    """delete the patcher's own folder (settings and anything else it saved); -> True if it is gone.
    Only that folder: the game images and the English game are never touched."""
    folder = os.path.dirname(settings_path())
    if os.path.basename(folder).lower() != 'bl3_patcher':
        return False
    shutil.rmtree(folder, ignore_errors=True)
    return not os.path.exists(folder)

PROJECT_LINK = 'github.com/GuiAugusti/bomberman-land-3-english'
CREDITS_NOTE = ('This game is very special to me. I hope you can have as much fun as I had finally realizing '
                'my dream of fully understanding it!')
CREDITS_ROWS = (('About', 'A free and independent, AI-assisted translation project. It is not for sale.'),
                ('Font', 'M+ Rounded 1c, SIL Open Font License'),
                ('Project page', PROJECT_LINK))
CREDITS_LEGAL = ('Bomberman Land 3 \u00a9 2005 Hudson Soft. This fan patch is not affiliated with or endorsed by '
                 'Hudson Soft or Konami.')

def animations_enabled():
    """False when Windows is set not to show animations (Settings > Accessibility > Visual effects)"""
    if sys.platform.startswith('win'):
        try:
            import ctypes
            on = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(on), 0):   # SPI_GETCLIENTAREAANIMATION
                return bool(on.value)
        except Exception:
            pass
    return True

def load_private_fonts():
    """make the bundled rounded font usable by this program only (Windows; nothing is installed)"""
    if not sys.platform.startswith('win'):
        return
    try:
        import ctypes
        for name in FONT_FILES:
            path = os.path.join(HERE, 'fonts', name)
            if os.path.isfile(path):
                ctypes.windll.gdi32.AddFontResourceExW(path, 0x10, 0)     # FR_PRIVATE
    except Exception:
        pass

# ---------------------------------------------------------------- sound effects
class Sounds:
    """the patcher's cartoon sound effects (sounds/*.wav, made by docs/tools/make_patcher_sounds.py):
    winsound on Windows; afplay (macOS) or paplay / aplay (Linux) when there; silent otherwise, when a
    file is missing, or when muted. One sound at a time: a new one cuts the one before."""
    def __init__(self):
        self.dir = os.path.join(HERE, 'sounds')
        self.muted = False
        self.proc = None
        self.player = None
        if not winsound:
            for cmd in (['afplay'], ['paplay'], ['aplay', '-q']):
                if shutil.which(cmd[0]):
                    self.player = cmd
                    break

    def play(self, name):
        if self.muted or not name:
            return
        path = os.path.join(self.dir, name + '.wav')
        if not os.path.isfile(path):
            return
        try:
            if winsound:
                winsound.PlaySound(path, winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)
            elif self.player:
                self._kill()
                self.proc = subprocess.Popen(self.player + [path], stdout=subprocess.DEVNULL,
                                             stderr=subprocess.DEVNULL)
        except Exception:
            pass

    def stop(self):
        try:
            if winsound:
                winsound.PlaySound(None, 0)
            else:
                self._kill()
        except Exception:
            pass

    def _kill(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
            except Exception:
                pass
        self.proc = None

SFX = Sounds()

# ---------------------------------------------------------------- drawing helpers
def rounded(x0, y0, x1, y1, r):
    """polygon points for a rounded rectangle (draw with smooth=True)"""
    r = max(1, min(r, (x1 - x0) / 2, (y1 - y0) / 2))
    return [x0 + r, y0, x0 + r, y0, x1 - r, y0, x1 - r, y0, x1, y0, x1, y0 + r, x1, y0 + r,
            x1, y1 - r, x1, y1 - r, x1, y1, x1 - r, y1, x1 - r, y1, x0 + r, y1, x0 + r, y1,
            x0, y1, x0, y1 - r, x0, y1 - r, x0, y0 + r, x0, y0 + r, x0, y0]

def stadium(x0, y0, x1, y1, n=28):
    """polygon points of a pill with exact half-circle ends (no smoothing): the same shape the
    Apply button's rainbow slices fill, so its edge sits right on them"""
    r = (y1 - y0) / 2
    cy = y0 + r
    pts = []
    for k in range(n + 1):                        # right end, top to bottom
        a = -math.pi / 2 + math.pi * k / n
        pts += [x1 - r + r * math.cos(a), cy + r * math.sin(a)]
    for k in range(n + 1):                        # left end, bottom to top
        a = math.pi / 2 + math.pi * k / n
        pts += [x0 + r + r * math.cos(a), cy + r * math.sin(a)]
    return pts


def star(cx, cy, ro, ri, n=8, rot=0.0):
    pts = []
    for k in range(2 * n):
        a = rot + math.pi * k / n - math.pi / 2
        r = ro if k % 2 == 0 else ri
        pts += [cx + r * math.cos(a), cy + r * math.sin(a)]
    return pts


class Painter:
    """a canvas plus the scale factor (high-DPI screens) and the fonts; coordinates are given in
    96-dpi pixels and scaled here"""
    def __init__(self, canvas, S, fonts):
        self.c, self.S, self.fonts = canvas, S, fonts

    def f(self, kind, px):
        fam, weight = self.fonts[kind]
        return (fam, -max(1, int(round(px * self.S))), weight)

    def p(self, *v):
        return [x * self.S for x in v]

    def w(self, px):
        return max(1, round(px * self.S))

    def rrect(self, x0, y0, x1, y1, r, fill, outline='', width=0, **kw):
        return self.c.create_polygon(rounded(*self.p(x0, y0, x1, y1, r)), smooth=True, fill=fill,
                                     outline=outline, width=self.w(width) if width else 0, **kw)

    def text(self, x, y, text, kind, px, fill=TEXT, outline=TEXT_LINE, ow=2.0, anchor='center', tags=(), **kw):
        """text in the game's style: light fill inside a dark outline (the text drawn around itself)"""
        X, Y = self.p(x, y)
        ids = []
        if outline:
            o = ow * self.S
            for k in range(12):
                a = 2 * math.pi * k / 12
                ids.append(self.c.create_text(X + o * math.cos(a), Y + o * math.sin(a), text=text,
                                              font=self.f(kind, px), fill=outline, anchor=anchor, tags=tags, **kw))
        ids.append(self.c.create_text(X, Y, text=text, font=self.f(kind, px), fill=fill, anchor=anchor,
                                      tags=tags, **kw))
        return ids

    def bomb(self, cx, cy, r, cap_angle=-150, tags=()):
        """a cartoon bomb; returns the point where its fuse starts (top of the cap)"""
        c, S = self.c, self.S
        X, Y, R = cx * S, cy * S, r * S
        lw = self.w(3)
        a = math.radians(cap_angle)
        ux, uy = math.cos(a), math.sin(a)
        w, h = R * 0.36, R * 0.42
        bx, by = X + ux * R * 0.88, Y + uy * R * 0.88
        px_, py_ = -uy, ux
        cap = [bx + px_ * w, by + py_ * w, bx + px_ * w + ux * h, by + py_ * w + uy * h,
               bx - px_ * w + ux * h, by - py_ * w + uy * h, bx - px_ * w, by - py_ * w]
        c.create_polygon(cap, fill='#8d8fb8', outline=INK, width=lw, tags=tags)
        c.create_oval(X - R, Y - R, X + R, Y + R, fill=BOMB, outline=INK, width=lw, tags=tags)
        c.create_oval(X - R * 0.58, Y - R * 0.62, X - R * 0.18, Y - R * 0.3, fill='#ffffff', outline='', tags=tags)
        c.create_oval(X - R * 0.62, Y - R * 0.16, X - R * 0.44, Y + R * 0.02, fill='#7d7aa8', outline='', tags=tags)
        return (bx + ux * h) / S, (by + uy * h) / S

    def heart(self, cx, cy, r, fill='#ff466e', outline='#780a28', tags=()):
        pts = []
        for k in range(48):
            t = 2 * math.pi * k / 48
            pts += self.p(cx + r * 16 * math.sin(t) ** 3 / 17,
                          cy - r * (13 * math.cos(t) - 5 * math.cos(2 * t) - 2 * math.cos(3 * t) - math.cos(4 * t)) / 17)
        return self.c.create_polygon(pts, fill=fill, outline=outline, width=self.w(2.5), tags=tags)

    def spark(self, x, y, r, tags=()):
        X, Y, R = x * self.S, y * self.S, r * self.S
        a = self.c.create_polygon(star(X, Y, R, R * 0.45, 8), fill='#ffe34d', outline='#ff7a1a',
                                  width=self.w(2), tags=tags)
        b = self.c.create_oval(X - R * 0.28, Y - R * 0.28, X + R * 0.28, Y + R * 0.28, fill='#ffffff', outline='', tags=tags)
        return a, b


class Pressable:
    """hover and press for a button drawn as a group of canvas items (all tagged self.tag). It counts
    as under the mouse while the pointer is inside the group's box, checked every 40 ms while it is,
    not by Enter / Leave per item: moving between the pill and its letters, or the pill sinking when
    pressed, made it flicker and drop clicks at the edges."""
    hot_ones = set()

    def _bind(self):
        self.hot = self.down = False
        for ev, fn in (('<Enter>', self.enter), ('<ButtonPress-1>', self.press), ('<ButtonRelease-1>', self.release)):
            self.c.tag_bind(self.tag, ev, fn)

    def available(self):
        return True

    def look(self, hot):
        pass

    def inside(self, x=None, y=None):
        try:
            if x is None:
                x = self.c.winfo_pointerx() - self.c.winfo_rootx()
                y = self.c.winfo_pointery() - self.c.winfo_rooty()
            b = self.c.bbox(self.tag)
        except tk.TclError:
            return False
        return bool(b) and b[0] - 1 <= x <= b[2] + 1 and b[1] - 1 <= y <= b[3] + 1

    def enter(self, e=None):
        if self.hot:
            return
        self.hot = True
        Pressable.hot_ones.add(self)
        self.look(True)
        self._watch()

    def _watch(self, outside=0):
        if not self.hot:
            return
        outside = 0 if self.inside() else outside + 1
        if outside >= 2:                          # out for two checks in a row: gone
            return self.leave()
        try:
            self.c.after(40, self._watch, outside)
        except tk.TclError:
            self.hot = False
            Pressable.hot_ones.discard(self)

    def leave(self, e=None):
        self.hot = False
        Pressable.hot_ones.discard(self)
        if self.down:
            self.c.move(self.face, 0, -2 * self.pt.S); self.down = False
        self.look(False)
        if not any(b.c is self.c for b in Pressable.hot_ones):   # not already over the next button
            try:
                self.c.configure(cursor='')
            except tk.TclError:
                pass

    def press(self, e=None):
        if not self.available():
            SFX.play('bonk')
        elif not self.down:
            SFX.play('click')
            self.c.move(self.face, 0, 2 * self.pt.S); self.down = True

    def release(self, e=None):
        if self.down:
            self.c.move(self.face, 0, -2 * self.pt.S); self.down = False
            if self.available() and e is not None and self.inside(e.x, e.y):
                self.command()


class Prompt(Pressable):
    """a button prompt as in the game's top band: a gold pill"""
    def __init__(self, pt, x1, y, label, command, h=32, px=16, anchor='e'):
        self.pt, self.c, S = pt, pt.c, pt.S
        self.command, self.enabled = command, True
        self.tag = 'p%d' % id(self); self.face = self.tag + 'f'
        tw = tkfont.Font(pt.c, font=pt.f('heavy', px)).measure(label) / S
        w = tw + max(34, h * 1.1)
        x0 = x1 - w if anchor == 'e' else x1
        x1 = x0 + w
        self.box = (x0, y, x1, y + h)
        self.base = pt.rrect(x0, y + 3, x1, y + h + 3, h / 2, PILL_EDGE, tags=(self.tag,))
        self.pill = pt.rrect(x0, y, x1, y + h, h / 2, PILL, outline=PILL_EDGE, width=2, tags=(self.tag, self.face))
        self.label = pt.text((x0 + x1) / 2, y + h / 2 + 1, label, 'heavy', px, fill=PILL_TEXT, outline='#fff3d0',
                             ow=1.4, tags=(self.tag, self.face))
        self._bind()

    def available(self):
        return self.enabled

    def look(self, hot):
        if hot:
            if self.enabled:
                SFX.play('hover')
                self.c.itemconfigure(self.pill, fill='#ffd977')
                self.c.configure(cursor='hand2')
        else:
            self.c.itemconfigure(self.pill, fill=PILL if self.enabled else PILL_OFF)

    def set_enabled(self, on):
        self.enabled = on
        self.c.itemconfigure(self.pill, fill=PILL if on else PILL_OFF, outline=PILL_EDGE)
        self.c.itemconfigure(self.base, fill=PILL_EDGE)
        self.c.itemconfigure(self.label[-1], fill=PILL_TEXT if on else '#a8987a')
        for i in self.label[:-1]:
            self.c.itemconfigure(i, state='normal' if on else 'hidden')


class BombButton(Pressable):
    """the patch button: a big cartoon bomb with PATCH! across it and a crackling fuse. The mouse
    over it makes it glow and jiggle; clicking it starts the patch, and the bomb explodes (a burst,
    then puffs of smoke) before it comes back. While it isn't available it is pale, its fuse out."""
    BODY, CAP, HI, DOT = BOMB, '#8d8fb8', '#ffffff', '#7d7aa8'
    OFF = dict(body='#9b97b6', cap='#c4c2d8', hi='#e9e7f4', dot='#b3b0cb', text='#f4f1fb', shadow='#7f7b99')

    def __init__(self, pt, cx, cy, r, label, command):
        self.pt, self.c, S = pt, pt.c, pt.S
        self.command, self.enabled = command, True
        self.tag = 'bombbtn%d' % id(self); self.face = self.tag + 'f'
        self.cx, self.cy, self.r = cx, cy, r
        F = (self.tag, self.face)
        c = self.c
        lw = pt.w(3.5)
        X, Y, R = cx * S, cy * S, r * S
        self.glow = c.create_oval(X - R - 7 * S, Y - R - 7 * S, X + R + 7 * S, Y + R + 7 * S, fill='',
                                  outline='#ffe34d', width=pt.w(4), state='hidden', tags=F)
        a = math.radians(-60)                          # the cap leans to the upper right
        ux, uy = math.cos(a), math.sin(a)
        w, h = R * 0.34, R * 0.38
        bx, by = X + ux * R * 0.88, Y + uy * R * 0.88
        px_, py_ = -uy, ux
        cap = [bx + px_ * w, by + py_ * w, bx + px_ * w + ux * h, by + py_ * w + uy * h,
               bx - px_ * w + ux * h, by - py_ * w + uy * h, bx - px_ * w, by - py_ * w]
        self.cap = c.create_polygon(cap, fill=self.CAP, outline=INK, width=lw, tags=F)
        fx, fy = (bx + ux * h) / S, (by + uy * h) / S
        self.spark_at = (fx + 13, fy - 12)
        fuse = pt.p(fx, fy, fx + 3, fy - 10, self.spark_at[0], self.spark_at[1])
        c.create_line(*fuse, smooth=True, fill=INK, width=pt.w(6), capstyle='round', tags=F)
        self.rope = c.create_line(*fuse, smooth=True, fill=ROPE, width=pt.w(3), capstyle='round', tags=F)
        self.body = c.create_oval(X - R, Y - R, X + R, Y + R, fill=self.BODY, outline=INK, width=lw, tags=F)
        self.hi = c.create_oval(X - R * 0.6, Y - R * 0.66, X - R * 0.2, Y - R * 0.34, fill=self.HI, outline='', tags=F)
        self.dot = c.create_oval(X - R * 0.66, Y - R * 0.2, X - R * 0.46, Y, fill=self.DOT, outline='', tags=F)
        self.spark_ids = pt.spark(*self.spark_at, 9, tags=F)
        # PATCH! across the bomb, tilted a little, white with a hard shadow
        font = pt.f('heavy', 22)
        self.label = [c.create_text(X + 2 * S, Y + 6 * S, text=label, font=font, fill='#160f26', angle=8, tags=F),
                      c.create_text(X, Y + 4 * S, text=label, font=font, fill='#ffffff', angle=8, tags=F)]
        b = c.bbox(self.tag)
        self.box = (b[0] / S, b[1] / S, b[2] / S, b[3] / S)
        self.wiggle = 0.0                              # how far the face is moved sideways now
        self.exploding = False
        self.t = 0.0
        self._bind()

    def available(self):
        return self.enabled and not self.exploding

    def look(self, hot):
        if not self.enabled or self.exploding:
            return
        self.c.itemconfigure(self.glow, state='normal' if hot else 'hidden')
        if hot:
            SFX.play('hover')
            self.c.configure(cursor='hand2')
        elif self.wiggle:
            self.c.move(self.face, -self.wiggle * self.pt.S, 0); self.wiggle = 0.0

    def set_enabled(self, on):
        self.enabled = on
        if self.exploding:
            return
        self.paint(on)

    def paint(self, on):
        c, o = self.c, self.OFF
        c.itemconfigure(self.body, fill=self.BODY if on else o['body'])
        c.itemconfigure(self.cap, fill=self.CAP if on else o['cap'])
        c.itemconfigure(self.hi, fill=self.HI if on else o['hi'])
        c.itemconfigure(self.dot, fill=self.DOT if on else o['dot'])
        c.itemconfigure(self.label[0], fill='#160f26' if on else o['shadow'])
        c.itemconfigure(self.label[1], fill='#ffffff' if on else o['text'])
        c.itemconfigure(self.rope, fill=ROPE if on else ASH)
        for i in self.spark_ids:
            c.itemconfigure(i, state='normal' if on else 'hidden')
        if not on:
            c.itemconfigure(self.glow, state='hidden')

    def animate(self, t):
        """one frame: the spark crackles; under the mouse the bomb glows and jiggles"""
        self.t = t
        if not self.enabled or self.exploding:
            return
        c, S = self.c, self.pt.S
        if self.hot:
            want = 1.6 * math.sin(t * 38)
            c.move(self.face, (want - self.wiggle) * S, 0); self.wiggle = want
            c.itemconfigure(self.glow, width=self.pt.w(3.5 + 1.5 * (0.5 + 0.5 * math.sin(t * 9))))
        dy = 2 * S if self.down else 0
        x, y = self.spark_at[0] + self.wiggle, self.spark_at[1]
        sr = (11 if self.hot else 9) + 1.8 * math.sin(t * 23) + 1.0 * math.sin(t * 37)
        star_id, dot = self.spark_ids
        c.coords(star_id, *star(x * S, y * S + dy, sr * S, sr * S * 0.42, 8, t * 5))
        c.coords(dot, (x - 2.8) * S, (y - 2.8) * S + dy, (x + 2.8) * S, (y + 2.8) * S + dy)
        c.itemconfigure(star_id, fill='#fff6b0' if int(t * 14) % 3 == 0 else '#ffe34d')

    def explode(self, done=None):
        """BOOM: the bomb vanishes in a burst and puffs of smoke, then comes back (pale while busy)"""
        c, S, pt = self.c, self.pt.S, self.pt
        self.exploding = True
        if self.down:
            c.move(self.face, 0, -2 * S); self.down = False
        if self.wiggle:
            c.move(self.face, -self.wiggle * S, 0); self.wiggle = 0.0
        c.itemconfigure(self.face, state='hidden')
        SFX.play('blast')
        X, Y = self.cx * S, self.cy * S
        burst = c.create_polygon(star(X, Y, 10 * S, 6 * S, 12, 0.2), fill='#ffe34d', outline='#e0401c',
                                 width=pt.w(4), joinstyle='round')
        core = c.create_polygon(star(X, Y, 5 * S, 3 * S, 12, 0.5), fill='#ffffff', outline='')
        c.tag_raise(burst); c.tag_raise(core)
        puffs = []
        for k in range(6):
            ang = k * math.pi / 3 + 0.4
            puffs.append((c.create_oval(0, 0, 0, 0, fill='#5d5670', outline=INK, width=pt.w(2), state='hidden'),
                          math.cos(ang), math.sin(ang) * 0.8, 9 + (k % 3) * 3))
        frames = 18

        def step(k=0):
            try:
                if k < 7:                                  # the burst grows, spinning
                    rr = (14 + k * 7.5) * S                    # up to about 60 px
                    c.coords(burst, *star(X, Y, rr, rr * 0.58, 12, 0.2 + k * 0.12))
                    c.coords(core, *star(X, Y, rr * 0.5, rr * 0.3, 12, 0.5 - k * 0.1))
                    c.itemconfigure(burst, fill='#ffe34d' if k % 2 else '#ffb31a')
                elif k == 7:
                    c.delete(burst); c.delete(core)
                if k >= 5:                                 # smoke puffs drift out and shrink away
                    u = (k - 5) / (frames - 5)
                    for pid, dx, dy, size in puffs:
                        rr = size * (1.0 + 0.8 * u) * (1 - u) + 1
                        px, py = X + dx * (28 + 30 * u) * S, Y + dy * (28 + 30 * u) * S - 10 * u * S
                        c.coords(pid, px - rr * S, py - rr * S, px + rr * S, py + rr * S)
                        grey = int(0x5d + (0xb8 - 0x5d) * u)
                        c.itemconfigure(pid, state='normal', fill='#%02x%02x%02x' % (grey, grey - 6, grey + 14))
                if k < frames:
                    c.after(30, step, k + 1)
                    return
                for pid, *_ in puffs:
                    c.delete(pid)
                self.exploding = False
                c.itemconfigure(self.face, state='normal')
                c.itemconfigure(self.glow, state='hidden')
                self.paint(self.enabled)
                if done:
                    done()
            except tk.TclError:
                pass
        step()

    def press(self, e=None):
        if not self.available():
            if not self.exploding:
                SFX.play('bonk')
        elif not self.down:
            SFX.play('click')
            self.c.move(self.face, 0, 2 * self.pt.S); self.down = True

    def release(self, e=None):
        if self.down:
            self.c.move(self.face, 0, -2 * self.pt.S); self.down = False
            if self.available() and e is not None and self.inside(e.x, e.y):
                self.command()

    def leave(self, e=None):
        if self.wiggle:
            self.c.move(self.face, -self.wiggle * self.pt.S, 0); self.wiggle = 0.0
        if self.down:
            self.c.move(self.face, 0, -2 * self.pt.S); self.down = False
        self.c.itemconfigure(self.glow, state='hidden')
        Pressable.leave(self, e)


class SoundButton(Pressable):
    """a round gold prompt with a speaker on it: sound on (waves) or off (a cross)"""
    def __init__(self, pt, x1, y, command, h=30):
        self.pt, self.c = pt, pt.c
        self.command = command
        self.tag = 'snd%d' % id(self); self.face = self.tag + 'f'
        x0 = x1 - h
        self.box = (x0, y, x1, y + h)
        pt.rrect(x0, y + 3, x1, y + h + 3, h / 2, PILL_EDGE, tags=(self.tag,))
        self.pill = pt.rrect(x0, y, x1, y + h, h / 2, PILL, outline=PILL_EDGE, width=2, tags=(self.tag, self.face))
        cx, cy = x0 + h * 0.42, y + h / 2              # the speaker's mouth
        body = [cx - 8, cy - 3.5, cx - 4, cy - 3.5, cx + 1, cy - 8, cx + 1, cy + 8, cx - 4, cy + 3.5, cx - 8, cy + 3.5]
        self.c.create_polygon(pt.p(*body), fill=PILL_TEXT, outline=PILL_TEXT, width=pt.w(1), joinstyle='round',
                              tags=(self.tag, self.face))
        self.on_ids = [self.c.create_arc(*pt.p(cx + 1 - r, cy - r, cx + 1 + r, cy + r), start=-48, extent=96,
                                         style='arc', outline=PILL_TEXT, width=pt.w(2.2),
                                         tags=(self.tag, self.face)) for r in (5, 9.5)]
        self.off_ids = [self.c.create_line(*pt.p(cx + 5, cy - 4.5, cx + 13, cy + 4.5), fill=PILL_TEXT, width=pt.w(2.6),
                                           capstyle='round', tags=(self.tag, self.face)),
                        self.c.create_line(*pt.p(cx + 5, cy + 4.5, cx + 13, cy - 4.5), fill=PILL_TEXT, width=pt.w(2.6),
                                           capstyle='round', tags=(self.tag, self.face))]
        self._bind()

    def show(self, on):
        for i in self.on_ids:
            self.c.itemconfigure(i, state='normal' if on else 'hidden')
        for i in self.off_ids:
            self.c.itemconfigure(i, state='hidden' if on else 'normal')

    def look(self, hot):
        self.c.itemconfigure(self.pill, fill='#ffd977' if hot else PILL)
        if hot:
            self.c.configure(cursor='hand2')
            SFX.play('hover')


class Popup(tk.Toplevel):
    """message window in the same style; returns the label of the prompt pressed (None if closed)"""
    TITLES = {'done': 'Patch applied', 'error': "Can't continue", 'question': 'File already exists'}

    SOUNDS = {'error': 'bonk', 'question': 'pop', 'info': 'pop'}

    def __init__(self, app, kind, message, buttons=('OK',), title=None, default=None, sound=None):
        super().__init__(app)
        self.withdraw()
        self.title(WINDOW_TITLE)
        self.resizable(False, False)
        self.result = None
        S = app.S
        w = 480
        c = tk.Canvas(self, width=w * S, height=10, highlightthickness=0, bg=FIELD)
        c.pack()
        pt = Painter(c, S, app.fonts)
        probe = c.create_text(0, 0, text=message, font=pt.f('bold', 15), width=(w - 48) * S, anchor='nw')
        th = (c.bbox(probe)[3] - c.bbox(probe)[1]) / S
        c.delete(probe)
        h = 56 + 22 + th + 22 + 56
        c.configure(height=h * S)
        c.create_rectangle(0, 0, w * S, 48 * S, fill=BAND, outline='')
        c.create_rectangle(0, 46 * S, w * S, 51 * S, fill=STRIP, outline='')
        c.create_rectangle(0, 51 * S, w * S, 53 * S, fill=STRIP_LIGHT, outline='')
        c.create_rectangle(0, 53 * S, w * S, 56 * S, fill=BAND_EDGE, outline='')
        pt.text(22, 24, title or self.TITLES.get(kind, APP_TITLE), 'heavy', 22, anchor='w')
        c.create_text(24 * S, 78 * S, text=message, font=pt.f('bold', 15), width=(w - 48) * S, anchor='nw',
                      fill='#ffffff')
        x1 = w - 18
        for label in reversed(buttons):
            p = Prompt(pt, x1, h - 48, label, lambda l=label: self.finish(l))
            x1 = p.box[0] - 12
        self.protocol('WM_DELETE_WINDOW', lambda: self.finish(None))
        self.bind('<Return>', lambda e: self.finish(default or buttons[0]))
        self.bind('<Escape>', lambda e: self.finish(buttons[-1]))
        self.transient(app)
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry('+%d+%d' % (max(0, x), max(0, y)))
        self.deiconify()
        SFX.play(self.SOUNDS.get(kind) if sound is None else sound)
        self.grab_set()
        self.focus_set()
        app.wait_window(self)

    def finish(self, label):
        self.result = label
        self.grab_release()
        self.destroy()


class Credits(tk.Toplevel):
    """the credits, laid out like the game's own credits screen: the logo, the facts, the note"""
    def __init__(self, app):
        super().__init__(app)
        self.withdraw()
        self.title(WINDOW_TITLE)
        self.resizable(False, False)
        S = app.S
        w = 600
        c = tk.Canvas(self, width=w * S, height=10, highlightthickness=0, bg=FIELD)
        c.pack()
        pt = Painter(c, S, app.fonts)

        def height(text, kind, px, width):
            i = c.create_text(0, 0, text=text, font=pt.f(kind, px), width=width * S, anchor='nw')
            b = c.bbox(i); c.delete(i)
            return (b[3] - b[1]) / S

        # header band, as on the message windows
        c.create_rectangle(0, 0, w * S, 48 * S, fill=BAND, outline='')
        c.create_rectangle(0, 46 * S, w * S, 51 * S, fill=STRIP, outline='')
        c.create_rectangle(0, 51 * S, w * S, 53 * S, fill=STRIP_LIGHT, outline='')
        c.create_rectangle(0, 53 * S, w * S, 56 * S, fill=BAND_EDGE, outline='')
        pt.text(22, 24, 'Credits', 'heavy', 22, anchor='w')

        # the patch's logo (from the player's own disc image) once a game image is chosen; before
        # that, no title. No version: the patcher is one, the patches have versions
        logo = app.credits_logo()
        if logo:
            png, lw, lh, _box = logo
            self.logo_img = tk.PhotoImage(data=base64.b64encode(png).decode('ascii'))   # kept: Tk drops it otherwise
            c.create_image(w / 2 * S, 70 * S, image=self.logo_img, anchor='n')
            y = 70 + lh / S + 18
        else:
            y = 78

        # the facts: a label column and a value column
        lw = max(tkfont.Font(c, font=pt.f('heavy', 15)).measure(k) for k, v in CREDITS_ROWS) / S + 18
        for key, value in CREDITS_ROWS:
            vh = height(value, 'bold', 15, w - 48 - lw)
            pt.text(24, y, key, 'heavy', 15, anchor='nw', ow=1.6)
            if value == PROJECT_LINK:
                link = c.create_text((24 + lw) * S, y * S, text=value, font=pt.f('bold', 15), fill='#bfe3ff',
                                     anchor='nw')
                c.tag_bind(link, '<Enter>', lambda e, i=link: (c.itemconfigure(i, fill='#ffffff', font=pt.f('bold', 15) + ('underline',)),
                                                               c.configure(cursor='hand2'), SFX.play('hover')))
                c.tag_bind(link, '<Leave>', lambda e, i=link: (c.itemconfigure(i, fill='#bfe3ff', font=pt.f('bold', 15)),
                                                               c.configure(cursor='')))
                c.tag_bind(link, '<ButtonRelease-1>', lambda e: (SFX.play('click'), webbrowser.open(PROJECT_URL)))
            else:
                c.create_text((24 + lw) * S, y * S, text=value, font=pt.f('bold', 15), fill='#ffffff',
                              width=(w - 48 - lw) * S, anchor='nw')
            y += max(vh, 20) + 10
        y += 12                                       # room for the note's heart

        # the note, in one of the menus' glass capsules, with a heart where the fuse would be
        nh = height(CREDITS_NOTE, 'bold', 16, w - 96)
        x0, x1, y1 = 24, w - 24, y + nh + 30
        pt.rrect(x0, y, x1, y1, 22, CAP_TOP, outline=CAP_EDGE, width=3.5)
        pt.rrect(x0 + 4, y + (y1 - y) * 0.5, x1 - 4, y1 - 4, 18, CAP_BOTTOM)
        pt.rrect(x0 + 12, y + 10, x1 - 12, y1 - 10, 12, INSET)
        c.create_text((x0 + 26) * S, (y + 15) * S, text=CREDITS_NOTE, font=pt.f('bold', 16), fill='#ffe6aa',
                      width=(w - 96) * S, anchor='nw')
        pt.heart(x1 - 22, y + 4, 15)
        y = y1 + 22

        # the small print, under a rule
        y += 2
        c.create_line(24 * S, y * S, (w - 24) * S, y * S, fill='#b49cc6', width=pt.w(2))
        y += 12
        gh = height(CREDITS_LEGAL, 'bold', 13, w - 48)
        c.create_text(24 * S, y * S, text=CREDITS_LEGAL, font=pt.f('bold', 13), fill='#ddd2e8',
                      width=(w - 48) * S, anchor='nw')
        y += gh + 20

        # prompts
        h = y + 32 + 22
        c.configure(height=h * S)
        close = Prompt(pt, w - 18, y, 'Close', self.destroy)
        Prompt(pt, close.box[0] - 12, y, 'Open GitHub page', lambda: webbrowser.open(PROJECT_URL))
        self.protocol('WM_DELETE_WINDOW', self.destroy)
        self.bind('<Return>', lambda e: self.destroy())
        self.bind('<Escape>', lambda e: self.destroy())
        self.transient(app)
        self.update_idletasks()
        x = app.winfo_rootx() + (app.winfo_width() - self.winfo_reqwidth()) // 2
        y = app.winfo_rooty() + (app.winfo_height() - self.winfo_reqheight()) // 3
        self.geometry('+%d+%d' % (max(0, x), max(0, y)))
        self.deiconify()
        self.grab_set()
        self.focus_set()
        app.wait_window(self)


class App(tk.Tk):
    def __init__(self, src=None, patch=None, dst=None):
        load_private_fonts()
        super().__init__()
        self.title(WINDOW_TITLE)
        self.resizable(False, False)
        self.S = S = max(1.0, self.winfo_fpixels('1i') / 96.0)
        self.fonts = self.pick_fonts()
        self.q = queue.Queue()        # log lines and the final result from the worker thread
        self.prog = None              # latest (fraction, label) from the worker, read by poll()
        self.shown = None
        self.worker = None
        self.busy = False
        self.tick = 0
        self.details = False
        self.focus_step = None        # the capsule under the mouse / with the keyboard focus
        self.locked_key = None        # a locked capsule under the mouse (its help says what comes first)
        self.message = None           # (text, colour) of the last progress / result message
        self.patch_note = ''
        self.patch_ok = False
        self.settings = load_settings()
        SFX.muted = bool(self.settings.get('muted'))
        self.logo_cache, self.logo_lock, self.logo_busy = {}, threading.Lock(), False
        last = self.settings.get('last_output') or ''
        self.last_output = last if os.path.isfile(last) else None

        src, patch, dst = src or '', patch or '', dst or ''   # nothing is picked automatically
        if dst.lower().endswith('.bin'):
            dst = os.path.dirname(dst)
        self.v_src = tk.StringVar(value=src)
        self.v_patch = tk.StringVar(value=patch)
        self.v_dst = tk.StringVar(value=dst)       # a folder: the file name comes from the original's

        self.c = tk.Canvas(self, width=W * S, height=H_SMALL * S, highlightthickness=0, bg=FIELD)
        self.c.pack()
        self.pt = Painter(self.c, S, self.fonts)
        self.icon()
        self.draw_field()
        self.draw_capsules()
        self.draw_bands()
        self.draw_progress()
        self.draw_log()

        self.v_patch.trace_add('write', lambda *a: self.refresh_info())
        self.v_src.trace_add('write', self._src_changed)
        self.v_dst.trace_add('write', lambda *a: (self.new_input(), self.check_files(), self.show_help()))
        self.refresh_info()
        if self.last_output:
            self.write('Last patched image: %s' % self.last_output, 'ok')
        self.bind('<Return>', lambda e: self.start())
        self.after(100, self.poll)

    # ---- fonts and icon ----
    def pick_fonts(self):
        have = set(tkfont.families(self))
        def first(*cands):
            for fam, weight in cands:
                if fam in have:
                    return fam, weight
            return 'TkDefaultFont', 'bold'
        heavy = first((HEAVY, 'normal'), ('Arial Rounded MT Bold', 'normal'), ('Segoe UI Black', 'normal'),
                      ('Arial Black', 'normal'), ('DejaVu Sans', 'bold'), ('Helvetica', 'bold'))
        bold = first((BOLD, 'normal'), ('Arial Rounded MT Bold', 'normal'), ('Segoe UI Semibold', 'normal'),
                     ('Segoe UI', 'bold'), ('DejaVu Sans', 'bold'), ('Helvetica', 'bold'))
        mono = first(('Consolas', 'normal'), ('DejaVu Sans Mono', 'normal'), ('Courier New', 'normal'))
        return {'heavy': heavy, 'bold': bold, 'mono': mono}

    def icon(self):
        try:                                    # a little bomb for the title bar and taskbar
            n = 32; img = tk.PhotoImage(width=n, height=n)
            for y in range(n):
                for x in range(n):
                    dx, dy = x - 14.5, y - 18.5
                    d = math.hypot(dx, dy)
                    if 21 <= x <= 26 and 3 <= y <= 9 and abs((x - 21) - (9 - y)) <= 1: col = '#ffb000'
                    elif 19 <= x <= 24 and 6 <= y <= 11: col = '#8d8fb8'
                    elif d <= 11: col = '#ffffff' if math.hypot(dx + 4, dy + 4) <= 3 else BOMB
                    elif d <= 13: col = INK
                    else: continue
                    img.put(col, (x, y))
            self.iconphoto(True, img)
            self._icon = img
        except tk.TclError:
            pass

    # ---- the screen: purple field with big outlined blobs, orange bands top and bottom ----
    # each blob: centre, radius, colour, and its slow wandering path (amplitudes in px, periods in s)
    BLOBS = ((96, 470, 150, BLOB_BLUE, 46, 30, 16, 12), (330, 60, 120, BLOB_GREEN, 52, 36, 14, 18),
             (560, 470, 130, BLOB_GREEN, 40, 34, 19, 13), (760, 140, 140, BLOB_BLUE, 44, 50, 12, 17),
             (-40, 170, 110, BLOB_GREEN, 38, 46, 15, 11), (470, 250, 60, BLOB_BLUE, 56, 40, 11, 14),
             (250, 330, 80, BLOB_BLUE, 48, 34, 17, 13))

    def draw_field(self):
        c, S = self.c, self.S
        c.create_rectangle(0, 0, W * S, H_BIG * S, fill=FIELD, outline='')
        self.blobs = []
        for cx, cy, r, col, ax, ay, px, py in self.BLOBS:
            item = c.create_oval((cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S, fill=col,
                                 outline=BLOB_LINE, width=self.pt.w(4))
            self.blobs.append((item, cx, cy, r, ax, ay, 2 * math.pi / px, 2 * math.pi / py, cx * 0.013, cy * 0.017))
        self.t0 = time.monotonic()
        if animations_enabled():
            self.after(40, self.drift)

    def drift(self):
        """the blobs wander slowly behind everything, as on the game's menu screens; Apply patch's
        rainbow flows (with its glint, sparkles and spark) while it is available"""
        t = time.monotonic() - self.t0
        S = self.S
        if getattr(self, 'b_apply', None):
            self.b_apply.animate(t)
        for item, cx, cy, r, ax, ay, wx, wy, ph, qh in self.blobs:
            x = cx + ax * math.sin(wx * t + ph) + ax * 0.35 * math.sin(wx * 2.7 * t + qh)
            y = cy + ay * math.cos(wy * t + qh) + ay * 0.35 * math.sin(wy * 1.9 * t + ph)
            self.c.coords(item, (x - r) * S, (y - r) * S, (x + r) * S, (y + r) * S)
        self.after(40, self.drift)

    def draw_bands(self):
        c, pt, S = self.c, self.pt, self.S
        # top band
        c.create_rectangle(0, 0, W * S, TOP_H * S, fill=BAND, outline='')
        c.create_rectangle(0, (TOP_H - 2) * S, W * S, (TOP_H + 3) * S, fill=STRIP, outline='')
        c.create_rectangle(0, (TOP_H + 3) * S, W * S, (TOP_H + 5) * S, fill=STRIP_LIGHT, outline='')
        c.create_rectangle(0, (TOP_H + 5) * S, W * S, (TOP_H + 8) * S, fill=BAND_EDGE, outline='')
        pt.text(26, TOP_H / 2 + 1, 'BL3 ENGLISH PATCHER', 'heavy', 30, ow=2.6, anchor='w')
        y = TOP_H / 2 - 16
        self.b_details = Prompt(pt, W - 20, y, 'Details', self.toggle_details, h=30, px=15)
        self.b_credits = Prompt(pt, self.b_details.box[0] - 10, y, 'Credits', self.show_credits, h=30, px=15)
        self.b_clear = Prompt(pt, self.b_credits.box[0] - 10, y, 'Clear', self.clear_data, h=30, px=15)
        self.b_sound = SoundButton(pt, self.b_clear.box[0] - 10, y, self.toggle_sound)
        self.b_sound.show(not SFX.muted)
        # bottom band
        y0 = FIELD_Y1
        c.create_rectangle(0, y0 * S, W * S, (y0 + 3) * S, fill=BAND_EDGE, outline='')
        c.create_rectangle(0, (y0 + 3) * S, W * S, (y0 + 5) * S, fill=STRIP_LIGHT, outline='')
        c.create_rectangle(0, (y0 + 5) * S, W * S, (y0 + 10) * S, fill=STRIP, outline='')
        c.create_rectangle(0, (y0 + 10) * S, W * S, H_SMALL * S, fill=BAND, outline='')

    # ---- the three files, as the game's glass capsules ----
    def draw_capsules(self):
        pt, c, S = self.pt, self.c, self.S
        rows = (('src', 'Original game image (.bin)', self.v_src, self.pick_src),
                ('patch', 'Patch file (.bl3p)', self.v_patch, self.pick_patch),
                ('dst', 'Output folder', self.v_dst, self.pick_dst))
        self.caps = {}
        for k, (key, label, var, cmd) in enumerate(rows):
            x0, y0, x1, y1 = 24, 94 + k * 102, 708, 168 + k * 102
            tag = 'cap_' + key
            # fuse stub at the top-right, as on the game's menu capsules
            fx, fy = x1 - 44, y0 + 6
            fuse = (fx * S, fy * S, (fx + 18) * S, (fy - 20) * S)
            c.create_line(*fuse, fill=BLOB_LINE, width=pt.w(14), capstyle='round', tags=(tag,))
            fuse_edge = c.create_line(*fuse, fill=CAP_EDGE, width=pt.w(11), capstyle='round', tags=(tag,))
            fuse_in = c.create_line(*fuse, fill=CAP_BOTTOM, width=pt.w(5), capstyle='round', tags=(tag,))
            edge = pt.rrect(x0, y0, x1, y1, 24, CAP_TOP, outline=CAP_EDGE, width=3.5, tags=(tag,))
            bottom = pt.rrect(x0 + 4, y0 + (y1 - y0) * 0.5, x1 - 4, y1 - 4, 20, CAP_BOTTOM, tags=(tag,))
            text = pt.text(x0 + 20, y0 + 21, label, 'heavy', 17, anchor='w', tags=(tag,))
            browse = Prompt(pt, x1 - 16, y0 + 8, 'Browse', cmd, h=26, px=14)
            inset = pt.rrect(x0 + 14, y0 + 38, x1 - 14, y1 - 9, 12, INSET, tags=(tag,))
            e = tk.Entry(c, textvariable=var, font=pt.f('bold', 14), relief='flat', bd=0, highlightthickness=0,
                         bg=INSET, fg='#ffffff', insertbackground='#ffffff', selectbackground=PILL,
                         selectforeground=PILL_TEXT, disabledbackground=OFF_INSET, disabledforeground='#a9a5c2')
            c.create_window((x0 + 26) * S, (y0 + 52.5) * S, window=e, anchor='w', width=(x1 - x0 - 52) * S,
                            height=22 * S, tags=(tag,))
            self.caps[key] = dict(edge=edge, fuse=fuse_edge, fuse_in=fuse_in, bottom=bottom, text=text, inset=inset,
                                  tag=tag, entry=e, browse=browse, on=True,
                                  box=(x0, fy - 22, x1 + 8, y1))     # both places it sits in, and its fuse
            for widget_tag in (tag, browse.tag):
                c.tag_bind(widget_tag, '<Enter>', lambda ev, k=key: self.hover(k))
            e.bind('<Enter>', lambda ev, k=key: self.hover(k))
            e.bind('<FocusIn>', lambda ev, k=key: self.hover(k))
        c.bind('<Motion>', self._motion)

    def over_capsule(self, key, x, y):
        """is (x, y) (canvas pixels) inside the capsule's area: where it is, where it moves to when
        selected, and its fuse. By area, not by item: the selected capsule moves 8 px right, and
        going by item made it jump back and forth under a mouse at its left edge."""
        x0, y0, x1, y1 = self.caps[key]['box']
        S = self.S
        return x0 * S <= x <= x1 * S and y0 * S <= y <= y1 * S

    def _motion(self, e):
        """leave the capsule selection when the mouse is over none (and no entry has the focus)"""
        if self.locked_key and not self.over_capsule(self.locked_key, e.x, e.y):
            self.locked_key = None
            self.show_help()
        if not self.focus_step:
            return
        cap = self.caps[self.focus_step]
        if self.over_capsule(self.focus_step, e.x, e.y):
            return
        if self.focus_get() is cap['entry']:
            return
        self.hover(None)

    def hover(self, key):
        if key and not self.caps[key]['on']:     # a later step, still locked: say what comes first
            if self.locked_key != key:
                self.locked_key = key
                self.show_help()
            key = None
        if key == self.focus_step:
            return
        if self.focus_step:                  # the selected capsule sits a little to the right, as in the game
            self.c.move(self.caps[self.focus_step]['tag'], -8 * self.S, 0)
            self.c.move(self.caps[self.focus_step]['browse'].tag, -8 * self.S, 0)
        self.focus_step = key
        if key:
            SFX.play('hover')
            self.c.move(self.caps[key]['tag'], 8 * self.S, 0)
            self.c.move(self.caps[key]['browse'].tag, 8 * self.S, 0)
        self.check_files()
        self.show_help()

    # ---- the progress bar ----
    def draw_progress(self):
        c, pt, S = self.c, self.pt, self.S
        x0, x1, y = 30, W - 124, FIELD_Y1 + 44
        self.bar = (x0, y - 11, x1, y + 11)
        pt.rrect(x0, y - 11, x1, y + 11, 11, INSET, outline=INK, width=3)
        self.bar_fill = c.create_polygon(0, 0, 0, 0, smooth=True, fill=CAP_EDGE, outline='', state='hidden')
        self.bar_shine = c.create_polygon(0, 0, 0, 0, smooth=True, fill=CAP_EDGE_HI, outline='', state='hidden')
        # the help line, as at the bottom of the game's menus; the PATCH! bomb on the right, beside
        # the bar and the help (which wraps before it)
        self.b_apply = BombButton(pt, W - 70, FIELD_Y1 + 80, 36, 'PATCH!', self.start)
        self.help_ids = pt.text(30, FIELD_Y1 + 99, '', 'heavy', 17, anchor='w',
                                width=(self.b_apply.box[0] - 30 - 16) * S)

    def draw_log(self):
        pt, S = self.pt, self.S
        self.c.create_rectangle(0, H_SMALL * S, W * S, H_BIG * S, fill=LOG_BG, outline='')
        self.log = tk.Text(self.c, font=pt.f('mono', 13), wrap='word', bg=LOG_BG, fg='#e6defa',
                           insertbackground='white', relief='flat', bd=0, highlightthickness=0)
        self.c.create_window(26 * S, (H_SMALL + 14) * S, window=self.log, anchor='nw', width=(W - 52) * S,
                             height=(H_BIG - H_SMALL - 28) * S)
        self.log.tag_configure('err', foreground='#ff9b8a')
        self.log.tag_configure('ok', foreground='#a8f0a0')
        self.log.tag_configure('warn', foreground='#ffd27a')
        self.log.configure(state='disabled')

    def toggle_details(self, show=None):
        if show is None:
            SFX.play('slidedown' if self.details else 'slideup')
        self.details = (not self.details) if show is None else show
        self.c.configure(height=(H_BIG if self.details else H_SMALL) * self.S)

    # ---- the help line ----
    def help(self, text, colour=TEXT):
        for i in self.help_ids[:-1]:
            self.c.itemconfigure(i, text=text)
        self.c.itemconfigure(self.help_ids[-1], text=text, fill=colour)

    def show_help(self):
        """while patching: the progress; otherwise the hint for the selected capsule, the last
        result, or what is still missing"""
        if self.busy and self.message:
            return self.help(*self.message)
        missing = self.check_files()
        if self.locked_key:
            need = [w for k, w in (('src', 'your .bin'), ('patch', 'the patch')) if k in missing]
            what = 'a folder' if self.locked_key == 'dst' else 'the patch file'
            return self.help('First choose %s above. Then pick %s here.' % (' and '.join(need), what))
        if self.focus_step:
            if self.focus_step == 'patch':
                return self.help(self.patch_note or 'The English patch file (.bl3p).')
            if self.focus_step == 'dst':
                return self.help('The folder for the English game. "%s" is made there.'
                                 % output_name(self.v_src.get().strip()))
            return self.help(HINTS[self.focus_step])
        if self.message:
            return self.help(*self.message)
        if 'src' in missing:
            return self.help('Choose the .bin you extracted from your own game disc to start.')
        if 'patch' in missing:
            return self.help(self.patch_note or 'Choose the patch file (.bl3p).')
        if 'dst' in missing:
            return self.help('Choose a folder for the English game.')
        self.help(HINTS[None])

    def check_files(self):
        """step by step: each capsule opens once the ones above it are done, Apply patch once all
        three are (and nothing while patching). Open capsules: bright edge when still empty, red
        when what is in them is wrong, cyan when fine. -> missing keys"""
        missing = set()
        if not os.path.isfile(self.v_src.get().strip()): missing.add('src')
        if hasattr(self, 'logo_cache'):
            self.warm_logo()
        if not os.path.isfile(self.v_patch.get().strip()) or not self.patch_ok: missing.add('patch')
        if not os.path.isdir(self.v_dst.get().strip()): missing.add('dst')
        caps = getattr(self, 'caps', {})
        for i, key in enumerate(('src', 'patch', 'dst')):
            if key not in caps:
                continue
            cap = caps[key]
            on = not self.busy and not (set(('src', 'patch')[:i]) & missing)     # the steps above are done
            if on != cap['on']:
                cap['on'] = on
                if not on and self.focus_step == key:
                    self.hover(None)
                c = self.c
                c.itemconfigure(cap['edge'], fill=CAP_TOP if on else OFF_TOP)
                c.itemconfigure(cap['bottom'], fill=CAP_BOTTOM if on else OFF_BOTTOM)
                c.itemconfigure(cap['fuse_in'], fill=CAP_BOTTOM if on else OFF_BOTTOM)
                c.itemconfigure(cap['inset'], fill=INSET if on else OFF_INSET)
                for t in cap['text'][:-1]:
                    c.itemconfigure(t, fill=TEXT_LINE if on else OFF_LINE)
                c.itemconfigure(cap['text'][-1], fill=TEXT if on else OFF_TEXT)
                cap['entry'].configure(state='normal' if on else 'disabled')
                cap['browse'].set_enabled(on)
            empty = not cap['entry'].get().strip()      # empty: the step to do now (bright); wrong: red
            col = (OFF_EDGE if not on else (CAP_EDGE_HI if empty else CAP_WARN) if key in missing else
                   CAP_EDGE_HI if key == self.focus_step else CAP_EDGE)
            self.c.itemconfigure(cap['edge'], outline=col)
            self.c.itemconfigure(cap['fuse'], fill=col)
        if hasattr(self, 'b_apply'):
            self.b_apply.set_enabled(not self.busy and not missing)
        if hasattr(self, 'b_clear'):
            self.b_clear.set_enabled(not self.busy)
        return missing

    # ---- progress drawing ----
    def show_progress(self, f, colour=CAP_EDGE, shine=CAP_EDGE_HI):
        c, S = self.c, self.S
        x0, y0, x1, y1 = self.bar
        inner = x1 - x0 - 8
        w = max(0.0, min(1.0, f)) * inner
        if w < 1:
            c.itemconfigure(self.bar_fill, state='hidden'); c.itemconfigure(self.bar_shine, state='hidden')
            return
        w = max(w, 14)                                # never thinner than its rounded ends
        c.coords(self.bar_fill, *rounded(*[v * S for v in (x0 + 4, y0 + 4, x0 + 4 + w, y1 - 4)], 7 * S))
        c.itemconfigure(self.bar_fill, state='normal', fill=colour)
        if w > 20:
            c.coords(self.bar_shine, *rounded(*[v * S for v in (x0 + 9, y0 + 6, x0 + w - 1, y0 + 9.5)], 1.7 * S))
            c.itemconfigure(self.bar_shine, state='normal', fill=shine)
        else:
            c.itemconfigure(self.bar_shine, state='hidden')

    def reset_progress(self):
        self.show_progress(0)

    def progress_done(self):
        self.show_progress(1.0, BAR_DONE, BAR_DONE_HI)

    def progress_failed(self):
        f = self.prog[0] if self.prog else 0.0
        self.show_progress(max(f, 0.02), CAP_WARN, '#ffb3a3')

    def status(self, text, colour=TEXT):
        self.message = (text, colour)
        self.show_help()

    # ---- pickers ----
    def picked(self, ok):
        self.after(30, lambda: SFX.play('ok' if ok() else 'bonk'))

    def pick_src(self):
        p = filedialog.askopenfilename(title='Choose the .bin you extracted from your Bomberman Land 3 disc',
                                       filetypes=[('Raw CD image', '*.bin'), ('All files', '*.*')],
                                       initialdir=os.path.dirname(self.v_src.get()) or START)
        if p:
            self.v_src.set(os.path.normpath(p))
            self.picked(lambda: os.path.isfile(self.v_src.get()))

    def pick_patch(self):
        p = filedialog.askopenfilename(title='Choose a patch file',
                                       filetypes=[('BL3 patch', '*.bl3p'), ('All files', '*.*')],
                                       initialdir=os.path.dirname(self.v_patch.get()) or START)
        if p:
            self.v_patch.set(os.path.normpath(p))
            self.picked(lambda: self.patch_ok)

    def pick_dst(self):
        cur = self.v_dst.get().strip()
        p = filedialog.askdirectory(title='Choose a folder for the English game', mustexist=True,
                                    initialdir=cur if os.path.isdir(cur) else os.path.dirname(self.v_src.get()) or START)
        if p:
            self.v_dst.set(os.path.normpath(p))
            self.picked(lambda: os.path.isdir(self.v_dst.get()))

    def new_input(self):
        """a field changed: the last result no longer applies, show the step guidance again"""
        if not self.busy:
            self.message = None

    def _src_changed(self, *a):
        self.new_input()
        self.check_files(); self.show_help()

    def refresh_info(self):
        self.new_input()
        p = self.v_patch.get().strip()
        self.patch_ok = False
        if not p:
            self.patch_note = 'Choose the patch file (.bl3p).'
        else:
            try:
                meta, _ = core.load_patch(p, with_data=False)
                n = len(meta.get('files', []))
                title = str(meta.get('title') or 'The English patch file')
                self.patch_note = '%s. It changes %d game file%s.' % (title, n, '' if n == 1 else 's')
                self.patch_ok = True
            except Exception as e:
                self.patch_note = "This file can't be read as a patch: %s" % e
        self.check_files()
        self.show_help()

    # ---- log ----
    def write(self, line, tag=None):
        self.log.configure(state='normal')
        if tag is None:
            low = line.lower()
            tag = 'err' if low.startswith('error') else 'warn' if 'warning' in low else \
                  'ok' if (low.startswith('done') or ' 0 mismatched' in low) else None
        self.log.insert('end', line + '\n', tag)
        self.log.see('end')
        self.log.configure(state='disabled')

    def popup(self, kind, message, buttons=('OK',), title=None, default=None, sound=None):
        return Popup(self, kind, message, buttons, title, default, sound).result

    # ---- credits and clear data ----
    def show_credits(self):
        Credits(self)

    # ---- the patch's logo for Credits: the game's logo comes from the player's own disc image ----
    def _logo_key(self):
        """(image, its mtime, width in device pixels) for the first game image we know, or None"""
        if not bl3_logo:
            return None
        for path in (self.v_src.get().strip(), self.last_output or ''):
            if path and os.path.isfile(path):
                try:
                    return (os.path.abspath(path), os.path.getmtime(path), int(round(400 * self.S)))
                except OSError:
                    pass
        return None

    def _make_logo(self, key):
        try:
            res = bl3_logo.logo_png(key[0], key[2])
        except Exception:
            res = None                                # not the right game, unreadable: no logo
        with self.logo_lock:
            self.logo_cache[key] = res
        return res

    def warm_logo(self):
        """make the logo in the background, so Credits opens at once"""
        key = self._logo_key()
        if not key or key in self.logo_cache or self.logo_busy:
            return
        self.logo_busy = True
        def work():
            try:
                self._make_logo(key)
            finally:
                self.logo_busy = False
        threading.Thread(target=work, daemon=True).start()

    def credits_logo(self):
        key = self._logo_key()
        if not key:
            return None
        with self.logo_lock:
            if key in self.logo_cache:
                return self.logo_cache[key]
        self.configure(cursor='watch'); self.update_idletasks()
        try:
            return self._make_logo(key)
        finally:
            self.configure(cursor='')

    def toggle_sound(self):
        SFX.muted = not SFX.muted
        if SFX.muted:
            SFX.stop()
        else:
            SFX.play('pop')
        self.b_sound.show(not SFX.muted)
        self.settings['muted'] = SFX.muted
        save_settings(self.settings)

    def clear_data(self):
        if self.busy:
            return
        folder = os.path.dirname(settings_path())
        gone = clear_saved_data()
        self.settings = {}
        self.last_output = None
        self.message = None
        for var in (self.v_src, self.v_patch, self.v_dst):
            var.set('')
        self.reset_progress()
        self.log.configure(state='normal'); self.log.delete('1.0', 'end'); self.log.configure(state='disabled')
        if gone:
            SFX.play('whoosh')
            self.status('All saved data was removed.')
        else:
            self.show_help()
            self.popup('error', "Some saved data couldn't be removed. You can delete this folder yourself:\n\n%s" % folder)

    # ---- run ----
    def start(self):
        if self.busy or not self.b_apply.enabled:
            return
        src, patch, folder = self.v_src.get().strip(), self.v_patch.get().strip(), self.v_dst.get().strip()
        if not os.path.isfile(src):
            return self.popup('error', 'Choose the .bin you extracted from your own game disc first.')
        if not os.path.isfile(patch):
            return self.popup('error', 'Choose a patch file (.bl3p) first.')
        if not folder:
            return self.popup('error', 'Choose a folder for the English game.')
        if not os.path.isdir(folder):
            return self.popup('error', "The folder %s doesn't exist. Choose another one with Browse." % folder)
        dst = os.path.join(folder, output_name(src))
        if os.path.abspath(src) == os.path.abspath(dst):
            return self.popup('error', 'The English game must be saved as a different file from the original.')
        if os.path.exists(dst) and self.popup('question', '%s already exists. Replace it?'
                                              % os.path.basename(dst), ('Yes', 'No')) != 'Yes':
            return
        self.set_busy(True)
        self.reset_progress()
        self.prog = self.shown = None
        self.write('-' * 60, None)
        self.status('Starting...')
        self.b_apply.explode()
        self.worker = threading.Thread(target=self.run, args=(src, patch, dst), daemon=True)
        self.worker.start()

    def run(self, src, patch, dst):
        try:
            out, cue, n = core.apply_patch(src, patch, dst,
                                           log=lambda s: self.q.put(('log', s)),
                                           progress=self.set_progress)
            self.q.put(('done', (out, n)))
        except core.PatchError as e:
            self.q.put(('fail', str(e)))
        except Exception as e:
            self.q.put(('fail', '%s\n%s' % (e, traceback.format_exc())))

    def set_progress(self, frac, label):
        # called from the worker thread: only remember the latest value. The window shows it
        # in poll(), so the worker can never flood the window with updates
        self.prog = (frac, label)

    def poll(self):
        self.tick += 1
        p = self.prog
        if self.busy and p is not None:
            f, label = p
            self.show_progress(f)
            if p != self.shown:
                self.shown = p
                self.status('%s... %d%%' % (label, f * 100) if f < 1 else 'Almost there...')
        try:
            for _ in range(50):           # a handful of messages per tick keeps the window live
                kind, val = self.q.get_nowait()
                if kind == 'log':
                    self.write(val)
                elif kind == 'done':
                    out, n = val
                    self.last_output = out
                    self.settings['last_output'] = os.path.abspath(out)     # only noted, never picked again
                    save_settings(self.settings)
                    self.prog = self.shown = (1.0, 'Done')
                    self.set_busy(False)
                    SFX.play('fanfare')
                    self.progress_done()
                    self.status('Done! %d sectors patched. Your English game is ready.' % n, '#d8ffc8')
                    if self.popup('done', 'Your English game is ready:\n\n%s' % out, ('Open folder', 'OK'),
                                  default='OK') == 'Open folder':
                        show_in_folder(out)
                elif kind == 'fail':
                    self.shown = self.prog
                    self.set_busy(False)
                    self.progress_failed()
                    self.status('The patch was not applied. See Details for what went wrong.', '#ffd0c4')
                    self.write('ERROR: ' + val)
                    self.toggle_details(True)
                    SFX.play('wahwah')
                    self.popup('error', val.split('\n')[0], sound='')
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def set_busy(self, busy):
        self.busy = busy
        self.check_files()                    # nothing can be changed while patching
        self.configure(cursor='watch' if busy else '')

def main():
    sys.setswitchinterval(0.001)      # the patching thread is pure Python: hand the window its turn
    if sys.platform.startswith('win'):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)   # crisp text on high-DPI screens
        except Exception:
            pass
    App().mainloop()

if __name__ == '__main__':
    main()
