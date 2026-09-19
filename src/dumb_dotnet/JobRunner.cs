using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;
using System.Text;
using System.Threading;

namespace AircDumb
{
    internal static class JobRunner
    {
        public static readonly Encoding Utf8 = new UTF8Encoding(false);
        public const int ResultBytesMax = 8192;
        public static readonly string[] DefaultBins = new string[]
        {
            "cmd.exe", "powershell.exe", "hostname.exe", "ipconfig.exe", "whoami.exe",
            "hostname", "ipconfig", "whoami"
        };
        private static readonly char[] MetaChars = new char[] { '&', '|', '>', '<', '^' };
        private static readonly object Busy = new object();

        public static void Info(string msg)
        {
            Console.WriteLine(msg);
            Console.Out.Flush();
        }

        public static HashSet<string> ParseOperators(string raw)
        {
            HashSet<string> set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            if (raw == null)
                return set;
            string[] parts = raw.Split(new char[] { ',' });
            for (int i = 0; i < parts.Length; i++)
            {
                string x = parts[i].Trim();
                if (x.Length > 0)
                    set.Add(x);
            }
            return set;
        }

        public static HashSet<string> ParseBins(string extra)
        {
            HashSet<string> set = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            for (int i = 0; i < DefaultBins.Length; i++)
                set.Add(DefaultBins[i]);
            if (!string.IsNullOrEmpty(extra))
            {
                string[] parts = extra.Split(new char[] { ',' });
                for (int i = 0; i < parts.Length; i++)
                {
                    string x = parts[i].Trim();
                    if (x.Length > 0)
                        set.Add(x);
                }
            }
            return set;
        }

        public static void ProtectPath(string path)
        {
            if (string.IsNullOrEmpty(path) || !File.Exists(path) && !Directory.Exists(path))
                return;
            string user = Environment.GetEnvironmentVariable("USERNAME");
            if (string.IsNullOrEmpty(user))
                user = "Administrators";
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = "icacls";
            psi.Arguments = "\"" + path + "\" /inheritance:r /grant:r \"NT AUTHORITY\\SYSTEM:(F)\" /grant:r \"BUILTIN\\Administrators:(F)\" /grant:r \"" + user + ":(F)\"";
            psi.UseShellExecute = false;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.CreateNoWindow = true;
            using (Process p = Process.Start(psi))
            {
                p.WaitForExit(15000);
                if (!p.HasExited || p.ExitCode != 0)
                    throw new InvalidOperationException("icacls exit " + (p.HasExited ? p.ExitCode.ToString() : "timeout"));
            }
        }

        public static string JailRoot(string allow)
        {
            string p = Path.GetFullPath(allow);
            Directory.CreateDirectory(p);
            ProtectPath(p);
            return p;
        }

        public static bool InJail(string root, string target)
        {
            try
            {
                if (string.IsNullOrEmpty(target))
                    return false;
                if (target.StartsWith("\\\\") || target.StartsWith("//"))
                    return false;
                string t = Path.GetFullPath(target);
                string r = Path.GetFullPath(root);
                if (t.StartsWith("\\\\") || t.StartsWith("//"))
                    return false;
                r = TrimSlash(r);
                t = TrimSlash(t);
                if (string.Equals(r, t, StringComparison.OrdinalIgnoreCase))
                    return true;
                if (t.Length > r.Length && t.StartsWith(r, StringComparison.OrdinalIgnoreCase))
                {
                    char c = t[r.Length];
                    if (c == '\\' || c == '/')
                        return true;
                }
                return false;
            }
            catch
            {
                return false;
            }
        }

        private static string TrimSlash(string p)
        {
            while (p.Length > 3 && (p[p.Length - 1] == '\\' || p[p.Length - 1] == '/'))
                p = p.Substring(0, p.Length - 1);
            return p;
        }

        public static bool IsSecretName(string path)
        {
            string bn = Path.GetFileName(path);
            if (string.IsNullOrEmpty(bn))
                return false;
            return string.Equals(bn, "identity.json", StringComparison.OrdinalIgnoreCase)
                || string.Equals(bn, "connector.key", StringComparison.OrdinalIgnoreCase)
                || string.Equals(bn, "peers.json", StringComparison.OrdinalIgnoreCase);
        }

        public static byte[] LoadConnectorKey(string path)
        {
            if (!File.Exists(path))
                return null;
            byte[] raw = File.ReadAllBytes(path);
            byte[] magic = Encoding.ASCII.GetBytes("AIRC1");
            if (raw.Length >= 5 && raw[0] == magic[0] && raw[1] == magic[1] && raw[2] == magic[2] && raw[3] == magic[3] && raw[4] == magic[4])
            {
                byte[] wrapped = new byte[raw.Length - 5];
                Buffer.BlockCopy(raw, 5, wrapped, 0, wrapped.Length);
                byte[] plain = ProtectedData.Unprotect(wrapped, null, DataProtectionScope.CurrentUser);
                if (plain == null || plain.Length != 32)
                    throw new InvalidOperationException("key unreadable");
                return plain;
            }
            if (raw.Length == 32)
                return raw;
            throw new InvalidOperationException("key unreadable");
        }

        public static void SpillResults(string home, string jid, string stdout, string stderr)
        {
            string dir = Path.Combine(home, "dumb");
            dir = Path.Combine(dir, "results");
            Directory.CreateDirectory(dir);
            string dest = Path.Combine(dir, jid + ".txt");
            string body = "--- stdout ---\n" + (stdout ?? "") + "\n--- stderr ---\n" + (stderr ?? "") + "\n";
            File.WriteAllText(dest, body, Utf8);
            try { ProtectPath(dest); }
            catch { }
        }

        public static string RunJob(string jobJson, HashSet<string> operators, string fromNick, string allowPath, HashSet<string> allowBin, bool allowMeta, string home)
        {
            string op = Json.GetString(jobJson, "op") ?? "";
            string jid = Json.GetString(jobJson, "id") ?? "";
            if (!operators.Contains(fromNick ?? ""))
                return Json.Err(op, jid, "operator");
            if (op == "ping")
                return "{\"v\":1,\"op\":\"ping\",\"id\":" + Json.Str(jid) + ",\"ok\":true,\"rc\":0}";
            if (op == "sysinfo")
            {
                string machine = Environment.GetEnvironmentVariable("COMPUTERNAME") ?? "";
                string user = Environment.GetEnvironmentVariable("USERNAME") ?? "";
                return "{\"v\":1,\"op\":\"sysinfo\",\"id\":" + Json.Str(jid)
                    + ",\"ok\":true,\"sys\":{\"os\":\"win32\",\"machine\":" + Json.Str(machine)
                    + ",\"user\":" + Json.Str(user) + "}}";
            }
            if (op == "get" || op == "put")
            {
                string raw = Json.GetString(jobJson, "path");
                if (string.IsNullOrEmpty(raw))
                    raw = Json.GetString(jobJson, "cwd") ?? "";
                if (raw.StartsWith("\\\\") || raw.StartsWith("//"))
                    return Json.Err(op, jid, "jail");
                string dest = raw;
                if (!Path.IsPathRooted(dest))
                    dest = Path.Combine(allowPath, dest);
                if (!InJail(allowPath, dest))
                    return Json.Err(op, jid, "jail");
                if (IsSecretName(dest))
                    return Json.Err(op, jid, "jail");
                try
                {
                    if (op == "get")
                    {
                        byte[] data = File.ReadAllBytes(dest);
                        string hex = DumbCrypto.Sha256Hex(data);
                        string b64 = data.Length <= 12 * 1024 ? DumbCrypto.B64(data) : "";
                        return "{\"v\":1,\"op\":\"get\",\"id\":" + Json.Str(jid) + ",\"ok\":true,\"sha256\":" + Json.Str(hex) + ",\"b64\":" + Json.Str(b64) + "}";
                    }
                    string b64in = Json.GetString(jobJson, "b64") ?? "";
                    byte[] rawB = string.IsNullOrEmpty(b64in) ? new byte[0] : DumbCrypto.B64d(b64in);
                    if (rawB == null)
                        rawB = new byte[0];
                    string parent = Path.GetDirectoryName(dest);
                    if (!string.IsNullOrEmpty(parent))
                        Directory.CreateDirectory(parent);
                    File.WriteAllBytes(dest, rawB);
                    return "{\"v\":1,\"op\":\"put\",\"id\":" + Json.Str(jid) + ",\"ok\":true,\"sha256\":" + Json.Str(DumbCrypto.Sha256Hex(rawB)) + "}";
                }
                catch
                {
                    return Json.Err(op, jid, "jail");
                }
            }
            if (op == "exec")
            {
                if (!Monitor.TryEnter(Busy))
                    return Json.Err(op, jid, "busy");
                try
                {
                    string[] argv = Json.GetStringArray(jobJson, "argv");
                    if (argv == null || argv.Length < 1)
                        return Json.Err(op, jid, "bin");
                    string bin0 = Path.GetFileName(argv[0]);
                    if (string.IsNullOrEmpty(bin0) || !allowBin.Contains(bin0))
                        return Json.Err(op, jid, "bin");
                    string joined = string.Join(" ", argv);
                    if (joined.IndexOf("..", StringComparison.Ordinal) >= 0
                        || joined.IndexOf("\\\\", StringComparison.Ordinal) >= 0
                        || joined.IndexOf("//", StringComparison.Ordinal) >= 0)
                        return Json.Err(op, jid, "jail");
                    if (!allowMeta && joined.IndexOfAny(MetaChars) >= 0)
                        return Json.Err(op, jid, "bin");
                    int timeout = Json.GetInt(jobJson, "timeout_s", 20);
                    if (timeout < 1)
                        timeout = 1;
                    if (timeout > 60)
                        timeout = 60;
                    string cwd = Json.GetString(jobJson, "cwd");
                    if (string.IsNullOrEmpty(cwd))
                        cwd = allowPath;
                    if (cwd.StartsWith("\\\\") || cwd.StartsWith("//"))
                        return Json.Err(op, jid, "jail");
                    if (!InJail(allowPath, cwd))
                        return Json.Err(op, jid, "jail");
                    cwd = Path.GetFullPath(cwd);
                    string stdout, stderr;
                    int rc;
                    int st = Exec(argv, cwd, timeout, out stdout, out stderr, out rc);
                    if (st == -5)
                        return Json.Err(op, jid, "timeout");
                    if (st != 0)
                        return Json.Err(op, jid, "bin");
                    bool trunc = false;
                    if ((stdout.Length + stderr.Length) > ResultBytesMax)
                    {
                        trunc = true;
                        if (!string.IsNullOrEmpty(home) && !string.IsNullOrEmpty(jid))
                            SpillResults(home, jid, stdout, stderr);
                        if (stdout.Length > 4000)
                            stdout = stdout.Substring(0, 4000);
                        if (stderr.Length > 4000)
                            stderr = stderr.Substring(0, 4000);
                    }
                    return "{\"v\":1,\"op\":\"exec\",\"id\":" + Json.Str(jid)
                        + ",\"ok\":" + (rc == 0 ? "true" : "false")
                        + ",\"rc\":" + rc.ToString()
                        + ",\"stdout\":" + Json.Str(stdout)
                        + ",\"stderr\":" + Json.Str(stderr)
                        + ",\"truncated\":" + (trunc ? "true" : "false") + "}";
                }
                finally
                {
                    Monitor.Exit(Busy);
                }
            }
            return Json.Err(op, jid, "op");
        }

        private static int Exec(string[] argv, string cwd, int timeoutS, out string stdout, out string stderr, out int rc)
        {
            stdout = "";
            stderr = "";
            rc = 1;
            ProcessStartInfo psi = new ProcessStartInfo();
            psi.FileName = argv[0];
            psi.Arguments = QuoteRest(argv);
            psi.WorkingDirectory = cwd;
            psi.UseShellExecute = false;
            psi.RedirectStandardOutput = true;
            psi.RedirectStandardError = true;
            psi.CreateNoWindow = true;
            try
            {
                using (Process p = new Process())
                {
                    p.StartInfo = psi;
                    StringBuilder so = new StringBuilder();
                    StringBuilder se = new StringBuilder();
                    p.OutputDataReceived += delegate(object s, DataReceivedEventArgs e)
                    {
                        if (e.Data != null)
                            lock (so) { so.AppendLine(e.Data); }
                    };
                    p.ErrorDataReceived += delegate(object s, DataReceivedEventArgs e)
                    {
                        if (e.Data != null)
                            lock (se) { se.AppendLine(e.Data); }
                    };
                    if (!p.Start())
                        return -3;
                    p.BeginOutputReadLine();
                    p.BeginErrorReadLine();
                    if (!p.WaitForExit(timeoutS * 1000))
                    {
                        try { p.Kill(); }
                        catch { }
                        return -5;
                    }
                    p.WaitForExit();
                    rc = p.ExitCode;
                    lock (so) { stdout = so.ToString(); }
                    lock (se) { stderr = se.ToString(); }
                    return 0;
                }
            }
            catch
            {
                return -3;
            }
        }

        private static string QuoteRest(string[] argv)
        {
            if (argv.Length < 2)
                return "";
            StringBuilder sb = new StringBuilder();
            for (int i = 1; i < argv.Length; i++)
            {
                if (i > 1)
                    sb.Append(' ');
                sb.Append(QuoteArg(argv[i]));
            }
            return sb.ToString();
        }

        private static string QuoteArg(string a)
        {
            if (a == null)
                a = "";
            bool need = a.IndexOfAny(new char[] { ' ', '\t', '"' }) >= 0;
            if (!need)
                return a;
            StringBuilder sb = new StringBuilder();
            sb.Append('"');
            for (int i = 0; i < a.Length; i++)
            {
                if (a[i] == '"')
                    sb.Append('\\');
                sb.Append(a[i]);
            }
            sb.Append('"');
            return sb.ToString();
        }

        public static void ApplyTrunc(string home, string jid, ref string stdout, ref string stderr, out bool truncated)
        {
            truncated = false;
            if (((stdout ?? "").Length + (stderr ?? "").Length) <= ResultBytesMax)
                return;
            truncated = true;
            if (!string.IsNullOrEmpty(home) && !string.IsNullOrEmpty(jid))
                SpillResults(home, jid, stdout, stderr);
            if (stdout != null && stdout.Length > 4000)
                stdout = stdout.Substring(0, 4000);
            if (stderr != null && stderr.Length > 4000)
                stderr = stderr.Substring(0, 4000);
        }
    }

    internal static class Json
    {
        public static string Str(string s)
        {
            if (s == null)
                s = "";
            StringBuilder sb = new StringBuilder();
            sb.Append('"');
            for (int i = 0; i < s.Length; i++)
            {
                char c = s[i];
                if (c == '\\' || c == '"')
                {
                    sb.Append('\\');
                    sb.Append(c);
                }
                else if (c == '\n')
                    sb.Append("\\n");
                else if (c == '\r')
                    sb.Append("\\r");
                else if (c == '\t')
                    sb.Append("\\t");
                else if (c < 0x20)
                    sb.Append("\\u").Append(((int)c).ToString("x4"));
                else
                    sb.Append(c);
            }
            sb.Append('"');
            return sb.ToString();
        }

        public static string Err(string op, string id, string error)
        {
            return "{\"v\":1,\"op\":" + Str(op ?? "") + ",\"id\":" + Str(id ?? "") + ",\"ok\":false,\"error\":" + Str(error) + "}";
        }

        public static string GetString(string json, string key)
        {
            int p = FindKey(json, key);
            if (p < 0)
                return null;
            p = SkipWs(json, p);
            if (p >= json.Length || json[p] != '"')
                return null;
            p++;
            StringBuilder sb = new StringBuilder();
            while (p < json.Length && json[p] != '"')
            {
                if (json[p] == '\\' && p + 1 < json.Length)
                {
                    p++;
                    char e = json[p];
                    if (e == 'n')
                        sb.Append('\n');
                    else if (e == 'r')
                        sb.Append('\r');
                    else if (e == 't')
                        sb.Append('\t');
                    else if (e == 'u' && p + 4 < json.Length)
                    {
                        int code;
                        if (int.TryParse(json.Substring(p + 1, 4), System.Globalization.NumberStyles.HexNumber, null, out code))
                            sb.Append((char)code);
                        p += 4;
                    }
                    else
                        sb.Append(e);
                    p++;
                }
                else
                    sb.Append(json[p++]);
            }
            return sb.ToString();
        }

        public static int GetInt(string json, string key, int def)
        {
            int p = FindKey(json, key);
            if (p < 0)
                return def;
            p = SkipWs(json, p);
            int end = p;
            if (end < json.Length && json[end] == '-')
                end++;
            while (end < json.Length && json[end] >= '0' && json[end] <= '9')
                end++;
            int v;
            if (end > p && int.TryParse(json.Substring(p, end - p), out v))
                return v;
            return def;
        }

        public static string[] GetStringArray(string json, string key)
        {
            int p = FindKey(json, key);
            if (p < 0)
                return null;
            p = SkipWs(json, p);
            if (p >= json.Length || json[p] != '[')
                return null;
            p++;
            List<string> list = new List<string>();
            while (p < json.Length)
            {
                p = SkipWs(json, p);
                if (p < json.Length && json[p] == ',')
                {
                    p++;
                    p = SkipWs(json, p);
                }
                if (p < json.Length && json[p] == ']')
                    break;
                if (p >= json.Length || json[p] != '"')
                    return list.ToArray();
                p++;
                StringBuilder sb = new StringBuilder();
                while (p < json.Length && json[p] != '"')
                {
                    if (json[p] == '\\' && p + 1 < json.Length)
                    {
                        p++;
                        sb.Append(json[p]);
                        p++;
                    }
                    else
                        sb.Append(json[p++]);
                }
                if (p < json.Length && json[p] == '"')
                    p++;
                list.Add(sb.ToString());
            }
            return list.ToArray();
        }

        private static int SkipWs(string s, int p)
        {
            while (p < s.Length && (s[p] == ' ' || s[p] == '\t' || s[p] == '\r' || s[p] == '\n'))
                p++;
            return p;
        }

        private static int FindKey(string json, string key)
        {
            if (json == null || key == null)
                return -1;
            string needle = "\"" + key + "\"";
            int from = 0;
            while (true)
            {
                int i = json.IndexOf(needle, from, StringComparison.Ordinal);
                if (i < 0)
                    return -1;
                int p = SkipWs(json, i + needle.Length);
                if (p < json.Length && json[p] == ':')
                    return p + 1;
                from = i + 1;
            }
        }
    }
}
