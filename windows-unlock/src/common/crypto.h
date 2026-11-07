// Windows CNG (bcrypt) wrappers used by the unlock protocol.
//
// Protocol primitives (must match the Android client):
//   * Phone identity:  ECDSA P-256 / SHA-256, DER signatures, public key as 65-byte point 04|X|Y.
//   * Key transport:   ephemeral ECDH P-256 (phone) x static ECDH P-256 (service),
//                      HKDF-SHA256(shared, salt, info) -> 64 bytes = AES key (32) | MAC key (32).
//   * Encryption:      AES-256-GCM, 12-byte IV, 16-byte tag appended to ciphertext.
#pragma once

#include "util.h"

#include <bcrypt.h>

namespace pcpr {

constexpr size_t kPointSize = 65;  // uncompressed P-256 point
constexpr size_t kGcmIvSize = 12;
constexpr size_t kGcmTagSize = 16;

bool RandomBytes(uint8_t* out, size_t size);
Bytes RandomBytes(size_t size);

Bytes Sha256(const Bytes& data);
Bytes HmacSha256(const Bytes& key, const Bytes& data);
Bytes HkdfSha256(const Bytes& ikm, const Bytes& salt, const std::string& info, size_t length);
bool ConstantTimeEqual(const Bytes& a, const Bytes& b);

// AES-256-GCM. Output/input ciphertext is ciphertext||tag.
bool AesGcmEncrypt(const Bytes& key, const Bytes& iv, const Bytes& aad, const Bytes& plaintext, Bytes& out);
bool AesGcmDecrypt(const Bytes& key, const Bytes& iv, const Bytes& aad, const Bytes& ciphertextAndTag, Bytes& out);

// Static ECDH key pair owned by the service.
class EcdhKey {
public:
    EcdhKey() = default;
    ~EcdhKey();
    EcdhKey(const EcdhKey&) = delete;
    EcdhKey& operator=(const EcdhKey&) = delete;

    bool Generate();
    bool ImportPrivate(const Bytes& blob);   // BCRYPT_ECCPRIVATE_BLOB
    bool ExportPrivate(Bytes& blob) const;   // BCRYPT_ECCPRIVATE_BLOB (secret!)
    Bytes PublicPoint() const;               // 04|X|Y
    // Raw shared secret (big-endian X coordinate, 32 bytes) with a peer point.
    bool Agree(const Bytes& peerPoint, Bytes& shared) const;
    bool Valid() const { return key_ != nullptr; }

private:
    BCRYPT_KEY_HANDLE key_ = nullptr;
};

// Generates an ephemeral key and agrees with peerPoint (used by tests / clients).
bool EphemeralAgree(const Bytes& peerPoint, Bytes& ephemeralPoint, Bytes& shared);

// Verifies a DER ECDSA-P256-SHA256 signature over message with a 65-byte public point.
bool EcdsaVerify(const Bytes& publicPoint, const Bytes& message, const Bytes& derSignature);

// Test helper: ECDSA key that can sign (DER output), used by the selftest tool.
class EcdsaKey {
public:
    ~EcdsaKey();
    bool Generate();
    Bytes PublicPoint() const;
    bool Sign(const Bytes& message, Bytes& derSignature) const;

private:
    BCRYPT_KEY_HANDLE key_ = nullptr;
};

inline Bytes ToBytes(const std::string& s) { return Bytes(s.begin(), s.end()); }

}  // namespace pcpr
