// blt-render-host: renders every voiced track of one OpenUtau project to its own WAV, headlessly.
//
//   blt-render-host --project FILE.ustx --out DIR --base NAME
//                   [--singers-dir DIR] [--phonemize-timeout-ms N] [--render-timeout-ms N]
//
// DIR must exist and be empty: the caller owns it (the Python backend passes an isolated staging
// directory), so the host never moves or deletes anything and never publishes. stdout is one JSON
// object per line, the last being {"event":"result",...}; exit codes are the Exit class.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Diagnostics;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading;
using OpenUtau.Core;
using OpenUtau.Core.Format;
using OpenUtau.Core.Ustx;
using OpenUtau.Core.Util;
using YamlDotNet.Serialization;

namespace Blt.RenderHost {
    static class Program {
        static readonly BlockingCollection<Action> queue = new BlockingCollection<Action>();
        static readonly Stopwatch clock = Stopwatch.StartNew();
        static readonly Dictionary<string, object> result = new Dictionary<string, object>();
        static readonly Dictionary<string, long> timingsMs = new Dictionary<string, long>();
        static readonly HashSet<string> known = new HashSet<string> {
            "--project", "--out", "--base", "--singers-dir", "--phonemize-timeout-ms", "--render-timeout-ms",
        };

        static bool Pump(Func<bool> done, int timeoutMs) {
            var sw = Stopwatch.StartNew();
            while (!done()) {
                if (sw.ElapsedMilliseconds > timeoutMs) return false;
                if (queue.TryTake(out var action, 20)) action();
            }
            return true;
        }

        static int Finish(int code, string status, string error = null) {
            result["status"] = status;
            result["exit_code"] = code;
            if (error != null) { result["error"] = error; Console.Error.WriteLine("error: " + error); }
            timingsMs["total"] = clock.ElapsedMilliseconds;
            result["timings_ms"] = timingsMs;
            result["peak_working_set_mb"] = Math.Round(Process.GetCurrentProcess().PeakWorkingSet64 / 1048576.0, 1);
            Events.Emit("result", result);
            return code;
        }

        static void Phase(string name) {
            timingsMs[name] = clock.ElapsedMilliseconds;
            Events.Emit("phase", new Dictionary<string, object> { ["name"] = name, ["elapsed_ms"] = clock.ElapsedMilliseconds });
        }

        static string Arg(string[] a, string name) {
            int i = Array.IndexOf(a, name);
            return i >= 0 && i + 1 < a.Length ? a[i + 1] : null;
        }

        static string Metadata(string key) =>
            typeof(Program).Assembly.GetCustomAttributes<AssemblyMetadataAttribute>().FirstOrDefault(m => m.Key == key)?.Value;

        static int Main(string[] args) {
            int code;
            try {
                code = Run(args);
            } catch (Exception e) {
                code = Finish(Exit.Internal, "internal_error", e.GetType().Name + ": " + e.Message);
            }
            // background render threads must not keep a finished (or timed-out) host alive
            Environment.Exit(code);
            return code;
        }

        static int Run(string[] args) {
            for (int i = 0; i < args.Length; i++) {
                if (args[i].StartsWith("--") && !known.Contains(args[i])) return Finish(Exit.Usage, "usage", "unknown option " + args[i]);
            }
            string projectPath = Arg(args, "--project"), outDir = Arg(args, "--out"), baseName = Arg(args, "--base");
            string singersDir = Arg(args, "--singers-dir");
            if (projectPath == null || outDir == null || baseName == null) {
                return Finish(Exit.Usage, "usage", "need --project, --out and --base");
            }
            if (!int.TryParse(Arg(args, "--phonemize-timeout-ms") ?? "60000", out int phonemizeTimeout) ||
                !int.TryParse(Arg(args, "--render-timeout-ms") ?? "300000", out int renderTimeout)) {
                return Finish(Exit.Usage, "usage", "timeouts must be integers (milliseconds)");
            }
            if (!File.Exists(projectPath)) return Finish(Exit.ProjectLoad, "load_failed", "project file not found: " + projectPath);
            if (!Directory.Exists(outDir)) return Finish(Exit.Usage, "usage", "--out directory does not exist: " + outDir);
            if (Directory.EnumerateFileSystemEntries(outDir).Any()) return Finish(Exit.Usage, "usage", "--out directory is not empty");

            result["host"] = "blt-render-host";
            result["host_version"] = typeof(Program).Assembly.GetName().Version?.ToString();
            result["openutau_core_version"] = typeof(DocManager).Assembly.GetName().Version?.ToString();
            result["openutau_commit"] = Metadata("OpenUtauCommit");
            Events.Emit("start", new Dictionary<string, object> { ["project"] = Path.GetFileName(projectPath) });

            // the GUI's Main registers this first; voicebank text files are often Shift-JIS
            System.Text.Encoding.RegisterProvider(System.Text.CodePagesEncodingProvider.Instance);

            // 1. environment: the native resampler must sit beside the host
            string native = Path.Combine(AppContext.BaseDirectory, "worldline.dll");
            if (OperatingSystem.IsWindows() && !File.Exists(native)) {
                return Finish(Exit.Environment, "native_library_missing", "worldline.dll is not beside the host: " + native);
            }
            result["data_path"] = PathManager.Inst.DataPath;
            result["installed_mode"] = PathManager.Inst.IsInstalled;
            if (singersDir != null) {
                if (!Directory.Exists(singersDir)) return Finish(Exit.Environment, "singers_dir_missing", singersDir);
                // OpenUtau's own supported preference for a second singers directory
                Preferences.Default.AdditionalSingerPath = Path.GetFullPath(singersDir);
            }

            // 2. headless initialisation (GUI order): tools, singers, document manager
            var collector = new Collector();
            try {
                OpenUtau.Classic.ToolsManager.Inst.Initialize();
                DocManager.Inst.Initialize(Thread.CurrentThread, new QueueScheduler(queue));
                DocManager.Inst.PostOnUIThread = action => queue.Add(action);
                DocManager.Inst.AddSubscriber(collector);
                SingerManager.Inst.SearchAllSingers();
            } catch (Exception e) {
                return Finish(Exit.Environment, "initialisation_failed", e.GetType().Name + ": " + e.Message);
            }
            result["singers_found"] = SingerManager.Inst.Singers.Keys.OrderBy(k => k).ToArray();
            Phase("init");

            // 3. load the project
            UProject project;
            Dictionary<object, object> raw;
            try {
                raw = new DeserializerBuilder().Build().Deserialize<Dictionary<object, object>>(File.ReadAllText(projectPath));
                project = Ustx.Load(projectPath);
            } catch (Exception e) {
                return Finish(Exit.ProjectLoad, "load_failed", e.GetType().Name + ": " + e.Message);
            }
            Phase("load_project");

            // 4. resolve singer, phonemizer and renderer explicitly: OpenUtau replaces unknown ones silently
            var storedTracks = (raw.TryGetValue("tracks", out var tr) ? tr as List<object> : null) ?? new List<object>();
            var tracks = new List<object>();
            var problems = new List<string>();
            var expected = new List<string>();
            for (int i = 0; i < project.tracks.Count; i++) {
                var t = project.tracks[i];
                var stored = i < storedTracks.Count ? storedTracks[i] as Dictionary<object, object> : null;
                string Stored(string key) => stored != null && stored.TryGetValue(key, out var v) ? v?.ToString() : null;
                string storedRenderer = null;
                if (stored != null && stored.TryGetValue("renderer_settings", out var rs) && rs is Dictionary<object, object> rd &&
                    rd.TryGetValue("renderer", out var rv)) storedRenderer = rv?.ToString();
                bool hasNotes = project.parts.OfType<UVoicePart>().Any(p => p.trackNo == i && p.notes.Count > 0);
                string singerId = Stored("singer");
                string phonemizer = t.Phonemizer?.GetType().FullName;
                string renderer = t.RendererSettings?.renderer;
                bool found = t.Singer != null && t.Singer.Found;
                tracks.Add(new Dictionary<string, object> {
                    ["index"] = i, ["name"] = t.TrackName, ["has_notes"] = hasNotes, ["singer"] = singerId,
                    ["singer_found"] = found, ["phonemizer"] = phonemizer, ["phonemizer_stored"] = Stored("phonemizer"),
                    ["renderer"] = renderer, ["renderer_stored"] = storedRenderer,
                });
                if (!hasNotes) continue;
                if (string.IsNullOrEmpty(singerId)) problems.Add($"track {i} '{t.TrackName}': no singer stored");
                else if (!found) problems.Add($"track {i} '{t.TrackName}': singer '{singerId}' is not installed");
                if (string.IsNullOrEmpty(Stored("phonemizer"))) problems.Add($"track {i} '{t.TrackName}': no phonemizer stored");
                else if (Stored("phonemizer") != phonemizer) problems.Add($"track {i} '{t.TrackName}': phonemizer '{Stored("phonemizer")}' did not resolve (OpenUtau would use '{phonemizer}')");
                if (string.IsNullOrEmpty(storedRenderer)) problems.Add($"track {i} '{t.TrackName}': no renderer stored");
                else if (storedRenderer != renderer) problems.Add($"track {i} '{t.TrackName}': renderer '{storedRenderer}' was replaced by '{renderer}'");
                if (!t.Muted) expected.Add($"{baseName}_{t.TrackName}.wav");
            }
            result["tracks"] = tracks;
            result["expected_stems"] = expected;
            if (problems.Count > 0) {
                result["problems"] = problems;
                return Finish(Exit.Unresolved, "unresolved_singer_phonemizer_or_renderer", string.Join("; ", problems));
            }
            Phase("validate");

            // 5. let OpenUtau phonemize (asynchronous in its own pipeline)
            DocManager.Inst.ExecuteCmd(new LoadProjectNotification(project));
            int voiceParts = project.parts.OfType<UVoicePart>().Count();
            Pump(() => collector.Phonemized >= voiceParts, phonemizeTimeout);
            if (collector.Phonemized < voiceParts) {
                return Finish(Exit.PhonemizeTimeout, "phonemize_timeout", $"{collector.Phonemized} of {voiceParts} parts phonemized");
            }
            Phase("phonemize");

            // 6. render through the public PlaybackManager.RenderToFiles straight into --out. It reports
            //    failures as notifications instead of throwing, so the collector decides success; there is
            //    no public cancellation, so cancelling means ending this process (the caller does that).
            string exportBase = Path.Combine(outDir, baseName + ".wav");
            try {
                var renderTask = PlaybackManager.Inst.RenderToFiles(project, exportBase);
                Pump(() => renderTask.IsCompleted, renderTimeout);
                if (!renderTask.IsCompleted) return Finish(Exit.RenderTimeout, "render_timeout", $"no result after {renderTimeout} ms");
                renderTask.GetAwaiter().GetResult();
                Pump(() => false, 200);  // let queued error notifications arrive
            } catch (Exception e) {
                return Finish(Exit.Render, "render_failed", e.GetType().Name + ": " + e.Message);
            }
            Phase("render");
            if (collector.Errors.Count > 0) {
                result["errors"] = collector.Errors;
                return Finish(Exit.Render, "render_reported_errors", string.Join("; ", collector.Errors));
            }
            var present = Directory.GetFiles(outDir, "*.wav").Select(Path.GetFileName).ToHashSet();
            var missing = expected.Where(e => !present.Contains(e)).ToList();
            if (missing.Count > 0) return Finish(Exit.Render, "stems_missing", string.Join(", ", missing));
            result["stems"] = expected.Select(n => new Dictionary<string, object> { ["file"] = n, ["bytes"] = new FileInfo(Path.Combine(outDir, n)).Length }).ToList();
            return Finish(Exit.Ok, "ok");
        }
    }
}
