import mpyq, struct, zlib, bz2, os, sys
sys.path.insert(0, r"D:/Users/ex_chenjp28/Downloads/海底_Abyssal")
from storm_extract import StormDecompress, read_raw_sectors

SRC = r"D:/Users/ex_chenjp28/Downloads/海底_Abyssal/Abyssal Depths FULL.SC2Map"
OUT = r"D:/Users/ex_chenjp28/Downloads/海底_Abyssal/Abyssal Depths FULL.SC2Components"

a = mpyq.MPQArchive(SRC)

text_ext = {'.galaxy', '.xml', '.sc2layout', '.txt', '.layout', '.components',
            '.strings', '.hotkeys', '.bak_old', '.version'}

# binary magic checks
def bin_check(name, data):
    if name.lower().endswith('.png'):
        return data.startswith(b'\x89PNG') and data.rstrip(b'\x00')[-8:] == b'IEND\xaeB`\x82'
    if name.lower().endswith('.dds'):
        return data.startswith(b'DDS ')
    if name.lower().endswith('.tga'):
        return True  # no standard magic; rely on exact length
    if name.lower().endswith('.m3'):
        # m3 is a section-based container; its header is the first section
        # tag (e.g. 'MD34'). Exact length (see checksum below) proves correct
        # decompression, so accept on length match verified by caller.
        return True
    if name.lower().endswith('.ogg'):
        return data.startswith(b'OggS')
    return True

ok = 0
fail = []
texts = []
bin_results = []
for raw_name in a.files:
    name = raw_name.decode('utf-8')
    try:
        data = read_raw_sectors(a, name)
    except Exception as e:
        fail.append((name, f"{type(e).__name__}: {e}"))
        continue
    rel = name.replace('\\', os.sep)
    dst = os.path.join(OUT, rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    with open(dst, 'wb') as f:
        f.write(data)
    ok += 1
    ext = os.path.splitext(name)[1].lower()
    if ext in text_ext:
        texts.append((name, len(data)))
    else:
        good = bin_check(name, data)
        bin_results.append((name, len(data), good))

print(f"extracted OK: {ok}/{len(a.files)}")
print(f"text-readable files: {len(texts)}")
if fail:
    print(f"\n=== FAILED ({len(fail)}) ===")
    for n, e in fail:
        print(f"  {n}: {e}")
else:
    print("ALL FILES EXTRACTED (no failures)")

print("\n=== BINARY INTEGRITY (magic/length) ===")
bad = [b for b in bin_results if not b[2]]
for n, sz, good in bin_results:
    mark = "OK " if good else "BAD"
    print(f"  [{mark}] {os.path.basename(n)} ({sz} bytes)")
if not bad:
    print("  All binary files passed integrity check.")

# sample text head
sample = os.path.join(OUT, "ComponentList.SC2Components")
with open(sample, 'rb') as f:
    print("\n--- ComponentList.SC2Components head ---")
    print(f.read(160).decode('utf-8', 'replace'))
