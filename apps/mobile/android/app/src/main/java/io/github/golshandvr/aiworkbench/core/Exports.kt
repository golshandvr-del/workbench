package io.github.golshandvr.aiworkbench.core

import java.io.File

/**
 * Builds the bytes of a user-chosen export (bundle / files ZIP) from the project id at the moment the system file
 * picker returns (BF-074). Nothing is kept in an Activity field while the picker is open: Android may recreate or
 * kill the screen in the meantime, and an export built beforehand would be lost, leaving an empty chosen file.
 */
object Exports {
    /** The stored project with this id, or null (empty/unsafe id, or no such project). */
    fun project(projectsDir: File, id: String?): Project? {
        if (id.isNullOrEmpty() || id != File(id).name || id == "." || id == "..") return null
        val dir = File(projectsDir, id)
        if (!File(dir, "state.json").isFile) return null
        return Project(ProjectStore(dir, id))
    }

    fun bundleBytes(projectsDir: File, id: String?, version: String): ByteArray? =
        project(projectsDir, id)?.let { ProjectBundle.dumps(ProjectBundle.export(it.state(), it.store.projectId, version = version)).toByteArray(Charsets.UTF_8) }

    fun zipBytes(projectsDir: File, id: String?): ByteArray? = project(projectsDir, id)?.let { Files.zip(it.store) }
}
