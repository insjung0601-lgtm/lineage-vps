#!/usr/bin/env python3
"""list.txt 생성기 (launcher src/server_list.rs 의 config_encrypt 와 동일)
사용: python3 make_list.py "나만의리니지" 100.89.142.27 2000 > list.txt"""
import base64, re, struct, sys
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

KEY = b"4zF8sAc5bYkCRM3w"
SRC = open(__file__.replace('launcher_dist/make_list.py', 'launcher/src/server_list.rs'), encoding='utf-8').read()
XOR_TABLE = bytes(int(x, 16) for x in re.findall(r'0x([0-9A-Fa-f]{2})', SRC.split('const XOR_TABLE')[1].split('];')[0]))
assert len(XOR_TABLE) == 256

def table():
    return bytes(XOR_TABLE[i] ^ KEY[i % 16] for i in range(256))

def encrypt(data):
    t = table(); b = bytearray(d ^ t[i % 256] for i, d in enumerate(data))
    n = len(b) // 16 * 16
    enc = Cipher(algorithms.AES(KEY), modes.ECB()).encryptor()
    b[:n] = enc.update(bytes(b[:n])) + enc.finalize()
    return bytes(b)

def decrypt(data):
    b = bytearray(data); n = len(b) // 16 * 16
    dec = Cipher(algorithms.AES(KEY), modes.ECB()).decryptor()
    b[:n] = dec.update(bytes(b[:n])) + dec.finalize()
    t = table(); return bytes(d ^ t[i % 256] for i, d in enumerate(b))

def server_info(name, ip, port):
    buf = bytearray(213)
    nm = name.encode('utf-16-le')[:62]; buf[0:len(nm)] = nm
    ipb = ip.encode('ascii')[:31]; buf[64:64 + len(ipb)] = ipb
    buf[96:100] = struct.pack('<i', port)
    buf[100] = 1  # used
    return bytes(buf)

if __name__ == '__main__':
    name, ip, port = sys.argv[1], sys.argv[2], int(sys.argv[3])
    raw = server_info(name, ip, port)
    enc = encrypt(raw)
    assert decrypt(enc) == raw
    sys.stdout.write('[list]\nServerData0=%s\n' % base64.b64encode(enc).decode())
