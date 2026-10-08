// M7a feasibility spike: headless OpenUtau.Core render host. NOT production code.
//
// usage: blt-spike-renderhost --project FILE.ustx --out DIR --base NAME
//                             [--phonemize-timeout-ms N]
// stdout: exactly one JSON document. stderr: human diagnostics. exit codes:
//   0 ok, 2 usage, 3 project load failure, 4 singer/phonemizer unresolved,
//   5 render/export failure, 6 cancelled, 7 phonemization timed out.
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using OpenUtau.Core;
using OpenUtau.Core.Format;
using OpenUtau.Core.Ustx;

namespace BltSpike {
    class Collector : ICmdSubscriber {
        static string Describe(Exception x) {
            var inner = x is MessageCustomizableException m && m.SubstanceException != null ? m.SubstanceException : x.InnerException;
            return x.GetType().Name + ": " + x.Message + (inner != null ? " <- " + Describe(inner) : "") +
                (x is MessageCustomizableException ? "" : " @ " + (x.StackTrace ?? "").Replace("\r", " ").Replace("\n", " "));
        }
        public readonly List<string> Errors = new List<string>();
        public int Phonemized;
        public void OnNext(UCommand cmd, bool isUndo) {
            if (cmd is ErrorMessageNotification e) {
                lock (Errors) { Errors.Add((e.message ?? "") + " | " + (e.e == null ? "" : Describe(e.e))); }
            } else if (cmd is PhonemizedNotification) {
                Interlocked.Increment(ref Phonemized);
            }
        }
    }

    // OpenUtau.Core posts work to a "main thread" it is told about at Initialize; headless, that is
    // simply this process's main thread, which must pump the queue while it waits.
    class QueueScheduler : TaskScheduler {
        readonly System.Collections.Concurrent.BlockingCollection<Action> queue;
        public QueueScheduler(System.Collections.Concurrent.BlockingCollection<Action> queue) { this.queue = queue; }
        protected override void QueueTask(Task task) { queue.Add(() => TryExecuteTask(task)); }
        protected override bool TryExecuteTaskInline(Task task, bool taskWasPreviouslyQueued) => false;
        protected override IEnumerable<Task> GetScheduledTasks() => Enumerable.Empty<Task>();
    }

    static class Program {
        static readonly System.Collections.Concurrent.BlockingCollection<Action> queue =
            new System.Collections.Concurrent.BlockingCollection<Action>();

        static bool Pump(Func<bool> done, int timeoutMs) {
            var sw = Stopwatch.StartNew();
            while (!done()) {
                if (sw.ElapsedMilliseconds > timeoutMs) return false;
                if (queue.TryTake(out var action, 20)) action();
            }
            return true;
        }

        static readonly Stopwatch clock = Stopwatch.StartNew();
        static readonly Dictionary<string, object> result = new Dictionary<string, object>();
        static readonly Dictionary<string, long> timingsMs = new Dictionary<string, long>();

        static int Finish(int code, string status, string error = null) {
            result["status"] = status;
            result["exit_code"] = code;
            if (error != null) { result["error"] = error; Console.Error.WriteLine("error: " + error); }
            var proc = Process.GetCurrentProcess();
            result["peak_working_set_mb"] = Math.Round(proc.PeakWorkingSet64 / 1048576.0, 1);
            result["peak_private_mb"] = Math.Round(proc.PeakPagedMemorySize64 / 1048576.0, 1);
            result["main_window_handle"] = proc.MainWindowHandle.ToInt64();
            timingsMs["total"] = clock.ElapsedMilliseconds;
            result["timings_ms"] = timingsMs;
            Console.Out.WriteLine(JsonSerializer.Serialize(result, new JsonSerializerOptions { WriteIndented = true }));
            Console.Out.Flush();
            return code;
        }

        static string Arg(string[] a, string name) {
            int i = Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        static int Main(string[] args) {
            string projectPath = Arg(args, "--project"), outDir = Arg(args, "--out"), baseName = Arg(args, "--base");
            int phonemizeTimeout = int.Parse(Arg(args, "--phonemize-timeout-ms") ?? "60000");
            int renderTimeout = int.Parse(Arg(args, "--render-timeout-ms") ?? "300000");
            if (projectPath == null || outDir == null || baseName == null) {
                return Finish(2, "usage", "need --project, --out and --base");
            }
            // the GUI's Main does this first; voicebank text files are often Shift-JIS
            System.Text.Encoding.RegisterProvider(System.Text.CodePagesEncodingProvider.Instance);
            result["host"] = "blt-spike-renderhost (M7a, not production)";
            result["openutau_core_version"] = typeof(DocManager).Assembly.GetName().Version?.ToString();
            result["project"] = Path.GetFileName(projectPath);

            // 1. headless initialisation: no Avalonia, no window
            var collector = new Collector();
            // same order as the GUI's splash window: tools (resamplers), singers, document manager
            OpenUtau.Classic.ToolsManager.Inst.Initialize();
            DocManager.Inst.Initialize(Thread.CurrentThread, new QueueScheduler(queue));
            DocManager.Inst.PostOnUIThread = action => queue.Add(action);
            DocManager.Inst.AddSubscriber(collector);
            result["data_path_is_host_dir"] = !PathManager.Inst.IsInstalled;
            result["singers_path_kind"] = PathManager.Inst.IsInstalled ? "user data (installed.txt present)" : "next to the host";
            result["singers_dir_exists"] = Directory.Exists(PathManager.Inst.SingersPath);
            result["singers_dir_entries"] = Directory.Exists(PathManager.Inst.SingersPath)
                ? Directory.GetDirectories(PathManager.Inst.SingersPath).Select(Path.GetFileName).ToArray() : new string[0];
            timingsMs["init"] = clock.ElapsedMilliseconds;

            // 2. singers
            SingerManager.Inst.SearchAllSingers();
            result["singers_found"] = SingerManager.Inst.Singers.Keys.OrderBy(k => k).ToArray();
            timingsMs["search_singers"] = clock.ElapsedMilliseconds;

            // 3. load the project
            UProject project;
            string text;
            try {
                text = File.ReadAllText(projectPath);
                project = Ustx.Load(projectPath);
            } catch (Exception e) {
                return Finish(3, "load_failed", e.Message);
            }
            timingsMs["load_project"] = clock.ElapsedMilliseconds;

            // 4. resolve singer and phonemizer explicitly: OpenUtau falls back silently otherwise
            var storedPhonemizers = Regex.Matches(text, @"^- (?:singer: .*\n  )?phonemizer: (.+)$", RegexOptions.Multiline)
                .Select(m => m.Groups[1].Value.Trim()).ToList();
            // the stored singer id per track block (OpenUtau replaces an unknown one with a placeholder)
            var section = Regex.Match(text, @"^tracks:\r?\n(.*?)^voice_parts:", RegexOptions.Multiline | RegexOptions.Singleline);
            var storedSingers = Regex.Split(section.Success ? section.Groups[1].Value : "", @"^- ", RegexOptions.Multiline)
                .Skip(1)
                .Select(block => Regex.Match(block, @"^(?:  )?singer: (.+?)\s*$", RegexOptions.Multiline))
                .Select(m => m.Success ? m.Groups[1].Value.Trim() : "(none stored)")
                .ToList();
            var tracks = new List<object>();
            var problems = new List<string>();
            for (int i = 0; i < project.tracks.Count; i++) {
                var t = project.tracks[i];
                bool hasNotes = project.parts.OfType<UVoicePart>().Any(p => p.trackNo == i && p.notes.Count > 0);
                string singerId = storedSingers.Count > i ? storedSingers[i] : t.Singer?.Id;
                bool found = t.Singer != null && t.Singer.Found;
                string phon = t.Phonemizer?.GetType().FullName;
                string stored = i < storedPhonemizers.Count ? storedPhonemizers[i] : null;
                tracks.Add(new Dictionary<string, object> {
                    ["index"] = i, ["name"] = t.TrackName, ["has_notes"] = hasNotes, ["singer"] = singerId,
                    ["singer_found"] = found, ["phonemizer"] = phon, ["phonemizer_stored"] = stored,
                    ["renderer"] = t.RendererSettings?.renderer,
                });
                if (hasNotes && !found) problems.Add($"track {i} '{t.TrackName}': singer '{singerId}' is not installed");
                if (hasNotes && stored != null && stored != phon) problems.Add($"track {i} '{t.TrackName}': phonemizer '{stored}' did not resolve (fell back to '{phon}')");
            }
            result["tracks"] = tracks;
            if (problems.Count > 0) {
                result["problems"] = problems;
                return Finish(4, "unresolved_singer_or_phonemizer", string.Join("; ", problems));
            }

            // 5. let OpenUtau phonemize (asynchronous in its own pipeline)
            DocManager.Inst.ExecuteCmd(new LoadProjectNotification(project));
            int voiceParts = project.parts.OfType<UVoicePart>().Count();
            Pump(() => collector.Phonemized >= voiceParts, phonemizeTimeout);
            result["phonemized_notifications"] = collector.Phonemized;
            timingsMs["phonemize"] = clock.ElapsedMilliseconds;
            if (collector.Phonemized < voiceParts) {
                return Finish(7, "phonemize_timeout", $"{collector.Phonemized} of {voiceParts} parts phonemized");
            }

            // 6. render per track through the public PlaybackManager.RenderToFiles into a staging
            //    directory; that method reports failures as notifications rather than throwing, and
            //    the 0.1.565 export path has no public cancellation (cancel = end the process).
            Directory.CreateDirectory(outDir);
            string staging = Path.Combine(outDir, ".staging-" + Environment.ProcessId);
            Directory.CreateDirectory(staging);
            result["staging"] = Path.GetFileName(staging);
            try {
                string exportBase = Path.Combine(staging, baseName + ".wav");
                var renderTask = PlaybackManager.Inst.RenderToFiles(project, exportBase);
                Pump(() => renderTask.IsCompleted, renderTimeout);
                if (!renderTask.IsCompleted) return Finish(5, "render_timeout", $"no result after {renderTimeout} ms");
                renderTask.GetAwaiter().GetResult();
                Pump(() => false, 200);  // let queued notifications (errors) arrive
                timingsMs["render"] = clock.ElapsedMilliseconds;
                var staged = Directory.GetFiles(staging, "*.wav").OrderBy(f => f).ToList();
                var expected = new List<string>();
                for (int i = 0; i < project.tracks.Count; i++) {
                    bool hasNotes = project.parts.OfType<UVoicePart>().Any(p => p.trackNo == i && p.notes.Count > 0);
                    if (hasNotes && !project.tracks[i].Muted) expected.Add($"{baseName}_{project.tracks[i].TrackName}.wav");
                }
                if (collector.Errors.Count > 0) {
                    result["errors"] = collector.Errors;
                    return Finish(5, "render_reported_errors", string.Join("; ", collector.Errors));
                }
                var missing = expected.Where(e => !staged.Any(f => Path.GetFileName(f) == e)).ToList();
                if (missing.Count > 0) {
                    return Finish(5, "stems_missing", string.Join(", ", missing));
                }
                var stems = new List<object>();
                foreach (var name in expected) {
                    string dest = Path.Combine(outDir, name);
                    if (File.Exists(dest)) File.Delete(dest);
                    File.Move(Path.Combine(staging, name), dest);
                    stems.Add(new Dictionary<string, object> { ["file"] = name, ["bytes"] = new FileInfo(dest).Length });
                }
                result["stems"] = stems;
                timingsMs["write"] = clock.ElapsedMilliseconds;
                return Finish(0, "ok");
            } catch (Exception e) {
                return Finish(5, "render_failed", e.GetType().Name + ": " + e.Message);
            } finally {
                try { Directory.Delete(staging, true); } catch { }
            }
        }
    }
}
