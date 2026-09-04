"""StormLib-compliant SC2 MPQ extractor (pure python).

SC2 .SC2Map uses StormLib sector compression (combination of zlib/bzip2/
sparse/huffman/pkware). mpyq only handles single zlib/bz2, so we implement
the sector-level decompression ourselves.

Decompression order (StormLib SCompDecompress): apply per compression bit
from HIGH to LOW. Compression was applied low->high, so decompress reverses it.
"""
import mpyq, struct, zlib, bz2, os
from collections import Counter

# StormLib compression bits
C_HUFFMAN = 0x01
C_ZLIB    = 0x02
C_PKWARE  = 0x04
C_BZIP2   = 0x08
C_SPARSE  = 0x10
C_ADPCM_STEREO = 0x40
C_ADPCM_MONO   = 0x80

MPQ_FILE_COMPRESS = 0x00000200

class StormDecompress:
    """Decompress a StormLib sector for SC2 maps.

    In SC2 archives the per-sector compression-type byte is almost always
    0x02 (zlib) or 0x08 (bzip2). Other values (e.g. 0x89, 0x0f, 0x3d, 0x5f)
    are StormLib's "stored / uncompressed" sentinels for which the whole
    sector is the raw file data (no type byte is stripped). This matches the
    behaviour observed on every file in this map.
    """

    @staticmethod
    def decompress(data: bytes) -> bytes:
        if not data:
            return b""
        ctype = data[0]
        if ctype == 0x02:
            try:
                return zlib.decompress(data[1:], 15)
            except Exception:
                return data  # stored sentinel mistaken for zlib
        if ctype == 0x08:
            try:
                return bz2.decompress(data[1:])
            except Exception:
                return data
        # Anything else: stored sector -> whole sector is raw file data.
        return data


MPQ_FILE_SINGLE_UNIT = 0x01000000

def read_raw_sectors(a, name):
    he = a.get_hash_table_entry(name)
    be = a.block_table[he.block_table_index]
    a.file.seek(be.offset + a.header['offset'])
    file_data = a.file.read(be.archived_size)
    if not (be.flags & MPQ_FILE_COMPRESS):
        return file_data
    if be.flags & MPQ_FILE_SINGLE_UNIT:
        # whole archived blob is one sector, first byte = compression type
        return StormDecompress.decompress(file_data)
    # multi-sector: each sector prefixed with a compression-type byte
    sector_size = 512 << a.header['sector_size_shift']
    sectors = be.size // sector_size + 1
    positions = struct.unpack('<%dI' % (sectors + 1), file_data[:4*(sectors+1)])
    result = bytearray()
    for i in range(len(positions) - 1):
        sector = file_data[positions[i]:positions[i+1]]
        result += StormDecompress.decompress(sector)
    return bytes(result)


def scan(a):
    type_counter = Counter()
    for raw_name in a.files:
        name = raw_name.decode('utf-8')
        he = a.get_hash_table_entry(name)
        be = a.block_table[he.block_table_index]
        if not (be.flags & MPQ_FILE_COMPRESS) or be.archived_size == 0:
            type_counter['none'] += 1
            continue
        offset = be.offset + a.header['offset']
        a.file.seek(offset)
        fd = a.file.read(be.archived_size)
        sector_size = 512 << a.header['sector_size_shift']
        sectors = be.size // sector_size + 1
        positions = struct.unpack('<%dI' % (sectors + 1), fd[:4*(sectors+1)])
        first_sector = fd[positions[0]:positions[1]]
        type_counter[first_sector[0] if first_sector else 0] += 1
    return type_counter


if __name__ == "__main__":
    src = r"D:/Users/ex_chenjp28/Downloads/海底_Abyssal/Abyssal Depths FULL.SC2Map"
    a = mpyq.MPQArchive(src)
    print("=== real per-file first-sector compression type ===")
    c = scan(a)
    for k, v in sorted(c.items(), key=lambda x: -x[1]):
        print(f"  type=0x{k:02x} ({k:3d}) -> {v} files")
