// Small dependency-free helpers shared by the unlock service, provider and tests:
// base64url, flat JSON objects, UTF-8/UTF-16 conversion and secure zeroing.
#pragma once

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
#include <windows.h>

#include <cstdint>
#include <map>
#include <string>
#include <vector>

namespace pcpr {

using Bytes = std::vector<uint8_t>;

inline void Wipe(void* data, size_t size) {
    if (data && size) SecureZeroMemory(data, size);
}
inline void Wipe(Bytes& data) {
    Wipe(data.data(), data.size());
    data.clear();
}
inline void Wipe(std::string& data) {
    Wipe(&data[0], data.size());
    data.clear();
}
inline void Wipe(std::wstring& data) {
    Wipe(&data[0], data.size() * sizeof(wchar_t));
    data.clear();
}

// RAII holder for secret byte buffers.
struct SecretBytes {
    Bytes value;
    SecretBytes() = default;
    explicit SecretBytes(Bytes v) : value(std::move(v)) {}
    SecretBytes(const SecretBytes&) = delete;
    SecretBytes& operator=(const SecretBytes&) = delete;
    ~SecretBytes() { Wipe(value); }
};

// ---------------------------------------------------------------- base64url
inline std::string B64UrlEncode(const uint8_t* data, size_t size) {
    static const char* alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    std::string out;
    out.reserve((size + 2) / 3 * 4);
    size_t i = 0;
    while (i + 3 <= size) {
        uint32_t n = (data[i] << 16) | (data[i + 1] << 8) | data[i + 2];
        out += alphabet[(n >> 18) & 63];
        out += alphabet[(n >> 12) & 63];
        out += alphabet[(n >> 6) & 63];
        out += alphabet[n & 63];
        i += 3;
    }
    if (size - i == 1) {
        uint32_t n = data[i] << 16;
        out += alphabet[(n >> 18) & 63];
        out += alphabet[(n >> 12) & 63];
    } else if (size - i == 2) {
        uint32_t n = (data[i] << 16) | (data[i + 1] << 8);
        out += alphabet[(n >> 18) & 63];
        out += alphabet[(n >> 12) & 63];
        out += alphabet[(n >> 6) & 63];
    }
    return out;
}
inline std::string B64UrlEncode(const Bytes& data) { return B64UrlEncode(data.data(), data.size()); }

// Accepts base64url (and standard base64) with or without padding. Returns false on bad input.
inline bool B64UrlDecode(const std::string& text, Bytes& out) {
    out.clear();
    uint32_t buffer = 0;
    int bits = 0;
    size_t padding = 0;
    for (char c : text) {
        int v;
        if (c >= 'A' && c <= 'Z') v = c - 'A';
        else if (c >= 'a' && c <= 'z') v = c - 'a' + 26;
        else if (c >= '0' && c <= '9') v = c - '0' + 52;
        else if (c == '-' || c == '+') v = 62;
        else if (c == '_' || c == '/') v = 63;
        else if (c == '=') { ++padding; continue; }
        else return false;
        if (padding) return false;
        buffer = (buffer << 6) | static_cast<uint32_t>(v);
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            out.push_back(static_cast<uint8_t>((buffer >> bits) & 0xFF));
        }
    }
    // Remaining bits must be zero padding (canonical encoding) and at most 4 bits.
    if (bits >= 6 || (buffer & ((1u << bits) - 1)) != 0) return false;
    return padding <= 2;
}

// ---------------------------------------------------------------- strings
inline std::wstring Utf8ToWide(const std::string& s) {
    if (s.empty()) return std::wstring();
    int n = MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.data(), (int)s.size(), nullptr, 0);
    if (n <= 0) return std::wstring();
    std::wstring w(n, L'\0');
    MultiByteToWideChar(CP_UTF8, MB_ERR_INVALID_CHARS, s.data(), (int)s.size(), &w[0], n);
    return w;
}
inline std::string WideToUtf8(const std::wstring& w) {
    if (w.empty()) return std::string();
    int n = WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), nullptr, 0, nullptr, nullptr);
    if (n <= 0) return std::string();
    std::string s(n, '\0');
    WideCharToMultiByte(CP_UTF8, 0, w.data(), (int)w.size(), &s[0], n, nullptr, nullptr);
    return s;
}

// ---------------------------------------------------------------- flat JSON
// Only flat objects are supported: {"key": "string" | number | true | false | null}.
// Values are kept as strings (literals keep their textual form). Nested values are rejected.
using JsonObject = std::map<std::string, std::string>;

inline void AppendUtf8(std::string& out, uint32_t cp) {
    if (cp < 0x80) out += static_cast<char>(cp);
    else if (cp < 0x800) { out += static_cast<char>(0xC0 | (cp >> 6)); out += static_cast<char>(0x80 | (cp & 0x3F)); }
    else if (cp < 0x10000) { out += static_cast<char>(0xE0 | (cp >> 12)); out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F)); out += static_cast<char>(0x80 | (cp & 0x3F)); }
    else { out += static_cast<char>(0xF0 | (cp >> 18)); out += static_cast<char>(0x80 | ((cp >> 12) & 0x3F)); out += static_cast<char>(0x80 | ((cp >> 6) & 0x3F)); out += static_cast<char>(0x80 | (cp & 0x3F)); }
}

inline bool JsonParseString(const std::string& s, size_t& i, std::string& out) {
    out.clear();
    if (i >= s.size() || s[i] != '"') return false;
    ++i;
    auto hex4 = [&](uint32_t& v) -> bool {
        if (i + 4 > s.size()) return false;
        v = 0;
        for (int k = 0; k < 4; ++k) {
            char c = s[i++];
            v <<= 4;
            if (c >= '0' && c <= '9') v |= c - '0';
            else if (c >= 'a' && c <= 'f') v |= c - 'a' + 10;
            else if (c >= 'A' && c <= 'F') v |= c - 'A' + 10;
            else return false;
        }
        return true;
    };
    while (i < s.size()) {
        char c = s[i++];
        if (c == '"') return true;
        if (static_cast<unsigned char>(c) < 0x20) return false;
        if (c != '\\') { out += c; continue; }
        if (i >= s.size()) return false;
        char e = s[i++];
        switch (e) {
        case '"': out += '"'; break;
        case '\\': out += '\\'; break;
        case '/': out += '/'; break;
        case 'b': out += '\b'; break;
        case 'f': out += '\f'; break;
        case 'n': out += '\n'; break;
        case 'r': out += '\r'; break;
        case 't': out += '\t'; break;
        case 'u': {
            uint32_t cp;
            if (!hex4(cp)) return false;
            if (cp >= 0xD800 && cp <= 0xDBFF) {
                uint32_t lo;
                if (i + 2 > s.size() || s[i] != '\\' || s[i + 1] != 'u') return false;
                i += 2;
                if (!hex4(lo) || lo < 0xDC00 || lo > 0xDFFF) return false;
                cp = 0x10000 + ((cp - 0xD800) << 10) + (lo - 0xDC00);
            } else if (cp >= 0xDC00 && cp <= 0xDFFF) {
                return false;
            }
            AppendUtf8(out, cp);
            break;
        }
        default: return false;
        }
    }
    return false;
}

inline bool JsonParseFlat(const std::string& s, JsonObject& out) {
    out.clear();
    size_t i = 0;
    auto ws = [&]() { while (i < s.size() && (s[i] == ' ' || s[i] == '\t' || s[i] == '\r' || s[i] == '\n')) ++i; };
    ws();
    if (i >= s.size() || s[i] != '{') return false;
    ++i;
    ws();
    if (i < s.size() && s[i] == '}') { ++i; ws(); return i == s.size(); }
    while (true) {
        ws();
        std::string key, value;
        if (!JsonParseString(s, i, key)) return false;
        ws();
        if (i >= s.size() || s[i] != ':') return false;
        ++i;
        ws();
        if (i >= s.size()) return false;
        if (s[i] == '"') {
            if (!JsonParseString(s, i, value)) return false;
        } else {
            size_t start = i;
            while (i < s.size() && (isalnum(static_cast<unsigned char>(s[i])) || s[i] == '-' || s[i] == '+' || s[i] == '.')) ++i;
            if (i == start) return false;  // objects/arrays are not supported
            value = s.substr(start, i - start);
        }
        if (out.count(key)) return false;  // duplicate keys are ambiguous
        out[key] = value;
        ws();
        if (i >= s.size()) return false;
        if (s[i] == ',') { ++i; continue; }
        if (s[i] == '}') { ++i; ws(); return i == s.size(); }
        return false;
    }
}

inline std::string JsonEscape(const std::string& v) {
    std::string out;
    out.reserve(v.size() + 2);
    for (unsigned char c : v) {
        switch (c) {
        case '"': out += "\\\""; break;
        case '\\': out += "\\\\"; break;
        case '\n': out += "\\n"; break;
        case '\r': out += "\\r"; break;
        case '\t': out += "\\t"; break;
        default:
            if (c < 0x20) {
                char buf[8];
                sprintf_s(buf, "\\u%04x", c);
                out += buf;
            } else {
                out += static_cast<char>(c);
            }
        }
    }
    return out;
}

class JsonWriter {
public:
    JsonWriter& Str(const std::string& key, const std::string& value) {
        Sep(); body_ += "\"" + JsonEscape(key) + "\":\"" + JsonEscape(value) + "\""; return *this;
    }
    JsonWriter& Raw(const std::string& key, const std::string& literal) {
        Sep(); body_ += "\"" + JsonEscape(key) + "\":" + literal; return *this;
    }
    JsonWriter& Bool(const std::string& key, bool v) { return Raw(key, v ? "true" : "false"); }
    JsonWriter& Int(const std::string& key, long long v) { return Raw(key, std::to_string(v)); }
    std::string Build() const { return "{" + body_ + "}"; }
    // Wipes the internal buffer (used when the JSON contains a secret).
    void WipeBuffer() { Wipe(body_); }
    ~JsonWriter() { Wipe(body_); }

private:
    void Sep() { if (!body_.empty()) body_ += ","; }
    std::string body_;
};

inline std::string Get(const JsonObject& o, const char* key) {
    auto it = o.find(key);
    return it == o.end() ? std::string() : it->second;
}

}  // namespace pcpr
