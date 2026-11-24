"""The patch's logo for the patcher's Credits window, put together from the player's own disc image.

Nothing from the game ships with the patcher: the game's logo is read from the chosen .bin (CDDATA.DIG
entry 1174, the title screen; texture page 4 is the logo, an 8-bit swizzled PS2 texture with a
256-colour CLUT). images/english_subtitle.png is the project's own half: the ENGLISH! subtitle with
its white border, made by docs/tools/make_patcher_logo.py, laid over the game's logo at the spot
images/english_subtitle.json gives, which rebuilds the logo of the credits screen exactly. An English
image (one the patcher made) already has that logo, smaller, on its title screen: it is shown as it is.
Standard library only (a small PNG reader/writer and a resize, so Tk can show it at any scale).
"""
import os, json, struct, zlib, math
import bl3_apply_patch as core

TITLE_ENTRY = 1174            # CDDATA.DIG TOC entry: the title screen (texture subfile 0, page 4 = logo)
TOC_SECTORS = 10              # CDDATA.DIG's TOC (16-byte entries)
SECT = 2048
IMAGES = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'images')

def decompress(src, out_size):
    """the game's LZ decoder (FUN_0012a070): 9-bit LSB-first codes; bit 8 set = literal, else copy
    (c & 7) + 1 bytes from one of the last 32 code starts seen after the same previous byte"""
    out = bytearray(out_size)
    hist = [[0] * 32 for _ in range(256)]
    ring = [0] * 256
    ctx = op = 0
    src = bytes(src) + b'\0\0'
    n = len(src) - 2
    ip = bit = 0
    while ip < n and op < out_size:
        code = (src[ip] | (src[ip + 1] << 8)) >> bit
        bit += 1
        if bit > 7:
            ip += 2; bit = 0
        else:
            ip += 1
        start = op
        if code & 0x100:
            out[op] = code & 0xff; op += 1
        else:
            p = hist[ctx][(code >> 3) & 31]
            for _ in range((code & 7) + 1):
                if op >= out_size: break
                out[op] = out[p]; op += 1; p += 1
        h = hist[ctx]; r = ring[ctx]; h[r] = start; ring[ctx] = (r + 1) & 31
        ctx = out[op - 1]
    return bytes(out[:op])

def _page(tex, k):
    """(psm, tw, th, w, h, image bytes as a full CT32 buffer, clut bytes) of texture page k"""
    npg, nup = struct.unpack_from('<II', tex, 0)
    regs = {}
    for j in range(4):
        v, r = struct.unpack_from('<QQ', tex, 0x10 + k * 0x50 + 16 + 16 * j); regs[r] = v
    t = regs.get(6, 0)
    psm, tw, th = (t >> 20) & 0x3f, 1 << ((t >> 26) & 0xf), 1 << ((t >> 30) & 0xf)
    info = struct.unpack_from('<HHIHBBIHH', tex, 0x10 + npg * 0x50 + k * 20)
    up0 = 0x10 + npg * 0x50 + npg * 20
    def upload(i):
        e = up0 + i * 16
        _a, rel, wh, _sz = struct.unpack_from('<4I', tex, e)
        uw, uh = wh & 0xffff, wh >> 16
        return tex[e + rel:e + rel + uw * uh * 4], uw, uh
    data, uw, uh = upload(info[0])
    fw, fh = tw // 2, th // 2                       # PSMT8 page = (tw/2 x th/2) CT32 words
    if (uw, uh) != (fw, fh):
        buf = bytearray(fw * fh * 4)
        for y in range(min(uh, fh)):
            buf[y * fw * 4:y * fw * 4 + uw * 4] = data[y * uw * 4:(y + 1) * uw * 4]
        data = bytes(buf)
    clut, _cw, _ch = upload(info[3])
    return psm, tw, th, info[7], info[8], data, clut

def read_logo(bin_path):
    """-> (w, h, RGBA bytes) of the logo in the player's disc image, cropped to its visible pixels"""
    with open(bin_path, 'rb') as f:
        lba, _size = core.find_file(f, 'CDDATA.DIG')
        toc = core.read_user(f, lba, TOC_SECTORS)
        s, u, _c, p = struct.unpack_from('<4I', toc, TITLE_ENTRY * 16)
        if not u:
            raise ValueError('no title screen entry')
        raw = core.read_user(f, lba + s, p or u)
    data = decompress(raw, u * SECT) if p else raw
    _sid, size, off, _z = struct.unpack_from('<4I', data, 0)
    tex = data[off:off + size]
    psm, tw, th, w, h, img, clut = _page(tex, 4)
    if psm != 19 or len(clut) < 1024:
        raise ValueError('unexpected logo texture')
    cols = [tuple(clut[i * 4:i * 4 + 4]) for i in range(256)]
    pal = [None] * 256
    for i in range(256):                            # CSM1 order
        r, g, b, a = cols[(i & ~0x18) | ((i & 0x08) << 1) | ((i & 0x10) >> 1)]
        pal[i] = bytes((r, g, b, min(255, a * 2)))
    out = bytearray(w * h * 4)
    for y in range(h):                              # PSMT8 unswizzle
        blk = (y & ~0xf) * tw
        swap = (((y + 2) >> 2) & 1) * 4
        col = ((((y & ~3) >> 1) + (y & 1)) & 7) * tw * 2
        b1 = (y >> 1) & 1
        o = y * w * 4
        for x in range(w):
            i = img[blk + (x & ~0xf) * 2 + col + ((x + swap) & 7) * 4 + (b1 + ((x >> 2) & 2))]
            out[o:o + 4] = pal[i]; o += 4
    # crop to the visible pixels
    alpha = [out[i] for i in range(3, len(out), 4)]
    ys = [y for y in range(h) if any(alpha[y * w:(y + 1) * w])]
    xs = [x for x in range(w) if any(alpha[y * w + x] for y in ys)]
    x0, x1, y0, y1 = xs[0], xs[-1] + 1, ys[0], ys[-1] + 1
    cw = x1 - x0
    crop = b''.join(bytes(out[(y * w + x0) * 4:(y * w + x1) * 4]) for y in range(y0, y1))
    return cw, y1 - y0, crop

# ---------------------------------------------------------------- PNG and resizing
def png_bytes(w, h, rgba):
    def chunk(kind, body):
        return struct.pack('>I', len(body)) + kind + body + struct.pack('>I', zlib.crc32(kind + body) & 0xffffffff)
    rows = b''.join(b'\0' + rgba[y * w * 4:(y + 1) * w * 4] for y in range(h))
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', w, h, 8, 6, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(rows, 6)) + chunk(b'IEND', b''))

def png_read(path):
    """-> (w, h, RGBA bytes) of an 8-bit RGBA, non-interlaced PNG"""
    data = open(path, 'rb').read()
    pos = 8
    w = h = None; idat = b''
    while pos < len(data):
        n, kind = struct.unpack_from('>I4s', data, pos)
        body = data[pos + 8:pos + 8 + n]; pos += 12 + n
        if kind == b'IHDR':
            w, h, depth, ctype, _c, _f, inter = struct.unpack('>IIBBBBB', body)
            if (depth, ctype, inter) != (8, 6, 0):
                raise ValueError('only 8-bit RGBA PNGs')
        elif kind == b'IDAT':
            idat += body
    raw = zlib.decompress(idat)
    stride = w * 4
    out = bytearray(h * stride); prev = bytearray(stride)
    for y in range(h):
        ft = raw[y * (stride + 1)]
        line = bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if ft == 1: line[i] = (line[i] + a) & 255
            elif ft == 2: line[i] = (line[i] + b) & 255
            elif ft == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif ft == 4:
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[i] = (line[i] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        out[y * stride:(y + 1) * stride] = line; prev = line
    return w, h, bytes(out)

def _taps(n_in, n_out):
    s = n_in / n_out
    res = []
    for o in range(n_out):
        if s <= 1:                                   # enlarging: linear
            c = (o + 0.5) * s - 0.5; i = math.floor(c); t = c - i
            res.append([(min(max(i, 0), n_in - 1), 1 - t), (min(max(i + 1, 0), n_in - 1), t)])
        else:                                        # shrinking: area average
            a, b = o * s, (o + 1) * s
            taps, i = [], int(a)
            while i < b and i < n_in:
                wgt = min(b, i + 1) - max(a, i)
                if wgt > 0: taps.append((i, wgt / s))
                i += 1
            res.append(taps)
    return res

def resize(w, h, rgba, nw, nh):
    """RGBA resize with premultiplied alpha (no dark fringes)"""
    src = [[0.0] * (w * 4) for _ in range(h)]
    for y in range(h):
        row = src[y]; o = y * w * 4
        for x in range(w):
            a = rgba[o + 3] / 255.0
            row[x * 4] = rgba[o] * a; row[x * 4 + 1] = rgba[o + 1] * a; row[x * 4 + 2] = rgba[o + 2] * a
            row[x * 4 + 3] = rgba[o + 3]; o += 4
    tx = _taps(w, nw)
    mid = []
    for row in src:
        r = [0.0] * (nw * 4)
        for x, taps in enumerate(tx):
            for k in range(4):
                r[x * 4 + k] = sum(row[i * 4 + k] * t for i, t in taps)
        mid.append(r)
    out = bytearray(nw * nh * 4)
    for y, taps in enumerate(_taps(h, nh)):
        o = y * nw * 4
        for x in range(nw * 4):
            out[o + x] = 0
        vals = [sum(mid[i][x] * t for i, t in taps) for x in range(nw * 4)]
        for x in range(nw):
            a = vals[x * 4 + 3]
            if a > 0.5:
                f = 255.0 / a
                out[o + x * 4] = min(255, int(vals[x * 4] * f + 0.5))
                out[o + x * 4 + 1] = min(255, int(vals[x * 4 + 1] * f + 0.5))
                out[o + x * 4 + 2] = min(255, int(vals[x * 4 + 2] * f + 0.5))
                out[o + x * 4 + 3] = min(255, int(a + 0.5))
    return bytes(out)

def compose(logo, sub, at):
    """the subtitle layer (w, h, rgba) laid over the game's logo placed at `at` -> (w, h, rgba)"""
    lw, lh, lrgba = logo
    sw, sh, srgba = sub
    out = bytearray(srgba)
    ax, ay = at
    for y in range(lh):
        ty = y + ay
        if not 0 <= ty < sh:
            continue
        for x in range(lw):
            tx = x + ax
            if not 0 <= tx < sw:
                continue
            i = (y * lw + x) * 4; o = (ty * sw + tx) * 4
            la = lrgba[i + 3]
            if not la:
                continue
            ta = out[o + 3]
            if ta == 255:
                continue                             # the subtitle covers it
            # out = subtitle over logo
            a = ta + la * (255 - ta) / 255.0
            for k in range(3):
                out[o + k] = int((out[o + k] * ta + lrgba[i + k] * la * (255 - ta) / 255.0) / a + 0.5)
            out[o + 3] = int(a + 0.5)
    return sw, sh, bytes(out)


def logo_png(bin_path, width):
    """-> (PNG bytes, w, h, subtitle box scaled (x, y, w, h)): the patch's logo from the player's disc
    image, `width` pixels wide"""
    with open(os.path.join(IMAGES, 'english_subtitle.json'), encoding='utf-8') as f:
        spec = json.load(f)
    logo = read_logo(bin_path)
    fw, fh = spec['size']
    if [logo[0], logo[1]] == spec['logo_size']:     # the Japanese game: its logo + our subtitle
        w, h, rgba = compose(logo, png_read(os.path.join(IMAGES, 'english_subtitle.png')), spec['logo_at'])
    elif abs(logo[0] / logo[1] - fw / fh) < 0.02:   # the English game: its title logo already has
        w, h, rgba = logo                           # ENGLISH! (made smaller to fit), shown as it is
    else:
        raise ValueError('this image has a different logo (%dx%d)' % logo[:2])
    nw = max(1, int(round(width))); nh = max(1, int(round(h * nw / w)))
    k = nw / fw                                     # the subtitle box is in the full logo's pixels
    box = tuple(v * k for v in spec.get('subtitle_box', (0, 0, fw, fh)))
    return png_bytes(nw, nh, resize(w, h, rgba, nw, nh)), nw, nh, box
