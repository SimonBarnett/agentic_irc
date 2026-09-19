using System;
using System.Collections.Generic;
using System.Security.Cryptography;
using System.Text;
using System.Text.RegularExpressions;

namespace AircDumb
{
    internal sealed class DumbLine
    {
        public string ToNick;
        public string FromNick;
        public string MsgId;
        public int I;
        public int N;
        public string Chunk;
    }

    /// <summary>
    /// DUMB v1 wire + PSK AES-256-GCM. AAD = lower(channel)|lower(to)|lower(from)|lower(id)|dumb-v1
    /// Chunk 300, n &lt;= 64. Matches scripts/seal.py dumb_seal_bytes / dumb_open_bytes / dumb_irc_lines.
    /// </summary>
    internal static class DumbCrypto
    {
        public const int Chunk = 300;
        public const int MaxN = 64;
        public const double BagTtlS = 120.0;
        public static readonly Regex MsgidRe = new Regex("^[a-fA-F0-9]{16}$", RegexOptions.Compiled);
        public static readonly Regex NickRe = new Regex("^[A-Za-z\\[\\]^`{|}][A-Za-z0-9\\[\\]^`{|_-]{0,31}$", RegexOptions.Compiled);

        public static string Lower(string s)
        {
            return s == null ? "" : s.ToLowerInvariant();
        }

        public static byte[] DumbAad(string channel, string toNick, string fromNick, string msgId)
        {
            string a = Lower(channel) + "|" + Lower(toNick) + "|" + Lower(fromNick) + "|" + Lower(msgId) + "|dumb-v1";
            return Encoding.UTF8.GetBytes(a);
        }

        public static byte[] Seal(byte[] key32, string channel, string toNick, string fromNick, string msgId, byte[] plaintext)
        {
            byte[] nonce = new byte[12];
            using (RNGCryptoServiceProvider rng = new RNGCryptoServiceProvider())
                rng.GetBytes(nonce);
            byte[] aad = DumbAad(channel, toNick, fromNick, msgId);
            byte[] ct = Aes256Gcm.Encrypt(key32, nonce, aad, plaintext);
            byte[] blob = new byte[12 + ct.Length];
            Buffer.BlockCopy(nonce, 0, blob, 0, 12);
            Buffer.BlockCopy(ct, 0, blob, 12, ct.Length);
            return blob;
        }

        public static byte[] Open(byte[] key32, string channel, string toNick, string fromNick, string msgId, byte[] blob)
        {
            if (blob == null || blob.Length < 12 + 16)
                return null;
            byte[] nonce = new byte[12];
            Buffer.BlockCopy(blob, 0, nonce, 0, 12);
            byte[] ct = new byte[blob.Length - 12];
            Buffer.BlockCopy(blob, 12, ct, 0, ct.Length);
            return Aes256Gcm.Decrypt(key32, nonce, DumbAad(channel, toNick, fromNick, msgId), ct);
        }

        public static string B64(byte[] data)
        {
            if (data == null)
                return "";
            return Convert.ToBase64String(data);
        }

        public static byte[] B64d(string text)
        {
            if (string.IsNullOrEmpty(text))
                return new byte[0];
            try
            {
                return Convert.FromBase64String(text.Trim());
            }
            catch (FormatException)
            {
                return null;
            }
        }

        public static string[] IrcLines(byte[] blob, string toNick, string fromNick, string msgId)
        {
            string payload = B64(blob);
            int n = (payload.Length + Chunk - 1) / Chunk;
            if (n < 1)
                n = 1;
            if (n > MaxN)
                throw new InvalidOperationException("too many chunks");
            string[] lines = new string[n];
            for (int i = 0; i < n; i++)
            {
                int start = i * Chunk;
                int len = payload.Length - start;
                if (len > Chunk)
                    len = Chunk;
                if (len < 0)
                    len = 0;
                string part = payload.Length == 0 ? "" : payload.Substring(start, len);
                lines[i] = "DUMB v1 " + toNick + " " + fromNick + " " + msgId + " " + (i + 1).ToString() + " " + n.ToString() + " " + part;
            }
            return lines;
        }

        public static DumbLine ParseLine(string body)
        {
            if (body == null)
                return null;
            string text = body.Trim();
            if (!text.StartsWith("DUMB v1 ", StringComparison.Ordinal))
                return null;
            string[] bits = text.Split(new char[] { ' ' });
            if (bits.Length != 8)
                return null;
            string toNick = bits[2];
            string fromNick = bits[3];
            string msgId = bits[4];
            int i, n;
            if (!int.TryParse(bits[5], out i) || !int.TryParse(bits[6], out n))
                return null;
            if (bits[5].Length > 2 || bits[6].Length > 2)
                return null;
            if (n < 1 || n > MaxN || i < 1 || i > n)
                return null;
            if (!MsgidRe.IsMatch(msgId) || !NickRe.IsMatch(toNick) || !NickRe.IsMatch(fromNick))
                return null;
            DumbLine ln = new DumbLine();
            ln.ToNick = toNick;
            ln.FromNick = fromNick;
            ln.MsgId = msgId;
            ln.I = i;
            ln.N = n;
            ln.Chunk = bits[7];
            return ln;
        }

        public static int HexDecode(string hex, byte[] dest)
        {
            if (hex == null || (hex.Length % 2) != 0)
                return -1;
            int n = hex.Length / 2;
            if (n > dest.Length)
                return -1;
            for (int i = 0; i < n; i++)
            {
                int hi = HexNibble(hex[i * 2]);
                int lo = HexNibble(hex[i * 2 + 1]);
                if (hi < 0 || lo < 0)
                    return -1;
                dest[i] = (byte)((hi << 4) | lo);
            }
            return n;
        }

        private static int HexNibble(char c)
        {
            if (c >= '0' && c <= '9')
                return c - '0';
            if (c >= 'a' && c <= 'f')
                return c - 'a' + 10;
            if (c >= 'A' && c <= 'F')
                return c - 'A' + 10;
            return -1;
        }

        public static string Sha256Hex(byte[] data)
        {
            using (SHA256Managed sha = new SHA256Managed())
            {
                byte[] d = sha.ComputeHash(data == null ? new byte[0] : data);
                char[] hex = new char[d.Length * 2];
                const string digits = "0123456789abcdef";
                for (int i = 0; i < d.Length; i++)
                {
                    hex[i * 2] = digits[(d[i] >> 4) & 0xf];
                    hex[i * 2 + 1] = digits[d[i] & 0xf];
                }
                return new string(hex);
            }
        }
    }

    internal sealed class FragmentStore
    {
        private sealed class Bag
        {
            public int N;
            public Dictionary<int, string> Parts = new Dictionary<int, string>();
            public DateTime T0;
        }

        private readonly Dictionary<string, Bag> _bags = new Dictionary<string, Bag>();

        public string Add(DumbLine line)
        {
            DateTime now = DateTime.UtcNow;
            List<string> dead = new List<string>();
            foreach (KeyValuePair<string, Bag> kv in _bags)
            {
                if ((now - kv.Value.T0).TotalSeconds > DumbCrypto.BagTtlS)
                    dead.Add(kv.Key);
            }
            for (int i = 0; i < dead.Count; i++)
                _bags.Remove(dead[i]);
            if (line.N > DumbCrypto.MaxN || line.I < 1 || line.I > line.N)
                return null;
            string key = DumbCrypto.Lower(line.FromNick) + "\0" + DumbCrypto.Lower(line.MsgId);
            Bag bag;
            if (!_bags.TryGetValue(key, out bag))
            {
                bag = new Bag();
                bag.N = line.N;
                bag.T0 = now;
                _bags[key] = bag;
            }
            if (bag.N != line.N)
                return null;
            string prev;
            if (bag.Parts.TryGetValue(line.I, out prev) && prev != line.Chunk)
            {
                _bags.Remove(key);
                return null;
            }
            bag.Parts[line.I] = line.Chunk;
            if (bag.Parts.Count < bag.N)
                return null;
            StringBuilder sb = new StringBuilder();
            for (int j = 1; j <= bag.N; j++)
            {
                string p;
                if (!bag.Parts.TryGetValue(j, out p))
                {
                    _bags.Remove(key);
                    return null;
                }
                sb.Append(p);
            }
            _bags.Remove(key);
            return sb.ToString();
        }
    }
}
