using System;

namespace AircDumb
{
    /// <summary>
    /// AES-256-GCM (no NuGet). Interops with Python cryptography AESGCM / seal.dumb_seal_bytes.
    /// Port of src/moot_thin/aes256gcm.c so Server 2012 need not restore packages at runtime.
    /// </summary>
    internal static class Aes256Gcm
    {
        private static readonly byte[] Sbox = new byte[]
        {
            0x63,0x7c,0x77,0x7b,0xf2,0x6b,0x6f,0xc5,0x30,0x01,0x67,0x2b,0xfe,0xd7,0xab,0x76,
            0xca,0x82,0xc9,0x7d,0xfa,0x59,0x47,0xf0,0xad,0xd4,0xa2,0xaf,0x9c,0xa4,0x72,0xc0,
            0xb7,0xfd,0x93,0x26,0x36,0x3f,0xf7,0xcc,0x34,0xa5,0xe5,0xf1,0x71,0xd8,0x31,0x15,
            0x04,0xc7,0x23,0xc3,0x18,0x96,0x05,0x9a,0x07,0x12,0x80,0xe2,0xeb,0x27,0xb2,0x75,
            0x09,0x83,0x2c,0x1a,0x1b,0x6e,0x5a,0xa0,0x52,0x3b,0xd6,0xb3,0x29,0xe3,0x2f,0x84,
            0x53,0xd1,0x00,0xed,0x20,0xfc,0xb1,0x5b,0x6a,0xcb,0xbe,0x39,0x4a,0x4c,0x58,0xcf,
            0xd0,0xef,0xaa,0xfb,0x43,0x4d,0x33,0x85,0x45,0xf9,0x02,0x7f,0x50,0x3c,0x9f,0xa8,
            0x51,0xa3,0x40,0x8f,0x92,0x9d,0x38,0xf5,0xbc,0xb6,0xda,0x21,0x10,0xff,0xf3,0xd2,
            0xcd,0x0c,0x13,0xec,0x5f,0x97,0x44,0x17,0xc4,0xa7,0x7e,0x3d,0x64,0x5d,0x19,0x73,
            0x60,0x81,0x4f,0xdc,0x22,0x2a,0x90,0x88,0x46,0xee,0xb8,0x14,0xde,0x5e,0x0b,0xdb,
            0xe0,0x32,0x3a,0x0a,0x49,0x06,0x24,0x5c,0xc2,0xd3,0xac,0x62,0x91,0x95,0xe4,0x79,
            0xe7,0xc8,0x37,0x6d,0x8d,0xd5,0x4e,0xa9,0x6c,0x56,0xf4,0xea,0x65,0x7a,0xae,0x08,
            0xba,0x78,0x25,0x2e,0x1c,0xa6,0xb4,0xc6,0xe8,0xdd,0x74,0x1f,0x4b,0xbd,0x8b,0x8a,
            0x70,0x3e,0xb5,0x66,0x48,0x03,0xf6,0x0e,0x61,0x35,0x57,0xb9,0x86,0xc1,0x1d,0x9e,
            0xe1,0xf8,0x98,0x11,0x69,0xd9,0x8e,0x94,0x9b,0x1e,0x87,0xe9,0xce,0x55,0x28,0xdf,
            0x8c,0xa1,0x89,0x0d,0xbf,0xe6,0x42,0x68,0x41,0x99,0x2d,0x0f,0xb0,0x54,0xbb,0x16
        };

        private static readonly byte[] Rcon = new byte[] { 0x00, 0x01, 0x02, 0x04, 0x08, 0x10, 0x20, 0x40, 0x80, 0x1b, 0x36 };

        private static byte Xtime(byte x)
        {
            return (byte)((x << 1) ^ ((x & 0x80) != 0 ? 0x1b : 0));
        }

        private sealed class Aes256Ctx
        {
            public readonly byte[][] Rk = new byte[15][];
            public Aes256Ctx()
            {
                for (int i = 0; i < 15; i++)
                    Rk[i] = new byte[16];
            }
        }

        private static void Aes256Init(Aes256Ctx c, byte[] key)
        {
            byte[] w = new byte[60 * 4];
            Buffer.BlockCopy(key, 0, w, 0, 32);
            for (int i = 8; i < 60; i++)
            {
                byte[] temp = new byte[4];
                Buffer.BlockCopy(w, (i - 1) * 4, temp, 0, 4);
                if (i % 8 == 0)
                {
                    byte t = temp[0];
                    temp[0] = temp[1];
                    temp[1] = temp[2];
                    temp[2] = temp[3];
                    temp[3] = t;
                    temp[0] = Sbox[temp[0]];
                    temp[1] = Sbox[temp[1]];
                    temp[2] = Sbox[temp[2]];
                    temp[3] = Sbox[temp[3]];
                    temp[0] ^= Rcon[i / 8];
                }
                else if (i % 8 == 4)
                {
                    temp[0] = Sbox[temp[0]];
                    temp[1] = Sbox[temp[1]];
                    temp[2] = Sbox[temp[2]];
                    temp[3] = Sbox[temp[3]];
                }
                w[i * 4 + 0] = (byte)(w[(i - 8) * 4 + 0] ^ temp[0]);
                w[i * 4 + 1] = (byte)(w[(i - 8) * 4 + 1] ^ temp[1]);
                w[i * 4 + 2] = (byte)(w[(i - 8) * 4 + 2] ^ temp[2]);
                w[i * 4 + 3] = (byte)(w[(i - 8) * 4 + 3] ^ temp[3]);
            }
            for (int i = 0; i < 15; i++)
                Buffer.BlockCopy(w, i * 16, c.Rk[i], 0, 16);
        }

        private static void MixColumns(byte[] s)
        {
            for (int col = 0; col < 4; col++)
            {
                int o = col * 4;
                byte a0 = s[o], a1 = s[o + 1], a2 = s[o + 2], a3 = s[o + 3];
                s[o] = (byte)(Xtime(a0) ^ Xtime(a1) ^ a1 ^ a2 ^ a3);
                s[o + 1] = (byte)(a0 ^ Xtime(a1) ^ Xtime(a2) ^ a2 ^ a3);
                s[o + 2] = (byte)(a0 ^ a1 ^ Xtime(a2) ^ Xtime(a3) ^ a3);
                s[o + 3] = (byte)(Xtime(a0) ^ a0 ^ a1 ^ a2 ^ Xtime(a3));
            }
        }

        private static void Aes256EncryptBlock(Aes256Ctx c, byte[] input, int inOff, byte[] output, int outOff)
        {
            byte[] s = new byte[16];
            Buffer.BlockCopy(input, inOff, s, 0, 16);
            for (int i = 0; i < 16; i++)
                s[i] ^= c.Rk[0][i];
            for (int r = 1; r < 14; r++)
            {
                for (int i = 0; i < 16; i++)
                    s[i] = Sbox[s[i]];
                byte[] t = new byte[16];
                t[0] = s[0]; t[4] = s[4]; t[8] = s[8]; t[12] = s[12];
                t[1] = s[5]; t[5] = s[9]; t[9] = s[13]; t[13] = s[1];
                t[2] = s[10]; t[6] = s[14]; t[10] = s[2]; t[14] = s[6];
                t[3] = s[15]; t[7] = s[3]; t[11] = s[7]; t[15] = s[11];
                Buffer.BlockCopy(t, 0, s, 0, 16);
                MixColumns(s);
                for (int i = 0; i < 16; i++)
                    s[i] ^= c.Rk[r][i];
            }
            {
                for (int i = 0; i < 16; i++)
                    s[i] = Sbox[s[i]];
                byte[] t = new byte[16];
                t[0] = s[0]; t[4] = s[4]; t[8] = s[8]; t[12] = s[12];
                t[1] = s[5]; t[5] = s[9]; t[9] = s[13]; t[13] = s[1];
                t[2] = s[10]; t[6] = s[14]; t[10] = s[2]; t[14] = s[6];
                t[3] = s[15]; t[7] = s[3]; t[11] = s[7]; t[15] = s[11];
                Buffer.BlockCopy(t, 0, s, 0, 16);
                for (int i = 0; i < 16; i++)
                    s[i] ^= c.Rk[14][i];
            }
            Buffer.BlockCopy(s, 0, output, outOff, 16);
        }

        private static void Xor16(byte[] a, byte[] b)
        {
            for (int i = 0; i < 16; i++)
                a[i] ^= b[i];
        }

        private static void GfMult(byte[] x, byte[] y, byte[] z)
        {
            byte[] v = new byte[16];
            Array.Clear(z, 0, 16);
            Buffer.BlockCopy(y, 0, v, 0, 16);
            for (int i = 0; i < 16; i++)
            {
                for (int j = 7; j >= 0; j--)
                {
                    if ((x[i] & (1 << j)) != 0)
                        Xor16(z, v);
                    int lsb = v[15] & 1;
                    for (int k = 15; k > 0; k--)
                        v[k] = (byte)((v[k] >> 1) | ((v[k - 1] & 1) << 7));
                    v[0] >>= 1;
                    if (lsb != 0)
                        v[0] ^= 0xe1;
                }
            }
        }

        private static void Ghash(byte[] H, byte[] aad, int aadLen, byte[] ct, int ctOff, int ctLen, byte[] s)
        {
            byte[] y = new byte[16];
            byte[] tmp = new byte[16];
            byte[] work = new byte[16];
            for (int i = 0; i < aadLen; i += 16)
            {
                int n = aadLen - i;
                if (n > 16)
                    n = 16;
                Array.Clear(tmp, 0, 16);
                Buffer.BlockCopy(aad, i, tmp, 0, n);
                Xor16(y, tmp);
                GfMult(y, H, work);
                Buffer.BlockCopy(work, 0, y, 0, 16);
            }
            for (int i = 0; i < ctLen; i += 16)
            {
                int n = ctLen - i;
                if (n > 16)
                    n = 16;
                Array.Clear(tmp, 0, 16);
                Buffer.BlockCopy(ct, ctOff + i, tmp, 0, n);
                Xor16(y, tmp);
                GfMult(y, H, work);
                Buffer.BlockCopy(work, 0, y, 0, 16);
            }
            byte[] lenblk = new byte[16];
            ulong al = (ulong)aadLen * 8UL;
            ulong cl = (ulong)ctLen * 8UL;
            lenblk[0] = (byte)(al >> 56);
            lenblk[1] = (byte)(al >> 48);
            lenblk[2] = (byte)(al >> 40);
            lenblk[3] = (byte)(al >> 32);
            lenblk[4] = (byte)(al >> 24);
            lenblk[5] = (byte)(al >> 16);
            lenblk[6] = (byte)(al >> 8);
            lenblk[7] = (byte)al;
            lenblk[8] = (byte)(cl >> 56);
            lenblk[9] = (byte)(cl >> 48);
            lenblk[10] = (byte)(cl >> 40);
            lenblk[11] = (byte)(cl >> 32);
            lenblk[12] = (byte)(cl >> 24);
            lenblk[13] = (byte)(cl >> 16);
            lenblk[14] = (byte)(cl >> 8);
            lenblk[15] = (byte)cl;
            Xor16(y, lenblk);
            GfMult(y, H, work);
            Buffer.BlockCopy(work, 0, s, 0, 16);
        }

        private static void Inc32(byte[] ctr)
        {
            for (int i = 15; i >= 12; i--)
            {
                ctr[i]++;
                if (ctr[i] != 0)
                    break;
            }
        }

        private static void Gctr(Aes256Ctx aes, byte[] icb, byte[] input, int inOff, int inLen, byte[] output, int outOff)
        {
            byte[] ctr = new byte[16];
            byte[] ks = new byte[16];
            Buffer.BlockCopy(icb, 0, ctr, 0, 16);
            int i = 0;
            while (i < inLen)
            {
                int n = inLen - i;
                if (n > 16)
                    n = 16;
                Aes256EncryptBlock(aes, ctr, 0, ks, 0);
                for (int k = 0; k < n; k++)
                    output[outOff + i + k] = (byte)(input[inOff + i + k] ^ ks[k]);
                Inc32(ctr);
                i += n;
            }
        }

        /// <summary>out = ciphertext || tag(16). Does not prepend nonce.</summary>
        public static byte[] Encrypt(byte[] key, byte[] nonce12, byte[] aad, byte[] pt)
        {
            if (key == null || key.Length != 32)
                throw new ArgumentException("key");
            if (nonce12 == null || nonce12.Length != 12)
                throw new ArgumentException("nonce");
            if (aad == null)
                aad = new byte[0];
            if (pt == null)
                pt = new byte[0];
            Aes256Ctx aes = new Aes256Ctx();
            Aes256Init(aes, key);
            byte[] zero = new byte[16];
            byte[] H = new byte[16];
            Aes256EncryptBlock(aes, zero, 0, H, 0);
            byte[] J0 = new byte[16];
            Buffer.BlockCopy(nonce12, 0, J0, 0, 12);
            J0[15] = 1;
            byte[] icb = new byte[16];
            Buffer.BlockCopy(J0, 0, icb, 0, 16);
            Inc32(icb);
            byte[] ct = new byte[pt.Length];
            if (pt.Length > 0)
                Gctr(aes, icb, pt, 0, pt.Length, ct, 0);
            byte[] S = new byte[16];
            Ghash(H, aad, aad.Length, ct, 0, ct.Length, S);
            byte[] tag = new byte[16];
            Gctr(aes, J0, S, 0, 16, tag, 0);
            byte[] output = new byte[pt.Length + 16];
            Buffer.BlockCopy(ct, 0, output, 0, pt.Length);
            Buffer.BlockCopy(tag, 0, output, pt.Length, 16);
            return output;
        }

        /// <summary>Returns plaintext or null if the tag does not match.</summary>
        public static byte[] Decrypt(byte[] key, byte[] nonce12, byte[] aad, byte[] ctAndTag)
        {
            if (key == null || key.Length != 32)
                return null;
            if (nonce12 == null || nonce12.Length != 12)
                return null;
            if (ctAndTag == null || ctAndTag.Length < 16)
                return null;
            if (aad == null)
                aad = new byte[0];
            int ctLen = ctAndTag.Length - 16;
            Aes256Ctx aes = new Aes256Ctx();
            Aes256Init(aes, key);
            byte[] zero = new byte[16];
            byte[] H = new byte[16];
            Aes256EncryptBlock(aes, zero, 0, H, 0);
            byte[] J0 = new byte[16];
            Buffer.BlockCopy(nonce12, 0, J0, 0, 12);
            J0[15] = 1;
            byte[] S = new byte[16];
            Ghash(H, aad, aad.Length, ctAndTag, 0, ctLen, S);
            byte[] tag = new byte[16];
            Gctr(aes, J0, S, 0, 16, tag, 0);
            int diff = 0;
            for (int i = 0; i < 16; i++)
                diff |= tag[i] ^ ctAndTag[ctLen + i];
            if (diff != 0)
                return null;
            byte[] icb = new byte[16];
            Buffer.BlockCopy(J0, 0, icb, 0, 16);
            Inc32(icb);
            byte[] pt = new byte[ctLen];
            if (ctLen > 0)
                Gctr(aes, icb, ctAndTag, 0, ctLen, pt, 0);
            return pt;
        }
    }
}
