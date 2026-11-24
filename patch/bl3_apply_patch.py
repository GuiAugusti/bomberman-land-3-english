#!/usr/bin/env python3
"""
Bomberman Land 3 (SLPM-62643) English patch applier.

Applies a .bl3p patch to the Redump BIN "Bomberman Land 3 (Japan).bin" (raw 2352-byte sectors,
Mode 2 Form 1) and writes a NEW bin + cue. Your original image is never modified.

  python bl3_apply_patch.py "Bomberman Land 3 (Japan).bin" BL3_EN.bl3p "Bomberman Land 3 (English).bin"

(For a window instead of the command line, double-click BL3_Patcher.pyw in this folder.)

What it does
  1. Reads the ISO9660 file system inside the BIN to find each patched file (e.g. CDDATA.DIG).
  2. Checks every sector it will replace still holds the original data (SHA-1), so it refuses to
     patch a different version or an already-modified image.
  3. Copies the BIN, writes the new 2048-byte user data, and recomputes EDC/ECC for those sectors.
     Before writing, it recomputes EDC/ECC for a sample of the ORIGINAL sectors and compares with
     what is on the disc image, which proves the EDC/ECC code is correct for your image.
Only the Python 3 standard library is needed.
"""
import sys, os, json, zlib, struct, hashlib, time

RAW, USER, DATA_OFF = 2352, 2048, 24
SELF_CHECK = 256              # original sectors per file whose EDC/ECC is recomputed as a self-check

class PatchError(Exception):
    pass

# ---------------- EDC / ECC (ECMA-130), Mode 2 Form 1 ----------------
EDC_LUT = []
for i in range(256):
    e = i
    for _ in range(8):
        e = (e >> 1) ^ (0xD8018001 if e & 1 else 0)
    EDC_LUT.append(e)
ECC_F = [0] * 256; ECC_B = [0] * 256
for i in range(256):
    j = ((i << 1) ^ (0x11D if i & 0x80 else 0)) & 0xFF
    ECC_F[i] = j; ECC_B[i ^ j] = i

def edc(data):
    e = 0
    for b in data:
        e = (e >> 8) ^ EDC_LUT[(e ^ b) & 0xFF]
    return e

def _ecc_block(src, major_count, minor_count, major_mult, minor_inc):
    size = major_count * minor_count
    out = bytearray(major_count * 2)
    for major in range(major_count):
        index = (major >> 1) * major_mult + (major & 1)
        a = b = 0
        for _ in range(minor_count):
            t = src[index]
            index += minor_inc
            if index >= size: index -= size
            a ^= t; b ^= t
            a = ECC_F[a]
        a = ECC_B[ECC_F[a] ^ b]
        out[major] = a
        out[major + major_count] = a ^ b
    return out

def fix_sector_m2f1(sec):
    """sec: bytearray(2352) with sync/header/subheader/data filled; fills EDC and ECC."""
    struct.pack_into('<I', sec, 0x818, edc(sec[0x10:0x818]))
    hdr = bytes(sec[0x0C:0x10]); sec[0x0C:0x10] = b'\0\0\0\0'      # Mode 2: address excluded
    sec[0x81C:0x8C8] = _ecc_block(sec[0x0C:], 86, 24, 2, 86)        # P parity
    sec[0x8C8:0x930] = _ecc_block(sec[0x0C:], 52, 43, 86, 88)       # Q parity
    sec[0x0C:0x10] = hdr
    return sec

SYNC = b'\x00' + b'\xff' * 10 + b'\x00'

# ---------------- ISO9660 ----------------
def read_user(f, lba, count=1):
    out = bytearray()
    for k in range(count):
        f.seek((lba + k) * RAW)
        raw = f.read(RAW)
        if len(raw) < RAW or raw[:12] != SYNC or raw[15] != 2:
            raise PatchError('Sector %d is not a Mode 2 CD sector. Please choose the raw Redump '
                             '.bin (2352-byte sectors), not an .iso.' % (lba + k))
        out += raw[DATA_OFF:DATA_OFF + USER]
    return bytes(out)

def find_file(f, path):
    pvd = read_user(f, 16)
    if pvd[1:6] != b'CD001':
        raise PatchError('No ISO9660 file system found in this image.')
    root = pvd[156:156 + 34]
    lba, size = struct.unpack_from('<I', root, 2)[0], struct.unpack_from('<I', root, 10)[0]
    parts = [p for p in path.upper().replace('\\', '/').split('/') if p]
    for name in parts:
        data = read_user(f, lba, (size + USER - 1) // USER)
        pos, hit = 0, None
        while pos < len(data):
            ln = data[pos]
            if ln == 0:
                pos = (pos // USER + 1) * USER; continue
            rec = data[pos:pos + ln]
            nl = rec[32]; nm = rec[33:33 + nl].decode('ascii', 'replace').split(';')[0]
            if nm == name:
                hit = (struct.unpack_from('<I', rec, 2)[0], struct.unpack_from('<I', rec, 10)[0]); break
            pos += ln
        if not hit:
            raise PatchError('%s was not found in the disc image. Is this Bomberman Land 3?' % path)
        lba, size = hit
    return lba, size

# ---------------- patch format ----------------
def load_patch(path, with_data=True):
    with open(path, 'rb') as fh:
        head = fh.read(12)
        if head[:8] != b'BL3PATCH':
            raise PatchError('%s is not a .bl3p patch file.' % os.path.basename(path))
        hlen = struct.unpack_from('<I', head, 8)[0]
        meta = json.loads(fh.read(hlen).decode())
        data = zlib.decompress(fh.read()) if with_data else None
    return meta, data

def describe_patch(path):
    """Short human-readable summary of a patch file (reads only its header)."""
    meta, _ = load_patch(path, with_data=False)
    files = ', '.join('%s (%d sectors)' % (f['name'], len(f['sectors'])) for f in meta['files'])
    return meta.get('title', '?'), files

def apply_patch(src, patch, dst, log=print, progress=None):
    """Apply `patch` to `src`, writing `dst` (+ .cue). log(str); progress(fraction 0..1, label).

    Progress is reported at most once per 0.1 %, weighted by how long each step takes: checking
    the original sectors 0-15 %, copying the image 15-40 %, writing the patched sectors 40-100 %
    (the writing step recomputes EDC/ECC for every sector, the slowest part)."""
    last = [-1, None]
    def prog(frac, label):
        k = int(frac * 1000)
        if progress and (k != last[0] or label != last[1]):
            last[0], last[1] = k, label
            progress(frac, label)
    if os.path.abspath(src) == os.path.abspath(dst):
        raise PatchError('The output must be a different file from the original image.')
    prog(0.0, 'Reading the patch')
    meta, data = load_patch(patch)
    log('Patch: %s' % meta.get('title', '?'))
    total_secs = sum(len(fe['sectors']) for fe in meta['files']) or 1
    done = 0
    plan = []
    with open(src, 'rb') as f:
        for fe in meta['files']:
            lba, size = find_file(f, fe['name'])
            if size != fe['size']:
                raise PatchError('%s has size %d but the patch expects %d. Different game version?'
                                 % (fe['name'], size, fe['size']))
            log('  %s found at LBA %d (%d bytes), %d sectors to patch'
                % (fe['name'], lba, size, len(fe['sectors'])))
            ecc_ok = ecc_bad = already = 0
            for rel, old_sha, new_sha, off in fe['sectors']:
                n = min(USER, size - rel * USER)      # a file's last sector may be partly used
                f.seek((lba + rel) * RAW); raw = bytearray(f.read(RAW))
                user = bytes(raw[DATA_OFF:DATA_OFF + n])
                h = hashlib.sha1(user).hexdigest()
                done += 1
                prog(0.15 * done / total_secs, 'Checking original data')
                if done % 8 == 0: time.sleep(0)       # let a window running beside us redraw
                if h == new_sha:
                    already += 1; continue
                if h != old_sha:
                    raise PatchError('Sector %d of %s does not match the original game data. '
                                     'This image is a different version or was already modified.'
                                     % (rel, fe['name']))
                if ecc_ok + ecc_bad < SELF_CHECK:      # a sample is enough to prove the EDC/ECC code
                    if fix_sector_m2f1(bytearray(raw)) == raw: ecc_ok += 1
                    else: ecc_bad += 1
                new_user = data[off:off + n]
                if hashlib.sha1(new_user).hexdigest() != new_sha:
                    raise PatchError('The patch file is damaged (sector %d).' % rel)
                plan.append((lba + rel, new_user))
            if already == len(fe['sectors']):
                log('    already patched, nothing to do for this file')
            elif already:
                log('    %d sectors were already patched' % already)
            if ecc_ok + ecc_bad:
                log('    EDC/ECC self-check on %d original sectors: %d ok, %d mismatched'
                    % (ecc_ok + ecc_bad, ecc_ok, ecc_bad))
            if ecc_bad:
                log('    WARNING: EDC/ECC could not be reproduced. Do not burn this image to a disc.')
    # copy with progress
    total = os.path.getsize(src)
    log('Copying image (%.0f MB) ...' % (total / 1048576))
    try:
        with open(src, 'rb') as fi, open(dst, 'wb') as fo:
            copied = 0
            while True:
                chunk = fi.read(8 << 20)
                if not chunk: break
                fo.write(chunk); copied += len(chunk)
                prog(0.15 + 0.25 * copied / total, 'Copying image')
        with open(dst, 'r+b') as out:
            for k, (lba, user) in enumerate(plan):
                out.seek(lba * RAW); raw = bytearray(out.read(RAW))
                raw[DATA_OFF:DATA_OFF + len(user)] = user
                fix_sector_m2f1(raw)
                out.seek(lba * RAW); out.write(raw)
                prog(0.40 + 0.60 * (k + 1) / max(1, len(plan)), 'Writing patched sectors')
                if k % 8 == 0: time.sleep(0)
    except BaseException:
        try: os.remove(dst)
        except OSError: pass
        raise
    cue = os.path.splitext(dst)[0] + '.cue'
    with open(cue, 'w', newline='\r\n') as c:
        c.write('FILE "%s" BINARY\n  TRACK 01 MODE2/2352\n    INDEX 01 00:00:00\n' % os.path.basename(dst))
    prog(1.0, 'Done')
    log('Done: %d sectors written.' % len(plan))
    log('  %s' % dst)
    log('  %s' % cue)
    return dst, cue, len(plan)

def main():
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    try:
        apply_patch(*sys.argv[1:])
    except PatchError as e:
        sys.exit('ERROR: %s' % e)

if __name__ == '__main__':
    main()
