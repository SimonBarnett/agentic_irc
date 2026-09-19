using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Threading;

namespace AircDumb
{
    internal static class Program
    {
        public const string Version = "0.1.0";

        private static int Main(string[] args)
        {
            try
            {
                System.Net.ServicePointManager.SecurityProtocol = (System.Net.SecurityProtocolType)3072;
            }
            catch { }

            Args a;
            try
            {
                a = Args.Parse(args);
            }
            catch (Exception e)
            {
                JobRunner.Info("INFO " + e.Message);
                return 2;
            }
            if (a.Help)
            {
                Usage();
                return 0;
            }
            if (a.Selftest)
                return Selftest();
            if (a.Operators.Count == 0)
            {
                JobRunner.Info("INFO installer MUST refuse empty --operators");
                return 2;
            }
            if (a.Offline)
                return Offline(a);
            if (string.IsNullOrEmpty(a.Nick) || string.IsNullOrEmpty(a.Channel) || string.IsNullOrEmpty(a.Home) || string.IsNullOrEmpty(a.AllowPathRaw))
            {
                Usage();
                return 2;
            }
            Connector c;
            try
            {
                c = BuildConnector(a);
            }
            catch (Exception e)
            {
                JobRunner.Info("INFO " + e.Message);
                return 2;
            }
            JobRunner.Info("INFO dumb connector " + a.Nick + " jail=" + c.AllowPath);
            Console.CancelKeyPress += delegate(object s, ConsoleCancelEventArgs e)
            {
                e.Cancel = true;
                c.Stop.Set();
            };
            try
            {
                if (a.Once)
                    c.Session();
                else
                    c.RunForever();
                return 0;
            }
            catch (Exception e)
            {
                JobRunner.Info("INFO session end " + e.GetType().Name);
                return 1;
            }
            finally
            {
                c.Close();
            }
        }

        private static void Usage()
        {
            JobRunner.Info("airc-dumb " + Version + " — net45 DUMB connector (not an LLM)");
            JobRunner.Info("usage: airc-dumb.exe --nick N --channel #chan --home DIR --allow-path DIR --operators nicks");
            JobRunner.Info("  [--host HOST] [--port N] [--hello TEXT] [--once] [--allow-meta] [--allow-bin list] [--tls-insecure]");
            JobRunner.Info("  --selftest   offline checks, no sockets");
            JobRunner.Info("  --offline --from-nick N --job-in job.json [--job-out result.json]");
            JobRunner.Info("empty --operators is refused. Python scripts/dumb_agent.py is the protocol reference.");
            JobRunner.Info("TLS 1.2 required on Server 2012 (SchUseStrongCrypto). --tls-insecure is lab/offline only.");
        }

        private static Connector BuildConnector(Args a)
        {
            string chan = a.Channel.StartsWith("#") ? a.Channel : "#" + a.Channel;
            if (chan.IndexOf('|') >= 0)
                throw new InvalidOperationException("channel must not contain |");
            string home = Path.GetFullPath(a.Home);
            Directory.CreateDirectory(home);
            string allow = JobRunner.JailRoot(a.AllowPathRaw);
            byte[] key = null;
            string kp = Path.Combine(Path.Combine(home, "dumb"), "connector.key");
            if (File.Exists(kp))
                key = JobRunner.LoadConnectorKey(kp);
            Connector c = new Connector();
            c.OriginalNick = a.Nick;
            c.LiveNick = a.Nick;
            c.Chan = chan;
            c.Home = home;
            c.AllowPath = allow;
            c.Host = string.IsNullOrEmpty(a.Host) ? DefaultHost() : a.Host;
            c.Port = a.Port;
            c.Realname = a.Realname;
            c.Hello = a.Hello;
            c.TlsInsecure = a.TlsInsecure;
            c.AllowMeta = a.AllowMeta;
            c.Operators = a.Operators;
            c.AllowBin = JobRunner.ParseBins(a.AllowBin);
            c.Key = key;
            return c;
        }

        private static string DefaultHost()
        {
            // Production default matches Python dumb_agent.py. Tests must pass --host explicitly.
            return "irc." + "libera" + ".chat";
        }

        private static int Offline(Args a)
        {
            if (string.IsNullOrEmpty(a.FromNick))
            {
                JobRunner.Info("INFO missing --from-nick");
                return 2;
            }
            if (string.IsNullOrEmpty(a.JobIn) || !File.Exists(a.JobIn))
            {
                JobRunner.Info("INFO cannot read --job-in");
                return 2;
            }
            string home = string.IsNullOrEmpty(a.Home) ? Path.GetTempPath() : Path.GetFullPath(a.Home);
            Directory.CreateDirectory(home);
            string allow = string.IsNullOrEmpty(a.AllowPathRaw) ? home : JobRunner.JailRoot(a.AllowPathRaw);
            string job = File.ReadAllText(a.JobIn, JobRunner.Utf8);
            string res = JobRunner.RunJob(job, a.Operators, a.FromNick, allow, JobRunner.ParseBins(a.AllowBin), a.AllowMeta, home);
            if (!string.IsNullOrEmpty(a.JobOut))
                File.WriteAllText(a.JobOut, res, JobRunner.Utf8);
            JobRunner.Info(res);
            return 0;
        }

        private static int Selftest()
        {
            int fails = 0;
            JobRunner.Info("INFO selftest airc-dumb " + Version);

            string tmp = Path.Combine(Path.GetTempPath(), "airc-dumb-" + ProcessId());
            Directory.CreateDirectory(tmp);
            string jail = Path.Combine(tmp, "drop");
            Directory.CreateDirectory(jail);

            HashSet<string> empty = JobRunner.ParseOperators("  ,  ");
            if (empty.Count != 0)
            {
                JobRunner.Info("FAIL empty operators parse");
                fails++;
            }
            else
                JobRunner.Info("INFO empty operators refused");

            if (JobRunner.InJail(jail, Path.Combine(jail, "..", "Windows", "win.ini"))
                || JobRunner.InJail(jail, "\\\\server\\share\\x")
                || JobRunner.InJail(jail, "//server/share/x"))
            {
                JobRunner.Info("FAIL jail escape");
                fails++;
            }
            else if (!JobRunner.InJail(jail, jail) || !JobRunner.InJail(jail, Path.Combine(jail, "n.txt")))
            {
                JobRunner.Info("FAIL jail root");
                fails++;
            }
            else
                JobRunner.Info("INFO jail refuse ok");

            byte[] key = new byte[32];
            if (DumbCrypto.HexDecode("00112233445566778899aabbccddeeff00112233445566778899aabbccddeeff", key) != 32)
            {
                JobRunner.Info("FAIL key hex");
                fails++;
            }
            byte[] blob = new byte[128];
            const string blobHex = "0102030405060708090a0b0c01507382d2268963858899fb4e9f767c14bc8fd55e95c4790ea2c59d7f03107e72e67adda31cd8f667954d7248703b3eb582e3b2f1d462c441bba7";
            int bn = DumbCrypto.HexDecode(blobHex, blob);
            byte[] slim = new byte[bn];
            Buffer.BlockCopy(blob, 0, slim, 0, bn);
            byte[] pt = DumbCrypto.Open(key, "#ops", "box", "alice", "0123456789abcdef", slim);
            const string want = "{\"v\":1,\"op\":\"ping\",\"id\":\"0123456789abcdef\"}";
            if (pt == null || Encoding.UTF8.GetString(pt) != want)
            {
                JobRunner.Info("FAIL aesgcm open");
                fails++;
            }
            else
                JobRunner.Info("INFO aesgcm vector ok");

            byte[] sealedPt = DumbCrypto.Seal(key, "#ops", "box", "alice", "0123456789abcdef", Encoding.UTF8.GetBytes(want));
            byte[] opened = DumbCrypto.Open(key, "#ops", "box", "alice", "0123456789abcdef", sealedPt);
            if (opened == null || Encoding.UTF8.GetString(opened) != want)
            {
                JobRunner.Info("FAIL aesgcm roundtrip");
                fails++;
            }
            else
                JobRunner.Info("INFO aesgcm roundtrip ok");

            DumbLine badN = DumbCrypto.ParseLine("DUMB v1 bob alice 0123456789abcdef 1 100 AAAA");
            if (badN != null)
            {
                JobRunner.Info("FAIL dumb n=100");
                fails++;
            }
            else
                JobRunner.Info("INFO dumb n=100 dropped");

            HashSet<string> ops = JobRunner.ParseOperators("alice");
            HashSet<string> bins = JobRunner.ParseBins("");
            string mallory = JobRunner.RunJob("{\"v\":1,\"op\":\"exec\",\"id\":\"0123456789abcdef\",\"argv\":[\"hostname\"]}", ops, "mallory", jail, bins, false, tmp);
            if (mallory.IndexOf("\"error\":\"operator\"", StringComparison.Ordinal) < 0)
            {
                JobRunner.Info("FAIL operator drop " + mallory);
                fails++;
            }
            else
                JobRunner.Info("INFO operator drop ok");

            string ping = JobRunner.RunJob("{\"v\":1,\"op\":\"ping\",\"id\":\"0123456789abcdef\"}", ops, "alice", jail, bins, false, tmp);
            if (ping.IndexOf("\"ok\":true", StringComparison.Ordinal) < 0 || ping.IndexOf("ping", StringComparison.Ordinal) < 0)
            {
                JobRunner.Info("FAIL ping " + ping);
                fails++;
            }
            else
                JobRunner.Info("INFO ping ok");

            string exec = JobRunner.RunJob("{\"v\":1,\"op\":\"exec\",\"id\":\"0123456789abcdef\",\"argv\":[\"hostname\"]}", ops, "alice", jail, bins, false, tmp);
            if (exec.IndexOf("\"op\":\"exec\"", StringComparison.Ordinal) < 0 || exec.IndexOf("\"rc\":", StringComparison.Ordinal) < 0 || exec.IndexOf("stdout", StringComparison.Ordinal) < 0)
            {
                JobRunner.Info("FAIL exec framing " + exec);
                fails++;
            }
            else
                JobRunner.Info("INFO exec stdout/rc ok");

            string big = new string('B', 9000);
            string errb = "";
            bool trunc;
            JobRunner.ApplyTrunc(tmp, "0123456789abcdef", ref big, ref errb, out trunc);
            string spill = Path.Combine(Path.Combine(Path.Combine(tmp, "dumb"), "results"), "0123456789abcdef.txt");
            if (!trunc || big.Length > 4000 || !File.Exists(spill))
            {
                JobRunner.Info("FAIL truncation");
                fails++;
            }
            else
                JobRunner.Info("INFO truncation flag ok");

            Connector c = new Connector();
            c.OriginalNick = "box";
            c.LiveNick = "box";
            c.Chan = "#ops";
            c.Home = tmp;
            c.AllowPath = jail;
            c.Operators = ops;
            c.AllowBin = bins;
            c.Key = key;
            byte[] jobBlob = DumbCrypto.Seal(key, "#ops", "box", "mallory", "0123456789abcdef",
                Encoding.UTF8.GetBytes("{\"v\":1,\"op\":\"exec\",\"id\":\"0123456789abcdef\",\"argv\":[\"hostname\"]}"));
            string[] malLines = DumbCrypto.IrcLines(jobBlob, "box", "mallory", "0123456789abcdef");
            for (int i = 0; i < malLines.Length; i++)
                c.HandlePrivmsg("mallory!u@h", "#ops", malLines[i]);
            bool leaked = false;
            lock (c.Sent)
            {
                for (int i = 0; i < c.Sent.Count; i++)
                {
                    if (c.Sent[i].IndexOf("DUMB v1", StringComparison.Ordinal) >= 0 || c.Sent[i].StartsWith("PRIVMSG", StringComparison.Ordinal))
                        leaked = true;
                }
            }
            if (leaked)
            {
                JobRunner.Info("FAIL D2 result ciphertext");
                fails++;
            }
            else
                JobRunner.Info("INFO D2 no result ciphertext ok");

            byte[] pingBlob = DumbCrypto.Seal(key, "#ops", "box", "alice", "fedcba9876543210",
                Encoding.UTF8.GetBytes("{\"v\":1,\"op\":\"ping\",\"id\":\"fedcba9876543210\"}"));
            string[] pingLines = DumbCrypto.IrcLines(pingBlob, "box", "alice", "fedcba9876543210");
            for (int i = 0; i < pingLines.Length; i++)
                c.HandlePrivmsg("alice!u@h", "#ops", pingLines[i]);
            bool got = false;
            lock (c.Sent)
            {
                for (int i = 0; i < c.Sent.Count; i++)
                {
                    if (c.Sent[i].IndexOf("DUMB v1", StringComparison.Ordinal) >= 0)
                        got = true;
                }
            }
            if (!got)
            {
                JobRunner.Info("FAIL ping result on wire");
                fails++;
            }
            else
                JobRunner.Info("INFO ping result on wire ok");

            string capa = c.CapaLine();
            if (capa.IndexOf("CAPA v1 dumb", StringComparison.Ordinal) < 0 || capa.IndexOf("verbs=ping,sysinfo,exec,get,put", StringComparison.Ordinal) < 0)
            {
                JobRunner.Info("FAIL capa " + capa);
                fails++;
            }
            else
                JobRunner.Info("INFO capa ok");

            try
            {
                if (Directory.Exists(tmp))
                    Directory.Delete(tmp, true);
            }
            catch { }

            if (fails != 0)
            {
                JobRunner.Info("INFO selftest FAIL " + fails.ToString());
                return 1;
            }
            JobRunner.Info("INFO selftest ok");
            return 0;
        }

        private static string ProcessId()
        {
            return System.Diagnostics.Process.GetCurrentProcess().Id.ToString();
        }

        private sealed class Args
        {
            public string Nick;
            public string Channel;
            public string Home;
            public string AllowPathRaw;
            public HashSet<string> Operators = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
            public string Hello = "";
            public string Host;
            public int Port = 6697;
            public string Realname = "airc-dumb";
            public bool Once;
            public bool AllowMeta;
            public string AllowBin = "";
            public bool Selftest;
            public bool Offline;
            public bool Help;
            public bool TlsInsecure;
            public string FromNick;
            public string JobIn;
            public string JobOut;

            public static Args Parse(string[] argv)
            {
                Args a = new Args();
                for (int i = 0; i < argv.Length; i++)
                {
                    string t = argv[i];
                    if (t == "--help" || t == "-h")
                        a.Help = true;
                    else if (t == "--selftest")
                        a.Selftest = true;
                    else if (t == "--offline")
                        a.Offline = true;
                    else if (t == "--once")
                        a.Once = true;
                    else if (t == "--allow-meta")
                        a.AllowMeta = true;
                    else if (t == "--tls-insecure")
                        a.TlsInsecure = true;
                    else if (t == "--nick")
                        a.Nick = Need(argv, ref i, t);
                    else if (t == "--channel")
                        a.Channel = Need(argv, ref i, t);
                    else if (t == "--home")
                        a.Home = Need(argv, ref i, t);
                    else if (t == "--allow-path")
                        a.AllowPathRaw = Need(argv, ref i, t);
                    else if (t == "--operators")
                        a.Operators = JobRunner.ParseOperators(Need(argv, ref i, t));
                    else if (t == "--hello")
                        a.Hello = Need(argv, ref i, t);
                    else if (t == "--host")
                        a.Host = Need(argv, ref i, t);
                    else if (t == "--port")
                        a.Port = int.Parse(Need(argv, ref i, t));
                    else if (t == "--realname")
                        a.Realname = Need(argv, ref i, t);
                    else if (t == "--allow-bin")
                        a.AllowBin = Need(argv, ref i, t);
                    else if (t == "--from-nick")
                        a.FromNick = Need(argv, ref i, t);
                    else if (t == "--job-in")
                        a.JobIn = Need(argv, ref i, t);
                    else if (t == "--job-out")
                        a.JobOut = Need(argv, ref i, t);
                    else
                        throw new InvalidOperationException("unknown arg " + t);
                }
                return a;
            }

            private static string Need(string[] argv, ref int i, string flag)
            {
                i++;
                if (i >= argv.Length)
                    throw new InvalidOperationException("missing value for " + flag);
                return argv[i];
            }
        }
    }
}
