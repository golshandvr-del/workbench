package io.github.golshandvr.aiworkbench.core

import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.io.File
import java.security.MessageDigest
import java.util.zip.ZipEntry
import java.util.zip.ZipInputStream
import java.util.zip.ZipOutputStream

/**
 * The project's file space on the phone (roadmap 4.3.0 / mobile 1.4.0, flowchart F16–F17).
 *
 * Port of desktop `aiwb/v2/files.py`. Files live in `<project>/files/`, next to `state.json`. A pasted delivery is
 * only staged on its handoff; accepting it (F16) writes the files, keeps old content under `backups/<handoff>/`
 * and records `files_integrated` (F17). [safePath] is checked against
 * `packages/contracts/fixtures/files/safe-paths.v1.json`.
 */
object Files {
    const val MAX_FILE = 512 * 1024
    const val MAX_TOTAL = 8 * 1024 * 1024
    private val RESERVED = setOf(".git", ".workbench")

    fun dir(store: ProjectStore): File = File(store.root, "files")

    /** The normalised relative path, or "" when it must never be written. */
    fun safePath(path: String?): String {
        val p = path.orEmpty().replace('\\', '/')
        if (p.isEmpty() || p.startsWith("/") || Regex("^[A-Za-z]:").containsMatchIn(p)) return ""
        val parts = p.split("/").filter { it.isNotEmpty() && it != "." }
        if (parts.isEmpty() || parts[0].lowercase(java.util.Locale.ROOT) in RESERVED) return ""
        val device = Regex("^(CON|PRN|AUX|NUL|COM[1-9¹²³]|LPT[1-9¹²³])(?:\\.|$)", RegexOption.IGNORE_CASE)
        if (parts.any { part -> part == ".." || part.endsWith(".") || part.endsWith(" ") ||
                part.any { it.code < 32 || it in "<>:\"|?*" } || device.containsMatchIn(part) }) return ""
        return parts.joinToString("/")
    }

    private fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    /** Refuse links (including dangling links), case aliases, directories and parent-file conflicts. */
    private fun target(root: File, path: String): File {
        if (safePath(path) != path || path.isEmpty()) throw ModelError("unsafe path '$path'")
        if (root.absoluteFile != root.canonicalFile ||
            (!root.exists() && root.parentFile?.list()?.contains(root.name) == true)) throw ModelError("linked file root")
        if (root.exists() && !root.isDirectory) throw ModelError("file root is not a directory")
        var at = root.absoluteFile
        val parts = path.split('/')
        for ((i, part) in parts.withIndex()) {
            val children = at.list()?.toSet().orEmpty()
            val alias = children.firstOrNull { it.equals(part, ignoreCase = true) && it != part }
            if (alias != null) throw ModelError("case alias at $path: $alias")
            at = File(at, part)
            // File.canonicalFile does not resolve dangling symlinks on every JVM.
            // An entry present in its parent but not dereferenceable must also be refused.
            if (at.absoluteFile != at.canonicalFile || (part in children && !at.exists()))
                throw ModelError("linked or inaccessible path '$path'")
            if (at.exists() && (if (i == parts.lastIndex) !at.isFile else !at.isDirectory))
                throw ModelError("file/directory conflict at '$path'")
        }
        return at
    }

    private fun preflight(root: File, staged: List<Obj>) {
        val paths = staged.map { Json.str(it["path"]) }
        val folded = paths.map { it.lowercase(java.util.Locale.ROOT) }
        if (folded.toSet().size != paths.size || folded.any { a -> folded.any { b -> a != b && b.startsWith("$a/") } })
            throw ModelError("case or file/directory collision in delivery")
        for (f in staged) {
            val p = Json.str(f["path"])
            val dest = target(root, p)
            val actual = if (dest.isFile) sha(dest.readBytes()) else ""
            if ("base_sha256" in f && Json.str(f["base_sha256"]) != actual)
                throw ModelError("$p changed since preview; paste the answer again")
        }
    }

    /** Keep complete safe files and explicit diagnostics for every omission; preserve retained preview hashes. */
    fun stage(store: ProjectStore, handoffId: String, text: String): List<String> = store.transaction("stage files") { s ->
        val h = State.require(s, "handoffs", handoffId)
        val allowed = Diagnose.taskPaths(Json.obj(State.coll(s, "tasks")[h["task_id"]]))
        val staged = LinkedHashMap<String, Obj>()
        val problems = ArrayList<Any?>()
        fun problem(code: String, message: String, path: String = "", severity: String = "error") {
            problems.add(Diagnose.Problem(code, severity, message, path).toMap())
        }
        for (raw in Json.list(h["retained_files"])) {
            val f = Json.obj(raw); val p = Json.str(f["path"])
            if (p.isNotEmpty() && safePath(p) == p && Diagnose.inScope(p, allowed) && f["content"] is String)
                staged[p] = LinkedHashMap(f)
        }
        val parsed = Diagnose.parseFiles(text)
        val seen = HashSet<String>()
        for (f in parsed.first) {
            val p = safePath(f.path)
            if (f.action != "write" || !f.complete || !f.fenceBalanced) {
                problem(if (f.action != "write") "unsupported_action" else "truncated",
                    "${f.path}: unsupported operation or incomplete file; resend a complete write", f.path)
                staged.remove(p); continue
            }
            if (p.isEmpty()) { problem("unsafe_path", "unsafe file path '${f.path}'", f.path); continue }
            if (!Diagnose.inScope(p, allowed)) { problem("out_of_scope", "$p is outside this task's allowed paths", p); continue }
            if (!seen.add(p)) problem("duplicate_path", "$p was sent twice — the last complete version is used", p, "warning")
            // A broken replacement must not silently fall back to a retained old version.
            staged.remove(p)
            if (!f.complete || !f.fenceBalanced) {
                problem("truncated", "$p is incomplete; send the complete file", p); continue
            }
            val body = f.body + if (f.body.isNotEmpty() && !f.body.endsWith("\n")) "\n" else ""
            val bytes = body.toByteArray(Charsets.UTF_8)
            if (bytes.size > MAX_FILE) { problem("too_large", "$p exceeds the per-file limit", p); continue }
            staged[p] = linkedMapOf("path" to p, "sha256" to sha(bytes), "size" to bytes.size.toLong(), "content" to body)
        }
        val values = staged.values.toList()
        if (values.sumOf { Json.str(it["content"]).toByteArray(Charsets.UTF_8).size.toLong() } > MAX_TOTAL)
            problem("total_too_large", "Delivery exceeds the total file limit")
        try {
            preflight(dir(store), values)
            for (f in values) if ("base_sha256" !in f) {
                val dest = target(dir(store), Json.str(f["path"]))
                f["base_sha256"] = if (dest.isFile) sha(dest.readBytes()) else ""
            }
        } catch (e: Exception) { problem("file_conflict", e.message ?: "File preflight failed") }
        h["staged_files"] = ArrayList<Any?>(values)
        h["staging_problems"] = problems
        staged.keys.toList()
    }

    /** Flush complete bytes and replace without deleting the previous destination on rename failure. */
    private fun atomicWrite(dest: File, bytes: ByteArray) {
        val parent = dest.parentFile ?: throw ModelError("missing parent")
        if (!parent.isDirectory && !parent.mkdirs()) throw ModelError("cannot create ${parent.name}")
        val tmp = File.createTempFile(".aiwb-", ".tmp", parent)
        try {
            java.io.FileOutputStream(tmp).use { it.write(bytes); it.fd.sync() }
            if (!tmp.renameTo(dest)) throw ModelError("cannot replace ${dest.name}")
        } finally { tmp.delete() }
    }

    private fun requirePublishable(state: Obj, h: Obj) {
        val task = State.require(state, "tasks", Json.str(h["task_id"]))
        if (task["status"] in setOf("cancelled", "superseded") || h["status"] in setOf("rejected", "superseded"))
            throw ModelError("This delivery is closed or its task is cancelled/superseded; create a new task instead")
    }

    /** Exception-atomic files + acceptance. Not a power-loss transaction or hostile concurrent-writer guarantee. */
    fun integrate(store: ProjectStore, handoffId: String, accept: ((Obj) -> Unit)? = null): List<String> {
        val state = store.load()
        val h = State.require(state, "handoffs", handoffId)
        requirePublishable(state, h)
        if (h["source_response_id"] != null && "staged_files" !in h)
            throw ModelError("The files of this answer were not staged; paste it again")
        val blocking = Json.list(h["staging_problems"]).map { Json.obj(it) }.filter {
            it["severity"] == "error" && it["code"] in setOf("too_large", "total_too_large", "file_conflict", "truncated")
        }
        if (blocking.isNotEmpty()) throw ModelError("Cannot integrate: " + blocking.joinToString("; ") { Json.str(it["message"]) })
        val staged = Json.list(h["staged_files"]).map { Json.obj(it) }.filter { it["content"] is String }
        val root = dir(store).absoluteFile
        preflight(root, staged)
        val originals = staged.associate { f ->
            val p = Json.str(f["path"]); val dest = target(root, p)
            p to if (dest.isFile) dest.readBytes() else null
        }
        // Fresh exclusive backup per attempt, never overwrite an earlier recovery copy.
        val backupRoot = File(store.root, "backups").absoluteFile
        if (backupRoot != backupRoot.canonicalFile || (backupRoot.exists() && !backupRoot.isDirectory) ||
            (!backupRoot.exists() && backupRoot.parentFile?.list()?.contains(backupRoot.name) == true))
            throw ModelError("unsafe backup directory")
        if (!backupRoot.isDirectory && !backupRoot.mkdirs()) throw ModelError("cannot create backups")
        if (!Regex("HO-[0-9]+").matches(handoffId)) throw ModelError("unsafe handoff backup name")
        var backup = File(backupRoot, handoffId)
        if (!backup.mkdir()) {
            backup = File(backupRoot, "$handoffId-${java.util.UUID.randomUUID()}")
            if (!backup.mkdir()) throw ModelError("cannot create exclusive backup")
        }
        for ((p, bytes) in originals) if (bytes != null) atomicWrite(File(backup, p), bytes)
        val journal = File.createTempFile(".integration-", ".json", backup)
        atomicWrite(journal, StrictJson.stringify(linkedMapOf<String, Any?>(
            "handoff_id" to handoffId, "original_paths" to originals.filterValues { it != null }.keys.toList(),
            "new_paths" to originals.filterValues { it == null }.keys.toList())).toByteArray(Charsets.UTF_8))
        val written = ArrayList<String>()
        try {
            preflight(root, staged)
            for (f in staged) {
                val p = Json.str(f["path"])
                atomicWrite(target(root, p), Json.str(f["content"]).toByteArray(Charsets.UTF_8))
                written.add(p)
            }
            store.transaction("integrate files") { s ->
                val hh = State.require(s, "handoffs", handoffId)
                requirePublishable(s, hh)
                if (hh != h) throw ModelError("delivery changed during integration")
                accept?.invoke(s)
                hh["staged_files"] = ArrayList<Any?>(staged.map { LinkedHashMap(it).apply { remove("content") } })
                hh.remove("retained_files")
                hh["integrated_files"] = ArrayList<Any?>(written)
                hh["integration_backup"] = backup.relativeTo(store.root).invariantSeparatorsPath
                hh["integrated_at"] = State.nowUtc()
                State.emit(s, "files_integrated", "handoff_id" to handoffId, "task_id" to hh["task_id"],
                    "paths" to ArrayList<Any?>(written.take(50)), "count" to written.size.toLong(), "importance" to "major")
            }
        } catch (e: Exception) {
            val failed = ArrayList<String>()
            for (p in written.asReversed()) try {
                val dest = target(root, p)
                val expected = staged.first { it["path"] == p }
                if (!dest.isFile || sha(dest.readBytes()) != expected["sha256"])
                    throw ModelError("newer edit preserved")
                val old = originals[p]
                if (old == null) { if (!dest.delete()) throw ModelError("cannot remove new file") }
                else atomicWrite(dest, old)
            } catch (_: Exception) { failed.add(p) }
            if (failed.isNotEmpty()) throw ModelError("Integration failed; rollback incomplete for ${failed.joinToString()}; backups: ${backup.path}. ${e.message}")
            throw ModelError("Integration failed; original files restored. ${e.message}")
        }
        return written
    }

    data class Entry(val path: String, val size: Long)

    /** Project files, sorted, with sizes. */
    fun list(store: ProjectStore): List<Entry> {
        val root = dir(store)
        if (!root.isDirectory) return emptyList()
        return root.walkTopDown().filter { it.isFile }.map { it.relativeTo(root).invariantSeparatorsPath to it }
            .filter { safePath(it.first) == it.first }.map { Entry(it.first, it.second.length()) }.sortedBy { it.path }.toList()
    }

    fun read(store: ProjectStore, path: String): String {
        val p = safePath(path)
        if (p.isEmpty()) throw ModelError("unsafe path '$path'")
        return File(dir(store), p).readText(Charsets.UTF_8)
    }

    /** Every project file as one ZIP (deterministic order and timestamps, same bytes as the desktop for the same files). */
    fun zip(store: ProjectStore): ByteArray {
        val out = ByteArrayOutputStream()
        ZipOutputStream(out).use { z ->
            for (e in list(store)) {
                z.putNextEntry(ZipEntry(e.path).apply { time = FIXED_TIME })
                z.write(File(dir(store), e.path).readBytes())
                z.closeEntry()
            }
        }
        return out.toByteArray()
    }

    /** What an imported ZIP did, in words the user can read (BF-075). */
    data class ZipReport(val written: List<String>, val replaced: List<String>, val unchanged: List<String>,
                         val skipped: List<String>, val skippedCount: Int, val fixes: List<String>, val backup: String) {
        fun message(): String {
            val sb = StringBuilder("${written.size} file(s) imported")
            if (replaced.isNotEmpty()) sb.append(", ${replaced.size} replaced (backup kept in $backup)")
            if (unchanged.isNotEmpty()) sb.append(", ${unchanged.size} unchanged")
            if (skippedCount > 0)
                sb.append(", $skippedCount skipped: ").append(skipped.joinToString("; ")).append(if (skippedCount > skipped.size) "; …" else "")
            sb.append('.')
            if (fixes.isNotEmpty()) sb.append(' ').append(fixes.joinToString(". ")).append('.')
            return sb.toString()
        }
    }

    private val ZIP_NOISE = listOf("__MACOSX/", ".DS_Store", "Thumbs.db", "desktop.ini")
    private val ZIP_ROOTS = setOf("README.md", "readme.md", "package.json", "pyproject.toml", "requirements.txt", ".gitignore",
        "build.gradle", "build.gradle.kts", "settings.gradle", "Cargo.toml", "go.mod", "index.html")

    private fun looksSecret(base: String): Boolean {
        val b = base.lowercase(java.util.Locale.ROOT)
        return b == ".env" || (b.startsWith(".env.") && b != ".env.example") || b == "id_rsa" || b == "id_ed25519" ||
            listOf(".pem", ".p12", ".pfx", ".key", ".keystore", ".jks").any { b.endsWith(it) }
    }

    /**
     * Import a ZIP into the file space with the desktop rules (`intake/answer_files.zip_files`), BF-075:
     * `./` and `\` names are normalised, one top folder that holds README/package.json/… is taken as the project root,
     * system junk, any `.git`/`.workbench` part, binaries and secret files are skipped (and listed), every entry is read
     * with a size bound, overwritten files are backed up under `backups/zip-import-N/`, and a `files_imported` event is
     * recorded. A genuine traversal (`..`, absolute path, drive letter) still refuses the whole archive.
     */
    fun importZip(store: ProjectStore, data: ByteArray): ZipReport {
        val fixes = ArrayList<String>()
        val skipped = ArrayList<String>()
        var skippedCount = 0
        fun skip(why: String) { skippedCount++; if (skipped.size < 8) skipped.add(why) }
        val raw = LinkedHashMap<String, ByteArray>()
        var kept = 0L
        var expanded = 0L
        var noise = 0
        var vcs = 0
        var normalised = 0
        ZipInputStream(ByteArrayInputStream(data)).use { z ->
            while (true) {
                val e = z.nextEntry ?: break
                if (e.isDirectory) continue
                val orig = e.name
                var name = orig.replace('\\', '/')
                if (name != orig) normalised++
                while (name.startsWith("./")) { name = name.substring(2); normalised++ }
                val parts = name.split('/').filter { it.isNotEmpty() }
                if (name.startsWith("/") || Regex("^[A-Za-z]:").containsMatchIn(name) || parts.any { it == ".." } || parts.isEmpty())
                    throw ModelError("unsafe ZIP entry: $orig")
                // bounded read: one huge entry must not exhaust memory
                val buf = ByteArrayOutputStream()
                val chunk = ByteArray(8192)
                var tooBig = false
                while (true) {
                    val n = z.read(chunk)
                    if (n < 0) break
                    expanded += n
                    if (expanded > MAX_TOTAL * 4L) throw ModelError("ZIP too large")
                    if (!tooBig) { buf.write(chunk, 0, n); if (buf.size() > MAX_FILE) { tooBig = true; buf.reset() } }
                }
                if (ZIP_NOISE.any { it in name }) { noise++; continue }
                if (parts.any { it.lowercase(java.util.Locale.ROOT) in RESERVED }) { vcs++; continue }
                if (tooBig) { skip("${parts.joinToString("/")} is larger than ${MAX_FILE / 1024} KB"); continue }
                val bytes = buf.toByteArray()
                if (bytes.take(8192).any { it == 0.toByte() }) { skip("${parts.joinToString("/")} is a binary file"); continue }
                if (looksSecret(parts.last())) { skip("${parts.joinToString("/")} looks like a secret"); continue }
                if (safePath(name).isEmpty()) { skip("${parts.joinToString("/")} is not a valid file name"); continue }
                if (kept + bytes.size > MAX_TOTAL) { skip("the files exceed ${MAX_TOTAL / (1024 * 1024)} MB in total"); break }
                kept += bytes.size
                raw[safePath(name)] = bytes
            }
        }
        if (normalised > 0) fixes.add("$normalised name(s) with ./ or \\ were normalised")
        if (noise > 0) fixes.add("$noise system file(s) (__MACOSX, .DS_Store…) ignored")
        if (vcs > 0) fixes.add("$vcs .git/.workbench file(s) ignored")
        // one top folder that is itself the project root (GitHub "Download ZIP": myapp-main/…) is stripped
        val tops = raw.keys.map { it.substringBefore('/') }.toSet()
        var strip = ""
        if (tops.size == 1 && raw.keys.all { '/' in it } && raw.keys.any { it.substringAfter('/') in ZIP_ROOTS }) {
            strip = tops.first() + "/"
            fixes.add("the ZIP's top folder \"${tops.first()}/\" was taken as the project root")
        }
        val entries = LinkedHashMap<String, ByteArray>()
        for ((p0, b) in raw) {
            val p = safePath(if (strip.isNotEmpty()) p0.removePrefix(strip) else p0)
            if (p.isEmpty()) { skip("$p0 is not a valid file name"); continue }
            entries[p] = b
        }
        val root = dir(store).apply { mkdirs() }.absoluteFile
        val staged = entries.keys.map { linkedMapOf<String, Any?>("path" to it) as Obj }
        preflight(root, staged)   // links, case aliases and file/directory collisions refuse the whole archive
        val originals = entries.keys.associateWith { p -> target(root, p).let { if (it.isFile) it.readBytes() else null } }
        val replaced = entries.keys.filter { originals[it] != null && !originals[it]!!.contentEquals(entries[it]!!) }
        val unchanged = entries.keys.filter { originals[it] != null && originals[it]!!.contentEquals(entries[it]!!) }
        var backupName = ""
        if (replaced.isNotEmpty()) {
            val backupRoot = File(store.root, "backups").absoluteFile
            if (backupRoot.exists() && !backupRoot.isDirectory) throw ModelError("unsafe backup directory")
            if (!backupRoot.isDirectory && !backupRoot.mkdirs()) throw ModelError("cannot create backups")
            var n = 1
            var backup = File(backupRoot, "zip-import-$n")
            while (!backup.mkdir()) { n++; backup = File(backupRoot, "zip-import-$n"); if (n > 10_000) throw ModelError("cannot create backup") }
            for (p in replaced) atomicWrite(File(backup, p), originals[p]!!)
            backupName = "backups/zip-import-$n"
        }
        val written = ArrayList<String>()
        try {
            for ((p, b) in entries) {
                if (p in unchanged) continue
                atomicWrite(target(root, p), b)
                written.add(p)
            }
        } catch (e: Exception) {
            for (p in written.asReversed()) try {
                val old = originals[p]
                if (old == null) target(root, p).delete() else atomicWrite(target(root, p), old)
            } catch (_: Exception) { }
            throw ModelError("Import failed; the files were restored. ${e.message}")
        }
        val report = ZipReport(written.toList(), replaced, unchanged, skipped, skippedCount, fixes, backupName)
        store.transaction("import files from ZIP") { s ->
            State.emit(s, "files_imported", "count" to written.size.toLong(), "replaced" to replaced.size.toLong(),
                "skipped" to skippedCount.toLong(), "paths" to ArrayList<Any?>(written.take(50)), "backup" to backupName,
                "importance" to "major")
        }
        return report
    }

    /** Compatibility wrapper: the paths written by [importZip]. */
    fun unzip(store: ProjectStore, data: ByteArray): List<String> = importZip(store, data).let { it.written + it.unchanged }

    private val FIXED_TIME = java.util.GregorianCalendar(2020, 0, 1, 0, 0, 0).timeInMillis
}
