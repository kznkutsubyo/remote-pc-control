import CommonCrypto
import CryptoKit
import Foundation
import LocalAuthentication
import Security
import UIKit

struct ParsedEnrollUri {
    let enrollToken: String
    let pcPubFp: String
    let userSid: String
    let qualifiedUser: String
    let vaultMode: String
    let splitKeyB64: String
    let pinSplitKeyB64: String
    let pinSaltB64: String
    let pinTagB64: String
    let host: String
    let port: String
    let pcName: String
    let pin: String

    var isPinMode: Bool {
        !pinSplitKeyB64.isEmpty && !pinSaltB64.isEmpty && !pinTagB64.isEmpty
    }
}

struct EnrollmentMeta: Codable {
    let deviceId: String
    let userSid: String
    let qualifiedUser: String
    let vaultMode: String
    let hasSplitKey: Bool
    let requiresPhonePin: Bool
    let pinSaltB64: String
    let pinTagB64: String
    let wrappedKeyB64: String
}

enum UnlockCryptoError: LocalizedError {
    case invalidUri
    case missingEnrollment
    case invalidPcPublicKey
    case wrongPhonePin
    case cryptoFailure(String)

    var errorDescription: String? {
        switch self {
        case .invalidUri: return "Invalid enrollment link or QR code."
        case .missingEnrollment: return "This PC is not paired for phone unlock yet."
        case .invalidPcPublicKey: return "Invalid PC public key returned in challenge."
        case .wrongPhonePin: return "Wrong Phone Unlock PIN."
        case .cryptoFailure(let msg): return msg
        }
    }
}

enum UnlockCrypto {
    private static let defaults = UserDefaults.standard

    static func b64UrlEncode(_ data: Data) -> String {
        data.base64EncodedString()
            .replacingOccurrences(of: "+", with: "-")
            .replacingOccurrences(of: "/", with: "_")
            .replacingOccurrences(of: "=", with: "")
    }

    static func b64UrlDecode(_ str: String) -> Data? {
        var padded = str.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "-", with: "+")
            .replacingOccurrences(of: "_", with: "/")
        let rem = padded.count % 4
        if rem > 0 {
            padded += String(repeating: "=", count: 4 - rem)
        }
        return Data(base64Encoded: padded)
    }

    static func parseEnrollCode(_ rawInput: String) -> ParsedEnrollUri? {
        let trimmed = rawInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty,
              let comp = URLComponents(string: trimmed),
              comp.scheme == "pcphone",
              comp.host == "enroll"
        else { return nil }

        let params = Dictionary(
            (comp.queryItems ?? []).map { ($0.name, $0.value ?? "") },
            uniquingKeysWith: { first, _ in first }
        )
        let token = params["token"] ?? ""
        let fp = params["fp"] ?? ""
        let sid = params["sid"] ?? ""
        guard !token.isEmpty, !fp.isEmpty, !sid.isEmpty else { return nil }

        return ParsedEnrollUri(
            enrollToken: token,
            pcPubFp: fp,
            userSid: sid,
            qualifiedUser: params["user"] ?? "Windows User",
            vaultMode: params["mode"] ?? "split_key",
            splitKeyB64: params["k"] ?? "",
            pinSplitKeyB64: params["pk"] ?? "",
            pinSaltB64: params["ps"] ?? "",
            pinTagB64: params["pt"] ?? "",
            host: params["host"] ?? "",
            port: params["port"] ?? "8765",
            pcName: params["name"] ?? "PC",
            pin: params["pin"] ?? ""
        )
    }

    // MARK: - Keychain storage for P-256 signing private key & split key
    private static func keychainSave(account: String, data: Data) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.pcphoneremote.unlock",
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
        var add = query
        add[kSecValueData as String] = data
        add[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
        SecItemAdd(add as CFDictionary, nil)
    }

    private static func keychainLoad(account: String) -> Data? {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.pcphoneremote.unlock",
            kSecAttrAccount as String: account,
            kSecReturnData as String: true,
            kSecMatchLimit as String: kSecMatchLimitOne,
        ]
        var result: AnyObject?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess else {
            return nil
        }
        return result as? Data
    }

    private static func keychainDelete(account: String) {
        let query: [String: Any] = [
            kSecClass as String: kSecClassGenericPassword,
            kSecAttrService as String: "com.pcphoneremote.unlock",
            kSecAttrAccount as String: account,
        ]
        SecItemDelete(query as CFDictionary)
    }

    private static func getOrCreateSigningKey(profileId: String) throws -> P256.Signing.PrivateKey {
        let account = "signing_\(profileId)"
        if let raw = keychainLoad(account: account),
           let key = try? P256.Signing.PrivateKey(rawRepresentation: raw)
        {
            return key
        }
        let key = P256.Signing.PrivateKey()
        keychainSave(account: account, data: key.rawRepresentation)
        return key
    }

    static func pbkdf2Sha256(password: String, salt: Data, rounds: UInt32 = 100_000, keyLength: Int = 32) throws -> Data {
        let pwData = Data(password.utf8)
        var derived = Data(count: keyLength)
        let status = derived.withUnsafeMutableBytes { derivedPtr in
            salt.withUnsafeBytes { saltPtr in
                pwData.withUnsafeBytes { pwPtr in
                    CCKeyDerivationPBKDF(
                        CCPBKDFAlgorithm(kCCPBKDF2),
                        pwPtr.baseAddress?.assumingMemoryBound(to: Int8.self),
                        pwData.count,
                        saltPtr.baseAddress?.assumingMemoryBound(to: UInt8.self),
                        salt.count,
                        CCPseudoRandomAlgorithm(kCCPRFHmacAlgSHA256),
                        rounds,
                        derivedPtr.baseAddress?.assumingMemoryBound(to: UInt8.self),
                        keyLength
                    )
                }
            }
        }
        guard status == kCCSuccess else {
            throw UnlockCryptoError.cryptoFailure("PBKDF2 key derivation failed (\(status))")
        }
        return derived
    }

    static func loadMeta(profileId: String) -> EnrollmentMeta? {
        guard let data = defaults.data(forKey: "unlock_meta_\(profileId)") else { return nil }
        return try? JSONDecoder().decode(EnrollmentMeta.self, from: data)
    }

    static func clearEnrollment(profileId: String) {
        defaults.removeObject(forKey: "unlock_meta_\(profileId)")
        keychainDelete(account: "signing_\(profileId)")
        keychainDelete(account: "splitk_\(profileId)")
    }

    static func checkPhonePinLocally(profileId: String, phonePin: String) -> Bool {
        guard let meta = loadMeta(profileId: profileId), meta.requiresPhonePin else { return true }
        guard let salt = b64UrlDecode(meta.pinSaltB64),
              let expectedTag = b64UrlDecode(meta.pinTagB64),
              let mask = try? pbkdf2Sha256(password: phonePin, salt: salt)
        else { return false }
        let mac = HMAC<SHA256>.authenticationCode(
            for: Data("pcpr-pin-check-v1".utf8),
            using: SymmetricKey(data: mask)
        )
        return Data(mac.prefix(16)) == expectedTag
    }

    static func prepareEnrollment(profileId: String, parsed: ParsedEnrollUri) throws -> (request: [String: Any], commit: () -> EnrollmentMeta) {
        let privKey = try getOrCreateSigningKey(profileId: profileId)
        let phonePubB64 = b64UrlEncode(privKey.publicKey.x963Representation)
        let deviceId = (defaults.string(forKey: "ios_device_id") ?? {
            let fresh = UUID().uuidString.replacingOccurrences(of: "-", with: "").lowercased()
            defaults.set(fresh, forKey: "ios_device_id")
            return fresh
        }())

        let transcript = "pcpr-enroll-v1\n\(parsed.enrollToken)\n\(parsed.pcPubFp)\n\(parsed.userSid)\n\(deviceId)\n\(phonePubB64)"
        let signature = try privKey.signature(for: Data(transcript.utf8))
        let sigB64 = b64UrlEncode(signature.derRepresentation)
        let deviceName = String(UIDevice.current.name.prefix(60))

        let req: [String: Any] = [
            "action": "unlock.enroll",
            "enroll_token": parsed.enrollToken,
            "device_id": deviceId,
            "device_name": deviceName.isEmpty ? "iPhone" : deviceName,
            "phone_pub": phonePubB64,
            "signature": sigB64,
        ]

        let commit: () -> EnrollmentMeta = {
            var storedKeyB64 = ""
            var hasSplit = false
            if parsed.isPinMode, let masked = b64UrlDecode(parsed.pinSplitKeyB64) {
                keychainSave(account: "splitk_\(profileId)", data: masked)
                storedKeyB64 = parsed.pinSplitKeyB64
                hasSplit = true
            } else if !parsed.splitKeyB64.isEmpty, let rawK = b64UrlDecode(parsed.splitKeyB64) {
                keychainSave(account: "splitk_\(profileId)", data: rawK)
                storedKeyB64 = parsed.splitKeyB64
                hasSplit = true
            }

            let meta = EnrollmentMeta(
                deviceId: deviceId,
                userSid: parsed.userSid,
                qualifiedUser: parsed.qualifiedUser,
                vaultMode: parsed.vaultMode,
                hasSplitKey: hasSplit,
                requiresPhonePin: parsed.isPinMode,
                pinSaltB64: parsed.pinSaltB64,
                pinTagB64: parsed.pinTagB64,
                wrappedKeyB64: storedKeyB64
            )
            if let encoded = try? JSONEncoder().encode(meta) {
                defaults.set(encoded, forKey: "unlock_meta_\(profileId)")
            }
            return meta
        }

        return (req, commit)
    }

    static func buildUnlockSubmitRequest(
        profileId: String,
        challenge: [String: Any],
        password: String?,
        phonePin: String?
    ) throws -> [String: Any] {
        guard let meta = loadMeta(profileId: profileId) else {
            throw UnlockCryptoError.missingEnrollment
        }
        let signingKey = try getOrCreateSigningKey(profileId: profileId)

        let challengeId = challenge["challenge_id"] as? String ?? ""
        let nonceB64 = challenge["nonce"] as? String ?? ""
        let pcPubB64 = challenge["pc_pub"] as? String ?? ""
        let userSid = (challenge["user_sid"] as? String).flatMap { $0.isEmpty ? nil : $0 } ?? meta.userSid
        let timestamp: String = {
            if let s = challenge["timestamp"] as? String, !s.isEmpty { return s }
            if let n = challenge["timestamp"] as? NSNumber { return n.stringValue }
            return String(Int(Date().timeIntervalSince1970))
        }()

        guard let pcPubData = b64UrlDecode(pcPubB64),
              let pcPubKey = try? P256.KeyAgreement.PublicKey(x963Representation: pcPubData),
              let nonceData = b64UrlDecode(nonceB64)
        else {
            throw UnlockCryptoError.invalidPcPublicKey
        }

        let ephKey = P256.KeyAgreement.PrivateKey()
        let ephPubB64 = b64UrlEncode(ephKey.publicKey.x963Representation)
        let sharedSecret = try ephKey.sharedSecretFromKeyAgreement(with: pcPubKey)

        let infoData = Data("pcpr-unlock-v1|\(userSid)|\(meta.deviceId)".utf8)
        let encKey = sharedSecret.hkdfDerivedSymmetricKey(
            using: SHA256.self,
            salt: nonceData,
            sharedInfo: infoData,
            outputByteCount: 32
        )

        var innerDict: [String: Any] = [:]
        if let pw = password, !pw.isEmpty {
            innerDict["password"] = pw
        } else {
            guard let storedKeyData = keychainLoad(account: "splitk_\(profileId)") else {
                throw UnlockCryptoError.missingEnrollment
            }
            var rawK = storedKeyData
            if meta.requiresPhonePin {
                guard let pin = phonePin, !pin.isEmpty,
                      let salt = b64UrlDecode(meta.pinSaltB64),
                      let expectedTag = b64UrlDecode(meta.pinTagB64)
                else {
                    throw UnlockCryptoError.wrongPhonePin
                }
                let mask = try pbkdf2Sha256(password: pin, salt: salt)
                let mac = HMAC<SHA256>.authenticationCode(
                    for: Data("pcpr-pin-check-v1".utf8),
                    using: SymmetricKey(data: mask)
                )
                guard Data(mac.prefix(16)) == expectedTag else {
                    throw UnlockCryptoError.wrongPhonePin
                }
                rawK = Data(zip(storedKeyData, mask).map { $0 ^ $1 })
            }
            innerDict["k"] = b64UrlEncode(rawK)
        }

        let innerData = try JSONSerialization.data(withJSONObject: innerDict)
        let ivBytes = AES.GCM.Nonce()
        let ivData = Data(ivBytes)
        let ivB64 = b64UrlEncode(ivData)

        let aad = "pcpr-unlock-v1\n\(challengeId)\n\(nonceB64)\n\(userSid)\n\(meta.deviceId)\n\(timestamp)\n\(ephPubB64)\n\(ivB64)"
        let sealed = try AES.GCM.seal(innerData, using: encKey, nonce: ivBytes, authenticating: Data(aad.utf8))
        let ctAndTag = sealed.ciphertext + sealed.tag
        let ctB64 = b64UrlEncode(ctAndTag)

        let transcript = "\(aad)\n\(ctB64)"
        let signature = try signingKey.signature(for: Data(transcript.utf8))

        return [
            "action": "unlock.submit",
            "challenge_id": challengeId,
            "device_id": meta.deviceId,
            "user_sid": userSid,
            "timestamp": timestamp,
            "eph_pub": ephPubB64,
            "iv": ivB64,
            "ciphertext": ctB64,
            "signature": b64UrlEncode(signature.derRepresentation),
        ]
    }

    static func authenticateBiometrics(reason: String) async -> Result<Void, Error> {
        let context = LAContext()
        var authErr: NSError?
        guard context.canEvaluatePolicy(.deviceOwnerAuthentication, error: &authErr) else {
            return .failure(authErr ?? NSError(domain: "PCPhoneRemote", code: 1, userInfo: [NSLocalizedDescriptionKey: "Device authentication is unavailable. Use Windows password mode or configure a device passcode."]))
        }
        return await withCheckedContinuation { cont in
            context.evaluatePolicy(.deviceOwnerAuthentication, localizedReason: reason) { ok, err in
                if ok {
                    cont.resume(returning: .success(()))
                } else {
                    cont.resume(returning: .failure(err ?? UnlockCryptoError.cryptoFailure("Authentication cancelled")))
                }
            }
        }
    }
}
