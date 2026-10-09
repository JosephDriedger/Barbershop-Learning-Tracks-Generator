// Small pieces the host needs around OpenUtau.Core: the exit-code contract, the event stream, the
// notification collector and the main-thread queue.
using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using OpenUtau.Core;
using OpenUtau.Core.Ustx;

namespace Blt.RenderHost {
    /// <summary>Stable process exit codes. The Python backend maps these to typed errors.</summary>
    static class Exit {
        public const int Ok = 0;
        public const int Usage = 2;              // bad or missing arguments, output dir not usable
        public const int ProjectLoad = 3;        // the .ustx could not be read or parsed
        public const int Unresolved = 4;         // singer, phonemizer or renderer not resolvable
        public const int Render = 5;             // OpenUtau reported render/export errors, or stems missing
        public const int Cancelled = 6;          // reserved: cancellation is by process-tree termination
        public const int PhonemizeTimeout = 7;
        public const int Environment = 8;        // native library, singers directory, initialisation
        public const int RenderTimeout = 9;
        public const int Internal = 10;          // unexpected exception in the host itself
    }

    /// <summary>
    /// stdout carries exactly one JSON object per line ("event": progress/phase/warning/result);
    /// the last line is always the result. stderr is for humans only.
    /// </summary>
    static class Events {
        static readonly object gate = new object();
        static readonly JsonSerializerOptions options = new JsonSerializerOptions { WriteIndented = false };

        public static void Emit(string name, IDictionary<string, object> fields = null) {
            var line = new Dictionary<string, object> { ["event"] = name };
            if (fields != null) foreach (var kv in fields) line[kv.Key] = kv.Value;
            lock (gate) {
                Console.Out.WriteLine(JsonSerializer.Serialize(line, options));
                Console.Out.Flush();
            }
        }
    }

    /// <summary>Subscribes to DocManager notifications: render failures arrive here, not as exceptions.</summary>
    class Collector : ICmdSubscriber {
        public readonly List<string> Errors = new List<string>();
        public int Phonemized;

        static string Describe(Exception x) {
            var inner = x is MessageCustomizableException m && m.SubstanceException != null
                ? m.SubstanceException : x.InnerException;
            return x.GetType().Name + ": " + x.Message + (inner != null ? " <- " + Describe(inner) : "");
        }

        public void OnNext(UCommand cmd, bool isUndo) {
            if (cmd is ErrorMessageNotification e) {
                string text = (e.message ?? "") + (e.e == null ? "" : " | " + Describe(e.e));
                lock (Errors) { Errors.Add(text); }
                Events.Emit("error_notification", new Dictionary<string, object> { ["message"] = text });
            } else if (cmd is PhonemizedNotification) {
                Interlocked.Increment(ref Phonemized);
            } else if (cmd is ProgressBarNotification p && !string.IsNullOrEmpty(p.Info)) {
                Events.Emit("progress", new Dictionary<string, object> { ["info"] = p.Info });
            }
        }
    }

    // OpenUtau.Core posts work to a "main thread" it is told about at Initialize; headless, that is
    // this process's main thread, which must pump the queue while it waits.
    class QueueScheduler : TaskScheduler {
        readonly BlockingCollection<Action> queue;
        public QueueScheduler(BlockingCollection<Action> queue) { this.queue = queue; }
        protected override void QueueTask(Task task) { queue.Add(() => TryExecuteTask(task)); }
        protected override bool TryExecuteTaskInline(Task task, bool taskWasPreviouslyQueued) => false;
        protected override IEnumerable<Task> GetScheduledTasks() => Enumerable.Empty<Task>();
    }
}
