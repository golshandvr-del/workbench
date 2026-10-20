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
        val p = path.orEmpty().trim().replace('\\', '/')
        if (p.isEmpty() || p.startsWith("/") || Regex("^[A-Za-z]:").containsMatchIn(p) || '\u0000' in p) return ""
        val parts = p.split("/").filter { it.isNotEmpty() && it != "." }
        if (parts.isEmpty() || parts.any { it == ".." } || parts[0] in RESERVED) return ""
        return parts.joinToString("/")
    }

    private fun sha(b: ByteArray) = MessageDigest.getInstance("SHA-256").digest(b).joinToString("") { "%02x".format(it) }

    /** Keep the safe, in-scope files of a pasted answer on the handoff (replacing earlier staging). */
    fun stage(store: ProjectStore, handoffId: String, text: String): List<String> = store.transaction("stage files") { s ->
        val h = State.require(s, "handoffs", handoffId)
        val allowed = Diagnose.taskPaths(Json.obj(State.coll(s, "tasks")[h["task_id"]]))
        val staged = LinkedHashMap<String, Obj>()
        var total = 0
        for (f in Diagnose.parseFiles(text).first) {
            val p = safePath(f.path)
            val body = f.body + if (f.body.isNotEmpty() && !f.body.endsWith("\n")) "\n" else ""
            val bytes = body.toByteArray(Charsets.UTF_8)
            if (p.isEmpty() || !Diagnose.inScope(p, allowed) || body.isBlank() || bytes.size > MAX_FILE || total + bytes.size > MAX_TOTAL) continue
            total += bytes.size
            staged.remove(p)
            staged[p] = linkedMapOf("path" to p, "sha256" to sha(bytes), "size" to bytes.size.toLong(), "content" to body)
        }
        h["staged_files"] = ArrayList<Any?>(staged.values)
        staged.keys.toList()
    }

    /** F17: write the staged files of an accepted handoff into the project's file space. */
    fun integrate(store: ProjectStore, handoffId: String): List<String> {
        val root = dir(store).apply { mkdirs() }.canonicalFile
        val h = Json.obj(State.coll(store.load(), "handoffs")[handoffId])
        val staged = Json.list(h["staged_files"]).map { Json.obj(it) }.filter { it["content"] is String }
        if (staged.isEmpty()) return emptyList()
        val backup = File(store.root, "backups/$handoffId")
        val written = ArrayList<String>()
        for (f in staged) {
            val p = safePath(Json.str(f["path"]))
            if (p.isEmpty()) continue
            val target = File(root, p).canonicalFile
            if (!target.path.startsWith(root.path + File.separator)) continue
            target.parentFile?.mkdirs()
            if (target.isFile) File(backup, p).apply { parentFile?.mkdirs() }.writeBytes(target.readBytes())
            val tmp = File(target.parentFile, target.name + ".aiwb-tmp")
            tmp.writeText(Json.str(f["content"]), Charsets.UTF_8)
            if (!tmp.renameTo(target)) { target.delete(); tmp.renameTo(target) }
            written.add(p)
        }
        store.transaction("integrate files") { s ->
            val hh = State.require(s, "handoffs", handoffId)
            hh["staged_files"] = ArrayList<Any?>(Json.list(hh["staged_files"]).map { LinkedHashMap(Json.obj(it)).apply { remove("content") } })
            hh["integrated_files"] = ArrayList<Any?>(written)
            hh["integrated_at"] = State.nowUtc()
            State.emit(s, "files_integrated", "handoff_id" to handoffId, "task_id" to hh["task_id"],
                "paths" to ArrayList<Any?>(written.take(50)), "count" to written.size.toLong(), "importance" to "major")
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

    /** Extract a ZIP into the file space; refuses the whole archive if any entry is unsafe (zip-slip). */
    fun unzip(store: ProjectStore, data: ByteArray): List<String> {
        val entries = LinkedHashMap<String, ByteArray>()
        var total = 0L
        ZipInputStream(ByteArrayInputStream(data)).use { z ->
            while (true) {
                val e = z.nextEntry ?: break
                if (e.isDirectory) continue
                val name = e.name.trim('/')
                if (safePath(e.name) != name) throw ModelError("unsafe ZIP entry: ${e.name}")
                val b = z.readBytes()
                total += b.size
                if (total > MAX_TOTAL * 4L) throw ModelError("ZIP too large")
                entries[safePath(name)] = b
            }
        }
        val root = dir(store).apply { mkdirs() }
        for ((p, b) in entries) File(root, p).apply { parentFile?.mkdirs() }.writeBytes(b)
        return entries.keys.toList()
    }

    private val FIXED_TIME = java.util.GregorianCalendar(2020, 0, 1, 0, 0, 0).timeInMillis
}
