package io.github.golshandvr.aiworkbench.core

import java.net.HttpURLConnection
import java.net.URL

/**
 * Minimal GitHub REST client for the blue nodes on the phone (roadmap 4.5.0 / mobile 1.6.0, F3, F22, F24).
 *
 * Same rules as desktop `publisher.GitHubStateClient` + `repo.py`: one atomic Git Data commit, fast-forward only
 * (`force=false`), never a protected branch. The transport is injectable so `RepoTest` runs against a fake GitHub
 * without network. The token comes from [io.github.golshandvr.aiworkbench.TokenVault] (Android Keystore).
 */
class GitHubApi(private val token: String, val owner: String, val repo: String,
                private val transport: (method: String, url: String, headers: Map<String, String>, body: String?) -> Pair<Int, String> = ::http,
                private val api: String = "https://api.github.com") {

    class ApiError(val status: Int, message: String) : Exception(message)

    fun call(method: String, path: String, payload: Any? = null, absolute: Boolean = false): Any? {
        val url = if (absolute) "$api$path" else "$api/repos/$owner/$repo$path"
        val headers = linkedMapOf("Authorization" to "Bearer $token", "Accept" to "application/vnd.github+json",
            "X-GitHub-Api-Version" to "2022-11-28", "User-Agent" to "AI-Workbench-Android")
        val body = payload?.let { headers["Content-Type"] = "application/json"; StrictJson.stringify(it) }
        val (status, text) = try { transport(method, url, headers, body) } catch (e: java.io.IOException) {
            throw ApiError(0, "GitHub is not reachable (${e.javaClass.simpleName})")
        }
        if (status == 401) throw ApiError(status, "GitHub rejected the token (401). Update the token.")
        if (status == 403 || status == 429) throw ApiError(status, "GitHub refused access ($status): check the token permissions or the rate limit.")
        if (status in setOf(409, 422) && "/git/refs" in path) throw ApiError(status, "the branch moved on GitHub (not fast-forward)")
        if (status >= 400) throw ApiError(status, "GitHub API $method ${path.substringBefore('?')} failed: $status")
        return if (text.isBlank()) null else StrictJson.parse(text)
    }

    fun branchHead(branch: String): String? = try {
        Json.str(Json.obj(Json.obj(call("GET", "/git/ref/heads/$branch"))["object"])["sha"])
    } catch (e: ApiError) { if (e.status == 404) null else throw e }

    fun defaultHead(): String {
        val def = Json.str(Json.obj(call("GET", ""))["default_branch"])
        return Json.str(Json.obj(Json.obj(call("GET", "/git/ref/heads/$def"))["object"])["sha"])
    }

    /** F3: the repository exists and the project branch exists (created from the default head when missing). */
    fun connect(branch: String): String {
        if (branch in Repo.PROTECTED) throw ModelError("refusing to use the protected branch '$branch'")
        call("GET", "")
        branchHead(branch)?.let { return it }
        val head = defaultHead()
        call("POST", "/git/refs", linkedMapOf("ref" to "refs/heads/$branch", "sha" to head))
        return head
    }

    /** F22: one atomic commit, fast-forward only. Returns the new commit SHA. */
    fun commitFiles(branch: String, files: Map<String, String>, message: String): String {
        if (branch in Repo.PROTECTED) throw ModelError("refusing to write the protected branch '$branch'")
        val head = branchHead(branch)
        val parent = head ?: defaultHead()
        val baseTree = Json.str(Json.obj(Json.obj(call("GET", "/git/commits/$parent"))["tree"])["sha"])
        val tree = ArrayList<Any?>()
        for ((p, c) in files.toSortedMap()) {
            val blob = Json.str(Json.obj(call("POST", "/git/blobs", linkedMapOf("content" to c, "encoding" to "utf-8")))["sha"])
            tree.add(linkedMapOf("path" to p, "mode" to "100644", "type" to "blob", "sha" to blob))
        }
        val newTree = Json.str(Json.obj(call("POST", "/git/trees", linkedMapOf("base_tree" to baseTree, "tree" to tree)))["sha"])
        val commit = Json.str(Json.obj(call("POST", "/git/commits",
            linkedMapOf("message" to message, "tree" to newTree, "parents" to arrayListOf<Any?>(parent))))["sha"])
        if (head == null) call("POST", "/git/refs", linkedMapOf("ref" to "refs/heads/$branch", "sha" to commit))
        else call("PATCH", "/git/refs/heads/$branch", linkedMapOf("sha" to commit, "force" to false))
        return commit
    }

    /** F24: tag on the saved commit + GitHub Release. Returns the release URL. */
    fun release(tag: String, sha: String, branch: String, label: String): String {
        call("POST", "/git/refs", linkedMapOf("ref" to "refs/tags/$tag", "sha" to sha))
        val body = call("POST", "/releases", linkedMapOf("tag_name" to tag, "name" to label, "target_commitish" to branch,
            "body" to "Released with AI Workbench."))
        return Json.str(Json.obj(body)["html_url"])
    }

    companion object {
        fun http(method: String, url: String, headers: Map<String, String>, body: String?): Pair<Int, String> {
            if (!url.startsWith("https://")) throw java.io.IOException("GitHub API URL must use https")
            val c = URL(url).openConnection() as HttpURLConnection
            c.connectTimeout = 15000; c.readTimeout = 30000
            try { c.requestMethod = method }  // Android's HttpURLConnection (OkHttp) accepts PATCH
            catch (_: java.net.ProtocolException) { c.requestMethod = "POST"; c.setRequestProperty("X-HTTP-Method-Override", method) }
            for ((k, v) in headers) c.setRequestProperty(k, v)
            if (body != null) { c.doOutput = true; c.outputStream.use { it.write(body.toByteArray(Charsets.UTF_8)) } }
            val code = c.responseCode
            val text = (if (code >= 400) c.errorStream else c.inputStream)?.use { it.readBytes().toString(Charsets.UTF_8) } ?: ""
            c.disconnect()
            return code to text
        }
    }
}
