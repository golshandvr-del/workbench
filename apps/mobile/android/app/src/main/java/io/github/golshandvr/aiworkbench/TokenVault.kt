package io.github.golshandvr.aiworkbench

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * GitHub token on the phone (roadmap 4.5.0 / mobile 1.6.0): AES-256-GCM with a non-exportable key in the
 * Android Keystore. Only the ciphertext is kept in private SharedPreferences; the token is never logged,
 * exported in bundles or shown again. Without a token every GitHub step stays manual.
 */
class TokenVault(context: Context) {
    private val prefs = context.getSharedPreferences("aiwb_github", Context.MODE_PRIVATE)

    private fun key(): SecretKey {
        val ks = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        gen.init(KeyGenParameterSpec.Builder(ALIAS, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256).build())
        return gen.generateKey()
    }

    fun has(): Boolean = prefs.contains(PREF)

    fun save(token: String) {
        val t = token.trim()
        require(t.isNotEmpty()) { "empty token" }
        val c = Cipher.getInstance(TRANSFORM).apply { init(Cipher.ENCRYPT_MODE, key()) }
        val blob = c.iv + c.doFinal(t.toByteArray(Charsets.UTF_8))
        prefs.edit().putString(PREF, Base64.encodeToString(blob, Base64.NO_WRAP)).apply()
    }

    fun load(): String? {
        val b64 = prefs.getString(PREF, null) ?: return null
        return try {
            val blob = Base64.decode(b64, Base64.NO_WRAP)
            val c = Cipher.getInstance(TRANSFORM).apply { init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, blob, 0, 12)) }
            String(c.doFinal(blob, 12, blob.size - 12), Charsets.UTF_8)
        } catch (_: Exception) {
            null // key invalidated (e.g. device reset): the user enters the token again
        }
    }

    fun clear() = prefs.edit().remove(PREF).apply()

    companion object {
        private const val ALIAS = "aiwb-github-token"
        private const val PREF = "token_v1"
        private const val TRANSFORM = "AES/GCM/NoPadding"
    }
}
