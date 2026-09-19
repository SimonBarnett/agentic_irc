using System;
using System.Collections.Generic;
using System.IO;
using System.Net.Security;
using System.Net.Sockets;
using System.Security.Authentication;
using System.Security.Cryptography.X509Certificates;
using System.Text;
using System.Threading;

namespace AircDumb
{
    internal sealed class Connector
    {
        public const int FloodMs = 800;
        public const int CapaMs = 600000;
        public const int SettleMs = 1000;

        public string OriginalNick;
        public string LiveNick;
        public string Chan;
        public string Home;
        public string AllowPath;
        public string Host;
        public int Port;
        public string Realname;
        public string Hello;
        public bool TlsInsecure;
        public bool AllowMeta;
        public HashSet<string> Operators;
        public HashSet<string> AllowBin;
        public byte[] Key;
        public readonly List<string> Sent = new List<string>();
        public readonly FragmentStore Fragments = new FragmentStore();
        public readonly ManualResetEvent Stop = new ManualResetEvent(false);

        private Stream _stream;
        private TcpClient _tcp;
        private readonly object _lock = new object();
        private readonly ManualResetEvent _ready = new ManualResetEvent(false);
        private readonly ManualResetEvent _joined = new ManualResetEvent(false);
        private readonly ManualResetEvent _dead = new ManualResetEvent(false);
        private Thread _reader;

        public string CapaLine()
        {
            string psk = Key != null ? "1" : "0";
            return "CAPA v1 dumb nick=" + OriginalNick
                + " verbs=ping,sysinfo,exec,get,put psk=" + psk
                + " agpk=0 jail=" + AllowPath;
        }

        public void Send(string line)
        {
            lock (Sent)
                Sent.Add(line);
            Stream s = _stream;
            if (s == null)
                return;
            byte[] data = Encoding.UTF8.GetBytes(line + "\r\n");
            lock (_lock)
                s.Write(data, 0, data.Length);
        }

        public void Say(string msg)
        {
            Send("PRIVMSG " + Chan + " :" + msg);
            Thread.Sleep(FloodMs);
        }

        public Stream Connect()
        {
            TcpClient tcp = new TcpClient();
            IAsyncResult ar = tcp.BeginConnect(Host, Port, null, null);
            if (!ar.AsyncWaitHandle.WaitOne(20000, false))
            {
                try { tcp.Close(); }
                catch { }
                throw new TimeoutException("connect");
            }
            tcp.EndConnect(ar);
            _tcp = tcp;
            SslStream ssl = new SslStream(tcp.GetStream(), false, ValidateCert);
            ssl.AuthenticateAsClient(Host, null, SslProtocols.Tls12, !TlsInsecure);
            return ssl;
        }

        private bool ValidateCert(object sender, X509Certificate cert, X509Chain chain, SslPolicyErrors errors)
        {
            if (TlsInsecure)
                return true;
            return errors == SslPolicyErrors.None;
        }

        public void HandleDumb(string src, string body)
        {
            DumbLine dl = DumbCrypto.ParseLine(body);
            if (dl == null)
                return;
            if (!string.IsNullOrEmpty(dl.FromNick) && !string.Equals(dl.FromNick, src, StringComparison.OrdinalIgnoreCase))
            {
                JobRunner.Info("INFO DUMB prefix != from_nick, drop");
                return;
            }
            if (!string.Equals(dl.ToNick, OriginalNick, StringComparison.OrdinalIgnoreCase)
                && !string.Equals(dl.ToNick, LiveNick, StringComparison.OrdinalIgnoreCase))
                return;
            if (!Operators.Contains(src))
            {
                JobRunner.Info("INFO dumb drop operator from=" + src);
                return;
            }
            string payload = Fragments.Add(dl);
            if (payload == null)
                return;
            if (Key == null)
            {
                JobRunner.Info("INFO dumb job id=" + dl.MsgId + " decrypt failed");
                return;
            }
            byte[] blob = DumbCrypto.B64d(payload);
            byte[] pt = blob == null ? null : DumbCrypto.Open(Key, Chan, dl.ToNick, src, dl.MsgId, blob);
            string job;
            try
            {
                if (pt == null)
                    throw new InvalidOperationException("open");
                job = Encoding.UTF8.GetString(pt);
            }
            catch
            {
                JobRunner.Info("INFO dumb job id=" + dl.MsgId + " decrypt failed");
                return;
            }
            string result = JobRunner.RunJob(job, Operators, src, AllowPath, AllowBin, AllowMeta, Home);
            string rid = Json.GetString(job, "id");
            if (string.IsNullOrEmpty(rid))
                rid = dl.MsgId;
            byte[] outBlob = DumbCrypto.Seal(Key, Chan, src, OriginalNick, rid, Encoding.UTF8.GetBytes(result));
            string[] lines = DumbCrypto.IrcLines(outBlob, src, OriginalNick, rid);
            for (int i = 0; i < lines.Length; i++)
                Say(lines[i]);
            string op = Json.GetString(job, "op") ?? "";
            JobRunner.Info("INFO dumb job id=" + dl.MsgId + " op=" + op + " from=" + src);
        }

        public void HandlePrivmsg(string prefix, string target, string body)
        {
            if (!string.Equals(target, Chan, StringComparison.OrdinalIgnoreCase))
                return;
            string src = prefix;
            int bang = prefix.IndexOf('!');
            if (bang >= 0)
                src = prefix.Substring(0, bang);
            if (src.StartsWith(":"))
                src = src.Substring(1);
            HandleDumb(src, body);
        }

        private void Reader()
        {
            Stream s = _stream;
            byte[] buf = new byte[4096];
            MemoryStream acc = new MemoryStream();
            try
            {
                while (!Stop.WaitOne(0, false))
                {
                    int n = s.Read(buf, 0, buf.Length);
                    if (n <= 0)
                        return;
                    acc.Write(buf, 0, n);
                    byte[] all = acc.ToArray();
                    int start = 0;
                    for (int i = 0; i < all.Length; i++)
                    {
                        if (all[i] != (byte)'\n')
                            continue;
                        int len = i - start;
                        if (len > 0 && all[i - 1] == (byte)'\r')
                            len--;
                        string t = Encoding.UTF8.GetString(all, start, len);
                        start = i + 1;
                        DispatchLine(t);
                    }
                    if (start > 0)
                    {
                        acc.SetLength(0);
                        if (start < all.Length)
                            acc.Write(all, start, all.Length - start);
                    }
                }
            }
            catch (IOException)
            {
            }
            catch (ObjectDisposedException)
            {
            }
            finally
            {
                _dead.Set();
            }
        }

        private void DispatchLine(string t)
        {
            if (t.StartsWith("PING ", StringComparison.Ordinal))
            {
                Send("PONG " + t.Substring(5));
                return;
            }
            string prefix = "";
            string rest = t;
            if (t.StartsWith(":"))
            {
                int sp = t.IndexOf(' ');
                if (sp < 0)
                    return;
                prefix = t.Substring(1, sp - 1);
                rest = t.Substring(sp + 1);
            }
            string[] parts = rest.Split(new char[] { ' ' });
            string cmd = parts.Length > 0 ? parts[0] : "";
            if (cmd == "001")
                _ready.Set();
            if (cmd == "JOIN")
            {
                string ch = parts.Length > 1 ? parts[1].TrimStart(':') : "";
                if (string.Equals(ch, Chan, StringComparison.OrdinalIgnoreCase))
                    _joined.Set();
            }
            if (cmd == "433" || cmd == "432")
            {
                if (LiveNick == OriginalNick)
                {
                    LiveNick = OriginalNick + "_l";
                    Send("NICK " + LiveNick);
                    JobRunner.Info("INFO nick -> " + LiveNick + " (still accept " + OriginalNick + ")");
                }
            }
            if (cmd == "PRIVMSG")
            {
                int trail = t.IndexOf(" :", StringComparison.Ordinal);
                if (trail < 0)
                    return;
                string target = parts.Length > 1 ? parts[1].TrimStart(':') : "";
                HandlePrivmsg(prefix, target, t.Substring(trail + 2));
            }
        }

        public void Session()
        {
            _ready.Reset();
            _joined.Reset();
            _dead.Reset();
            LiveNick = OriginalNick;
            _stream = Connect();
            _reader = new Thread(Reader);
            _reader.IsBackground = true;
            _reader.Start();
            Send("CAP LS 302");
            Send("NICK " + LiveNick);
            string rn = string.IsNullOrEmpty(Realname) ? "airc-dumb" : Realname;
            Send("USER " + LiveNick + " 0 * :" + rn);
            if (!_ready.WaitOne(30000, false))
                throw new TimeoutException("NO 001");
            Thread.Sleep(SettleMs);
            Send("JOIN " + Chan);
            if (!_joined.WaitOne(30000, false))
                throw new TimeoutException("NO JOIN");
            if (!string.IsNullOrEmpty(Hello))
                Say(Hello);
            Say(CapaLine());
            JobRunner.Info("INFO joined " + Chan + " as " + LiveNick);
            DateTime lastCapa = DateTime.UtcNow;
            while (!Stop.WaitOne(0, false))
            {
                if (_dead.WaitOne(1000, false))
                    break;
                if ((DateTime.UtcNow - lastCapa).TotalMilliseconds >= CapaMs)
                {
                    Say(CapaLine());
                    lastCapa = DateTime.UtcNow;
                }
            }
        }

        public void CloseSock()
        {
            try
            {
                if (_stream != null)
                    _stream.Close();
            }
            catch { }
            try
            {
                if (_tcp != null)
                    _tcp.Close();
            }
            catch { }
            _stream = null;
            _tcp = null;
        }

        public void Close()
        {
            Stop.Set();
            CloseSock();
            _dead.Set();
        }

        public void RunForever()
        {
            double backoff = 1.0;
            Random rng = new Random();
            while (!Stop.WaitOne(0, false))
            {
                try
                {
                    Session();
                    backoff = 1.0;
                }
                catch (Exception e)
                {
                    JobRunner.Info("INFO session end " + e.GetType().Name);
                }
                CloseSock();
                if (Stop.WaitOne(0, false))
                    break;
                double delay = backoff + rng.NextDouble();
                JobRunner.Info("INFO reconnect in " + delay.ToString("0.0") + "s");
                Thread.Sleep((int)(delay * 1000));
                backoff = Math.Min(60.0, backoff * 2);
            }
        }
    }
}
