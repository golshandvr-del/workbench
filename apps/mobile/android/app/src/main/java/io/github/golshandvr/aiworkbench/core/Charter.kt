package io.github.golshandvr.aiworkbench.core

/**
 * Project Charter on the phone (roadmap mobile 1.0.0; port of desktop `aiwb/v2/charter.py`, contract
 * `project-charter.v1`).
 *
 * Same prompt, same block markers, same validation messages and the same conversion into a manager proposal, so a
 * charter accepted on the phone produces the same state document as on the desktop.
 */
object Charter {
    private val CHARTER_RE = Regex("(?s)<<<AIWB_PROJECT_CHARTER>>>\\s*(.*?)\\s*<<<AIWB_END_PROJECT_CHARTER>>>")
    const val OPEN_MARK = "<<<AIWB_PROJECT_CHARTER>>>"
    val SEMVER = Regex("^v?\\d+\\.\\d+\\.\\d+(?:[-+][0-9A-Za-z.-]+)?$")
    private val REF = Regex("^[A-Za-z0-9][A-Za-z0-9_.-]{0,39}$")
    val REQUIRED_SECTIONS = listOf("architecture", "team", "coordination", "roadmap", "tasks", "start_prompts")
    const val MAX_TASKS = 40
    const val MAX_MILESTONES = 12
    const val MAX_AGENTS = 12

    data class Result(val ok: Boolean, val data: Obj?, val errors: List<String>, val warnings: List<String>,
                      val fixes: List<String>)

    data class Validation(val errors: List<String>, val warnings: List<String>)

    val FORMAT = """Return your reasoning in plain text first, then exactly ONE block (valid JSON, no comments):
<<<AIWB_PROJECT_CHARTER>>>
{"schema_version": "1.0", "charter_type": "project_charter", "base_state_revision": <the state_revision above>,
 "project": {"name": "…", "goal": "…", "summary": "two or three sentences"},
 "architecture": {"summary": "…", "modules": [
   {"id": "core", "name": "Core logic", "purpose": "…", "paths": ["src/core/**"], "depends_on": []},
   {"id": "ui", "name": "User interface", "purpose": "…", "paths": ["src/ui/**"], "depends_on": ["core"]}]},
 "team": {"pm_counted": true, "total_agents": 3, "parallel_chats": 2,
          "rationale": "why this many AI chats work in parallel", "simpler_alternative": "a smaller option and its trade-off",
          "agents": [
   {"agent_id": "agent-project-manager", "role": "project_manager", "name": "Project manager", "purpose": "…", "owns_modules": []},
   {"agent_id": "agent-core-dev", "role": "implementer", "name": "Core developer", "purpose": "…", "owns_modules": ["core"]},
   {"agent_id": "agent-ui-dev", "role": "implementer", "name": "UI developer", "purpose": "…", "owns_modules": ["ui"]}]},
 "coordination": {
   "file_ownership": [{"agent_id": "agent-core-dev", "paths": ["src/core/**"]}, {"agent_id": "agent-ui-dev", "paths": ["src/ui/**"]}],
   "shared_contracts": [{"name": "Core API", "path": "docs/contracts/core-api.md", "owner_agent_id": "agent-core-dev",
                         "consumers": ["agent-ui-dev"]}],
   "sync_points": [{"after_milestone": "m1", "description": "UI starts only after the core API contract is frozen"}],
   "conflict_resolution": "who decides when two AIs need the same file or disagree"},
 "roadmap": {"milestones": [
   {"ref": "m1", "title": "Core ready", "version": "0.1.0", "criteria": ["…"], "task_refs": ["t1"]},
   {"ref": "m2", "title": "First usable app", "version": "0.2.0", "criteria": ["…"], "task_refs": ["t2"]}]},
 "tasks": [
   {"ref": "t1", "title": "…", "objective": "…", "owner_agent_id": "agent-core-dev", "milestone_ref": "m1",
    "depends_on_refs": [], "parallel_group": "A", "scope": {"include": ["src/core/**"], "exclude": []},
    "acceptance_criteria": ["…"], "priority": "high"},
   {"ref": "t2", "title": "…", "objective": "…", "owner_agent_id": "agent-ui-dev", "milestone_ref": "m2",
    "depends_on_refs": ["t1"], "parallel_group": "B", "scope": {"include": ["src/ui/**"], "exclude": []},
    "acceptance_criteria": ["…"], "priority": "medium"}],
 "start_prompts": [{"agent_id": "agent-core-dev", "prompt": "the complete first message for this AI's own chat"},
                   {"agent_id": "agent-ui-dev", "prompt": "…"}],
 "risks": ["…"], "questions_for_user": ["…"]}
<<<AIWB_END_PROJECT_CHARTER>>>
Rules:
- Every section above is required: architecture, team, coordination, roadmap, tasks, start_prompts.
- agent_id looks like agent-<lowercase-words>; role is one of: """ + State.ROLES.joinToString(", ") + """.
- Every task has exactly one owner from team.agents, a milestone_ref, a file scope inside that owner's file_ownership,
  and acceptance criteria. Use refs (t1, m1, …); Workbench assigns the real IDs.
- Never give two AIs ownership of the same path. Shared files go into shared_contracts with one owner.
- Tasks in the same parallel_group run at the same time: never more groups' tasks at once than parallel_chats.
- Every milestone has a semantic version (e.g. 0.1.0); versions grow along the roadmap.
- Every AI except the project manager gets a start prompt that stands on its own: that chat has NO access to this
  conversation, the files or other chats; the user copies every prompt by hand.
- Prefer a small team; propose more parallel AIs only with the benefit, the risk and the coordination cost."""

    /** The "design the whole project" prompt (same text as the desktop). */
    fun prompt(project: Map<String, Any?>, state: Obj): String {
        val agents = State.coll(state, "agents").values.map { Json.obj(it) }
            .filter { it["enabled"] != false }.sortedBy { Json.str(it["agent_id"]) }
        val accounts = State.coll(state, "account_profiles").values.map { Json.obj(it) }
            .filter { it["enabled"] != false }.sortedBy { Json.str(it["account_profile_id"]) }
        val team = Json.obj(Json.obj(state["settings"])["team"])
        val maxChats = (team["max_parallel_chats"] as? Number)?.toInt() ?: 2
        val lines = mutableListOf("# AI Workbench — Project Charter (design the whole project)",
            "You are the Project Manager and architect for this project. You cannot read files, run anything or " +
                "contact other chats; the user copies every prompt by hand and pastes your answer back.", "",
            "State revision: ${Json.int(state["state_revision"])}", "", "## Project",
            "- Goal: ${Json.str(project["goal"])}")
        for ((k, label) in listOf("non_goals" to "Non-goals", "success" to "Success criteria",
            "platform" to "Platform / technology", "constraints" to "Constraints", "limits" to "Time / cost limits")) {
            val v = Json.str(project[k])
            if (v.isNotEmpty()) lines.add("- $label: $v")
        }
        lines += listOf("", "## Resources registered by the user (self-declared labels, NOT verified)")
        if (accounts.isEmpty()) lines.add("- (no account profiles registered)")
        for (a in accounts) lines.add("- ${Json.str(a["account_profile_id"])}: ${Json.str(a["display_name"])} " +
            "(${Json.str(a["provider"])}, plan ${Json.str(a["plan"])})")
        lines += listOf("- Maximum chats the user will follow at the same time: $maxChats", "",
            "## Existing agents (you may reuse them by agent_id)")
        for (a in agents) lines.add("- ${Json.str(a["agent_id"])} (${Json.str(a["role"])}): ${Json.str(a["purpose"])}")
        lines += listOf("", "## Your task — answer ALL of these",
            "1. Architecture: the modules of the whole project, their purpose, the paths each one owns and how they " +
                "depend on each other.",
            "2. Team: how many AI chats work in parallel and WHY that number (and a simpler alternative).",
            "3. Coordination protocol: which AI owns which files/paths, the shared contracts between them, the sync " +
                "points (when one AI must wait for another) and how conflicts are resolved.",
            "4. Roadmap: milestones in order, each with a version number and acceptance criteria.",
            "5. Tasks: the tasks of every AI, with owner, milestone, dependencies, scope and acceptance criteria.",
            "6. Start prompts: a complete first message for every AI's own chat.",
            "7. Risks and the questions only the user can answer.", "", FORMAT)
        return lines.joinToString("\n")
    }

    // ------------------------------------------------------------------ parsing

    fun find(text: String?): String? {
        val m = CHARTER_RE.find(text ?: "") ?: return null
        val body = m.groupValues[1].trim()
        val f = Regex("(?s)^`{3,}\\s*(?:json)?\\s*\\n(.*?)\\n`{3,}$").find(body)
        return f?.groupValues?.get(1) ?: body
    }

    fun has(text: String?): Boolean {
        if (CHARTER_RE.containsMatchIn(text ?: "")) return true
        return try { CHARTER_RE.containsMatchIn(Normalize.normalize(text).text) } catch (_: Exception) { false }
    }

    private fun load(text: String?): Triple<Obj?, List<String>, List<String>> {
        val fixes = ArrayList<String>()
        val n = Normalize.normalize(text ?: "")
        val candidates = mutableListOf(text ?: "")
        if (n.changed) candidates.add(n.text)
        var lastError = ""
        for ((i, cand) in candidates.withIndex()) {
            val body = find(cand) ?: continue
            for (round in 0..1) {
                val attempt: String = if (round == 0) body else {
                    val r = Normalize.normalizeJsonText(body)
                    if (!r.changed) break
                    fixes.addAll(r.fixes)
                    r.text
                }
                val data = try { StrictJson.copy(StrictJson.parse(attempt)) } catch (e: StrictJson.ParseError) {
                    lastError = "the charter block is not valid JSON: ${e.message}"
                    continue
                }
                val all = if (i > 0) n.fixes + fixes else fixes
                @Suppress("UNCHECKED_CAST")
                val obj = data as? Obj ?: return Triple(null, listOf("the charter block must be one JSON object"), all)
                return Triple(obj, emptyList(), all)
            }
        }
        if (lastError.isNotEmpty()) return Triple(null, listOf(lastError), fixes)
        if ("AIWB_PROJECT_CHARTER" in (text ?: "")) return Triple(null, listOf("the charter block is not closed: " +
            "<<<AIWB_END_PROJECT_CHARTER>>> is missing (the answer was probably cut off)"), fixes)
        return Triple(null, listOf("no AIWB_PROJECT_CHARTER block found"), fixes)
    }

    private fun isInt(v: Any?) = v is Long || v is Int

    private fun list(d: Map<*, *>, key: String, path: String, errors: MutableList<String>, required: Boolean = true): List<Any?> {
        val v = d[key]
        if (v == null) { if (required) errors.add("$path.$key: missing (a non-empty list is required)"); return emptyList() }
        if (v !is List<*>) { errors.add("$path.$key: must be a list"); return emptyList() }
        if (required && v.isEmpty()) errors.add("$path.$key: is empty")
        return v
    }

    private fun str(d: Map<*, *>, key: String, path: String, errors: MutableList<String>, required: Boolean = true,
                    limit: Int = 4000): String {
        val v = d[key]
        if (v == null || (v is String && v.isBlank())) { if (required) errors.add("$path.$key: missing"); return "" }
        if (v !is String) { errors.add("$path.$key: must be text"); return "" }
        if (v.length > limit) errors.add("$path.$key: longer than $limit characters")
        return v.trim()
    }

    private fun strs(v: Any?): List<String> = Json.strs(v)
    private fun m(v: Any?): Map<*, *> = v as? Map<*, *> ?: emptyMap<String, Any?>()
    private fun repr(v: Any?): String = if (v is String) "'$v'" else if (v == null) "None" else v.toString()

    fun normPath(p: String): String {
        var s = p.replace("\\", "/").trim().trimStart('.', '/')
        s = s.replace(Regex("/?\\*\\*?$"), "")
        return s.trimEnd('/')
    }

    fun pathsOverlap(a: String, b: String): Boolean {
        val x = normPath(a); val y = normPath(b)
        if (x.isEmpty() || y.isEmpty()) return true
        return x == y || x.startsWith("$y/") || y.startsWith("$x/")
    }

    fun inside(path: String, owned: List<String>): Boolean {
        val p = normPath(path)
        return owned.any { val o = normPath(it); p == o || p.startsWith("$o/") || o.isEmpty() }
    }

    /** Check every required part (desktop `validate_charter`, same messages). Pure. */
    fun validate(data: Map<String, Any?>, state: Obj? = null): Validation {
        val errors = ArrayList<String>()
        val warnings = ArrayList<String>()
        val stAgents = State.coll(state ?: linkedMapOf(), "agents")
        if (data["schema_version"] != "1.0") errors.add("schema_version: must be \"1.0\"")
        if (!isInt(data["base_state_revision"]))
            errors.add("base_state_revision: missing (an integer, copy the state_revision from the prompt)")
        for (sec in REQUIRED_SECTIONS) if (sec !in data) errors.add("$sec: section missing")
        val obj = listOf("architecture", "team", "coordination", "roadmap").associateWith { m(data[it]) }
        for (k in obj.keys) if (k in data && data[k] !is Map<*, *>) errors.add("$k: must be an object")

        // architecture
        val arch = obj.getValue("architecture")
        if ("architecture" in data) str(arch, "summary", "architecture", errors)
        val modules = if ("architecture" in data) list(arch, "modules", "architecture", errors) else emptyList()
        val moduleIds = ArrayList<String>()
        modules.forEachIndexed { i, raw ->
            val p = "architecture.modules[$i]"
            val mo = raw as? Map<*, *> ?: run { errors.add("$p: must be an object"); return@forEachIndexed }
            val mid = str(mo, "id", p, errors, limit = 40)
            if (mid.isNotEmpty() && mid in moduleIds) errors.add("$p.id: duplicate module id '$mid'")
            moduleIds.add(mid)
            str(mo, "purpose", p, errors)
            if (strs(mo["paths"]).isEmpty()) errors.add("$p.paths: missing (which files/folders belong to module ${mid.ifEmpty { i.toString() }})")
        }
        modules.forEachIndexed { i, raw ->
            val mo = raw as? Map<*, *> ?: return@forEachIndexed
            for (dep in strs(mo["depends_on"])) if (dep !in moduleIds)
                errors.add("architecture.modules[$i].depends_on: unknown module '$dep'")
        }

        // team
        val team = obj.getValue("team")
        val agents = if ("team" in data) list(team, "agents", "team", errors) else emptyList()
        if ("team" in data) {
            str(team, "rationale", "team", errors)
            if (team["pm_counted"] !is Boolean)
                errors.add("team.pm_counted: missing (true/false — is the project manager counted in total_agents?)")
            for (k in listOf("total_agents", "parallel_chats")) {
                val v = team[k]
                if (!isInt(v) || (v as Number).toLong() < 1) errors.add("team.$k: missing (a whole number ≥ 1)")
            }
            if (str(team, "simpler_alternative", "team", ArrayList(), required = false).isEmpty())
                warnings.add("team.simpler_alternative: no simpler alternative was given")
        }
        if (agents.size > MAX_AGENTS) errors.add("team.agents: too many agents (${agents.size} > $MAX_AGENTS)")
        val agentRoles = LinkedHashMap<String, String>()
        agents.forEachIndexed { i, raw ->
            val p = "team.agents[$i]"
            val a = raw as? Map<*, *> ?: run { errors.add("$p: must be an object"); return@forEachIndexed }
            val aid = a["agent_id"]
            if (!State.validAgentId(aid)) {
                errors.add("$p.agent_id: ${repr(aid)} must look like 'agent-core-dev' (lowercase letters, digits, '-')")
                return@forEachIndexed
            }
            aid as String
            if (aid in agentRoles) errors.add("$p.agent_id: duplicate agent $aid")
            val role = a["role"]
            if (role !in State.ROLES) errors.add("$p.role: ${repr(role)} must be one of ${State.ROLES.joinToString(", ")}")
            val existing = stAgents[aid] as? Map<*, *>
            if (existing != null && role in State.ROLES && existing["role"] != role)
                errors.add("$p: agent $aid already exists with role ${existing["role"]}, not $role")
            str(a, "purpose", p, errors)
            for (mod in strs(a["owns_modules"])) if (mod !in moduleIds) errors.add("$p.owns_modules: unknown module '$mod'")
            agentRoles[aid] = role.toString()
        }
        if (agents.isNotEmpty() && isInt(team["total_agents"])) {
            val declared = (team["total_agents"] as Number).toInt()
            val actual = if (team["pm_counted"] != false) agentRoles.size else agentRoles.values.count { it != "project_manager" }
            if (declared != actual) warnings.add("team.total_agents: says $declared but team.agents lists $actual counted agent(s)")
        }
        val workers = agentRoles.filter { it.value != "project_manager" }.keys.toList()
        if (agents.isNotEmpty() && workers.isEmpty()) errors.add("team.agents: no AI besides the project manager does the work")
        val ownedModules = agents.mapNotNull { it as? Map<*, *> }.flatMap { strs(it["owns_modules"]) }.toSet()
        for (mid in moduleIds) if (mid.isNotEmpty() && mid !in ownedModules)
            warnings.add("architecture: module '$mid' has no owner in team.agents[].owns_modules")

        // coordination
        val co = obj.getValue("coordination")
        val ownership = LinkedHashMap<String, MutableList<String>>()
        var sync: List<Any?> = emptyList()
        if ("coordination" in data) {
            list(co, "file_ownership", "coordination", errors).forEachIndexed { i, raw ->
                val p = "coordination.file_ownership[$i]"
                val o = raw as? Map<*, *> ?: run { errors.add("$p: must be an object"); return@forEachIndexed }
                val aid = Json.str(o["agent_id"])
                if (aid !in agentRoles) errors.add("$p.agent_id: ${aid.ifEmpty { "(missing)" }} is not in team.agents")
                val paths = strs(o["paths"])
                if (paths.isEmpty()) errors.add("$p.paths: missing")
                ownership.getOrPut(aid) { ArrayList() }.addAll(paths)
            }
            val owners = ownership.keys.sorted()
            for (x in owners.indices) for (y in x + 1 until owners.size)
                for (pa in ownership.getValue(owners[x])) for (pb in ownership.getValue(owners[y]))
                    if (pathsOverlap(pa, pb)) errors.add("coordination.file_ownership: ${owners[x]} ($pa) and ${owners[y]} ($pb) own the " +
                        "same path — give it to one AI or make it a shared contract")
            list(co, "shared_contracts", "coordination", errors, required = false).forEachIndexed { i, raw ->
                val p = "coordination.shared_contracts[$i]"
                val sc = raw as? Map<*, *> ?: run { errors.add("$p: must be an object"); return@forEachIndexed }
                str(sc, "name", p, errors, limit = 200)
                if (Json.str(sc["owner_agent_id"]) !in agentRoles)
                    errors.add("$p.owner_agent_id: ${Json.str(sc["owner_agent_id"]).ifEmpty { "(missing)" }} is not in team.agents")
                for (c in strs(sc["consumers"])) if (c !in agentRoles) errors.add("$p.consumers: $c is not in team.agents")
            }
            if (list(co, "shared_contracts", "coordination", ArrayList(), required = false).isEmpty() && workers.size > 1)
                warnings.add("coordination.shared_contracts: several AIs work in parallel but no shared contract is defined")
            sync = list(co, "sync_points", "coordination", errors, required = workers.size > 1)
            str(co, "conflict_resolution", "coordination", errors)
        }
        for (w in workers) if (w !in ownership) warnings.add("coordination.file_ownership: $w owns no files")

        // roadmap
        val rm = obj.getValue("roadmap")
        val milestones = if ("roadmap" in data) list(rm, "milestones", "roadmap", errors) else emptyList()
        if (milestones.size > MAX_MILESTONES) errors.add("roadmap.milestones: too many (${milestones.size} > $MAX_MILESTONES)")
        val msRefs = ArrayList<String>()
        val versions = ArrayList<List<Int>>()
        milestones.forEachIndexed { i, raw ->
            val p = "roadmap.milestones[$i]"
            val mo = raw as? Map<*, *> ?: run { errors.add("$p: must be an object"); return@forEachIndexed }
            val ref = Json.str(mo["ref"])
            if (!REF.matches(ref)) errors.add("$p.ref: missing or invalid (e.g. m1)")
            else if (ref in msRefs) errors.add("$p.ref: duplicate $ref")
            msRefs.add(ref)
            str(mo, "title", p, errors, limit = 200)
            val ver = Json.str(mo["version"])
            if (!SEMVER.matches(ver)) errors.add("$p.version: ${ver.ifEmpty { "(missing)" }} is not a semantic version like 0.1.0")
            else {
                val nums = Regex("\\d+").findAll(ver.trimStart('v')).take(3).map { it.value.toInt() }.toList()
                if (versions.isNotEmpty() && cmp(nums, versions.last()) <= 0) errors.add("$p.version: $ver does not grow along the roadmap")
                versions.add(nums)
            }
            if (strs(mo["criteria"]).isEmpty()) errors.add("$p.criteria: missing (how the user knows the milestone is reached)")
        }
        sync.forEachIndexed { i, raw ->
            val sp = raw as? Map<*, *> ?: return@forEachIndexed
            val after = sp["after_milestone"]
            if (after != null && after != "" && after !in msRefs)
                errors.add("coordination.sync_points[$i].after_milestone: unknown milestone ${repr(after)}")
            if (Json.str(sp["description"]).isBlank()) errors.add("coordination.sync_points[$i].description: missing")
        }

        // tasks
        val tasks = data["tasks"] as? List<*> ?: emptyList<Any?>()
        if ("tasks" in data && data["tasks"] !is List<*>) errors.add("tasks: must be a list")
        else if ("tasks" in data && tasks.isEmpty()) errors.add("tasks: is empty")
        if (tasks.size > MAX_TASKS) errors.add("tasks: too many (${tasks.size} > $MAX_TASKS); plan the first milestones in detail only")
        val taskRefs = ArrayList<String>()
        tasks.forEachIndexed { i, raw ->
            val t = raw as? Map<*, *> ?: return@forEachIndexed
            val ref = Json.str(t["ref"])
            if (!REF.matches(ref)) errors.add("tasks[$i].ref: missing or invalid (e.g. t1)")
            else if (ref in taskRefs) errors.add("tasks[$i].ref: duplicate $ref")
            taskRefs.add(ref)
        }
        val ownersWithTasks = HashSet<String>()
        tasks.forEachIndexed { i, raw ->
            val p = "tasks[$i]"
            val t = raw as? Map<*, *> ?: run { errors.add("$p: must be an object"); return@forEachIndexed }
            str(t, "title", p, errors, limit = 200)
            str(t, "objective", p, errors)
            val owner = Json.str(t["owner_agent_id"])
            if (owner !in agentRoles) errors.add("$p.owner_agent_id: ${owner.ifEmpty { "(missing)" }} is not in team.agents")
            ownersWithTasks.add(owner)
            val msr = Json.str(t["milestone_ref"])
            if (msr !in msRefs) errors.add("$p.milestone_ref: ${msr.ifEmpty { "(missing)" }} is not a roadmap milestone")
            for (d in strs(t["depends_on_refs"])) {
                if (d !in taskRefs) errors.add("$p.depends_on_refs: unknown task '$d'")
                if (d == t["ref"]) errors.add("$p.depends_on_refs: a task cannot depend on itself")
            }
            if (strs(t["acceptance_criteria"]).isEmpty()) errors.add("$p.acceptance_criteria: missing")
            val inc = strs(m(t["scope"])["include"])
            if (inc.isEmpty()) errors.add("$p.scope.include: missing (which files this task may change)")
            else if (owner in ownership) {
                val outside = inc.filter { !inside(it, ownership.getValue(owner)) }
                if (outside.isNotEmpty()) warnings.add("$p.scope: ${outside.take(3).joinToString(", ")} is outside the files $owner owns")
            }
        }
        milestones.forEachIndexed { i, raw ->
            val mo = raw as? Map<*, *> ?: return@forEachIndexed
            for (r in strs(mo["task_refs"])) if (r !in taskRefs) errors.add("roadmap.milestones[$i].task_refs: unknown task '$r'")
        }
        for (w in workers) if (w !in ownersWithTasks) warnings.add("tasks: $w has no task")
        errors.addAll(cycles(tasks))

        // start prompts
        val sps = data["start_prompts"] as? List<*> ?: emptyList<Any?>()
        if ("start_prompts" in data && data["start_prompts"] !is List<*>) errors.add("start_prompts: must be a list")
        val have = HashSet<String>()
        sps.forEachIndexed { i, raw ->
            val p = "start_prompts[$i]"
            val sp = raw as? Map<*, *> ?: run { errors.add("$p: must be an object"); return@forEachIndexed }
            val aid = Json.str(sp["agent_id"])
            if (aid !in agentRoles) errors.add("$p.agent_id: ${aid.ifEmpty { "(missing)" }} is not in team.agents")
            if (str(sp, "prompt", p, errors, limit = 20000).length < 40 && sp["prompt"] != null && sp["prompt"] != "")
                errors.add("$p.prompt: too short to start a chat on its own (at least 40 characters)")
            have.add(aid)
        }
        for (w in workers) if ("start_prompts" in data && w !in have) errors.add("start_prompts: no start prompt for $w")
        return Validation(errors.distinct(), warnings.distinct())
    }

    private fun cmp(a: List<Int>, b: List<Int>): Int {
        for (i in 0 until maxOf(a.size, b.size)) {
            val x = a.getOrElse(i) { -1 }; val y = b.getOrElse(i) { -1 }
            if (x != y) return x.compareTo(y)
        }
        return 0
    }

    private fun cycles(tasks: List<Any?>): List<String> {
        val graph = LinkedHashMap<String, List<String>>()
        for (raw in tasks) { val t = raw as? Map<*, *> ?: continue; val r = Json.str(t["ref"]); if (r.isNotEmpty()) graph[r] = strs(t["depends_on_refs"]) }
        val seen = HashMap<String, Int>()
        val out = ArrayList<String>()
        fun visit(n: String, path: List<String>) {
            if (seen[n] == 2 || n !in graph) return
            if (seen[n] == 1) { out.add("tasks: dependency cycle " + (path.subList(path.indexOf(n), path.size) + n).joinToString(" → ")); return }
            seen[n] = 1
            for (d in graph.getValue(n)) visit(d, path + n)
            seen[n] = 2
        }
        for (n in graph.keys) visit(n, emptyList())
        return out.take(1)
    }

    /** Never throws for bad model output. */
    fun parse(text: String?, state: Obj? = null): Result {
        val (data, errors, fixes) = load(text)
        if (data == null) return Result(false, null, errors, emptyList(), fixes)
        val v = validate(data, state)
        return Result(v.errors.isEmpty(), data, v.errors, v.warnings, fixes)
    }

    fun fixPrompt(r: Result): String {
        val lines = mutableListOf("# AI Workbench — please fix your Project Charter",
            "Workbench could not accept your charter; nothing was applied. Fix every point below and return the " +
                "COMPLETE corrected charter as one <<<AIWB_PROJECT_CHARTER>>> … <<<AIWB_END_PROJECT_CHARTER>>> block " +
                "(same format, valid JSON, every section present).", "", "## Problems found by Workbench")
        lines += r.errors.map { "- $it" }.ifEmpty { listOf("- (none)") }
        if (r.warnings.isNotEmpty()) lines += listOf("", "## Also worth fixing") + r.warnings.map { "- $it" }
        if (r.errors.any { "cut off" in it || "not closed" in it })
            lines += listOf("", "Your previous answer was cut off. If it is long, shorten the start prompts and plan only the first " +
                "milestones in detail.")
        return lines.joinToString("\n")
    }

    // --------------------------------------------------------------- conversion

    /** A *valid* charter → manager proposal data (reviewed per operation; nothing applied here). */
    fun toProposal(data: Map<String, Any?>, state: Obj): Obj {
        val v = validate(data, state)
        if (v.errors.isNotEmpty()) throw ModelError("the charter is incomplete: " + v.errors.take(5).joinToString("; "))
        val team = m(data["team"])
        val agents = (team["agents"] as List<*>).map { m(it) }
        val tasks = (data["tasks"] as List<*>).map { m(it) }
        val stAgents = State.coll(state, "agents")
        val ops = ArrayList<Any?>()
        for (a in agents) {
            if (a["agent_id"] in stAgents) continue
            ops.add(linkedMapOf("operation" to "create_agent", "agent_id" to a["agent_id"], "role" to a["role"],
                "name" to (Json.str(a["name"]).ifEmpty { Json.str(a["agent_id"]) }), "purpose" to Json.str(a["purpose"]),
                "reason" to "Project Charter team"))
        }
        for (t in tasks) {
            val scope = m(t["scope"])
            val op: Obj = linkedMapOf("operation" to "create_task", "temporary_ref" to t["ref"], "title" to t["title"],
                "objective" to t["objective"], "owner_agent_id" to t["owner_agent_id"],
                "depends_on_refs" to ArrayList<Any?>(strs(t["depends_on_refs"])),
                "scope" to linkedMapOf<String, Any?>("include" to ArrayList<Any?>(strs(scope["include"])),
                    "exclude" to ArrayList<Any?>(strs(scope["exclude"]))),
                "acceptance_criteria" to ArrayList<Any?>(strs(t["acceptance_criteria"])),
                "reason" to "Charter milestone ${t["milestone_ref"]}")
            for (k in listOf("parallel_group", "priority", "reviewer_agent_id", "risk_level"))
                if (t[k] != null && t[k] != "" && t[k] != false) op[k] = t[k]
            ops.add(op)
        }
        for (mo in (m(data["roadmap"])["milestones"] as List<*>).map { m(it) }) {
            val refs = strs(mo["task_refs"]).ifEmpty { tasks.filter { it["milestone_ref"] == mo["ref"] }.map { Json.str(it["ref"]) } }
            ops.add(linkedMapOf("operation" to "create_milestone", "temporary_ref" to "ms:" + Json.str(mo["ref"]),
                "title" to mo["title"], "version" to mo["version"], "criteria" to ArrayList<Any?>(strs(mo["criteria"])),
                "task_refs" to ArrayList<Any?>(refs), "reason" to "Charter roadmap ${mo["ref"]} → ${mo["version"]}"))
        }
        for (r in (data["risks"] as? List<*>).orEmpty())
            if (r is String && r.isNotBlank()) ops.add(linkedMapOf("operation" to "report_risk", "description" to r.trim().take(500)))
        val workers = agents.count { it["role"] != "project_manager" }
        return linkedMapOf("schema_version" to "1.0", "proposal_type" to "team_plan",
            "base_state_revision" to data["base_state_revision"],
            "summary" to (Json.str(m(data["project"])["summary"]).ifEmpty { Json.str(m(data["architecture"])["summary"]) }),
            "assumptions" to ArrayList<Any?>(), "risks" to ArrayList<Any?>(strs(data["risks"])),
            "questions_for_user" to ArrayList<Any?>(strs(data["questions_for_user"])),
            "team" to linkedMapOf<String, Any?>("pm_counted" to team["pm_counted"], "total_agents" to team["total_agents"],
                "additional_workers" to workers.toLong(), "size_rationale" to Json.str(team["rationale"]),
                "simpler_alternative" to Json.str(team["simpler_alternative"])),
            "operations" to ops)
    }

    /** What is kept in `settings.charter` once the user accepted the charter. */
    fun record(data: Map<String, Any?>): Obj {
        val team = m(data["team"])
        val prompts = LinkedHashMap<String, Any?>()
        for (sp in (data["start_prompts"] as? List<*>).orEmpty()) { val s = sp as? Map<*, *> ?: continue; prompts[Json.str(s["agent_id"])] = s["prompt"] }
        return linkedMapOf("schema_version" to "1.0", "project" to StrictJson.copy(data["project"] ?: linkedMapOf<String, Any?>()),
            "architecture" to StrictJson.copy(data["architecture"]),
            "team" to linkedMapOf<String, Any?>().also { t ->
                for (k in listOf("pm_counted", "total_agents", "parallel_chats", "rationale", "simpler_alternative", "agents")) t[k] = StrictJson.copy(team[k])
            },
            "coordination" to StrictJson.copy(data["coordination"]), "roadmap" to StrictJson.copy(data["roadmap"]),
            "start_prompts" to prompts, "risks" to ArrayList<Any?>(strs(data["risks"])),
            "questions_for_user" to ArrayList<Any?>(strs(data["questions_for_user"])))
    }

    /** The start prompt of one AI, framed with its ownership, contracts and sync points. */
    fun startPrompt(charter: Map<String, Any?>, agentId: String, taskLines: List<String> = emptyList()): String {
        val prompt = Json.str(m(charter["start_prompts"])[agentId])
        if (prompt.isEmpty()) throw ModelError("the charter has no start prompt for $agentId")
        val co = m(charter["coordination"])
        val own = (co["file_ownership"] as? List<*>).orEmpty().map { m(it) }.filter { it["agent_id"] == agentId }.flatMap { strs(it["paths"]) }
        val contracts = (co["shared_contracts"] as? List<*>).orEmpty().map { m(it) }
            .filter { it["owner_agent_id"] == agentId || agentId in strs(it["consumers"]) }
        val lines = mutableListOf("# AI Workbench — start prompt for $agentId",
            "You have NO access to earlier chats, the project files or other AIs; everything you need is below.", "",
            prompt.trim(), "", "## Coordination rules (from the Project Charter)",
            "- You may change only: " + own.joinToString(", ").ifEmpty { "(no files — ask the project manager)" })
        for (c in contracts) {
            val role = if (c["owner_agent_id"] == agentId) "you own it" else "owned by ${c["owner_agent_id"]}; do not change it"
            lines.add("- Shared contract ${c["name"]} (${Json.str(c["path"])}): $role")
        }
        for (sp in (co["sync_points"] as? List<*>).orEmpty().map { m(it) })
            lines.add("- Sync point after ${Json.str(sp["after_milestone"]).ifEmpty { "?" }}: ${Json.str(sp["description"])}")
        if (Json.str(co["conflict_resolution"]).isNotEmpty()) lines.add("- Conflicts: ${co["conflict_resolution"]}")
        if (taskLines.isNotEmpty()) lines += listOf("", "## Your tasks") + taskLines.map { "- $it" }
        return lines.joinToString("\n")
    }
}
