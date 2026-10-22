package io.github.golshandvr.aiworkbench

import io.github.golshandvr.aiworkbench.core.Json
import io.github.golshandvr.aiworkbench.core.MissionModel
import io.github.golshandvr.aiworkbench.core.StrictJson
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File

/**
 * Roadmap 6.1.0 / mobile 3.1.0 gate: the phone's Mission Map is the desktop's Mission Map.
 *
 * `packages/contracts/fixtures/mission/mission-map.v1.json` holds V2 states, view options and the map the desktop
 * `mission_model.build` returns (written by `tools/gen_mission_fixture.py`, kept fresh by desktop
 * `test_mission_fixture`). [MissionModel.build] must return exactly the same data for every case.
 */
class MissionModelTest {
    private fun fixture(): Map<*, *> {
        var dir: File? = File("").absoluteFile
        val rel = "packages/contracts/fixtures/mission/mission-map.v1.json"
        while (dir != null && !File(dir, rel).isFile) dir = dir.parentFile
        return Json.parseObj(File(requireNotNull(dir) { "fixture not found" }, rel).readText())
    }

    private fun cases() = Json.list(fixture()["cases"]).map { Json.obj(it) }

    @Test fun everyFixtureCaseEqualsTheDesktop() {
        val cases = cases()
        assertTrue("fixture has cases", cases.size >= 10)
        for (c in cases) {
            val o = Json.obj(c["options"])
            val have = MissionModel.build(Json.obj(c["state"]), hideDone = o["hide_done"] == true, openOnly = o["open_only"] == true)
            assertEquals(Json.str(c["name"]), StrictJson.stringify(c["expect"], sortKeys = true),
                StrictJson.stringify(have, sortKeys = true))
        }
    }

    @Test fun readingTheStateNeverWritesIt() {
        for (c in cases()) {
            val st = Json.obj(c["state"])
            val before = StrictJson.stringify(st, sortKeys = true)
            MissionModel.build(st, hideDone = true, openOnly = true)
            assertEquals(Json.str(c["name"]), before, StrictJson.stringify(st, sortKeys = true))
        }
    }

    @Test fun nodeStates() {
        assertEquals("done", MissionModel.nodeState(mapOf("status" to "done"), handoffOpen = true))
        assertEquals("blocked", MissionModel.nodeState(mapOf("status" to "blocked")))
        assertEquals("attention", MissionModel.nodeState(mapOf("status" to "needs_decision")))
        for (st in listOf("ready", "in_progress", "in_review", "validation_pending"))
            assertEquals(st, "active", MissionModel.nodeState(mapOf("status" to st)))
        assertEquals("idle", MissionModel.nodeState(mapOf("status" to "draft")))
        assertEquals("active", MissionModel.nodeState(mapOf("status" to "draft"), handoffOpen = true))
    }

    @Test fun layoutPlacesEveryNodeOnItsLaneAndColumn() {
        val c = cases().first { it["name"] == "five_ai_semver" }
        val m = MissionModel.build(Json.obj(c["state"]))
        val l = MissionModel.layout(m, 2f)
        val lanes = Json.list(m["lanes"]).map { Json.obj(it) }
        assertEquals(lanes.size, l.laneY.size)
        assertEquals(Json.list(m["slots"]).size, l.colX.size)
        assertEquals(20, l.nodes.size)
        lanes.forEachIndexed { i, lane ->
            for (nd in Json.list(lane["nodes"]).map { Json.obj(it) }) {
                val (x, y) = l.nodes.getValue(Json.str(nd["task_id"]))
                assertEquals(l.laneY[i], y, 0.001f)
                assertEquals(l.colX[Json.int(nd["column"])] + Json.int(nd["slot"]) * 66 * 2f, x, 0.001f)
            }
        }
        assertTrue(l.colX.zipWithNext().all { (a, b) -> b > a })
        assertTrue(l.width > l.endX && l.height > l.laneY.last())
        val empty = MissionModel.layout(MissionModel.build(null))
        assertEquals(1, empty.laneY.size)
        assertTrue(empty.nodes.isEmpty())
    }
}
