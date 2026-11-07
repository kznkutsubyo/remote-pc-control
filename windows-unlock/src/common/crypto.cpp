#include "crypto.h"

#include <wincrypt.h>

#pragma comment(lib, "bcrypt.lib")
#pragma comment(lib, "crypt32.lib")

namespace pcpr {

namespace {

struct AlgHandle {
    BCRYPT_ALG_HANDLE h = nullptr;
    ~AlgHandle() { if (h) BCryptCloseAlgorithmProvider(h, 0); }
};

struct HashHandle {
    BCRYPT_HASH_HANDLE h = nullptr;
    ~HashHandle() { if (h) BCryptDestroyKey(h); }
};

struct KeyHandle {
    BCRYPT_KEY_HANDLE h = nullptr;
    ~KeyHandle() { if (h) BCryptDestroyKey(h); }
};

// Encodes two 32-byte big-endian integers (r, s) as an ASN.1 DER ECDSA-Sig-Value.
Bytes RawSigToDer(const uint8_t* raw64) {
    auto encodeInt = [](const uint8_t* p) -> Bytes {
        size_t i = 0;
        while (i < 31 && p[i] == 0) ++i;
        Bytes v;
        if (p[i] & 0x80) v.push_back(0x00);
        v.insert(v.end(), p + i, p + 32);
        Bytes out = {0x02, static_cast<uint8_t>(v.size())};
        out.insert(out.end(), v.begin(), v.end());
        return out;
    };
    Bytes r = encodeInt(raw64);
    Bytes s = encodeInt(raw64 + 32);
    Bytes seq = {0x30, static_cast<uint8_t>(r.size() + s.size())};
    seq.insert(seq.end(), r.begin(), r.end());
    seq.insert(seq.end(), s.begin(), s.end());
    return seq;
}

// Decodes a strict ASN.1 DER ECDSA-Sig-Value into 64-byte (r || s) for BCryptVerifySignature.
bool DerSigToRaw(const Bytes& der, Bytes& raw64) {
    raw64.assign(64, 0);
    if (der.size() < 8 || der.size() > 72 || der[0] != 0x30) return false;
    size_t seqLen = der[1];
    if (seqLen + 2 != der.size()) return false;
    size_t pos = 2;
    for (int part = 0; part < 2; ++part) {
        if (pos + 2 > der.size() || der[pos] != 0x02) return false;
        size_t len = der[pos + 1];
        pos += 2;
        if (len == 0 || len > 33 || pos + len > der.size()) return false;
        // Reject non-minimal DER integer padding.
        if (der[pos] == 0x00 && (len == 1 || (der[pos + 1] & 0x80) == 0)) return false;
        if (der[pos] & 0x80) return false;  // negative integer
        const uint8_t* src = &der[pos];
        if (len == 33) {
            if (*src != 0x00) return false;
            ++src;
            --len;
        }
        memcpy(&raw64[part * 32 + (32 - len)], src, len);
        pos += (der[pos - 1]);
    }
    return pos == der.size();
}

bool ExportPublicPoint(BCRYPT_KEY_HANDLE key, Bytes& point) {
    ULONG cb = 0;
    if (BCryptExportKey(key, nullptr, BCRYPT_ECCPUBLIC_BLOB, nullptr, 0, &cb, 0) != 0 || cb != sizeof(BCRYPT_ECCKEY_BLOB) + 64) {
        return false;
    }
    Bytes blob(cb);
    if (BCryptExportKey(key, nullptr, BCRYPT_ECCPUBLIC_BLOB, blob.data(), cb, &cb, 0) != 0) {
        return false;
    }
    point.resize(kPointSize);
    point[0] = 0x04;
    memcpy(&point[1], blob.data() + sizeof(BCRYPT_ECCKEY_BLOB), 64);
    return true;
}

bool ImportPublicPoint(BCRYPT_ALG_HANDLE alg, ULONG magic, const Bytes& point, BCRYPT_KEY_HANDLE* outKey) {
    if (point.size() != kPointSize || point[0] != 0x04) return false;
    Bytes blob(sizeof(BCRYPT_ECCKEY_BLOB) + 64);
    auto* hdr = reinterpret_cast<BCRYPT_ECCKEY_BLOB*>(blob.data());
    hdr->dwMagic = magic;
    hdr->cbKey = 32;
    memcpy(blob.data() + sizeof(BCRYPT_ECCKEY_BLOB), &point[1], 64);
    return BCryptImportKeyPair(alg, nullptr, BCRYPT_ECCPUBLIC_BLOB, outKey, blob.data(), (ULONG)blob.size(), 0) == 0;
}

}  // namespace

bool RandomBytes(uint8_t* out, size_t size) {
    return BCryptGenRandom(nullptr, out, (ULONG)size, BCRYPT_USE_SYSTEM_PREFERRED_RNG) == 0;
}

Bytes RandomBytes(size_t size) {
    Bytes b(size);
    if (!RandomBytes(b.data(), size)) b.clear();
    return b;
}

Bytes Sha256(const Bytes& data) {
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_SHA256_ALGORITHM, nullptr, 0) != 0) return {};
    BCRYPT_HASH_HANDLE h = nullptr;
    if (BCryptCreateHash(alg.h, &h, nullptr, 0, nullptr, 0, 0) != 0) return {};
    Bytes out(32);
    bool ok = BCryptHashData(h, const_cast<PUCHAR>(data.data()), (ULONG)data.size(), 0) == 0 &&
              BCryptFinishHash(h, out.data(), (ULONG)out.size(), 0) == 0;
    BCryptDestroyHash(h);
    return ok ? out : Bytes{};
}

Bytes HmacSha256(const Bytes& key, const Bytes& data) {
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_SHA256_ALGORITHM, nullptr, BCRYPT_ALG_HANDLE_HMAC_FLAG) != 0) return {};
    BCRYPT_HASH_HANDLE h = nullptr;
    if (BCryptCreateHash(alg.h, &h, nullptr, 0, const_cast<PUCHAR>(key.data()), (ULONG)key.size(), 0) != 0) return {};
    Bytes out(32);
    bool ok = BCryptHashData(h, const_cast<PUCHAR>(data.data()), (ULONG)data.size(), 0) == 0 &&
              BCryptFinishHash(h, out.data(), (ULONG)out.size(), 0) == 0;
    BCryptDestroyHash(h);
    return ok ? out : Bytes{};
}

Bytes HkdfSha256(const Bytes& ikm, const Bytes& salt, const std::string& info, size_t length) {
    Bytes realSalt = salt.empty() ? Bytes(32, 0) : salt;
    SecretBytes prk(HmacSha256(realSalt, ikm));
    if (prk.value.size() != 32) return {};
    Bytes out;
    out.reserve(length);
    Bytes prev;
    uint8_t counter = 1;
    while (out.size() < length) {
        Bytes msg = prev;
        msg.insert(msg.end(), info.begin(), info.end());
        msg.push_back(counter++);
        prev = HmacSha256(prk.value, msg);
        Wipe(msg);
        if (prev.size() != 32) return {};
        size_t take = (std::min)(length - out.size(), prev.size());
        out.insert(out.end(), prev.begin(), prev.begin() + take);
    }
    Wipe(prev);
    return out;
}

bool ConstantTimeEqual(const Bytes& a, const Bytes& b) {
    if (a.size() != b.size()) return false;
    uint8_t diff = 0;
    for (size_t i = 0; i < a.size(); ++i) diff |= (a[i] ^ b[i]);
    return diff == 0;
}

bool AesGcmEncrypt(const Bytes& key, const Bytes& iv, const Bytes& aad, const Bytes& plaintext, Bytes& out) {
    if (key.size() != 32 || iv.size() != kGcmIvSize) return false;
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_AES_ALGORITHM, nullptr, 0) != 0) return false;
    if (BCryptSetProperty(alg.h, BCRYPT_CHAINING_MODE, (PUCHAR)BCRYPT_CHAIN_MODE_GCM, sizeof(BCRYPT_CHAIN_MODE_GCM), 0) != 0) return false;
    KeyHandle kh;
    if (BCryptGenerateSymmetricKey(alg.h, &kh.h, nullptr, 0, const_cast<PUCHAR>(key.data()), (ULONG)key.size(), 0) != 0) return false;

    Bytes ivCopy = iv;
    Bytes tag(kGcmTagSize);
    BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO info;
    BCRYPT_INIT_AUTH_MODE_INFO(info);
    info.pbNonce = ivCopy.data();
    info.cbNonce = (ULONG)ivCopy.size();
    info.pbAuthData = aad.empty() ? nullptr : const_cast<PUCHAR>(aad.data());
    info.cbAuthData = (ULONG)aad.size();
    info.pbTag = tag.data();
    info.cbTag = (ULONG)tag.size();

    out.resize(plaintext.size() + kGcmTagSize);
    ULONG cbResult = 0;
    NTSTATUS st = BCryptEncrypt(
        kh.h,
        plaintext.empty() ? nullptr : const_cast<PUCHAR>(plaintext.data()),
        (ULONG)plaintext.size(),
        &info,
        nullptr, 0,
        out.data(), (ULONG)plaintext.size(),
        &cbResult, 0);
    if (st != 0 || cbResult != plaintext.size()) {
        Wipe(out);
        return false;
    }
    memcpy(out.data() + plaintext.size(), tag.data(), kGcmTagSize);
    return true;
}

bool AesGcmDecrypt(const Bytes& key, const Bytes& iv, const Bytes& aad, const Bytes& ciphertextAndTag, Bytes& out) {
    if (key.size() != 32 || iv.size() != kGcmIvSize || ciphertextAndTag.size() < kGcmTagSize) return false;
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_AES_ALGORITHM, nullptr, 0) != 0) return false;
    if (BCryptSetProperty(alg.h, BCRYPT_CHAINING_MODE, (PUCHAR)BCRYPT_CHAIN_MODE_GCM, sizeof(BCRYPT_CHAIN_MODE_GCM), 0) != 0) return false;
    KeyHandle kh;
    if (BCryptGenerateSymmetricKey(alg.h, &kh.h, nullptr, 0, const_cast<PUCHAR>(key.data()), (ULONG)key.size(), 0) != 0) return false;

    size_t ctLen = ciphertextAndTag.size() - kGcmTagSize;
    Bytes ivCopy = iv;
    Bytes tag(ciphertextAndTag.begin() + ctLen, ciphertextAndTag.end());
    BCRYPT_AUTHENTICATED_CIPHER_MODE_INFO info;
    BCRYPT_INIT_AUTH_MODE_INFO(info);
    info.pbNonce = ivCopy.data();
    info.cbNonce = (ULONG)ivCopy.size();
    info.pbAuthData = aad.empty() ? nullptr : const_cast<PUCHAR>(aad.data());
    info.cbAuthData = (ULONG)aad.size();
    info.pbTag = tag.data();
    info.cbTag = (ULONG)tag.size();

    out.resize(ctLen);
    ULONG cbResult = 0;
    NTSTATUS st = BCryptDecrypt(
        kh.h,
        ctLen ? const_cast<PUCHAR>(ciphertextAndTag.data()) : nullptr,
        (ULONG)ctLen,
        &info,
        nullptr, 0,
        ctLen ? out.data() : nullptr, (ULONG)ctLen,
        &cbResult, 0);
    if (st != 0 || cbResult != ctLen) {
        Wipe(out);
        return false;
    }
    return true;
}

EcdhKey::~EcdhKey() {
    if (key_) BCryptDestroyKey(key_);
}

bool EcdhKey::Generate() {
    if (key_) { BCryptDestroyKey(key_); key_ = nullptr; }
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_ECDH_P256_ALGORITHM, nullptr, 0) != 0) return false;
    if (BCryptGenerateKeyPair(alg.h, &key_, 256, 0) != 0) return false;
    if (BCryptFinalizeKeyPair(key_, 0) != 0) {
        BCryptDestroyKey(key_);
        key_ = nullptr;
        return false;
    }
    return true;
}

bool EcdhKey::ImportPrivate(const Bytes& blob) {
    if (key_) { BCryptDestroyKey(key_); key_ = nullptr; }
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_ECDH_P256_ALGORITHM, nullptr, 0) != 0) return false;
    return BCryptImportKeyPair(alg.h, nullptr, BCRYPT_ECCPRIVATE_BLOB, &key_, const_cast<PUCHAR>(blob.data()), (ULONG)blob.size(), 0) == 0;
}

bool EcdhKey::ExportPrivate(Bytes& blob) const {
    if (!key_) return false;
    ULONG cb = 0;
    if (BCryptExportKey(key_, nullptr, BCRYPT_ECCPRIVATE_BLOB, nullptr, 0, &cb, 0) != 0 || cb == 0) return false;
    blob.resize(cb);
    return BCryptExportKey(key_, nullptr, BCRYPT_ECCPRIVATE_BLOB, blob.data(), cb, &cb, 0) == 0;
}

Bytes EcdhKey::PublicPoint() const {
    Bytes pt;
    if (!key_ || !ExportPublicPoint(key_, pt)) return {};
    return pt;
}

bool EcdhKey::Agree(const Bytes& peerPoint, Bytes& shared) const {
    if (!key_) return false;
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_ECDH_P256_ALGORITHM, nullptr, 0) != 0) return false;
    KeyHandle peer;
    if (!ImportPublicPoint(alg.h, BCRYPT_ECDH_PUBLIC_P256_MAGIC, peerPoint, &peer.h)) return false;
    BCRYPT_SECRET_HANDLE secret = nullptr;
    if (BCryptSecretAgreement(key_, peer.h, &secret, 0) != 0) return false;
    ULONG cb = 0;
    bool ok = false;
    if (BCryptDeriveKey(secret, BCRYPT_KDF_RAW_SECRET, nullptr, nullptr, 0, &cb, 0) == 0 && cb == 32) {
        shared.resize(cb);
        if (BCryptDeriveKey(secret, BCRYPT_KDF_RAW_SECRET, nullptr, shared.data(), cb, &cb, 0) == 0) {
            // Note: Windows CNG BCRYPT_KDF_RAW_SECRET returns the shared secret in little-endian byte order!
            // Reverse to standard big-endian (RFC 6090 / IEEE P1363 / Java KeyAgreement "ECDH") so both
            // Windows and Android derive the exact same 32-byte X coordinate.
            std::reverse(shared.begin(), shared.end());
            ok = true;
        }
    }
    BCryptDestroySecret(secret);
    return ok;
}

bool EphemeralAgree(const Bytes& peerPoint, Bytes& ephemeralPoint, Bytes& shared) {
    EcdhKey eph;
    if (!eph.Generate()) return false;
    ephemeralPoint = eph.PublicPoint();
    return !ephemeralPoint.empty() && eph.Agree(peerPoint, shared);
}

bool EcdsaVerify(const Bytes& publicPoint, const Bytes& message, const Bytes& derSignature) {
    Bytes rawSig;
    if (!DerSigToRaw(derSignature, rawSig)) return false;
    Bytes digest = Sha256(message);
    if (digest.size() != 32) return false;
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_ECDSA_P256_ALGORITHM, nullptr, 0) != 0) return false;
    KeyHandle pub;
    if (!ImportPublicPoint(alg.h, BCRYPT_ECDSA_PUBLIC_P256_MAGIC, publicPoint, &pub.h)) return false;
    return BCryptVerifySignature(pub.h, nullptr, digest.data(), (ULONG)digest.size(), rawSig.data(), (ULONG)rawSig.size(), 0) == 0;
}

EcdsaKey::~EcdsaKey() {
    if (key_) BCryptDestroyKey(key_);
}

bool EcdsaKey::Generate() {
    if (key_) { BCryptDestroyKey(key_); key_ = nullptr; }
    AlgHandle alg;
    if (BCryptOpenAlgorithmProvider(&alg.h, BCRYPT_ECDSA_P256_ALGORITHM, nullptr, 0) != 0) return false;
    if (BCryptGenerateKeyPair(alg.h, &key_, 256, 0) != 0) return false;
    return BCryptFinalizeKeyPair(key_, 0) == 0;
}

Bytes EcdsaKey::PublicPoint() const {
    Bytes pt;
    if (!key_ || !ExportPublicPoint(key_, pt)) return {};
    return pt;
}

bool EcdsaKey::Sign(const Bytes& message, Bytes& derSignature) const {
    if (!key_) return false;
    Bytes digest = Sha256(message);
    if (digest.size() != 32) return false;
    uint8_t raw[64] = {};
    ULONG cb = 0;
    if (BCryptSignHash(key_, nullptr, digest.data(), (ULONG)digest.size(), raw, sizeof(raw), &cb, 0) != 0 || cb != 64) {
        return false;
    }
    derSignature = RawSigToDer(raw);
    return true;
}

}  // namespace pcpr
