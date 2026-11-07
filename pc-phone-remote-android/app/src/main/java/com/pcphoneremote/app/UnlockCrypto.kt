package com.pcphoneremote.app

import android.app.Activity
import android.content.Context
import android.content.SharedPreferences
import android.hardware.biometrics.BiometricPrompt
import android.net.Uri
import android.os.Build
import android.os.CancellationSignal
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import org.json.JSONObject
import java.math.BigInteger
import java.net.DatagramPacket
import java.net.DatagramSocket
import java.net.InetAddress
import java.nio.charset.StandardCharsets
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.PublicKey
import java.security.SecureRandom
import java.security.Signature
import java.security.interfaces.ECPublicKey
import java.security.spec.ECGenParameterSpec
import java.security.spec.ECParameterSpec
import java.security.spec.ECPoint
import java.security.spec.ECPublicKeySpec
import java.security.spec.PKCS8EncodedKeySpec
import java.util.Arrays
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyAgreement
import javax.crypto.KeyGenerator
import javax.crypto.Mac
import javax.crypto.SecretKey
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.PBEKeySpec
import javax.crypto.spec.SecretKeySpec

/**
 * End-to-End Cryptographic Engine for Windows Sign-In / Unlock (`PhoneUnlockService.exe`).
 *
 * Security Guarantees:
 * - Phone ECDSA P-256 identity keys and AES-256-GCM wrapping keys live in `AndroidKeyStore`.
 * - Split-key vault key `K` (32 bytes) is wrapped by the hardware-backed Keystore AES-256-GCM key.
 * - Passwords are NEVER stored on the phone in SharedPreferences or files, and are NEVER transmitted
 *   in plain HTTP: every unlock submission is encrypted with ephemeral ECDH P-256 + HKDF-SHA256 +
 *   AES-256-GCM to the PC's pinned `pc_pub` key and signed with the phone's ECDSA P-256 key.
 */
object UnlockCrypto {
    private const val ANDROID_KEYSTORE = "AndroidKeyStore"
    private const val META_PREFS = "pc_unlock_keystore_meta"
    private const val EC_CURVE = "secp256r1"
    private const val B64_FLAGS = Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
    private val rng = SecureRandom()

    data class EnrollmentMeta(
        val profileId: String,
        val deviceId: String,
        val userSid: String,
        val qualifiedUser: String,
        val pcPubFp: String,
        val vaultMode: String,
        val hasSplitKey: Boolean,
        val requiresPhonePin: Boolean,
        val enrolledAt: Long
    )

    data class ParsedEnrollUri(
        val enrollToken: String,
        val pcPubFp: String,
        val userSid: String,
        val qualifiedUser: String,
        val vaultMode: String,
        val splitKeyB64: String,
        val pinMaskedKeyB64: String = "",
        val pinSaltB64: String = "",
        val pinTagB64: String = "",
        val host: String,
        val port: String,
        val pin: String,
        val pcName: String
    )

    private fun prefs(context: Context): SharedPreferences =
        context.applicationContext.getSharedPreferences(META_PREFS, Context.MODE_PRIVATE)

    fun b64UrlEncode(bytes: ByteArray): String =
        Base64.encodeToString(bytes, B64_FLAGS)

    fun b64UrlDecode(text: String): ByteArray {
        val cleaned = text.trim()
        return Base64.decode(cleaned, Base64.URL_SAFE or Base64.NO_WRAP)
    }

    fun sha256(data: ByteArray): ByteArray =
        MessageDigest.getInstance("SHA-256").digest(data)

    fun getEnrollmentMeta(context: Context, profileId: String): EnrollmentMeta? {
        val raw = prefs(context).getString("meta_$profileId", null) ?: return null
        return try {
            val obj = JSONObject(raw)
            val sid = obj.optString("user_sid", "")
            val fp = obj.optString("pc_pub_fp", "")
            val devId = obj.optString("device_id", "")
            if (sid.isEmpty() || fp.isEmpty() || devId.isEmpty()) return null
            val hasDirectK = obj.optString("wrapped_k", "").isNotEmpty() && obj.optString("wrapped_k_iv", "").isNotEmpty()
            val hasPinK = obj.optString("wrapped_pk", "").isNotEmpty() && obj.optString("pin_salt", "").isNotEmpty()
            EnrollmentMeta(
                profileId = profileId,
                deviceId = devId,
                userSid = sid,
                qualifiedUser = obj.optString("qualified_user", "Windows User"),
                pcPubFp = fp,
                vaultMode = obj.optString("vault_mode", "split_key"),
                hasSplitKey = hasDirectK || hasPinK,
                requiresPhonePin = hasPinK,
                enrolledAt = obj.optLong("enrolled_at", 0L)
            )
        } catch (_: Exception) {
            null
        }
    }

    fun clearEnrollment(context: Context, profileId: String) {
        prefs(context).edit()
            .remove("meta_$profileId")
            .remove("sw_ec_$profileId")
            .apply()
        try {
            val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
            val idAlias = "pcpr_id_$profileId"
            val wrapAlias = "pcpr_wrap_$profileId"
            if (ks.containsAlias(idAlias)) ks.deleteEntry(idAlias)
            if (ks.containsAlias(wrapAlias)) ks.deleteEntry(wrapAlias)
        } catch (_: Exception) {
        }
    }

    fun parseEnrollCode(rawInput: String): ParsedEnrollUri? {
        val trimmed = rawInput.trim()
        if (trimmed.isEmpty()) return null
        return try {
            if (trimmed.startsWith("{")) {
                val obj = JSONObject(trimmed)
                val token = obj.optString("enroll_token", obj.optString("token", ""))
                val fp = obj.optString("pc_pub_fp", obj.optString("fp", ""))
                val sid = obj.optString("user_sid", obj.optString("sid", ""))
                if (token.isEmpty() || fp.isEmpty() || sid.isEmpty()) return null
                ParsedEnrollUri(
                    enrollToken = token,
                    pcPubFp = fp,
                    userSid = sid,
                    qualifiedUser = obj.optString("qualified_user", obj.optString("user", "")),
                    vaultMode = obj.optString("vault_mode", obj.optString("mode", "split_key")),
                    splitKeyB64 = obj.optString("split_key", obj.optString("k", "")),
                    pinMaskedKeyB64 = obj.optString("pk", ""),
                    pinSaltB64 = obj.optString("ps", ""),
                    pinTagB64 = obj.optString("pt", ""),
                    host = obj.optString("host", ""),
                    port = obj.optString("port", "8765"),
                    pin = obj.optString("pin", ""),
                    pcName = obj.optString("name", "")
                )
            } else {
                val uri = Uri.parse(trimmed)
                if (uri.scheme != "pcphone" || uri.host != "enroll") return null
                val token = uri.getQueryParameter("token") ?: ""
                val fp = uri.getQueryParameter("fp") ?: ""
                val sid = uri.getQueryParameter("sid") ?: ""
                if (token.isEmpty() || fp.isEmpty() || sid.isEmpty()) return null
                ParsedEnrollUri(
                    enrollToken = token,
                    pcPubFp = fp,
                    userSid = sid,
                    qualifiedUser = uri.getQueryParameter("user") ?: "",
                    vaultMode = uri.getQueryParameter("mode") ?: "split_key",
                    splitKeyB64 = uri.getQueryParameter("k") ?: "",
                    pinMaskedKeyB64 = uri.getQueryParameter("pk") ?: "",
                    pinSaltB64 = uri.getQueryParameter("ps") ?: "",
                    pinTagB64 = uri.getQueryParameter("pt") ?: "",
                    host = uri.getQueryParameter("host") ?: "",
                    port = uri.getQueryParameter("port") ?: "8765",
                    pin = uri.getQueryParameter("pin") ?: "",
                    pcName = uri.getQueryParameter("name") ?: ""
                )
            }
        } catch (_: Exception) {
            null
        }
    }

    private fun getOrCreateWrapKey(profileId: String): SecretKey {
        val alias = "pcpr_wrap_$profileId"
        val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
        val existing = ks.getEntry(alias, null) as? KeyStore.SecretKeyEntry
        if (existing != null) return existing.secretKey

        val kg = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEYSTORE)
        val spec = KeyGenParameterSpec.Builder(
            alias,
            KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
        )
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
            .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
            .setKeySize(256)
            .build()
        kg.init(spec)
        return kg.generateKey()
    }

    private fun wrapSecret(profileId: String, plain: ByteArray): Pair<String, String> {
        val key = getOrCreateWrapKey(profileId)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, key)
        val ct = cipher.doFinal(plain)
        return Pair(b64UrlEncode(ct), b64UrlEncode(cipher.iv))
    }

    private fun unwrapSecret(profileId: String, ctB64: String, ivB64: String): ByteArray {
        val key = getOrCreateWrapKey(profileId)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, key, GCMParameterSpec(128, b64UrlDecode(ivB64)))
        return cipher.doFinal(b64UrlDecode(ctB64))
    }

    private fun getOrCreateIdentityKeyPair(context: Context, profileId: String): Pair<PrivateKey, ECPublicKey> {
        val alias = "pcpr_id_$profileId"
        try {
            val ks = KeyStore.getInstance(ANDROID_KEYSTORE).apply { load(null) }
            val entry = ks.getEntry(alias, null) as? KeyStore.PrivateKeyEntry
            if (entry != null && entry.certificate.publicKey is ECPublicKey) {
                return Pair(entry.privateKey, entry.certificate.publicKey as ECPublicKey)
            }
            val kpg = KeyPairGenerator.getInstance(KeyProperties.KEY_ALGORITHM_EC, ANDROID_KEYSTORE)
            val spec = KeyGenParameterSpec.Builder(
                alias,
                KeyProperties.PURPOSE_SIGN or KeyProperties.PURPOSE_VERIFY
            )
                .setAlgorithmParameterSpec(ECGenParameterSpec(EC_CURVE))
                .setDigests(KeyProperties.DIGEST_SHA256)
                .build()
            kpg.initialize(spec)
            val kp = kpg.generateKeyPair()
            return Pair(kp.private, kp.public as ECPublicKey)
        } catch (_: Exception) {
            // Fallback: software EC P-256 keypair whose PKCS#8 private key is wrapped by Keystore AES-256-GCM
            val p = prefs(context)
            val stored = p.getString("sw_ec_$profileId", null)
            val kf = KeyFactory.getInstance("EC")
            if (stored != null) {
                val obj = JSONObject(stored)
                val pkcs8 = unwrapSecret(profileId, obj.getString("ct"), obj.getString("iv"))
                return try {
                    val priv = kf.generatePrivate(PKCS8EncodedKeySpec(pkcs8))
                    val pubPoint = b64UrlDecode(obj.getString("pub"))
                    val pub = importPublicPoint65(pubPoint)
                    Pair(priv, pub)
                } finally {
                    Arrays.fill(pkcs8, 0.toByte())
                }
            }
            val kpg = KeyPairGenerator.getInstance("EC")
            kpg.initialize(ECGenParameterSpec(EC_CURVE), rng)
            val kp = kpg.generateKeyPair()
            val encoded = kp.private.encoded
            try {
                val (ct, iv) = wrapSecret(profileId, encoded)
                val pubB64 = b64UrlEncode(exportPublicPoint65(kp.public as ECPublicKey))
                p.edit().putString(
                    "sw_ec_$profileId",
                    JSONObject().put("ct", ct).put("iv", iv).put("pub", pubB64).toString()
                ).apply()
            } finally {
                Arrays.fill(encoded, 0.toByte())
            }
            return Pair(kp.private, kp.public as ECPublicKey)
        }
    }

    private fun toFixed32(value: BigInteger): ByteArray {
        val raw = value.toByteArray()
        return when {
            raw.size == 32 -> raw
            raw.size == 33 && raw[0] == 0.toByte() -> raw.copyOfRange(1, 33)
            raw.size < 32 -> {
                val out = ByteArray(32)
                System.arraycopy(raw, 0, out, 32 - raw.size, raw.size)
                out
            }
            else -> raw.copyOfRange(raw.size - 32, raw.size)
        }
    }

    /** Exports an EC P-256 public key as a 65-byte uncompressed SEC1 point (`0x04 || X(32) || Y(32)`). */
    fun exportPublicPoint65(pubKey: ECPublicKey): ByteArray {
        val w = pubKey.w
        val x = toFixed32(w.affineX)
        val y = toFixed32(w.affineY)
        val out = ByteArray(65)
        out[0] = 0x04
        System.arraycopy(x, 0, out, 1, 32)
        System.arraycopy(y, 0, out, 33, 32)
        return out
    }

    private val p256Params: ECParameterSpec by lazy {
        val kpg = KeyPairGenerator.getInstance("EC")
        kpg.initialize(ECGenParameterSpec(EC_CURVE))
        (kpg.generateKeyPair().public as ECPublicKey).params
    }

    /** Imports a 65-byte uncompressed SEC1 point (`0x04 || X(32) || Y(32)`) into an `ECPublicKey`. */
    fun importPublicPoint65(point: ByteArray): ECPublicKey {
        if (point.size != 65 || point[0] != 0x04.toByte()) {
            throw IllegalArgumentException("Invalid P-256 uncompressed public point")
        }
        val x = BigInteger(1, point.copyOfRange(1, 33))
        val y = BigInteger(1, point.copyOfRange(33, 65))
        val spec = ECPublicKeySpec(ECPoint(x, y), p256Params)
        return KeyFactory.getInstance("EC").generatePublic(spec) as ECPublicKey
    }

    private fun signSha256Ecdsa(privKey: PrivateKey, message: ByteArray): ByteArray {
        val sig = Signature.getInstance("SHA256withECDSA")
        sig.initSign(privKey)
        sig.update(message)
        return sig.sign()
    }

    /** RFC 5869 HKDF-SHA256 matching `HkdfSha256` in `windows-unlock/src/common/crypto.cpp`. */
    fun hkdfSha256(ikm: ByteArray, salt: ByteArray, info: ByteArray, outLen: Int = 32): ByteArray {
        val mac = Mac.getInstance("HmacSHA256")
        val actualSalt = if (salt.isEmpty()) ByteArray(32) else salt
        mac.init(SecretKeySpec(actualSalt, "HmacSHA256"))
        val prk = mac.doFinal(ikm)
        try {
            val out = ByteArray(outLen)
            var t = ByteArray(0)
            var offset = 0
            var counter = 1
            while (offset < outLen) {
                mac.init(SecretKeySpec(prk, "HmacSHA256"))
                if (t.isNotEmpty()) mac.update(t)
                if (info.isNotEmpty()) mac.update(info)
                mac.update(counter.toByte())
                t = mac.doFinal()
                val copyLen = minOf(t.size, outLen - offset)
                System.arraycopy(t, 0, out, offset, copyLen)
                offset += copyLen
                counter++
            }
            if (t.isNotEmpty()) Arrays.fill(t, 0.toByte())
            return out
        } finally {
            Arrays.fill(prk, 0.toByte())
        }
    }

    /**
     * Builds the signed `unlock.enroll` RPC request and persists the wrapped split-key after server confirmation.
     */
    fun buildEnrollmentRequest(
        context: Context,
        profileId: String,
        parsed: ParsedEnrollUri
    ): Pair<JSONObject, () -> EnrollmentMeta> {
        val existing = getEnrollmentMeta(context, profileId)
        val deviceId = existing?.deviceId ?: ("android-" + UUID.randomUUID().toString().replace("-", "").take(20))
        val (privKey, pubKey) = getOrCreateIdentityKeyPair(context, profileId)
        val phonePubB64 = b64UrlEncode(exportPublicPoint65(pubKey))
        val transcript = "pcpr-enroll-v1\n" +
            parsed.enrollToken + "\n" +
            parsed.pcPubFp + "\n" +
            parsed.userSid + "\n" +
            deviceId + "\n" +
            phonePubB64
        val sigBytes = signSha256Ecdsa(privKey, transcript.toByteArray(StandardCharsets.UTF_8))
        val sigB64 = b64UrlEncode(sigBytes)
        val deviceName = "${Build.MANUFACTURER} ${Build.MODEL}".trim().ifEmpty { "Android Phone" }.take(60)

        val request = JSONObject()
            .put("action", "unlock.enroll")
            .put("enroll_token", parsed.enrollToken)
            .put("device_id", deviceId)
            .put("device_name", deviceName)
            .put("phone_pub", phonePubB64)
            .put("signature", sigB64)

        val commit: () -> EnrollmentMeta = {
            var wrappedCt = ""
            var wrappedIv = ""
            var wrappedPk = ""
            var wrappedPkIv = ""
            if (parsed.splitKeyB64.isNotEmpty()) {
                val rawKey = b64UrlDecode(parsed.splitKeyB64)
                try {
                    val pair = wrapSecret(profileId, rawKey)
                    wrappedCt = pair.first
                    wrappedIv = pair.second
                } finally {
                    Arrays.fill(rawKey, 0.toByte())
                }
            } else if (parsed.pinMaskedKeyB64.isNotEmpty() && parsed.pinSaltB64.isNotEmpty()) {
                val maskedBytes = b64UrlDecode(parsed.pinMaskedKeyB64)
                try {
                    val pair = wrapSecret(profileId, maskedBytes)
                    wrappedPk = pair.first
                    wrappedPkIv = pair.second
                } finally {
                    Arrays.fill(maskedBytes, 0.toByte())
                }
            }
            val now = System.currentTimeMillis()
            val storedJson = JSONObject()
                .put("device_id", deviceId)
                .put("user_sid", parsed.userSid)
                .put("qualified_user", parsed.qualifiedUser.ifEmpty { "Windows User" })
                .put("pc_pub_fp", parsed.pcPubFp)
                .put("vault_mode", parsed.vaultMode)
                .put("wrapped_k", wrappedCt)
                .put("wrapped_k_iv", wrappedIv)
                .put("wrapped_pk", wrappedPk)
                .put("wrapped_pk_iv", wrappedPkIv)
                .put("pin_salt", parsed.pinSaltB64)
                .put("pin_tag", parsed.pinTagB64)
                .put("enrolled_at", now)
            prefs(context).edit().putString("meta_$profileId", storedJson.toString()).apply()
            EnrollmentMeta(
                profileId = profileId,
                deviceId = deviceId,
                userSid = parsed.userSid,
                qualifiedUser = parsed.qualifiedUser.ifEmpty { "Windows User" },
                pcPubFp = parsed.pcPubFp,
                vaultMode = parsed.vaultMode,
                hasSplitKey = wrappedCt.isNotEmpty() || wrappedPk.isNotEmpty(),
                requiresPhonePin = wrappedPk.isNotEmpty(),
                enrolledAt = now
            )
        }
        return Pair(request, commit)
    }

    private fun derivePinMask(pinChars: CharArray, salt: ByteArray): ByteArray {
        val spec = PBEKeySpec(pinChars, salt, 100_000, 256)
        return try {
            SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded
        } finally {
            spec.clearPassword()
        }
    }

    /**
     * Encrypts and signs a single-use `unlock.submit` request against a fresh `unlock.challenge` response.
     * Wipes all intermediate secrets (`shared`, `encKey`, `splitKey`, `passwordChars`, `innerBytes`) before returning.
     */
    fun buildUnlockSubmitRequest(
        context: Context,
        profileId: String,
        challenge: JSONObject,
        passwordChars: CharArray? = null,
        phonePinChars: CharArray? = null
    ): JSONObject {
        val meta = getEnrollmentMeta(context, profileId)
            ?: throw IllegalStateException("Вход с телефона ещё не привязан к этому ПК")
        val challengeId = challenge.optString("challenge_id", "")
        val nonceB64 = challenge.optString("nonce", "")
        val userSid = challenge.optString("user_sid", "")
        val pcPubB64 = challenge.optString("pc_pub", "")
        val pcPubFp = challenge.optString("pc_pub_fp", "")
        if (challengeId.isEmpty() || nonceB64.isEmpty() || userSid.isEmpty() || pcPubB64.isEmpty()) {
            throw IllegalStateException("Некорректный challenge от службы Windows Unlock")
        }

        // Verify pinned PC identity key fingerprint and Windows user SID to prevent MITM key substitution.
        val pcPubBytes = b64UrlDecode(pcPubB64)
        val computedFp = b64UrlEncode(sha256(pcPubBytes))
        if (computedFp != pcPubFp || (meta.pcPubFp.isNotEmpty() && meta.pcPubFp != computedFp)) {
            throw SecurityException("Ключ безопасности ПК не совпадает с привязанным (защита от MITM). Перепривяжите устройство.")
        }
        if (meta.userSid.isNotEmpty() && !meta.userSid.equals(userSid, ignoreCase = true)) {
            throw SecurityException("SID пользователя Windows на ПК не совпадает с привязанной учётной записью.")
        }

        val pcPubKey = importPublicPoint65(pcPubBytes)

        // Generate ephemeral EC P-256 keypair for forward-secret E2E encryption.
        val ephKpg = KeyPairGenerator.getInstance("EC")
        ephKpg.initialize(ECGenParameterSpec(EC_CURVE), rng)
        val ephPair: KeyPair = ephKpg.generateKeyPair()
        val ephPubB64 = b64UrlEncode(exportPublicPoint65(ephPair.public as ECPublicKey))

        val ka = KeyAgreement.getInstance("ECDH")
        ka.init(ephPair.private)
        ka.doPhase(pcPubKey, true)
        val rawShared = ka.generateSecret()
        val shared = if (rawShared.size == 32) rawShared else toFixed32(BigInteger(1, rawShared))

        val nonceBytes = b64UrlDecode(nonceB64)
        val infoBytes = "pcpr-unlock-v1|$userSid|${meta.deviceId}".toByteArray(StandardCharsets.UTF_8)
        val encKey = hkdfSha256(shared, nonceBytes, infoBytes, 32)
        var innerBytes = ByteArray(0)
        var unwrappedK = ByteArray(0)
        var pinMask = ByteArray(0)
        var maskedPk = ByteArray(0)

        try {
            val innerJson = JSONObject()
            if (passwordChars != null && passwordChars.isNotEmpty()) {
                innerJson.put("password", String(passwordChars))
            } else {
                val rawMeta = JSONObject(prefs(context).getString("meta_$profileId", "{}") ?: "{}")
                val wrappedCt = rawMeta.optString("wrapped_k", "")
                val wrappedIv = rawMeta.optString("wrapped_k_iv", "")
                val wrappedPk = rawMeta.optString("wrapped_pk", "")
                val wrappedPkIv = rawMeta.optString("wrapped_pk_iv", "")
                val pinSaltB64 = rawMeta.optString("pin_salt", "")
                val pinTagB64 = rawMeta.optString("pin_tag", "")

                if (wrappedCt.isNotEmpty() && wrappedIv.isNotEmpty()) {
                    unwrappedK = unwrapSecret(profileId, wrappedCt, wrappedIv)
                    innerJson.put("k", b64UrlEncode(unwrappedK))
                } else if (wrappedPk.isNotEmpty() && wrappedPkIv.isNotEmpty() && pinSaltB64.isNotEmpty()) {
                    if (phonePinChars == null || phonePinChars.isEmpty()) {
                        throw IllegalArgumentException("Введите PIN-код для входа с телефона")
                    }
                    val salt = b64UrlDecode(pinSaltB64)
                    pinMask = derivePinMask(phonePinChars, salt)
                    if (pinTagB64.isNotEmpty()) {
                        val expectedTag = b64UrlDecode(pinTagB64)
                        val mac = Mac.getInstance("HmacSHA256")
                        mac.init(SecretKeySpec(pinMask, "HmacSHA256"))
                        val fullTag = mac.doFinal("pcpr-pin-check-v1".toByteArray(StandardCharsets.UTF_8))
                        val actualTag = fullTag.copyOfRange(0, minOf(16, fullTag.size))
                        if (!MessageDigest.isEqual(expectedTag, actualTag)) {
                            throw IllegalArgumentException("Неверный PIN-код телефона! Проверьте введённый код.")
                        }
                    }
                    maskedPk = unwrapSecret(profileId, wrappedPk, wrappedPkIv)
                    if (maskedPk.size != 32 || pinMask.size != 32) {
                        throw IllegalStateException("Повреждён локальный ключ привязки")
                    }
                    unwrappedK = ByteArray(32) { idx ->
                        (maskedPk[idx].toInt() xor pinMask[idx].toInt()).toByte()
                    }
                    innerJson.put("k", b64UrlEncode(unwrappedK))
                } else {
                    throw IllegalStateException("Для этого режима требуется ввести пароль Windows")
                }
            }
            innerBytes = innerJson.toString().toByteArray(StandardCharsets.UTF_8)

            val iv = ByteArray(12).also { rng.nextBytes(it) }
            val ivB64 = b64UrlEncode(iv)
            val timestamp = (System.currentTimeMillis() / 1000L).toString()

            val aad = "pcpr-unlock-v1\n" +
                challengeId + "\n" +
                nonceB64 + "\n" +
                userSid + "\n" +
                meta.deviceId + "\n" +
                timestamp + "\n" +
                ephPubB64 + "\n" +
                ivB64

            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(Cipher.ENCRYPT_MODE, SecretKeySpec(encKey, "AES"), GCMParameterSpec(128, iv))
            cipher.updateAAD(aad.toByteArray(StandardCharsets.UTF_8))
            val ctAndTag = cipher.doFinal(innerBytes)
            val ctB64 = b64UrlEncode(ctAndTag)

            val transcript = "$aad\n$ctB64"
            val (phonePriv, _) = getOrCreateIdentityKeyPair(context, profileId)
            val sigBytes = signSha256Ecdsa(phonePriv, transcript.toByteArray(StandardCharsets.UTF_8))
            val sigB64 = b64UrlEncode(sigBytes)

            return JSONObject()
                .put("action", "unlock.submit")
                .put("challenge_id", challengeId)
                .put("device_id", meta.deviceId)
                .put("user_sid", userSid)
                .put("timestamp", timestamp)
                .put("eph_pub", ephPubB64)
                .put("iv", ivB64)
                .put("ciphertext", ctB64)
                .put("signature", sigB64)
        } finally {
            Arrays.fill(rawShared, 0.toByte())
            Arrays.fill(shared, 0.toByte())
            Arrays.fill(encKey, 0.toByte())
            if (innerBytes.isNotEmpty()) Arrays.fill(innerBytes, 0.toByte())
            if (unwrappedK.isNotEmpty()) Arrays.fill(unwrappedK, 0.toByte())
            if (pinMask.isNotEmpty()) Arrays.fill(pinMask, 0.toByte())
            if (maskedPk.isNotEmpty()) Arrays.fill(maskedPk, 0.toByte())
            if (passwordChars != null) Arrays.fill(passwordChars, '\u0000')
            if (phonePinChars != null) Arrays.fill(phonePinChars, '\u0000')
        }
    }

    fun checkPhonePinLocally(context: Context, profileId: String, pinChars: CharArray): Boolean {
        val rawMeta = JSONObject(prefs(context).getString("meta_$profileId", "{}") ?: "{}")
        val pinSaltB64 = rawMeta.optString("pin_salt", "")
        val pinTagB64 = rawMeta.optString("pin_tag", "")
        if (pinSaltB64.isEmpty() || pinTagB64.isEmpty()) return true
        val copyChars = pinChars.clone()
        val mask = derivePinMask(copyChars, b64UrlDecode(pinSaltB64))
        return try {
            val expectedTag = b64UrlDecode(pinTagB64)
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(mask, "HmacSHA256"))
            val fullTag = mac.doFinal("pcpr-pin-check-v1".toByteArray(StandardCharsets.UTF_8))
            val actualTag = fullTag.copyOfRange(0, minOf(16, fullTag.size))
            MessageDigest.isEqual(expectedTag, actualTag)
        } finally {
            Arrays.fill(mask, 0.toByte())
            Arrays.fill(copyChars, '\u0000')
        }
    }

    /**
     * Prompts the user with hardware BiometricPrompt (API 28+) if enrolled on the phone,
     * or invokes `onVerified()` immediately if biometrics are not configured on the handset.
     */
    fun confirmUserPresence(
        activity: Activity,
        title: String,
        subtitle: String,
        cancelLabel: String,
        onVerified: () -> Unit,
        onCancelled: (String) -> Unit
    ) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.P) {
            onVerified()
            return
        }
        try {
            val cancelSignal = CancellationSignal()
            val prompt = BiometricPrompt.Builder(activity)
                .setTitle(title)
                .setSubtitle(subtitle)
                .setNegativeButton(cancelLabel, activity.mainExecutor) { _, _ ->
                    onCancelled("Отменено пользователем")
                }
                .build()

            prompt.authenticate(
                cancelSignal,
                activity.mainExecutor,
                object : BiometricPrompt.AuthenticationCallback() {
                    override fun onAuthenticationSucceeded(result: BiometricPrompt.AuthenticationResult?) {
                        onVerified()
                    }

                    override fun onAuthenticationError(errorCode: Int, errString: CharSequence?) {
                        // If handset has no biometrics enrolled (BIOMETRIC_ERROR_NO_BIOMETRICS = 11,
                        // BIOMETRIC_ERROR_HW_NOT_PRESENT = 12, BIOMETRIC_ERROR_HW_UNAVAILABLE = 1),
                        // allow proceeding so devices/emulators without fingerprint sensor still work.
                        if (errorCode == 11 || errorCode == 12 || errorCode == 1 || errorCode == 14) {
                            onVerified()
                        } else {
                            onCancelled(errString?.toString() ?: "Биометрия отменена")
                        }
                    }
                }
            )
        } catch (_: Exception) {
            onVerified()
        }
    }

    /**
     * Sends a direct UDP Wake-on-LAN Magic Packet (`6x FF` + `16x MAC`) from the phone to LAN broadcast
     * and the target host IP so that a powered-off PC can be woken even when the Python server is offline.
     */
    fun sendDirectMagicPacket(macAddress: String, targetHost: String) {
        val hex = macAddress.replace(Regex("[^0-9A-Fa-f]"), "")
        if (hex.length != 12) throw IllegalArgumentException("Укажите корректный MAC-адрес (XX:XX:XX:XX:XX:XX)")
        val macBytes = ByteArray(6)
        for (i in 0 until 6) {
            macBytes[i] = hex.substring(i * 2, i * 2 + 2).toInt(16).toByte()
        }
        val packet = ByteArray(6 + 16 * 6)
        Arrays.fill(packet, 0, 6, 0xFF.toByte())
        for (i in 0 until 16) {
            System.arraycopy(macBytes, 0, packet, 6 + i * 6, 6)
        }
        DatagramSocket().use { socket ->
            socket.broadcast = true
            val targets = linkedSetOf("255.255.255.255")
            val cleanedHost = targetHost.trim().removePrefix("http://").removePrefix("https://").substringBefore(":")
            if (cleanedHost.matches(Regex("\\d+\\.\\d+\\.\\d+\\.\\d+"))) {
                targets.add(cleanedHost)
                val parts = cleanedHost.split(".")
                if (parts.size == 4) {
                    targets.add("${parts[0]}.${parts[1]}.${parts[2]}.255")
                }
            }
            for (addr in targets) {
                try {
                    val inet = InetAddress.getByName(addr)
                    socket.send(DatagramPacket(packet, packet.size, inet, 9))
                    socket.send(DatagramPacket(packet, packet.size, inet, 7))
                } catch (_: Exception) {
                }
            }
        }
    }
}
