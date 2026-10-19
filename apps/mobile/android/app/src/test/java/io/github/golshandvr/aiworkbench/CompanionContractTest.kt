package io.github.golshandvr.aiworkbench

import org.json.JSONObject
import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Assert.fail
import org.junit.Test
import java.io.File

/** Kotlin side of the companion contract: shared vectors + client protocol against a simulated desktop. */
class CompanionContractTest {
    private fun vectors(): JSONObject {
        var dir: File? = File("").absoluteFile
        while (dir != null && !File(dir, "packages/contracts").isDirectory) dir = dir.parentFile
        return JSONObject(File(requireNotNull(dir), "packages/contracts/vectors/companion-envelope.v1.json").readText())
    }

    @Test fun sharedVectorsMatchByteForByte() {
        val cases = vectors().getJSONArray("cases")
        assertTrue(cases.length() >= 2)
        for (i in 0 until cases.length()) {
            val c = cases.getJSONObject(i)
            val master = B64Url.decode(c.getString("master_key_b64url"))
            val expected = CompanionClient.fromJson(c.getJSONObject("envelope"))
            val sealed = CompanionCrypto.seal(master, expected.kid, c.getString("plaintext").toByteArray(Charsets.UTF_8),
                expected.ts, B64Url.decode(expected.nonce), expected.re)
            assertEquals(expected, sealed)
            assertEquals(c.getString("plaintext"), String(CompanionCrypto.open(master, expected, expected.ts), Charsets.UTF_8))
        }
    }

    @Test fun tamperedOrOldMessagesRejected() {
        val k = CompanionCrypto.randomBytes(32)
        val e = CompanionCrypto.seal(k, "dev-x", "{}".toByteArray(), 1000)
        for (bad in listOf(e.copy(kid = "dev-y"), e.copy(ts = 1001), e.copy(re = "x"))) {
            try { CompanionCrypto.open(k, bad, 1000); fail("accepted $bad") } catch (_: EnvelopeException) {}
        }
        try { CompanionCrypto.open(k, e, 1301); fail("too old accepted") } catch (_: EnvelopeException) {}
        try { CompanionCrypto.open(CompanionCrypto.randomBytes(32), e, 1000); fail("wrong key accepted") } catch (_: EnvelopeException) {}
    }

    @Test fun base64UrlRoundTrip() {
        for (n in 0..40) {
            val b = CompanionCrypto.randomBytes(n)
            assertArrayEquals(b, B64Url.decode(B64Url.encode(b)))
        }
        assertEquals("AAECAwQFBgcICQoLDA0ODw", B64Url.encode(ByteArray(16) { it.toByte() }))
    }

    @Test fun pairingCodeOnlyForLocalNetwork() {
        val s = B64Url.encode(ByteArray(32))
        val k = "AAISEM2EKVTHPCEZ"
        assertNotNull(PairingCode.parse("aiwb://pair?h=192.168.1.20&p=47821&k=$k"))
        assertNotNull(PairingCode.parse("aiwb://pair?h=10.0.0.5&p=47821&k=$k"))
        assertNotNull(PairingCode.parse("aiwb://pair?h=172.20.1.1&p=1&k=$k"))
        assertNull(PairingCode.parse("aiwb://pair?h=8.8.8.8&p=47821&k=$k"), "public IP refused")
        assertNull(PairingCode.parse("aiwb1:192.168.1.20:47821:pair-0123456789ab:$s"), "v1 codes are no longer accepted")
        assertNotNull(PairingCode.manual("192.168.1.20:47821", "aais-em2e-kvth-pcez"))
        assertNull(PairingCode.manual("192.168.1.20", "AAIS-EM2E-KVTH-PCEZ"), "port required")
        val p = Pairing("192.168.1.20", 47821, "dev-abc", ByteArray(32) { 7 })
        assertEquals(p.deviceId, Pairing.decode(p.encode())!!.deviceId)
        assertNull(Pairing.decode("{\"host\":\"1.2.3.4\",\"port\":1,\"device_id\":\"d\",\"key\":\"$s\"}"))
    }

    private fun assertNull(v: Any?, msg: String = "") = org.junit.Assert.assertNull(msg, v)

    /** Simulated desktop implementing the same rules as aiwb/companion/service.py. */
    private class FakeDesktop(val code: PairingCode) {
        var deviceKey: ByteArray? = null
        var approved = false
        val tasks = mutableListOf<String>()
        val seen = HashSet<String>()

        fun handle(body: String): Pair<Int, String> {
            val env = CompanionClient.fromJson(JSONObject(body))
            if (!seen.add(env.kid + env.nonce)) return 401 to "{\"error\":\"unauthenticated\"}"
            val key = if (env.kid == code.pairingId) code.secret else if (approved && env.kid == "dev-1") deviceKey!! else
                return 403 to "{\"error\":\"device_not_paired\"}"
            val req = JSONObject(String(CompanionCrypto.open(key, env, env.ts), Charsets.UTF_8))
            val out = when (req.getString("op")) {
                "pair_request" -> { deviceKey = B64Url.decode(req.getString("device_key")); JSONObject().put("ok", true).put("status", "pending") }
                "pair_status" -> if (approved) JSONObject().put("ok", true).put("status", "approved").put("device_id", "dev-1")
                                 else JSONObject().put("ok", true).put("status", "pending")
                "create_task" -> { tasks += req.getString("title"); JSONObject().put("ok", true).put("task_id", "TASK-000${tasks.size}") }
                "get_state" -> JSONObject().put("ok", true).put("next_action", "Start the next task")
                    .put("snapshot", JSONObject().put("project_id", "demo").put("state_revision", 4)
                        .put("summary", JSONObject().put("total_tasks", tasks.size).put("verified_complete", 0).put("blocked_tasks", 0)))
                    .put("tasks", org.json.JSONArray(tasks.mapIndexed { i, t -> JSONObject().put("task_id", "TASK-000${i + 1}").put("title", t).put("status_text", "Not planned yet") }))
                    .put("builds", org.json.JSONArray().put(JSONObject().put("run_id", 77).put("outcome", "success").put("commit_sha", "f".repeat(40))))
                "submit_response" -> JSONObject().put("ok", false).put("error", "forbidden").put("message", "not allowed to submit response")
                else -> JSONObject().put("ok", false).put("error", "bad_op")
            }
            val reply = CompanionCrypto.seal(key, env.kid, out.toString().toByteArray(Charsets.UTF_8), env.ts, re = env.nonce)
            return 200 to CompanionClient.toJson(reply).toString()
        }
    }

    @Test fun fullFlowPairApproveViewCreateAndRefusals() {
        val code = PairingCode.fromSecret("192.168.1.20", 47821, CompanionCrypto.randomBytes(10))
        val desk = FakeDesktop(code)
        val client = CompanionClient({ _, _, body -> desk.handle(body) }, now = { 1_792_300_000L })
        val dk = CompanionCrypto.randomBytes(32)
        assertEquals("pending", client.requestPairing(code, "Pixel", dk).getString("status"))
        assertNull(client.pairingStatus(code, dk))
        desk.approved = true
        val p = client.pairingStatus(code, dk)!!
        assertEquals("dev-1", p.deviceId)
        assertEquals("TASK-0001", client.request(p, "create_task", JSONObject().put("title", "From phone").put("objective", "o")).getString("task_id"))
        val view = CompanionView.summary(client.request(p, "get_state"))
        assertTrue(view, view.contains("From phone") && view.contains("build 77 success") && view.contains("demo · rev 4"))
        try { client.request(p, "submit_response", JSONObject().put("text", "x")); fail() } catch (e: CompanionException) { assertEquals("forbidden", e.code) }
        desk.approved = false
        try { client.request(p, "get_state"); fail() } catch (e: CompanionException) { assertEquals("device_not_paired", e.code) }
    }

    @Test fun replyForAnotherRequestIsRejected() {
        val k = CompanionCrypto.randomBytes(32)
        val client = CompanionClient({ _, _, _ ->
            200 to CompanionClient.toJson(CompanionCrypto.seal(k, "dev-1", "{\"ok\":true}".toByteArray(), 5, re = "other")).toString()
        }, now = { 5L })
        try { client.call("192.168.1.2", 1, "dev-1", k, JSONObject().put("op", "hello")); fail() } catch (e: CompanionException) { assertEquals("bad_reply", e.code) }
    }
}
