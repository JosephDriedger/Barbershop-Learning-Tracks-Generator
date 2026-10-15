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
using OpenUtau.Api;
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
            "--g2p-check", "--inventory", "--lookup-words", "--allow-unknown-words", "--phonemize-only",
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

        static string Sha256Hex(byte[] bytes) {
            using var sha = System.Security.Cryptography.SHA256.Create();
            return Convert.ToHexString(sha.ComputeHash(bytes)).ToLowerInvariant();
        }

        static List<Dictionary<string, object>> ZipMembers(byte[] zip) {
            var members = new List<Dictionary<string, object>>();
            using var archive = new System.IO.Compression.ZipArchive(new MemoryStream(zip), System.IO.Compression.ZipArchiveMode.Read);
            foreach (var entry in archive.Entries.OrderBy(e => e.FullName, StringComparer.Ordinal)) {
                using var stream = entry.Open();
                using var copy = new MemoryStream();
                stream.CopyTo(copy);
                members.Add(new Dictionary<string, object> {
                    ["name"] = entry.FullName, ["size"] = copy.Length, ["sha256"] = Sha256Hex(copy.ToArray()),
                });
            }
            return members;
        }

        /// <summary>Everything embedded in an assembly: each entry of its .resources sets and each other manifest resource.</summary>
        static List<Dictionary<string, object>> EmbeddedResources(Assembly assembly) {
            var list = new List<Dictionary<string, object>>();
            string owner = assembly.GetName().Name;
            foreach (var name in assembly.GetManifestResourceNames().OrderBy(n => n, StringComparer.Ordinal)) {
                using var stream = assembly.GetManifestResourceStream(name);
                if (name.EndsWith(".resources", StringComparison.Ordinal)) {
                    using var reader = new System.Resources.ResourceReader(stream);
                    var entries = new List<System.Collections.DictionaryEntry>();
                    foreach (System.Collections.DictionaryEntry entry in reader) entries.Add(entry);
                    foreach (var entry in entries.OrderBy(e => (string)e.Key, StringComparer.Ordinal)) {
                        byte[] bytes = entry.Value as byte[] ?? (entry.Value is string text ? System.Text.Encoding.UTF8.GetBytes(text) : null);
                        var item = new Dictionary<string, object> {
                            ["assembly"] = owner, ["set"] = name, ["name"] = (string)entry.Key,
                            ["size"] = bytes?.Length ?? 0,
                            ["sha256"] = bytes != null ? Sha256Hex(bytes) : "(" + entry.Value?.GetType().Name + ")",
                        };
                        if (bytes != null && bytes.Length > 4 && bytes[0] == (byte)'P' && bytes[1] == (byte)'K') item["zip_members"] = ZipMembers(bytes);
                        list.Add(item);
                    }
                } else {
                    using var copy = new MemoryStream();
                    stream.CopyTo(copy);
                    list.Add(new Dictionary<string, object> {
                        ["assembly"] = owner, ["set"] = "(manifest resource)", ["name"] = name,
                        ["size"] = copy.Length, ["sha256"] = Sha256Hex(copy.ToArray()),
                    });
                }
            }
            return list;
        }

        static IEnumerable<Type> LoadableTypes(Assembly assembly) {
            try { return assembly.GetTypes(); } catch (ReflectionTypeLoadException e) { return e.Types.Where(t => t != null); }
        }

        // What this host can phonemize with and what data it carries, read from the assemblies themselves (nothing of
        // OpenUtau runs). packaging/verify_host_inventory.py compares it with compliance/host-inventory.json, an
        // allow-list: a phonemizer or an embedded resource that is not listed there fails the package build, so a
        // removed engine or dictionary cannot come back unnoticed.
        static int Inventory() {
            try {
                var core = typeof(DocManager).Assembly;
                var builtin = typeof(OpenUtau.Plugin.Builtin.ArpasingPhonemizer).Assembly;
                var baseType = typeof(OpenUtau.Api.Phonemizer);
                var phonemizers = new List<string>();
                foreach (var assembly in new[] { core, builtin }) {
                    foreach (var type in LoadableTypes(assembly)) {
                        if (type.IsClass && !type.IsAbstract && baseType.IsAssignableFrom(type)) phonemizers.Add(type.FullName);
                    }
                }
                phonemizers.Sort(StringComparer.Ordinal);
                // every type of the two assemblies: the checker hashes the list and refuses names it has been told must not return
                var types = new List<string>();
                foreach (var assembly in new[] { core, builtin }) {
                    foreach (var type in LoadableTypes(assembly)) types.Add(type.FullName);
                }
                types.Sort(StringComparer.Ordinal);
                var resources = EmbeddedResources(core);
                resources.AddRange(EmbeddedResources(builtin));
                var english = resources.FirstOrDefault(r => (string)r["name"] == "g2p-arpabet");
                var members = english != null && english.TryGetValue("zip_members", out var m) ? (List<Dictionary<string, object>>)m : null;
                bool hasModel = members != null && members.Any(x => (string)x["name"] == "g2p.onnx");
                result["phonemizers"] = phonemizers;
                result["types"] = types;
                result["resources"] = resources;
                result["g2p_model"] = hasModel ? "included" : "excluded";
                result["openutau_commit"] = Metadata("OpenUtauCommit");
                return Finish(0, "ok");
            } catch (Exception e) {
                return Finish(Exit.Environment, "inventory_failed", e.GetType().Name + ": " + e.Message);
            }
        }

        // Which of the given words (separated by |) the English dictionary has, and their phonemes. Needs no project and no
        // singer; it asks the same ArpabetG2p (CMUdict) the Arpasing, English VCCV and X-SAMPA phonemizers use. A voicebank's own
        // dictionary file is not consulted here (the render check below does consult it, because the phonemizer itself reports).
        static int LookupWords(string list) {
            try {
                var g2p = new OpenUtau.Core.G2p.ArpabetG2p();
                var found = new Dictionary<string, object>();
                foreach (var word in list.Split('|', StringSplitOptions.RemoveEmptyEntries)) {
                    var phonemes = g2p.Query(word.ToLowerInvariant());
                    found[word] = phonemes == null ? null : string.Join(" ", phonemes);
                }
                result["lookup"] = found;
                result["g2p_model_loaded"] = LoadedOnnxRuntime() != null;
                return Finish(0, "ok");
            } catch (Exception e) {
                return Finish(Exit.Environment, "lookup_failed", e.GetType().Name + ": " + e.Message);
            }
        }

        /// <summary>
        /// The words the tracks' dictionary phonemizers could not look up (see host/patch_openutau.py): after phonemizing, each
        /// phonemizer instance lists them. Upstream turns such a word into a voicebank alias or into "word not found", which renders
        /// as silence. A note with a phonetic hint ("word[w er d]") or a forced alias is not a missing word.
        /// </summary>
        static List<Dictionary<string, object>> UnknownWords(UProject project) {
            var found = new List<Dictionary<string, object>>();
            foreach (var track in project.tracks) {
                if (!(track.Phonemizer is IMissingWordReporter reporter)) continue;
                List<MissingWord> snapshot;
                lock (reporter.MissingWords) { snapshot = reporter.MissingWords.ToList(); }
                foreach (var missing in snapshot.OrderBy(m => m.position).ThenBy(m => m.word, StringComparer.Ordinal)) {
                    found.Add(new Dictionary<string, object> {
                        ["track"] = track.TrackName, ["position"] = missing.position, ["lyric"] = missing.lyric, ["word"] = missing.word,
                    });
                }
            }
            return found;
        }

        /// <summary>
        /// Symbols of a phonetic hint that the track's phonemizer does not know (see host/patch_openutau.py). Arpasing silently
        /// drops such a symbol and the syllable phonemizers use it as written; either way the note would not be sung as the
        /// person wrote it. A hint is only accepted when every symbol is one the phonemizer knows.
        /// </summary>
        static List<Dictionary<string, object>> HintProblems(UProject project) {
            var found = new List<Dictionary<string, object>>();
            foreach (var track in project.tracks) {
                if (!(track.Phonemizer is IMissingWordReporter reporter)) continue;
                List<HintProblem> snapshot;
                lock (reporter.HintProblems) { snapshot = reporter.HintProblems.ToList(); }
                foreach (var problem in snapshot.OrderBy(h => h.position).ThenBy(h => h.symbol, StringComparer.Ordinal)) {
                    found.Add(new Dictionary<string, object> {
                        ["track"] = track.TrackName, ["position"] = problem.position, ["lyric"] = problem.lyric,
                        ["symbol"] = problem.symbol, ["reason"] = "symbol_unknown",
                    });
                }
            }
            return found;
        }

        /// <summary>
        /// What the phonemizers made of every note that carries a phonetic hint: the aliases they chose for it (and for the
        /// notes that extend it). It is the effective pronunciation, recorded in the package; a hinted note that produced no
        /// sound at all is a problem of its own (the hint was accepted but nothing would be sung).
        /// </summary>
        static List<Dictionary<string, object>> HintedNotes(UProject project, List<Dictionary<string, object>> problems) {
            var found = new List<Dictionary<string, object>>();
            var pattern = new System.Text.RegularExpressions.Regex(@"\[(.*)\]");
            foreach (var part in project.parts.OfType<UVoicePart>()) {
                var track = project.tracks[part.trackNo];
                foreach (var note in part.notes) {
                    var match = pattern.Match(note.lyric ?? "");
                    if (!match.Success) continue;
                    var aliases = part.phonemes
                        .Where(p => p.Parent != null && (p.Parent.Extends ?? p.Parent) == note)
                        .OrderBy(p => p.position)
                        .Select(p => p.phoneme ?? p.rawPhoneme)
                        .ToList();
                    int position = part.position + note.position;
                    found.Add(new Dictionary<string, object> {
                        ["track"] = track.TrackName, ["position"] = position,
                        ["lyric"] = pattern.Replace(note.lyric, "").Trim(), ["hint"] = match.Groups[1].Value.Trim(),
                        ["phonemes"] = aliases,
                    });
                    // OpenUtau's phonemizer runner answers a phonemizer that threw an exception with the alias "error"
                    bool failed = aliases.Contains("error");
                    if (aliases.Count == 0 || failed) {
                        problems.Add(new Dictionary<string, object> {
                            ["track"] = track.TrackName, ["position"] = position, ["lyric"] = pattern.Replace(note.lyric, "").Trim(),
                            ["symbol"] = null, ["reason"] = failed ? "engine_error" : "no_sound",
                        });
                    }
                }
            }
            return found;
        }

        static string LoadedOnnxRuntime() {
            foreach (ProcessModule m in Process.GetCurrentProcess().Modules) {
                if (m.ModuleName.StartsWith("onnxruntime", StringComparison.OrdinalIgnoreCase)) return m.FileName;
            }
            return null;
        }

        // The English phonemizers look a word up in the CMU dictionary and, when it is not there, ask a neural
        // model to spell it out. That model runs on the ONNX Runtime, a native library that must sit beside the
        // host (otherwise it silently depends on whatever Windows happens to provide). This check makes both
        // visible: it phonemizes a word that is not in the dictionary and reports which onnxruntime was loaded.
        // In a host built without the model (the default of host/build.ps1) it checks the opposite: dictionary
        // words still work, a word that is not in the dictionary gets no guess, and no onnxruntime is loaded.
        static int G2pCheck() {
            try {
                var g2p = new OpenUtau.Core.G2p.ArpabetG2p();
                var known = g2p.Query("hello");
                var phonemes = g2p.Query("blorptastic");
                string loaded = LoadedOnnxRuntime();
                string here = Path.TrimEndingDirectorySeparator(AppContext.BaseDirectory);
                var english = EmbeddedResources(typeof(DocManager).Assembly).First(r => (string)r["name"] == "g2p-arpabet");
                bool hasModel = ((List<Dictionary<string, object>>)english["zip_members"]).Any(x => (string)x["name"] == "g2p.onnx");
                result["g2p_model"] = hasModel ? "included" : "excluded";
                result["g2p_known_word"] = "hello";
                result["g2p_known_phonemes"] = known == null ? "" : string.Join(" ", known);
                result["g2p_word"] = "blorptastic";
                result["g2p_phonemes"] = phonemes == null ? "" : string.Join(" ", phonemes);
                result["onnxruntime"] = loaded;
                result["onnxruntime_beside_host"] = loaded != null &&
                    string.Equals(Path.GetDirectoryName(loaded), here, StringComparison.OrdinalIgnoreCase);
                if (known == null || known.Length == 0) {
                    return Finish(Exit.Environment, "g2p_failed", "a word of the dictionary got no phonemes");
                }
                if (hasModel) {
                    bool ok = phonemes != null && phonemes.Length > 0 && (bool)result["onnxruntime_beside_host"];
                    return Finish(ok ? 0 : Exit.Environment, ok ? "ok" : "g2p_failed",
                        ok ? null : "the neural English g2p did not run with an onnxruntime.dll beside the host");
                }
                bool excludedOk = (phonemes == null || phonemes.Length == 0) && loaded == null;
                return Finish(excludedOk ? 0 : Exit.Environment, excludedOk ? "ok" : "g2p_failed",
                    excludedOk ? null : "this host is built without the g2p model, but a word outside the dictionary got phonemes or onnxruntime was loaded");
            } catch (Exception e) {
                return Finish(Exit.Environment, "g2p_failed", e.GetType().Name + ": " + e.Message);
            }
        }

        /// <summary>Why the project needs the tension effect this build leaves out, or null if it does not.</summary>
        static string TensionRequested(UProject project) {
            if (project.expressions.TryGetValue(Ustx.TENC, out var descriptor) && descriptor.defaultValue != 0) {
                return $"the project sets the default of the tension curve to {descriptor.defaultValue}, but this build has no tension effect";
            }
            foreach (var part in project.parts.OfType<UVoicePart>()) {
                foreach (var curve in part.curves) {
                    if (curve.abbr == Ustx.TENC && !curve.IsEmpty) {
                        return $"part '{part.name}' has a tension curve, but this build has no tension effect";
                    }
                }
            }
            return null;
        }

        /// <summary>
        /// Phonemes the voicebank has no sound for. OpenUtau renders them as silence without any error. The usual cause
        /// is a word the pronunciation dictionary does not have (the English phonemizers then pass the lyric itself on,
        /// or the alias "word not found"); the other is an alias the voicebank lacks. BLT's stem check finds the silence afterwards;
        /// this says why.
        /// </summary>
        static List<Dictionary<string, object>> UnsungPhonemes(UProject project) {
            var found = new List<Dictionary<string, object>>();
            foreach (var part in project.parts.OfType<UVoicePart>()) {
                var track = project.tracks[part.trackNo];
                var singer = track.Singer;
                if (singer == null || !singer.Found || !singer.Loaded) continue;
                foreach (var phoneme in part.phonemes) {
                    string alias = phoneme.phoneme ?? phoneme.rawPhoneme;
                    if (string.IsNullOrEmpty(alias) || singer.TryGetOto(alias, out _)) continue;
                    found.Add(new Dictionary<string, object> {
                        ["track"] = track.TrackName,
                        ["lyric"] = phoneme.Parent?.lyric,
                        ["alias"] = alias,
                        // a phonemizer that cannot phonemize a word passes the lyric itself on (or "word not found")
                        // "error" is what OpenUtau's phonemizer runner answers a phonemizer that threw an exception with: not a recording
                        ["reason"] = alias == "error" ? "engine_error"
                            : alias == "word not found" || string.Equals(alias, phoneme.Parent?.lyric, StringComparison.OrdinalIgnoreCase)
                            ? "lyric_has_no_sound" : "alias_not_in_voicebank",
                    });
                }
            }
            return found;
        }

        /// <summary>Deletes the phrases WORLDLINE-R rendered in earlier runs (wdl-*.wav in the cache); returns how many.</summary>
        static int DiscardRenderedPhrases() {
            int removed = 0;
            try {
                string cache = PathManager.Inst.CachePath;
                if (!Directory.Exists(cache)) return 0;
                foreach (var file in Directory.EnumerateFiles(cache, "wdl-*.wav")) {
                    File.Delete(file);
                    removed++;
                }
            } catch (Exception e) when (e is IOException || e is UnauthorizedAccessException) {
                Events.Emit("warning", new Dictionary<string, object> {
                    ["message"] = "could not remove cached phrases; a reused phrase can differ from a fresh render by one bit: " + e.Message,
                });
            }
            return removed;
        }

        static int Run(string[] args) {
            for (int i = 0; i < args.Length; i++) {
                if (args[i].StartsWith("--") && !known.Contains(args[i])) return Finish(Exit.Usage, "usage", "unknown option " + args[i]);
            }
            if (Array.IndexOf(args, "--g2p-check") >= 0) return G2pCheck();
            if (Array.IndexOf(args, "--inventory") >= 0) return Inventory();
            if (Array.IndexOf(args, "--lookup-words") >= 0) return LookupWords(Arg(args, "--lookup-words") ?? "");
            string projectPath = Arg(args, "--project"), outDir = Arg(args, "--out"), baseName = Arg(args, "--base");
            string singersDir = Arg(args, "--singers-dir");
            // --phonemize-only runs everything up to and including the pronunciation checks and then stops: no stems, no --out
            bool phonemizeOnly = Array.IndexOf(args, "--phonemize-only") >= 0;
            if (projectPath == null || (!phonemizeOnly && (outDir == null || baseName == null))) {
                return Finish(Exit.Usage, "usage", "need --project, --out and --base (or --project and --phonemize-only)");
            }
            baseName ??= "check";
            if (!int.TryParse(Arg(args, "--phonemize-timeout-ms") ?? "60000", out int phonemizeTimeout) ||
                !int.TryParse(Arg(args, "--render-timeout-ms") ?? "300000", out int renderTimeout)) {
                return Finish(Exit.Usage, "usage", "timeouts must be integers (milliseconds)");
            }
            if (!File.Exists(projectPath)) return Finish(Exit.ProjectLoad, "load_failed", "project file not found: " + projectPath);
            if (outDir != null && !Directory.Exists(outDir)) return Finish(Exit.Usage, "usage", "--out directory does not exist: " + outDir);
            if (outDir != null && Directory.EnumerateFileSystemEntries(outDir).Any()) return Finish(Exit.Usage, "usage", "--out directory is not empty");

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
                // The syllable phonemizers (English VCCV, X-SAMPA, ...) read their dictionary on a background task and answer
                // "" for every note until it is loaded, expecting the GUI to phonemize again afterwards. This host phonemizes
                // once, so without this the notes of those phonemizers were rendered EMPTY. Testing = true makes the load
                // synchronous (it is what OpenUtau's own phonemizer tests do) and silences the GUI progress notifications.
                if (t.Phonemizer != null) t.Phonemizer.Testing = true;
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
            // BLT's worldline.dll has no tension effect (docs/worldline-provenance.md): a project that asks for one is
            // refused instead of being rendered silently without it. BLT's own projects never ask for it.
            string tensionProblem = TensionRequested(project);
            if (tensionProblem != null) {
                result["problems"] = new List<string> { tensionProblem };
                return Finish(Exit.ProjectLoad, "unsupported_tension", tensionProblem);
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
            // a word the dictionary lacks must stop the run BEFORE anything is rendered: never guess, never drop it silently
            var unknown = UnknownWords(project);
            result["unknown_word_count"] = unknown.Count;
            if (unknown.Count > 0 && Array.IndexOf(args, "--allow-unknown-words") < 0) {
                result["unknown_words"] = unknown.Take(200).ToList();
                var shown = unknown.Take(6).Select(u => $"{u["track"]}: '{u["word"]}'");
                return Finish(Exit.PronunciationUnknown, "pronunciation_unknown",
                    $"the pronunciation dictionary has no entry for {unknown.Count} word(s): {string.Join("; ", shown)}{(unknown.Count > 6 ? "; ..." : "")}");
            }
            // a phonetic hint (a person's pronunciation) is accepted only if the phonemizer knows every symbol of it and made
            // some sound from it; this also stops the run BEFORE anything is rendered
            var hintProblems = HintProblems(project);
            var hinted = HintedNotes(project, hintProblems);
            result["pronunciations"] = hinted;
            result["hint_problem_count"] = hintProblems.Count;
            if (hintProblems.Count > 0) {
                result["invalid_hints"] = hintProblems.Take(200).ToList();
                var shown = hintProblems.Take(6).Select(h => h["symbol"] == null
                    ? ((string)h["reason"] == "engine_error"
                        ? $"{h["track"]}: the phonemizer failed on '{h["lyric"]}' with the given symbols"
                        : $"{h["track"]}: '{h["lyric"]}' makes no sound")
                    : $"{h["track"]}: '{h["lyric"]}' has the unknown symbol '{h["symbol"]}'");
                return Finish(Exit.PronunciationInvalid, "pronunciation_invalid",
                    $"{hintProblems.Count} problem(s) in the given pronunciations: {string.Join("; ", shown)}{(hintProblems.Count > 6 ? "; ..." : "")}");
            }
            var unsung = UnsungPhonemes(project);
            result["unsung_phoneme_count"] = unsung.Count;
            if (unsung.Count > 0) {
                result["unsung_phonemes"] = unsung.Take(60).ToList();
                Events.Emit("warning", new Dictionary<string, object> {
                    ["message"] = $"{unsung.Count} phoneme(s) have no sound in the voicebank (for example '{unsung[0]["alias"]}' for '{unsung[0]["lyric"]}')",
                });
            }

            if (phonemizeOnly) {
                result["stems"] = new List<object>();
                return Finish(Exit.Ok, "ok");
            }

            // 5b. never reuse a phrase rendered earlier. OpenUtau keeps every rendered phrase in its cache as a 16-bit file and
            //     reuses it; a reused phrase differs from a fresh render by one least-significant bit, so the same score gave
            //     different bytes on its first run and on every later one. BLT promises reproducible tracks.
            result["rendered_phrases_discarded"] = DiscardRenderedPhrases();

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
