import hashlib, hmac, os, sys, zlib
from dotenv import load_dotenv

load_dotenv()

def _boot():
    bin_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core.bin")
    if not os.path.exists(bin_path):
        sys.exit("[sys.core] fatal: core.bin not found")
    with open(bin_path, "rb") as f:
         blob = f.read()
    salt, mac, ct = blob[:16], blob[16:48], blob[48:]
    pwd = os.getenv("CORE_KEY", "").strip()
    if not pwd:
        sys.exit("[sys.core] fatal: CORE_KEY environment variable is not set")
    key = hashlib.pbkdf2_hmac("sha256", pwd.encode("utf-8"), salt, 250000, 32)
    if not hmac.compare_digest(mac, hmac.new(key, ct, hashlib.sha256).digest()):
        sys.exit("[sys.core] fatal: CORE_KEY signature mismatch")
    out = bytearray(len(ct))
    for blk_idx in range(0, len(ct), 32):
        digest = hmac.new(key, (blk_idx // 32).to_bytes(4, "big"), hashlib.sha256).digest()
        chunk = ct[blk_idx:blk_idx + 32]
        for j, b in enumerate(chunk):
            out[blk_idx + j] = b ^ digest[j]
    src = zlib.decompress(bytes(out)).decode("utf-8")
    g = globals()
    g["__file__"] = os.path.abspath(__file__)
    exec(compile(src, "core.bin", "exec"), g)

if __name__ == "__main__":
    _boot()
